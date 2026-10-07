"""U3 real orchestration rig; substitutes only HTTP/launcher/time boundaries."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
from fixture_support import FakeFixtureChannel
from journey_support import JourneyWorld
from pool_support import POOL, RUN_ID, SECRET, FakeChannel
from population_support import PopulationWorld
from report_support import ReportClock, literal_report

from tailtag_simulator.reports import RunReport

CONFIG: dict[str, object] = {
    "pool": POOL,
    "family": "baseline",
    "casual": 2,
    "active": 1,
    "heavy": 1,
    "retry_prone": 2,
    "normal_owners": 1,
    "popular_owners": 1,
    "fursuits": 2,
}


class PopulationFixtures(FakeFixtureChannel):
    def __init__(
        self, world: JourneyWorld, leases: FakeChannel, population: PopulationWorld
    ) -> None:
        super().__init__(world, leases, population.gameplay.state)
        self.population = population

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        result = await super().call(operation, arguments)
        if operation == "provision":
            self.population.rebind(self.state.owners, self.state.catchers)
        return result


class Inspection:
    def __init__(self, population: PopulationWorld) -> None:
        self.population = population
        self.calls: list[dict[str, int]] = []
        self.corrupt = False

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        self.calls.append(dict(identities))
        data = dict(await self.population.inspect(pool, run_id, identities))
        if self.corrupt:
            data["fixture_photos_unchanged"] = False
        return data


@dataclass
class Rig:
    world: JourneyWorld
    population: PopulationWorld
    leases: FakeChannel
    fixtures: PopulationFixtures
    inspection: Inspection
    report: RunReport
    lines: list[str]

    async def run(
        self,
        *,
        api_transport: httpx.AsyncBaseTransport | None = None,
        clerk_transport: httpx.AsyncBaseTransport | None = None,
    ) -> int:
        from tailtag_simulator.convention import run_convention

        return await run_convention(
            POOL,
            config=CONFIG,
            seed=-42,
            prompt_secret=lambda: SECRET,
            lease_channel=self.leases,
            fixture_channel=self.fixtures,
            inspection_channel=self.inspection,
            emit=self.lines.append,
            clerk_transport=clerk_transport or self.world.clerk_transport,
            api_transport=api_transport or self.world.api_transport,
            clock=self.world.clock,
            run_id=RUN_ID,
            report=self.report,
        )


def rig(root: Path) -> Rig:
    from tailtag_simulator.behavior_config import resolve_behavior_config

    config = resolve_behavior_config(CONFIG)
    population = PopulationWorld(config)
    population.rebind(range(2), range(2, 8))
    world = JourneyWorld(gameplay=population.gameplay)
    world.route = population.route
    leases = FakeChannel(world, slots=8)
    fixtures = PopulationFixtures(world, leases, population)
    evidence_clock = ReportClock()
    report = RunReport(
        root,
        "convention-baseline",
        config=config,
        seed=-42,
        run_id=RUN_ID,
        wall_clock=evidence_clock.wall_clock,
        monotonic=evidence_clock.monotonic,
    )
    report.record_source(literal_report()["source"])
    report.begin("provenance")
    report.end("provenance", "passed")
    return Rig(
        world,
        population,
        leases,
        fixtures,
        Inspection(population),
        report,
        [],
    )


class BlockedHttp:
    """A pending external response, with an observable cancellation acknowledgement."""

    def __init__(self, transport: httpx.AsyncBaseTransport, path: str) -> None:
        self.transport = transport
        self.path = path
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.released = asyncio.Event()
        self.after_cancel: list[str] = []

    async def serve(self, request: httpx.Request) -> httpx.Response:
        if self.cancelled.is_set():
            self.after_cancel.append(request.url.path)
        if request.url.path == self.path:
            self.entered.set()
            try:
                await self.released.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return await self.transport.handle_async_request(request)

    @property
    def boundary(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.serve)
