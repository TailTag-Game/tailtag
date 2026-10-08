"""HTTP, inspection and coherent virtual-time boundaries for traffic behavior."""

import asyncio
import heapq
import json
from collections.abc import Mapping
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any

import httpx
from population_support import PopulationWorld

from tailtag_simulator.behavior import PopulationContext
from tailtag_simulator.client import open_client
from tailtag_simulator.population_reconciliation import (
    PopulationReconciliationResult,
    reconcile_population,
)
from tailtag_simulator.traffic import Clock
from tailtag_simulator.traffic_behavior import (
    TrafficPopulationRun,
    simulate_traffic_population,
)
from tailtag_simulator.traffic_config import resolve_traffic_config

CONFIRM = "/api/catches/confirm/"
AT = "2026-10-03T12:00:00Z"


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


def config_for(
    *, actors: int = 1, family: str = "baseline", **overrides: object
) -> dict[str, object]:
    return resolve_traffic_config(
        {
            "pool": "alpha",
            "family": family,
            "normal_owners": 0 if family == "hotspot" else 1,
            "popular_owners": 1 if family == "hotspot" else 0,
            "fursuits": 1,
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


class TrafficWorld(PopulationWorld):
    """Reuse existing wire/domain fixtures; extend only external timing/failures."""

    def __init__(
        self, config: Mapping[str, object], time: VirtualTime | None = None
    ) -> None:
        super().__init__(config)
        self.time = time or VirtualTime()
        self.times: list[tuple[str, str, str, float]] = []
        self.responses: list[tuple[str, str, int, Any]] = []
        self.expires: dict[int, float] = {}
        self.lost_first = False
        self.exhaust_actor: str | None = None
        self.history_transients = 0
        self.failed_history_actor: str | None = None
        self.protected_fault: str | None = None
        self.context_failure = False
        self.overlap = False
        self.confirming = 0
        self.confirm_peak = 0
        self.release = asyncio.Event()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.send)

    async def send(self, request: httpx.Request) -> httpx.Response:
        actor = request.headers["Authorization"].removeprefix("Bearer ")
        path = request.url.path
        self.times.append((actor, request.method, path, self.time.now))
        if path == CONFIRM and self.overlap:
            self.confirming += 1
            self.confirm_peak = max(self.confirm_peak, self.confirming)
            if self.confirming == 2:
                self.release.set()
            try:
                await self.release.wait()
            finally:
                self.confirming -= 1
        if (
            path == "/api/catches/"
            and actor.startswith("attendee")
            and self.history_transients
        ):
            self.failed_history_actor = self.failed_history_actor or actor
        history_failure = (
            path == "/api/catches/"
            and actor == self.failed_history_actor
            and self.history_transients > 0
        )
        context_failure = self.context_failure and path == "/api/conventions/active/"
        if (
            (path == CONFIRM and self.exhaust_actor == actor)
            or history_failure
            or context_failure
        ):
            self.history_transients -= int(history_failure)
            self.requests.append(
                (
                    actor,
                    request.method,
                    path,
                    json.loads(request.content) if request.content else {},
                )
            )
            response = httpx.Response(503, json={"detail": "SENTINEL"})
        else:
            response = super().serve(request)
        if path.endswith("/catch-session/") and request.method == "PUT":
            body = json.loads(response.content)
            if body["is_active"]:
                target = int(path.split("/")[-3])
                self.expires[target] = self.time.clock.wall_time() + 43200
                body["expires_at"] = datetime.fromtimestamp(
                    self.expires[target], UTC
                ).isoformat()
                response = httpx.Response(200, json=body)
        if path == CONFIRM:
            if self.protected_fault == "redirect":
                response = httpx.Response(
                    307, headers={"location": "https://evil.test"}
                )
            elif self.protected_fault == "oversize":
                response = httpx.Response(200, content=b"x" * 65_537)
            elif self.protected_fault == "malformed":
                response = httpx.Response(201, json={"outcome": "created", "catch": {}})
        try:
            body: Any = json.loads(response.content) if response.content else None
        except ValueError:
            body = None
        self.responses.append((actor, path, response.status_code, body))
        if path == CONFIRM and self.lost_first:
            self.lost_first = False
            raise httpx.ReadError("SENTINEL committed response lost", request=request)
        return response

    def route(self, method: str, path: str, index: int) -> httpx.Response | None:
        # The fake server checks its own expiration clock; no simulator state
        # mutation or shortened public session lifetime manufactures expiry.
        for target, deadline in self.expires.items():
            if self.time.clock.wall_time() >= deadline:
                self.gameplay.sessions[target] = False
        return super().route(method, path, index)


def run_traffic(
    world: TrafficWorld,
    config: Mapping[str, object],
    *,
    seed: int = 728,
    check_joined: bool = False,
) -> tuple[TrafficPopulationRun, PopulationReconciliationResult]:
    async def execute() -> tuple[TrafficPopulationRun, PopulationReconciliationResult]:
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
                context = PopulationContext(
                    owners=tuple(
                        clients[f"owner{n}"] for n in range(len(world.owners))
                    ),
                    attendees=tuple(
                        clients[f"attendee{n}"] for n in range(len(world.attendees))
                    ),
                )
                previous_tasks = set(asyncio.all_tasks())
                result = await asyncio.wait_for(
                    simulate_traffic_population(
                        context, config, seed, clock=world.time.clock
                    ),
                    timeout=5,
                )
                if check_joined:
                    assert set(asyncio.all_tasks()) <= previous_tasks
                compared = await reconcile_population(
                    result.population.expectations,
                    clients,
                    world.indexes,
                    world,
                    pool="alpha",
                    run_id="aaaaaaaa-1111-4111-8111-111111111111",
                    convention=result.population.convention,
                )
                return result, compared
        finally:
            driver.cancel()
            await asyncio.gather(driver, return_exceptions=True)

    return asyncio.run(execute())
