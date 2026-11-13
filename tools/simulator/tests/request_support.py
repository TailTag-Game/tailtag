"""An in-memory catch request API behind the real HTTP client, for #508 tests.

The fake follows the reusable TailTag contract closely enough for the simulator:
one pending request per trio, automatic approval, owner approve and decline,
tag replacement, stopped sessions, and the existing-result check before the
target checks. Faults sit on the HTTP boundary only.
"""

import asyncio
import heapq
import json
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from tailtag_simulator.behavior import PopulationContext
from tailtag_simulator.client import open_client
from tailtag_simulator.population_reconciliation import (
    PopulationReconciliationResult,
    reconcile_population,
)
from tailtag_simulator.request_behavior import (
    RequestPopulationRun,
    simulate_request_population,
)
from tailtag_simulator.safety import SafetyRuntime
from tailtag_simulator.traffic import Clock, TrafficRuntime
from tailtag_simulator.traffic_config import resolve_request_traffic_config


class VirtualTime:
    """Wake concurrent sleepers at their own deadlines, rather than summing sleeps.

    The driver yields ready HTTP/tasks before advancing to the next sleeping task.
    No event-loop or global asyncio monkeypatch is used.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.epoch = datetime(2026, 10, 3, 12, tzinfo=UTC).timestamp()
        self.pending: list[tuple[float, int, asyncio.Future[None]]] = []
        self.ordinal = 0
        self.revision = 0

    @property
    def clock(self) -> Clock:
        return Clock(
            monotonic=lambda: self.now,
            sleep=self.sleep,
            wall_time=lambda: self.epoch + self.now,
        )

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        self.ordinal += 1
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self.pending, (self.now + seconds, self.ordinal, future))
        self.revision += 1
        try:
            await future
        finally:
            self.revision += 1

    async def drive(self) -> None:
        while True:
            # New sleepers and cancellations mean runnable request/cleanup chains
            # still progress. Settle that activity before advancing server time.
            revision = self.revision
            idle = 0
            while idle < 30:
                await asyncio.sleep(0)
                if self.revision != revision:
                    revision = self.revision
                    idle = 0
                else:
                    idle += 1
            while self.pending and self.pending[0][2].done():
                heapq.heappop(self.pending)
            if not self.pending:
                continue
            self.now = max(self.now, self.pending[0][0])
            while self.pending and self.pending[0][0] <= self.now:
                _, _, future = heapq.heappop(self.pending)
                if not future.done():
                    future.set_result(None)


CONVENTION = 4242
PERSONAS = ("casual", "active", "heavy", "retry_prone")
NOT_FOUND = {"code": "catch_target_unavailable", "detail": "Not found."}


def request_config(
    *, actors: int = 1, family: str = "baseline", **overrides: object
) -> dict[str, object]:
    return resolve_request_traffic_config(
        {
            "pool": "alpha",
            "family": family,
            "normal_owners": 0 if family == "hotspot" else 1,
            "popular_owners": 1 if family == "hotspot" else 0,
            "fursuits": 2,
            "casual": actors,
            "active": 0,
            "heavy": 0,
            "retry_prone": 0,
            "traffic": {
                "segments": [{"duration_seconds": 1, "start": 0, "end": 0}],
                "bursts": [{"at_seconds": 0.01, "count": actors}],
                "think_seconds": 0,
                "max_entries": actors,
            },
            **overrides,
        }
    )


@dataclass
class Row:
    id: int
    player: str
    fursuit: int
    state: str
    requested_at: str


@dataclass
class Suit:
    id: int
    owner: str
    payloads: list[str] = field(default_factory=list[str])
    version: int = 0
    mode: str = "manual"
    session: bool = False


class RequestWorld:
    """Owners own `fursuits` suits each; attendees catch through the request API."""

    def __init__(self, config: Mapping[str, object], time: VirtualTime | None = None):
        self.time = time or VirtualTime()
        owners = int(str(config["normal_owners"])) + int(str(config["popular_owners"]))
        attendees = sum(int(str(config[name])) for name in PERSONAS)
        per_owner = int(str(config["fursuits"]))
        self.indexes = {
            **{f"owner{n}": 17 + n for n in range(owners)},
            **{f"attendee{n}": 31 + n for n in range(attendees)},
        }
        self.suits: dict[int, Suit] = {}
        for owner in range(owners):
            for position in range(per_owner):
                suit_id = 500 + owner * 10 + position
                self.suits[suit_id] = Suit(suit_id, f"owner{owner}")
        self.rows: list[Row] = []
        self.catches: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str, str]] = []
        self.lost_submits = 0
        self.refuse_submits = 0
        self.duplicate_catch = False
        # Changes server state after the run, before the inspection reads it.
        self.tamper: Callable[[RequestWorld], None] | None = None
        self.overlap = False
        self.submitting = 0
        self.release = asyncio.Event()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.send)

    def _at(self) -> str:
        moment = datetime.fromtimestamp(self.time.clock.wall_time(), UTC)
        return moment.isoformat().replace("+00:00", "Z")

    def _suit(self, payload: object) -> tuple[Suit | None, bool]:
        """Return the suit a payload names, and whether it is the current tag."""
        for suit in self.suits.values():
            if payload in suit.payloads:
                return suit, payload == suit.payloads[-1]
        return None, False

    def _summary(self, suit: Suit) -> dict[str, Any]:
        return {
            "id": suit.id,
            "tailtag_id": f"00000000-0000-4000-8000-{suit.id:012d}",
            "name": f"Suit {suit.id}",
            "photo_url": "https://media.test/p.png",
        }

    def _request(self, row: Row) -> dict[str, Any]:
        return {
            "id": row.id,
            "fursuit": self._summary(self.suits[row.fursuit]),
            "convention_id": CONVENTION,
            "state": "unavailable" if row.state == "invalidated" else row.state,
            "requested_at": row.requested_at,
            "review_deadline_at": "2026-10-06T04:00:00Z",
        }

    def _catch_for(self, player: str, fursuit: int) -> dict[str, Any] | None:
        return next(
            (
                c
                for c in self.catches
                if c["player"] == player and c["fursuit"] == fursuit
            ),
            None,
        )

    def _catch(self, catch: dict[str, Any]) -> dict[str, Any]:
        suit = self.suits[catch["fursuit"]]
        summary = self._summary(suit)
        return {
            "id": catch["id"],
            "caught_at": catch["caught_at"],
            "approved_at": catch["approved_at"],
            "convention_id": CONVENTION,
            "fursuit": {k: summary[k] for k in ("tailtag_id", "name", "photo_url")},
        }

    def _approve(self, row: Row) -> dict[str, Any]:
        row.state = "approved"
        catch: dict[str, Any] = {
            "id": 9000 + len(self.catches),
            "player": row.player,
            "fursuit": row.fursuit,
            "caught_at": row.requested_at,
            "approved_at": self._at(),
        }
        self.catches.append(catch)
        if self.duplicate_catch:
            self.catches.append({**catch, "id": catch["id"] + 500})
        return catch

    async def send(self, request: httpx.Request) -> httpx.Response:
        actor = request.headers["Authorization"].removeprefix("Bearer ")
        path, method = request.url.path, request.method
        self.calls.append((actor, method, path))
        body: Any = json.loads(request.content) if request.content else {}
        if path == "/api/catches/requests/" and method == "POST":
            if self.overlap:
                self.submitting += 1
                if self.submitting == 2:
                    self.release.set()
                try:
                    await self.release.wait()
                finally:
                    self.submitting -= 1
            if self.refuse_submits:
                self.refuse_submits -= 1
                return httpx.Response(
                    429,
                    headers={"Retry-After": "10"},
                    json={
                        "code": "rate_limited",
                        "detail": "Try again later.",
                        "retry_after_seconds": 10,
                    },
                )
            response = self.submit(actor, body)
            if self.lost_submits:
                self.lost_submits -= 1
                raise httpx.ReadError("SENTINEL lost submit", request=request)
            return response
        response = self.route(actor, method, path, body, request.url.params)
        assert response is not None, f"unsupported: {method} {path}"
        return response

    def submit(self, actor: str, body: Mapping[str, Any]) -> httpx.Response:
        suit, current = self._suit(body.get("payload"))
        if suit is None:
            return httpx.Response(404, json=NOT_FOUND)
        catch = self._catch_for(actor, suit.id)
        if catch is not None:
            return httpx.Response(
                200,
                json={
                    "outcome": "already_caught",
                    "request": None,
                    "catch": self._catch(catch),
                },
            )
        pending = next(
            (
                r
                for r in self.rows
                if r.player == actor and r.fursuit == suit.id and r.state == "pending"
            ),
            None,
        )
        if pending is not None:
            return httpx.Response(
                200,
                json={
                    "outcome": "already_pending",
                    "request": self._request(pending),
                    "catch": None,
                },
            )
        if not current or not suit.session:
            return httpx.Response(404, json=NOT_FOUND)
        row = Row(1000 + len(self.rows), actor, suit.id, "pending", self._at())
        self.rows.append(row)
        if suit.mode == "automatic":
            catch = self._approve(row)
            return httpx.Response(
                201,
                json={
                    "outcome": "approved",
                    "request": self._request(row),
                    "catch": self._catch(catch),
                },
            )
        return httpx.Response(
            201,
            json={"outcome": "pending", "request": self._request(row), "catch": None},
        )

    def route(
        self,
        actor: str,
        method: str,
        path: str,
        body: Mapping[str, Any],
        params: httpx.QueryParams,
    ) -> httpx.Response | None:
        parts = path.strip("/").split("/")
        if path == "/api/me/":
            return httpx.Response(200, json={"id": 1000 + self.indexes[actor]})
        if path == "/api/conventions/active/":
            return httpx.Response(
                200,
                json={
                    "enrollment": {"convention": {"id": CONVENTION}, "is_active": True}
                },
            )
        if path == "/api/fursuits/" and method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": s.id,
                        "tailtag_id": self._summary(s)["tailtag_id"],
                        "is_enabled": True,
                    }
                    for s in self.suits.values()
                    if s.owner == actor
                ],
            )
        if path == f"/api/conventions/{CONVENTION}/fursuit-activations/":
            return httpx.Response(
                200,
                json=[
                    {
                        "fursuit_id": s.id,
                        "convention_id": CONVENTION,
                        "is_eligible": True,
                    }
                    for s in self.suits.values()
                    if s.owner == actor
                ],
            )
        if parts[:3] == ["api", "conventions", str(CONVENTION)] and len(parts) >= 5:
            suit = self.suits[int(parts[4])]
            if len(parts) == 5 and method == "PUT":
                return httpx.Response(
                    200,
                    json={
                        "is_active": body["is_active"],
                        "fursuit_id": suit.id,
                        "convention_id": CONVENTION,
                    },
                )
            if parts[5:] == ["catch-session"] and method == "PUT":
                suit.session = bool(body["is_active"])
                expires = datetime.fromtimestamp(
                    self.time.clock.wall_time() + 43200, UTC
                )
                return httpx.Response(
                    200,
                    json={"is_active": suit.session, "expires_at": expires.isoformat()},
                )
        if parts[:2] == ["api", "fursuits"] and len(parts) >= 3:
            suit = self.suits[int(parts[2])]
            assert suit.owner == actor
            if len(parts) == 3 and method == "PATCH":
                suit.mode = body["catch_approval_mode"]
                return httpx.Response(
                    200, json={"id": suit.id, "catch_approval_mode": suit.mode}
                )
            if parts[3:] == ["tag"] and method == "GET":
                if not suit.payloads:
                    suit.version = 1
                    suit.payloads.append(f"https://tailtag.app/t#tag-{suit.id}-1")
                return httpx.Response(200, json=self._tag(suit))
            if parts[3:] == ["tag", "replace"] and method == "POST":
                assert body["expected_version"] == suit.version
                suit.version += 1
                suit.payloads.append(
                    f"https://tailtag.app/t#tag-{suit.id}-{suit.version}"
                )
                return httpx.Response(200, json=self._tag(suit))
        if path == "/api/catches/preview/" and method == "POST":
            suit, current = self._suit(body.get("payload"))
            if suit is None or not current or not suit.session:
                return httpx.Response(404, json=NOT_FOUND)
            return httpx.Response(
                200, json={"fursuit": self._summary(suit), "convention_id": CONVENTION}
            )
        if path == "/api/catches/" and method == "GET":
            rows = self.history(actor)
            return httpx.Response(
                200,
                json={
                    "catch_count": len(rows),
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": c["id"],
                            "fursuit": {"id": c["fursuit"]},
                            "convention": {"id": CONVENTION},
                            "caught_at": c["caught_at"],
                        }
                        for c in rows
                    ],
                },
            )
        if path == "/api/catches/requests/" and method == "GET":
            assert params.get("convention_id") == str(CONVENTION)
            rows = [r for r in reversed(self.rows) if r.player == actor]
            return httpx.Response(
                200, json={"results": [self._request(r) for r in rows]}
            )
        if path == "/api/catches/incoming-requests/" and method == "GET":
            rows = [
                r for r in reversed(self.rows) if self.suits[r.fursuit].owner == actor
            ]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            **self._request(r),
                            "player": {"display_name": "", "handle": ""},
                        }
                        for r in rows
                    ]
                },
            )
        if parts[:3] == ["api", "catches", "incoming-requests"] and method == "POST":
            row = next(r for r in self.rows if r.id == int(parts[3]))
            assert self.suits[row.fursuit].owner == actor
            if parts[4] == "approve":
                if row.state != "pending":
                    return httpx.Response(
                        409, json={"code": "request_state_changed", "detail": "x"}
                    )
                catch = self._approve(row)
                return httpx.Response(
                    200,
                    json={"request": self._request(row), "catch": self._catch(catch)},
                )
            if parts[4] == "decline":
                row.state = "declined"
                return httpx.Response(200, json=self._request(row))
        return None

    def _tag(self, suit: Suit) -> dict[str, Any]:
        return {
            "fursuit_id": suit.id,
            "state": "current",
            "tag_version": suit.version,
            "payload": suit.payloads[-1],
        }

    def history(self, actor: str) -> list[dict[str, Any]]:
        return [c for c in self.catches if c["player"] == actor]

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        assert pool and run_id and dict(identities) == self.indexes
        if self.tamper is not None:
            self.tamper(self)
            self.tamper = None
        index = self.indexes
        return {
            "catches": [
                {
                    "id": c["id"],
                    "catcher": index[c["player"]],
                    "fursuit": c["fursuit"],
                    "fursuit_owner": index[self.suits[c["fursuit"]].owner],
                    "run_convention": True,
                    "provenance": True,
                    "in_window": True,
                    "caught_at": c["caught_at"],
                }
                for c in self.catches
            ],
            "fursuits": [],
            "fixture_photos_unchanged": True,
            "avatars": [],
            "requests": [
                {
                    "id": r.id,
                    "player": index[r.player],
                    "fursuit": r.fursuit,
                    "run_convention": True,
                    "state": r.state,
                    "requested_at": r.requested_at,
                }
                for r in self.rows
            ],
        }


def run_requests(
    world: RequestWorld,
    config: Mapping[str, object],
    *,
    seed: int = 728,
    reconcile: bool = False,
    safety: SafetyRuntime | None = None,
) -> tuple[RequestPopulationRun, PopulationReconciliationResult | None]:
    async def execute() -> tuple[
        RequestPopulationRun, PopulationReconciliationResult | None
    ]:
        driver = asyncio.create_task(world.time.drive())
        try:
            async with AsyncExitStack() as stack:
                clients = {
                    actor: await stack.enter_async_context(
                        open_client(
                            "https://staging.tailtag.app",
                            token=actor,
                            transport=world.transport,
                        )
                    )
                    for actor in world.indexes
                }
                owners = [a for a in world.indexes if a.startswith("owner")]
                attendees = [a for a in world.indexes if a.startswith("attendee")]
                context = PopulationContext(
                    owners=tuple(clients[a] for a in owners),
                    attendees=tuple(clients[a] for a in attendees),
                )
                runtime = TrafficRuntime(
                    config, clock=world.time.clock, request_flow=True
                )
                with safety.scope() if safety is not None else nullcontext():
                    result = await asyncio.wait_for(
                        simulate_request_population(
                            context,
                            config,
                            seed,
                            clock=world.time.clock,
                            runtime=runtime,
                        ),
                        timeout=10,
                    )
                compared = None
                if reconcile:
                    compared = await reconcile_population(
                        result.population.expectations,
                        clients,
                        world.indexes,
                        world,
                        pool="alpha",
                        run_id="aaaaaaaa-1111-4111-8111-111111111111",
                        convention=result.population.convention,
                        request_flow=True,
                    )
                return result, compared
        finally:
            driver.cancel()
            await asyncio.gather(driver, return_exceptions=True)

    return asyncio.run(execute())
