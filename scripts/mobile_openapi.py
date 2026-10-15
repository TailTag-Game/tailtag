"""Generate or check the mobile API client package from the OpenAPI snapshot.

Usage: python scripts/mobile_openapi.py generate|check
(or: task mobile-api-generate / task mobile-api-check)

`generate` rewrites `apps/mobile/packages/tailtag_api/` from
`services/api/openapi/schema.yaml` with the pinned tonik tool in
`apps/mobile/tool/openapi/`. `check` regenerates into a temporary directory and
fails, naming the generate command, when the committed package differs.
Generation is byte-deterministic and uses only the pinned Flutter SDK's Dart.
Standard library and `fvm_sdk` only, Python 3.9 or newer.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

import fvm_sdk

PACKAGE_NAME = "tailtag_api"
GENERATE_COMMAND = "task mobile-api-generate"
# The one edit made to tonik's pubspec: join the app's pub workspace, so the
# package shares the app's lockfile and analysis context.
WORKSPACE_MARKER = "\nenvironment:\n"
WORKSPACE_LINE = "\nresolution: workspace\nenvironment:\n"
# Local pub state that is not part of the committed package.
IGNORED_DIRECTORIES = frozenset({".dart_tool", "build"})
MAX_REPORTED_DIFFERENCES = 20


def die(message: str) -> NoReturn:
    """Print a message to stderr and stop with exit status 1."""
    print(message, file=sys.stderr)
    sys.exit(1)


def run(command: list[str], cwd: Path, description: str) -> None:
    """Run a tool, hiding its output unless it fails."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout, file=sys.stderr)
        print(completed.stderr, file=sys.stderr)
        die(f"{description} failed (exit {completed.returncode}).")


def package_files(package: Path) -> dict[str, bytes]:
    """Map each committed file's relative POSIX path to its newline-normalized bytes."""
    return {
        path.relative_to(package).as_posix(): path.read_bytes().replace(b"\r\n", b"\n")
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and not IGNORED_DIRECTORIES.intersection(path.relative_to(package).parts)
    }


def package_differences(expected: Path, actual: Path) -> list[str]:
    """Describe how the package at `actual` differs from `expected`; empty when equal."""
    wanted = package_files(expected)
    found = package_files(actual) if actual.is_dir() else {}
    return [
        *(f"missing    {name}" for name in sorted(wanted.keys() - found.keys())),
        *(f"unexpected {name}" for name in sorted(found.keys() - wanted.keys())),
        *(
            f"changed    {name}"
            for name in sorted(wanted.keys() & found.keys())
            if wanted[name] != found[name]
        ),
    ]


def generate_into(repository_root: Path, destination: Path, fvm: str) -> Path:
    """Generate and format the package under `destination`; return its directory."""
    mobile = repository_root / "apps/mobile"
    tool = mobile / "tool/openapi"
    schema = repository_root / "services/api/openapi/schema.yaml"
    if not schema.is_file():
        die("services/api/openapi/schema.yaml is missing; run: task api-schema")

    run(
        [fvm, "dart", "pub", "get", "--enforce-lockfile"],
        tool,
        "Resolving the pinned tonik tool",
    )
    # tonik reports its content-type fallbacks for the schema endpoint itself.
    run(
        [
            fvm,
            "dart",
            "run",
            "tonik",
            "-s",
            str(schema),
            "-o",
            str(destination),
            "-p",
            PACKAGE_NAME,
            "--backend",
            "http",
            "--log-level",
            "warn",
        ],
        tool,
        "tonik",
    )

    package = destination / PACKAGE_NAME
    pubspec = package / "pubspec.yaml"
    text = pubspec.read_bytes().decode("utf-8").replace("\r\n", "\n")
    if WORKSPACE_MARKER not in text:
        die("tonik's pubspec.yaml no longer has the expected environment section.")
    pubspec.write_bytes(
        text.replace(WORKSPACE_MARKER, WORKSPACE_LINE, 1).encode("utf-8")
    )
    run([fvm, "dart", "format", str(package)], mobile, "dart format")
    return package


def committed_package(repository_root: Path) -> Path:
    """Return the directory of the committed generated package."""
    return repository_root / "apps/mobile/packages" / PACKAGE_NAME


def sync(source: Path, destination: Path) -> None:
    """Make `destination` hold exactly the files of `source`, leaving pub state alone."""
    wanted = package_files(source)
    for name in package_files(destination) if destination.is_dir() else {}:
        if name not in wanted:
            (destination / name).unlink()
    for name in wanted:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)


def main(arguments: list[str]) -> int:
    """Run `generate` or `check`."""
    if len(arguments) != 1 or arguments[0] not in {"generate", "check"}:
        print("usage: python scripts/mobile_openapi.py generate|check", file=sys.stderr)
        return 2
    repository_root = Path(__file__).resolve().parents[1]
    fvm = fvm_sdk.find_fvm()
    if fvm is None:
        die(fvm_sdk.FVM_MISSING)

    with tempfile.TemporaryDirectory() as scratch:
        generated = generate_into(repository_root, Path(scratch), fvm)
        committed = committed_package(repository_root)
        if arguments[0] == "generate":
            sync(generated, committed)
            print(f"Regenerated apps/mobile/packages/{PACKAGE_NAME}/.")
            return 0
        differences = package_differences(generated, committed)
    if differences:
        print("\n".join(differences[:MAX_REPORTED_DIFFERENCES]), file=sys.stderr)
        print(
            f"The committed apps/mobile/packages/{PACKAGE_NAME}/ does not match "
            "services/api/openapi/schema.yaml; regenerate it with: "
            f"{GENERATE_COMMAND}",
            file=sys.stderr,
        )
        return 1
    print("The generated API client matches the OpenAPI snapshot.")
    return 0


if __name__ == "__main__":
    fvm_sdk.configure_output()
    sys.exit(main(sys.argv[1:]))
