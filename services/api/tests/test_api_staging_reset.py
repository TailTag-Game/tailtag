"""Offline operator acceptance contract for the guarded #204 reset command."""

from __future__ import annotations

import importlib
import json
import socket
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, Self, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_reset.py"
STAGING_URL = "https://staging.tailtag.app"
SENSITIVE = "untrusted-reset-diagnostic-secret"
IDENTITY = {
    "source_sha": "c070f413eec1518459f1fef21b471642765a54e9",
    "deployment_id": "93de11d6-714f-405a-b931-a9b567d5ec1e",
    "environment": "staging",
}
COUNTS = {
    "profiles": 2,
    "conventions": 1,
    "fursuits": 2,
    "enrollments": 2,
    "activations": 2,
    "catches": 0,
    "sessions": 0,
    "credentials": 0,
}

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command contract never contacts Staging, Clerk, or R2 in these tests."""

    def forbidden_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("operator acceptance tests must remain offline")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden_network)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)


@pytest.fixture
def command() -> Any:
    """Load the only approved reset entry point after production code is created."""
    assert SCRIPT.is_file()
    return cast(Any, importlib.import_module("scripts.api_staging_reset"))


class Maintenance:
    """Observe the frozen maintenance boundary without replacing reset domain work."""

    def __init__(self, _configuration: object, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> Self:
        self.events.append("maintenance-enter")
        return self

    def quiesce(self) -> None:
        self.events.append("quiesce")

    def resume(self) -> None:
        self.events.append("resume")

    def __exit__(self, *_: object) -> None:
        self.events.append("maintenance-exit")


class RegateFailureMaintenance(Maintenance):
    """Expose the distinct unsafe state where re-gating itself cannot be proved."""

    def quiesce(self) -> None:
        super().quiesce()
        if self.events.count("quiesce") == 2:
            raise RuntimeError(SENSITIVE)


class EnterFailureMaintenance(Maintenance):
    """Model a maintenance context whose initial safety gate cannot be established."""

    def __enter__(self) -> Self:
        super().__enter__()
        raise RuntimeError(SENSITIVE)


class BaseExceptionEnterFailureMaintenance(Maintenance):
    """Expose an interrupt before maintenance context entry proves a safe gate."""

    def __init__(
        self, configuration: object, events: list[str], failure: BaseException
    ) -> None:
        super().__init__(configuration, events)
        self._failure = failure

    def __enter__(self) -> Self:
        super().__enter__()
        raise self._failure


class BaseExceptionQuiesceFailureMaintenance(Maintenance):
    """Expose an interrupt while initial quiescence is still unproven."""

    def __init__(
        self, configuration: object, events: list[str], failure: BaseException
    ) -> None:
        super().__init__(configuration, events)
        self._failure = failure

    def quiesce(self) -> None:
        super().quiesce()
        raise self._failure


def returning[T](value: T) -> Callable[[object], T]:
    """Create a named typed replacement at an approved CLI seam."""

    def callback(_: object) -> T:
        return value

    return callback


def record_then_return[T](
    events: list[str], event: str, value: T
) -> Callable[[object], T]:
    """Observe ordered orchestration while preserving the patched return contract."""

    def callback(_: object) -> T:
        events.append(event)
        return value

    return callback


def maintenance_factory(events: list[str]) -> Callable[[object], Maintenance]:
    """Expose the maintenance context boundary without replacing domain work."""

    def callback(configuration: object) -> Maintenance:
        return Maintenance(configuration, events)

    return callback


def regate_failure_maintenance_factory(
    events: list[str],
) -> Callable[[object], RegateFailureMaintenance]:
    """Return a context that fails only the deliberate re-gate attempt."""

    def callback(configuration: object) -> RegateFailureMaintenance:
        return RegateFailureMaintenance(configuration, events)

    return callback


def enter_failure_maintenance_factory(
    events: list[str],
) -> Callable[[object], EnterFailureMaintenance]:
    """Return a maintenance boundary that fails before destructive work begins."""

    def callback(configuration: object) -> EnterFailureMaintenance:
        return EnterFailureMaintenance(configuration, events)

    return callback


def base_exception_enter_failure_maintenance_factory(
    events: list[str], failure: BaseException
) -> Callable[[object], BaseExceptionEnterFailureMaintenance]:
    """Return a context that interrupts before entry can establish maintenance."""

    def callback(configuration: object) -> BaseExceptionEnterFailureMaintenance:
        return BaseExceptionEnterFailureMaintenance(configuration, events, failure)

    return callback


def base_exception_quiesce_failure_maintenance_factory(
    events: list[str], failure: BaseException
) -> Callable[[object], BaseExceptionQuiesceFailureMaintenance]:
    """Return a context interrupted during its initial gate proof."""

    def callback(configuration: object) -> BaseExceptionQuiesceFailureMaintenance:
        return BaseExceptionQuiesceFailureMaintenance(configuration, events, failure)

    return callback


def fixed_identity(_: object) -> dict[str, str]:
    return IDENTITY


def deny_maintenance(_: object) -> NoReturn:
    raise AssertionError("maintenance must not open")


def deny_reset_maintenance(_: object) -> NoReturn:
    raise AssertionError("provision must not reset")


def run_main_with_fixed_classification(command: ModuleType) -> int:
    """Turn an escaped interrupt into a normal assertion failure without aborting pytest."""
    try:
        return command.main()
    except (KeyboardInterrupt, SystemExit) as error:
        pytest.fail(
            f"operator interruption escaped fixed classification: {type(error).__name__}",
            pytrace=False,
        )


def test_bad_confirmation_denies_before_preflight_configuration_or_destructive_work(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5/8: accidental invocation cannot open any transport or mutation phase."""
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", ["api_staging_reset.py", "--confirm", "wrong"])
    monkeypatch.setattr(
        command, "validate_target", record_then_return(calls, "preflight", None)
    )
    monkeypatch.setattr(
        command, "load_configuration", record_then_return(calls, "config", None)
    )

    assert run_main_with_fixed_classification(command) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset confirmation\n"
    assert calls == []


def test_unknown_argument_is_sanitized_as_a_confirmation_failure(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5: parser diagnostics must not echo untrusted operator input."""
    monkeypatch.setattr(sys, "argv", ["api_staging_reset.py", f"--unsafe={SENSITIVE}"])

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset confirmation\n"
    assert SENSITIVE not in captured.err


def test_preflight_failure_is_sanitized_and_denies_before_maintenance(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5/6: canonical #203 preflight is mandatory and failures reveal no diagnostics."""
    safety = importlib.import_module("rehearsal.safety")
    calls: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )

    def fail_preflight(_: object) -> NoReturn:
        raise safety.ResetSafetyError(SENSITIVE)

    monkeypatch.setattr(command, "validate_target", fail_preflight)
    monkeypatch.setattr(
        command, "load_configuration", record_then_return(calls, "config", None)
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset preflight\n"
    assert SENSITIVE not in captured.err
    assert calls == []


def test_success_uses_canonical_preflight_then_one_maintenance_boundary(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-2/5/6: reset ordering binds fresh public identity to guarded mutation."""
    events: list[str] = []
    configuration = object()
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )

    def preflight(target: object) -> dict[str, str]:
        events.append(f"preflight:{target}")
        return IDENTITY

    monkeypatch.setattr(command, "validate_target", preflight)
    monkeypatch.setattr(
        command,
        "load_configuration",
        record_then_return(events, "configuration", configuration),
    )
    monkeypatch.setattr(command, "DatabaseMaintenance", maintenance_factory(events))
    monkeypatch.setattr(
        command, "reset_baseline", record_then_return(events, "reset", COUNTS)
    )

    assert command.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert events == [
        f"preflight:{STAGING_URL}",
        "configuration",
        "maintenance-enter",
        "quiesce",
        "reset",
        "resume",
        f"preflight:{STAGING_URL}",
        "maintenance-exit",
    ]
    output = json.loads(captured.out)
    assert output == {
        "identity": IDENTITY,
        "baseline_version": 1,
        "counts": COUNTS,
    }
    assert SENSITIVE not in captured.out


def test_reset_or_resume_failure_reports_only_its_fixed_phase_and_never_success(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/7/RELIABILITY: a committed reset with failed resumption is not success."""
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    preflight_calls = 0

    def preflight(_: str) -> dict[str, str]:
        nonlocal preflight_calls
        preflight_calls += 1
        if preflight_calls == 2:
            return {**IDENTITY, "deployment_id": "1b6a4b35-4e94-4775-a4b9-304205c75786"}
        return IDENTITY

    monkeypatch.setattr(command, "validate_target", preflight)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(command, "DatabaseMaintenance", maintenance_factory(events))
    monkeypatch.setattr(
        command, "reset_baseline", record_then_return(events, "reset", COUNTS)
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset committed maintenance retained\n"
    assert SENSITIVE not in captured.err
    assert events == [
        "maintenance-enter",
        "quiesce",
        "reset",
        "resume",
        "quiesce",
        "maintenance-exit",
    ]


def test_configuration_failure_never_enters_maintenance(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5: unsafe local runtime configuration is denied before a gate mutation."""
    safety = importlib.import_module("rehearsal.safety")
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )

    def fail_configuration(_: object) -> NoReturn:
        raise safety.ResetSafetyError(SENSITIVE)

    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", fail_configuration)
    monkeypatch.setattr(command, "DatabaseMaintenance", deny_maintenance)

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset configuration\n"
    assert SENSITIVE not in captured.err


def test_reset_exception_retains_maintenance_without_attempting_resume(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/7: reset failure cannot reopen writers or report a completed baseline."""
    safety = importlib.import_module("rehearsal.safety")
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )

    def fail_reset(_: object) -> NoReturn:
        raise safety.ResetSafetyError(SENSITIVE)

    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(command, "DatabaseMaintenance", maintenance_factory(events))
    monkeypatch.setattr(command, "reset_baseline", fail_reset)

    assert run_main_with_fixed_classification(command) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance retained\n"
    assert SENSITIVE not in captured.err
    assert events == ["maintenance-enter", "quiesce", "maintenance-exit"]


@pytest.mark.parametrize(
    "failure",
    (KeyboardInterrupt(SENSITIVE), SystemExit(SENSITIVE)),
    ids=("keyboard-interrupt", "system-exit"),
)
def test_reset_base_exception_retains_maintenance_without_resume_or_regate(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
) -> None:
    """AC-6/7/RELIABILITY: destructive-work interrupts retain the already proven gate."""
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )

    def fail_reset(_: object) -> NoReturn:
        events.append("reset")
        raise failure

    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(command, "DatabaseMaintenance", maintenance_factory(events))
    monkeypatch.setattr(command, "reset_baseline", fail_reset)

    assert run_main_with_fixed_classification(command) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance retained\n"
    assert SENSITIVE not in captured.err
    assert events == ["maintenance-enter", "quiesce", "reset", "maintenance-exit"]


@pytest.mark.parametrize(
    "failure",
    (KeyboardInterrupt(SENSITIVE), SystemExit(SENSITIVE)),
    ids=("keyboard-interrupt", "system-exit"),
)
def test_maintenance_entry_base_exception_reports_maintenance_unknown(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
) -> None:
    """AC-5/6/RELIABILITY: interrupted entry cannot claim maintenance was proven."""
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(
        command,
        "DatabaseMaintenance",
        base_exception_enter_failure_maintenance_factory(events, failure),
    )

    assert run_main_with_fixed_classification(command) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance unknown\n"
    assert SENSITIVE not in captured.err
    assert events == ["maintenance-enter"]


@pytest.mark.parametrize(
    "failure",
    (KeyboardInterrupt(SENSITIVE), SystemExit(SENSITIVE)),
    ids=("keyboard-interrupt", "system-exit"),
)
def test_initial_quiesce_base_exception_reports_maintenance_unknown(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
) -> None:
    """AC-5/6/RELIABILITY: an unproven initial gate cannot be reported retained."""
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(
        command,
        "DatabaseMaintenance",
        base_exception_quiesce_failure_maintenance_factory(events, failure),
    )
    monkeypatch.setattr(command, "reset_baseline", deny_maintenance)

    assert run_main_with_fixed_classification(command) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance unknown\n"
    assert SENSITIVE not in captured.err
    assert events == ["maintenance-enter", "quiesce", "maintenance-exit"]


def test_failed_regate_after_changed_final_identity_reports_maintenance_unknown(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/7: inability to re-establish the writer gate is more severe than success."""
    events: list[str] = []
    preflight_calls = 0

    def preflight(_: str) -> dict[str, str]:
        nonlocal preflight_calls
        preflight_calls += 1
        return (
            IDENTITY if preflight_calls == 1 else {**IDENTITY, "source_sha": "d" * 40}
        )

    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    monkeypatch.setattr(command, "validate_target", preflight)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(
        command, "DatabaseMaintenance", regate_failure_maintenance_factory(events)
    )
    monkeypatch.setattr(
        command, "reset_baseline", record_then_return(events, "reset", COUNTS)
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance unknown\n"
    assert SENSITIVE not in captured.err
    assert events == [
        "maintenance-enter",
        "quiesce",
        "reset",
        "resume",
        "quiesce",
        "maintenance-exit",
    ]


def test_initial_maintenance_gate_failure_reports_maintenance_unknown(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-5/6: reset cannot report a retained gate it never proved during entry."""
    events: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(
        command, "DatabaseMaintenance", enter_failure_maintenance_factory(events)
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance unknown\n"
    assert SENSITIVE not in captured.err
    assert events == ["maintenance-enter"]


def test_keyboard_interrupt_during_final_preflight_regates_before_reporting_failure(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/RELIABILITY: an interrupt after resume cannot silently leave writers open."""
    events: list[str] = []
    preflight_calls = 0

    def interrupted_final_preflight(_: str) -> dict[str, str]:
        nonlocal preflight_calls
        preflight_calls += 1
        if preflight_calls == 2:
            raise KeyboardInterrupt(SENSITIVE)
        return IDENTITY

    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"],
    )
    monkeypatch.setattr(command, "validate_target", interrupted_final_preflight)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(command, "DatabaseMaintenance", maintenance_factory(events))
    monkeypatch.setattr(
        command, "reset_baseline", record_then_return(events, "reset", COUNTS)
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset committed maintenance retained\n"
    assert SENSITIVE not in captured.err
    assert events == [
        "maintenance-enter",
        "quiesce",
        "reset",
        "resume",
        "quiesce",
        "maintenance-exit",
    ]


def test_provision_requires_separate_confirmation_and_never_enters_reset_maintenance(
    command: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-1/4/5: sentinel provisioning is a distinct non-destructive operator path."""
    calls: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_reset.py",
            "--provision",
            "--confirm",
            "provision-tailtag-staging-reset",
        ],
    )
    monkeypatch.setattr(command, "validate_target", fixed_identity)
    monkeypatch.setattr(command, "load_configuration", returning(object()))
    monkeypatch.setattr(
        command, "provision_identity", record_then_return(calls, "provision", None)
    )
    monkeypatch.setattr(command, "DatabaseMaintenance", deny_reset_maintenance)

    assert command.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert calls == ["provision"]
    assert SENSITIVE not in captured.out
