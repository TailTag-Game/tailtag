"""Check a contributor's TailTag environment: `task doctor` and `task mobile-doctor`.

Modes: host (default), the TailTag devcontainer (TAILTAG_DEVCONTAINER=1), and
`--mobile` for the Flutter toolchain on the host. Run it from the repository
root. Exit status: 0 when every required check passes, 1 when one fails, 2 for
bad arguments. Standard library and `fvm_sdk` only, Python 3.9 or newer.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from http.client import HTTPException
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from urllib.request import urlopen

import fvm_sdk

REQUIRED_FILES = (
    "services/api/Dockerfile",
    "services/api/compose.yaml",
    "services/api/pyproject.toml",
    "services/api/uv.lock",
    "services/api/.env.example",
    ".devcontainer/devcontainer.json",
    ".devcontainer/compose.devcontainer.yaml",
    "Taskfile.yml",
    "scripts/doctor.sh",
    "scripts/doctor.py",
)
MOBILE_DIRECTORY = "apps/mobile"
MOBILE_CONFIG = "apps/mobile/config/development.json"
CONFIG_TEMPLATE_HINT = (
    "cp apps/mobile/config/development.example.json apps/mobile/config/development.json"
)
FOOTER = "Mobile checks: run task mobile-doctor on the host."
DATABASE_PROBE = """
from django import setup
from django.db import connection

setup()
connection.ensure_connection()
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
"""
# Flutter prints a check mark on most hosts and a square root sign on Windows.
FLUTTER_OK_MARKS = ("✓", "√")
ANDROID_HINT = (
    "set ANDROID_HOME or run: fvm flutter config --android-sdk <path>, "
    "then see: fvm flutter doctor -v"
)
IOS_HINT = (
    "install Xcode and run: sudo xcodebuild -runFirstLaunch, "
    "then see: fvm flutter doctor -v"
)


class Result:
    """The outcome of one external command; status 127 when it could not start."""

    def __init__(self, status: int, stdout: str = "", stderr: str = "") -> None:
        self.status = status
        self.stdout = stdout
        self.stderr = stderr


def run(
    command: Sequence[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    merge_stderr: bool = False,
) -> Result:
    """Run a command, decoding its output as UTF-8, and never raise for a failure."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        return Result(127, stderr=str(error))
    return Result(completed.returncode, completed.stdout or "", completed.stderr or "")


class Report:
    """Prints PASS, WARN, and FAIL lines and counts the failures."""

    def __init__(self) -> None:
        self.failures = 0

    def passed(self, message: str) -> None:
        print(f"PASS  {message}")

    def warn(self, message: str) -> None:
        print(f"WARN  {message}")

    def fail(self, message: str) -> None:
        print(f"FAIL  {message}")
        self.failures += 1


def check_command(report: Report, name: str, display_name: str) -> str | None:
    """Report whether a tool is on PATH and return its resolved path."""
    path = shutil.which(name)
    if path is None:
        report.fail(f"{display_name} is not installed")
        return None
    report.passed(f"{display_name} is installed")
    return path


def check_required_path(report: Report, path: str, expected_type: str) -> None:
    """Report whether a foundation artifact exists with the expected type."""
    target = Path(path)
    if (expected_type == "directory" and target.is_dir()) or (
        expected_type == "regular file" and target.is_file()
    ):
        report.passed(f"Required foundation artifact exists: {path}")
    elif target.exists():
        report.fail(f"Required foundation artifact is not a {expected_type}: {path}")
    else:
        report.fail(f"Required foundation artifact is missing: {path}")


def sanitized_remote_url(url: str) -> str:
    """Drop credentials from an HTTP(S) remote URL."""
    return re.sub(r"(https?://)[^/@]*@", r"\1", url)


def is_repository_root(toplevel: str) -> bool:
    """Return whether Git's top-level directory is the current directory."""
    try:
        return os.path.samefile(toplevel, os.getcwd())
    except OSError:
        return False


def check_repository(report: Report) -> None:
    git = check_command(report, "git", "Git")

    toplevel = ""
    if git is not None:
        revision = run([git, "rev-parse", "--show-toplevel"])
        toplevel = revision.stdout.strip() if revision.status == 0 else ""
    if toplevel and is_repository_root(toplevel):
        report.passed("Current directory is the TailTag repository root")
    else:
        report.fail("Run this script from the root of the cloned TailTag repository")

    if git is None:
        return

    remote_url = run([git, "remote", "get-url", "origin"]).stdout.strip()
    if "TailTag-Game/tailtag" in remote_url:
        report.passed("Origin points to TailTag-Game/tailtag")
    elif remote_url:
        report.warn(
            "Origin points to an unexpected repository: "
            f"{sanitized_remote_url(remote_url)}"
        )
    else:
        report.fail("No origin remote is configured")

    current_branch = run([git, "branch", "--show-current"]).stdout.strip()
    if current_branch == "main":
        report.warn("You are on main; create a feature branch before making changes")
    elif current_branch:
        report.passed(f"Current branch is {current_branch}")

    if (
        run([git, "diff", "--quiet"]).status == 0
        and run([git, "diff", "--cached", "--quiet"]).status == 0
    ):
        report.passed("Working tree has no uncommitted changes")
    else:
        report.warn("Working tree contains uncommitted changes")


def check_github_cli(report: Report) -> None:
    gh = shutil.which("gh")
    if gh is None:
        report.warn(
            "GitHub CLI is not installed; it is recommended but not currently required"
        )
        return
    report.passed("GitHub CLI is installed")
    if run([gh, "auth", "status"]).status == 0:
        report.passed("GitHub CLI is authenticated")
    else:
        report.warn("GitHub CLI is installed but not authenticated; run: gh auth login")


def check_foundation_structure(report: Report) -> None:
    check_required_path(report, "services/api", "directory")
    for path in REQUIRED_FILES:
        check_required_path(report, path, "regular file")


def check_host_prerequisites(report: Report) -> None:
    docker = shutil.which("docker")
    if docker is None:
        report.fail("Docker is not installed; install Docker with the Compose plugin")
    else:
        report.passed("Docker is installed")
        if run([docker, "info"]).status == 0:
            report.passed("Docker daemon is reachable")
        else:
            report.fail("Docker daemon is unavailable; start Docker and try again")
        if run([docker, "compose", "version"]).status == 0:
            report.passed("Docker Compose is available")
        else:
            report.fail(
                "Docker Compose is unavailable; install Docker with the Compose plugin"
            )

    if shutil.which("devcontainer") is not None:
        report.passed("Dev Container CLI is available")
    else:
        report.warn(
            "No Dev Container CLI was detected; use a devcontainer-capable editor "
            "or install a compatible Dev Container CLI"
        )


def expected_python_version() -> str:
    """Return major.minor from requires-python in services/api/pyproject.toml."""
    try:
        text = Path("services/api/pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(
        r'^\s*requires-python\s*=\s*"[>=\s]*([0-9]+\.[0-9]+)', text, re.MULTILINE
    )
    return match.group(1) if match else ""


def check_devcontainer_environment(report: Report) -> None:
    python = shutil.which("python")
    if python is None:
        report.fail("Python is not installed in the TailTag devcontainer")
    else:
        expected = expected_python_version()
        detected = run(
            [
                python,
                "-c",
                'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")',
            ]
        ).stdout.strip()
        if not expected:
            report.fail(
                "Could not determine the required Python version from "
                "services/api/pyproject.toml"
            )
        elif detected == expected:
            report.passed(f"Python {detected} matches the required version {expected}")
        else:
            report.fail(
                f"Python {detected or 'unknown'} does not match the required "
                f"version {expected}"
            )

    uv = shutil.which("uv")
    if uv is None:
        report.fail("uv is not installed in the TailTag devcontainer")
    else:
        report.passed("uv is available")
        backend = [uv, "--directory", "services/api", "run", "--locked", "--no-sync"]

        if run([*backend, "python", "-c", "import django; import psycopg"]).status == 0:
            report.passed("Locked backend dependencies are usable")
        else:
            report.fail(
                "Locked backend dependencies are unusable; "
                "run the established backend setup flow"
            )

        # The URL carries credentials: it goes only to the probe's environment.
        compose_url = run([*backend, "python", "-m", "config.compose_database_url"])
        probe = Result(1)
        if compose_url.status == 0:
            probe = run(
                [*backend, "python", "-c", DATABASE_PROBE],
                env={
                    **os.environ,
                    "DJANGO_SETTINGS_MODULE": "config.settings.local",
                    "DATABASE_URL": compose_url.stdout.strip(),
                },
            )
        if probe.status == 0:
            report.passed("PostgreSQL is reachable from the backend environment")
        else:
            report.fail(
                "PostgreSQL is not reachable from the backend environment; "
                "verify the local database service is running and healthy"
            )

    task = shutil.which("task")
    if task is not None and run([task, "--list-all"]).status == 0:
        report.passed("Canonical backend task commands are available")
    else:
        report.fail(
            "Canonical backend task commands are unavailable; "
            "verify go-task is installed and the root Taskfile.yml parses"
        )


def flutter_doctor_state(doctor_output: str, section: str) -> str:
    """Return ok, warn, or bad for the named `fvm flutter doctor` section."""
    for line in doctor_output.splitlines():
        match = re.match(rf"\[(.)\] {re.escape(section)}", line)
        if match is None:
            continue
        if match.group(1) in FLUTTER_OK_MARKS:
            return "ok"
        return "warn" if match.group(1) == "!" else "bad"
    return "bad"


def check_mobile_toolchains(report: Report, fvm: str) -> None:
    doctor_output = run(
        [fvm, "flutter", "doctor"], cwd=MOBILE_DIRECTORY, merge_stderr=True
    ).stdout
    android_state = flutter_doctor_state(doctor_output, "Android toolchain")
    # Xcode only exists on macOS, so iOS is not applicable anywhere else.
    ios_state = (
        flutter_doctor_state(doctor_output, "Xcode")
        if fvm_sdk.host_os() == "Darwin"
        else ""
    )

    if android_state == "bad" and ios_state in ("", "bad"):
        if not ios_state:
            report.fail(
                f"The Android toolchain is not usable ({ANDROID_HINT}); "
                "iOS is not applicable on this host"
            )
        else:
            report.fail(
                "Neither the Android toolchain nor Xcode is usable; "
                f"Android: {ANDROID_HINT}; iOS: {IOS_HINT}"
            )
        return

    if android_state == "ok":
        report.passed("Android toolchain is usable")
    elif android_state == "warn":
        report.warn(
            "Android toolchain is usable with warnings; see: fvm flutter doctor -v"
        )
    else:
        report.warn(
            f"Android toolchain is not usable (optional while iOS works): {ANDROID_HINT}"
        )

    if not ios_state:
        report.passed("iOS is not applicable on this host (Xcode requires macOS)")
    elif ios_state == "ok":
        report.passed("Xcode (iOS) toolchain is usable")
    elif ios_state == "warn":
        report.warn(
            "Xcode (iOS) toolchain is usable with warnings; see: fvm flutter doctor -v"
        )
    else:
        report.warn(
            f"Xcode (iOS) toolchain is not usable (optional while Android works): {IOS_HINT}"
        )


def check_mobile_devices(report: Report, fvm: str) -> None:
    devices = fvm_sdk.parse_json(
        run([fvm, "flutter", "devices", "--machine"], cwd=MOBILE_DIRECTORY).stdout, "["
    )
    platforms: list[object] = []
    if isinstance(devices, list):
        for entry in cast("list[object]", devices):
            if isinstance(entry, dict):
                platforms.append(cast("dict[str, object]", entry).get("targetPlatform"))

    if any(
        isinstance(target, str) and (target.startswith("android") or target == "ios")
        for target in platforms
    ):
        report.passed("An Android or iOS device or emulator is available")
    else:
        report.warn(
            "No Android or iOS device or emulator is available; "
            "start one with: fvm flutter emulators --launch <emulator-id>"
        )


def api_answers(origin: str) -> bool:
    """Return whether GET <origin>/health/live succeeds within five seconds."""
    if urlsplit(origin).scheme not in ("http", "https"):
        return False
    try:
        with urlopen(f"{origin}/health/live", timeout=5):
            return True
    except (OSError, ValueError, HTTPException):
        return False


def check_mobile_configuration(report: Report, fvm: str) -> None:
    missing = f"Mobile configuration is missing; run: {CONFIG_TEMPLATE_HINT}"
    if not Path(MOBILE_CONFIG).is_file():
        report.warn(missing)
        return

    # The tool prints the validated origin on stdout and problems on stderr; keep
    # them apart so incidental tool output never becomes the probed origin.
    checked = run(
        [fvm, "dart", "run", "tool/check_config.dart", "config/development.json"],
        cwd=MOBILE_DIRECTORY,
    )
    if checked.status == 2:
        report.warn(missing)
        return
    if checked.status != 0:
        report.fail("Mobile configuration is invalid")
        for problem in checked.stderr.splitlines():
            print(f"      {problem}")
        return

    report.passed("Mobile configuration is valid")
    # The tool prints the validated origin as its final line.
    lines = checked.stdout.strip().splitlines()
    origin = lines[-1] if lines else ""
    reachability = "host reachability does not prove device reachability"

    if api_answers(origin):
        report.passed(
            f"API at {origin} answered /health/live from this host ({reachability})"
        )
    else:
        report.warn(
            f"API at {origin} did not answer /health/live from this host; "
            f"start it or check the URL ({reachability})"
        )


def check_mobile_environment(report: Report) -> None:
    if os.environ.get("TAILTAG_DEVCONTAINER") == "1":
        report.fail("Mobile checks run on the host, not in the TailTag devcontainer")
        return

    fvm = fvm_sdk.find_fvm()
    if fvm is None:
        report.fail(
            "FVM is not installed; install it: "
            "https://fvm.app/documentation/getting-started/installation"
        )
        report.warn(
            "Flutter SDK, toolchain, device, and configuration checks skipped "
            "until FVM is installed"
        )
        return

    report.passed("FVM is installed")
    version = fvm_sdk.pinned_flutter_version(Path.cwd())
    if version is None:
        report.fail(
            "Could not determine the pinned Flutter version from apps/mobile/.fvmrc"
        )
        report.warn("Flutter SDK, toolchain, device, and configuration checks skipped")
        return

    if not fvm_sdk.sdk_installed(fvm, version):
        report.fail(fvm_sdk.sdk_not_installed_message(version))
        report.warn(
            "Toolchain, device, and configuration checks skipped "
            "until the pinned Flutter SDK is installed"
        )
        return
    report.passed(f"Flutter {version} (pinned in apps/mobile/.fvmrc) is installed")

    check_mobile_toolchains(report, fvm)
    check_mobile_devices(report, fvm)
    check_mobile_configuration(report, fvm)


def main(arguments: list[str]) -> int:
    """Run the checks for the selected mode and return the exit status."""
    fvm_sdk.configure_output()
    mobile_mode = False
    for argument in arguments:
        if argument != "--mobile":
            print("usage: task doctor [--mobile]", file=sys.stderr)
            return 2
        mobile_mode = True

    report = Report()
    print("TailTag contributor environment check\n")
    print("Repository")
    check_repository(report)
    check_github_cli(report)
    check_foundation_structure(report)

    if mobile_mode:
        print("\nMobile environment (host)")
        check_mobile_environment(report)
    elif os.environ.get("TAILTAG_DEVCONTAINER") == "1":
        print("\nBackend environment (TailTag devcontainer)")
        check_devcontainer_environment(report)
        print(FOOTER)
    else:
        print("\nHost prerequisites")
        check_host_prerequisites(report)
        print(FOOTER)

    print()
    if report.failures:
        print(f"{report.failures} required check(s) failed.")
        return 1
    print("Required checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
