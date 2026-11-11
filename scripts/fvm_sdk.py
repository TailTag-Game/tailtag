"""Shared FVM and pinned Flutter SDK helpers for the mobile contributor tooling.

doctor.py and mobile_run.py import this module. It is also the guard behind the
`mobile-setup` and `mobile-run` tasks:

    python scripts/fvm_sdk.py <repository_root>

The guard exits 0 silently when `apps/mobile/.fvmrc` pins an SDK that FVM has
installed, so FVM never downloads a missing SDK on its own. Otherwise it prints
one message to stderr and exits 1. Standard library only, Python 3.9 or newer.
"""

from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

FVM_MISSING = (
    "FVM is not installed; install it: "
    "https://fvm.app/documentation/getting-started/installation"
)
PIN_UNREADABLE = "Could not read the pinned Flutter version from apps/mobile/.fvmrc."
# iOS boots with `xcrun simctl`, which works with Simulator.app (Xcode 26) and
# Device Hub, its Xcode 27 replacement.
ANDROID_START_HINT = "fvm flutter emulators --launch <emulator-id>"
IOS_START_HINT = (
    'xcrun simctl boot "<device>", then open Device Hub (Xcode 27) '
    "or Simulator (Xcode 26)"
)
PINNED_FLUTTER = re.compile(r'"flutter"\s*:\s*"([^"]+)"')
# A hung tool (a stuck Docker daemon, a stalled network) fails its check instead
# of blocking doctor; 124 is the status `timeout` reports.
COMMAND_TIMEOUT_SECONDS = 120.0
TIMED_OUT = 124


def configure_output() -> None:
    """Make stdout and stderr UTF-8 so tool output never crashes a legacy codepage.

    A Windows pipe defaults to the ANSI codepage (cp1252), which cannot encode
    characters that tools such as Flutter print. Interactive consoles are not
    affected, because Python writes to them as Unicode.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def host_os() -> str:
    """Return Darwin, Linux, or Windows; TAILTAG_DOCTOR_HOST_OS overrides it for tests."""
    return os.environ.get("TAILTAG_DOCTOR_HOST_OS") or platform.system()


def command_timeout() -> float:
    """Return how long one tool may run; TAILTAG_DOCTOR_COMMAND_TIMEOUT overrides it for tests."""
    configured = os.environ.get("TAILTAG_DOCTOR_COMMAND_TIMEOUT")
    return float(configured) if configured else COMMAND_TIMEOUT_SECONDS


def run_command(
    command: Sequence[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    merge_stderr: bool = False,
) -> tuple[int, str, str]:
    """Run a tool and return its status, stdout, and stderr decoded as UTF-8.

    The status is 127 when the tool cannot start and TIMED_OUT when it runs past
    `command_timeout()`. A timed-out tool is killed without reading the rest of its
    output, because a process it started may still hold that output open.
    """
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        return 127, "", str(error)
    timeout = command_timeout()
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return TIMED_OUT, "", f"{command[0]} timed out after {timeout:g} seconds"
    return process.returncode, stdout or "", stderr or ""


def find_fvm() -> str | None:
    """Return the FVM executable on PATH, including Windows `.bat` and `.exe` shims."""
    return shutil.which("fvm")


def parse_json(text: str, opener: str) -> object | None:
    """Parse the first JSON value in tool output that begins at `opener`."""
    start = text.find(opener)
    if start < 0:
        return None
    try:
        value: object
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except ValueError:
        return None
    return value


def pinned_flutter_version(repository_root: Path) -> str | None:
    """Return the Flutter version pinned in apps/mobile/.fvmrc, if any."""
    try:
        text = (repository_root / "apps/mobile/.fvmrc").read_text(encoding="utf-8")
    except OSError:
        return None
    match = PINNED_FLUTTER.search(text)
    return match.group(1) if match else None


def sdk_installed(fvm: str, version: str) -> bool:
    """Return whether `fvm api list --compress` lists the version under `versions`.

    Entries under `projects` and versions that merely share a prefix do not count.
    """
    _, listing, _ = run_command([fvm, "api", "list", "--compress"])
    document = parse_json(listing, "{")
    if not isinstance(document, dict):
        return False
    versions = cast("dict[str, object]", document).get("versions")
    if not isinstance(versions, list):
        return False
    return any(
        isinstance(entry, dict)
        and cast("dict[str, object]", entry).get("name") == version
        for entry in cast("list[object]", versions)
    )


def sdk_not_installed_message(version: str) -> str:
    """Return the fix-it message for a pinned SDK that FVM has not installed."""
    return (
        f"Flutter {version} (pinned in apps/mobile/.fvmrc) is not installed; "
        "run: (cd apps/mobile && fvm install)"
    )


def main(arguments: list[str]) -> int:
    """Check that FVM and the pinned Flutter SDK are installed."""
    if len(arguments) != 1:
        print("usage: python scripts/fvm_sdk.py <repository_root>", file=sys.stderr)
        return 2

    fvm = find_fvm()
    if fvm is None:
        print(FVM_MISSING, file=sys.stderr)
        return 1

    version = pinned_flutter_version(Path(arguments[0]))
    if version is None:
        print(PIN_UNREADABLE, file=sys.stderr)
        return 1

    if not sdk_installed(fvm, version):
        print(sdk_not_installed_message(version), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
