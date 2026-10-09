"""Foreground maintainer authority, immutable preparation and owned SSH session."""

import argparse
import asyncio
import os
import re
import shlex
import signal
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import cast

from .client import open_client
from .host_bridge import BridgeServer, BridgeSession, fixed_dispatch
from .host_protocol import decode_document, encode_frame, validate_manifest
from .host_release import read_release
from .safety import resolve_safety_policy
from .targets import resolve_target, verify_target
from .traffic_config import resolve_traffic_config

SSH_OPTIONS = [
    "-a",
    "-o",
    "ForwardAgent=no",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ExitOnForwardFailure=yes",
    "-o",
    "StreamLocalBindUnlink=no",
]


def read_json(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError
    with path.open("rb") as stream:
        raw = stream.read(65537)
    return decode_document(raw)


def _private_directory(path: Path) -> None:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o700:
        raise ValueError


def _write_new(path: Path, value: dict[str, object]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encode_frame(value))
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


async def _prepare(
    profile: Path, safety: Path, release_path: Path, output: Path
) -> int:
    wrapper = read_json(profile)
    if set(wrapper) != {"scenario_id", "scenario_version", "seed", "configuration"}:
        raise ValueError
    release = read_release(release_path)
    manifest = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        **wrapper,
        "configuration": resolve_traffic_config(
            cast(dict[str, object], wrapper["configuration"])
        ),
        "safety": resolve_safety_policy(read_json(safety)),
        "backend_identity": {
            "source_sha": "0" * 40,
            "deployment_id": "00000000-0000-4000-8000-000000000000",
            "environment": "staging",
        },
        "release": {
            key: release[key]
            for key in (
                "simulator_sha",
                "dependency_lock_sha256",
                "image_id",
                "platform",
            )
        },
    }
    validate_manifest(manifest)  # Resolve every local premise before network.
    target = resolve_target("staging", None)
    async with open_client(target.origin) as client:
        manifest["backend_identity"] = (await verify_target(client, target)).identity()
    _write_new(output, validate_manifest(manifest))
    return 0


async def _control(host: str, command: list[str], payload: dict[str, object]) -> int:
    process = await asyncio.create_subprocess_exec(
        "ssh",
        *SSH_OPTIONS,
        host,
        shlex.join(command),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.communicate(encode_frame(payload)), 30)
        return int(process.returncode or 0)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def run_session(
    manifest: dict[str, object],
    host: str,
    host_root: Path,
    *,
    state_dir: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Own the bridge and attached SSH child; workload authority never renews."""
    process: asyncio.subprocess.Process | None = None
    server: BridgeServer | None = None
    session: BridgeSession | None = None
    previous: dict[int, object] = {}
    try:
        manifest = validate_manifest(manifest)
        root_text = str(host_root)
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", host) is None
            or not host_root.is_absolute()
            or len(root_text) > 512
            or any(ord(c) < 32 or ord(c) == 127 for c in root_text)
            or ":" in root_text
            or "," in root_text
        ):
            raise ValueError
        state = state_dir or Path.home() / ".local/state/tailtag-simulator"
        _private_directory(state)
        run_id = str(manifest["run_id"])
        _write_new(
            state / (run_id + ".used.json"), {"schema_version": 1, "run_id": run_id}
        )
        release = cast(dict[str, object], manifest["release"])
        python = str(
            host_root / "releases" / str(release["simulator_sha"]) / ".venv/bin/python"
        )
        command = [python, "-m", "tailtag_simulator.host_runner"]
        if await _control(
            host,
            [*command, "prepare", "--root", root_text, "--manifest", "-"],
            manifest,
        ):
            return 1
        with tempfile.TemporaryDirectory(prefix="tailtag-op-", dir="/tmp") as temporary:
            directory = Path(temporary).resolve()
            directory.chmod(0o700)
            session = BridgeSession(manifest, fixed_dispatch, clock=clock)
            server = BridgeServer(session, directory)
            await server.start()
            safety = cast(dict[str, object], manifest["safety"])
            execution_end = clock() + cast(float, safety["seconds"])
            terminal_end = execution_end + cast(float, safety["final_seconds"])
            stopped = False
            interrupted = False

            def revoke() -> None:
                nonlocal stopped, terminal_end
                if not stopped:
                    stopped = True
                    terminal_end = min(
                        terminal_end, clock() + cast(float, safety["final_seconds"])
                    )
                    assert session is not None
                    session.revoke_workload()

            def interrupt() -> None:
                nonlocal interrupted
                interrupted = True
                revoke()

            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
                previous[sig] = signal.getsignal(sig)
                loop.add_signal_handler(sig, interrupt)
            base = host_root / "runs" / run_id
            process = await asyncio.create_subprocess_exec(
                "ssh",
                *SSH_OPTIONS,
                *(["-tt"] if os.isatty(0) and os.isatty(1) else []),
                "-R",
                str(base / "rpc/rpc.sock") + ":" + str(directory / "rpc.sock"),
                "-R",
                str(base / "control/health.sock")
                + ":"
                + str(directory / "health.sock"),
                host,
                shlex.join(
                    [
                        *command,
                        "run",
                        "--root",
                        root_text,
                        "--manifest",
                        str(base / "control/manifest.json"),
                        "--release",
                        str(
                            host_root
                            / "releases"
                            / str(release["simulator_sha"])
                            / "release.json"
                        ),
                    ]
                ),
            )  # Inherit the caller's real TTY; no input/output transcript.
            while process.returncode is None:
                if clock() >= execution_end:
                    revoke()
                if clock() >= terminal_end:
                    revoke()
                    break
                # Bound owned-child exit observation independently of a fake clock.
                waiter = asyncio.create_task(process.wait())
                pause = asyncio.ensure_future(
                    sleep(min(0.1, max(0, terminal_end - clock())))
                )
                done, pending = await asyncio.wait(
                    (waiter, pause), return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(
                    *cast(list[asyncio.Future[object]], list(pending)),
                    return_exceptions=True,
                )
                if waiter in done:
                    revoke()
            revoke()
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            await session.settle()
            _write_new(state / (run_id + ".bridge.json"), session.evidence())
            receipt = session.receipt()
            resolved = False
            if receipt["disposition"] in {"released", "no_mutation"}:
                resolved = (
                    await _control(
                        host,
                        [
                            *command,
                            "recovery-resolve",
                            "--root",
                            root_text,
                            "--run-id",
                            run_id,
                            "--receipt",
                            "-",
                        ],
                        receipt,
                    )
                    == 0
                )
            return (
                0
                if process.returncode == 0
                and not interrupted
                and resolved
                and clock() < execution_end
                else 1
            )
    except (OSError, ValueError, TimeoutError):
        return 1
    finally:
        if session is not None:
            session.revoke_workload()
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        if server is not None:
            await server.close()
        for sig, handler in previous.items():
            asyncio.get_running_loop().remove_signal_handler(sig)
            signal.signal(sig, handler)  # type: ignore[arg-type]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("profile", "safety-config", "release", "output"):
        prepare.add_argument("--" + name, type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--host", required=True)
    run.add_argument("--host-root", type=Path, required=True)
    run.add_argument("--state-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            return asyncio.run(
                _prepare(args.profile, args.safety_config, args.release, args.output)
            )
        return asyncio.run(
            run_session(
                read_json(args.manifest),
                args.host,
                args.host_root,
                state_dir=args.state_dir,
            )
        )
    except Exception:  # noqa: BLE001 - public error is deliberately detail-free
        print("FAIL host_operator", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
