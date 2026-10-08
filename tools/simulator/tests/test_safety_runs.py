"""#227 U4: real command/lifecycle behavior against network and launcher boundaries."""

import asyncio
import getpass
import json
import socket
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypedDict, cast

import httpx
import pool_support
import pytest
from convention_support import CONFIG, BlockedHttp, PopulationFixtures, Rig, rig
from fixture_support import FakeFixtureChannel, FixtureState
from journey_support import VALID_A, VALID_B
from pool_support import POOL, RUN_ID, SECRET, FakeChannel, World
from report_support import read_report
from traffic_support import ManualClock

from tailtag_simulator.__main__ import main
from tailtag_simulator.convention import run_convention
from tailtag_simulator.fixtures import run_fixture_smoke
from tailtag_simulator.journeys import JourneyImages, run_journeys
from tailtag_simulator.pool import run_pool_smoke
from tailtag_simulator.safety import SafetyRuntime
from tailtag_simulator.smoke import run_smoke

world = pool_support.world
CONFIRM = "/api/catches/confirm/"


class SharedRunArgs(TypedDict):
    prompt_secret: Callable[[], str]
    emit: Callable[[str], None]
    clerk_transport: httpx.AsyncBaseTransport
    api_transport: httpx.AsyncBaseTransport
    clock: Callable[[], float]
    run_id: str
    safety: SafetyRuntime


@pytest.mark.parametrize(
    "command",
    [
        "smoke",
        "pool-smoke",
        "fixture-smoke",
        "journeys",
        "convention-v1",
        "convention-v2",
    ],
)
def test_every_execution_command_uses_the_supplied_shared_budget_before_credentials(
    tmp_path: Path,
    world: World,
    command: str,
) -> None:
    runtime = SafetyRuntime({"requests": 1})
    prompts: list[str] = []
    lines: list[str] = []
    leases = FakeChannel(world, slots=8)
    fixtures = FakeFixtureChannel(world, leases, FixtureState())
    common: SharedRunArgs = {
        "prompt_secret": lambda: (prompts.append("prompt"), SECRET)[1],
        "emit": lines.append,
        "clerk_transport": world.clerk_transport,
        "api_transport": world.api_transport,
        "clock": world.clock,
        "run_id": RUN_ID,
        "safety": runtime,
    }

    async def execute() -> int:
        if command == "smoke":
            return await run_smoke(
                "staging",
                prompt_token=lambda: (prompts.append("prompt"), "a.b.c")[1],
                emit=lines.append,
                transport=world.api_transport,
                safety=runtime,
            )
        if command == "pool-smoke":
            return await run_pool_smoke(POOL, 2, channel=leases, **common)
        if command == "fixture-smoke":
            return await run_fixture_smoke(
                POOL, 1, 1, 1, lease_channel=leases, fixture_channel=fixtures, **common
            )
        if command == "journeys":
            from journey_support import JourneyWorld
            from test_journeys import make_rig

            value = make_rig(JourneyWorld())
            return await run_journeys(
                POOL,
                images=JourneyImages(valid_a=VALID_A, valid_b=VALID_B),
                lease_channel=value.leases,
                fixture_channel=value.fixtures,
                inspection_channel=value.inspection,
                **common,
            )
        value = rig(tmp_path)
        return await run_convention(
            POOL,
            config=CONFIG,
            seed=-42,
            scenario_version=2 if command == "convention-v2" else 1,
            lease_channel=value.leases,
            fixture_channel=value.fixtures,
            inspection_channel=value.inspection,
            **common,
        )

    assert asyncio.run(execute()) != 0
    assert runtime.abort_reason == "request_ceiling"
    assert prompts == []
    assert [request.url.path for request in world.api_requests] == ["/health/identity"]
    assert not world.opened_sessions
    assert not leases.calls


async def guarded_convention(
    value: Rig,
    runtime: SafetyRuntime,
    transport: httpx.AsyncBaseTransport,
) -> int:
    return await run_convention(
        POOL,
        config=CONFIG,
        seed=-42,
        prompt_secret=lambda: SECRET,
        lease_channel=value.leases,
        fixture_channel=value.fixtures,
        inspection_channel=value.inspection,
        emit=value.lines.append,
        clerk_transport=value.world.clerk_transport,
        api_transport=transport,
        clock=value.world.clock,
        run_id=RUN_ID,
        report=value.report,
        safety=runtime,
    )


def test_pool_finalization_keeps_its_reserve_after_execution_deadline(
    world: World,
) -> None:
    time = ManualClock()
    runtime = SafetyRuntime(
        {"seconds": 1, "final_seconds": 10},
        monotonic=lambda: time.now,
        sleep=time.sleep,
    )
    entered = asyncio.Event()
    lines: list[str] = []

    class SlowRelease(FakeChannel):
        async def call(
            self, operation: str, pool: str, arguments: Mapping[str, object]
        ) -> Mapping[str, object]:
            if operation == "release":
                entered.set()
                await time.sleep(2)
            return await super().call(operation, pool, arguments)

    leases = SlowRelease(world)

    async def token_wait(seconds: float) -> None:
        # Advance the external token expiry clock, keeping execution at t=0.
        world.clock.now += seconds
        await asyncio.sleep(0)

    async def execute() -> int:
        existing = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_pool_smoke(
                POOL,
                2,
                prompt_secret=lambda: SECRET,
                channel=leases,
                emit=lines.append,
                clerk_transport=world.clerk_transport,
                api_transport=world.api_transport,
                sleep=token_wait,
                clock=world.clock,
                run_id=RUN_ID,
                safety=runtime,
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 3)
            await time.settle()
            assert time.now == 0
            await time.advance(1)
            assert runtime.abort_reason is None
            assert (
                cast(dict[str, object], runtime.snapshot()["finalization"])["exhausted"]
                is None
            )
            assert not task.done()
            await time.advance(1)
            code = await asyncio.wait_for(task, 3)
            assert not (set(asyncio.all_tasks()) - existing)
            return code
        finally:
            # Even a failed assertion must let the external release finish and
            # join the shielded finalizer before the loop is closed.
            if not task.done():
                await time.advance(10)
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert asyncio.run(execute()) == 0
    assert lines[-1] == "PASS release"
    assert leases.indexes("leased") == set()
    assert set(world.ended_sessions) == set(world.opened_sessions)
    assert runtime.abort_reason is None
    assert not time.waiters


@pytest.mark.parametrize("status", [200, 201, 503])
def test_pool_profile_success_violation_latches_while_provider_failure_stays_ordinary(
    world: World, status: int
) -> None:
    runtime = SafetyRuntime({})
    leases = FakeChannel(world)
    lines: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/profile/":
            return httpx.Response(
                status,
                json={
                    "handle": "sp_p1_0",
                    "display_name": "Sim p1 0",
                    "onboarding_complete": True,
                }
                if status == 201
                else [],
            )
        return await world.api_transport.handle_async_request(request)

    async def token_wait(seconds: float) -> None:
        world.clock.now += seconds
        await asyncio.sleep(0)

    code = asyncio.run(
        run_pool_smoke(
            POOL,
            2,
            prompt_secret=lambda: SECRET,
            channel=leases,
            emit=lines.append,
            clerk_transport=world.clerk_transport,
            api_transport=httpx.MockTransport(respond),
            sleep=token_wait,
            clock=world.clock,
            run_id=RUN_ID,
            safety=runtime,
        )
    )
    assert code != 0
    assert runtime.abort_reason == (None if status == 503 else "correctness")
    assert not any(request.url.path == "/api/me/" for request in world.api_requests)
    assert set(world.ended_sessions) == set(world.opened_sessions)
    assert leases.indexes("leased") == set()


@pytest.mark.parametrize(
    "cause",
    [
        "correctness",
        "resource_saturation",
        "identity_mismatch",
        "readiness",
        "duration_ceiling",
    ],
)
def test_aborted_convention_cancels_work_and_applies_target_safe_finalization(
    tmp_path: Path,
    world: World,
    cause: str,
) -> None:
    del world
    value = rig(
        tmp_path, safety_policy={"seconds": 1} if cause == "duration_ceiling" else None
    )
    if cause == "duration_ceiling":
        # A later authoritative violation must fail recovery without replacing
        # the original deadline abort.
        value.inspection.corrupt = True
    time = ManualClock()
    runtime = SafetyRuntime(
        {"seconds": 1} if cause == "duration_ceiling" else {},
        monotonic=lambda: time.now,
        sleep=time.sleep,
        observe=value.report.record_safety,
    )
    blocked = BlockedHttp(value.world.api_transport, CONFIRM)
    changed = False
    after_abort: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        if runtime.abort_reason:
            after_abort.append(request.url.path)
        if (
            changed
            and request.url.path == "/health/identity"
            and cause == "identity_mismatch"
        ):
            return httpx.Response(
                200,
                json={
                    "source_sha": "b" * 40,
                    "deployment_id": "22222222-2222-4222-8222-222222222222",
                    "environment": "staging",
                },
            )
        if (
            changed
            and request.url.path == "/health/ready"
            and cause == "readiness"
            and runtime.abort_reason is None
        ):
            # Two failing execution probes; revalidation in finalization recovers.
            return httpx.Response(503, json={"status": "unavailable"})
        response = await blocked.serve(request)
        if request.url.path == CONFIRM and cause == "correctness":
            return httpx.Response(201, json={"SENTINEL-private": "malformed-success"})
        return response

    async def execute() -> int:
        nonlocal changed
        existing = set(asyncio.all_tasks())
        task = asyncio.create_task(
            guarded_convention(value, runtime, httpx.MockTransport(respond))
        )
        try:
            await asyncio.wait_for(blocked.entered.wait(), 3)
            await time.settle()
            changed = True
            if cause == "resource_saturation":
                runtime.abort("resource_saturation")
            elif cause == "correctness":
                blocked.released.set()
            elif cause == "duration_ceiling":
                await time.advance(1)
            else:
                await time.advance(10)
                if cause == "readiness":
                    # A whole target probe crosses three real HTTP/request races;
                    # settle completion before advancing to its next poll deadline.
                    for _ in range(10):
                        await time.settle()
                    assert runtime.abort_reason is None
                    assert (
                        cast(dict[str, object], runtime.snapshot()["probes"])[
                            "consecutive_failures"
                        ]
                        == 1
                    )
                    await time.advance(10)
            code = await asyncio.wait_for(task, 3)
            assert not (set(asyncio.all_tasks()) - existing)
            return code
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert asyncio.run(execute()) != 0
    assert runtime.abort_reason == cause
    report = read_report(value.report.path)
    assert report["schema_version"] == 4 and report["outcome"] == "aborted"
    assert report["safety"]["abort"]["reason"] == cause
    assert "cleanup" not in value.fixtures.operations
    assert set(value.world.ended_sessions) == set(value.world.opened_sessions)
    assert not time.waiters
    if cause == "identity_mismatch":
        assert after_abort == []
        assert "retain" not in value.fixtures.operations
        assert value.leases.calls_to("release") == []
        assert report["safety"]["finalization"]["release"] == "skipped"
    else:
        assert "retain" in value.fixtures.operations
        assert value.leases.calls_to("release") == [{"run_id": RUN_ID}]
        assert report["safety"]["finalization"]["release"] == "passed"
        if cause in {"correctness", "duration_ceiling"}:
            assert value.inspection.calls
            assert report["safety"]["finalization"]["reconciliation"] == (
                "failed" if cause == "duration_ceiling" else "passed"
            )
        else:
            assert not value.inspection.calls
    for private in (SECRET, "SENTINEL", "user_SECRET", "tailtag:catch"):
        assert private not in value.report.path.read_text() + "\n".join(value.lines)


def test_cancelled_provision_reply_cannot_readmit_possibly_owned_fixtures(
    tmp_path: Path,
    world: World,
) -> None:
    del world
    value = rig(tmp_path)
    time = ManualClock()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    class CommittedWithoutReply(PopulationFixtures):
        async def call(
            self, operation: str, arguments: Mapping[str, object]
        ) -> dict[str, object]:
            result = await super().call(operation, arguments)
            if operation == "provision":
                # The remote transaction commits before a response reaches the caller.
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return result

    value.fixtures = CommittedWithoutReply(value.world, value.leases, value.population)
    runtime = SafetyRuntime(
        {},
        monotonic=lambda: time.now,
        sleep=time.sleep,
        observe=value.report.record_safety,
    )
    possibly_owned: set[int] = set()

    async def execute() -> int:
        existing = set(asyncio.all_tasks())
        task = asyncio.create_task(
            guarded_convention(value, runtime, value.world.api_transport)
        )
        try:
            await asyncio.wait_for(entered.wait(), 3)
            possibly_owned.update(value.leases.indexes("leased"))
            assert possibly_owned and value.fixtures.state.enrollments
            runtime.abort("resource_saturation")
            code = await asyncio.wait_for(task, 3)
            assert cancelled.is_set()
            assert not (set(asyncio.all_tasks()) - existing)
            return code
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert asyncio.run(execute()) != 0
    assert possibly_owned <= (
        value.leases.indexes("quarantined") | value.leases.indexes("leased")
    )
    assert "cleanup" not in value.fixtures.operations
    assert set(value.world.ended_sessions) == set(value.world.opened_sessions)
    assert not time.waiters
    report = read_report(value.report.path)
    assert report["outcome"] == "aborted"
    assert report["safety"]["abort"]["reason"] == "resource_saturation"
    retention = report["safety"]["finalization"]["retention"]
    assert retention == (
        "passed" if "retain" in value.fixtures.operations else "uncertain"
    )


@pytest.mark.parametrize(
    "bad_config",
    [
        '{"requests":1,"requests":2}',
        '{"seconds":NaN}',
        '{"unknown":"SENTINEL"}',
        '"' + "x" * 65536 + '"',
    ],
    ids=["duplicate", "nonfinite", "unknown", "oversized"],
)
def test_cli_rejects_invalid_safety_json_before_secret_or_external_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_config: str,
) -> None:
    config = tmp_path / "safety.json"
    config.write_text(bad_config)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("invalid policy reached an external boundary")

    monkeypatch.setattr(getpass, "getpass", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert main(["smoke", "--target", "staging", "--safety-config", str(config)]) == 1
    assert "SENTINEL" not in capsys.readouterr().out


def test_unattended_convention_is_denied_before_external_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "scenario.json"
    config.write_text(json.dumps(CONFIG))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unattended convention reached an external boundary")

    monkeypatch.setattr(getpass, "getpass", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert (
        main(
            [
                "convention",
                "--family",
                "baseline",
                "--pool",
                POOL,
                "--config",
                str(config),
                "--unattended",
            ]
        )
        == 1
    )


def test_cli_operator_signal_stops_owned_http_and_restores_signal_handler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real SIGUSR1 exercises CLI ownership, with only source/prompt/network boundaries."""
    import hashlib
    import importlib
    import os
    import signal
    import threading
    import time

    from tailtag_simulator import __main__ as command

    # Existing provenance contract: create a verifiable standalone source bundle.
    module = importlib.import_module("tailtag_simulator")
    assert module.__file__ is not None
    package = Path(module.__file__).parent
    source = tmp_path / "source"
    source.mkdir()
    files: dict[str, bytes] = {
        "pyproject.toml": (package.parent / "pyproject.toml").read_bytes(),
        "uv.lock": (package.parent / "uv.lock").read_bytes(),
    }
    checkout = Path(__file__).parents[3]
    for directory, destination in (
        (package, "tailtag_simulator"),
        (
            checkout / "services/api/simulation_fixtures/images",
            "services/api/simulation_fixtures/images",
        ),
    ):
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".jpg"}:
                files[f"{destination}/{path.relative_to(directory)}"] = (
                    path.read_bytes()
                )
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }
    (source / "source.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "simulator_sha": "f" * 40,
                "dependency_lock_sha256": manifest["uv.lock"],
                "manifest": manifest,
            }
        )
    )
    monkeypatch.setattr(command, "REPOSITORY_ROOT", source)

    def token_prompt(*_args: object, **_kwargs: object) -> str:
        return "a.b.c"

    monkeypatch.setattr(getpass, "getpass", token_prompt)
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    original_handler = signal.getsignal(signal.SIGUSR1)

    def previous(_signum: int, _frame: object) -> None:
        # A failed install must never deliver SIGUSR1 to its process-killing default.
        pass

    signal.signal(signal.SIGUSR1, previous)
    acknowledged = False
    delivered: list[float] = []
    sender: threading.Thread | None = None
    sent: list[str] = []

    async def serve(
        _transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        nonlocal acknowledged, sender
        sent.append(request.url.path)
        if request.url.path == "/health/identity":
            return httpx.Response(
                200,
                json={
                    "source_sha": "a" * 40,
                    "deployment_id": "11111111-1111-4111-8111-111111111111",
                    "environment": "staging",
                },
            )
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/api/me/"
        assert signal.getsignal(signal.SIGUSR1) != previous, (
            "CLI never installed operator signal handler"
        )

        def send_while_idle() -> None:
            # Let all runnable HTTP/race tasks settle into the selector first.
            time.sleep(0.1)
            delivered.append(time.monotonic())
            os.kill(os.getpid(), signal.SIGUSR1)

        sender = threading.Thread(target=send_while_idle)
        sender.start()
        try:
            # The long timer bounds red without accidentally supplying the wakeup.
            await asyncio.wait_for(asyncio.Event().wait(), timeout=5)
        finally:
            acknowledged = True
        return httpx.Response(200, json={"id": 1})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", serve)
    reports = tmp_path / "reports"
    try:
        assert main(["smoke", "--target", "staging", "--report-dir", str(reports)]) != 0
        finished = time.monotonic()
        assert signal.getsignal(signal.SIGUSR1) is previous
        assert delivered and finished - delivered[0] < 1, (
            "operator stop waited for the idle selector watchdog"
        )
    finally:
        try:
            if sender is not None:
                sender.join(timeout=1)
                assert not sender.is_alive()
        finally:
            signal.signal(signal.SIGUSR1, original_handler)
    assert acknowledged
    values = list(reports.rglob("*.json"))
    assert len(values) == 1
    evidence = read_report(values[0])
    assert evidence["outcome"] == "aborted"
    assert evidence["safety"]["abort"]["reason"] == "resource_saturation"
    assert sent.count("/api/me/") == 1
