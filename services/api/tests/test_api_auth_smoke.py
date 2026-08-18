"""Behavioral contract for the guarded authenticated API smoke orchestration."""

from __future__ import annotations

import importlib
import json
import logging
import socket
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import NoReturn, Self

import httpx
import pytest
from _pytest.capture import CaptureResult
from _pytest.logging import LogCaptureFixture
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


@dataclass
class _ApiResponse:
    status: int
    body: bytes
    location: str | None = None
    url: str = ""

    def read(self) -> bytes:
        return self.body

    @property
    def headers(self) -> dict[str, str]:
        return {"Location": self.location} if self.location is not None else {}

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class RecordingApiOpener:
    """Injectable HTTP boundary for the concrete authenticated runtime."""

    def __init__(self, *responses: _ApiResponse) -> None:
        self.responses = list(responses)
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **_kwargs: object) -> _ApiResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the authenticated API adapter made an extra request")
        response = self.responses.pop(0)
        response.url = request.full_url
        return response


def json_response(body: object, *, status: int = 200) -> _ApiResponse:
    return _ApiResponse(status=status, body=json.dumps(body).encode())


def default_runtime(opener: RecordingApiOpener) -> object:
    """Use the public seam for the same concrete runtime selected by main()."""
    return auth_smoke.DefaultSmokeRuntime(opener=opener)


def prohibit_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """Every ordinary test must replace every external boundary explicitly."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("ordinary authenticated smoke tests must remain offline")

    import http.client
    import urllib.request

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


def assert_supported_outputs_are_sanitized(
    outcome: object,
    captured: CaptureResult[str],
    caplog: LogCaptureFixture,
    *rendered_exceptions: BaseException,
) -> None:
    rendered = "\n".join(
        (
            repr(outcome),
            captured.out,
            captured.err,
            caplog.text,
            *(f"{error!s}\n{error!r}" for error in rendered_exceptions),
        )
    )
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
    {"API_BASE_URL": "http://127.0.0.1:8001"},
    {"API_BASE_URL": "http://localhost:8000"},
    {"API_BASE_URL": "http://localhost"},
    {"API_BASE_URL": "http://127.0.0.2:8000"},
    {"API_BASE_URL": "http://127.1:8000"},
    {"API_BASE_URL": "http://127.000.000.001:8000"},
    {"API_BASE_URL": "http://2130706433:8000"},
    {"API_BASE_URL": "http://0x7f000001:8000"},
    {"API_BASE_URL": "http://0177.0.0.1:8000"},
    {"API_BASE_URL": "http://[::1]:8000"},
    {"API_BASE_URL": "http://127.0.0.1:8000//"},
    {"API_BASE_URL": "http://127.0.0.1:8000/path"},
    {"API_BASE_URL": "http://127.0.0.1:8000?x=1"},
    {"API_BASE_URL": "http://127.0.0.1:8000#fragment"},
    {"API_BASE_URL": "http://127.0.0.1:8000?"},
    {"API_BASE_URL": "http://127.0.0.1:8000#"},
    {"API_BASE_URL": "http://127.0.0.1:8000\\path"},
    {"API_BASE_URL": " http://127.0.0.1:8000"},
    {"API_BASE_URL": "http://127.0.0.1:8000\n"},
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
        "API_BASE_URL": "https://development.tailtag.example/%2F",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development%2etailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://evildevelopment.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example//",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://development.tailtag.example",
    },
    {
        "API_BASE_URL": "https://development.tailtag.example",
        "TAILTAG_DEVELOPMENT_API_BASE_URL": "https://other-development.tailtag.example",
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


def test_default_api_me_boundary_accepts_only_the_exact_success_contract() -> None:
    opener = RecordingApiOpener(json_response({"id": 123}))
    runtime = default_runtime(opener)

    result = runtime.request_current_user(  # type: ignore[attr-defined]
        base_url="http://127.0.0.1:8000",
        bearer_token="eyJsynthetic.header.payload",
    )

    assert result is None
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == "http://127.0.0.1:8000/api/me/"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == ("Bearer eyJsynthetic.header.payload")


@pytest.mark.parametrize("status", (199, 201, 204, 299, 400, 500))
def test_default_api_me_boundary_rejects_every_non_200_status(status: int) -> None:
    opener = RecordingApiOpener(json_response({"id": 123}, status=status))
    runtime = default_runtime(opener)

    with pytest.raises(Exception) as raised:
        runtime.request_current_user(  # type: ignore[attr-defined]
            base_url="http://127.0.0.1:8000",
            bearer_token="eyJsynthetic.header.payload",
        )

    assert str(raised.value) == "authenticated API response invalid"
    assert len(opener.requests) == 1


@pytest.mark.parametrize("status", (301, 302, 303, 307, 308))
def test_default_api_me_boundary_never_follows_redirects(status: int) -> None:
    opener = RecordingApiOpener(
        _ApiResponse(
            status=status,
            body=b'{"id": 123}',
            location="https://unapproved.example/api/me/",
        ),
        json_response({"id": 123}),
    )
    runtime = default_runtime(opener)

    with pytest.raises(Exception) as raised:
        runtime.request_current_user(  # type: ignore[attr-defined]
            base_url="http://127.0.0.1:8000",
            bearer_token="eyJsynthetic.header.payload",
        )

    assert str(raised.value) == "authenticated API response invalid"
    assert len(opener.requests) == 1
    assert len(opener.responses) == 1


@pytest.mark.parametrize(
    "body",
    (
        {"id": True},
        {"id": "123"},
        {"id": 1.5},
        {"id": None},
        {"id": 123, "extra": "synthetic"},
        {},
        [123],
        None,
        123,
        "synthetic",
    ),
    ids=(
        "bool-id",
        "string-id",
        "float-id",
        "null-id",
        "extra-key",
        "missing-id",
        "array",
        "null",
        "number",
        "string-body",
    ),
)
def test_default_api_me_boundary_rejects_every_nonexact_json_body(
    body: object,
) -> None:
    opener = RecordingApiOpener(json_response(body))
    runtime = default_runtime(opener)

    with pytest.raises(Exception) as raised:
        runtime.request_current_user(  # type: ignore[attr-defined]
            base_url="http://127.0.0.1:8000",
            bearer_token="eyJsynthetic.header.payload",
        )

    assert str(raised.value) == "authenticated API response invalid"
    assert len(opener.requests) == 1


def test_default_api_me_boundary_rejects_malformed_json() -> None:
    opener = RecordingApiOpener(_ApiResponse(status=200, body=b'{"id":'))
    runtime = default_runtime(opener)

    with pytest.raises(Exception) as raised:
        runtime.request_current_user(  # type: ignore[attr-defined]
            base_url="http://127.0.0.1:8000",
            bearer_token="eyJsynthetic.header.payload",
        )

    assert str(raised.value) == "authenticated API response invalid"
    assert len(opener.requests) == 1


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
    failure: str,
    expected_stage: str,
    expected_events: list[str],
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
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
    assert_supported_outputs_are_sanitized(outcome, capsys.readouterr(), caplog, error)


def test_primary_and_cleanup_failures_are_both_sanitized(
    capsys: pytest.CaptureFixture[str], caplog: LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    error = SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))
    runtime = RecordingRuntime(api_me_error=error, cleanup_error=error)

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage == "authenticated API response invalid"
    assert outcome.cleanup_incomplete
    assert not outcome.succeeded
    assert runtime.events[-2:] == ["api-me", "cleanup"]
    assert_supported_outputs_are_sanitized(outcome, capsys.readouterr(), caplog, error)


def test_cleanup_failure_alone_makes_an_otherwise_valid_run_unsuccessful(
    capsys: pytest.CaptureFixture[str], caplog: LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    error = SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))
    runtime = RecordingRuntime(cleanup_error=error)

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage is None
    assert outcome.cleanup_incomplete
    assert not outcome.succeeded
    assert_supported_outputs_are_sanitized(outcome, capsys.readouterr(), caplog, error)


@dataclass
class _SuccessfulOutcome:
    succeeded: bool = True


def test_main_rejects_all_arguments_before_running_any_live_boundary(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[str] = []

    def run_if_called(*_: object, **__: object) -> _SuccessfulOutcome:
        calls.append("run")
        return _SuccessfulOutcome()

    monkeypatch.setattr(auth_smoke, "run", run_if_called)
    for argument in (
        "sk_test_synthetic_credential_material",
        "--secret=sk_test_synthetic_credential_material",
        "--key=sk_test_synthetic_credential_material",
        "--token",
        "--unknown-flag",
        "-x",
    ):
        monkeypatch.setattr(sys, "argv", ["api_auth_smoke.py", argument])
        assert auth_smoke.main() != 0

    assert calls == []


def test_main_uses_hidden_tty_prompt_with_exact_copy_and_never_echoes_secret(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    secret = "sk_test_synthetic_credential_material"

    class TtyStream(StringIO):
        def isatty(self) -> bool:
            return True

    def run_prompt_probe(
        _environment: Mapping[str, str], runtime: object
    ) -> _SuccessfulOutcome:
        prompt = runtime.prompt_secret  # type: ignore[attr-defined]
        calls.append(prompt())
        return _SuccessfulOutcome()

    def hidden_prompt(prompt: str, *, stream: object) -> str:
        calls.extend((prompt, stream))
        return secret

    import getpass

    monkeypatch.setattr(getpass, "getpass", hidden_prompt)
    fresh_module = importlib.reload(auth_smoke)
    monkeypatch.setattr(fresh_module, "run", run_prompt_probe)
    monkeypatch.setattr(sys, "argv", ["api_auth_smoke.py"])
    monkeypatch.setattr(sys, "stdin", TtyStream())
    monkeypatch.setattr(sys, "stderr", TtyStream())

    assert fresh_module.main() == 0
    assert calls[0] == secret
    assert calls[1] == "Clerk Development secret:"
    assert calls[2] is sys.stderr
    rendered = capsys.readouterr()
    assert secret not in rendered.out
    assert secret not in rendered.err


@pytest.mark.parametrize("stream_name", ("stdin", "stderr"))
def test_main_fails_closed_without_both_required_tty_streams(
    monkeypatch: MonkeyPatch, stream_name: str
) -> None:
    calls: list[str] = []

    class NonTty(StringIO):
        def isatty(self) -> bool:
            return False

    class TtyStream(StringIO):
        def isatty(self) -> bool:
            return True

    def run_prompt_probe(
        _environment: Mapping[str, str], runtime: object
    ) -> _SuccessfulOutcome:
        calls.append(runtime.prompt_secret())  # type: ignore[attr-defined]
        return _SuccessfulOutcome()

    monkeypatch.setattr(auth_smoke, "run", run_prompt_probe)
    monkeypatch.setattr(sys, "argv", ["api_auth_smoke.py"])
    other_stream_name = "stderr" if stream_name == "stdin" else "stdin"
    monkeypatch.setattr(sys, other_stream_name, TtyStream())
    monkeypatch.setattr(sys, stream_name, NonTty())

    assert auth_smoke.main() != 0
    assert calls == []


def test_main_never_accepts_a_secret_environment_value(
    monkeypatch: MonkeyPatch,
) -> None:
    observed: list[str] = []

    def run_prompt_probe(
        _environment: Mapping[str, str], runtime: object
    ) -> _SuccessfulOutcome:
        observed.append(runtime.prompt_secret())  # type: ignore[attr-defined]
        return _SuccessfulOutcome()

    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_synthetic_credential_material")

    class TtyStream(StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", TtyStream())
    monkeypatch.setattr(sys, "stderr", TtyStream())
    import getpass

    monkeypatch.setattr(
        getpass, "getpass", lambda _prompt, *, stream: "sk_test_prompt_only_value"
    )
    fresh_module = importlib.reload(auth_smoke)
    monkeypatch.setattr(fresh_module, "run", run_prompt_probe)
    monkeypatch.setattr(sys, "argv", ["api_auth_smoke.py"])

    assert fresh_module.main() == 0
    assert observed == ["sk_test_prompt_only_value"]


def test_orchestration_uses_no_network_when_every_boundary_is_fake() -> None:

    outcome = auth_smoke.run(VALID_ENVIRONMENT, RecordingRuntime())

    assert outcome.succeeded
