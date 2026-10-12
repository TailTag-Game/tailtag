"""#228 U2: actual launcher shims preserve wire contracts and hide bad peers."""

import asyncio
import json
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import pytest

from tailtag_simulator.fixtures import FixtureFailed, FixtureLauncherChannel
from tailtag_simulator.pool import LauncherChannel, LeaseFailed
from tailtag_simulator.population_reconciliation import (
    PopulationInspectionLauncherChannel,
)
from tailtag_simulator.reconciliation import InspectionFailed
from tailtag_simulator.safety import SafetyRuntime

RUN = "55555555-5555-4555-8555-555555555555"
IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
SENTINEL = "SENTINEL-private-secret"


def shim(directory: Path, channel: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tailtag_simulator.host_channel",
        "--channel",
        channel,
        "--socket-dir",
        str(directory),
    ]


@pytest.mark.parametrize("channel", ["pool", "fixture", "inspection"])
@pytest.mark.parametrize("result", ["PASS", "FAIL_TARGET"])
def test_existing_launcher_uses_real_shim_and_exact_private_rpc_wire(
    channel: str, result: str
) -> None:
    async def execute(directory: Path) -> None:
        seen: list[object] = []

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                raw = await reader.readline()
                seen.append(json.loads(raw))
                writer.write(
                    json.dumps({"result": result, "data": {"count": 3}}).encode()
                    + b"\n"
                )
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(serve, path=directory / "rpc.sock")
        command = shim(directory, channel)
        invoke: Callable[[], Awaitable[Mapping[str, object]]]
        if channel == "pool":
            lease = LauncherChannel(command, timeout_seconds=5)
            invoke = lambda: lease.call("release", "alpha", {"run_id": RUN})
            envelope: dict[str, object] = {
                "operation": "release",
                "pool": "alpha",
                "arguments": {"run_id": RUN},
            }
        elif channel == "fixture":
            fixture = FixtureLauncherChannel(command, timeout_seconds=5)
            invoke = lambda: fixture.call("cleanup", {"pool": "alpha", "run_id": RUN})
            envelope = {
                "operation": "cleanup",
                "arguments": {"pool": "alpha", "run_id": RUN},
            }
        else:
            inspection = PopulationInspectionLauncherChannel(command, timeout_seconds=5)
            invoke = lambda: inspection.inspect(
                "alpha", RUN, {"owner0": 17, "attendee0": 23}
            )
            envelope = {
                "operation": "inspect-population-v1",
                "arguments": {
                    "pool": "alpha",
                    "run_id": RUN,
                    "identities": {"owner0": 17, "attendee0": 23},
                },
            }
        runtime = SafetyRuntime({})

        async def probe() -> dict[str, object]:
            return dict(IDENTITY)

        runtime.bind_probe(probe)
        try:
            with runtime.scope():
                await runtime.check_target()
                if result == "PASS":
                    assert await invoke() == {"count": 3}
                else:
                    with pytest.raises(
                        (LeaseFailed, FixtureFailed, InspectionFailed)
                    ) as caught:
                        await invoke()
                    assert caught.value.result == "FAIL_TARGET"
                    assert runtime.abort_reason == "identity_mismatch"
            assert seen == [
                {
                    "schema_version": 1,
                    "channel": channel,
                    "request": {**envelope, "expected_identity": IDENTITY},
                }
            ]
        finally:
            server.close()
            await server.wait_closed()

    # macOS Unix path length is smaller than a typical pytest temporary path.
    with tempfile.TemporaryDirectory(prefix="t228-", dir="/tmp") as path:
        asyncio.run(execute(Path(path).resolve()))


BAD_REPLIES: dict[str, bytes | None] = {
    "missing-socket": None,
    "raw-diagnostic": f"{SENTINEL}\n".encode(),
    "unknown-field": f'{{"result":"PASS","data":{{}},"error":"{SENTINEL}"}}\n'.encode(),
    "duplicate-result": b'{"result":"PASS","result":"FAIL_TARGET","data":{}}\n',
    "unsafe-result": f'{{"result":"FAIL_{SENTINEL}","data":{{}}}}\n'.encode(),
    "nonfinite": b'{"result":"PASS","data":{"count":NaN}}\n',
    "oversized": b'{"result":"PASS","data":{"error":"' + b"x" * 65536 + b'"}}\n',
    "closed-before-reply": b"",
}


@pytest.mark.parametrize("fault", BAD_REPLIES)
def test_shim_transport_failures_emit_only_closed_failure_without_peer_details(
    fault: str,
) -> None:
    async def execute(directory: Path) -> None:
        reply = BAD_REPLIES[fault]

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                await reader.readline()
                writer.write(reply or b"")
                await writer.drain()
            except (ConnectionError, BrokenPipeError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = (
            await asyncio.start_unix_server(serve, path=directory / "rpc.sock")
            if reply is not None
            else None
        )
        process = await asyncio.create_subprocess_exec(
            *shim(directory, "pool"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            output, error = await asyncio.wait_for(
                process.communicate(
                    json.dumps(
                        {
                            "operation": "release",
                            "pool": "alpha",
                            "arguments": {"run_id": RUN},
                            "expected_identity": IDENTITY,
                        }
                    ).encode()
                ),
                5,
            )
            assert process.returncode == 1
            assert json.loads(output) == {"result": "FAIL_LAUNCHER", "data": {}}
            assert SENTINEL.encode() not in output + error
            assert str(directory).encode() not in error
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if server is not None:
                server.close()
                await server.wait_closed()

    with tempfile.TemporaryDirectory(prefix="t228-", dir="/tmp") as path:
        asyncio.run(execute(Path(path).resolve()))
