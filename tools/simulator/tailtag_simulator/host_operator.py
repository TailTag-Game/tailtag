"""Foreground maintainer authority, immutable preparation, local session and collection."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

from .client import open_client
from .evaluation import EvaluationFailed, evaluate, write_evaluation
from .host_bridge import (
    BridgeServer,
    BridgeSession,
    RelayDispatch,
    relay_dispatch,
)
from .host_protocol import decode_document, encode_frame, validate_manifest
from .host_release import read_release
from .reports import load_report
from .safety import resolve_safety_policy
from .targets import resolve_target, verify_target
from .traffic_config import resolve_traffic_config

SSH_OPTIONS = [
    "-a",
    "-o",
    "ForwardAgent=no",
    "-o",
    "StrictHostKeyChecking=yes",
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
        # Journeys carry a pool-only configuration that validate_manifest closes.
        "configuration": cast(dict[str, object], wrapper["configuration"])
        if wrapper["scenario_id"] == "journeys"
        else resolve_traffic_config(cast(dict[str, object], wrapper["configuration"])),
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


def _host_target(host: str, host_root: Path) -> str:
    """Validate the SSH alias and absolute host root; returns the root text."""
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
    return root_text


def _remote_command(command: list[str], cwd: Path) -> str:
    """Fixed shell grammar; package=false requires the verified release directory."""
    return "cd -- " + shlex.quote(str(cwd)) + " && exec " + shlex.join(command)


async def _exchange(
    command: list[str], payload: dict[str, object], *, cwd: Path | None = None
) -> int:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
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


MAX_EVIDENCE_BYTES = 33_554_432
EVIDENCE_NAMES = {"report": None, "stages": "stages.log", "host": "host.json"}
# Host-mode (#316) operator state, listed only when the run has it.
OPERATOR_EVIDENCE = ("used", "bridge")
STATES = {"settled", "held", "incomplete"}
DEFAULT_BASELINES = Path(__file__).resolve().parents[1] / "baselines"
# The `-o` options of SSH_OPTIONS only: scp never gets -a, -T or recursion.
SCP_OPTIONS = [
    "-o" + value for flag, value in pairwise(SSH_OPTIONS) if flag == "-o"
] + ["-q"]


async def _capture(host: str, command: list[str], cwd: Path) -> bytes:
    """Run one fixed remote command, returning at most 65,536 bytes of stdout."""
    process = await asyncio.create_subprocess_exec(
        "ssh",
        *SSH_OPTIONS,
        host,
        _remote_command(command, cwd),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        raw = b""
        async with asyncio.timeout(30):
            while len(raw) <= 65536 and (chunk := await process.stdout.read(65537)):
                raw += chunk
            if len(raw) > 65536:
                raise ValueError
            await process.wait()
        if process.returncode != 0:
            raise ValueError
        return raw
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _digest_record(value: object, *, optional: bool = False) -> dict[str, Any] | None:
    if value is None and optional:
        return None
    if not isinstance(value, dict) or set(cast(dict[str, Any], value)) != {
        "sha256",
        "bytes",
    }:
        raise ValueError
    record = cast(dict[str, Any], value)
    if (
        not isinstance(record["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        or type(record["bytes"]) is not int
        or not 1 <= record["bytes"] <= MAX_EVIDENCE_BYTES
    ):
        raise ValueError
    return record


def _validate_inventory(
    raw: bytes,
) -> tuple[list[tuple[str, str, dict[str, Any] | None]], int]:
    """Strictly validate the untrusted remote inventory; any defect refuses it all."""
    document = decode_document(raw)
    omitted = document.get("omitted")
    if (
        set(document) != {"schema_version", "runs", "omitted"}
        or document["schema_version"] != 1
        or type(document["schema_version"]) is not int
        or type(omitted) is not int
        or omitted < 0
    ):
        raise ValueError
    runs = document["runs"]
    if not isinstance(runs, list) or len(cast(list[object], runs)) > 64:
        raise ValueError
    seen: set[str] = set()
    listing: list[tuple[str, str, dict[str, Any] | None]] = []
    for item in cast(list[object], runs):
        if not isinstance(item, dict) or set(cast(dict[str, Any], item)) != {
            "run_id",
            "state",
            "files",
        }:
            raise ValueError
        entry = cast(dict[str, Any], item)
        run_id, state, files = entry["run_id"], entry["state"], entry["files"]
        if (
            not isinstance(run_id, str)
            or str(uuid.UUID(run_id)) != run_id
            or run_id in seen
            or state not in STATES
        ):
            raise ValueError
        seen.add(run_id)
        if state != "settled":
            if files is not None:
                raise ValueError
            listing.append((run_id, cast(str, state), None))
            continue
        if not isinstance(files, dict) or not (
            set(EVIDENCE_NAMES)
            <= set(cast(dict[str, Any], files))
            <= {*EVIDENCE_NAMES, *OPERATOR_EVIDENCE}
        ):
            raise ValueError
        digests = cast(dict[str, Any], files)
        listing.append(
            (
                run_id,
                "settled",
                {
                    "report": _digest_record(digests["report"]),
                    "stages": _digest_record(digests["stages"], optional=True),
                    "host": _digest_record(digests["host"]),
                    **{
                        kind: _digest_record(digests[kind])
                        for kind in OPERATOR_EVIDENCE
                        if kind in digests
                    },
                },
            )
        )
    return listing, omitted


async def _fetch(host: str, remote: Path, local: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        "scp",
        *SCP_OPTIONS,
        "--",
        f"{host}:{remote}",
        str(local),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(300):
            await process.wait()
        if process.returncode != 0:
            raise ValueError
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _verify(path: Path, record: dict[str, Any]) -> None:
    """Check size and SHA-256 of a regular, unlinked, owner-held local copy."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != record["bytes"]:
            raise ValueError
        data = os.read(fd, record["bytes"] + 1)
    finally:
        os.close(fd)
    if (
        len(data) != record["bytes"]
        or hashlib.sha256(data).hexdigest() != record["sha256"]
    ):
        raise ValueError


def _write_private(path: Path, value: dict[str, object]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=1, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _evaluate_collected(
    report: dict[str, object], partial: Path, run_id: str, baselines: Path
) -> str:
    """Evaluate a verified convention schema-5 report; never fails the collection."""
    scenario = cast(dict[str, Any], report["scenario"])
    if report["schema_version"] != 5 or not str(scenario["id"]).startswith(
        "convention-"
    ):
        return "not_applicable"
    try:
        artifact = evaluate(
            partial / f"{run_id}.json",
            host_companion=partial / "host.json",
            context=None,
            baselines_dir=baselines,
        )
        write_evaluation(artifact, partial / f"{run_id}.evaluation.json")
    except EvaluationFailed:
        return "failed"
    return "written"


async def _collect_run(
    host: str,
    host_root: Path,
    archive: Path,
    baselines: Path,
    run_id: str,
    files: dict[str, Any],
) -> str:
    """Collect one settled run; returns the result token for its COLLECT line."""
    final, partial = archive / run_id, archive / f".{run_id}.partial"
    try:
        existing = final.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return "failed"
    else:
        # Never touch an existing final directory, even an empty one.
        try:
            recorded = stat.S_ISREG((final / "collected.json").lstat().st_mode)
        except OSError:
            return "failed"
        return "skipped" if stat.S_ISDIR(existing.st_mode) and recorded else "failed"
    renamed = False
    try:
        with suppress(FileNotFoundError):
            if not stat.S_ISDIR(partial.lstat().st_mode):
                return "failed"
            shutil.rmtree(partial)  # A crashed earlier attempt; never evidence.
        partial.mkdir(mode=0o700)
        base = host_root / "runs" / run_id
        sources = {
            "report": (base / "reports" / f"{run_id}.json", f"{run_id}.json"),
            "stages": (base / "reports/stages.log", "stages.log"),
            "host": (base / "host.json", "host.json"),
        }
        for kind in OPERATOR_EVIDENCE:
            if kind in files:
                name = f"{run_id}.{kind}.json"
                sources[kind] = (host_root / "operator-state" / name, name)
        for kind, (remote, name) in sources.items():
            record = files[kind]
            if record is None:
                continue
            await _fetch(host, remote, partial / name)
            _verify(partial / name, record)
        report = load_report(partial / f"{run_id}.json")
        if report["run_id"] != run_id:
            raise ValueError  # A valid report for another run is misattributed.
        evaluation = _evaluate_collected(report, partial, run_id, baselines)
        _write_private(
            partial / "collected.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "files": files,
                "collected_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        _sync(partial)
        os.rename(partial, final)
        renamed = True
        _sync(archive)
        return f"collected evaluation={evaluation}"
    except Exception:  # noqa: BLE001 - public output is deliberately detail-free
        return "failed"
    finally:
        if not renamed:
            shutil.rmtree(partial, ignore_errors=True)


async def _collect(
    host: str, host_root: Path, release_path: Path, archive: Path, baselines: Path
) -> int:
    root_text = _host_target(host, host_root)
    if re.fullmatch(r"/[A-Za-z0-9_./-]+", root_text) is None:
        raise ValueError  # scp remote paths are not shell-quoted.
    archive = archive.absolute()
    _private_directory(archive)
    release = read_release(release_path)
    runtime = host_root / "releases" / str(release["simulator_sha"])
    listing, omitted = _validate_inventory(
        await _capture(
            host,
            [
                str(runtime / ".venv/bin/python"),
                "-m",
                "tailtag_simulator.host_runner",
                "inventory",
                "--root",
                root_text,
            ],
            runtime,
        )
    )
    failed = False
    if omitted:
        print(f"COLLECT omitted={omitted}", flush=True)
    for run_id, state, files in sorted(listing, key=lambda item: item[0]):
        if files is None:
            result = state
        else:
            result = await _collect_run(
                host, host_root, archive, baselines, run_id, files
            )
        failed = failed or result == "failed"
        print(f"COLLECT {run_id} {result}", flush=True)
    return 1 if failed else 0


async def _operate(
    manifest: dict[str, object],
    state: Path,
    dispatch: RelayDispatch,
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]],
    prepare: Callable[[], Awaitable[int]],
    bind: Callable[[BridgeSession], BridgeServer],
    spawn: Callable[[], Awaitable[asyncio.subprocess.Process]],
    resolve: Callable[[dict[str, object]], Awaitable[int]],
) -> int:
    """Session core; the local adapter supplies only the transport."""
    process: asyncio.subprocess.Process | None = None
    server: BridgeServer | None = None
    session: BridgeSession | None = None
    previous: dict[int, object] = {}
    try:
        _private_directory(state)
        run_id = str(manifest["run_id"])
        _write_new(
            state / (run_id + ".used.json"), {"schema_version": 1, "run_id": run_id}
        )
        if await prepare():
            return 1
        session = BridgeSession(manifest, dispatch, clock=clock)
        server = bind(session)
        await server.start()
        safety = cast(dict[str, object], manifest["safety"])
        execution_end = clock() + cast(float, safety["seconds"])
        terminal_end = execution_end + cast(float, safety["final_seconds"])
        stopped = False
        interrupted = False

        def revoke(cause: str) -> None:
            nonlocal stopped, terminal_end
            if not stopped:
                stopped = True
                terminal_end = min(
                    terminal_end, clock() + cast(float, safety["final_seconds"])
                )
                assert session is not None
                session.revoke_workload(cause)

        def interrupt(sig: signal.Signals) -> None:
            nonlocal interrupted
            interrupted = True
            revoke("signal_" + sig.name)
            # Local mode has no SSH to drop: the child must hear the signal itself.
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.send_signal(sig)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            loop.add_signal_handler(sig, interrupt, sig)
        process = await spawn()  # Inherit the caller's real TTY; no transcript.
        while process.returncode is None:
            if clock() >= execution_end:
                revoke("execution_deadline")
            if clock() >= terminal_end:
                revoke("terminal_deadline")
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
                revoke("child_exit")
        revoke("operator_exit")
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
        if process.returncode == 0 and receipt["disposition"] in {
            "released",
            "no_mutation",
        }:
            resolved = await resolve(receipt) == 0
        return (
            0
            if process.returncode == 0
            and not interrupted
            and resolved
            and clock() < execution_end
            else 1
        )
    finally:
        if session is not None:
            session.revoke_workload("operator_exit")
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        if server is not None:
            await server.close()
        for sig, handler in previous.items():
            asyncio.get_running_loop().remove_signal_handler(sig)
            signal.signal(sig, handler)  # type: ignore[arg-type]


def _plain_absolute(path: Path) -> bool:
    """True for an absolute path with no symlink in it or in any ancestor."""
    return path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents))


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _refuse_local(workspace: Path, tools: Path) -> Path | None:
    """Return the host `uv` when every start condition holds; otherwise None (C1)."""
    uv = next((p for p in (tools / "uv", tools / "bin/uv") if _executable(p)), None)
    if (
        os.environ.get("RAILWAY_NO_AUTO_UPDATE") != "1"
        or not (os.isatty(0) and os.isatty(1))  # The Clerk prompt needs a terminal.
        or not (workspace / "Taskfile.yml").is_file()
        or not (workspace / "services/api").is_dir()
        or not _executable(tools / "bin/task")
        or not _executable(tools / "bin/railway")
    ):
        return None
    return uv


async def run_local_session(
    manifest: dict[str, object],
    host_root: Path,
    workspace: Path,
    tools: Path,
    state_dir: Path,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Own the bridge and a local host_runner child on the host itself (#316)."""
    try:
        manifest = validate_manifest(manifest)
        uv = (
            _refuse_local(workspace, tools)
            if all(map(_plain_absolute, (host_root, workspace, tools, state_dir)))
            else None
        )
        if uv is None:
            print("REFUSED run-local", flush=True)
            return 1
        run_id = str(manifest["run_id"])
        release = cast(dict[str, object], manifest["release"])
        runtime = host_root / "releases" / str(release["simulator_sha"])
        command = [
            str(runtime / ".venv/bin/python"),
            "-m",
            "tailtag_simulator.host_runner",
        ]
        root_text = str(host_root)
        base = host_root / "runs" / run_id
        # Explicit and minimal: nothing of the operator's own PATH reaches the relays.
        env = {
            "PATH": os.pathsep.join(
                [str(tools / "bin"), "/usr/local/bin", "/usr/bin", "/bin"]
            ),
            "UV": str(uv),
            "RAILWAY_NO_AUTO_UPDATE": "1",
            "HOME": os.environ["HOME"],
        }

        async def spawn() -> asyncio.subprocess.Process:
            # Same process group: a terminal Ctrl-C reaches the runner as it does over ssh -tt.
            return await asyncio.create_subprocess_exec(
                *command,
                "run",
                "--root",
                root_text,
                "--manifest",
                str(base / "control/manifest.json"),
                "--release",
                str(runtime / "release.json"),
                cwd=runtime,
            )

        return await _operate(
            manifest,
            state_dir,
            relay_dispatch(workspace, tools / "bin/task", env),
            clock=clock,
            sleep=sleep,
            prepare=lambda: _exchange(
                [*command, "prepare", "--root", root_text, "--manifest", "-"],
                manifest,
                cwd=runtime,
            ),
            bind=lambda session: BridgeServer.for_paths(
                session, base / "rpc/rpc.sock", base / "control/health.sock"
            ),
            spawn=spawn,
            resolve=lambda receipt: _exchange(
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
                cwd=runtime,
            ),
        )
    except (OSError, ValueError, TimeoutError, KeyError):
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("profile", "safety-config", "release", "output"):
        prepare.add_argument("--" + name, type=Path, required=True)
    local = commands.add_parser("run-local")
    for name in ("manifest", "host-root", "workspace", "tools", "state-dir"):
        local.add_argument("--" + name, type=Path, required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--host", required=True)
    collect.add_argument("--host-root", type=Path, required=True)
    collect.add_argument("--release", type=Path, required=True)
    collect.add_argument("--archive", type=Path, required=True)
    collect.add_argument("--baselines-dir", type=Path, default=DEFAULT_BASELINES)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            return asyncio.run(
                _collect(
                    args.host,
                    args.host_root,
                    args.release,
                    args.archive,
                    args.baselines_dir,
                )
            )
        if args.command == "prepare":
            return asyncio.run(
                _prepare(args.profile, args.safety_config, args.release, args.output)
            )
        return asyncio.run(
            run_local_session(
                read_json(args.manifest),
                args.host_root,
                args.workspace,
                args.tools,
                args.state_dir,
            )
        )
    except Exception:  # noqa: BLE001 - public error is deliberately detail-free
        print("FAIL host_operator", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
