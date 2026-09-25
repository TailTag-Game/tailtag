"""Offline acceptance tests for guarded emergency Staging decommission."""

from __future__ import annotations

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
MODULE = "scripts.api_staging_emergency_operator_decommission_ssh"
IDENTITY = {
    "environment": "staging",
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
PROJECT = "a1111111-1111-4111-8111-111111111111"
ENVIRONMENT = "c3333333-3333-4333-8333-333333333333"
SERVICE = "d4444444-4444-4444-8444-444444444444"
POSTGRES = "e5555555-5555-4555-8555-555555555555"
PRIVATE = "private-emergency-identifier-password-database-sentinel"
REQUEST = {
    "identity": IDENTITY,
    "database_url_fingerprint": "b" * 64,
    "database_facts_fingerprint": "c" * 64,
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    assert (
        ROOT / "scripts/api_staging_emergency_operator_decommission_ssh.py"
    ).is_file()
    return importlib.import_module(MODULE)


def _inspector_result(status: str = "PASS") -> dict[str, object]:
    return {
        "result": status,
        "phase": "exact_instance_inspector",
        "identity": dict(IDENTITY),
        "target_verified": True,
        "window_utc": ["2026-09-25T00:00:00Z", "2026-09-25T00:00:01Z"],
    }


def _registry_result(*, mismatch: str | None = None) -> dict[str, object]:
    from scripts import api_staging_registry_reconcile as registry

    structural = {"registry_singleton", "registry_structure", "root_completeness"}
    checks = {
        key: "PASS" if key in structural else "MATCH"
        for key in registry._CHECKS  # pyright: ignore[reportPrivateUsage]
    }
    if mismatch is not None:
        checks[mismatch] = "MISMATCH"
    return {"result": "MISMATCH" if mismatch else "PASS", "checks": checks}


def _green_guards(runner: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub external reads and transport, retaining the launcher's decisions."""
    events: list[str] = []

    def marked(name: str) -> None:
        events.append(name)

    def preflight() -> dict[str, str]:
        marked("preflight")
        return dict(IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == IDENTITY
        marked("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == IDENTITY
        marked("instance")
        return INSTANCE

    def registry(_path: Path) -> dict[str, object]:
        marked("registry")
        return _registry_result()

    def inspector() -> dict[str, object]:
        marked("inspector")
        return _inspector_result()

    def precondition(identity: dict[str, str], instance_id: str) -> str:
        assert identity == IDENTITY and instance_id == INSTANCE
        marked("precondition")
        return "READY"

    def postcondition(identity: dict[str, str], instance_id: str) -> str:
        assert identity == IDENTITY and instance_id == INSTANCE
        marked("postcondition")
        return "DECOMMISSIONED"

    def binding_request(_identity: dict[str, str]) -> dict[str, object]:
        return dict(REQUEST)

    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    monkeypatch.setattr(runner, "_github_identity", lambda: marked("github"))
    monkeypatch.setattr(runner, "_railway_identity", lambda: marked("railway"))
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(
        runner, "_target_ids", lambda: (PROJECT, ENVIRONMENT, SERVICE, POSTGRES)
    )
    monkeypatch.setattr(runner, "_binding_request", binding_request)
    monkeypatch.setattr(runner._registry_reconcile, "run", registry)
    monkeypatch.setattr(runner._inspector, "run", inspector)
    monkeypatch.setattr(runner, "_emergency_precondition", precondition)
    monkeypatch.setattr(runner, "_emergency_postcondition", postcondition)
    return events


def _result(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    result = cast(dict[str, object], value)
    assert set(result) == {"result", "phase", "identity", "window_utc"}
    assert result["identity"] in (None, IDENTITY)
    assert PRIVATE not in json.dumps(result)
    assert INSTANCE not in json.dumps(result)
    return result


def _unexpected_ssh(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("Decommission SSH began before every guard passed")


def test_exact_instance_decommission_requires_independent_postcondition(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _green_guards(runner, monkeypatch)
    executions: list[list[str]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        executions.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = _result(runner.run())

    assert result["result"] == "PASS_EMERGENCY_OPERATOR_DECOMMISSIONED"
    assert len(executions) == 1
    assert events.index("github") < events.index("ssh")
    assert events.index("railway") < events.index("ssh")
    assert events.index("preflight") < events.index("receipt") < events.index("ssh")
    assert events.index("receipt") < events.index("instance") < events.index("ssh")
    assert events.index("registry") < events.index("ssh")
    assert events.index("inspector") < events.index("ssh")
    assert (
        events.index("precondition")
        < events.index("ssh")
        < events.index("postcondition")
    )
    assert events.index("ssh") < len(events) - 1
    assert events.count("preflight") >= 2
    assert events.count("inspector") >= 2
    args = executions[0]
    assert args[:2] == ["railway", "ssh"]
    for flag, expected in (
        ("--project", PROJECT),
        ("--service", SERVICE),
        ("--environment", ENVIRONMENT),
        ("--deployment-instance", INSTANCE),
    ):
        assert args[args.index(flag) + 1] == expected
    assert json.loads(args[-1]) == REQUEST
    rendered = " ".join(args)
    assert PRIVATE not in rendered
    assert "--password" not in args
    assert "--identifier" not in args


@pytest.mark.parametrize("detached", ("stdin", "stdout"))
def test_real_terminal_required_before_provider_access(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    monkeypatch.setattr(runner.sys, detached, Terminal(attached=False))
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    assert cast(str, _result(runner.run())["result"]).startswith("FAIL_")
    assert events == []


@pytest.mark.parametrize(
    "state", ("ABSENT", "DECOMMISSIONED", "MISMATCH", "INDETERMINATE")
)
def test_emergency_state_must_be_ready_before_decommission(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    events = _green_guards(runner, monkeypatch)

    def precondition(_identity: dict[str, str], _instance: str) -> str:
        return state

    monkeypatch.setattr(runner, "_emergency_precondition", precondition)
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    assert cast(str, _result(runner.run())["result"]).startswith("FAIL_")
    assert "postcondition" not in events


@pytest.mark.parametrize(
    "guard",
    ("github", "railway", "preflight", "receipt", "instance", "registry", "roles"),
)
def test_identity_binding_or_role_failure_blocks_decommission(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, guard: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    if guard == "github":
        monkeypatch.setattr(
            runner,
            "_github_identity",
            lambda: (_ for _ in ()).throw(ValueError(PRIVATE)),
        )
    elif guard == "railway":
        monkeypatch.setattr(
            runner,
            "_railway_identity",
            lambda: (_ for _ in ()).throw(ValueError(PRIVATE)),
        )
    elif guard == "preflight":
        monkeypatch.setattr(
            runner, "_preflight", lambda: {**IDENTITY, "source_sha": "b" * 40}
        )
    elif guard == "receipt":

        def failed_receipt(_identity: dict[str, str]) -> NoReturn:
            raise ValueError(PRIVATE)

        monkeypatch.setattr(
            runner,
            "_approved_receipt",
            failed_receipt,
        )
    elif guard == "instance":

        def invalid_instance(_identity: dict[str, str]) -> str:
            return "not-a-uuid"

        monkeypatch.setattr(runner, "_active_instance", invalid_instance)
    elif guard == "registry":

        def bad_registry(_path: Path) -> dict[str, object]:
            return _registry_result(mismatch="cluster_identifier_actual_registry")

        monkeypatch.setattr(
            runner._registry_reconcile,
            "run",
            bad_registry,
        )
    else:
        monkeypatch.setattr(
            runner._inspector,
            "run",
            lambda: _inspector_result("FAIL_MANAGED_OPERATOR_PERMISSION"),
        )
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    assert cast(str, _result(runner.run())["result"]).startswith("FAIL_")
    assert "postcondition" not in events


@pytest.mark.parametrize("transport", ("nonzero", "stderr", "timeout"))
def test_transport_uncertainty_never_counts_as_decommissioned_or_retries(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    attempts = 0

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        events.append("ssh")
        if transport == "timeout":
            raise subprocess.TimeoutExpired(arguments, 30)
        if transport == "stderr":
            return subprocess.CompletedProcess(arguments, 0, None, PRIVATE)
        return subprocess.CompletedProcess(arguments, 1, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    assert _result(runner.run())["result"] == "FAIL_TRANSPORT_UNCERTAIN"
    assert attempts == 1
    assert "postcondition" not in events


@pytest.mark.parametrize("state", ("READY", "ABSENT", "MISMATCH", "INDETERMINATE"))
def test_zero_exit_is_not_cleanup_proof_without_exact_postcondition(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    events = _green_guards(runner, monkeypatch)

    def execute(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, None, "")

    def postcondition(_identity: dict[str, str], _instance: str) -> str:
        return state

    monkeypatch.setattr(runner, "_run", execute)
    monkeypatch.setattr(runner, "_emergency_postcondition", postcondition)

    assert cast(str, _result(runner.run())["result"]).startswith("FAIL_")
    assert "inspector" in events


@pytest.mark.parametrize("drift", ("public_source", "instance", "operator_roles"))
def test_postcondition_target_or_role_drift_blocks_cleanup_claim(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    events = _green_guards(runner, monkeypatch)

    def execute(args: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        return subprocess.CompletedProcess(args, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)
    if drift == "public_source":

        def preflight() -> dict[str, str]:
            events.append("preflight")
            return (
                {**IDENTITY, "source_sha": "b" * 40}
                if "ssh" in events
                else dict(IDENTITY)
            )

        monkeypatch.setattr(runner, "_preflight", preflight)
    elif drift == "instance":
        reads = 0

        def instance(_identity: dict[str, str]) -> str:
            nonlocal reads
            reads += 1
            events.append("instance")
            return "33333333-3333-4333-8333-333333333333" if reads >= 2 else INSTANCE

        monkeypatch.setattr(runner, "_active_instance", instance)
    else:
        reads = 0

        def inspector() -> dict[str, object]:
            nonlocal reads
            reads += 1
            events.append("inspector")
            return (
                _inspector_result("FAIL_LIMITED_OPERATOR_PERMISSION")
                if reads >= 2
                else _inspector_result()
            )

        monkeypatch.setattr(runner._inspector, "run", inspector)

    assert cast(str, _result(runner.run())["result"]).startswith("FAIL_")
    assert events.count("ssh") == 1


def test_main_refuses_arguments_without_reflecting_private_input(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runner.sys, "argv", ["emergency-decommission", PRIVATE])
    monkeypatch.setattr(runner, "run", _unexpected_ssh)

    assert runner.main() != 0
    output = capsys.readouterr()
    assert "FAIL_INVALID_ARGUMENTS" in output.out + output.err
    assert PRIVATE not in output.out + output.err


def test_transport_inherits_tty_and_does_not_capture_hidden_confirmation(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def subprocess_run(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(args, 0, None, "")

    monkeypatch.setattr(runner.subprocess, "run", subprocess_run)
    runner._run(["railway", "ssh"])

    assert observed.get("shell") is False
    assert observed.get("stdin") is None
    assert observed.get("stdout") is None
    assert observed.get("capture_output") is not True
    assert observed.get("input") is None
    assert observed.get("stderr") == subprocess.PIPE
