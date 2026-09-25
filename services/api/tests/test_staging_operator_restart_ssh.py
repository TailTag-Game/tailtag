"""External-boundary tests for the exact-instance #243 operator restart launcher."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

IDENTITY = {
    "environment": "staging",
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
}
PROJECT = "a1111111-1111-4111-8111-111111111111"
ENVIRONMENT = "c3333333-3333-4333-8333-333333333333"
SERVICE = "d4444444-4444-4444-8444-444444444444"
POSTGRES = "e5555555-5555-4555-8555-555555555555"
INSTANCE = "22222222-2222-4222-8222-222222222222"
PRIVATE = "private-credential-or-provider-detail-243"
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Terminal(StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def runner() -> ModuleType:
    return importlib.import_module("scripts.api_staging_operator_restart_ssh")


def inspector_result() -> dict[str, object]:
    return {
        "result": "PASS",
        "phase": "exact_instance_inspector",
        "identity": dict(IDENTITY),
        "target_verified": True,
        "window_utc": ["2026-09-25T00:00:00Z", "2026-09-25T00:00:01Z"],
    }


def registry_result() -> dict[str, object]:
    from scripts.api_staging_registry_reconcile import (
        _CHECKS,  # pyright: ignore[reportPrivateUsage]
    )

    structural = {"registry_singleton", "registry_structure", "root_completeness"}
    return {
        "result": "PASS",
        "checks": {name: "PASS" if name in structural else "MATCH" for name in _CHECKS},
    }


def install_green_guards(runner: ModuleType, patch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def mark(name: str) -> None:
        calls.append(name)

    def preflight() -> dict[str, str]:
        mark("preflight")
        return dict(IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == IDENTITY
        mark("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == IDENTITY
        mark("instance")
        return INSTANCE

    def registry(_path: Path) -> dict[str, object]:
        mark("registry")
        return registry_result()

    def binding_request(identity: dict[str, str]) -> dict[str, object]:
        assert identity == IDENTITY
        mark("database_binding")
        return {
            "identity": dict(identity),
            "database_url_fingerprint": "b" * 64,
            "database_facts_fingerprint": "c" * 64,
        }

    def forbid_provider_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Restart launcher test reached a real provider subprocess")

    patch.setattr(runner.sys, "stdin", Terminal())
    patch.setattr(runner.sys, "stdout", Terminal())
    patch.setattr(subprocess, "run", forbid_provider_call)
    patch.setattr(runner, "_github_identity", lambda: mark("github"))
    patch.setattr(
        runner._inspector, "run", lambda: (mark("inspector"), inspector_result())[1]
    )
    patch.setattr(runner, "_railway_identity", lambda: mark("railway"))
    patch.setattr(runner, "_preflight", preflight)
    patch.setattr(runner, "_approved_receipt", receipt)
    patch.setattr(runner, "_active_instance", instance)
    patch.setattr(
        runner, "_target_ids", lambda: (PROJECT, ENVIRONMENT, SERVICE, POSTGRES)
    )
    patch.setattr(runner._registry_reconcile, "run", registry)
    patch.setattr(runner._emergency, "_binding_request", binding_request)

    return calls


def assert_sanitized(result: dict[str, object]) -> None:
    assert result["identity"] in (None, IDENTITY)
    assert isinstance(result["window_utc"], list)
    assert PRIVATE not in json.dumps(result)
    assert INSTANCE not in json.dumps(result)


def test_fresh_guards_pin_one_exact_instance_ssh_attempt(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4: no write starts until inspector, registry, receipt and instance agree."""
    calls = install_green_guards(runner, monkeypatch)
    attempts: list[list[str]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append("ssh")
        attempts.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)
    result = cast(dict[str, object], runner.run())

    assert_sanitized(result)
    assert result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED"
    assert len(attempts) == 1
    assert calls.index("github") < calls.index("inspector")
    assert calls.index("inspector") < calls.index("registry") < calls.index("ssh")
    assert calls.index("receipt") < calls.index("instance") < calls.index("ssh")
    assert calls.index("database_binding") < calls.index("ssh")
    assert calls.count("preflight") >= 2
    arguments = attempts[0]
    assert arguments[:2] == ["railway", "ssh"]
    assert arguments[arguments.index("--project") + 1] == PROJECT
    assert arguments[arguments.index("--environment") + 1] == ENVIRONMENT
    assert arguments[arguments.index("--service") + 1] == SERVICE
    assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
    assert PRIVATE not in " ".join(arguments)


@pytest.mark.parametrize("failed_guard", ("receipt", "instance", "repeat_preflight"))
def test_failed_target_guard_never_starts_restart(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failed_guard: str,
) -> None:
    """AC-1/4: a stale receipt or changed running instance blocks mutation."""
    calls = install_green_guards(runner, monkeypatch)
    if failed_guard == "receipt":

        def reject_receipt(_identity: dict[str, str]) -> None:
            raise ValueError(PRIVATE)

        monkeypatch.setattr(runner, "_approved_receipt", reject_receipt)
    elif failed_guard == "instance":

        def wrong_instance(_identity: dict[str, str]) -> str:
            return "not-an-instance"

        monkeypatch.setattr(runner, "_active_instance", wrong_instance)
    else:
        reads = 0

        def changing_preflight() -> dict[str, str]:
            nonlocal reads
            reads += 1
            return (
                dict(IDENTITY) if reads == 1 else {**IDENTITY, "source_sha": "b" * 40}
            )

        monkeypatch.setattr(runner, "_preflight", changing_preflight)
    attempts: list[list[str]] = []

    def record_attempt(arguments: list[str]) -> None:
        attempts.append(arguments)

    monkeypatch.setattr(runner, "_run", record_attempt)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert_sanitized(result)
    assert attempts == []
    assert "ssh" not in calls


@pytest.mark.parametrize("failure", ("nonzero", "timeout", "os_error"))
def test_transport_failure_is_uncertain_and_never_retried(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """AC-4: after possible mutation, transport failure cannot imply rollback."""
    install_green_guards(runner, monkeypatch)
    attempts: list[list[str]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        attempts.append(arguments)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(arguments, 1, output=PRIVATE)
        if failure == "os_error":
            raise OSError(PRIVATE)
        return subprocess.CompletedProcess(arguments, 1, None, PRIVATE)

    monkeypatch.setattr(runner, "_run", execute)
    result = cast(dict[str, object], runner.run())

    assert result["result"] == "FAIL_TRANSPORT_UNCERTAIN"
    assert result["phase"] == "interactive_ssh"
    assert_sanitized(result)
    assert len(attempts) == 1


def test_cli_exit_zero_without_machine_verified_marker_is_nonzero(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: a plain SSH exit leaves manual witness and readback pending."""
    monkeypatch.setattr(runner.sys, "argv", ["api_staging_operator_restart_ssh"])
    monkeypatch.setattr(
        runner,
        "run",
        lambda: {
            "result": "TRANSPORT_EXITED_ZERO_UNVERIFIED",
            "phase": "test",
            "identity": dict(IDENTITY),
            "window_utc": ["2026-09-25T00:00:00Z", "2026-09-25T00:00:01Z"],
        },
    )
    assert runner.main() != 0
