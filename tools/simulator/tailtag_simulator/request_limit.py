"""The per-player limit and request expiry on Staging (#508, `request-limit` v1).

Eight owners with five suits each give 40 suits. Owners never decide, so every
request stays pending. Provisioning moves the run convention's review deadline
`REVIEW_DEADLINE_OFFSET_SECONDS` into the run. Three journeys run:

- `normal_play`: one player creates one request every 30 seconds for 10 minutes.
  Any 429 fails the journey.
- `abuse_limit`: a second player submits to a new suit every 2 seconds. Creates
  1 to 30 succeed, the 31st gets 429 `rate_limited`, and the next submission
  after `Retry-After` succeeds.
- `expiry`: after the deadline, the request lists are empty and approval returns
  409 `review_window_closed`.

Output lines carry only fixed names and codes, like the journeys.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Final, Literal

import httpx

from tailtag_simulator.client import ApiClient, Reply, RequestFailed, TransportFailed
from tailtag_simulator.fixtures import FixtureChannel, run_provisioned
from tailtag_simulator.gameplay import (
    StepFailed,
    arm_request_session,
    get_value,
    list_items,
    positive_number,
    step,
    text_value,
)
from tailtag_simulator.journeys import JourneyResult, journey_lines
from tailtag_simulator.limits import REVIEW_DEADLINE_OFFSET_SECONDS
from tailtag_simulator.pool import LeaseChannel
from tailtag_simulator.population_reconciliation import (
    PopulationExpectations,
    PopulationInspectionChannel,
    RequestFact,
    population_reconciliation_lines,
    reconcile_population,
)
from tailtag_simulator.reports import RunReport
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime, active_runtime
from tailtag_simulator.smoke import guarded_stage

OWNERS: Final = 8
FURSUITS_PER_OWNER: Final = 5
PLAYERS: Final = 2
NORMAL_REQUESTS: Final = 20
NORMAL_SPACING_SECONDS: Final = 30
LIMIT: Final = 30
ABUSE_SPACING_SECONDS: Final = 2
EXPIRY_MARGIN_SECONDS: Final = 5
REQUESTS_PATH: Final = "/api/catches/requests/"
INCOMING_PATH: Final = "/api/catches/incoming-requests/"


async def _ready(reply: Reply) -> Reply:
    return reply


class _Limit:
    def __init__(
        self,
        owners: tuple[ApiClient, ...],
        players: tuple[ApiClient, ...],
        *,
        sleep: Callable[[float], Awaitable[None]],
        wall: Callable[[], float],
    ) -> None:
        self.owners, self.players = owners, players
        self.sleep, self.wall = sleep, wall
        self.convention = 0
        self.payloads: list[tuple[int, str]] = []  # (fursuit id, payload)
        self.expectations = PopulationExpectations()
        self.deadline: float | None = None

    async def arm(self) -> None:
        body = await step(
            "convention",
            self.players[0].get("/api/conventions/active/"),
            200,
            shape=lambda b: positive_number(b, "enrollment", "convention", "id") > 0,
        )
        self.convention = positive_number(body, "enrollment", "convention", "id")
        for ordinal, owner in enumerate(self.owners):
            owned = await step("fursuits", owner.get("/api/fursuits/"), 200)
            ids = sorted(positive_number(row, "id") for row in list_items(owned))
            if len(ids) != FURSUITS_PER_OWNER or 0 in ids:
                raise StepFailed("fursuits", "200/-", "200/shape")
            for fursuit in ids:
                self.expectations.target_owners[fursuit] = f"owner{ordinal}"
                activation = (
                    f"/api/conventions/{self.convention}/fursuit-activations/{fursuit}/"
                )
                await step(
                    "activate",
                    owner.put(activation, {"is_active": True}),
                    200,
                    shape=lambda b: get_value(b, "is_active") is True,
                )
                payload = await arm_request_session(
                    owner, activation, fursuit, automatic=False
                )
                self.payloads.append((fursuit, payload))

    async def pending(self, player: int, position: int, name: str) -> None:
        fursuit, payload = self.payloads[position]
        label = f"attendee{player}"
        pair = (label, fursuit)
        self.expectations.attempts.add(pair)
        body = await step(
            name,
            self.players[player].post(REQUESTS_PATH, {"payload": payload}),
            201,
            "pending",
            shape=lambda b: positive_number(b, "request", "id") > 0,
        )
        self.expectations.requests[pair] = RequestFact(
            positive_number(body, "request", "id"),
            "pending",
            text_value(body, "request", "requested_at"),
        )
        self.expectations.pairs[pair] = "forbidden"
        deadline = text_value(body, "request", "review_deadline_at")
        if self.deadline is None and deadline:
            self.deadline = datetime.fromisoformat(deadline).timestamp()

    async def normal_play(self) -> None:
        start = self.wall()
        for position in range(NORMAL_REQUESTS):
            await self._at(start + position * NORMAL_SPACING_SECONDS)
            await self.pending(0, position, "submit")

    async def abuse_limit(self) -> None:
        start = self.wall()
        for position in range(LIMIT):
            await self._at(start + position * ABUSE_SPACING_SECONDS)
            await self.pending(1, position, "submit")
        await self._at(start + LIMIT * ABUSE_SPACING_SECONDS)
        fursuit, payload = self.payloads[LIMIT]
        self.expectations.attempts.add(("attendee1", fursuit))
        try:
            reply = await self.players[1].post(REQUESTS_PATH, {"payload": payload})
        except (TransportFailed, RequestFailed):
            raise StepFailed("submit_limited", "429/rate_limited", "error") from None
        wait = positive_number(reply.body, "retry_after_seconds")
        await step(
            "submit_limited",
            _ready(reply),
            429,
            "rate_limited",
            shape=lambda _b: wait > 0 and reply.retry_after == wait,
        )
        self.expectations.pairs[("attendee1", fursuit)] = "forbidden"
        await self.sleep(wait + 1)
        await self.pending(1, LIMIT + 1, "submit_after_wait")

    async def expiry(self) -> None:
        if self.deadline is None:
            raise StepFailed("deadline", "200/-", "200/shape")
        # A few seconds of margin absorb clock skew between host and server.
        await self._at(self.deadline + EXPIRY_MARGIN_SECONDS)
        for client in self.players:
            await step(
                "player_list",
                client.get(f"{REQUESTS_PATH}?convention_id={self.convention}"),
                200,
                shape=lambda b: list_items(get_value(b, "results")) == [],
            )
        await step(
            "owner_list",
            self.owners[0].get(f"{INCOMING_PATH}?convention_id={self.convention}"),
            200,
            shape=lambda b: list_items(get_value(b, "results")) == [],
        )
        fursuit = self.payloads[0][0]
        request = self.expectations.requests[("attendee0", fursuit)].id
        owner = int(self.expectations.target_owners[fursuit].removeprefix("owner"))
        reply = await self.owners[owner].post(f"{INCOMING_PATH}{request}/approve/")
        # Cleanup can delete the row after the deadline. The contract treats
        # 404 `request_not_found` like 409 `review_window_closed`.
        if reply.status == 404:
            await step("approve_closed", _ready(reply), 404, "request_not_found")
        else:
            await step("approve_closed", _ready(reply), 409, "review_window_closed")

    async def _at(self, moment: float) -> None:
        remaining = moment - self.wall()
        if remaining > 0:
            await self.sleep(remaining)


async def _journey(name: str, work: Awaitable[None]) -> JourneyResult:
    try:
        await work
    except StepFailed as failed:
        return JourneyResult(name, failed.step, failed.expected, failed.observed)
    except SafetyAborted:
        # The other journey aborted the run; this one stopped without an answer.
        return JourneyResult(name, "aborted", "-", "error")
    return JourneyResult(name, None, None, None)


async def simulate_request_limit(
    owners: tuple[ApiClient, ...],
    players: tuple[ApiClient, ...],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    wall: Callable[[], float] = time.time,
) -> tuple[tuple[JourneyResult, ...], _Limit]:
    """Arm every suit, run both players at once, then check expiry."""
    limit = _Limit(owners, players, sleep=sleep, wall=wall)
    await limit.arm()
    normal, abuse = await asyncio.gather(
        _journey("normal_play", limit.normal_play()),
        _journey("abuse_limit", limit.abuse_limit()),
    )
    expiry = await _journey("expiry", limit.expiry())
    return (normal, abuse, expiry), limit


def _role(actor: str | None) -> str | None:
    """Report roles name players, not population attendees."""
    if actor is None or not actor.startswith("attendee"):
        return actor
    return "player" + actor.removeprefix("attendee")


async def run_request_limit(
    pool: str,
    *,
    prompt_secret: Callable[[], str],
    lease_channel: LeaseChannel,
    fixture_channel: FixtureChannel,
    inspection_channel: PopulationInspectionChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    wall: Callable[[], float] = time.time,
) -> int:
    """Run the limit scenario on Staging, reconcile it, and return the exit code."""
    run = report.run_id if report is not None else run_id or str(uuid.uuid4())

    async def simulate(
        origin: str, clients: tuple[ApiClient, ...], indexes: tuple[int, ...]
    ) -> Literal["pass", "journeys", "reconciliation"]:
        del origin
        async with guarded_stage("simulation", report):
            results, limit = await simulate_request_limit(
                clients[:OWNERS], clients[OWNERS:], sleep=sleep, wall=wall
            )
        failed = sum(result.failed_step is not None for result in results)
        if report is not None:
            report.record_results(
                journeys={
                    "items": [
                        {
                            "name": result.name,
                            "status": "passed"
                            if result.failed_step is None
                            else "failed",
                        }
                        for result in results
                    ],
                    "passed": len(results) - failed,
                    "failed": failed,
                    "reason": None,
                }
            )
        # Unlike journeys, nothing printed these lines before an abort.
        for line in journey_lines(results):
            emit(line)
        labels = tuple(f"owner{n}" for n in range(OWNERS)) + tuple(
            f"attendee{n}" for n in range(PLAYERS)
        )
        async with guarded_stage("reconciliation", report):
            checked = await reconcile_population(
                limit.expectations,
                dict(zip(labels, clients, strict=True)),
                dict(zip(labels, indexes, strict=True)),
                inspection_channel,
                pool=pool,
                run_id=run,
                convention=limit.convention,
                request_flow=True,
            )
        if report is not None:
            report.record_results(
                checks={
                    "items": [
                        {
                            "check": item.check,
                            "journey": None,
                            "role": _role(item.actor),
                            "expected": item.expected,
                            "observed": item.observed,
                        }
                        for item in checked.discrepancies
                    ],
                    "count": checked.count,
                    "reason": None,
                }
            )
        for line in population_reconciliation_lines(checked):
            emit(line)
        if checked.integrity_failed:
            safety_runtime = active_runtime()
            if safety_runtime is not None:
                safety_runtime.abort("correctness")
            return "reconciliation"
        if failed:
            return "journeys"
        return "pass" if checked.passed else "reconciliation"

    return await run_provisioned(
        pool,
        OWNERS,
        FURSUITS_PER_OWNER,
        PLAYERS,
        0,
        prompt_secret=prompt_secret,
        lease_channel=lease_channel,
        fixture_channel=fixture_channel,
        emit=emit,
        clerk_transport=clerk_transport,
        api_transport=api_transport,
        clock=clock,
        run_id=run,
        report=report,
        safety=safety,
        simulate_and_reconcile=simulate,
        # The run outlasts one lease while it waits for the deadline.
        renew_leases=True,
        review_deadline_offset_seconds=REVIEW_DEADLINE_OFFSET_SECONDS,
    )
