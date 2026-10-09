"""#228 U2: real setup/renewal coupled to finite host bridge authority."""

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Literal, cast

import httpx
import pool_support
import pytest
from fixture_support import CLEANUP_LINE, FakeFixtureChannel, FixtureState
from pool_support import DEPLOYMENT_ID, POOL, RUN_ID, SECRET, SHA, FakeChannel, World
from test_host_protocol import manifest

from tailtag_simulator import fixtures
from tailtag_simulator.client import ApiClient
from tailtag_simulator.fixtures import FixtureFailed, run_provisioned
from tailtag_simulator.host_bridge import BridgeSession
from tailtag_simulator.pool import LeaseFailed
from tailtag_simulator.traffic_config import resolve_traffic_config

world = pool_support.world


class HostBoundary:
    """Real bridge, with existing stateful external relay/HTTP substitutes."""

    def __init__(self, world: World, held_operation: str) -> None:
        self.world = world
        self.leases = FakeChannel(world, slots=3)
        self.fixtures = FakeFixtureChannel(world, self.leases, FixtureState())
        self.held_operation = held_operation
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.heartbeat_finished = asyncio.Event()
        self.heartbeat_acknowledged = asyncio.Event()
        self.requests: list[str] = []
        self.rejected: list[str] = []
        launch = manifest()
        launch["run_id"] = RUN_ID
        launch["backend_identity"] = {
            "source_sha": SHA,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
        }
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
        self.session = BridgeSession(launch, self.dispatch)

    async def dispatch(
        self, channel: str, request: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        operation = cast(str, request["operation"])
        arguments = cast(dict[str, object], request["arguments"])
        if operation == self.held_operation and not self.entered.is_set():
            self.entered.set()
            await self.resume.wait()
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
    if held_operation == "quarantine":
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
