"""Immutable Docker archive verification and attributed host runtime installation."""

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import selectors
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path
from types import FrameType
from typing import Any, cast

from .host_artifacts import (
    _private,  # pyright: ignore[reportPrivateUsage]
    _read,  # pyright: ignore[reportPrivateUsage]
    _write,  # pyright: ignore[reportPrivateUsage]
)
from .provenance import (
    DIGEST,
    SHA,
    SourceRejected,
    _packaged,  # pyright: ignore[reportPrivateUsage]
    _pairs,  # pyright: ignore[reportPrivateUsage]
)

IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
MAX_COMMAND_OUTPUT_BYTES = 65536
COMMAND_SECONDS = 30.0
TRANSFER_SECONDS = 300.0
CLEANUP_SECONDS = 5.0
# Actual CLI signal session and async-owned verifier worker share cancellation.
_COMMAND_STATE: ContextVar[tuple[threading.Event, float | None] | None] = ContextVar(
    "host_release_command_state", default=None
)


def _validate_release(value: object) -> dict[str, Any]:
    keys = {
        "schema_version",
        "simulator_sha",
        "dependency_lock_sha256",
        "image_id",
        "platform",
        "archive_sha256",
    }
    if not isinstance(value, Mapping):
        raise SourceRejected()
    result = dict(cast(Mapping[str, Any], value))
    if set(result) != keys:
        raise SourceRejected()
    if (
        type(result["schema_version"]) is not int
        or result["schema_version"] != 1
        or result["platform"] != "linux/amd64"
    ):
        raise SourceRejected()
    for key, pattern in (
        ("simulator_sha", SHA),
        ("dependency_lock_sha256", DIGEST),
        ("archive_sha256", DIGEST),
        ("image_id", IMAGE),
    ):
        if not isinstance(result[key], str) or pattern.fullmatch(result[key]) is None:
            raise SourceRejected()
    return result


def read_release(path: Path) -> dict[str, object]:
    """Read closed immutable release metadata without exposing untrusted detail."""
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise SourceRejected()
        value: object = json.loads(path.read_text(), object_pairs_hook=_pairs)
        return _validate_release(value)
    except (OSError, ValueError):
        raise SourceRejected() from None


def _cancelled() -> bool:
    state = _COMMAND_STATE.get()
    return state is not None and state[0].is_set()


def _reap(process: subprocess.Popen[bytes]) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        try:
            process.wait(timeout=1)
            return
        except subprocess.TimeoutExpired:
            continue
    raise SourceRejected()


def _run(
    arguments: list[str],
    *,
    timeout_seconds: float = COMMAND_SECONDS,
    cleanup: bool = False,
    deadline: float | None = None,
) -> str:
    state = None if cleanup else _COMMAND_STATE.get()
    if state is not None and state[0].is_set():
        raise SourceRejected()
    deadline = (
        min(deadline, time.monotonic() + timeout_seconds)
        if deadline is not None
        else time.monotonic() + timeout_seconds
    )
    if state is not None and state[1] is not None:
        deadline = min(deadline, state[1])
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    output = bytearray()
    completed = False
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or (state is not None and state[0].is_set()):
                    raise SourceRejected()
                for key, _ in selector.select(min(0.05, remaining)):
                    chunk = os.read(
                        key.fd, min(65536, MAX_COMMAND_OUTPUT_BYTES - len(output) + 1)
                    )
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(output) + len(chunk) > MAX_COMMAND_OUTPUT_BYTES:
                        raise SourceRejected()
                    else:
                        output.extend(chunk)
            if process.returncode != 0 or time.monotonic() >= deadline:
                raise SourceRejected()
            completed = True
        return output.decode("utf-8")
    finally:
        if not completed or process.poll() is None:
            _reap(process)
        if process.stdout is not None:
            process.stdout.close()


@contextmanager
def _cli_signals() -> Generator[None]:
    cancelled = threading.Event()
    token = _COMMAND_STATE.set((cancelled, None))
    previous: dict[int, object] = {}

    def request_stop(_sig: int, _frame: FrameType | None) -> None:
        cancelled.set()

    try:
        for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, request_stop)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)  # type: ignore[arg-type]
        _COMMAND_STATE.reset(token)


def _probe_seconds(value: float) -> float:
    if type(value) not in {int, float} or not 0 < value <= COMMAND_SECONDS:
        raise SourceRejected()
    return value


def _hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SourceRejected()
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _remove_named(name: str) -> None:
    deadline = time.monotonic() + CLEANUP_SECONDS
    try:
        _run(["docker", "rm", "--force", name], cleanup=True, deadline=deadline)
        return
    except SourceRejected:
        if time.monotonic() >= deadline:
            raise
    remaining = _run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            "name=^/" + name + "$",
            "--format",
            "{{.Names}}",
        ],
        cleanup=True,
        deadline=deadline,
    )
    if remaining.strip():
        raise SourceRejected()


def _probe_source(image: str, *, timeout_seconds: float) -> str:
    name = "tailtag-sim-source-" + str(uuid.uuid4())
    try:
        return _run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--rm",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--log-driver=none",
                "--entrypoint",
                "python",
                image,
                "-m",
                "tailtag_simulator.provenance",
                "inspect",
            ],
            timeout_seconds=timeout_seconds,
        )
    finally:
        _remove_named(name)


def _inspect(image: str, *, timeout_seconds: float = COMMAND_SECONDS) -> dict[str, Any]:
    seconds = _probe_seconds(timeout_seconds)
    state = _COMMAND_STATE.get()
    token = _COMMAND_STATE.set(
        (state[0] if state else threading.Event(), time.monotonic() + seconds)
    )
    try:
        result = _inspect_body(image, timeout_seconds=seconds)
        if _cancelled():
            raise SourceRejected()
        return result
    finally:
        _COMMAND_STATE.reset(token)


def _inspect_body(image: str, *, timeout_seconds: float) -> dict[str, Any]:
    if IMAGE.fullmatch(image) is None:
        raise SourceRejected()
    value: Any = json.loads(
        _run(["docker", "image", "inspect", image]), object_pairs_hook=_pairs
    )
    if (
        not isinstance(value, list)
        or len(cast(list[Any], value)) != 1
        or not isinstance(value[0], dict)
    ):
        raise SourceRejected()
    value = cast(list[dict[str, Any]], value)
    if (
        len(value) != 1
        or value[0].get("Id") != image
        or value[0].get("Os") != "linux"
        or value[0].get("Architecture") != "amd64"
    ):
        raise SourceRejected()
    source: Any = json.loads(
        _probe_source(image, timeout_seconds=timeout_seconds),
        object_pairs_hook=_pairs,
    )
    if not isinstance(source, dict):
        raise SourceRejected()
    source = cast(dict[str, Any], source)
    if (
        set(source) != {"simulator_sha", "provenance", "reason", "runtime"}
        or source["provenance"] != "clean"
        or source["reason"] is not None
    ):
        raise SourceRejected()
    raw_runtime: object = source["runtime"]
    if not isinstance(raw_runtime, dict):
        raise SourceRejected()
    runtime = cast(dict[str, Any], raw_runtime)
    if set(runtime) != {
        "python",
        "httpx",
        "dependency_lock_sha256",
    }:
        raise SourceRejected()
    for raw_record in (source["simulator_sha"], *runtime.values()):
        if not isinstance(raw_record, dict):
            raise SourceRejected()
        record = cast(dict[str, Any], raw_record)
        if (
            set(record) != {"value", "reason"}
            or record["reason"] is not None
            or not isinstance(record["value"], str)
        ):
            raise SourceRejected()
    if (
        SHA.fullmatch(source["simulator_sha"]["value"]) is None
        or DIGEST.fullmatch(runtime["dependency_lock_sha256"]["value"]) is None
        or re.fullmatch(r"3\.13\.[0-9]+", runtime["python"]["value"]) is None
    ):
        raise SourceRejected()
    return cast(dict[str, Any], source)


def _verify_image(
    release: Mapping[str, object], *, timeout_seconds: float = COMMAND_SECONDS
) -> dict[str, object]:
    """Verify the installed immutable image and its bound packaged source."""
    try:
        record = _validate_release(release)
        source = _inspect(record["image_id"], timeout_seconds=timeout_seconds)
        if (
            source["simulator_sha"]["value"] != record["simulator_sha"]
            or source["runtime"]["dependency_lock_sha256"]["value"]
            != record["dependency_lock_sha256"]
        ):
            raise SourceRejected()
        return source
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        raise SourceRejected() from None


def verify_image(release: Mapping[str, object]) -> dict[str, object]:
    """Verify the installed immutable image using a bounded source probe."""
    return _verify_image(release)


async def verify_image_async(
    release: Mapping[str, object], *, timeout_seconds: float = COMMAND_SECONDS
) -> dict[str, object]:
    """Join the owned verifier and named cleanup even when the caller cancels."""
    seconds = _probe_seconds(timeout_seconds)
    cancelled = threading.Event()

    def verify() -> dict[str, object]:
        token = _COMMAND_STATE.set((cancelled, None))
        try:
            return _verify_image(release, timeout_seconds=seconds)
        finally:
            _COMMAND_STATE.reset(token)

    # Keep the executor Future separate from asyncio Tasks: loop shutdown may
    # cancel every Task, but must still let this wrapper join its owned worker.
    worker = asyncio.get_running_loop().run_in_executor(None, verify)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:  # noqa: BLE001 - consume the joined verifier failure
                break
        with suppress(Exception):
            worker.result()
        raise


def load_release(archive: Path, metadata: Path) -> str:
    record = cast(dict[str, Any], read_release(metadata))
    if _hash(archive) != record["archive_sha256"]:
        raise SourceRejected()
    loaded = _run(
        ["docker", "load", "--input", str(archive)], timeout_seconds=TRANSFER_SECONDS
    )
    if "Loaded image ID: " + record["image_id"] not in loaded.splitlines():
        raise SourceRejected()
    verify_image(record)
    return str(record["image_id"])


def _copy_runtime(image: str, runtime: Path) -> None:
    _private(runtime)
    if any(runtime.iterdir()) or IMAGE.fullmatch(image) is None:
        raise SourceRejected()
    mount = io.StringIO()
    csv.writer(mount).writerow(["type=bind", "src=" + str(runtime), "dst=/output"])
    code = (
        "import os, shutil; os.umask(0o077); "
        "shutil.copytree('/app','/output',dirs_exist_ok=True,symlinks=True,"
        "copy_function=shutil.copyfile,"
        "ignore=lambda path,names:['.venv'] if path=='/app' else [])"
    )
    name = "tailtag-sim-copy-" + str(uuid.uuid4())
    try:
        _run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--rm",
                "--init",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--log-driver=none",
                "--ulimit",
                "core=0:0",
                "--mount",
                mount.getvalue().removesuffix("\r\n"),
                "--entrypoint",
                "python",
                image,
                "-c",
                code,
            ],
            timeout_seconds=TRANSFER_SECONDS,
        )
    finally:
        _remove_named(name)


def install_runtime(archive: Path, metadata: Path, root: Path) -> Path:
    if not root.is_absolute() or any(
        parent.is_symlink() for parent in (root, *root.parents)
    ):
        raise SourceRejected()
    _private(root)
    record = cast(dict[str, Any], read_release(metadata))
    releases = root / "releases"
    if releases.exists() or releases.is_symlink():
        _private(releases)
    runtime = releases / record["simulator_sha"]
    if runtime.exists() or runtime.is_symlink():
        _private(runtime)
        if _packaged(runtime) != (
            record["simulator_sha"],
            record["dependency_lock_sha256"],
        ):
            raise SourceRejected()
        if _read(runtime / "release.json") != record:
            raise SourceRejected()
    image = load_release(archive, metadata)
    releases = root / "releases"
    releases.mkdir(mode=0o700, exist_ok=True)
    _private(releases)
    if not runtime.exists():
        runtime.mkdir(mode=0o700)
        _copy_runtime(image, runtime)
        if _packaged(runtime) != (
            record["simulator_sha"],
            record["dependency_lock_sha256"],
        ):
            raise SourceRejected()
        runtime.chmod(0o700, follow_symlinks=False)
        for path in runtime.rglob("*"):
            if path.is_symlink():
                raise SourceRejected()
            path.chmod(0o700 if path.is_dir() else 0o600, follow_symlinks=False)
        _write(runtime / "release.json", record)
    _private(root / "tools")
    uv = root / "tools" / "uv"
    if (
        uv.is_symlink()
        or not uv.is_file()
        or uv.stat().st_uid != os.getuid()
        or uv.stat().st_mode & 0o077
    ):
        raise SourceRejected()
    _run(
        [
            str(uv),
            "sync",
            "--directory",
            str(runtime),
            "--locked",
            "--no-dev",
            "--python",
            "3.13.11",
            "--managed-python",
        ],
        timeout_seconds=TRANSFER_SECONDS,
    )
    if _packaged(runtime) != (
        record["simulator_sha"],
        record["dependency_lock_sha256"],
    ):
        raise SourceRejected()
    return runtime


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify immutable host simulator releases"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "load", "install-runtime"):
        command = commands.add_parser(name)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--metadata", type=Path, required=True)
        if name == "export":
            command.add_argument("--image", required=True)
        if name == "install-runtime":
            command.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            if args.archive.exists() or args.metadata.exists():
                raise SourceRejected()
            source = _inspect(args.image)
            _run(
                ["docker", "save", "--output", str(args.archive), args.image],
                timeout_seconds=TRANSFER_SECONDS,
            )
            args.archive.chmod(0o600)
            _write(
                args.metadata,
                {
                    "schema_version": 1,
                    "simulator_sha": source["simulator_sha"]["value"],
                    "dependency_lock_sha256": source["runtime"][
                        "dependency_lock_sha256"
                    ]["value"],
                    "image_id": args.image,
                    "platform": "linux/amd64",
                    "archive_sha256": _hash(args.archive),
                },
            )
        elif args.command == "install-runtime":
            print(install_runtime(args.archive, args.metadata, args.root))
        else:
            print(load_release(args.archive, args.metadata))
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        SourceRejected,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        print("host_release_rejected")
        return 1


def main(argv: list[str] | None = None) -> int:
    with _cli_signals():
        result = _main(argv)
        if _cancelled() and result == 0:
            print("host_release_rejected")
            return 1
        return result


if __name__ == "__main__":
    raise SystemExit(main())
