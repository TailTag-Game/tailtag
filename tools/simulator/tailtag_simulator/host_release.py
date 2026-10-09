"""Immutable Docker archive verification and attributed host runtime installation."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
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


def _run(arguments: list[str]) -> str:
    return subprocess.run(arguments, check=True, capture_output=True, text=True).stdout


def _hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SourceRejected()
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _inspect(image: str) -> dict[str, Any]:
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
        _run(
            [
                "docker",
                "run",
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
            ]
        ),
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


def verify_image(release: Mapping[str, object]) -> dict[str, object]:
    """Verify the installed immutable image and its bound packaged source."""
    try:
        record = _validate_release(release)
        source = _inspect(record["image_id"])
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


def load_release(archive: Path, metadata: Path) -> str:
    record = cast(dict[str, Any], read_release(metadata))
    if _hash(archive) != record["archive_sha256"]:
        raise SourceRejected()
    loaded = _run(["docker", "load", "--input", str(archive)])
    if "Loaded image ID: " + record["image_id"] not in loaded.splitlines():
        raise SourceRejected()
    verify_image(record)
    return str(record["image_id"])


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
        container: str | None = None
        try:
            container = _run(["docker", "create", image]).strip()
            if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container) is None:
                raise SourceRejected()
            _run(["docker", "cp", container + ":/app/.", str(runtime)])
        finally:
            if container is not None:
                _run(["docker", "rm", container])
        if _packaged(runtime) != (
            record["simulator_sha"],
            record["dependency_lock_sha256"],
        ):
            raise SourceRejected()
        # Image venv is a different platform/runtime installation. It is not
        # part of source.json; discard only this newly copied disposable venv.
        if runtime.is_symlink() or runtime.stat().st_uid != os.getuid():
            raise SourceRejected()
        runtime.chmod(0o700, follow_symlinks=False)
        copied_venv = runtime / ".venv"
        if copied_venv.is_symlink():
            copied_venv.unlink()
        elif copied_venv.exists():
            # Docker cp retains the image's chmod -R a-w. Restore only owned
            # real directories needed to unlink this freshly copied venv.
            for directory, _, _ in os.walk(copied_venv, followlinks=False):
                path = Path(directory)
                if path.is_symlink() or path.stat().st_uid != os.getuid():
                    raise SourceRejected()
                path.chmod(0o700, follow_symlinks=False)
            shutil.rmtree(copied_venv)
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
        ]
    )
    if _packaged(runtime) != (
        record["simulator_sha"],
        record["dependency_lock_sha256"],
    ):
        raise SourceRejected()
    return runtime


def main(argv: list[str] | None = None) -> int:
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
            _run(["docker", "save", "--output", str(args.archive), args.image])
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


if __name__ == "__main__":
    raise SystemExit(main())
