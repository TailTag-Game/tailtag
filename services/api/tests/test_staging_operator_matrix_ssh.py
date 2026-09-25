"""Acceptance tests for the exact-instance interactive #243 matrix launcher.

All provider and SSH observations are local fakes. Isolated bootstrap tests run
synthetic source in a local child process; they never contact Staging.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from copy import deepcopy
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "scripts" / "api_staging_operator_matrix_ssh.py"
MATRIX_PATH = ROOT / "scripts" / "api_staging_operator_matrix.py"
INSPECTOR_PATH = ROOT / "scripts" / "api_staging_operator_inspect.py"
CONTROL_PATHS = (
    "accounts/admin.py",
    "catches/admin.py",
    "conventions/admin.py",
    "fursuits/admin.py",
    "profiles/admin.py",
)
IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
WINDOW = ["2026-09-23T00:00:00Z", "2026-09-23T00:00:01Z"]
PRIVATE = "private-credential-provider-identifier-or-diagnostic"
PENDING_MARKER = "TAILTAG_MATRIX_LIVE_SEQUENCE_COMPLETED_PENDING_CASE9_EVIDENCE"
CASE9_NOT_EXERCISED = frozenset(
    {
        "catch_change",
        "credential_replacement",
        "credential_raw_edit",
        "activation_reactivation",
    }
)
CASE9_SUBCHECKS = frozenset(
    {
        "catch_add",
        "catch_change",
        "catch_bulk_edit",
        "credential_add",
        "credential_replacement",
        "credential_raw_edit",
        "session_add",
        "session_delete",
        "session_bulk_edit",
        "session_history_edit",
        "activation_add",
        "activation_delete",
        "activation_reactivation",
        "enrollment_add",
        "enrollment_selection_change",
        "convention_create",
        "convention_delete",
    }
)


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    assert RUNNER_PATH.is_file(), "the approved matrix launcher must exist"
    return importlib.import_module("scripts.api_staging_operator_matrix_ssh")


def inspector_result(*, identity: object = IDENTITY) -> dict[str, object]:
    return {
        "result": "PASS",
        "phase": "exact_instance_inspector",
        "identity": identity,
        "target_verified": True,
        "window_utc": WINDOW,
    }


def registry_result() -> dict[str, object]:
    from scripts.api_staging_registry_reconcile import (
        _CHECKS,  # pyright: ignore[reportPrivateUsage]
    )

    return {
        "result": "PASS",
        "checks": {
            name: (
                "PASS"
                if name
                in {"registry_singleton", "registry_structure", "root_completeness"}
                else "MATCH"
            )
            for name in _CHECKS
        },
    }


def source_bundle() -> dict[str, object]:
    sources: dict[str, dict[str, str]] = {}
    for name, path in (("inspector", INSPECTOR_PATH), ("matrix", MATRIX_PATH)):
        source = path.read_text(encoding="utf-8")
        sources[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    return {
        "sources": sources,
        "control_hashes": {
            name: hashlib.sha256(
                (ROOT / "services/api" / name).read_bytes()
            ).hexdigest()
            for name in CONTROL_PATHS
        },
    }


def install_guards(runner: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace only the approved provider, reconciliation, and SSH seams."""
    events: list[str] = []
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

    def github() -> None:
        events.append("github")

    def railway() -> None:
        events.append("railway")

    def preflight() -> dict[str, str]:
        events.append("preflight")
        return dict(IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == IDENTITY
        events.append("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == IDENTITY
        events.append("instance")
        return INSTANCE

    def reconcile() -> dict[str, object]:
        events.append("reconcile")
        return registry_result()

    def inspect() -> dict[str, object]:
        events.append("inspector")
        return inspector_result()

    monkeypatch.setattr(runner, "_github_identity", github)
    monkeypatch.setattr(runner, "_railway_identity", railway)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(runner, "_reconcile", reconcile)
    monkeypatch.setattr(runner._inspector, "run", inspect)
    monkeypatch.setattr(runner, "_reviewed_source", source_bundle)
    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    return events


def test_matrix_registry_guard_uses_replacement_private_configuration(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The #243 matrix cannot consume the retired #204 sentinel by default."""
    observed_paths: list[Path] = []

    def reconcile(path: Path) -> dict[str, object]:
        observed_paths.append(path)
        return registry_result()

    monkeypatch.setattr(runner._registry, "run", reconcile)

    assert runner._reconcile() == registry_result()
    assert observed_paths == [
        Path.home() / ".config/tailtag/staging-reset-replacement.env"
    ]


def assert_safe_result(result: dict[str, object]) -> None:
    rendered = json.dumps(result, sort_keys=True)
    assert PRIVATE not in rendered
    assert INSTANCE not in rendered
    assert "password" not in rendered.lower()
    assert "token" not in rendered.lower()
    assert result.get("identity") in (None, IDENTITY)
    assert result.get("window_utc") is not None


def no_ssh(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("SSH started despite failed guard")


def test_run_requires_fresh_full_registry_and_operator_pass_before_one_pinned_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preflight/exact tuple, complete registry, and exact operator are all gates."""
    events = install_guards(runner, monkeypatch)
    sent: list[dict[str, object]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        assert arguments[:2] == ["railway", "ssh"]
        assert arguments[arguments.index("--project") + 1] == runner._target_ids()[0]
        assert arguments[arguments.index("--service") + 1] == runner._target_ids()[2]
        assert (
            arguments[arguments.index("--environment") + 1] == runner._target_ids()[1]
        )
        assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
        assert arguments[arguments.index("-c") - 1] == "-I"
        assert "DJANGO_SETTINGS_MODULE=config.settings.production" in arguments
        sent.append(cast(dict[str, object], json.loads(arguments[-1])))
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED"
    assert events.count("reconcile") == 1
    assert events.count("inspector") == 1
    assert events.count("ssh") == 1
    assert events.index("reconcile") < events.index("inspector") < events.index("ssh")
    assert events.index("receipt") < events.index("instance") < events.index("ssh")
    assert events.count("preflight") >= 2
    assert events[-2:] == ["railway", "ssh"]
    assert sent == [{"identity": IDENTITY, **source_bundle()}]
    assert PRIVATE not in json.dumps(sent)


@pytest.mark.parametrize("detached", ["stdin", "stdout"])
def test_run_needs_both_real_terminals_before_any_provider_call(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    events = install_guards(runner, monkeypatch)
    monkeypatch.setattr(runner.sys, detached, Terminal(attached=False))
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert events == []


@pytest.mark.parametrize(
    "failure",
    [
        {"result": "MISMATCH", "checks": registry_result()["checks"]},
        {"result": "PASS", "checks": {}},
        {"result": "FAIL_CONFIGURATION", "checks": {}},
    ],
)
def test_run_rejects_incomplete_or_failed_registry_without_inspection_or_ssh(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failure: dict[str, object],
) -> None:
    events = install_guards(runner, monkeypatch)
    monkeypatch.setattr(runner, "_reconcile", lambda: failure)
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert "inspector" not in events


@pytest.mark.parametrize(
    "fault", ["failure", "unverified", "different_tuple", "extra_field"]
)
def test_run_rejects_noncanonical_inspector_before_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    events = install_guards(runner, monkeypatch)
    observed = inspector_result()
    if fault == "failure":
        observed["result"] = "FAIL_LIMITED_OPERATOR_MISSING"
    elif fault == "unverified":
        observed["target_verified"] = False
    elif fault == "different_tuple":
        observed["identity"] = {**IDENTITY, "source_sha": "b" * 40}
    else:
        observed["private"] = PRIVATE
    monkeypatch.setattr(runner._inspector, "run", lambda: observed)
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert "ssh" not in events


def test_run_refuses_tuple_drift_after_instance_selection(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = install_guards(runner, monkeypatch)
    observed = iter((dict(IDENTITY), {**IDENTITY, "deployment_id": INSTANCE}))
    monkeypatch.setattr(runner, "_preflight", lambda: next(observed))
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert "instance" in events


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["railway"], 1, None, PRIVATE),
        subprocess.CompletedProcess(["railway"], 0, None, PRIVATE),
        subprocess.TimeoutExpired("railway ssh", 1800, output=PRIVATE),
        KeyboardInterrupt(),
    ],
)
def test_run_stops_on_uncertain_ssh_without_retry_or_private_output(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    install_guards(runner, monkeypatch)
    attempts = 0

    def execute(_arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if isinstance(failure, BaseException):
            raise failure
        return cast(subprocess.CompletedProcess[str], failure)

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert result["result"] == "FAIL_TRANSPORT_UNCERTAIN"
    assert attempts == 1


def test_subprocess_inherits_tty_and_gives_prompt_and_reset_finite_time(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert observed.get("stderr") == subprocess.PIPE
    assert "input" not in observed
    assert observed.get("capture_output") is not True
    assert observed.get("shell") is False
    timeout = observed.get("timeout")
    assert isinstance(timeout, int | float)
    assert 1800 <= timeout <= 3600


def test_reviewed_bundle_uses_exact_checkout_source_and_five_admin_hashes(
    runner: ModuleType,
) -> None:
    """The internal control review receives hashes, never admin source/credentials."""
    assert runner._reviewed_source() == source_bundle()


def test_main_accepts_no_credential_argv(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for argv in (["launcher", PRIVATE], ["launcher", "--password", PRIVATE]):
        monkeypatch.setattr(runner.sys, "argv", argv)
        monkeypatch.setattr(runner, "run", lambda: pytest.fail("providers called"))
        assert runner.main() != 0
        output = capsys.readouterr()
        assert PRIVATE not in output.out + output.err


def isolated_bootstrap(
    runner: ModuleType, request: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", runner._BOOTSTRAP, json.dumps(request)],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def bootstrap_request(inspector_source: str, matrix_source: str) -> dict[str, object]:
    return {
        "identity": IDENTITY,
        "sources": {
            name: {
                "source": source,
                "sha256": hashlib.sha256(source.encode()).hexdigest(),
            }
            for name, source in (
                ("inspector", inspector_source),
                ("matrix", matrix_source),
            )
        },
        "control_hashes": {name: "0" * 64 for name in CONTROL_PATHS},
    }


def pending_matrix_result() -> dict[str, object]:
    return {
        "classification": "LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE",
        "identity": IDENTITY,
        "window_utc": WINDOW,
        "cases": {
            **{str(case): "PASS" for case in range(1, 9)},
            "9": "NOT_EXERCISED",
        },
        "case9": {
            name: "NOT_EXERCISED" if name in CASE9_NOT_EXERCISED else "PASS"
            for name in CASE9_SUBCHECKS
        },
        "case9_control_review": "NOT_EXERCISED",
        "case9_deterministic_evidence": "NOT_EXERCISED",
        "case9_limitations": sorted(CASE9_NOT_EXERCISED),
        "deployed_control_hash_match": "PASS",
        "mutation_may_have_begun": True,
        "reset": "PASS",
        "emergency_decommission": "NOT_EXERCISED",
        "decommission": "PASS",
        "audit_events": [
            {
                "action": "set_fursuit_enabled",
                "actor_class": "unauthorized_actor",
                "target_type": "fursuits.fursuit",
                "outcome": "denied",
                "count": 1,
            },
            {
                "action": "set_profile_enabled",
                "actor_class": "operator",
                "target_type": "profiles.playerprofile",
                "outcome": "succeeded",
                "count": 1,
            },
            {
                "action": "set_fursuit_enabled",
                "actor_class": "emergency_superuser",
                "target_type": "fursuits.fursuit",
                "outcome": "succeeded",
                "count": 1,
            },
        ],
        "session_cascade": "PASS",
        "credential_cascade": "NOT_EXERCISED",
    }


def matrix_source_for_result(result: object) -> str:
    return f"def run(expected_identity):\n    return {result!r}\n"


@pytest.mark.parametrize(
    "fault", ["inspector_hash", "matrix_hash", "control_hash", "extra_key"]
)
def test_bootstrap_rejects_tampered_bundle_before_any_source_side_effect(
    runner: ModuleType, tmp_path: Path, fault: str
) -> None:
    trace = tmp_path / "source-executed"
    source = f"from pathlib import Path\nPath({str(trace)!r}).write_text('executed')\n"
    request = bootstrap_request(source, source)
    sources = cast(dict[str, dict[str, str]], request["sources"])
    hashes = cast(dict[str, str], request["control_hashes"])
    if fault == "inspector_hash":
        sources["inspector"]["sha256"] = "f" * 64
    elif fault == "matrix_hash":
        sources["matrix"]["sha256"] = "f" * 64
    elif fault == "control_hash":
        hashes["accounts/admin.py"] = PRIVATE
    else:
        request["secret"] = PRIVATE

    result = isolated_bootstrap(runner, request)

    assert result.returncode != 0
    assert not trace.exists()
    assert PRIVATE not in result.stdout + result.stderr


def test_bootstrap_checks_target_before_django_and_matrix_source(
    runner: ModuleType, tmp_path: Path
) -> None:
    trace = tmp_path / "execution-order"
    inspector = f"""\
from pathlib import Path
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id):
    Path({str(trace)!r}).write_text('target')
    return False
def _bootstrap(): Path({str(trace)!r}).write_text('django')
def _inspect_orm_preconditions(): Path({str(trace)!r}).write_text('operator')
"""
    matrix = f"from pathlib import Path\nPath({str(trace)!r}).write_text('matrix')\n"

    result = isolated_bootstrap(runner, bootstrap_request(inspector, matrix))

    assert result.returncode != 0
    assert trace.read_text() == "target"
    assert PRIVATE not in result.stdout + result.stderr


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_bootstrap_rejects_inspector_startup_output_before_matrix(
    runner: ModuleType, tmp_path: Path, stream: str
) -> None:
    trace = tmp_path / "matrix-reached"
    noisy = (
        f"print({PRIVATE!r})"
        if stream == "stdout"
        else f"import sys; print({PRIVATE!r}, file=sys.stderr)"
    )
    inspector = f"""\
{noisy}
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions(): return 'PASS'
"""
    matrix = f"from pathlib import Path\nPath({str(trace)!r}).write_text('matrix')\n"

    result = isolated_bootstrap(runner, bootstrap_request(inspector, matrix))

    assert result.returncode != 0
    assert not trace.exists()
    assert PRIVATE not in result.stdout + result.stderr


@pytest.mark.parametrize("emergency_status", ("NOT_EXERCISED", "PASS"))
def test_bootstrap_injects_control_hashes_and_in_memory_inspector_then_marks_pending_sequence(
    runner: ModuleType,
    emergency_status: str,
) -> None:
    observed = pending_matrix_result()
    observed["emergency_decommission"] = emergency_status
    inspector = (
        SYNTHETIC_INSPECTOR
        + """\
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions(): return 'PASS'
"""
    )
    matrix = (
        """\
import sys
def run(expected_identity):
    helper = sys.modules['scripts.api_staging_operator_inspect']
    if not helper._target_identity_matches(expected_identity['source_sha'], expected_identity['deployment_id']):
        raise RuntimeError('identity')
    if set(_CONTROL_HASHES) != {'accounts/admin.py', 'catches/admin.py', 'conventions/admin.py', 'fursuits/admin.py', 'profiles/admin.py'}:
        raise RuntimeError('controls')
    return """
        + repr(observed)
        + "\n"
    )

    result = isolated_bootstrap(runner, bootstrap_request(inspector, matrix))

    assert result.returncode == 0
    assert PRIVATE not in result.stdout + result.stderr
    assert result.stdout.strip() == PENDING_MARKER
    assert "TAILTAG_MATRIX_COMMAND_COMPLETED" not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("fault", ("missing", "invalid", "wrong_type"))
def test_bootstrap_rejects_missing_or_malformed_emergency_cleanup_result(
    runner: ModuleType, fault: str
) -> None:
    observed = pending_matrix_result()
    if fault == "missing":
        del observed["emergency_decommission"]
    elif fault == "invalid":
        observed["emergency_decommission"] = "READY"
    else:
        observed["emergency_decommission"] = True

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("classification",), "PASS"),
        (("cases", "9"), "PASS"),
        (("deployed_control_hash_match",), "FAIL"),
        (("case9_control_review",), "PASS"),
        (("case9_deterministic_evidence",), "PASS"),
        (("reset",), "NOT_EXERCISED"),
        (("decommission",), "NOT_EXERCISED"),
        (("session_cascade",), "NOT_EXERCISED"),
        (("credential_cascade",), "PASS"),
        (("mutation_may_have_begun",), False),
        (("case9_limitations",), []),
        (("audit_events",), []),
    ],
)
def test_bootstrap_rejects_false_pending_sequence_claim(
    runner: ModuleType, path: tuple[str, ...], value: object
) -> None:
    observed = deepcopy(pending_matrix_result())
    target = observed
    for key in path[:-1]:
        target = cast(dict[str, object], target[key])
    target[path[-1]] = value

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


@pytest.mark.parametrize("case", range(1, 9))
def test_bootstrap_requires_each_live_case_to_pass(
    runner: ModuleType, case: int
) -> None:
    observed = pending_matrix_result()
    cast(dict[str, str], observed["cases"])[str(case)] = "NOT_EXERCISED"

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


@pytest.mark.parametrize("subcheck", sorted(CASE9_SUBCHECKS))
def test_bootstrap_requires_each_case9_subcheck_status(
    runner: ModuleType, subcheck: str
) -> None:
    observed = pending_matrix_result()
    cast(dict[str, str], observed["case9"])[subcheck] = (
        "PASS" if subcheck in CASE9_NOT_EXERCISED else "NOT_EXERCISED"
    )

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_bootstrap_requires_exact_case9_subcheck_names(
    runner: ModuleType, change: str
) -> None:
    observed = pending_matrix_result()
    subchecks = cast(dict[str, str], observed["case9"])
    if change == "missing":
        del subchecks["session_add"]
    else:
        subchecks["future_check"] = "PASS"

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


@pytest.mark.parametrize("event_index", range(3))
def test_bootstrap_requires_exact_bounded_audit_evidence(
    runner: ModuleType, event_index: int
) -> None:
    observed = pending_matrix_result()
    events = cast(list[dict[str, object]], observed["audit_events"])
    events[event_index]["count"] = 2

    result = isolated_bootstrap(
        runner,
        bootstrap_request(SYNTHETIC_INSPECTOR, matrix_source_for_result(observed)),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == "FAIL_MATRIX_UNCERTAIN"


# Local subprocesses receive a tiny database facade so either the inspector or
# the bootstrap may establish its read-only precondition transaction. No Django
# installation, settings, database, or external connection is used by this fake.
SYNTHETIC_INSPECTOR = """\
import contextlib, sys, types
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement):
        if statement != 'SET TRANSACTION READ ONLY': raise RuntimeError('write')
db = types.ModuleType('django.db')
db.connection = types.SimpleNamespace(cursor=Cursor)
db.transaction = types.SimpleNamespace(atomic=contextlib.nullcontext)
django = types.ModuleType('django')
django.db = db
sys.modules['django'] = django
sys.modules['django.db'] = db
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap(): pass
def _inspect_orm_preconditions(): return 'PASS'
"""


@pytest.mark.parametrize(
    "guard",
    [
        "_github_identity",
        "_railway_identity",
        "_preflight",
        "_approved_receipt",
        "_active_instance",
        "_reconcile",
        "_reviewed_source",
    ],
)
def test_guard_failure_stops_once_without_exposing_provider_diagnostics(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, guard: str
) -> None:
    install_guards(runner, monkeypatch)
    attempts = 0

    def failed(*_args: object, **_kwargs: object) -> NoReturn:
        nonlocal attempts
        attempts += 1
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(runner, guard, failed)
    monkeypatch.setattr(runner, "_run", no_ssh)
    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert attempts == 1


@pytest.mark.parametrize(
    "check", sorted(cast(dict[str, str], registry_result()["checks"]))
)
def test_registry_pass_cannot_hide_one_mismatched_check(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, check: str
) -> None:
    events = install_guards(runner, monkeypatch)
    observed = registry_result()
    cast(dict[str, str], observed["checks"])[check] = "MISMATCH"
    monkeypatch.setattr(runner, "_reconcile", lambda: observed)
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")
    assert "inspector" not in events


@pytest.mark.parametrize(
    "instance",
    ["", PRIVATE, "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", IDENTITY["source_sha"]],
)
def test_noncanonical_instance_never_reaches_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, instance: str
) -> None:
    install_guards(runner, monkeypatch)

    def active_instance(_identity: dict[str, str]) -> str:
        return instance

    monkeypatch.setattr(runner, "_active_instance", active_instance)
    monkeypatch.setattr(runner, "_run", no_ssh)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert str(result["result"]).startswith("FAIL_")


@pytest.mark.parametrize(
    "notice",
    [
        "Using SSH key from agent: public-key-description\n",
        "Using SSH key from file /local/ssh-key: public-key-description\n",
    ],
)
def test_known_ssh_key_notice_does_not_become_execution_proof(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, notice: str
) -> None:
    install_guards(runner, monkeypatch)

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, None, notice)

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result)
    assert result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED"
    assert notice not in json.dumps(result)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_environment",
        "malformed_sha",
        "malformed_deployment",
        "extra_identity",
        "missing_control",
        "extra_control",
        "extra_source",
        "extra_source_field",
    ],
)
def test_bootstrap_rejects_noncanonical_public_request_before_loading_code(
    runner: ModuleType, tmp_path: Path, fault: str
) -> None:
    trace = tmp_path / "source-executed"
    source = f"from pathlib import Path\nPath({str(trace)!r}).touch()\n"
    request = bootstrap_request(source, source)
    identity = cast(dict[str, str], request["identity"]).copy()
    request["identity"] = identity
    hashes = cast(dict[str, str], request["control_hashes"])
    sources = cast(dict[str, dict[str, str]], request["sources"])
    if fault == "wrong_environment":
        identity["environment"] = "production"
    elif fault == "malformed_sha":
        identity["source_sha"] = PRIVATE
    elif fault == "malformed_deployment":
        identity["deployment_id"] = PRIVATE
    elif fault == "extra_identity":
        identity["credential"] = PRIVATE
    elif fault == "missing_control":
        hashes.pop("catches/admin.py")
    elif fault == "extra_control":
        hashes["authentication/admin.py"] = "0" * 64
    elif fault == "extra_source":
        sources["unreviewed"] = sources["matrix"]
    else:
        sources["matrix"]["credential"] = PRIVATE

    result = isolated_bootstrap(runner, request)

    assert result.returncode != 0
    assert not trace.exists()
    assert PRIVATE not in result.stdout + result.stderr
    assert "TAILTAG_MATRIX_COMMAND_COMPLETED" not in result.stdout


@pytest.mark.parametrize("failure", ["return", "raise", "interrupt"])
def test_bootstrap_never_marks_failed_or_interrupted_matrix_complete(
    runner: ModuleType, failure: str
) -> None:
    body = {
        "return": "return {'classification': 'FAIL_RESET', 'cases': {}}",
        "raise": f"raise RuntimeError({PRIVATE!r})",
        "interrupt": "raise KeyboardInterrupt()",
    }[failure]
    matrix = f"def run(expected_identity):\n    {body}\n"

    result = isolated_bootstrap(runner, bootstrap_request(SYNTHETIC_INSPECTOR, matrix))

    assert result.returncode != 0
    assert PRIVATE not in result.stdout + result.stderr
    assert "TAILTAG_MATRIX_COMMAND_COMPLETED" not in result.stdout


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_bootstrap_rejects_matrix_import_noise_without_authentication(
    runner: ModuleType, tmp_path: Path, stream: str
) -> None:
    trace = tmp_path / "authentication-started"
    matrix = f"""\
import sys
from pathlib import Path
print({PRIVATE!r}, file=sys.{stream})
def run(expected_identity):
    Path({str(trace)!r}).touch()
    return {{'classification': 'PASS'}}
"""

    result = isolated_bootstrap(runner, bootstrap_request(SYNTHETIC_INSPECTOR, matrix))

    assert result.returncode != 0
    assert not trace.exists()
    assert PRIVATE not in result.stdout + result.stderr
    assert "TAILTAG_MATRIX_COMMAND_COMPLETED" not in result.stdout
