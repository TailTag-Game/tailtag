"""Behavioral contract for the guarded live media-storage smoke command."""

from __future__ import annotations

import http.client
import logging
import socket
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from _pytest.capture import CaptureResult
from _pytest.logging import LogCaptureFixture
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_media_storage_smoke as smoke

VALID_ENVIRONMENT = {
    "RAILWAY_ENVIRONMENT_NAME": "development",
    "RAILWAY_SERVICE_NAME": "api",
    "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": "run-r2-development-media-storage-smoke",
}
SENSITIVE_VALUES = (
    "r2-development-bucket-synthetic",
    "https://synthetic.r2.example/private?X-Amz-Signature=synthetic-signature",
    "AKIA_SYNTHETIC_ACCESS_KEY",
    "synthetic-secret-access-key",
    "images/123e4567-e89b-12d3-a456-426614174000.png",
    "synthetic-response-body",
    "X-Amz-Signature=synthetic-signature",
)


class SensitiveSyntheticError(Exception):
    """An external-boundary error whose content must never be rendered."""


class RecordingRuntime:
    """Offline fake for the live operation boundaries, including cleanup faults."""

    def __init__(
        self,
        *,
        failure: str | None = None,
        object_survives_delete: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.failure = failure
        self.object_survives_delete = object_survives_delete
        self.key = "images/123e4567-e89b-12d3-a456-426614174000.png"
        self.content = b"synthetic-canonical-image-content"
        self.url = (
            "https://synthetic.r2.example/private?"
            "X-Amz-Expires=600&X-Amz-Signature=synthetic-signature"
        )

    def _raise_when(self, stage: str) -> None:
        if self.failure == stage:
            raise SensitiveSyntheticError(
                "r2-development-bucket-synthetic "
                "AKIA_SYNTHETIC_ACCESS_KEY synthetic-secret-access-key "
                "https://synthetic.r2.example/private?"
                "X-Amz-Signature=synthetic-signature synthetic-response-body"
            )

    def create_key(self) -> str:
        self.events.append("create-key")
        self._raise_when("create-key")
        return self.key

    def canonical_content(self) -> bytes:
        self.events.append("canonical-content")
        self._raise_when("canonical-content")
        return self.content

    def upload(self, *, key: str, content: bytes) -> None:
        self.events.append("upload")
        assert key == self.key
        assert content == self.content
        self._raise_when("upload")

    def exists(self, *, key: str) -> bool:
        event = (
            "exists-after-delete" if "delete" in self.events else "exists-after-upload"
        )
        self.events.append(event)
        assert key == self.key
        self._raise_when(event)
        if event == "exists-after-upload":
            return self.failure != "missing-after-upload"
        return not self.object_survives_delete

    def presign_get(self, *, key: str, expires_in: int) -> str:
        self.events.append("presign")
        assert key == self.key
        assert expires_in == 600
        self._raise_when("presign")
        return self.url

    def fetch(self, *, url: str) -> bytes:
        self.events.append("fetch")
        assert url == self.url
        self._raise_when("fetch")
        return b"different-bytes" if self.failure == "byte-mismatch" else self.content

    def delete(self, *, key: str) -> None:
        self.events.append("delete")
        assert key == self.key
        self._raise_when("delete")


def prohibit_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """Every ordinary test must replace its external boundaries explicitly."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("ordinary media smoke tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", no_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    for client_type in (httpx.Client, httpx.AsyncClient):
        monkeypatch.setattr(client_type, "request", no_network)
        monkeypatch.setattr(client_type, "send", no_network)


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_outbound_network(monkeypatch)


def assert_sanitized(
    outcome: object,
    captured: CaptureResult[str],
    caplog: LogCaptureFixture,
    *errors: BaseException,
) -> None:
    """Ensure untrusted storage material cannot cross a supported boundary."""
    rendered = "\n".join(
        (
            repr(outcome),
            captured.out,
            captured.err,
            caplog.text,
            *(f"{error!s}\n{error!r}" for error in errors),
        )
    )
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "Development"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "API"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "worker"},
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
        {
            **VALID_ENVIRONMENT,
            "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": "yes",
        },
        {
            **VALID_ENVIRONMENT,
            "RAILWAY_ENVIRONMENT_NAME": (
                "development https://synthetic.r2.example/private?"
                "X-Amz-Signature=synthetic-signature"
            ),
        },
    ),
)
def test_invalid_or_non_development_target_stops_before_every_runtime_boundary(
    environment: Mapping[str, str],
) -> None:
    """Identity and fixed confirmation are exact, case-sensitive fail-closed guards."""
    runtime = RecordingRuntime()

    outcome = smoke.run(environment, runtime)

    assert not outcome.succeeded
    assert runtime.events == []


def test_successful_run_uses_only_the_required_order_and_exact_expiry() -> None:
    """The live path verifies the private object before and after its fixed-lifetime read."""
    runtime = RecordingRuntime()

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert runtime.events == [
        "create-key",
        "canonical-content",
        "upload",
        "exists-after-upload",
        "presign",
        "fetch",
        "delete",
        "exists-after-delete",
    ]
    assert parse_qs(urlsplit(runtime.url).query) == {
        "X-Amz-Expires": ["600"],
        "X-Amz-Signature": ["synthetic-signature"],
    }


def test_concrete_runtime_rejects_a_non_s3_default_storage(
    monkeypatch: MonkeyPatch,
) -> None:
    """The opt-in command cannot silently fall back to local or in-memory storage."""
    monkeypatch.setattr(smoke, "storages", {"default": object()})

    with pytest.raises(smoke.SmokeFailure):
        smoke.DefaultSmokeRuntime()


@pytest.mark.parametrize(
    "failure",
    (
        "canonical-content",
        "upload",
        "missing-after-upload",
        "presign",
        "fetch",
        "byte-mismatch",
    ),
)
def test_reachable_primary_failure_still_deletes_then_checks_absence(
    failure: str,
) -> None:
    """An allocated key always reaches both cleanup actions, regardless of primary failure."""
    runtime = RecordingRuntime(failure=failure)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[0] == "create-key"
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


@pytest.mark.parametrize("failure", ("delete", "exists-after-delete"))
def test_cleanup_errors_are_fatal_and_do_not_skip_the_independent_absence_check(
    failure: str,
) -> None:
    """Cleanup is not best effort: both operations run and either failure fails the smoke."""
    runtime = RecordingRuntime(failure=failure)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


def test_surviving_object_after_delete_is_a_fatal_smoke_result() -> None:
    """A successful delete call is insufficient until absence is independently confirmed."""
    runtime = RecordingRuntime(object_survives_delete=True)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


def test_main_rejects_arguments_and_invalid_target_before_constructing_runtime(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No CLI path, Django setup, or storage construction can bypass the guards."""
    constructed = False

    def fail_if_constructed() -> RecordingRuntime:
        nonlocal constructed
        constructed = True
        raise AssertionError("runtime construction must follow target validation")

    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", fail_if_constructed)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py", "--unsafe"])
    assert smoke.main() != 0
    assert not constructed

    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(
        smoke.os,
        "environ",
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
    )
    assert smoke.main() != 0
    assert not constructed
    captured = capsys.readouterr()
    assert "production" not in captured.out + captured.err


def test_main_output_is_fixed_stage_level_and_suppresses_hostile_storage_details(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """Operator output exposes only safe target/stage status, never boundary material."""
    runtime = RecordingRuntime(failure="fetch")
    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", lambda: runtime)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(smoke.os, "environ", VALID_ENVIRONMENT)
    caplog.set_level(logging.DEBUG)

    assert smoke.main() != 0

    captured = capsys.readouterr()
    assert "development/api" in captured.out + captured.err
    assert all(
        line.startswith(("PASS ", "FAIL "))
        for line in (captured.out + captured.err).splitlines()
        if line
    )
    assert_sanitized(smoke.run(VALID_ENVIRONMENT, runtime), captured, caplog)


def test_main_success_reports_only_safe_pass_stages(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live success reports the safe target and fixed successes, never object details."""
    runtime = RecordingRuntime()
    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", lambda: runtime)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(smoke.os, "environ", VALID_ENVIRONMENT)

    assert smoke.main() == 0

    output = capsys.readouterr().out
    assert "development/api" in output
    assert output.splitlines()
    assert all(line.startswith("PASS ") for line in output.splitlines() if line)
    for value in SENSITIVE_VALUES:
        assert value not in output
