"""Fake external tools for subprocess tests of the root contributor scripts.

Each fake is a small Python program plus a launcher that works on the current
OS: an executable `sh` script on POSIX and a `.cmd` shim on native Windows
(`shutil.which` resolves `git` to `git.cmd` through PATHEXT). Behavior comes
from `config.json` beside the tools, and every invocation is appended to
`calls.jsonl`, so tests assert on real subprocess behavior without mocking.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

IS_WINDOWS = sys.platform == "win32"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"

DEFAULT_DEVICES: list[dict[str, object]] = [
    {
        "name": "Pixel 8",
        "id": "emulator-5554",
        "isSupported": True,
        "targetPlatform": "android-arm64",
        "emulator": True,
    },
    {
        "name": "iPhone 17",
        "id": "ABCD-1234",
        "isSupported": True,
        "targetPlatform": "ios",
        "emulator": False,
    },
    {
        "name": "macOS",
        "id": "macos",
        "isSupported": True,
        "targetPlatform": "darwin",
        "emulator": False,
    },
]
DEFAULT_FLUTTER_DOCTOR = """Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2 25G83 darwin-arm64, locale en-US)
[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)
[✓] Xcode - develop for iOS and macOS (Xcode 27.0)
[✓] Chrome - develop for the web
[✓] Connected device (3 available)

• No issues found!"""
DEFAULT_DEVICES_TEXT = (
    "Found 3 connected devices:\n"
    "  Pixel 8 (mobile) • emulator-5554 • android-arm64 • Android 15 (emulator)\n"
    "  iPhone 17 (mobile) • ABCD-1234 • ios • iOS 27.0\n"
    "  macOS (desktop) • macos • darwin • macOS 26.6.2\n"
)


def fvm_list(
    versions: list[str],
    projects: list[str] | None = None,
    *,
    projects_first: bool = False,
) -> str:
    """Return `fvm api list --compress` output: compact JSON with `versions[].name`."""
    version_entries = [
        {"name": name, "type": "release", "isSetup": True} for name in versions
    ]
    project_entries = [
        {"name": name, "pinnedVersion": name} for name in (projects or [])
    ]
    document: dict[str, object] = {"size": "1 GB"}
    if projects_first:
        document |= {"projects": project_entries, "versions": version_entries}
    else:
        document |= {"versions": version_entries, "projects": project_entries}
    document["unreferencedVersions"] = []
    return json.dumps(document, separators=(",", ":"))


DEFAULTS: dict[str, object] = {
    "git_toplevel": None,
    "remote": "git@github.com:TailTag-Game/tailtag.git",
    "branch": "chore/test",
    "dirty": False,
    "docker_info_status": 0,
    "docker_info_seconds": 0,
    "docker_compose_status": 0,
    "task_list_status": 0,
    "gh_auth_status": 1,
    "python_version": "3.13",
    "compose_url_status": 0,
    "dependency_status": 0,
    "database_status": 0,
    "uv_status": 0,
    "python3_status": 0,
    "adb_status": 0,
    "fvm_list": fvm_list(["3.47.1", "3.47.2"]),
    "flutter_doctor": DEFAULT_FLUTTER_DOCTOR,
    "devices": DEFAULT_DEVICES,
    "devices_text": DEFAULT_DEVICES_TEXT,
    "check_stdout": "http://127.0.0.1:8000\n",
    "check_stderr": "",
    "check_status": 0,
    "run_status": 0,
}

PRELUDE = """
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as _handle:
    CONFIG = json.load(_handle)


def out(text):
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def err(text):
    sys.stderr.buffer.write(text.encode("utf-8"))
    sys.stderr.buffer.flush()


def record(tool):
    entry = {"tool": tool, "args": sys.argv[1:], "cwd": os.getcwd()}
    with open(os.path.join(HERE, "calls.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\\n")

"""

BODIES: dict[str, str] = {
    "git": """
args = sys.argv[1:]
if args[:2] == ["rev-parse", "--show-toplevel"]:
    out((CONFIG["git_toplevel"] or os.getcwd().replace(os.sep, "/")) + "\\n")
elif args[:3] == ["remote", "get-url", "origin"]:
    if CONFIG["remote"] is None:
        err("error: No such remote 'origin'\\n")
        sys.exit(2)
    out(CONFIG["remote"] + "\\n")
elif args[:2] == ["branch", "--show-current"]:
    out(CONFIG["branch"] + "\\n")
elif args[:1] == ["diff"]:
    sys.exit(1 if CONFIG["dirty"] else 0)
elif args[:1] == ["status"] and CONFIG["dirty"]:
    out(" M file\\n")
""",
    "docker": """
args = sys.argv[1:]
if args[:1] == ["info"]:
    time.sleep(CONFIG["docker_info_seconds"])
    sys.exit(CONFIG["docker_info_status"])
if args[:2] == ["compose", "version"]:
    sys.exit(CONFIG["docker_compose_status"])
""",
    "task": """
# Only a parsing command proves the Taskfile loads; --version does not.
if sys.argv[1:] != ["--list-all"]:
    sys.exit(2)
sys.exit(CONFIG["task_list_status"])
""",
    "gh": """
if sys.argv[1:3] == ["auth", "status"]:
    sys.exit(CONFIG["gh_auth_status"])
""",
    "devcontainer": "",
    "python": """
args = sys.argv[1:]
if args[:1] == ["-c"] and "sys.version_info" in args[1]:
    out(CONFIG["python_version"] + "\\n")
elif args[:1] == ["--version"]:
    out("Python " + CONFIG["python_version"] + ".0\\n")
""",
    "python3": """
sys.exit(CONFIG["python3_status"])
""",
    "uv": """
args = sys.argv[1:]
joined = " ".join(args)
if "config.compose_database_url" in joined:
    out("postgresql://test:password@db:5432/test\\n")
    sys.exit(CONFIG["compose_url_status"])
if "import django; import psycopg" in joined:
    sys.exit(CONFIG["dependency_status"])
if "-c" in args:
    # The database probe: it only works with the settings and URL from the previous step.
    settings_ok = os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.local"
    url_ok = os.environ.get("DATABASE_URL") == "postgresql://test:password@db:5432/test"
    sys.exit(CONFIG["database_status"] if settings_ok and url_ok else 1)
sys.exit(CONFIG["uv_status"])
""",
    "adb": """
sys.exit(CONFIG["adb_status"])
""",
    "fvm": """
args = sys.argv[1:]


def in_project():
    parts = os.path.normpath(os.getcwd()).replace(os.sep, "/").split("/")
    if parts[-2:] != ["apps", "mobile"]:
        err("FAKE_FVM: expected to run from apps/mobile, ran from " + os.getcwd() + "\\n")
        sys.exit(97)


if args[:3] == ["api", "list", "--compress"]:
    out(CONFIG["fvm_list"] + "\\n")
elif args[:2] == ["flutter", "doctor"]:
    in_project()
    out(CONFIG["flutter_doctor"] + "\\n")
elif args[:3] == ["flutter", "devices", "--machine"]:
    in_project()
    out(json.dumps(CONFIG["devices"], indent=2) + "\\n")
elif args[:2] == ["flutter", "devices"]:
    in_project()
    out(CONFIG["devices_text"])
elif args[:3] == ["dart", "run", "tool/check_config.dart"]:
    in_project()
    if not os.path.isfile(os.path.join(os.getcwd(), args[3])):
        err("missing: " + args[3] + "\\n")
        sys.exit(2)
    out(CONFIG["check_stdout"])
    if CONFIG["check_stderr"]:
        err(CONFIG["check_stderr"] + "\\n")
    sys.exit(CONFIG["check_status"])
elif args[:2] == ["flutter", "run"]:
    in_project()
    sys.exit(CONFIG["run_status"])
else:
    # Anything else (for example `api context`, which dumps the environment) is a bug.
    record("fvm-unexpected")
    out("LEAKED_ENV_CANARY=1\\n")
    sys.exit(99)
""",
}


@dataclass(frozen=True)
class ToolCall:
    """One recorded fake-tool invocation."""

    tool: str
    args: tuple[str, ...]
    cwd: str


@dataclass(frozen=True)
class Outcome:
    """The result of running a script under test."""

    status: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


class FakeTools:
    """A directory of fake tools that is the entire PATH of the script under test."""

    def __init__(self, directory: Path, names: Iterable[str]) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self._config: dict[str, object] = dict(DEFAULTS)
        self._write_config()
        for name in names:
            self.add(name)

    def _write_config(self) -> None:
        (self.directory / "config.json").write_text(
            json.dumps(self._config), encoding="utf-8"
        )

    def configure(self, **values: object) -> None:
        unknown = set(values) - set(DEFAULTS)
        assert not unknown, f"unknown fake tool settings: {sorted(unknown)}"
        self._config |= values
        self._write_config()

    def add(self, name: str) -> None:
        program = self.directory / f"{name}.py"
        program.write_text(
            f"TOOL = {name!r}\n{PRELUDE}record(TOOL)\n{BODIES[name]}",
            encoding="utf-8",
        )
        interpreter = str(Path(sys.executable))
        if IS_WINDOWS:
            shim = self.directory / f"{name}.cmd"
            shim.write_bytes(f'@"{interpreter}" -I "%~dp0{name}.py" %*\r\n'.encode())
        else:
            shim = self.directory / name
            shim.write_text(
                f"#!/bin/sh\nexec {shlex.quote(interpreter)} -I "
                f'{shlex.quote(str(program))} "$@"\n',
                encoding="utf-8",
            )
            shim.chmod(0o755)

    def remove(self, name: str) -> None:
        for candidate in (name, f"{name}.cmd", f"{name}.py"):
            (self.directory / candidate).unlink(missing_ok=True)

    def calls(self, tool: str | None = None) -> list[ToolCall]:
        log = self.directory / "calls.jsonl"
        if not log.exists():
            return []
        calls: list[ToolCall] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            calls.append(
                ToolCall(
                    tool=str(entry["tool"]),
                    args=tuple(str(argument) for argument in entry["args"]),
                    cwd=str(entry["cwd"]),
                )
            )
        return [call for call in calls if tool is None or call.tool == tool]

    def environment(
        self,
        *,
        host_os: str = "Darwin",
        scratch: Path | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return a hermetic environment whose PATH holds only the fake tools."""
        environment = {
            "PATH": str(self.directory),
            "PYTHONDONTWRITEBYTECODE": "1",
            "TAILTAG_DOCTOR_HOST_OS": host_os,
        }
        # Windows needs these to start Python and to run .cmd shims; they are
        # OS plumbing, not application configuration.
        for name in ("SYSTEMROOT", "COMSPEC", "PATHEXT"):
            if name in os.environ:
                environment[name] = os.environ[name]
        if scratch is not None:
            environment |= {
                "TMPDIR": str(scratch),
                "TEMP": str(scratch),
                "TMP": str(scratch),
            }
        return environment | (extra or {})


def run_script(
    script: Path,
    arguments: Iterable[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> Outcome:
    """Run a Python script as a real subprocess and decode its output as UTF-8."""
    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    return Outcome(completed.returncode, completed.stdout, completed.stderr)


def lines_with(output: str, prefix: str, fragment: str) -> list[str]:
    """Return output lines that start with `prefix` and contain `fragment`."""
    return [
        line
        for line in output.splitlines()
        if line.startswith(prefix) and fragment in line
    ]


class Workspace(Protocol):
    """A test fixture that owns a repository root and its fake tools."""

    root: Path
    tools: FakeTools


Setup = Callable[[Workspace], None]


def configure(**values: object) -> Setup:
    def apply(workspace: Workspace) -> None:
        workspace.tools.configure(**values)

    return apply


def remove_tool(name: str) -> Setup:
    def apply(workspace: Workspace) -> None:
        workspace.tools.remove(name)

    return apply


def remove_path(relative: str) -> Setup:
    def apply(workspace: Workspace) -> None:
        (workspace.root / relative).unlink()

    return apply


def write_text(relative: str, text: str) -> Setup:
    def apply(workspace: Workspace) -> None:
        (workspace.root / relative).write_text(text, encoding="utf-8")

    return apply


def replace_with_directory(relative: str) -> Setup:
    def apply(workspace: Workspace) -> None:
        (workspace.root / relative).unlink()
        (workspace.root / relative).mkdir()

    return apply
