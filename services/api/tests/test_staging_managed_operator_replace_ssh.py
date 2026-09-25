"""Acceptance tests for the exact-instance managed-login replacement launcher."""

from __future__ import annotations

import builtins
import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMMAND_PATH = (
    ROOT
    / "services"
    / "api"
    / "accounts"
    / "management"
    / "commands"
    / "replace_staging_managed_operator.py"
)
INSPECTOR_PATH = ROOT / "scripts" / "api_staging_operator_inspect.py"
IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
WINDOW = ["2026-09-23T00:00:00Z", "2026-09-23T00:00:01Z"]
PRIVATE_IDENTIFIER = "staging_managed_private_test_value"
PRIVATE_PASSWORD = "private-password-sentinel-243"
PRIVATE_DIAGNOSTIC = "private-provider-diagnostic-sentinel-243"


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    return importlib.import_module("scripts.api_staging_managed_operator_replace_ssh")


def inspector_result(
    status: str = "PASS", *, identity: object = IDENTITY
) -> dict[str, object]:
    return {
        "result": status,
        "phase": "exact_instance_inspector",
        "identity": identity,
        "target_verified": True,
        "window_utc": WINDOW,
    }


def reviewed_sources() -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for name, path in (
        ("inspector", INSPECTOR_PATH),
        ("recovery_command", COMMAND_PATH),
    ):
        source = path.read_text(encoding="utf-8")
        sources[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    return sources


def registry_payload(*, mismatch: bool = False) -> dict[str, object]:
    """Use the existing #204 tool's fixed, value-free result schema."""
    from scripts import api_staging_registry_reconcile as registry

    structural = {"registry_singleton", "registry_structure", "root_completeness"}
    checks = {key: "MATCH" for key in registry._CHECKS}  # pyright: ignore[reportPrivateUsage]
    for key in structural:
        checks[key] = "PASS"
    if mismatch:
        checks["database_name_actual_registry"] = "MISMATCH"
    return {"result": "MISMATCH" if mismatch else "PASS", "checks": checks}


def install_green_guards(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
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
        return inspector_result()

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

    def registry(config_path: Path) -> dict[str, object]:
        assert (
            config_path == Path.home() / ".config/tailtag/staging-reset-replacement.env"
        )
        calls.append("registry")
        return registry_payload()

    monkeypatch.setattr(runner._inspector, "run", inspect)
    monkeypatch.setattr(runner, "_railway_identity", railway)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(runner._registry_reconcile, "run", registry)
    monkeypatch.setattr(runner, "_reviewed_source", reviewed_sources)
    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    return calls


class SshRecorder:
    """Record an attempted transport even when the launcher catches exceptions."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")


def assert_safe_result(result: dict[str, object], expected: str) -> None:
    assert set(result) == {"result", "phase", "identity", "window_utc"}
    assert result["result"] == expected
    assert result["identity"] in (None, IDENTITY)
    assert isinstance(result["phase"], str)
    window = result["window_utc"]
    assert isinstance(window, list)
    typed_window = cast(list[object], window)
    assert len(typed_window) == 2
    assert all(isinstance(item, str) and item.endswith("Z") for item in typed_window)
    rendered = json.dumps(result, sort_keys=True)
    for private in (PRIVATE_IDENTIFIER, PRIVATE_PASSWORD, PRIVATE_DIAGNOSTIC, INSTANCE):
        assert private not in rendered


def test_green_guard_sequence_starts_one_pinned_ssh_without_private_input(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1/4: fresh guards precede exactly one pinned interactive transport."""
    calls = install_green_guards(runner, monkeypatch)
    attempts: list[list[str]] = []
    environment_before = dict(os.environ)

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append("ssh")
        attempts.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result, "TRANSPORT_EXITED_ZERO_UNVERIFIED")
    assert calls.count("inspector") == 1
    assert calls.count("registry") == 1
    assert calls.count("ssh") == 1
    assert calls.index("registry") < calls.index("ssh")
    assert "preflight" in calls[calls.index("registry") + 1 : calls.index("ssh")]
    assert calls.index("receipt") < calls.index("ssh")
    assert calls.index("instance") < calls.index("ssh")
    assert len(attempts) == 1
    arguments = attempts[0]
    assert arguments[:2] == ["railway", "ssh"]
    assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
    assert arguments[arguments.index("--project") + 1] == runner._target_ids()[0]
    assert arguments[arguments.index("--environment") + 1] == runner._target_ids()[1]
    assert arguments[arguments.index("--service") + 1] == runner._target_ids()[2]
    assert arguments[arguments.index("-c") - 1] == "-I"
    assert arguments[arguments.index("--") + 1] == "env"
    assert (
        arguments[arguments.index("--") + 2]
        == "DJANGO_SETTINGS_MODULE=config.settings.production"
    )
    request = json.loads(arguments[-1])
    assert request["identity"] == IDENTITY
    assert request["sources"] == reviewed_sources()
    assert set(request) == {"identity", "sources"}
    assert set(request["sources"]) == {"inspector", "recovery_command"}
    for source in request["sources"].values():
        assert source["sha256"] == hashlib.sha256(source["source"].encode()).hexdigest()
    joined = " ".join(arguments)
    for private in (PRIVATE_IDENTIFIER, PRIVATE_PASSWORD, PRIVATE_DIAGNOSTIC):
        assert private not in joined
        assert private not in json.dumps(dict(os.environ))
    assert dict(os.environ) == environment_before


@pytest.mark.parametrize("detached", ("stdin", "stdout"))
def test_real_terminal_required_before_any_remote_guard(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    """AC-1: hidden input is unavailable when either terminal stream detaches."""
    calls: list[str] = []
    monkeypatch.setattr(runner.sys, "stdin", Terminal(attached=detached != "stdin"))
    monkeypatch.setattr(runner.sys, "stdout", Terminal(attached=detached != "stdout"))
    monkeypatch.setattr(runner._inspector, "run", lambda: calls.append("inspector"))
    monkeypatch.setattr(runner, "_railway_identity", lambda: calls.append("railway"))
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert calls == []
    assert ssh.calls == []


@pytest.mark.parametrize(
    "bad_evidence",
    (
        "wrong_status",
        "wrong_phase",
        "unverified",
        "missing_identity",
        "wrong_environment",
    ),
)
def test_noncanonical_operator_inspection_never_reaches_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, bad_evidence: str
) -> None:
    """AC-1: both exact managed and limited role evidence is mandatory."""
    calls = install_green_guards(runner, monkeypatch)
    evidence = inspector_result()
    if bad_evidence == "wrong_status":
        evidence["result"] = "FAIL_LIMITED_OPERATOR_MISSING"
    elif bad_evidence == "wrong_phase":
        evidence["phase"] = "public_preflight"
    elif bad_evidence == "unverified":
        evidence["target_verified"] = False
    elif bad_evidence == "missing_identity":
        del evidence["identity"]
    else:
        evidence["identity"] = {**IDENTITY, "environment": "production"}
    monkeypatch.setattr(runner._inspector, "run", lambda: evidence)
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert calls == []
    assert ssh.calls == []


@pytest.mark.parametrize(
    "failed_guard",
    ("railway", "preflight", "receipt", "instance", "repeat_preflight"),
)
def test_failed_fresh_target_guard_prevents_transport(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, failed_guard: str
) -> None:
    """AC-1: no SSH after identity, receipt, instance, or drift failure."""
    calls = install_green_guards(runner, monkeypatch)
    if failed_guard == "railway":
        monkeypatch.setattr(
            runner,
            "_railway_identity",
            lambda: (_ for _ in ()).throw(ValueError(PRIVATE_DIAGNOSTIC)),
        )
    elif failed_guard == "preflight":
        monkeypatch.setattr(
            runner, "_preflight", lambda: {**IDENTITY, "source_sha": "b" * 40}
        )
    elif failed_guard == "receipt":

        def fail_receipt(_identity: dict[str, str]) -> NoReturn:
            raise ValueError(PRIVATE_DIAGNOSTIC)

        monkeypatch.setattr(
            runner,
            "_approved_receipt",
            fail_receipt,
        )
    elif failed_guard == "instance":

        def wrong_instance(_identity: dict[str, str]) -> str:
            return "not-a-valid-instance"

        monkeypatch.setattr(runner, "_active_instance", wrong_instance)
    else:
        reads = 0

        def changing_preflight() -> dict[str, str]:
            nonlocal reads
            reads += 1
            return (
                dict(IDENTITY)
                if reads == 1
                else {
                    **IDENTITY,
                    "deployment_id": "33333333-3333-4333-8333-333333333333",
                }
            )

        monkeypatch.setattr(runner, "_preflight", changing_preflight)
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert "ssh" not in calls
    assert ssh.calls == []
    assert PRIVATE_DIAGNOSTIC not in json.dumps(result)


def test_reviewed_source_failure_stops_before_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: missing/tampered reviewed command source cannot be executed."""
    install_green_guards(runner, monkeypatch)
    monkeypatch.setattr(
        runner,
        "_reviewed_source",
        lambda: (_ for _ in ()).throw(ValueError(PRIVATE_DIAGNOSTIC)),
    )
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert ssh.calls == []
    assert PRIVATE_DIAGNOSTIC not in json.dumps(result)


@pytest.mark.parametrize("failure", ("mismatch", "malformed_pass", "query_error"))
def test_registry_reconciliation_must_prove_all_private_and_live_bindings(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """AC-1: #204 private, persisted, and connected-DB state is a fresh guard."""
    calls = install_green_guards(runner, monkeypatch)

    def reconcile(config_path: Path) -> dict[str, object]:
        assert (
            config_path == Path.home() / ".config/tailtag/staging-reset-replacement.env"
        )
        calls.append("registry")
        if failure == "query_error":
            raise ValueError(PRIVATE_DIAGNOSTIC)
        if failure == "malformed_pass":
            return {"result": "PASS", "checks": {}}
        return registry_payload(mismatch=True)

    monkeypatch.setattr(runner._registry_reconcile, "run", reconcile)
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert calls.count("registry") == 1
    assert ssh.calls == []
    assert PRIVATE_DIAGNOSTIC not in json.dumps(result)


def test_public_target_is_rechecked_after_successful_registry_reconciliation(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: a deployment change during #204 readback blocks the write."""
    calls = install_green_guards(runner, monkeypatch)
    registry_complete = False
    base_registry = runner._registry_reconcile.run

    def reconcile(config_path: Path) -> dict[str, object]:
        nonlocal registry_complete
        result = cast(dict[str, object], base_registry(config_path))
        registry_complete = True
        return result

    def preflight() -> dict[str, str]:
        calls.append("preflight")
        if registry_complete:
            return {**IDENTITY, "deployment_id": "33333333-3333-4333-8333-333333333333"}
        return dict(IDENTITY)

    monkeypatch.setattr(runner._registry_reconcile, "run", reconcile)
    monkeypatch.setattr(runner, "_preflight", preflight)
    ssh = SshRecorder()
    monkeypatch.setattr(runner, "_run", ssh)

    result = cast(dict[str, object], runner.run())

    assert registry_complete
    assert calls.count("registry") == 1
    assert str(result["result"]).startswith("FAIL_")
    assert ssh.calls == []


@pytest.mark.parametrize("transport", ("nonzero", "timeout", "bad_stderr"))
def test_transport_failure_is_uncertain_and_never_retried(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    """AC-4: a possible commit cannot be classified failed or retried."""
    install_green_guards(runner, monkeypatch)
    attempts = 0

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if transport == "timeout":
            raise subprocess.TimeoutExpired(arguments, 1800, stderr=PRIVATE_DIAGNOSTIC)
        if transport == "nonzero":
            return subprocess.CompletedProcess(arguments, 1, None, PRIVATE_DIAGNOSTIC)
        return subprocess.CompletedProcess(arguments, 0, None, PRIVATE_DIAGNOSTIC)

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result, "FAIL_TRANSPORT_UNCERTAIN")
    assert attempts == 1
    assert PRIVATE_DIAGNOSTIC not in json.dumps(result)


def test_exit_zero_does_not_claim_managed_replacement_postcondition(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4/5: successful SSH teardown alone never becomes operational PASS."""
    install_green_guards(runner, monkeypatch)

    def exited_zero(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(
        runner,
        "_run",
        exited_zero,
    )

    result = cast(dict[str, object], runner.run())

    assert_safe_result(result, "TRANSPORT_EXITED_ZERO_UNVERIFIED")
    assert result["result"] not in {"PASS", "REPLACEMENT_READY"}


def test_reviewed_recovery_source_loads_without_undeployed_limited_role_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1: the deployed source bundle must not import an undeployed #243 command."""
    source = reviewed_sources()["recovery_command"]["source"]
    original_import = builtins.__import__
    blocked_attempts: list[str] = []

    def reject_undeployed_module(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] | None = None,
        level: int = 0,
    ) -> object:
        if "staging_validation_operator" in name or any(
            "staging_validation_operator" in item for item in (fromlist or ())
        ):
            blocked_attempts.append(name)
            raise ModuleNotFoundError("undeployed #243 module unavailable")
        return original_import(name, globals, locals, fromlist, level)

    assert source == COMMAND_PATH.read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "accounts.management.commands.replace_staging_managed_operator_compatibility_probe",
        COMMAND_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", reject_undeployed_module)
        spec.loader.exec_module(module)

    assert blocked_attempts == []
    assert hasattr(module, "Command")
    assert module.LIMITED_GROUP_NAME == "TailTag #243 Validation Operator"
    assert module.LIMITED_PERMISSION_NAMES == frozenset(
        {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
    )
