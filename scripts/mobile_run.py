"""Run the TailTag mobile app on one explicitly chosen Android or iOS target.

Usage: DEVICE=<id> python scripts/mobile_run.py   (or: task mobile-run DEVICE=<id>)

It never boots or chooses a device. It validates the mobile configuration, then
forwards the Local API port to an Android target before it launches
`fvm flutter run` and exits with Flutter's exit code. Standard library and
`fvm_sdk` only, Python 3.9 or newer.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, cast
from urllib.parse import urlsplit

import fvm_sdk

CONFIG_FILE = "config/development.json"
CONFIG_TEMPLATE = (
    "cp apps/mobile/config/development.example.json apps/mobile/config/development.json"
)
SAFE_DEVICE_ID = re.compile(r"[A-Za-z0-9._:-]+")


def die(message: str) -> NoReturn:
    """Print a message to stderr and stop with exit status 1."""
    print(message, file=sys.stderr)
    sys.exit(1)


def capture(
    command: list[str], mobile_directory: Path
) -> subprocess.CompletedProcess[str]:
    """Run a command in the mobile project, capturing UTF-8 stdout and stderr."""
    return subprocess.run(
        command,
        cwd=mobile_directory,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def device_platform(fvm: str, mobile_directory: Path, device: str) -> str | None:
    """Return the target platform of a connected device id, or None if it is unknown."""
    if not SAFE_DEVICE_ID.fullmatch(device):
        return None
    devices = fvm_sdk.parse_json(
        capture([fvm, "flutter", "devices", "--machine"], mobile_directory).stdout, "["
    )
    if not isinstance(devices, list):
        return None
    for entry in cast("list[object]", devices):
        if not isinstance(entry, dict):
            continue
        fields = cast("dict[str, object]", entry)
        target_platform = fields.get("targetPlatform")
        if fields.get("id") == device and isinstance(target_platform, str):
            return target_platform
    return None


def stop_without_device(fvm: str, mobile_directory: Path, device: str) -> NoReturn:
    """Explain how to pick a connected device, then stop."""
    if device:
        print("DEVICE is not a connected device id.", file=sys.stderr, flush=True)
    else:
        print(
            "DEVICE is required: choose one connected target.",
            file=sys.stderr,
            flush=True,
        )
    subprocess.run([fvm, "flutter", "devices"], cwd=mobile_directory, check=False)
    print(f"\nStart an Android emulator: {fvm_sdk.ANDROID_START_HINT}")
    print(f"Start an iOS simulator (macOS): {fvm_sdk.IOS_START_HINT}")
    print("Then run: task mobile-run DEVICE=<id>")
    sys.exit(1)


def check_configuration(fvm: str, mobile_directory: Path) -> str:
    """Return the validated API origin, or stop with the configuration problem."""
    # The tool prints the validated origin on stdout and problems on stderr; keep
    # them apart so incidental tool output never becomes part of the origin.
    checked = capture(
        [fvm, "dart", "run", "tool/check_config.dart", CONFIG_FILE], mobile_directory
    )

    if checked.returncode == 2:
        die(
            "Mobile configuration is missing: apps/mobile/config/development.json\n"
            f"Copy the template: {CONFIG_TEMPLATE}\n"
            "Then set CLERK_PUBLISHABLE_KEY to the Clerk Development publishable key."
        )
    if checked.returncode != 0:
        die(
            "Mobile configuration is invalid (apps/mobile/config/development.json):\n"
            f"{checked.stderr.rstrip()}\n"
            "Fix the listed values, or start again from the template: "
            f"{CONFIG_TEMPLATE}"
        )

    lines = checked.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def forward_local_api(origin: str, device: str) -> None:
    """Forward the Local API port from an Android target to this host's loopback."""
    adb = shutil.which("adb")
    if adb is None:
        die(
            "adb is not on PATH; install Android platform-tools (or set ANDROID_HOME and "
            "add platform-tools to PATH) so Local API access can be forwarded."
        )

    port = f"tcp:{urlsplit(origin).port or 80}"
    reversed_port = subprocess.run(
        [adb, "-s", device, "reverse", port, port], check=False
    )
    if reversed_port.returncode != 0:
        die(
            f"adb reverse failed for {device}; check that the device is online (adb devices)."
        )


def main() -> int:
    """Validate the target and configuration, then run the app."""
    fvm_sdk.configure_output()
    mobile_directory = Path(__file__).resolve().parent.parent / "apps/mobile"
    device = os.environ.get("DEVICE", "")

    if os.environ.get("TAILTAG_DEVCONTAINER") == "1":
        die("Mobile commands run on the host, not in the TailTag devcontainer.")

    fvm = fvm_sdk.find_fvm()
    if fvm is None:
        die(fvm_sdk.FVM_MISSING)

    platform = device_platform(fvm, mobile_directory, device)
    if platform is None:
        stop_without_device(fvm, mobile_directory, device)

    if not (platform.startswith("android") or platform == "ios"):
        die(
            f"TailTag supports Android and iOS targets; {device} is a {platform} target."
        )
    if platform == "ios" and fvm_sdk.host_os() != "Darwin":
        die(
            "iOS targets need macOS with Xcode; choose an Android device or emulator on this host."
        )

    origin = check_configuration(fvm, mobile_directory)
    if origin.startswith("http://") and platform.startswith("android"):
        forward_local_api(origin, device)

    process = subprocess.Popen(
        [
            fvm,
            "flutter",
            "run",
            "-d",
            device,
            f"--dart-define-from-file={CONFIG_FILE}",
        ],
        cwd=mobile_directory,
    )
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # Flutter receives the same Ctrl+C; let it exit on its own and
            # return its status, as the former exec did.
            continue


if __name__ == "__main__":
    sys.exit(main())
