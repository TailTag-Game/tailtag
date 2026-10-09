"""Owner-private Linux admission and irreversible named-container supervision."""

import argparse
import asyncio
import json
import math
import os
import platform
import resource
import signal
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import cast

from .host_artifacts import admit_run, resolve_recovery
from .host_operator import (
    _private_directory,  # pyright: ignore[reportPrivateUsage]
    _write_new,  # pyright: ignore[reportPrivateUsage]
    read_json,
)
from .host_protocol import (
    decode_document,
    decode_frame,
    encode_frame,
    validate_manifest,
)
from .host_release import read_release, verify_image


async def _docker(*arguments: str, timeout: float = 2) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "docker",
        *arguments,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        raw = await asyncio.wait_for(process.stdout.read(65537), timeout)
        await asyncio.wait_for(process.wait(), timeout)
        if len(raw) > 65536 or process.returncode != 0:
            raise ValueError
        return raw
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _running(name: str) -> tuple[bool, int]:
    value: object = json.loads(await _docker("inspect", name))
    if not isinstance(value, list) or len(cast(list[object], value)) != 1:
        raise ValueError
    item = cast(list[dict[str, object]], value)[0]
    state = cast(dict[str, object], item["State"])
    if type(state.get("Running")) is not bool or type(state.get("ExitCode")) is not int:
        raise ValueError
    return cast(bool, state["Running"]), cast(int, state["ExitCode"])


async def _health(path: Path, run_id: str) -> bool:
    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(2):
            reader, writer = await asyncio.open_unix_connection(path, limit=65536)
            writer.write(
                encode_frame(
                    {"schema_version": 1, "channel": "health", "run_id": run_id}
                )
            )
            await writer.drain()
            reply = decode_frame(await reader.readline())
            return (
                set(reply) == {"run_id", "live"}
                and reply["run_id"] == run_id
                and reply["live"] is True
            )
    except (OSError, ValueError, TimeoutError):
        return False
    finally:
        if writer is not None:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


async def _sample(name: str) -> dict[str, object]:
    sample: dict[str, object] = {
        "cpu_percent": None,
        "memory_percent": None,
        "cpu_steal_ticks": None,
    }
    try:
        raw = await _docker("stats", "--no-stream", "--format", "{{json .}}", name)
        stats = decode_frame(raw.rstrip(b"\n") + b"\n")
        for source, target in (
            ("CPUPerc", "cpu_percent"),
            ("MemPerc", "memory_percent"),
        ):
            text = stats[source]
            if isinstance(text, str) and len(text) <= 16 and text.endswith("%"):
                number = float(text[:-1])
                if math.isfinite(number) and 0 <= number <= 10000:
                    sample[target] = number
        with Path("/proc/stat").open() as stream:  # noqa: ASYNC230 - bounded local kernel counter
            parts = stream.readline(256).split()
        if parts[0] == "cpu" and len(parts) >= 9:
            ticks = int(parts[8])
            if 0 <= ticks < 2**63:
                sample["cpu_steal_ticks"] = ticks
    except (OSError, ValueError, KeyError, TimeoutError):
        pass
    return sample


async def supervise_run(
    manifest: dict[str, object],
    release: dict[str, object],
    root: Path,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Real admission/socket/filesystem with Docker as the external boundary."""
    manifest = validate_manifest(manifest)
    pinned = cast(dict[str, object], manifest["release"])
    if any(release.get(key) != value for key, value in pinned.items()):
        raise ValueError
    process: asyncio.subprocess.Process | None = None
    name = "tailtag-sim-" + str(manifest["run_id"])
    previous: dict[int, object] = {}
    requested_stop: str | None = None
    launched = False
    container_finished = False
    stop_event = asyncio.Event()
    hard_stop = False
    stop_reason: str | None = None
    final_at: float | None = None
    samples: list[dict[str, object]] = []
    safety = cast(dict[str, object], manifest["safety"])
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        nonlocal requested_stop
        requested_stop = "operator_interrupted"
        stop_event.set()

    try:
        with admit_run(root, manifest) as artifacts:
            try:
                # Admission owns the whole-host lock before any external image/workload action.
                verify_image(release)
                for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.getsignal(sig)
                    loop.add_signal_handler(sig, request_stop)
                base = artifacts.base
                # Only rpc is exposed; the host-only control directory stays unmounted.
                process = await asyncio.create_subprocess_exec(
                    "docker",
                    "run",
                    "--name",
                    name,
                    "--init",
                    "--interactive",
                    *(["--tty"] if sys.stdin.isatty() and sys.stdout.isatty() else []),
                    "--log-driver=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--ulimit",
                    "core=0:0",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--cpus=2",
                    "--memory=3g",
                    "--memory-swap=3g",
                    "--mount",
                    f"type=bind,src={base / 'rpc'},dst=/bridge,readonly",
                    "--mount",
                    f"type=bind,src={base / 'control/manifest.json'},dst=/manifest.json,readonly",
                    "--mount",
                    f"type=bind,src={artifacts.report_dir},dst=/reports",
                    "--entrypoint",
                    "python",
                    str(pinned["image_id"]),
                    "-m",
                    "tailtag_simulator",
                    "convention",
                    "--family",
                    str(cast(dict[str, object], manifest["configuration"])["family"]),
                    "--pool",
                    str(cast(dict[str, object], manifest["configuration"])["pool"]),
                    "--scenario-version",
                    "2",
                    "--seed",
                    str(manifest["seed"]),
                    "--host-manifest",
                    "/manifest.json",
                    "--host-socket-dir",
                    "/bridge",
                    "--report-dir",
                    "/reports",
                    "--stage-log",
                    "/reports/stages.log",
                )
                launched = True
                started = clock()
                execution_end = started + cast(float, safety["seconds"])
                last_live = started
                next_health = started
                exit_code = 1
                while True:
                    now = clock()
                    if stop_reason is None:
                        if now >= next_health:
                            if await _health(
                                base / "control/health.sock", str(manifest["run_id"])
                            ):
                                last_live = clock()
                            next_health = now + 5
                            if len(samples) < 301:
                                samples.append(await _sample(name))
                        try:
                            artifacts.check_budget()
                        except (OSError, ValueError):
                            requested_stop = "storage_uncertain"
                        now = clock()
                        if requested_stop:
                            stop_reason = requested_stop
                        elif now >= math.nextafter(execution_end, -math.inf):
                            stop_reason = "execution_deadline"
                        elif now - last_live >= 30:
                            stop_reason = "supervision_lost"
                        elif process.returncode is not None:
                            running, exit_code = await _running(name)
                            if not running:
                                container_finished = True
                                break
                            stop_reason = "attached_client_lost"
                        if stop_reason:
                            final_at = (
                                clock() + cast(float, safety["final_seconds"]) + 10
                            )
                            await _docker("kill", "--signal", "SIGINT", name)
                    if stop_reason is not None:
                        running, exit_code = await _running(name)
                        if not running:
                            container_finished = True
                            break
                        assert final_at is not None
                        if clock() >= math.nextafter(final_at, -math.inf):
                            await _docker("kill", "--signal", "SIGKILL", name)
                            hard_stop = True
                            container_finished = True
                            exit_code = 1
                            break
                    # An attached client may die without its named container exiting.
                    waiter = (
                        asyncio.create_task(process.wait())
                        if process.returncode is None
                        else None
                    )
                    deadline = (
                        final_at
                        if stop_reason
                        else min(execution_end, next_health, last_live + 30)
                    )
                    pause = asyncio.ensure_future(
                        sleep(min(5, max(0, cast(float, deadline) - clock())))
                    )
                    wake = (
                        asyncio.create_task(stop_event.wait())
                        if stop_reason is None
                        else None
                    )
                    tasks = (
                        [pause]
                        + ([waiter] if waiter is not None else [])
                        + ([wake] if wake is not None else [])
                    )
                    _, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(
                        *cast(list[asyncio.Future[object]], list(pending)),
                        return_exceptions=True,
                    )
                if process.returncode is None:
                    if hard_stop:
                        process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 2)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                evidence: dict[str, object] = {
                    "schema_version": 1,
                    "run_id": manifest["run_id"],
                    "image_id": pinned["image_id"],
                    "platform": pinned["platform"],
                    "stop_reason": stop_reason,
                    "hard_stop": hard_stop,
                    "container_exit_code": max(-255, min(255, exit_code)),
                    "recovery": "uncertain",
                    "samples": samples,
                }
                artifacts.record_completion(evidence)
                return 1 if stop_reason or hard_stop or exit_code != 0 else 0
            finally:
                if launched and not container_finished:
                    # A failed client/inspection is no evidence that Docker stopped.
                    with suppress(OSError, ValueError, TimeoutError):
                        await _docker("kill", "--signal", "SIGINT", name)
                        await _docker(
                            "wait",
                            name,
                            timeout=cast(float, safety["final_seconds"]) + 10,
                        )
                    with suppress(OSError, ValueError, TimeoutError):
                        await _docker("kill", "--signal", "SIGKILL", name)
                if process is not None and process.returncode is None:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
                if launched:
                    await _docker("rm", name)
    finally:
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)  # type: ignore[arg-type]


def _linux_policy() -> None:
    if (
        platform.system() != "Linux"
        or platform.machine() not in {"x86_64", "amd64"}
        or os.getuid() == 0
    ):
        raise ValueError
    if len(Path("/proc/swaps").read_text().splitlines()) != 1:
        raise ValueError
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if Path("/proc/sys/kernel/core_pattern").read_text().strip() != "|/bin/false":
        raise ValueError


def _input(path: str) -> dict[str, object]:
    return (
        decode_document(sys.stdin.buffer.read(65537))
        if path == "-"
        else read_json(Path(path))
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run", "stop", "recovery-resolve"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", type=Path, required=True)
        if command in {"prepare", "run"}:
            sub.add_argument("--manifest", required=True)
        else:
            sub.add_argument("--run-id", required=True)
        if command == "run":
            sub.add_argument("--release", type=Path, required=True)
        if command == "recovery-resolve":
            sub.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"prepare", "run"}:
            _linux_policy()
        if args.command == "prepare":
            value = validate_manifest(_input(args.manifest))
            root = args.root
            _private_directory(root)
            runs = root / "runs"
            _private_directory(runs)
            base = runs / str(value["run_id"])
            base.mkdir(mode=0o700)
            (base / "rpc").mkdir(mode=0o700)
            (base / "control").mkdir(mode=0o700)
            _write_new(base / "control/manifest.json", value)
            return 0
        if args.command == "run":
            return asyncio.run(
                supervise_run(
                    _input(args.manifest), read_release(args.release), args.root
                )
            )
        if str(uuid.UUID(args.run_id)) != args.run_id:
            raise ValueError
        if args.command == "stop":
            if not args.root.exists():
                raise ValueError
            _private_directory(args.root)
            owned = validate_manifest(
                read_json(args.root / "runs" / args.run_id / "control/manifest.json")
            )
            if owned["run_id"] != args.run_id:
                raise ValueError
            asyncio.run(
                _docker("kill", "--signal", "SIGINT", "tailtag-sim-" + args.run_id)
            )
            return 0
        resolve_recovery(args.root, args.run_id, _input(args.receipt))
        return 0
    except Exception:  # noqa: BLE001 - never expose terminal/provider diagnostics
        print("FAIL host_runner", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
