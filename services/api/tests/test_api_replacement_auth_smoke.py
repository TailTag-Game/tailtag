"""Offline acceptance tests for the two-environment replacement auth smoke."""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Self

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_replacement_auth_smoke as smoke

ORIGINS = {
    "development": "https://development.example.invalid",
    "staging": "https://staging.example.invalid",
}
TOKENS = {
    "development": "synthetic-development-token-private",
    "staging": "synthetic-staging-token-private",
}
SENSITIVE = (
    *TOKENS.values(),
    "synthetic-private-user-id",
    "synthetic-sensitive-response",
    "synthetic-private-origin",
)


class BoundaryError(Exception):
    """An untrusted failure containing synthetic secret material."""


class RecordingRuntime:
    """The approved narrow test seam; no network or provider admin operations."""

    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []
        self.origins: dict[str, str] = dict(ORIGINS)
        self.identity: dict[str, dict[str, str]] = {
            name: {
                "environment": name,
                "source_sha": "a" * 40,
                "deployment_id": "00000000-0000-4000-8000-000000000001",
            }
            for name in ORIGINS
        }
        self.responses: dict[tuple[str, str], tuple[int, bytes, str]] = {
            ("development", "development"): (
                200,
                b'{"id":1}',
                f"{ORIGINS['development']}/api/me/",
            ),
            ("development", "staging"): (
                401,
                b'{"detail":"Authentication credentials were not provided."}',
                f"{ORIGINS['staging']}/api/me/",
            ),
            ("staging", "staging"): (
                200,
                b'{"id":2}',
                f"{ORIGINS['staging']}/api/me/",
            ),
            ("staging", "development"): (
                401,
                b'{"detail":"Authentication credentials were not provided."}',
                f"{ORIGINS['development']}/api/me/",
            ),
        }
        self.fail_at: str | None = None

    def load_origins(self) -> dict[str, str]:
        self.events.append(("origins",))
        if self.fail_at == "origins":
            raise BoundaryError(SENSITIVE[0])
        return dict(self.origins)

    def preflight(self, *, environment: str, origin: str) -> dict[str, str]:
        self.events.append(("preflight", environment, origin))
        if self.fail_at == f"preflight-{environment}":
            raise BoundaryError(SENSITIVE[1])
        return dict(self.identity[environment])

    def prompt_token(self, *, environment: str) -> str:
        self.events.append(("prompt", environment))
        if self.fail_at == f"prompt-{environment}":
            raise BoundaryError(SENSITIVE[0])
        return TOKENS[environment]

    def request_me(self, *, origin: str, token: str) -> tuple[int, bytes, str]:
        source = next(name for name, value in TOKENS.items() if value == token)
        target = next(name for name, value in ORIGINS.items() if value == origin)
        self.events.append(("request", source, target))
        if self.fail_at == f"request-{source}-{target}":
            raise BoundaryError(SENSITIVE[2])
        return self.responses[(source, target)]


def assert_sanitized(outcome: Any, capsys: pytest.CaptureFixture[str]) -> None:
    captured = capsys.readouterr()
    rendered = repr(outcome) + captured.out + captured.err
    for value in SENSITIVE:
        assert value not in rendered


def test_success_preflights_both_targets_before_secret_prompts_and_requests_exact_matrix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RecordingRuntime()

    outcome = smoke.run(runtime)

    assert outcome.succeeded
    assert runtime.events == [
        ("origins",),
        ("preflight", "development", ORIGINS["development"]),
        ("preflight", "staging", ORIGINS["staging"]),
        ("prompt", "development"),
        ("request", "development", "development"),
        ("request", "development", "staging"),
        ("prompt", "staging"),
        ("request", "staging", "staging"),
        ("request", "staging", "development"),
    ]
    assert_sanitized(outcome, capsys)


@pytest.mark.parametrize(
    ("replacement", "failure_source"),
    [
        ((200, b'{"id":1}', f"{ORIGINS['staging']}/api/me/"), "development"),
        ((302, b"", "https://redirect.example.invalid/api/me/"), "development"),
        ((401, b'{"id":1}', f"{ORIGINS['development']}/api/me/"), "development"),
        ((200, b'{"id":true}', f"{ORIGINS['development']}/api/me/"), "development"),
        (
            (200, b'{"id":1,"extra":2}', f"{ORIGINS['development']}/api/me/"),
            "development",
        ),
        (
            (
                200,
                b'{"id":"synthetic-private-user-id"}',
                f"{ORIGINS['development']}/api/me/",
            ),
            "development",
        ),
        (
            (200, b"synthetic-sensitive-response", f"{ORIGINS['development']}/api/me/"),
            "development",
        ),
    ],
)
def test_own_target_rejects_wrong_status_redirect_or_malformed_body(
    replacement: tuple[int, bytes, str],
    failure_source: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RecordingRuntime()
    runtime.responses[(failure_source, failure_source)] = replacement

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == "authenticated API"
    assert ("request", failure_source, "staging") not in runtime.events
    assert_sanitized(outcome, capsys)


@pytest.mark.parametrize(
    "status,body",
    [
        (200, b'{"id":1}'),
        (403, b'{"detail":"synthetic-sensitive-response"}'),
        (302, b""),
    ],
)
def test_cross_target_requires_exact_401_and_stops_before_next_request(
    status: int, body: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = RecordingRuntime()
    runtime.responses[("development", "staging")] = (
        status,
        body,
        f"{ORIGINS['staging']}/api/me/",
    )

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == "authenticated API"
    assert ("request", "staging", "staging") not in runtime.events
    assert_sanitized(outcome, capsys)


def test_second_cross_target_is_checked_and_cannot_be_permissive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RecordingRuntime()
    runtime.responses[("staging", "development")] = (
        200,
        b'{"id":2}',
        f"{ORIGINS['development']}/api/me/",
    )

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == "authenticated API"
    assert runtime.events[-1] == ("request", "staging", "development")
    assert_sanitized(outcome, capsys)


@pytest.mark.parametrize(
    "bad_origins",
    [
        {
            "development": "http://development.example.invalid",
            "staging": ORIGINS["staging"],
        },
        {"development": ORIGINS["staging"], "staging": ORIGINS["staging"]},
        {
            "development": ORIGINS["development"],
            "staging": "https://staging.example.invalid/api",
        },
    ],
)
def test_target_configuration_fails_before_prompt(
    bad_origins: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = RecordingRuntime()
    runtime.origins = bad_origins

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == "target"
    assert not any(event[0] == "prompt" for event in runtime.events)
    assert_sanitized(outcome, capsys)


def test_preflight_environment_mismatch_fails_before_prompt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = RecordingRuntime()
    runtime.identity["staging"]["environment"] = "development"

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == "target"
    assert not any(event[0] == "prompt" for event in runtime.events)
    assert_sanitized(outcome, capsys)


@pytest.mark.parametrize(
    "phase,expected_stage",
    [
        ("origins", "target"),
        ("preflight-development", "target"),
        ("preflight-staging", "target"),
        ("prompt-development", "hidden input"),
        ("prompt-staging", "hidden input"),
        ("request-development-development", "authenticated API"),
        ("request-development-staging", "authenticated API"),
    ],
)
def test_untrusted_boundary_failures_have_fixed_sanitized_outcomes(
    phase: str, expected_stage: str, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime = RecordingRuntime()
    runtime.fail_at = phase

    outcome = smoke.run(runtime)

    assert not outcome.succeeded
    assert outcome.failure_stage == expected_stage
    assert_sanitized(outcome, capsys)


def test_no_token_is_requested_when_second_target_preflight_fails() -> None:
    runtime = RecordingRuntime()
    runtime.fail_at = "preflight-staging"

    smoke.run(runtime)

    assert not any(event[0] == "prompt" for event in runtime.events)
    assert not any(event[0] == "request" for event in runtime.events)


def test_default_prompt_refuses_non_tty_without_requesting_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NotATerminal:
        def isatty(self) -> bool:
            return False

    def forbidden_prompt(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("non-TTY input must stop before a password prompt")

    monkeypatch.setattr(sys, "stdin", NotATerminal())
    monkeypatch.setattr(sys, "stderr", NotATerminal())
    monkeypatch.setattr(smoke.getpass, "getpass", forbidden_prompt)

    with pytest.raises(smoke.SmokeFailure) as failure:
        smoke.DefaultSmokeRuntime().prompt_token(environment="development")

    assert "synthetic" not in str(failure.value)


def test_command_module_imports_from_repository_root_without_output() -> None:
    """The operator invocation resolves its module before any live boundary is used."""
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.api_replacement_auth_smoke"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize("http_error", [False, True])
def test_concrete_http_adapter_is_direct_bounded_and_does_not_echo_secrets(
    http_error: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both normal and denied HTTP responses use the same safe transport."""

    class BoundedBody(BytesIO):
        def read(self, size: int = -1) -> bytes:
            assert size == 4097
            return super().read(size)

    class Response:
        def __init__(self, url: str) -> None:
            self.url = url
            self.body = BoundedBody(b"synthetic-sensitive-response")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def geturl(self) -> str:
            return self.url

        def read(self, size: int = -1) -> bytes:
            return self.body.read(size)

    class Opener:
        def __init__(self) -> None:
            self.requests: list[tuple[urllib.request.Request, object]] = []

        def open(self, request: urllib.request.Request, *, timeout: object) -> Response:
            self.requests.append((request, timeout))
            if http_error:
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "synthetic-sensitive-response",
                    {},
                    BoundedBody(b"synthetic-sensitive-response"),
                )
            return Response(request.full_url)

    opener = Opener()
    handlers: list[object] = []

    def build_opener(*configured: object) -> Opener:
        handlers.extend(configured)
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    status, body, final_url = smoke.DefaultSmokeRuntime().request_me(
        origin=ORIGINS["development"], token=TOKENS["development"]
    )

    assert status == (401 if http_error else 200)
    assert body == b"synthetic-sensitive-response"
    assert final_url == f"{ORIGINS['development']}/api/me/"
    assert len(opener.requests) == 1
    request, timeout = opener.requests[0]
    assert request.full_url == final_url
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == f"Bearer {TOKENS['development']}"
    assert timeout == 5
    proxy_handlers = [
        handler
        for handler in handlers
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}
    redirect_handlers = [
        handler
        for handler in handlers
        if isinstance(handler, urllib.request.HTTPRedirectHandler)
    ]
    assert len(redirect_handlers) == 1
    assert redirect_handlers[0].redirect_request(None, None, 302, "", {}, "") is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
