"""Verified Git inputs and self-verifying container source metadata (#224)."""

import argparse
import hashlib
import json
import platform
import re
import subprocess
import tempfile
from importlib.machinery import all_suffixes
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

PACKAGE = "tools/simulator/tailtag_simulator"
IMAGES = "services/api/simulation_fixtures/images"
BUILD_FILES = {
    "Makefile",
    "tools/simulator/Dockerfile",
    "tools/simulator/.dockerignore",
    "tools/simulator/pyproject.toml",
    "tools/simulator/uv.lock",
}
# Host launchers execute through the API environment; validate these inputs but
# keep them out of the smoke-only container's runtime payload.
HOST_FILES = {
    "scripts/api_sim_pool_ssh.py",
    "scripts/api_sim_fixture_ssh.py",
    "scripts/api_sim_inspect_ssh.py",
    "scripts/api_staging_reset_ssh.py",
    "scripts/api_staging_preflight.py",
    "services/api/pyproject.toml",
    "services/api/uv.lock",
}
HOST_OPTIONAL_FILES = {
    stem + suffix
    for stem in ("scripts/__init__", "scripts")
    for suffix in all_suffixes()
}
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")


class SourceRejected(Exception):
    """A source identity cannot be established; no untrusted details escape."""

    def __init__(self) -> None:
        super().__init__("source_rejected")


def _ignored(path: Path) -> bool:
    return (
        any(
            part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
            for part in path.parts
        )
        or path.suffix == ".md"
        or path.name == ".DS_Store"
    )


def _relevant(name: str) -> bool:
    path = Path(name)
    return name in BUILD_FILES | HOST_FILES | HOST_OPTIONAL_FILES or (
        name.startswith((PACKAGE + "/", IMAGES + "/")) and not _ignored(path)
    )


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    ).stdout


def _files(root: Path, directory: str) -> set[str]:
    base = root / directory
    if (
        any(
            parent.is_symlink()
            for parent in (base, *base.parents)
            if parent != root and parent.is_relative_to(root)
        )
        or not base.is_dir()
    ):
        raise SourceRejected()
    result: set[str] = set()
    for path in base.rglob("*"):
        relative = path.relative_to(root)
        if _ignored(relative):
            continue
        if path.is_symlink():
            raise SourceRejected()
        if path.is_file():
            result.add(relative.as_posix())
        elif not path.is_dir():
            raise SourceRejected()
    return result


def _host(root: Path) -> tuple[str, dict[str, bytes]]:
    if (
        Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        != root.resolve()
    ):
        raise SourceRejected()
    sha = _git(root, "rev-parse", "HEAD").decode().strip()
    if SHA.fullmatch(sha) is None:
        raise SourceRejected()
    names = {
        name
        for name in _git(root, "ls-tree", "-r", "--name-only", "-z", sha)
        .decode()
        .split("\0")
        if name and _relevant(name)
    }
    required = {
        "Makefile",
        "tools/simulator/Dockerfile",
        "tools/simulator/pyproject.toml",
        "tools/simulator/uv.lock",
    }
    required |= HOST_FILES
    if not required <= names:
        raise SourceRejected()
    actual = _files(root, PACKAGE) | _files(root, IMAGES)
    if actual != {
        name
        for name in names
        if name not in BUILD_FILES | HOST_FILES | HOST_OPTIONAL_FILES
    }:
        raise SourceRejected()
    staged = (
        _git(root, "diff", "--cached", "--name-only", "-z", sha).decode().split("\0")
    )
    unstaged = _git(root, "diff", "--name-only", "-z").decode().split("\0")
    if any(_relevant(name) for name in staged + unstaged):
        raise SourceRejected()
    approved: dict[str, bytes] = {}
    for name in sorted(names):
        path = root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or any(
                parent.is_symlink()
                for parent in path.parents
                if parent != root and parent.is_relative_to(root)
            )
        ):
            raise SourceRejected()
        # Committed symlinks must not be accepted even when their current target is internal.
        mode = _git(root, "ls-tree", sha, "--", name).split(b" ", 1)[0]
        if mode not in {b"100644", b"100755"}:
            raise SourceRejected()
        content = _git(root, "show", f"{sha}:{name}")
        if path.read_bytes() != content:
            raise SourceRejected()
        approved[name] = content
    # Include ignored or dangling namespace initializers and build inputs.
    for name in BUILD_FILES | HOST_FILES | HOST_OPTIONAL_FILES:
        path = root / name
        if (path.exists() or path.is_symlink()) and name not in names:
            raise SourceRejected()
    # Packages and alternate supported loaders can take precedence over verified
    # launcher source. Reject them even when ignored or dangling symlinks.
    for name in HOST_FILES:
        if not name.startswith("scripts/") or not name.endswith(".py"):
            continue
        path = root / name
        package = path.with_suffix("")
        if package.is_dir() or package.is_symlink():
            raise SourceRejected()
        for suffix in all_suffixes():
            sibling = path.with_suffix(suffix)
            if sibling != path and (sibling.exists() or sibling.is_symlink()):
                raise SourceRejected()
    return sha, approved


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise SourceRejected()
        result[key] = value
    return result


def _packaged(root: Path) -> tuple[str, str]:
    metadata_file = root / "source.json"
    if metadata_file.is_symlink():
        raise SourceRejected()
    raw: object = json.loads(metadata_file.read_text(), object_pairs_hook=_pairs)
    if not isinstance(raw, dict):
        raise SourceRejected()
    metadata = cast(dict[str, Any], raw)
    if set(metadata) != {
        "schema_version",
        "simulator_sha",
        "dependency_lock_sha256",
        "manifest",
    }:
        raise SourceRejected()
    if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
        raise SourceRejected()
    sha = metadata["simulator_sha"]
    lock = metadata["dependency_lock_sha256"]
    manifest = metadata["manifest"]
    if (
        not isinstance(sha, str)
        or SHA.fullmatch(sha) is None
        or not isinstance(lock, str)
        or DIGEST.fullmatch(lock) is None
    ):
        raise SourceRejected()
    if not isinstance(manifest, dict) or not manifest:
        raise SourceRejected()
    manifest = cast(dict[str, Any], manifest)
    actual = (
        _files(root, "tailtag_simulator")
        | _files(root, IMAGES)
        | {"pyproject.toml", "uv.lock"}
    )
    if set(manifest) != actual:
        raise SourceRejected()
    for name, digest in manifest.items():
        relative = Path(name)
        path = root / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
        ):
            raise SourceRejected()
        if (
            not isinstance(digest, str)
            or DIGEST.fullmatch(digest) is None
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise SourceRejected()
    if manifest["uv.lock"] != lock:
        raise SourceRejected()
    return sha, lock


def load_source(root: Path | None = None) -> dict[str, object]:
    """Return the closed report source object or raise a detail-free rejection."""
    if root is None:
        package_root = Path(__file__).resolve().parent.parent
        root = next(
            (
                ancestor
                for ancestor in (package_root, *package_root.parents)
                if (ancestor / ".git").exists()
            ),
            package_root,
        )
    try:
        if not (root / ".git").exists() and (root / "source.json").exists():
            sha, lock = _packaged(root)
        else:
            sha, inputs = _host(root)
            lock = hashlib.sha256(inputs["tools/simulator/uv.lock"]).hexdigest()
        return {
            "simulator_sha": {"value": sha, "reason": None},
            "provenance": "clean",
            "reason": None,
            "runtime": {
                "python": {"value": platform.python_version(), "reason": None},
                "httpx": {"value": version("httpx"), "reason": None},
                "dependency_lock_sha256": {"value": lock, "reason": None},
            },
        }
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        SourceRejected,
        PackageNotFoundError,
    ):
        raise SourceRejected() from None


def _build(root: Path, tag: str) -> None:
    sha, inputs = _host(root)
    with tempfile.TemporaryDirectory(prefix="tailtag-simulator-build-") as temporary:
        context = Path(temporary)
        manifest: dict[str, str] = {}
        for name, content in inputs.items():
            if name in {"Makefile"} | HOST_FILES | HOST_OPTIONAL_FILES:
                continue
            destination = name.removeprefix("tools/simulator/")
            path = context / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if destination not in {"Dockerfile", ".dockerignore"}:
                manifest[destination] = hashlib.sha256(content).hexdigest()
        (context / "source.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "simulator_sha": sha,
                    "dependency_lock_sha256": manifest["uv.lock"],
                    "manifest": manifest,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        _packaged(context)
        subprocess.run(
            ["docker", "build", "-t", tag, str(context)],
            check=True,
            capture_output=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a verified simulator image")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        _build(args.root, args.tag)
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        SourceRejected,
        PackageNotFoundError,
    ):
        print("source_build_rejected")
        return 1
    print("source_build_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
