"""Behavioral contract for the guarded authenticated API smoke orchestration."""

from __future__ import annotations

import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_auth_smoke as auth_smoke

VALID_ENVIRONMENT = {
    "API_BASE_URL": "http://127.0.0.1:8000",
    "CLERK_SMOKE_USER_ID": "user_synthetic",
}
SENSITIVE_VALUES = (
    "sk_test_synthetic_credential_material",
    "ticket_synthetic_sensitive_material",
    "eyJsynthetic.header.payload",
    "user_synthetic_sensitive_identifier",
    "sess_synthetic_sensitive_identifier",
    '"private_claim":"synthetic-sensitive-value"',
)


class SensitiveSyntheticError(Exception):
    """An untrusted boundary failure containing only synthetic material."""


class RecordingSession:
    def __init__(
        self,
        events: list[str],
        *,
        token_error: BaseException | None = None,
        cleanup_error: BaseException | None = None,
    ) -> None:
        self._events = events
        self._token_error = token_error
        self._cleanup_error = cleanup_error

    def create_verified_token(self) -> str:
        self._events.append("provider-create-token")
        if self._token_error is not None:
            raise self._token_error
        return "eyJsynthetic.header.payload"

    def cleanup(self) -> None:
        self._events.append("cleanup")
        if self._cleanup_error is not None:
            raise self._cleanup_error


class RecordingRuntime:
    """Fully offline stand-in for the three orchestration boundaries."""

    def __init__(
        self,
        *,
        baseline_result: bool = True,
        validation_error: BaseException | None = None,
        token_error: BaseException | None = None,
        api_me_error: BaseException | None = None,
        cleanup_error: BaseException | None = None,
    ) -> None:
        self.events: list[str] = []
        self.baseline_result = baseline_result
        self.validation_error = validation_error
        self.token_error = token_error
        self.api_me_error = api_me_error
        self.cleanup_error = cleanup_error

    def run_baseline(self, *, base_url: str) -> bool:
        self.events.append(f"baseline:{base_url}")
        return self.baseline_result

    def prompt_secret(self) -> str:
        self.events.append("prompt")
        return "sk_test_synthetic_credential_material"

    def validate_clerk(self, *, secret: str, user_id: str) -> RecordingSession:
        self.events.append("provider-validate")
        assert secret == "sk_test_synthetic_credential_material"
        assert user_id == "user_synthetic"
        if self.validation_error is not None:
            raise self.validation_error
        return RecordingSession(
            self.events,
            token_error=self.token_error,
            cleanup_error=self.cleanup_error,
        )

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        self.events.append("api-me")
        assert base_url == "http://127.0.0.1:8000"
        assert bearer_token == "eyJsynthetic.header.payload"
        if self.api_me_error is not None:
            raise self.api_me_error


def assert_sanitized(outcome: object) -> None:
    rendered = repr(outcome)
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    ("environment", "expected"),
    (
        ({}, "http://127.0.0.1:8000"),
        ({"API_BASE_URL": "http://127.0.0.1:8000"}, "http://127.0.0.1:8000"),
        ({"API_BASE_URL": "http://127.0.0.1:8000/"}, "http://127.0.0.1:8000"),
        (
            {
                "API_BASE_URL": "https://development.tailtag.example/",
                "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example/",
            },
            "https://development.tailtag.example",
        ),
    ),
)
def test_target_policy_accepts_only_the_default_or_exact_development_root(
    environment: Mapping[str, str], expected: str
) -> None:
    assert auth_smoke.validate_api_target(environment) == expected


DISALLOWED_TARGETS = (
    {"API_BASE_URL": ""},
    {"API_BASE_URL": "http://localhost:8000"},
    {"API_BASE_URL": "http://[::1]:8000"},
    {"API_BASE_URL": "http://127.0.0.1:8000//"},
    {"API_BASE_URL": "http://127.0.0.1:8000/path"},
    {"API_BASE_URL": "http://127.0.0.1:8000?x=1"},
    {"API_BASE_URL": "http://127.0.0.1:8000#fragment"},
    {
        "API_BASE_URL": "https://user:password@development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "http://development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "HTTPS://development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example:443",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example.evil",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example/%2e",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example/path",
    },
    {"TAILTAG_DEVELOPMENT_API_BASE_URL": "http://development.tailtag.example"},
    {"TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example?x=1"},
)


@pytest.mark.parametrize("environment", DISALLOWED_TARGETS)
def test_disallowed_target_stops_before_baseline_prompt_or_provider(
    environment: Mapping[str, str],
) -> None:
    runtime = RecordingRuntime()

    outcome = auth_smoke.run(environment, runtime)

    assert outcome.primary_stage == "target configuration invalid"
    assert not outcome.cleanup_incomplete
    assert not outcome.succeeded
    assert runtime.events == []


def test_baseline_precedes_prompt_and_provider() -> None:
    runtime = RecordingRuntime()

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert runtime.events == [
        "baseline:http://127.0.0.1:8000",
        "prompt",
        "provider-validate",
        "provider-create-token",
        "api-me",
        "cleanup",
    ]


def test_unsuccessful_baseline_never_prompts_or_contacts_provider() -> None:
    runtime = RecordingRuntime(baseline_result=False)

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage == "baseline smoke unsuccessful"
    assert runtime.events == ["baseline:http://127.0.0.1:8000"]


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_events"),
    (
        (
            "validation",
            "Clerk instance not validated as Development",
            ["baseline:http://127.0.0.1:8000", "prompt", "provider-validate"],
        ),
        (
            "token",
            "provider session-token flow unsuccessful",
            [
                "baseline:http://127.0.0.1:8000",
                "prompt",
                "provider-validate",
                "provider-create-token",
                "cleanup",
            ],
        ),
        (
            "api",
            "authenticated API response invalid",
            [
                "baseline:http://127.0.0.1:8000",
                "prompt",
                "provider-validate",
                "provider-create-token",
                "api-me",
                "cleanup",
            ],
        ),
    ),
)
def test_sanitized_failure_categories_preserve_required_cleanup(
    failure: str, expected_stage: str, expected_events: list[str]
) -> None:
    error = SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))
    runtime = RecordingRuntime(
        validation_error=error if failure == "validation" else None,
        token_error=error if failure == "token" else None,
        api_me_error=error if failure == "api" else None,
    )

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage == expected_stage
    assert not outcome.succeeded
    assert runtime.events == expected_events
    assert_sanitized(outcome)


def test_primary_and_cleanup_failures_are_both_sanitized() -> None:
    error = SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))
    runtime = RecordingRuntime(api_me_error=error, cleanup_error=error)

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage == "authenticated API response invalid"
    assert outcome.cleanup_incomplete
    assert not outcome.succeeded
    assert runtime.events[-2:] == ["api-me", "cleanup"]
    assert_sanitized(outcome)


def test_cleanup_failure_alone_makes_an_otherwise_valid_run_unsuccessful() -> None:
    runtime = RecordingRuntime(cleanup_error=SensitiveSyntheticError("cleanup"))

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage is None
    assert outcome.cleanup_incomplete
    assert not outcome.succeeded


def test_orchestration_uses_no_network_when_every_boundary_is_fake(
    monkeypatch: MonkeyPatch,
) -> None:
    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("ordinary authenticated smoke tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)

    outcome = auth_smoke.run(VALID_ENVIRONMENT, RecordingRuntime())

    assert outcome.succeeded
