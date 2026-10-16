"""Behavior of the mobile SDK guard (`scripts/fvm_sdk.py`) and `scripts/mobile_run.py`.

Both run as real subprocesses with fake `fvm` and `adb` tools first (and only)
on PATH, so they run on every OS, including native Windows.

Module contract for the implementation:
- `scripts/fvm_sdk.py` is the shared FVM/pinned-SDK module that doctor imports
  and also the guard command: `python scripts/fvm_sdk.py <repository_root>`
  exits 0 silently when `apps/mobile/.fvmrc` pins an SDK that
  `fvm api list --compress` lists under `versions[].name`, else prints one of
  three messages to stderr and exits 1.
- `scripts/mobile_run.py` reads the target from the `DEVICE` environment
  variable, locates the repository from its own file location, and may import
  only the standard library and `fvm_sdk` from its own directory. The tests
  copy those two files into a fixture repository.
- The iOS-needs-macOS decision uses the same `TAILTAG_DOCTOR_HOST_OS` override
  as doctor (Darwin, Linux, or Windows). This is an assumption: the contract
  names that seam only for doctor.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.fake_tools_support import (
    SCRIPTS_DIRECTORY,
    FakeTools,
    Outcome,
    Setup,
    configure,
    fvm_list,
    remove_path,
    remove_tool,
    run_script,
    write_text,
)
from tests.semgrep_support import dry_run_commands, task_dry_run

FVM_MISSING = "FVM is not installed; install it: https://fvm.app/documentation/getting-started/installation"
PIN_UNREADABLE = "Could not read the pinned Flutter version from apps/mobile/.fvmrc."
SDK_MISSING = (
    "Flutter 3.47.2 (pinned in apps/mobile/.fvmrc) is not installed; "
    "run: (cd apps/mobile && fvm install)"
)
CONFIG_TEMPLATE = (
    "cp apps/mobile/config/development.example.json apps/mobile/config/development.json"
)


@dataclass
class MobileFixture:
    root: Path
    tools: FakeTools
    scratch: Path


def make_fixture(tmp_path: Path, *tools: str) -> MobileFixture:
    root = tmp_path / "repository"
    (root / "apps/mobile/config").mkdir(parents=True)
    (root / "apps/mobile/.fvmrc").write_text('{\n  "flutter": "3.47.2"\n}\n')
    (root / "apps/mobile/config/development.json").write_text("{}\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return MobileFixture(root, FakeTools(tmp_path / "tools", tools), scratch)


# --- mobile-sdk-guard helper --------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        pytest.param(remove_tool("fvm"), FVM_MISSING, id="fvm-missing"),
        pytest.param(
            write_text("apps/mobile/.fvmrc", "{}\n"), PIN_UNREADABLE, id="no-pin"
        ),
        pytest.param(remove_path("apps/mobile/.fvmrc"), PIN_UNREADABLE, id="no-fvmrc"),
        pytest.param(
            configure(fvm_list=fvm_list(["3.47.1", "3.47.20"])),
            SDK_MISSING,
            id="only-other-versions-including-a-prefix-match",
        ),
        pytest.param(
            configure(fvm_list=fvm_list(["3.47.1"], projects=["3.47.2"])),
            SDK_MISSING,
            id="pinned-version-only-under-projects",
        ),
        pytest.param(configure(), None, id="installed"),
        pytest.param(
            configure(
                fvm_list=fvm_list(["3.47.2"], projects=["3.47.2"], projects_first=True)
            ),
            None,
            id="installed-with-projects-listed-first",
        ),
    ],
)
def test_sdk_guard_requires_the_pinned_sdk_in_the_versions_list(
    tmp_path: Path, setup: Setup, message: str | None
) -> None:
    fixture = make_fixture(tmp_path, "fvm")
    setup(fixture)

    outcome = run_script(
        SCRIPTS_DIRECTORY / "fvm_sdk.py",
        [str(fixture.root)],
        cwd=tmp_path,
        environment=fixture.tools.environment(),
    )

    if message is None:
        assert outcome.status == 0, outcome.output
        assert outcome.output == ""
        assert [call.args for call in fixture.tools.calls("fvm")] == [
            ("api", "list", "--compress")
        ]
    else:
        assert outcome.status == 1
        assert outcome.stderr.strip() == message


# --- mobile_run.py ------------------------------------------------------------


class RunFixture(MobileFixture):
    def run(
        self,
        device: str | None,
        *,
        host_os: str = "Darwin",
        devcontainer: bool = False,
    ) -> Outcome:
        extra = {"DEVICE": device} if device is not None else {}
        if devcontainer:
            extra["TAILTAG_DEVCONTAINER"] = "1"
        outcome = run_script(
            self.root / "scripts/mobile_run.py",
            [],
            cwd=self.root,
            environment=self.tools.environment(
                host_os=host_os, scratch=self.scratch, extra=extra
            ),
        )
        # Temporary files are always cleaned up, whatever the outcome.
        assert list(self.scratch.iterdir()) == []
        return outcome

    def flutter_runs(self) -> list[tuple[str, ...]]:
        return [
            call.args
            for call in self.tools.calls("fvm")
            if call.args[:2] == ("flutter", "run")
        ]


def make_run_fixture(tmp_path: Path) -> RunFixture:
    base = make_fixture(tmp_path, "fvm", "adb")
    (base.root / "scripts").mkdir()
    shutil.copy(
        SCRIPTS_DIRECTORY / "mobile_run.py", base.root / "scripts/mobile_run.py"
    )
    shared = SCRIPTS_DIRECTORY / "fvm_sdk.py"
    if shared.exists():
        shutil.copy(shared, base.root / "scripts/fvm_sdk.py")
    return RunFixture(base.root, base.tools, base.scratch)


DEVICE_LISTING = "Pixel 8 (mobile)"
NO_DEVICE_HELP = (
    "Start one with: fvm flutter emulators --launch <emulator-id>",
    "Then run: task mobile-run DEVICE=<id>",
)
IOS_NEEDS_MACOS = "iOS targets need macOS with Xcode; choose an Android device or emulator on this host."


@dataclass(frozen=True)
class StopCase:
    device: str | None
    messages: tuple[str, ...]
    setup: Setup | None = None
    host_os: str = "Darwin"
    devcontainer: bool = False
    # True when the run must stop before the configuration is even validated.
    before_configuration: bool = True


STOP_CASES = {
    "devcontainer": StopCase(
        "emulator-5554",
        ("Mobile commands run on the host, not in the TailTag devcontainer.",),
        devcontainer=True,
    ),
    "fvm-missing": StopCase("emulator-5554", (FVM_MISSING,), remove_tool("fvm")),
    "device-missing": StopCase(
        None,
        (
            "DEVICE is required: choose one connected target.",
            DEVICE_LISTING,
            *NO_DEVICE_HELP,
        ),
    ),
    "device-id-with-unsafe-characters": StopCase(
        "x;touch pwned",
        ("DEVICE is not a connected device id.", DEVICE_LISTING, *NO_DEVICE_HELP),
    ),
    "device-not-connected": StopCase(
        "ghost-1",
        ("DEVICE is not a connected device id.", DEVICE_LISTING, *NO_DEVICE_HELP),
    ),
    "device-id-is-only-a-prefix-of-a-connected-id": StopCase(
        "emulator-555",
        ("DEVICE is not a connected device id.", DEVICE_LISTING, *NO_DEVICE_HELP),
    ),
    "unsupported-platform": StopCase(
        "macos",
        ("TailTag supports Android and iOS targets; macos is a darwin target.",),
    ),
    "ios-device-on-linux": StopCase("ABCD-1234", (IOS_NEEDS_MACOS,), host_os="Linux"),
    "configuration-missing": StopCase(
        "emulator-5554",
        (
            "Mobile configuration is missing: apps/mobile/config/development.json",
            f"Copy the template: {CONFIG_TEMPLATE}",
            "Then set CLERK_PUBLISHABLE_KEY to the Clerk Development publishable key.",
        ),
        remove_path("apps/mobile/config/development.json"),
        before_configuration=False,
    ),
    "configuration-invalid": StopCase(
        "emulator-5554",
        (
            "Mobile configuration is invalid (apps/mobile/config/development.json):",
            "CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key",
            f"Fix the listed values, or start again from the template: {CONFIG_TEMPLATE}",
        ),
        configure(
            check_stdout="",
            check_stderr="CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key",
            check_status=1,
        ),
        before_configuration=False,
    ),
    "adb-missing": StopCase(
        "emulator-5554",
        (
            (
                "adb is not on PATH; install Android platform-tools (or set ANDROID_HOME and "
                "add platform-tools to PATH) so Local API access can be forwarded."
            ),
        ),
        remove_tool("adb"),
        before_configuration=False,
    ),
    "adb-reverse-fails": StopCase(
        "emulator-5554",
        (
            (
                "adb reverse failed for emulator-5554; check that the device is online "
                "(adb devices)."
            ),
        ),
        configure(adb_status=1),
        before_configuration=False,
    ),
}


@pytest.mark.parametrize("case_name", list(STOP_CASES))
def test_mobile_run_stops_with_a_message_before_launching_flutter(
    tmp_path: Path, case_name: str
) -> None:
    case = STOP_CASES[case_name]
    fixture = make_run_fixture(tmp_path)
    if case.setup is not None:
        case.setup(fixture)

    outcome = fixture.run(
        case.device, host_os=case.host_os, devcontainer=case.devcontainer
    )

    assert outcome.status == 1, outcome.output
    for message in case.messages:
        assert message in outcome.output
    assert fixture.flutter_runs() == []
    if case.before_configuration:
        assert not any(
            call.args[:1] == ("dart",) for call in fixture.tools.calls("fvm")
        )


@pytest.mark.parametrize(
    ("device", "origin", "adb_args", "run_status"),
    [
        pytest.param(
            "emulator-5554",
            "http://127.0.0.1:8000",
            ("-s", "emulator-5554", "reverse", "tcp:8000", "tcp:8000"),
            0,
            id="android-http-origin-forwards-its-port",
        ),
        pytest.param(
            "emulator-5554",
            "http://localhost",
            ("-s", "emulator-5554", "reverse", "tcp:80", "tcp:80"),
            3,
            id="android-http-origin-without-port-uses-80",
        ),
        pytest.param(
            "emulator-5554",
            "https://api.example.test",
            None,
            0,
            id="android-https-skips-adb",
        ),
        pytest.param("ABCD-1234", "http://127.0.0.1:8000", None, 0, id="ios-skips-adb"),
    ],
)
def test_mobile_run_launches_flutter_with_the_config_and_propagates_its_exit_code(
    tmp_path: Path,
    device: str,
    origin: str,
    adb_args: tuple[str, ...] | None,
    run_status: int,
) -> None:
    fixture = make_run_fixture(tmp_path)
    fixture.tools.configure(check_stdout=f"{origin}\n", run_status=run_status)

    outcome = fixture.run(device)

    assert outcome.status == run_status, outcome.output
    calls = fixture.tools.calls()
    launches = [
        call
        for call in calls
        if call.tool == "fvm" and call.args[:2] == ("flutter", "run")
    ]
    assert [call.args for call in launches] == [
        (
            "flutter",
            "run",
            "-d",
            device,
            "--dart-define-from-file=config/development.json",
        )
    ]
    assert re.search(r"apps[\\/]mobile$", launches[0].cwd)
    forwards = [call for call in calls if call.tool == "adb"]
    assert [call.args for call in forwards] == ([] if adb_args is None else [adb_args])
    if forwards:
        assert calls.index(forwards[0]) < calls.index(launches[0])


# --- Taskfile wiring ----------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "required", "forbidden"),
    [
        pytest.param(
            "mobile-setup",
            [r"scripts/fvm_sdk\.py"],
            [r"\b(sed|grep|head)\b", r"\btr -d"],
            id="sdk-guard-is-the-python-helper",
        ),
        pytest.param(
            "mobile-run",
            [r"scripts/mobile_run\.py"],
            [r"mobile_run\.sh"],
            id="mobile-run-launches-the-python-script",
        ),
    ],
)
def test_mobile_tasks_use_the_python_helpers(
    target: str, required: list[str], forbidden: list[str]
) -> None:
    commands = dry_run_commands(task_dry_run(target).stdout)

    for pattern in required:
        assert any(re.search(pattern, command) for command in commands), commands
    for pattern in forbidden:
        assert not any(re.search(pattern, command) for command in commands), commands


# --- generated API client comparison ------------------------------------------


def test_generated_package_comparison_reports_every_kind_of_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "path", [str(SCRIPTS_DIRECTORY), *sys.path])
    import mobile_openapi

    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    for root, files in (
        (expected, {"same.dart": b"a\n", "edited.dart": b"b\n", "lost.dart": b"c\n"}),
        (
            actual,
            {
                "same.dart": b"a\r\n",  # CRLF checkout of identical content
                "edited.dart": b"B\n",
                "extra.dart": b"d\n",
                ".dart_tool/state.json": b"{}",  # local pub state is not compared
            },
        ),
    ):
        for name, content in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(content)

    assert mobile_openapi.package_differences(expected, actual) == [
        "missing    lost.dart",
        "unexpected extra.dart",
        "changed    edited.dart",
    ]
    assert mobile_openapi.package_differences(expected, expected) == []
