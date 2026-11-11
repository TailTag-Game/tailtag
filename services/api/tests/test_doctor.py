"""Behavior of `scripts/doctor.py`, the `scripts/doctor.sh` wrapper, and the doctor tasks.

Doctor runs as a real subprocess inside a fixture repository whose PATH holds
only fake external tools (see fake_tools_support), so these tests run on every
OS, including native Windows.

Assumptions the implementation must honor:
- The git checks call `git rev-parse --show-toplevel`, `git remote get-url origin`,
  `git branch --show-current`, and `git diff --quiet` / `git diff --cached --quiet`
  (or `git status --porcelain`).
- Devcontainer checks resolve `python` and `uv` through PATH and keep the
  `uv ... python -m config.compose_database_url`, `... -c 'import django; import
  psycopg'`, and `... -c <database probe>` invocations, with the probe receiving
  DJANGO_SETTINGS_MODULE and DATABASE_URL in its environment.
- Mobile checks resolve `fvm` through PATH and decode its output as UTF-8.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.fake_tools_support import (
    REPOSITORY_ROOT,
    SCRIPTS_DIRECTORY,
    FakeTools,
    Outcome,
    Setup,
    configure,
    fvm_list,
    lines_with,
    remove_path,
    remove_tool,
    replace_with_directory,
    run_script,
    write_text,
)
from tests.process_support import skip_on_windows
from tests.semgrep_support import dry_run_commands, task_dry_run

DOCTOR = SCRIPTS_DIRECTORY / "doctor.py"
FOOTER = "Mobile checks: run task mobile-doctor on the host."
HOST_TOOLS = ("git", "docker", "task", "gh", "devcontainer", "python", "uv")
DATABASE_SECRETS = ("postgresql://", ":password@")


@dataclass
class DoctorFixture:
    """A fixture TailTag repository plus the fake tools doctor sees."""

    root: Path
    tools: FakeTools
    scratch: Path

    def run(
        self,
        *arguments: str,
        devcontainer: bool = False,
        host_os: str = "Darwin",
        command_timeout: str | None = None,
    ) -> Outcome:
        extra = {"TAILTAG_DEVCONTAINER": "1"} if devcontainer else {}
        if command_timeout is not None:
            extra["TAILTAG_DOCTOR_COMMAND_TIMEOUT"] = command_timeout
        return run_script(
            DOCTOR,
            arguments,
            cwd=self.root,
            environment=self.tools.environment(
                host_os=host_os, scratch=self.scratch, extra=extra
            ),
        )


def make_fixture(tmp_path: Path, *, mobile: bool = False) -> DoctorFixture:
    root = tmp_path / "repository"
    for directory in (".git", ".devcontainer", "services/api", "scripts"):
        (root / directory).mkdir(parents=True)
    for name in (
        "services/api/Dockerfile",
        "services/api/compose.yaml",
        "services/api/uv.lock",
        "services/api/.env.example",
        ".devcontainer/devcontainer.json",
        ".devcontainer/compose.devcontainer.yaml",
        "scripts/doctor.sh",
        "scripts/doctor.py",
    ):
        (root / name).touch()
    (root / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  default:\n    cmds:\n      - 'true'\n"
    )
    (root / "services/api/pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.13,<3.14"\n'
    )
    names = (*HOST_TOOLS, "fvm") if mobile else HOST_TOOLS
    if mobile:
        (root / "apps/mobile/config").mkdir(parents=True)
        (root / "apps/mobile/.fvmrc").write_text('{\n  "flutter": "3.47.2"\n}\n')
        (root / "apps/mobile/config/development.json").write_text("{}\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return DoctorFixture(root, FakeTools(tmp_path / "tools", names), scratch)


@dataclass(frozen=True)
class Expect:
    """What a doctor run must show: exit status, substrings, and prefixed lines."""

    status: int
    contains: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    lines: tuple[tuple[str, str], ...] = ()
    no_lines: tuple[tuple[str, str], ...] = ()


def assert_outcome(outcome: Outcome, expect: Expect) -> None:
    output = outcome.output
    assert outcome.status == expect.status, output
    for text in expect.contains:
        assert text in output, output
    for text in expect.absent:
        assert text not in output, output
    for prefix, fragment in expect.lines:
        assert lines_with(output, prefix, fragment), (prefix, fragment, output)
    for prefix, fragment in expect.no_lines:
        assert not lines_with(output, prefix, fragment), (prefix, fragment, output)


NO_FAILURES = (("FAIL", ""),)


def test_host_mode_passes_and_runs_only_host_checks(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)

    outcome = fixture.run()

    assert_outcome(
        outcome,
        Expect(
            0,
            contains=(
                "PASS  Docker is installed",
                "PASS  Docker daemon is reachable",
                "PASS  Docker Compose is available",
                "PASS  Dev Container CLI is available",
                "PASS  Required foundation artifact exists: scripts/doctor.py",
                "PASS  Required foundation artifact exists: scripts/doctor.sh",
                "WARN  GitHub CLI is installed but not authenticated; run: gh auth login",
                "Required checks passed.",
                FOOTER,
            ),
            absent=("Python is", "uv is", "PostgreSQL is", "FVM"),
            no_lines=NO_FAILURES,
        ),
    )


@pytest.mark.parametrize(
    ("setup", "expect"),
    [
        pytest.param(
            configure(docker_info_status=1),
            Expect(
                1, ("FAIL  Docker daemon is unavailable; start Docker and try again",)
            ),
            id="docker-daemon-down",
        ),
        pytest.param(
            configure(docker_compose_status=1),
            Expect(
                1,
                (
                    "FAIL  Docker Compose is unavailable; install Docker with the Compose plugin",
                ),
            ),
            id="compose-unavailable",
        ),
        pytest.param(
            remove_tool("docker"),
            Expect(
                1,
                (
                    "FAIL  Docker is not installed; install Docker with the Compose plugin",
                ),
            ),
            id="docker-missing",
        ),
        pytest.param(
            remove_tool("devcontainer"),
            Expect(0, ("WARN  No Dev Container CLI was detected",)),
            id="devcontainer-cli-missing-only-warns",
        ),
        pytest.param(
            replace_with_directory("services/api/Dockerfile"),
            Expect(
                1,
                (
                    (
                        "FAIL  Required foundation artifact is not a regular file: "
                        "services/api/Dockerfile"
                    ),
                ),
            ),
            id="required-file-is-a-directory",
        ),
        pytest.param(
            remove_path(".devcontainer/compose.devcontainer.yaml"),
            Expect(
                1,
                (
                    (
                        "FAIL  Required foundation artifact is missing: "
                        ".devcontainer/compose.devcontainer.yaml"
                    ),
                ),
            ),
            id="devcontainer-override-missing",
        ),
        pytest.param(
            remove_path("scripts/doctor.py"),
            Expect(
                1, ("FAIL  Required foundation artifact is missing: scripts/doctor.py",)
            ),
            id="doctor-script-is-a-required-artifact",
        ),
        pytest.param(
            configure(remote="https://private-token@github.com/example/fork.git"),
            Expect(
                0,
                (
                    (
                        "WARN  Origin points to an unexpected repository: "
                        "https://github.com/example/fork.git"
                    ),
                ),
                absent=("private-token",),
            ),
            id="origin-credentials-redacted",
        ),
        pytest.param(
            configure(remote=None),
            Expect(1, ("FAIL  No origin remote is configured",)),
            id="no-origin",
        ),
        pytest.param(
            configure(git_toplevel="/somewhere/else"),
            Expect(
                1,
                (
                    "FAIL  Run this script from the root of the cloned TailTag repository",
                ),
            ),
            id="not-the-repository-root",
        ),
        pytest.param(
            remove_tool("git"),
            Expect(
                1,
                (
                    "FAIL  Git is not installed",
                    "FAIL  Run this script from the root of the cloned TailTag repository",
                ),
            ),
            id="git-missing",
        ),
        pytest.param(
            configure(branch="main"),
            Expect(
                0,
                (
                    "WARN  You are on main; create a feature branch before making changes",
                ),
            ),
            id="on-main",
        ),
        pytest.param(
            configure(dirty=True),
            Expect(0, ("WARN  Working tree contains uncommitted changes",)),
            id="dirty-working-tree",
        ),
        pytest.param(
            remove_tool("gh"),
            Expect(
                0,
                (
                    (
                        "WARN  GitHub CLI is not installed; it is recommended but not "
                        "currently required"
                    ),
                ),
            ),
            id="gh-missing",
        ),
        pytest.param(
            configure(gh_auth_status=0),
            Expect(0, ("PASS  GitHub CLI is authenticated",)),
            id="gh-authenticated",
        ),
    ],
)
def test_host_mode_reports_each_condition(
    tmp_path: Path, setup: Setup, expect: Expect
) -> None:
    fixture = make_fixture(tmp_path)
    setup(fixture)

    assert_outcome(fixture.run(), expect)


def test_a_hung_tool_fails_its_check_instead_of_hanging_doctor(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    fixture.tools.configure(docker_info_seconds=30)
    started = time.monotonic()

    outcome = fixture.run(command_timeout="1")

    assert time.monotonic() - started < 20
    assert_outcome(
        outcome,
        Expect(
            1,
            ("FAIL  Docker daemon is unavailable; start Docker and try again",),
            lines=(("PASS", "Docker Compose is available"),),
        ),
    )


def test_devcontainer_mode_passes_and_runs_only_backend_checks(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)

    outcome = fixture.run(devcontainer=True)

    assert_outcome(
        outcome,
        Expect(
            0,
            contains=(
                "PASS  Python 3.13 matches the required version 3.13",
                "PASS  uv is available",
                "PASS  Locked backend dependencies are usable",
                "PASS  PostgreSQL is reachable from the backend environment",
                "PASS  Canonical backend task commands are available",
                FOOTER,
            ),
            absent=("Docker daemon", *DATABASE_SECRETS),
            no_lines=NO_FAILURES,
        ),
    )


@pytest.mark.parametrize(
    ("setup", "expect"),
    [
        pytest.param(
            configure(task_list_status=109),
            Expect(
                1,
                (
                    (
                        "FAIL  Canonical backend task commands are unavailable; verify "
                        "go-task is installed and the root Taskfile.yml parses"
                    ),
                ),
            ),
            id="taskfile-does-not-parse",
        ),
        pytest.param(
            configure(python_version="3.12"),
            Expect(1, ("FAIL  Python 3.12 does not match the required version 3.13",)),
            id="wrong-python-version",
        ),
        pytest.param(
            remove_tool("python"),
            Expect(1, ("FAIL  Python is not installed in the TailTag devcontainer",)),
            id="python-missing",
        ),
        pytest.param(
            configure(dependency_status=1),
            Expect(1, ("FAIL  Locked backend dependencies are unusable",)),
            id="dependencies-unusable",
        ),
        pytest.param(
            configure(compose_url_status=1),
            Expect(
                1, ("FAIL  PostgreSQL is not reachable from the backend environment",)
            ),
            id="compose-database-url-fails",
        ),
        pytest.param(
            configure(database_status=1),
            Expect(
                1, ("FAIL  PostgreSQL is not reachable from the backend environment",)
            ),
            id="database-unreachable",
        ),
        pytest.param(
            remove_tool("uv"),
            Expect(1, ("FAIL  uv is not installed in the TailTag devcontainer",)),
            id="uv-missing",
        ),
    ],
)
def test_devcontainer_mode_reports_each_failure_without_leaking_database_urls(
    tmp_path: Path, setup: Setup, expect: Expect
) -> None:
    fixture = make_fixture(tmp_path)
    setup(fixture)

    outcome = fixture.run(devcontainer=True)

    assert_outcome(outcome, expect)
    for secret in DATABASE_SECRETS:
        assert secret not in outcome.output


def test_unknown_argument_prints_usage_and_exits_2_before_any_check(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)

    outcome = fixture.run("--bogus")

    assert outcome.status == 2
    assert "task doctor" in outcome.stderr
    assert "--mobile" in outcome.stderr
    assert "PASS" not in outcome.output


def test_devcontainer_marker_matches_the_value_doctor_checks() -> None:
    devcontainer = (REPOSITORY_ROOT / ".devcontainer/devcontainer.json").read_text(
        encoding="utf-8"
    )

    assert '"TAILTAG_DEVCONTAINER": "1"' in devcontainer


# --- doctor.py --mobile -------------------------------------------------------


class HealthServer:
    """A local API stand-in recording the paths doctor probes."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.status = 200
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.paths.append(self.path)
                self.send_response(owner.status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def health_server() -> Iterator[HealthServer]:
    server = HealthServer()
    try:
        yield server
    finally:
        server.close()


def unreachable_origin() -> str:
    """Return an origin on a port nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def mobile_fixture(
    tmp_path: Path, server: HealthServer, setup: Setup | None = None
) -> DoctorFixture:
    fixture = make_fixture(tmp_path, mobile=True)
    fixture.tools.configure(check_stdout=f"{server.origin}\n")
    if setup is not None:
        setup(fixture)
    return fixture


def test_mobile_mode_on_a_healthy_host_passes_and_probes_the_api(
    tmp_path: Path, health_server: HealthServer
) -> None:
    fixture = mobile_fixture(
        tmp_path,
        health_server,
        # Incidental stderr from the config tool must never become the probed origin.
        configure(check_stderr="notice: an incidental tool message"),
    )

    outcome = fixture.run("--mobile")

    assert_outcome(
        outcome,
        Expect(
            0,
            contains=(
                "Mobile environment (host)",
                "Required foundation artifact exists: services/api/Dockerfile",
                "PASS  FVM is installed",
                "PASS  Flutter 3.47.2 (pinned in apps/mobile/.fvmrc) is installed",
                "PASS  Mobile configuration is valid",
            ),
            absent=("Docker is installed", "LEAKED_ENV_CANARY", "notice:"),
            no_lines=(*NO_FAILURES, ("WARN", "configuration"), ("WARN", "emulators")),
        ),
    )
    assert health_server.paths == ["/health/live"]
    assert fixture.tools.calls("fvm-unexpected") == []
    # AC14: the result names the origin and says host reachability is not device reachability.
    passes = lines_with(outcome.output, "PASS", health_server.origin)
    assert len(passes) == 1
    assert "device" in passes[0]


def test_mobile_mode_inside_the_devcontainer_fails_without_running_mobile_tools(
    tmp_path: Path, health_server: HealthServer
) -> None:
    fixture = mobile_fixture(tmp_path, health_server)

    outcome = fixture.run("--mobile", devcontainer=True)

    assert_outcome(
        outcome,
        Expect(
            1,
            ("FAIL  Mobile checks run on the host, not in the TailTag devcontainer",),
            absent=("Docker daemon",),
        ),
    )
    assert fixture.tools.calls("fvm") == []


FLUTTER_DOCTOR_HEADER = "Doctor summary (to see all details, run flutter doctor -v):\n"
ANDROID_BAD = (
    "[✗] Android toolchain - develop for Android devices\n"
    "    ✗ cmdline-tools component is missing.\n"
)
XCODE_OK = "[✓] Xcode - develop for iOS and macOS (Xcode 27.0)\n"
CHROME = "[✓] Chrome - develop for the web"
LINUX_ANDROID_OK = (
    FLUTTER_DOCTOR_HEADER
    + "[✓] Flutter (Channel stable, 3.47.2, on Ubuntu 24.04, locale en-US)\n"
    + "[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)\n"
    + CHROME
)
LINUX_ANDROID_BAD = (
    FLUTTER_DOCTOR_HEADER
    + "[✓] Flutter (Channel stable, 3.47.2, on Ubuntu 24.04, locale en-US)\n"
    + ANDROID_BAD
    + CHROME
)


@dataclass(frozen=True)
class MobileCase:
    setup: Setup
    expect: Expect
    host_os: str = "Darwin"
    probed: bool = True


MOBILE_CASES = {
    "fvm-missing": MobileCase(
        remove_tool("fvm"),
        Expect(1, lines=(("FAIL", "FVM is not installed"), ("WARN", "skipped"))),
        probed=False,
    ),
    "pinned-version-unreadable": MobileCase(
        write_text("apps/mobile/.fvmrc", "{}\n"),
        Expect(
            1,
            (
                "FAIL  Could not determine the pinned Flutter version from apps/mobile/.fvmrc",
            ),
            lines=(("WARN", "skipped"),),
        ),
        probed=False,
    ),
    # 3.47.2 appears only under `projects` and as a prefix of 3.47.20: neither is installed.
    "pinned-sdk-not-installed": MobileCase(
        configure(fvm_list=fvm_list(["3.47.1", "3.47.20"], projects=["3.47.2"])),
        Expect(
            1,
            (
                (
                    "FAIL  Flutter 3.47.2 (pinned in apps/mobile/.fvmrc) is not installed; "
                    "run: (cd apps/mobile && fvm install)"
                ),
            ),
            lines=(("WARN", "skipped"),),
        ),
        probed=False,
    ),
    "no-usable-toolchain": MobileCase(
        configure(
            flutter_doctor=FLUTTER_DOCTOR_HEADER
            + "[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2, locale en-US)\n"
            + ANDROID_BAD
            + CHROME
        ),
        # An absent Xcode counts as unusable.
        Expect(
            1, lines=(("FAIL", "ANDROID_HOME"), ("FAIL", "xcodebuild -runFirstLaunch"))
        ),
    ),
    "one-toolchain-unusable-only-warns": MobileCase(
        configure(
            flutter_doctor=FLUTTER_DOCTOR_HEADER + ANDROID_BAD + XCODE_OK + CHROME
        ),
        Expect(0, lines=(("WARN", "ANDROID_HOME"),), no_lines=NO_FAILURES),
    ),
    # Both entries are [!]; treating [!] as unusable would FAIL this case.
    "toolchains-with-warnings-are-usable": MobileCase(
        configure(
            flutter_doctor=FLUTTER_DOCTOR_HEADER
            + "[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2, locale en-US)\n"
            + "[!] Android toolchain - develop for Android devices (Android SDK version 36.0.0)\n"
            + "    ! Some Android licenses not accepted.\n"
            + "[!] Xcode - develop for iOS and macOS (Xcode 27.0)\n"
            + "    ! CocoaPods not installed.\n"
            + CHROME
        ),
        Expect(0, lines=(("WARN", "usable with warnings"),), no_lines=NO_FAILURES),
    ),
    "ios-not-applicable-on-linux": MobileCase(
        configure(flutter_doctor=LINUX_ANDROID_OK),
        Expect(
            0,
            ("iOS is not applicable",),
            no_lines=(*NO_FAILURES, ("WARN", "iOS"), ("WARN", "Xcode")),
        ),
        host_os="Linux",
    ),
    # Flutter on Windows marks a usable toolchain [√] and an unusable one [X].
    "windows-square-root-mark-is-usable": MobileCase(
        configure(
            flutter_doctor=FLUTTER_DOCTOR_HEADER
            + "[√] Flutter (Channel stable, 3.47.2, on Microsoft Windows, locale en-US)\n"
            + "[√] Android toolchain - develop for Android devices (Android SDK version 36.0.0)\n"
        ),
        Expect(0, no_lines=(*NO_FAILURES, ("WARN", "ANDROID_HOME"))),
        host_os="Windows",
    ),
    "windows-x-mark-is-unusable": MobileCase(
        configure(
            flutter_doctor=FLUTTER_DOCTOR_HEADER
            + "[√] Flutter (Channel stable, 3.47.2, on Microsoft Windows, locale en-US)\n"
            + "[X] Android toolchain - develop for Android devices\n"
        ),
        Expect(1, lines=(("FAIL", "ANDROID_HOME"),)),
        host_os="Windows",
    ),
    "android-unusable-off-macos-fails": MobileCase(
        configure(flutter_doctor=LINUX_ANDROID_BAD),
        Expect(1, lines=(("FAIL", "iOS is not applicable on this host"),)),
        host_os="Linux",
    ),
    "no-android-or-ios-device-warns": MobileCase(
        configure(
            devices=[
                {"name": "macOS", "id": "macos", "targetPlatform": "darwin"},
                {"name": "Chrome", "id": "chrome", "targetPlatform": "web-javascript"},
            ]
        ),
        Expect(
            0,
            lines=(
                ("WARN", "fvm flutter emulators --launch <emulator-id>"),
                ("WARN", 'xcrun simctl boot "<device>", then open Device Hub'),
            ),
        ),
    ),
    "an-ios-device-alone-is-enough": MobileCase(
        configure(
            devices=[{"name": "iPhone 17", "id": "ABCD-1234", "targetPlatform": "ios"}]
        ),
        Expect(0, no_lines=(("WARN", "emulators --launch"),)),
    ),
    "configuration-missing-warns-without-probing": MobileCase(
        remove_path("apps/mobile/config/development.json"),
        Expect(
            0,
            (
                (
                    "WARN  Mobile configuration is missing; run: cp "
                    "apps/mobile/config/development.example.json "
                    "apps/mobile/config/development.json"
                ),
            ),
        ),
        probed=False,
    ),
    "configuration-invalid-fails-without-probing": MobileCase(
        configure(
            check_stdout="",
            check_stderr="CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key",
            check_status=1,
        ),
        Expect(
            1,
            (
                "FAIL  Mobile configuration is invalid",
                "CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key",
            ),
        ),
        probed=False,
    ),
}


@pytest.mark.parametrize("case_name", list(MOBILE_CASES))
def test_mobile_mode_reports_each_condition(
    tmp_path: Path, health_server: HealthServer, case_name: str
) -> None:
    case = MOBILE_CASES[case_name]
    fixture = mobile_fixture(tmp_path, health_server, case.setup)

    outcome = fixture.run("--mobile", host_os=case.host_os)

    assert_outcome(outcome, case.expect)
    assert health_server.paths == (["/health/live"] if case.probed else [])


@pytest.mark.parametrize("failure", ["connection-refused", "http-503"])
def test_unreachable_api_warns_with_the_origin_and_does_not_fail(
    tmp_path: Path, health_server: HealthServer, failure: str
) -> None:
    if failure == "http-503":
        health_server.status = 503
        origin = health_server.origin
    else:
        origin = unreachable_origin()
    fixture = mobile_fixture(
        tmp_path, health_server, configure(check_stdout=f"{origin}\n")
    )

    outcome = fixture.run("--mobile")

    assert outcome.status == 0, outcome.output
    warnings = lines_with(outcome.output, "WARN", origin)
    assert len(warnings) == 1
    assert "/health/live" in warnings[0]
    assert "device" in warnings[0]
    assert not lines_with(outcome.output, "PASS", origin)


# --- doctor.sh wrapper and Taskfile wiring ------------------------------------


@skip_on_windows("doctor.sh is a POSIX wrapper; Windows runs doctor.py through task.")
@pytest.mark.parametrize(
    ("tools", "expected_call", "expected_status", "expected_output"),
    [
        pytest.param(
            ("uv", "python3"),
            (
                "uv",
                (
                    "run",
                    "--no-project",
                    "python",
                    "scripts/doctor.py",
                    "--mobile",
                    "two words",
                ),
            ),
            7,
            "",
            id="prefers-uv",
        ),
        pytest.param(
            ("python3",),
            ("python3", ("scripts/doctor.py", "--mobile", "two words")),
            7,
            "",
            id="falls-back-to-python3",
        ),
        pytest.param(
            (),
            None,
            1,
            "Install uv (https://docs.astral.sh/uv/) or Python 3 to run doctor.",
            id="neither-prints-install-hint",
        ),
    ],
)
def test_doctor_sh_wrapper_launches_doctor_py(
    tmp_path: Path,
    tools: tuple[str, ...],
    expected_call: tuple[str, tuple[str, ...]] | None,
    expected_status: int,
    expected_output: str,
) -> None:
    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPTS_DIRECTORY / "doctor.sh", root / "scripts/doctor.sh")
    fake_tools = FakeTools(tmp_path / "tools", tools)
    fake_tools.configure(uv_status=7, python3_status=7)
    dirname = shutil.which("dirname")
    if dirname is not None:
        (fake_tools.directory / "dirname").symlink_to(dirname)
    bash = shutil.which("bash")
    assert bash is not None

    completed = subprocess.run(
        [bash, "scripts/doctor.sh", "--mobile", "two words"],
        cwd=root,
        env=fake_tools.environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == expected_status, completed.stderr
    assert expected_output in completed.stdout + completed.stderr
    calls = [(call.tool, call.args) for call in fake_tools.calls()]
    assert calls == ([] if expected_call is None else [expected_call])


@pytest.mark.parametrize(
    ("target", "launch", "guarded_by_host_check"),
    [
        pytest.param(
            "doctor",
            r'custom-uv run --no-project python "\S*scripts/doctor\.py"',
            False,
            id="doctor",
        ),
        pytest.param(
            "mobile-doctor",
            r'custom-uv run --no-project python "\S*scripts/doctor\.py" --mobile',
            True,
            id="mobile-doctor-behind-the-host-guard",
        ),
    ],
)
def test_doctor_tasks_launch_doctor_py_with_uv(
    target: str, launch: str, guarded_by_host_check: bool
) -> None:
    commands = dry_run_commands(
        task_dry_run(target, environment={"UV": "custom-uv"}).stdout
    )

    launches = [command for command in commands if "scripts/doctor.py" in command]
    assert len(launches) == 1, commands
    assert re.search(rf"{launch}$", launches[0]), launches[0]
    guarded = any("Mobile commands run on the host" in command for command in commands)
    assert guarded == guarded_by_host_check
