"""Exact-instance launcher tests for #243 managed password-only recovery."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest

from tests.test_staging_managed_operator_replace_ssh import (
    IDENTITY,
    INSTANCE,
    inspector_result,
    registry_payload,
)

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
COMMAND_PATH = (
    ROOT
    / "services/api/accounts/management/commands/rotate_staging_managed_password.py"
)
PRIVATE = "private-managed-password-never-in-launcher-output"


class Terminal(StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_staging_managed_password_rotate_ssh")


def green_guards(launcher: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []

    def inspected() -> dict[str, object]:
        events.append("inspector")
        return inspector_result()

    def reconciled(_config: Path) -> dict[str, object]:
        events.append("registry")
        return registry_payload()

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

    monkeypatch.setattr(launcher.sys, "stdin", Terminal())
    monkeypatch.setattr(launcher.sys, "stdout", Terminal())
    monkeypatch.setattr(launcher._inspector, "run", inspected)
    monkeypatch.setattr(launcher._registry_reconcile, "run", reconciled)
    monkeypatch.setattr(launcher, "_railway_identity", lambda: events.append("railway"))
    monkeypatch.setattr(launcher, "_preflight", preflight)
    monkeypatch.setattr(launcher, "_approved_receipt", receipt)
    monkeypatch.setattr(launcher, "_active_instance", instance)
    return events


def assert_sanitized_result(result: dict[str, object]) -> None:
    assert set(result) == {"result", "phase", "identity", "window_utc"}
    assert result["identity"] in (None, IDENTITY)
    assert PRIVATE not in json.dumps(result)
    assert INSTANCE not in json.dumps(result)


def unexpected_ssh(_argv: list[str]) -> NoReturn:
    pytest.fail("SSH started")


def mismatched_registry(_path: Path) -> dict[str, object]:
    return registry_payload(mismatch=True)


def rejected_receipt(_identity: dict[str, str]) -> NoReturn:
    raise ValueError(PRIVATE)


def invalid_instance(_identity: dict[str, str]) -> str:
    return "not-an-instance"


def test_full_guards_precede_one_pinned_interactive_ssh(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: exact roles, #204 reconciliation, receipt and instance precede write."""
    events = green_guards(launcher, monkeypatch)
    calls: list[list[str]] = []

    def execute(argv: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, None, "")

    monkeypatch.setattr(launcher, "_run", execute)
    result = cast(dict[str, object], launcher.run())

    assert_sanitized_result(result)
    assert result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED"
    assert (
        events.count("inspector")
        == events.count("registry")
        == events.count("ssh")
        == 1
    )
    assert events.index("inspector") < events.index("registry") < events.index("ssh")
    assert events.count("preflight") >= 2
    assert events.index("receipt") < events.index("instance") < events.index("ssh")
    assert len(calls) == 1
    argv = calls[0]
    assert argv[:2] == ["railway", "ssh"]
    assert argv[argv.index("--deployment-instance") + 1] == INSTANCE
    assert argv[argv.index("--project") + 1] == launcher._PROJECT_ID
    assert argv[argv.index("--service") + 1] == launcher._SERVICE_ID
    assert argv[argv.index("--environment") + 1] == launcher._ENVIRONMENT_ID
    assert argv[argv.index("-c") - 1] == "-I"
    request = json.loads(argv[-1])
    assert request["identity"] == IDENTITY
    assert request["sources"]["rotation_command"]["source"] == COMMAND_PATH.read_text(
        encoding="utf-8"
    )
    assert PRIVATE not in " ".join(argv)


@pytest.mark.parametrize("detached", ("stdin", "stdout"))
def test_detached_terminal_stops_before_any_provider_call(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    events = green_guards(launcher, monkeypatch)
    monkeypatch.setattr(launcher.sys, detached, StringIO())
    monkeypatch.setattr(launcher, "_run", unexpected_ssh)
    result = cast(dict[str, object], launcher.run())
    assert str(result["result"]).startswith("FAIL_")
    assert events == []


@pytest.mark.parametrize(
    "bad", ("inspector", "registry", "target", "receipt", "instance")
)
def test_bad_guard_never_starts_password_rotation(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    green_guards(launcher, monkeypatch)
    if bad == "inspector":
        monkeypatch.setattr(
            launcher._inspector,
            "run",
            lambda: inspector_result("FAIL_MANAGED_OPERATOR_MISSING"),
        )
    elif bad == "registry":
        monkeypatch.setattr(
            launcher._registry_reconcile,
            "run",
            mismatched_registry,
        )
    elif bad == "target":
        monkeypatch.setattr(
            launcher, "_preflight", lambda: {**IDENTITY, "source_sha": "b" * 40}
        )
    elif bad == "receipt":
        monkeypatch.setattr(
            launcher,
            "_approved_receipt",
            rejected_receipt,
        )
    else:
        monkeypatch.setattr(launcher, "_active_instance", invalid_instance)
    monkeypatch.setattr(launcher, "_run", unexpected_ssh)

    result = cast(dict[str, object], launcher.run())

    assert str(result["result"]).startswith("FAIL_")
    assert_sanitized_result(result)


@pytest.mark.parametrize(
    "outcome",
    (
        subprocess.CompletedProcess(["railway", "ssh"], 1, None, PRIVATE),
        subprocess.CompletedProcess(["railway", "ssh"], 0, None, PRIVATE),
        subprocess.TimeoutExpired("railway ssh", 120, output=PRIVATE),
    ),
)
def test_uncertain_transport_is_sanitized_and_never_retried(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    """AC-2: a remote success marker cannot turn teardown uncertainty into PASS."""
    green_guards(launcher, monkeypatch)
    attempts = 0

    def execute(argv: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return cast(subprocess.CompletedProcess[str], outcome)

    monkeypatch.setattr(launcher, "_run", execute)
    result = cast(dict[str, object], launcher.run())

    assert result["result"] == "FAIL_TRANSPORT_UNCERTAIN"
    assert attempts == 1
    assert_sanitized_result(result)


def test_real_source_bundle_bootstrap_loads_rotation_module_and_dispatches(
    launcher: ModuleType,
) -> None:
    """AC-1: execute actual bootstrap imports with only DB guards and write stubbed."""
    sources = launcher._reviewed_source()
    inspector_source = cast(str, sources["inspector"]["source"])
    rotation_source = cast(str, sources["rotation_command"]["source"])
    assert inspector_source == (
        ROOT / "scripts/api_staging_operator_inspect.py"
    ).read_text(encoding="utf-8")
    assert rotation_source == COMMAND_PATH.read_text(encoding="utf-8")

    # Keep every real import and class definition. Replace only the runtime
    # target/DB guards and the final write-bearing execute call in this child.
    inspector_source += f"""
def _valid_expected_identity(source_sha, deployment_id): return True
def _target_identity_matches(source_sha, deployment_id): return True
def _bootstrap():
    import contextlib, os, sys, django
    sys.path.insert(0, {str(ROOT / "services/api")!r})
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.local'
    django.setup()
    from django.db import connection, transaction
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql):
            if sql != 'SET TRANSACTION READ ONLY': raise AssertionError
    connection.cursor = lambda: Cursor()
    transaction.atomic = contextlib.nullcontext
def _inspect_orm_preconditions(): return 'PASS'
"""
    rotation_source += """
def _test_execute(self, *args, **kwargs):
    if kwargs.get('expected_identity', {}).get('environment') != 'staging':
        raise AssertionError
    print('TEST_ROTATION_EXECUTE_REACHED')
Command.execute = _test_execute
"""
    for name, source in (
        ("inspector", inspector_source),
        ("rotation_command", rotation_source),
    ):
        sources[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    request = json.dumps({"identity": IDENTITY, "sources": sources})
    environment = dict(os.environ)
    environment["DJANGO_SECRET_KEY"] = "local-bootstrap-test-only"
    environment["DATABASE_URL"] = "postgresql://local:local@127.0.0.1/local"
    completed = subprocess.run(
        [sys.executable, "-I", "-c", cast(str, launcher._BOOTSTRAP), request],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "TEST_ROTATION_EXECUTE_REACHED",
        "TAILTAG_MANAGED_PASSWORD_ROTATION_COMPLETED",
    ]
    assert completed.stderr == ""
