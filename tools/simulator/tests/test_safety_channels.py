"""#227 U2: actual launcher channels bind the independently checked run identity."""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import cast

import httpx
import pool_support
import pytest

from tailtag_simulator.fixtures import FixtureFailed, FixtureLauncherChannel
from tailtag_simulator.pool import LauncherChannel, LeaseFailed, run_pool_smoke
from tailtag_simulator.population_reconciliation import (
    PopulationInspectionLauncherChannel,
)
from tailtag_simulator.reconciliation import (
    InspectionFailed,
    InspectionLauncherChannel,
    Role,
)
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime

IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
POOL = "alpha"
RUN = "55555555-5555-4555-8555-555555555555"
world = pool_support.world


@pytest.mark.parametrize("channel", ["pool", "fixture", "inspection", "population"])
@pytest.mark.parametrize("result", ["PASS", "FAIL_TARGET"])
def test_channel_pins_envelope_and_target_failure_prohibits_another_launch(
    tmp_path: Path,
    channel: str,
    result: str,
) -> None:
    record = tmp_path / "record.jsonl"
    script = (
        "import json,sys\n"
        f"with open({str(record)!r},'a') as f: f.write(json.dumps({{'argv':sys.argv[1:],'wire':json.loads(sys.stdin.read())}})+'\\n')\n"
        f"print(json.dumps({{'result':{result!r},'data':{{}}}}))\n"
        f"sys.exit({0 if result == 'PASS' else 1})\n"
    )
    command = [sys.executable, "-c", script]
    invoke: Callable[[], Awaitable[Mapping[str, object]]]
    if channel == "pool":
        lease = LauncherChannel(command)
        invoke = lambda: lease.call("release", POOL, {"run_id": RUN})
        expected: dict[str, object] = {
            "operation": "release",
            "pool": POOL,
            "arguments": {"run_id": RUN},
        }
    elif channel == "fixture":
        fixture = FixtureLauncherChannel(command)
        invoke = lambda: fixture.call("status", {"run_id": RUN})
        expected = {"operation": "status", "arguments": {"run_id": RUN}}
    elif channel == "inspection":
        inspection = InspectionLauncherChannel(command)
        invoke = lambda: inspection.inspect(POOL, RUN, {Role.OWNER0: 1})
        expected = {
            "operation": "inspect",
            "arguments": {"pool": POOL, "run_id": RUN, "identities": {"owner0": 1}},
        }
    else:
        population = PopulationInspectionLauncherChannel(command)
        invoke = lambda: population.inspect(POOL, RUN, {"owner0": 1, "attendee0": 2})
        expected = {
            "operation": "inspect-population-v1",
            "arguments": {
                "pool": POOL,
                "run_id": RUN,
                "identities": {"owner0": 1, "attendee0": 2},
            },
        }

    async def execute() -> None:
        runtime = SafetyRuntime({})

        async def probe() -> dict[str, object]:
            return dict(IDENTITY)

        runtime.bind_probe(probe)
        with runtime.scope():
            await runtime.check_target()
            if result == "PASS":
                assert await invoke() == {}
                assert runtime.abort_reason is None
            else:
                with pytest.raises(
                    (SafetyAborted, FixtureFailed, LeaseFailed, InspectionFailed)
                ):
                    await invoke()
                assert runtime.abort_reason == "identity_mismatch"
                with pytest.raises(
                    (SafetyAborted, FixtureFailed, LeaseFailed, InspectionFailed)
                ):
                    await invoke()

    asyncio.run(execute())
    assert [json.loads(line) for line in record.read_text().splitlines()] == [
        {"argv": [], "wire": {**expected, "expected_identity": IDENTITY}},
    ]


def test_later_identity_mismatch_prohibits_recovery_without_replacing_first_reason(
    tmp_path: Path,
) -> None:
    """U2 HIGH regression: a correctness abort must not hide a later unsafe target."""
    import httpx

    from tailtag_simulator.client import open_client

    record = tmp_path / "launched"
    command = [
        sys.executable,
        "-c",
        f'from pathlib import Path; Path({str(record)!r}).touch(); print(\'{{"result":"FAIL_TARGET","data":{{}}}}\'); raise SystemExit(1)',
    ]
    channel = FixtureLauncherChannel(command)
    probes = 0
    sent: list[str] = []

    async def execute() -> None:
        nonlocal probes
        runtime = SafetyRuntime({})

        async def probe() -> dict[str, object]:
            nonlocal probes
            probes += 1
            return dict(IDENTITY)

        runtime.bind_probe(probe)
        with runtime.scope():
            await runtime.check_target()
            runtime.abort("correctness")
            assert await runtime.begin_finalization()
            with pytest.raises((SafetyAborted, FixtureFailed)):
                await channel.call("retain", {"run_id": RUN})
            assert record.exists()
            record.unlink()
            observed_probes = probes
            with pytest.raises((SafetyAborted, FixtureFailed)):
                await channel.call("release", {"run_id": RUN})
            async with open_client(
                "https://staging.tailtag.app",
                transport=httpx.MockTransport(
                    lambda r: (sent.append(r.url.path), httpx.Response(200, json={}))[1]
                ),
            ) as client:
                with pytest.raises(SafetyAborted):
                    await client.get("/must-not-follow-new-deployment")
            assert runtime.abort_reason == "correctness"
            assert probes == observed_probes
            assert not record.exists()
            assert sent == []

    asyncio.run(execute())


def test_profile_abort_cannot_readmit_unquarantined_identities_through_real_launcher(
    tmp_path: Path, world: pool_support.World
) -> None:
    state_path = tmp_path / "provider-state.json"
    phase_path = tmp_path / "observed-phase.json"
    calls_path = tmp_path / "provider-calls.jsonl"
    state_path.write_text(json.dumps({str(index): "free" for index in range(3)}))

    def observe(snapshot: Mapping[str, object]) -> None:
        phase_path.write_text(json.dumps(snapshot["finalization"]))

    runtime = SafetyRuntime({}, observe=observe)
    # Stateful external lease service: release frees only live leases; quarantine
    # is the durable operation that prevents readmission of a bad/unknown identity.
    script = (
        "import json\nfrom pathlib import Path\nimport sys\n"
        f"state_path=Path({str(state_path)!r})\n"
        f"phase_path=Path({str(phase_path)!r})\n"
        f"calls_path=Path({str(calls_path)!r})\n"
        "wire=json.loads(sys.stdin.read())\n"
        "state=json.loads(state_path.read_text())\n"
        "phase=json.loads(phase_path.read_text())\n"
        "op=wire['operation']; args=wire['arguments']\n"
        "with calls_path.open('a') as f:\n"
        " f.write(json.dumps({'wire':wire,'finalization':phase})+'\\n')\n"
        "if op=='allocate':\n"
        " indexes=[int(i) for i,s in state.items() if s=='free'][:args['count']]\n"
        " for i in indexes: state[str(i)]='leased'\n"
        " data={'indexes':indexes}\n"
        "elif op=='quarantine':\n"
        " state[str(args['index'])]='quarantined'; data={}\n"
        "elif op=='release':\n"
        " released=[i for i,s in state.items() if s=='leased']\n"
        " for i in released: state[i]='free'\n"
        " data={'released':len(released)}\n"
        "elif op=='heartbeat': data={'extended':sum(s=='leased' for s in state.values())}\n"
        "else: raise AssertionError(op)\n"
        "state_path.write_text(json.dumps(state))\n"
        "print(json.dumps({'result':'PASS','data':data}))\n"
    )
    channel = LauncherChannel([sys.executable, "-c", script])
    lines: list[str] = []
    setup_evidence: list[tuple[str, object]] = []

    def emit(line: str) -> None:
        lines.append(line)
        if line.startswith("FAIL setup"):
            setup_evidence.append(
                (
                    line,
                    cast(Mapping[str, object], runtime.snapshot()["finalization"])[
                        "started"
                    ],
                )
            )

    async def respond(request: httpx.Request) -> httpx.Response:
        response = await world.api_transport.handle_async_request(request)
        if request.url.path == "/api/profile/" and world.api_calls[-1] == (
            "GET",
            "/api/profile/",
            1,
        ):
            return httpx.Response(200, json=[])
        return response

    async def token_wait(seconds: float) -> None:
        world.clock.now += seconds
        await asyncio.sleep(0)

    assert (
        asyncio.run(
            run_pool_smoke(
                pool_support.POOL,
                3,
                prompt_secret=lambda: pool_support.SECRET,
                channel=channel,
                emit=emit,
                clerk_transport=world.clerk_transport,
                api_transport=httpx.MockTransport(respond),
                sleep=token_wait,
                clock=world.clock,
                run_id=pool_support.RUN_ID,
                safety=runtime,
            )
        )
        != 0
    )
    assert runtime.abort_reason == "correctness"
    assert setup_evidence == [("FAIL setup pending_quarantine=1,2", False)]
    state = json.loads(state_path.read_text())
    assert all(state[str(index)] in {"quarantined", "leased"} for index in (1, 2))
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    quarantines = [call for call in calls if call["wire"]["operation"] == "quarantine"]
    assert all(
        call["finalization"]["started"] and call["finalization"]["allowed"]
        for call in quarantines
    )
    if any(state[str(index)] == "leased" for index in (1, 2)):
        assert cast(Mapping[str, object], runtime.snapshot()["finalization"])[
            "release"
        ] in {
            "skipped",
            "failed",
            "uncertain",
        }
    assert not any(path == "/api/me/" for _, path, _ in world.api_calls)
    assert set(world.ended_sessions) == set(world.opened_sessions)
