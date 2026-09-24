"""Exact-instance launcher tests for #243 managed password-only recovery."""

from __future__ import annotations

import importlib
import json
import subprocess
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.test_staging_managed_operator_replace_ssh import (
    IDENTITY,
    INSTANCE,
    inspector_result,
    registry_payload,
)

COMMAND_PATH = (
    Path(__file__).resolve().parents[3]
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
    assert COMMAND_PATH.read_text(encoding="utf-8") in json.dumps(request)
    assert PRIVATE not in " ".join(argv)


@pytest.mark.parametrize("detached", ("stdin", "stdout"))
def test_detached_terminal_stops_before_any_provider_call(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    events = green_guards(launcher, monkeypatch)
    monkeypatch.setattr(launcher.sys, detached, StringIO())
    monkeypatch.setattr(launcher, "_run", lambda _argv: pytest.fail("SSH started"))
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
            lambda _path: registry_payload(mismatch=True),
        )
    elif bad == "target":
        monkeypatch.setattr(
            launcher, "_preflight", lambda: {**IDENTITY, "source_sha": "b" * 40}
        )
    elif bad == "receipt":
        monkeypatch.setattr(
            launcher,
            "_approved_receipt",
            lambda _identity: (_ for _ in ()).throw(ValueError(PRIVATE)),
        )
    else:
        monkeypatch.setattr(
            launcher, "_active_instance", lambda _identity: "not-an-instance"
        )
    monkeypatch.setattr(launcher, "_run", lambda _argv: pytest.fail("SSH started"))

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
