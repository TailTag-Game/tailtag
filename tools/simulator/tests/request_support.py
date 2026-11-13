"""Virtual time and HTTP-boundary faults for #508 request-flow load tests.

The request rules live once, in the shared `Gameplay` fake (journey_support),
which journeys, convention runs, and the limit scenario also use.
`RequestWorld` adds only what load tests need on top of that fake: a virtual
clock, lost and refused submissions, concurrent duplicates, and a hook that
changes stored state just before the inspection reads it.
"""

import asyncio
import heapq
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack, nullcontext
from datetime import UTC, datetime

import httpx
from population_support import PopulationWorld

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


class RequestWorld(PopulationWorld):
    """The shared request fake on a virtual clock, with load-test faults."""

    def __init__(
        self, config: Mapping[str, object], time: VirtualTime | None = None
    ) -> None:
        super().__init__(config)
        self.time = time or VirtualTime()
        self.gameplay.clock_source = self.time.clock.wall_time
        self.lost_submits = 0
        self.refuse_submits = 0
        self.overlap = False
        self.submitting = 0
        self.release = asyncio.Event()
        # Changes stored state after the run, before the inspection reads it.
        self.tamper: Callable[[RequestWorld], None] | None = None

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.send)

    async def send(self, request: httpx.Request) -> httpx.Response:
        submitting = (request.method, request.url.path) == (
            "POST",
            "/api/catches/requests/",
        )
        if submitting and self.overlap:
            self.submitting += 1
            if self.submitting == 2:
                self.release.set()
            try:
                await self.release.wait()
            finally:
                self.submitting -= 1
        if submitting and self.refuse_submits:
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
        response = self.serve(request)
        if submitting and self.lost_submits:
            # The submission committed; its response is lost.
            self.lost_submits -= 1
            raise httpx.ReadError("SENTINEL lost submit", request=request)
        return response

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        if self.tamper is not None:
            self.tamper(self)
            self.tamper = None
        return await super().inspect(pool, run_id, identities)


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
