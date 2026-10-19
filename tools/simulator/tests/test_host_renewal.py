"""#228 U2: real setup/renewal coupled to finite host bridge authority."""

import asyncio
import time
from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Literal, cast

import httpx
import pool_support
import pytest
from fixture_support import CLEANUP_LINE, FakeFixtureChannel, FixtureState
from pool_support import DEPLOYMENT_ID, POOL, RUN_ID, SECRET, SHA, FakeChannel, World
from test_host_protocol import expiration_manifest, manifest
from test_pool_smoke import assert_diagnostic, setup_diagnostics

from tailtag_simulator import fixtures
from tailtag_simulator.client import ApiClient
from tailtag_simulator.fixtures import FixtureFailed, run_provisioned
from tailtag_simulator.host_bridge import BridgeSession
from tailtag_simulator.pool import LeaseFailed
from tailtag_simulator.traffic_config import resolve_traffic_config

world = pool_support.world


class HostBoundary:
    """Real bridge, with existing stateful external relay/HTTP substitutes."""

    def __init__(
        self,
        world: World,
        held_operation: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        expiration: bool = False,
        fail_heartbeat: Callable[[int], bool] = lambda _number: False,
    ) -> None:
        self.world = world
        self.fail_heartbeat = fail_heartbeat
        self.heartbeat_dispatches = 0
        self.leases = FakeChannel(world, slots=3)
        self.fixtures = FakeFixtureChannel(world, self.leases, FixtureState())
        self.held_operation = held_operation
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.heartbeat_finished = asyncio.Event()
        self.heartbeat_acknowledged = asyncio.Event()
        self.requests: list[str] = []
        self.rejected: list[str] = []
        launch = expiration_manifest({"pool": POOL}) if expiration else manifest()
        launch["run_id"] = RUN_ID
        launch["backend_identity"] = {
            "source_sha": SHA,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
        }
        if not expiration:
            launch["configuration"] = resolve_traffic_config(
                {
                    "pool": POOL,
                    "normal_owners": 1,
                    "popular_owners": 0,
                    "casual": 2,
                    "active": 0,
                    "heavy": 0,
                    "retry_prone": 0,
                    "fursuits": 2,
                }
            )
        self.session = BridgeSession(launch, self.dispatch, clock=clock)

    async def dispatch(
        self, channel: str, request: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        operation = cast(str, request["operation"])
        arguments = cast(dict[str, object], request["arguments"])
        if operation == self.held_operation and not self.entered.is_set():
            self.entered.set()
            await self.resume.wait()
        if operation == "heartbeat":
            self.heartbeat_dispatches += 1
            if self.fail_heartbeat(self.heartbeat_dispatches):
                return "FAIL_LAUNCHER", {}
        if channel == "pool":
            data = await self.leases.call(
                operation, cast(str, request["pool"]), arguments
            )
        else:
            data = await self.fixtures.call(operation, arguments)
        return "PASS", dict(data)

    async def request(
        self, channel: str, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        self.requests.append(operation)
        envelope: dict[str, object] = {
            "operation": operation,
            "arguments": dict(arguments),
            "expected_identity": self.session.manifest["backend_identity"],
        }
        if channel == "pool":
            envelope["pool"] = POOL
        reply = await self.session.request(channel, envelope)
        if operation == "heartbeat":
            self.heartbeat_finished.set()
            if reply["result"] == "PASS":
                self.heartbeat_acknowledged.set()
        if reply["result"] != "PASS":
            self.rejected.append(operation)
            if channel == "pool":
                raise LeaseFailed(cast(str, reply["result"]), None)
            raise FixtureFailed(cast(str, reply["result"]))
        return cast(dict[str, object], reply["data"])


class PoolAdapter:
    def __init__(self, host: HostBoundary) -> None:
        self.host = host

    async def call(
        self, operation: str, pool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        assert pool == POOL
        return await self.host.request("pool", operation, arguments)


class FixtureAdapter:
    def __init__(self, host: HostBoundary) -> None:
        self.host = host

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return await self.host.request("fixture", operation, arguments)


@pytest.mark.parametrize("held_operation", ["quarantine", "provision", "cleanup"])
def test_setup_renewal_respects_terminal_recovery_and_pending_provision(
    world: World, monkeypatch: pytest.MonkeyPatch, held_operation: str
) -> None:
    host = HostBoundary(world, held_operation)
    lines: list[str] = []
    tick_finished = asyncio.Event()
    timer_cancelled = False
    ticks = 0
    simulated = False

    async def timer(seconds: float) -> None:
        nonlocal timer_cancelled, ticks
        assert seconds == 60
        ticks += 1
        if ticks > 1:
            await asyncio.Event().wait()
        try:
            await host.entered.wait()
        except asyncio.CancelledError:
            timer_cancelled = True
            raise
        finally:
            tick_finished.set()

    # Patch only fixtures' timer boundary; bridge scheduling and asyncio itself
    # remain real, including shielded mutation dispatch and joining.
    monkeypatch.setattr(
        fixtures, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": timer})
    )
    provider = world.clerk_transport

    async def clerk_reply(request: httpx.Request) -> httpx.Response:
        if held_operation == "quarantine" and request.url.path in {
            "/v1/client/sessions/sess_1/tokens",
            "/v1/client/sessions/sess_2/tokens",
        }:
            return httpx.Response(503, text="SENTINEL-provider-private")
        return await provider.handle_async_request(request)

    async def simulate(
        _origin: str, clients: tuple[ApiClient, ...], indexes: tuple[int, ...]
    ) -> Literal["pass"]:
        nonlocal simulated
        simulated = True
        assert indexes == (0, 1, 2)
        # A pending public interval lets the deferred renewal complete before
        # normal cleanup closes authority, without imposing task ordering.
        if held_operation == "provision":
            await host.heartbeat_acknowledged.wait()
        for client in clients:
            assert (await client.get("/api/me/")).status == 200
        return "pass"

    async def exercise() -> int:
        before = asyncio.all_tasks()
        task = asyncio.create_task(
            run_provisioned(
                POOL,
                1,
                2,
                2,
                0,
                prompt_secret=lambda: SECRET,
                lease_channel=PoolAdapter(host),
                fixture_channel=FixtureAdapter(host),
                emit=lines.append,
                clerk_transport=httpx.MockTransport(clerk_reply),
                api_transport=world.api_transport,
                clock=world.clock,
                run_id=RUN_ID,
                renew_leases=True,
                simulate_and_reconcile=simulate,
            )
        )
        try:
            await asyncio.wait_for(host.entered.wait(), 3)
            await asyncio.wait_for(tick_finished.wait(), 3)
            if held_operation in {"quarantine", "cleanup"} and not timer_cancelled:
                # Observe the actual rejected bridge request before allowing
                # terminal recovery's external acknowledgement to arrive.
                await asyncio.wait_for(host.heartbeat_finished.wait(), 3)
            await asyncio.sleep(0)
            host.resume.set()
            code = await asyncio.wait_for(task, 3)
            await host.session.settle()
            assert asyncio.all_tasks() - before == set()
            return code
        finally:
            host.resume.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await host.session.settle()
            host.session.close()

    code = asyncio.run(exercise())
    diagnostics = setup_diagnostics(lines)
    if held_operation == "quarantine":
        assert len(diagnostics) == 2
        for line, index in zip(diagnostics, [1, 2], strict=True):
            assert_diagnostic(
                line, index, "step=frontend_token failure=http status=503"
            )
        assert code == 1
        assert "FAIL setup quarantined=1,2" in lines
        assert "FAIL lease result=FAIL_LEASE" not in lines
        assert (
            host.requests[host.requests.index("quarantine") :].count("heartbeat") == 0
        )
        assert host.leases.calls_to("quarantine") == [
            {"index": 1, "run_id": RUN_ID},
            {"index": 2, "run_id": RUN_ID},
        ]
        assert host.leases.indexes("quarantined") == {1, 2}
        assert host.leases.indexes("free") == {0}
        assert host.fixtures.operations == ["retained_counts"]
        assert not simulated
    else:
        assert diagnostics == []
        assert code == 0
        assert "PASS setup identities=3 fursuits=2" in lines
        assert host.fixtures.operations == ["retained_counts", "provision", "cleanup"]
        if held_operation == "provision":
            assert host.leases.calls_to("heartbeat") == [
                {"run_id": RUN_ID, "ttl_seconds": 1800}
            ]
        else:
            assert "heartbeat" not in host.requests
            assert CLEANUP_LINE in lines
            assert "FAIL lease result=FAIL_LEASE" not in lines
        assert host.leases.indexes("free") == {0, 1, 2}
        assert simulated
    assert host.rejected == []
    assert host.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert "PASS release" in lines
    assert (
        set(world.ended_sessions)
        == set(world.opened_sessions)
        == {
            "sess_0",
            "sess_1",
            "sess_2",
        }
    )
    assert host.session.evidence()["release_acknowledged"] is True
    assert host.session.evidence()["pending_mutations"] == 0
    for secret in (SECRET, "SENTINEL", "user_SECRET", "TICKET", "COOKIE"):
        assert secret not in "\n".join(lines)


def test_host_renews_while_setup_cooldown_is_pending(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = HostBoundary(world, "unused")
    entered, resume = asyncio.Event(), asyncio.Event()
    waits: list[float] = []
    lines: list[str] = []
    ticks = 0

    async def setup_wait(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 1:
            entered.set()
            await resume.wait()
        else:
            await asyncio.sleep(0)

    async def timer(seconds: float) -> None:
        nonlocal ticks
        assert seconds == 60
        ticks += 1
        if ticks == 1:
            await entered.wait()
        else:
            await asyncio.Event().wait()

    monkeypatch.setattr(
        fixtures, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": timer})
    )
    lookups: list[str] = []
    provider = world.clerk_transport

    async def clerk_reply(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/users":
            lookups.append(request.url.params["external_id"])
        return await provider.handle_async_request(request)

    async def simulate(
        _origin: str, clients: tuple[ApiClient, ...], indexes: tuple[int, ...]
    ) -> Literal["pass"]:
        assert indexes == (0, 1, 2)
        for client in clients:
            assert (await client.get("/api/me/")).status == 200
        return "pass"

    async def exercise() -> int:
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_provisioned(
                POOL,
                1,
                2,
                2,
                0,
                prompt_secret=lambda: SECRET,
                lease_channel=PoolAdapter(host),
                fixture_channel=FixtureAdapter(host),
                emit=lines.append,
                clerk_transport=httpx.MockTransport(clerk_reply),
                api_transport=world.api_transport,
                clock=world.clock,
                run_id=RUN_ID,
                renew_leases=True,
                setup_sleep=setup_wait,
                simulate_and_reconcile=simulate,
            )
        )
        pending = asyncio.create_task(entered.wait())
        try:
            await asyncio.wait_for(
                asyncio.wait({task, pending}, return_when=asyncio.FIRST_COMPLETED), 3
            )
            assert entered.is_set(), "setup completed without the required cooldown"
            await asyncio.wait_for(host.heartbeat_acknowledged.wait(), 3)
            assert not task.done()
            assert waits == [4]
            assert lookups == [f"sim-pool-{POOL}-0", f"sim-pool-{POOL}-0"]
            assert world.tickets == [0]
            assert host.leases.calls_to("heartbeat") == [
                {"run_id": RUN_ID, "ttl_seconds": 1800}
            ]
            assert host.fixtures.operations == ["retained_counts"]
            resume.set()
            code = await asyncio.wait_for(task, 3)
            await host.session.settle()
            assert not (set(asyncio.all_tasks()) - before)
            return code
        finally:
            resume.set()
            if not pending.done():
                pending.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, pending, return_exceptions=True)
            await host.session.settle()
            host.session.close()

    assert asyncio.run(exercise()) == 0
    assert waits == [4, 4]
    assert host.rejected == []
    assert host.fixtures.operations == ["retained_counts", "provision", "cleanup"]
    assert host.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert (
        set(world.ended_sessions)
        == set(world.opened_sessions)
        == {"sess_0", "sess_1", "sess_2"}
    )
    assert host.session.evidence()["release_acknowledged"] is True
    assert host.session.evidence()["pending_mutations"] == 0
    assert "PASS release" in lines


COUNT = 3
BEAT = {"extended": COUNT}
LOST = LeaseFailed("FAIL_LAUNCHER")


@pytest.mark.parametrize(
    ("script", "failed"),
    [
        # A pass resets the run of failures, so no three are consecutive.
        pytest.param([LOST, LOST, BEAT, LOST, LOST], False, id="reset-by-pass"),
        pytest.param([LOST, LOST, LOST], True, id="three-consecutive"),
        pytest.param([LeaseFailed("FAIL_REQUEST")], True, id="other-lease-result"),
        pytest.param([{"extended": COUNT - 1}], True, id="wrong-extended"),
        pytest.param([RuntimeError()], True, id="other-exception"),
    ],
)
def test_renewal_tolerates_only_isolated_launcher_failures_on_the_regular_tick(
    monkeypatch: pytest.MonkeyPatch,
    script: list[Exception | dict[str, int]],
    failed: bool,
) -> None:
    heartbeats = 0
    calls_at_tick: list[int] = []
    exhausted = asyncio.Event()

    class Scripted:
        async def call(
            self, operation: str, pool: str, arguments: Mapping[str, object]
        ) -> Mapping[str, object]:
            nonlocal heartbeats
            if operation != "heartbeat":
                return {"indexes": list(range(COUNT))}
            heartbeats += 1
            outcome = script[heartbeats - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    async def timer(seconds: float) -> None:
        assert seconds == 60
        calls_at_tick.append(heartbeats)
        if heartbeats == len(script):
            exhausted.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        fixtures, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": timer})
    )

    async def idle() -> int:
        await asyncio.Event().wait()
        return 0

    async def exercise() -> bool:
        renewal = fixtures._Renewal(Scripted())  # pyright: ignore[reportPrivateUsage]
        renewal.worker = asyncio.create_task(idle())
        waiter = asyncio.create_task(exhausted.wait())
        try:
            allocation = {"run_id": RUN_ID, "count": COUNT, "ttl_seconds": 1800}
            await renewal.call("allocate", POOL, allocation)
            assert renewal.timer is not None
            await asyncio.wait_for(
                asyncio.wait(
                    {renewal.timer, waiter}, return_when=asyncio.FIRST_COMPLETED
                ),
                3,
            )
            assert renewal.failed is failed
            assert (renewal.worker.cancelling() > 0) is failed
            return renewal.failed
        finally:
            waiter.cancel()
            renewal.worker.cancel()
            await renewal.stop()
            await asyncio.gather(renewal.worker, waiter, return_exceptions=True)

    asyncio.run(exercise())
    # Exactly one heartbeat per tick: a retry never happens ahead of the next tick.
    assert heartbeats == len(script)
    assert calls_at_tick == list(range(len(calls_at_tick)))


def test_tolerated_heartbeat_failures_never_exhaust_the_bridge_budget(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    # The bridge admits heartbeats until the execution window (46800 s) ends, so
    # ticks fall at 60 s ... 46740 s: 779 in all, against a budget of 806. Two of
    # every three fail, so one extra call per failure would pass that budget.
    ticks = 779
    host = HostBoundary(
        world,
        "unused",
        clock=lambda: now[0],
        expiration=True,
        fail_heartbeat=lambda number: number % 3 != 0,
    )
    elapsed = 0
    finished = asyncio.Event()

    async def timer(seconds: float) -> None:
        nonlocal elapsed
        assert seconds == 60
        if elapsed == ticks:
            finished.set()
            await asyncio.Event().wait()
        elapsed += 1
        now[0] += 60

    monkeypatch.setattr(
        fixtures, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": timer})
    )

    async def idle() -> int:
        await asyncio.Event().wait()
        return 0

    async def exercise() -> None:
        renewal = fixtures._Renewal(PoolAdapter(host))  # pyright: ignore[reportPrivateUsage]
        renewal.worker = asyncio.create_task(idle())
        try:
            allocation = {"run_id": RUN_ID, "count": 2, "ttl_seconds": 1800}
            await renewal.call("allocate", POOL, allocation)
            await asyncio.wait_for(finished.wait(), 3)
            await host.session.settle()
            assert renewal.failed is False
        finally:
            renewal.worker.cancel()
            await renewal.stop()
            await asyncio.gather(renewal.worker, return_exceptions=True)
            await host.session.settle()
            host.session.close()

    asyncio.run(exercise())
    assert host.heartbeat_dispatches == ticks
    assert host.rejected == ["heartbeat"] * (ticks - ticks // 3)


def test_reclaimed_lease_fails_renewal_at_once_through_the_bridge(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = HostBoundary(world, "unused")
    host.leases.reclaim_before_heartbeat = 1
    ticks = 0
    second_tick = asyncio.Event()

    async def timer(seconds: float) -> None:
        nonlocal ticks
        assert seconds == 60
        ticks += 1
        if ticks > 1:
            second_tick.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        fixtures, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": timer})
    )

    async def idle() -> int:
        await asyncio.Event().wait()
        return 0

    async def exercise() -> bool:
        renewal = fixtures._Renewal(PoolAdapter(host))  # pyright: ignore[reportPrivateUsage]
        renewal.worker = asyncio.create_task(idle())
        waiter = asyncio.create_task(second_tick.wait())
        try:
            allocation = {"run_id": RUN_ID, "count": 3, "ttl_seconds": 1800}
            await renewal.call("allocate", POOL, allocation)
            assert renewal.timer is not None
            await asyncio.wait_for(
                asyncio.wait(
                    {renewal.timer, waiter}, return_when=asyncio.FIRST_COMPLETED
                ),
                3,
            )
            return renewal.failed
        finally:
            waiter.cancel()
            renewal.worker.cancel()
            await renewal.stop()
            await asyncio.gather(renewal.worker, waiter, return_exceptions=True)
            await host.session.settle()
            host.session.close()

    failed = asyncio.run(exercise())
    # A reclaimed lease is a lease verdict, not a transient launcher loss.
    outcomes = cast(dict[str, str], host.session.evidence()["outcomes"])
    assert outcomes["heartbeat"] == "FAIL_LEASE"
    assert len(host.leases.calls_to("heartbeat")) == 1
    assert failed is True
