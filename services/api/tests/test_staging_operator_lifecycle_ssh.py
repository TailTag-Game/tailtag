"""Acceptance coverage for the guarded interactive #243 lifecycle launcher.

The SSH argv request contains public reviewed code and target identity only.
Secret prompts remain attached to the real terminal inside the remote command.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "scripts" / "api_staging_operator_lifecycle_ssh.py"
INSPECTOR_PATH = ROOT / "scripts" / "api_staging_operator_inspect.py"
COMMAND_PATH = (
    ROOT
    / "services"
    / "api"
    / "accounts"
    / "management"
    / "commands"
    / "staging_validation_operator.py"
)
IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
WINDOW = ["2026-09-23T00:00:00Z", "2026-09-23T00:00:01Z"]
PRIVATE = "private-identifier-password-and-provider-diagnostic"


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    assert RUNNER_PATH.is_file(), "the approved lifecycle launcher must exist"
    return importlib.import_module("scripts.api_staging_operator_lifecycle_ssh")


def inspector_result(status: str, *, identity: object = IDENTITY) -> dict[str, object]:
    return {
        "result": status,
        "phase": "exact_instance_inspector",
        "identity": identity,
        "target_verified": True,
        "window_utc": WINDOW,
    }


def public_sources() -> dict[str, dict[str, str]]:
    """The only accepted argv payloads are reviewed source and its digest."""
    result: dict[str, dict[str, str]] = {}
    for name, path in (
        ("inspector", INSPECTOR_PATH),
        ("lifecycle_command", COMMAND_PATH),
    ):
        source = path.read_text(encoding="utf-8")
        result[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    return result


def install_guards(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action: str = "provision",
) -> list[str]:
    """Replace only inspector, provider, and source/subprocess boundaries."""
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "_target_ids",
        lambda: (
            "a1111111-1111-4111-8111-111111111111",
            "c3333333-3333-4333-8333-333333333333",
            "d4444444-4444-4444-8444-444444444444",
            "e5555555-5555-4555-8555-555555555555",
        ),
    )

    def inspect() -> dict[str, object]:
        calls.append("inspector")
        expected = "FAIL_LIMITED_OPERATOR_MISSING" if action == "provision" else "PASS"
        return inspector_result(expected)

    def railway() -> None:
        calls.append("railway")

    def preflight() -> dict[str, str]:
        calls.append("preflight")
        return dict(IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == IDENTITY
        calls.append("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == IDENTITY
        calls.append("instance")
        return INSTANCE

    monkeypatch.setattr(runner._inspector, "run", inspect)
    monkeypatch.setattr(runner, "_railway_identity", railway)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(runner, "_reviewed_source", public_sources)
    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    return calls


def assert_public_result(
    result: dict[str, object], *, action: str, success: bool
) -> None:
    assert set(result) == {"action", "result", "phase", "identity", "window_utc"}
    assert result["action"] == action
    assert result["identity"] in (None, IDENTITY)
    assert isinstance(result["phase"], str)
    if success:
        assert result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED"
    else:
        assert isinstance(result["result"], str)
        assert result["result"].startswith("FAIL_")
    window = result["window_utc"]
    assert isinstance(window, list)
    typed_window = cast(list[object], window)
    assert len(typed_window) == 2
    assert all(isinstance(item, str) and item.endswith("Z") for item in typed_window)
    rendered = json.dumps(result, sort_keys=True)
    assert PRIVATE not in rendered
    assert INSTANCE not in rendered


def unexpected_ssh(*_args: object) -> NoReturn:
    pytest.fail("SSH started")


@pytest.mark.parametrize("action", ["provision", "decommission"])
def test_run_uses_fresh_guards_and_one_pinned_interactive_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """A7/interactive boundary: exit zero alone is unverified transport evidence."""
    calls = install_guards(runner, monkeypatch, action=action)
    executions: list[tuple[list[str], dict[str, object]]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append("ssh")
        assert arguments[:2] == ["railway", "ssh"]
        assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
        assert arguments[arguments.index("--project") + 1] == runner._target_ids()[0]
        assert arguments[arguments.index("--service") + 1] == runner._target_ids()[2]
        assert (
            arguments[arguments.index("--environment") + 1] == runner._target_ids()[1]
        )
        assert arguments[arguments.index("-c") - 1] == "-I"
        request = json.loads(arguments[-1])
        executions.append((arguments, request))
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run(action))

    assert_public_result(result, action=action, success=True)
    assert calls == [
        "inspector",
        "railway",
        "preflight",
        "receipt",
        "instance",
        "preflight",
        "railway",
        "ssh",
    ]
    assert len(executions) == 1
    arguments, request = executions[0]
    assert request == {
        "action": action,
        "identity": IDENTITY,
        "sources": public_sources(),
    }
    joined = " ".join(arguments)
    assert PRIVATE not in joined
    assert set(request) == {"action", "identity", "sources"}


@pytest.mark.parametrize("attached", ["stdin", "stdout"])
def test_run_requires_both_real_terminals_before_any_provider_call(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    attached: str,
) -> None:
    """Interactive boundary: detached input or output cannot start inspection."""
    events: list[str] = []
    monkeypatch.setattr(runner.sys, "stdin", Terminal(attached=attached != "stdin"))
    monkeypatch.setattr(runner.sys, "stdout", Terminal(attached=attached != "stdout"))
    monkeypatch.setattr(runner._inspector, "run", lambda: events.append("inspector"))
    monkeypatch.setattr(runner, "_railway_identity", lambda: events.append("railway"))

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert events == []


@pytest.mark.parametrize(
    ("action", "inspector_status"),
    [
        ("provision", "PASS"),
        ("provision", "FAIL_MANAGED_OPERATOR_PERMISSION"),
        ("decommission", "FAIL_LIMITED_OPERATOR_MISSING"),
        ("decommission", "FAIL_LIMITED_OPERATOR_PERMISSION"),
    ],
)
def test_run_rejects_every_other_inspector_status_before_provider_recheck(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    inspector_status: str,
) -> None:
    """A7/A8: action-specific role evidence is exact, not merely a verified tuple."""
    calls = install_guards(runner, monkeypatch, action=action)
    monkeypatch.setattr(
        runner._inspector,
        "run",
        lambda: inspector_result(inspector_status),
    )

    result = cast(dict[str, object], runner.run(action))

    assert_public_result(result, action=action, success=False)
    assert calls == []


def test_run_rejects_inspector_target_disagreement_before_provider_recheck(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A7: public identity and target verification must agree with later guards."""
    calls = install_guards(runner, monkeypatch)
    wrong = inspector_result(
        "FAIL_LIMITED_OPERATOR_MISSING", identity={**IDENTITY, "source_sha": "b" * 40}
    )
    monkeypatch.setattr(runner._inspector, "run", lambda: wrong)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert "ssh" not in calls


@pytest.mark.parametrize("fault", ["target_unverified", "wrong_phase", "missing_key"])
def test_run_refuses_noncanonical_inspector_evidence(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """A7: a status string alone cannot authorize an interactive mutation."""
    install_guards(runner, monkeypatch)
    evidence = inspector_result("FAIL_LIMITED_OPERATOR_MISSING")
    if fault == "target_unverified":
        evidence["target_verified"] = False
    elif fault == "wrong_phase":
        evidence["phase"] = "public_preflight"
    else:
        del evidence["identity"]
    monkeypatch.setattr(runner._inspector, "run", lambda: evidence)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)


@pytest.mark.parametrize(
    ("failed", "expected_phase"),
    [
        ("railway", "railway_identity"),
        ("preflight", "public_preflight"),
        ("receipt", "approved_receipt"),
        ("instance", "running_instance"),
    ],
)
def test_run_stops_on_each_fresh_provider_guard(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failed: str,
    expected_phase: str,
) -> None:
    """A7: a failed identity, tuple, receipt, or instance guard has no SSH side effect."""
    calls = install_guards(runner, monkeypatch)
    seam = {
        "railway": "_railway_identity",
        "preflight": "_preflight",
        "receipt": "_approved_receipt",
        "instance": "_active_instance",
    }[failed]

    def unavailable(*_args: object) -> None:
        raise ValueError(PRIVATE)

    monkeypatch.setattr(runner, seam, unavailable)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert result["phase"] == expected_phase
    assert calls[0] == "inspector"
    assert "ssh" not in calls


def test_run_keeps_reviewed_source_failure_before_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive boundary: source-read failure cannot imply a mutation began."""
    install_guards(runner, monkeypatch)

    def source_unavailable() -> dict[str, dict[str, str]]:
        raise ValueError(PRIVATE)

    monkeypatch.setattr(runner, "_reviewed_source", source_unavailable)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert result["phase"] == "reviewed_source"


def test_run_stops_when_repeated_public_tuple_changes(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A7: selecting an instance never licenses SSH after deployment drift."""
    calls = install_guards(runner, monkeypatch)
    observations = iter(
        (
            dict(IDENTITY),
            {**IDENTITY, "deployment_id": "33333333-3333-4333-8333-333333333333"},
        )
    )
    monkeypatch.setattr(runner, "_preflight", lambda: next(observations))
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert calls.count("instance") == 1
    assert calls.count("railway") == 1


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["railway"], 1, None, PRIVATE),
        subprocess.CompletedProcess(["railway"], 0, None, PRIVATE),
        subprocess.TimeoutExpired("railway ssh", 120, output=PRIVATE),
        KeyboardInterrupt(),
    ],
)
def test_run_treats_transport_uncertainty_as_final_without_retry(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    """Interactive boundary: stderr, interruption, and timeout cannot retry mutation."""
    install_guards(runner, monkeypatch)
    attempts = 0

    def execute(_arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if isinstance(failure, BaseException):
            raise failure
        return cast(subprocess.CompletedProcess[str], failure)

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=False)
    assert attempts == 1


def test_run_accepts_only_the_reviewed_key_notice_on_stderr(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive boundary: a known CLI notice is discarded, never retained."""
    install_guards(runner, monkeypatch)
    notice = "Using SSH key from agent: synthetic-key-name\n"

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, None, notice)

    monkeypatch.setattr(
        runner,
        "_run",
        execute,
    )

    result = cast(dict[str, object], runner.run("provision"))

    assert_public_result(result, action="provision", success=True)
    assert notice not in json.dumps(result)


def test_subprocess_boundary_inherits_terminal_streams_and_privately_captures_stderr(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive boundary: no stdin/stdout pipe, input relay, or output transcript."""
    observed: dict[str, object] = {}

    def fake_run(
        arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._run(["railway", "ssh"])

    assert observed.get("stdin") in (None, sys.stdin)
    assert observed.get("stdout") in (None, sys.stdout)
    assert "input" not in observed
    assert observed.get("capture_output") is not True
    assert observed.get("stderr") == subprocess.PIPE
    assert observed.get("shell") is False


def test_interactive_timeout_allows_bounded_human_input_without_extending_reads(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the interactive lifecycle operation receives the 30-minute bound."""
    observed: list[object] = []

    def fake_run(
        arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._run(["railway", "ssh"])
    runner._inspector._run(["railway", "status"])
    runner._reset_ssh._run(["railway", "whoami"])

    assert observed == [1800, 120, 30]


def test_reviewed_source_is_exact_checkout_content_with_digest(
    runner: ModuleType,
) -> None:
    """Interactive boundary: the submitted code is the reviewed local checkout."""
    assert runner._reviewed_source() == public_sources()


def isolated_bootstrap(
    runner: ModuleType, request: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    """Run the actual bootstrap in an isolated local process, never Railway."""
    return subprocess.run(
        [sys.executable, "-I", "-c", runner._BOOTSTRAP, json.dumps(request)],
        text=True,
        capture_output=True,
        check=False,
    )


def bootstrap_request(inspector_source: str) -> dict[str, object]:
    lifecycle_source = "class Command: pass\n"
    return {
        "action": "provision",
        "identity": IDENTITY,
        "sources": {
            "inspector": {
                "source": inspector_source,
                "sha256": hashlib.sha256(inspector_source.encode()).hexdigest(),
            },
            "lifecycle_command": {
                "source": lifecycle_source,
                "sha256": hashlib.sha256(lifecycle_source.encode()).hexdigest(),
            },
        },
    }


def executing_command_request(command_source: str) -> dict[str, object]:
    """Supply a local Django command behind the reviewed bootstrap guards."""
    inspector_source = """\
import sys, types
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement):
        if statement != "SET TRANSACTION READ ONLY": raise RuntimeError
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): return self
    def __exit__(self, *args): return False
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap():
    from django.conf import settings
    if not settings.configured: settings.configure(SECRET_KEY="local-test-only", INSTALLED_APPS=[])
    import django.core.management.base
    from django.db import DatabaseError
    database.DatabaseError = DatabaseError
    sys.modules["django.db"] = database
def _inspect_orm_preconditions(): return "FAIL_LIMITED_OPERATOR_MISSING"
"""
    request = bootstrap_request(inspector_source)
    command_record = cast(
        dict[str, str], cast(dict[str, object], request["sources"])["lifecycle_command"]
    )
    command_record.update(
        source=command_source,
        sha256=hashlib.sha256(command_source.encode()).hexdigest(),
    )
    return request


def raising_command_source(exception: str, message: str, trace: Path) -> str:
    return f"""\
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from pathlib import Path
class Command(BaseCommand):
    def handle(self, *args, **options):
        Path({str(trace)!r}).write_text("handle reached")
        raise {exception}({message!r})
"""


def assert_fixed_bootstrap_failure(
    result: subprocess.CompletedProcess[str], expected: str
) -> None:
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == expected + "\n"
    assert "TAILTAG_LIFECYCLE_COMMAND_COMPLETED" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Invalid command arguments.", "FAIL_LIFECYCLE_CONFIGURATION"),
        (
            "This command is unavailable for the current target.",
            "FAIL_LIFECYCLE_TARGET",
        ),
        ("This command requires an interactive terminal.", "FAIL_LIFECYCLE_TTY"),
        ("Query debugging must be disabled.", "FAIL_LIFECYCLE_DEBUG_LOGGING"),
        ("Confirmation failed.", "FAIL_LIFECYCLE_CONFIRMATION"),
        ("Hidden terminal input is unavailable.", "FAIL_LIFECYCLE_HIDDEN_INPUT"),
        ("Operator identifier is invalid.", "FAIL_LIFECYCLE_IDENTIFIER_INPUT"),
        ("Passwords do not match.", "FAIL_LIFECYCLE_PASSWORD_CONFIRMATION"),
        (
            "Password does not meet operator requirements.",
            "FAIL_LIFECYCLE_PASSWORD_POLICY",
        ),
        (
            "Required operator permissions are unavailable.",
            "FAIL_LIFECYCLE_PERMISSION_PREREQUISITE",
        ),
        (
            "Existing group cannot be used as an operator.",
            "FAIL_LIFECYCLE_EXISTING_GROUP",
        ),
        (
            "Existing account cannot be used as an operator.",
            "FAIL_LIFECYCLE_EXISTING_ACCOUNT",
        ),
    ],
)
def test_isolated_bootstrap_classifies_only_exact_safe_command_errors(
    runner: ModuleType, tmp_path: Path, message: str, expected: str
) -> None:
    """Focused correction: known CommandError from execution has one fixed refusal."""
    trace = tmp_path / "command-reached.txt"
    request = executing_command_request(
        raising_command_source("CommandError", message, trace)
    )

    result = isolated_bootstrap(runner, request)

    assert trace.read_text() == "handle reached"
    assert_fixed_bootstrap_failure(result, expected)
    assert message not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        ("CommandError", "Validation operator action failed."),
        ("DatabaseError", PRIVATE),
        ("CommandError", PRIVATE),
        ("CommandError", "Confirmation failed. " + PRIVATE),
        ("CommandError", PRIVATE + " Confirmation failed."),
        ("CommandError", "Confirmation failed.\n" + PRIVATE),
        ("CommandError", "Confirmation failed.\x1b[31m"),
        ("RuntimeError", "Confirmation failed."),
    ],
)
def test_isolated_bootstrap_keeps_other_execution_failures_uncertain(
    runner: ModuleType, tmp_path: Path, exception: str, message: str
) -> None:
    """Focused correction: private, database, and non-CommandError failures stay opaque."""
    trace = tmp_path / "command-reached.txt"
    request = executing_command_request(
        raising_command_source(exception, message, trace)
    )

    result = isolated_bootstrap(runner, request)

    assert trace.read_text() == "handle reached"
    assert_fixed_bootstrap_failure(result, "FAIL_LIFECYCLE_UNCERTAIN")
    assert message not in result.stdout + result.stderr
    assert PRIVATE not in result.stdout + result.stderr


def test_isolated_bootstrap_keeps_known_message_from_startup_uncertain(
    runner: ModuleType,
) -> None:
    """Focused correction: a CommandError before execute is not a command refusal."""
    message = "Confirmation failed."
    command_source = f"""\
from django.core.management.base import CommandError
raise CommandError({message!r})
"""
    request = executing_command_request(command_source)

    result = isolated_bootstrap(runner, request)

    assert_fixed_bootstrap_failure(result, "FAIL_LIFECYCLE_UNCERTAIN")
    assert message not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "tamper",
    ["inspector_digest", "command_digest", "extra_key", "bad_action"],
)
def test_isolated_bootstrap_refuses_malformed_or_tampered_public_request(
    runner: ModuleType, tmp_path: Path, tamper: str
) -> None:
    """Interactive boundary: malformed code/target data cannot reach command."""
    trace = tmp_path / "source-executed.txt"
    request = bootstrap_request(
        f"from pathlib import Path\nPath({str(trace)!r}).write_text('executed')\n"
    )
    sources = cast(dict[str, dict[str, str]], request["sources"])
    if tamper == "inspector_digest":
        sources["inspector"]["sha256"] = "0" * 64
    elif tamper == "command_digest":
        sources["lifecycle_command"]["sha256"] = "0" * 64
    elif tamper == "extra_key":
        request["secret"] = PRIVATE
    else:
        request["action"] = "reactivate"

    result = isolated_bootstrap(runner, request)

    assert result.returncode != 0
    assert not trace.exists()
    assert PRIVATE not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("action", "observed_status"),
    [
        ("provision", "PASS"),
        ("provision", "FAIL_MANAGED_OPERATOR_PERMISSION"),
        ("decommission", "FAIL_LIMITED_OPERATOR_MISSING"),
    ],
)
def test_isolated_bootstrap_refuses_wrong_role_before_command(
    runner: ModuleType, tmp_path: Path, action: str, observed_status: str
) -> None:
    """A7/A8: the remote role check independently enforces action prerequisites."""
    trace = tmp_path / "read-only-inspection.txt"
    command_trace = tmp_path / "command-reached.txt"
    source = f"""\
import sys, types
from pathlib import Path
events = []
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement): events.append(statement)
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): events.append("atomic")
    def __exit__(self, *args): return False
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
sys.modules["django.db"] = database
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions():
    Path({str(trace)!r}).write_text("|".join(events))
    return {observed_status!r}
"""
    request = bootstrap_request(source)
    request["action"] = action
    command = f"""\
import sys, types
from pathlib import Path
class Command:
    def execute(self, *args, **kwargs): Path({str(command_trace)!r}).write_text("execute")
    def handle(self, *args, **kwargs): Path({str(command_trace)!r}).write_text("handle")
management = types.ModuleType("django.core.management")
def call_command(*args, **kwargs): Path({str(command_trace)!r}).write_text("call_command")
management.call_command = call_command
sys.modules["django.core.management"] = management
"""
    command_record = cast(
        dict[str, str], cast(dict[str, object], request["sources"])["lifecycle_command"]
    )
    command_record.update(
        source=command, sha256=hashlib.sha256(command.encode()).hexdigest()
    )

    result = isolated_bootstrap(runner, request)

    assert result.returncode != 0
    assert trace.read_text() == "atomic|SET TRANSACTION READ ONLY"
    assert not command_trace.exists()


def test_isolated_bootstrap_rejects_target_before_django_or_command(
    runner: ModuleType, tmp_path: Path
) -> None:
    """A7: runtime target mismatch prevents even Django startup."""
    trace = tmp_path / "target-inspection.txt"
    source = f"""\
from pathlib import Path
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id):
    Path({str(trace)!r}).write_text("target")
    return False
def _bootstrap(): Path({str(trace)!r}).write_text("django-started")
def _inspect_orm_preconditions(): Path({str(trace)!r}).write_text("role-inspected")
"""
    result = isolated_bootstrap(runner, bootstrap_request(source))

    assert result.returncode != 0
    assert trace.read_text() == "target"
    assert PRIVATE not in result.stdout + result.stderr


def test_isolated_bootstrap_suppresses_startup_output_and_never_reaches_command(
    runner: ModuleType,
) -> None:
    """Interactive boundary: imported source noise is private and fails closed."""
    source = f"print({PRIVATE!r})\nraise RuntimeError({PRIVATE!r})\n"
    result = isolated_bootstrap(runner, bootstrap_request(source))

    assert result.returncode != 0
    assert PRIVATE not in result.stdout + result.stderr


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_isolated_bootstrap_rejects_nonthrowing_startup_output_before_command(
    runner: ModuleType, tmp_path: Path, stream: str
) -> None:
    """Interactive boundary: even harmless startup chatter aborts the mutation."""
    command_trace = tmp_path / "command-reached.txt"
    print_statement = (
        f"print({PRIVATE!r})"
        if stream == "stdout"
        else f"print({PRIVATE!r}, file=sys.stderr)"
    )
    source = f"""\
import sys, types
{print_statement}
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement):
        if statement != "SET TRANSACTION READ ONLY": raise RuntimeError
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): return self
    def __exit__(self, *args): return False
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
sys.modules["django.db"] = database
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions(): return "FAIL_LIMITED_OPERATOR_MISSING"
"""
    request = bootstrap_request(source)
    command = f"""\
from pathlib import Path
class Command:
    def execute(self, *args, **kwargs): Path({str(command_trace)!r}).write_text("called")
"""
    command_record = cast(
        dict[str, str], cast(dict[str, object], request["sources"])["lifecycle_command"]
    )
    command_record.update(
        source=command, sha256=hashlib.sha256(command.encode()).hexdigest()
    )

    result = isolated_bootstrap(runner, request)

    assert result.returncode != 0
    assert not command_trace.exists()
    assert PRIVATE not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("action", "role_status"),
    [
        ("provision", "FAIL_LIMITED_OPERATOR_MISSING"),
        ("decommission", "PASS"),
    ],
)
def test_isolated_bootstrap_reaches_command_only_for_expected_read_only_role(
    runner: ModuleType, action: str, role_status: str
) -> None:
    """A7/A8: a verified remote role state permits only the requested action."""
    source = f"""\
import sys, types
events = []
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement): events.append(statement)
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): events.append("atomic")
    def __exit__(self, *args): return False
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
sys.modules["django.db"] = database
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions(): return {role_status!r} if events == ["atomic", "SET TRANSACTION READ ONLY"] else "FAIL_EXECUTION"
"""
    request = bootstrap_request(source)
    request["action"] = action
    command = """\
class Command:
    def execute(self, *args, **kwargs): print("LIFECYCLE_COMMAND_REACHED")
    def handle(self, *args, **kwargs): print("LIFECYCLE_COMMAND_REACHED")
"""
    command_record = cast(
        dict[str, str], cast(dict[str, object], request["sources"])["lifecycle_command"]
    )
    command_record.update(
        source=command, sha256=hashlib.sha256(command.encode()).hexdigest()
    )

    result = isolated_bootstrap(runner, request)

    assert result.returncode == 0
    assert "LIFECYCLE_COMMAND_REACHED" in result.stdout
    assert result.stderr == ""


def test_isolated_bootstrap_executes_real_django_base_command_options(
    runner: ModuleType,
) -> None:
    """Interactive boundary: real BaseCommand.execute receives required options."""
    source = """\
import sys, types
events = []
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement): events.append(statement)
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): events.append("atomic")
    def __exit__(self, *args): return False
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap():
    from django.conf import settings
    if not settings.configured: settings.configure(SECRET_KEY="local-test-only", INSTALLED_APPS=[])
    import django.core.management.base
    sys.modules["django.db"] = database
def _inspect_orm_preconditions():
    return "FAIL_LIMITED_OPERATOR_MISSING" if events == ["atomic", "SET TRANSACTION READ ONLY"] else "FAIL_EXECUTION"
"""
    request = bootstrap_request(source)
    command = """\
from django.core.management.base import BaseCommand
class Command(BaseCommand):
    def handle(self, *args, **options):
        if options.get("action") != "provision": raise RuntimeError("wrong action")
        self.stdout.write("THIN_BASE_COMMAND_REACHED")
"""
    command_record = cast(
        dict[str, str], cast(dict[str, object], request["sources"])["lifecycle_command"]
    )
    command_record.update(
        source=command, sha256=hashlib.sha256(command.encode()).hexdigest()
    )

    result = isolated_bootstrap(runner, request)

    assert result.returncode == 0
    assert "THIN_BASE_COMMAND_REACHED" in result.stdout
    assert "TAILTAG_LIFECYCLE_COMMAND_COMPLETED" in result.stdout
    assert result.stderr == ""


def test_run_rejects_invalid_action_without_recording_it(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive boundary: private invalid action text never enters evidence."""
    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    monkeypatch.setattr(
        runner._inspector, "run", lambda: pytest.fail("provider called")
    )

    result = cast(dict[str, object], runner.run(PRIVATE))

    assert PRIVATE not in json.dumps(result)
    assert result["action"] != PRIVATE


def test_main_uses_only_one_action_and_returns_failure_status(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Interactive boundary: private or additional CLI arguments are rejected."""
    for argv in (
        ["launcher"],
        ["launcher", "reactivate"],
        ["launcher", "provision", PRIVATE],
        ["launcher", "--identifier", PRIVATE, "provision"],
    ):
        monkeypatch.setattr(runner.sys, "argv", argv)
        monkeypatch.setattr(
            runner._inspector, "run", lambda: pytest.fail("provider called")
        )
        assert runner.main() != 0
        output = capsys.readouterr()
        assert PRIVATE not in output.out + output.err
