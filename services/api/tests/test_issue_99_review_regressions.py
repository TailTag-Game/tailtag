"""Independent regressions for Issue #99 review remediation.

These tests exercise only offline, synthetic provider and HTTP boundaries.  They
deliberately retain no credentials and prohibit every real network path.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import urllib.request
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from _pytest.capture import CaptureResult
from clerk_backend_api.utils import RetryConfig
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_auth_smoke as auth_smoke
from scripts import clerk_development_session as development_session

_REAL_HTTPX_CLIENT = httpx.Client

SYNTHETIC_SECRET = "sk_test_synthetic_credential_material"
SYNTHETIC_USER = "user_synthetic_review_subject"
SYNTHETIC_TICKET = "ticket_synthetic_review_value"
SYNTHETIC_OLD_SESSION = "sess_synthetic_old"
SYNTHETIC_NEW_SESSION = "sess_synthetic_new"
SYNTHETIC_TOKEN = "token_synthetic_private_value"
SYNTHETIC_JWT = (
    "eyJhbGciOiJub25lIn0."
    "eyJzdWIiOiJ1c2VyX3N5bnRoZXRpY19yZXZpZXdfc3ViamVjdCIsInNpZCI6InNlc3Nfc3ludGhldGljX25ldyJ9."
)
SYNTHETIC_CLAIMS = (
    "decoded_claims_sub_user_synthetic_review_subject_sid_sess_synthetic_new"
)
DEFAULT_PRIMARY_FRONTEND_API_URL = "https://development-synthetic.clerk.accounts.dev"
MAX_DEVELOPMENT_BROWSER_ERROR_BODY_BYTES = 4096
FAPI_USER_AGENT = "TailTag-Issue-99-Development-Smoke"
FAPI_ACCEPT = "application/json"


def prohibit_network(monkeypatch: MonkeyPatch) -> None:
    """Fail instead of allowing an ordinary test to make an outbound request."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("Issue #99 regression tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_network(monkeypatch)


@dataclass
class _Metadata:
    environment_type: str = "development"


@dataclass
class _User:
    id: str = SYNTHETIC_USER


@dataclass
class _Domain:
    is_satellite: object
    frontend_api_url: object


@dataclass
class _Domains:
    data: object


@dataclass
class _Ticket:
    id: str = SYNTHETIC_TICKET
    token: object = "ticket_synthetic_one_use_credential"
    url: object = None


class _InstanceSettings:
    def get(self) -> _Metadata:
        return _Metadata()


class _Users:
    def get(self, *, user_id: str) -> _User:
        assert user_id == SYNTHETIC_USER
        return _User()


class _DomainsResource:
    def __init__(self, *, data: object, error: BaseException | None) -> None:
        self._data = data
        self._error = error

    def list(self, **_kwargs: object) -> _Domains:
        if self._error is not None:
            raise self._error
        return _Domains(self._data)


class _SignInTokens:
    def __init__(
        self,
        ticket: _Ticket,
        events: list[tuple[str, dict[str, object]]],
        create_error: BaseException | None = None,
    ) -> None:
        self._ticket = ticket
        self._events = events
        self._create_error = create_error
        self.create_calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _Ticket:
        self.create_calls.append(kwargs)
        if self._create_error is not None:
            raise self._create_error
        return self._ticket

    def revoke(self, **kwargs: object) -> None:
        self._events.append(("ticket", kwargs))


class _Sessions:
    def __init__(self, events: list[tuple[str, dict[str, object]]]) -> None:
        self._events = events

    def revoke(self, **kwargs: object) -> None:
        self._events.append(("session", kwargs))


class _Transport:
    """The documented test transport seam, limited to synthetic provider values."""

    def __init__(
        self,
        ticket: _Ticket,
        *,
        create_error: BaseException | None = None,
        domain_data: object | None = None,
        domains_error: BaseException | None = None,
    ) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.instance_settings = _InstanceSettings()
        self.users = _Users()
        self.sign_in_tokens = _SignInTokens(ticket, self.events, create_error)
        self.sessions = _Sessions(self.events)
        self.domains = _DomainsResource(
            data=(
                [
                    _Domain(True, "https://satellite-synthetic.invalid"),
                    _Domain(False, DEFAULT_PRIMARY_FRONTEND_API_URL),
                ]
                if domain_data is None
                else domain_data
            ),
            error=domains_error,
        )


def validated_session(
    ticket: _Ticket,
    *,
    create_error: BaseException | None = None,
    domain_data: object | None = None,
    domains_error: BaseException | None = None,
) -> tuple[development_session.ClerkDevelopmentSession, _Transport]:
    transport = _Transport(
        ticket,
        create_error=create_error,
        domain_data=domain_data,
        domains_error=domains_error,
    )
    session = development_session.ClerkDevelopmentSession.validate(
        secret=SYNTHETIC_SECRET,
        user_id=SYNTHETIC_USER,
        transport=transport,
    )
    return session, transport


class _FrontendPeer:
    def __init__(
        self,
        responses: dict[str, dict[str, object]],
    ) -> None:
        self._responses = responses
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.urls.append(str(request.url))
        try:
            payload = self._responses[path]
        except KeyError as error:
            raise AssertionError(f"unexpected FAPI path {path}") from error
        return httpx.Response(200, json=payload)


class _RequestCapturingFrontendPeer(_FrontendPeer):
    """Synthetic FAPI peer that retains each fixed request contract for inspection."""

    def __init__(self, responses: dict[str, dict[str, object]]) -> None:
        super().__init__(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return super().__call__(request)


def install_fapi_mock(
    monkeypatch: MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Client]:
    """Construct live-tool FAPI clients only at an offline native boundary."""
    clients: list[httpx.Client] = []

    def make_client(**kwargs: object) -> httpx.Client:
        client = _REAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(handler), **cast(Any, kwargs)
        )
        clients.append(client)
        return client

    monkeypatch.setattr(development_session.httpx, "Client", make_client)
    return clients


def token_failure_sensitive_material() -> str:
    """Synthetic redaction probes for the final provider request boundary."""
    return (
        f"{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} {SYNTHETIC_JWT} "
        f"{SYNTHETIC_USER} {SYNTHETIC_NEW_SESSION} {SYNTHETIC_CLAIMS}"
    )


class _FinalTokenFailurePeer:
    """Complete synthetic FAPI flow whose final token request is configurable."""

    def __init__(
        self,
        token_result: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        self._token_result = token_result
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        path = request.url.path
        if path == "/v1/dev_browser":
            return httpx.Response(200, json={"id": "dev_browser_synthetic"})
        if path == "/v1/client":
            return httpx.Response(200, json={"sessions": []})
        if path == "/v1/client/sign_ins":
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "complete",
                        "created_session_id": SYNTHETIC_NEW_SESSION,
                    },
                    "client": {
                        "sessions": [
                            {
                                "id": SYNTHETIC_NEW_SESSION,
                                "status": "active",
                                "user": {"id": SYNTHETIC_USER},
                            }
                        ]
                    },
                },
            )
        if path == f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens":
            return self._token_result(request)
        raise AssertionError(f"unexpected Frontend API path {path}")


class _OrchestrationRuntime:
    """Offline command boundary that exposes only one already-validated session."""

    def __init__(self, session: development_session.ClerkDevelopmentSession) -> None:
        self._session = session

    def run_baseline(self, *, base_url: str) -> bool:
        assert base_url == "http://127.0.0.1:8000"
        return True

    def prompt_secret(self) -> str:
        return SYNTHETIC_SECRET

    def validate_clerk(
        self, *, secret: str, user_id: str
    ) -> development_session.ClerkDevelopmentSession:
        assert secret == SYNTHETIC_SECRET
        assert user_id == SYNTHETIC_USER
        return self._session

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        raise AssertionError("failed ticket/session ownership must not call the API")


class _ValidationRuntime:
    """Offline runtime that exercises the command's real validation boundary."""

    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def run_baseline(self, *, base_url: str) -> bool:
        assert base_url == "http://127.0.0.1:8000"
        return True

    def prompt_secret(self) -> str:
        return SYNTHETIC_SECRET

    def validate_clerk(
        self, *, secret: str, user_id: str
    ) -> development_session.ClerkDevelopmentSession:
        return development_session.ClerkDevelopmentSession.validate(
            secret=secret,
            user_id=user_id,
            transport=self._transport,
        )

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        raise AssertionError("validation failure must not call the authenticated API")


def run_main_with_runtime(
    monkeypatch: MonkeyPatch, runtime: auth_smoke.SmokeRuntime
) -> int:
    """Exercise the command boundary with a fully offline runtime."""

    def default_runtime() -> auth_smoke.SmokeRuntime:
        return runtime

    monkeypatch.setattr(auth_smoke, "DefaultSmokeRuntime", default_runtime)
    monkeypatch.setattr(sys, "argv", ["api_auth_smoke.py"])
    monkeypatch.setenv("API_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("CLERK_SMOKE_USER_ID", SYNTHETIC_USER)
    monkeypatch.delenv("TAILTAG_DEVELOPMENT_API_BASE_URL", raising=False)
    return auth_smoke.main()


def run_main_with_session(
    monkeypatch: MonkeyPatch,
    session: development_session.ClerkDevelopmentSession,
) -> int:
    """Exercise the command's public stdout/stderr boundary with an offline session."""
    return run_main_with_runtime(monkeypatch, _OrchestrationRuntime(session))


def assert_fapi_failure_output_is_sanitized(
    captured: CaptureResult[str],
) -> None:
    rendered = captured.out + captured.err
    for sensitive_value in (
        SYNTHETIC_SECRET,
        SYNTHETIC_USER,
        SYNTHETIC_TICKET,
        "ticket_synthetic_one_use_credential",
        SYNTHETIC_OLD_SESSION,
        SYNTHETIC_NEW_SESSION,
        SYNTHETIC_TOKEN,
        SYNTHETIC_JWT,
        SYNTHETIC_CLAIMS,
        DEFAULT_PRIMARY_FRONTEND_API_URL,
        "https://development-synthetic.clerk.accounts.dev/sensitive-path",
        "raw_provider_body",
        "503",
    ):
        assert sensitive_value not in rendered


def assert_fapi_failure_logs_are_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    """Provider diagnostics remain absent from message and formatted log output."""
    rendered_messages = "\n".join(record.getMessage() for record in caplog.records)
    for sensitive_value in (
        SYNTHETIC_SECRET,
        SYNTHETIC_TICKET,
        SYNTHETIC_JWT,
        SYNTHETIC_USER,
        SYNTHETIC_NEW_SESSION,
        SYNTHETIC_CLAIMS,
    ):
        assert sensitive_value not in rendered_messages
        assert sensitive_value not in caplog.text


@pytest.mark.parametrize("fails", (False, True), ids=("success", "failure"))
def test_post_prompt_orchestration_suppresses_http_debug_logs_and_restores_states(
    caplog: pytest.LogCaptureFixture, fails: bool
) -> None:
    """One exception-safe boundary covers validation, token use, API call, and cleanup."""
    sensitive = "sk_test_orchestration sess_synthetic bearer.synthetic cookie=private"
    names = ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2")
    loggers = [logging.getLogger(name) for name in names]
    prior = [logger.disabled for logger in loggers]
    for logger in loggers:
        logger.disabled = False

    def emit() -> None:
        for logger in loggers:
            logger.debug(sensitive)

    class Session:
        def create_verified_token(self) -> str:
            emit()
            if fails:
                raise development_session.ClerkFlowFailure(
                    development_session.ClerkFlowStage.TICKET
                )
            return sensitive

        def cleanup(self) -> None:
            emit()

    class Runtime:
        def run_baseline(self, *, base_url: str) -> bool:
            assert base_url == "http://127.0.0.1:8000"
            return True

        def prompt_secret(self) -> str:
            return sensitive

        def validate_clerk(self, *, secret: str, user_id: str) -> Session:
            assert secret == sensitive and user_id == SYNTHETIC_USER
            emit()
            return Session()

        def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
            assert base_url == "http://127.0.0.1:8000" and bearer_token == sensitive
            emit()

    caplog.set_level(logging.DEBUG)
    try:
        outcome = auth_smoke.run(
            {"CLERK_SMOKE_USER_ID": SYNTHETIC_USER}, cast(Any, Runtime())
        )
    finally:
        for logger, disabled in zip(loggers, prior, strict=True):
            logger.disabled = disabled

    assert outcome.primary_stage in (None, "provider ticket flow unsuccessful")
    assert sensitive not in caplog.text
    assert all(sensitive not in record.getMessage() for record in caplog.records)
    assert [logger.disabled for logger in loggers] == prior


@pytest.mark.parametrize("api_fails", (False, True), ids=("api-success", "api-failure"))
def test_orchestration_releases_prompted_secret_and_bearer_after_their_last_use(
    api_fails: bool,
) -> None:
    """Weak references characterize prompt/token lifetime without exposing either value."""

    class SensitiveString(str):
        __slots__ = ("__weakref__",)

    secret = SensitiveString("sk_test_weak_secret")
    token = SensitiveString("bearer.weak.token")
    secret_ref = weakref.ref(secret)
    token_ref = weakref.ref(token)

    class Session:
        def create_verified_token(self) -> str:
            nonlocal secret
            secret = None  # type: ignore[assignment]
            import gc

            gc.collect()
            assert secret_ref() is None
            return cast(str, token)

        def cleanup(self) -> None:
            nonlocal token
            token = None  # type: ignore[assignment]
            import gc

            gc.collect()
            assert token_ref() is None

    class Runtime:
        def run_baseline(self, *, base_url: str) -> bool:
            return base_url == "http://127.0.0.1:8000"

        def prompt_secret(self) -> str:
            return cast(str, secret)

        def validate_clerk(self, *, secret: str, user_id: str) -> Session:
            assert user_id == SYNTHETIC_USER
            return Session()

        def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
            assert base_url == "http://127.0.0.1:8000" and bearer_token == cast(
                str, token
            )
            if api_fails:
                raise RuntimeError("synthetic api failure")

    outcome = auth_smoke.run(
        {"CLERK_SMOKE_USER_ID": SYNTHETIC_USER}, cast(Any, Runtime())
    )
    assert outcome.primary_stage in (None, "authenticated API response invalid")


def assert_final_token_failure_at_command_boundary(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    token_result: Callable[[httpx.Request], httpx.Response],
    expected_stage: str,
) -> None:
    """The completed ticket flow cleans up after one classified token failure."""
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    session, transport = validated_session(_Ticket())
    opener = _FinalTokenFailurePeer(token_result)

    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    for sensitive_value in (
        SYNTHETIC_SECRET,
        SYNTHETIC_TICKET,
        SYNTHETIC_JWT,
        SYNTHETIC_USER,
        SYNTHETIC_NEW_SESSION,
        SYNTHETIC_CLAIMS,
    ):
        assert sensitive_value not in rendered_logs
        assert sensitive_value not in caplog.text
    assert captured.err == f"FAIL {expected_stage}\n"
    assert [urlsplit(url).path for url in opener.urls] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens",
    ]
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def assert_pre_sign_in_protocol_failure_at_command_boundary(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    failure_path: str,
    error: BaseException,
    expected_stage: str,
) -> None:
    """Failures before ticket sign-in revoke only the known ticket resource."""
    session, transport = validated_session(_Ticket())

    class ProtocolFailureOpener:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            path = request.url.path
            if path == failure_path:
                raise error
            if path == "/v1/dev_browser":
                return httpx.Response(200, json={"id": "dev_browser_synthetic"})
            raise AssertionError(f"unexpected Frontend API path {path}")

    opener = ProtocolFailureOpener()

    caplog.set_level(logging.DEBUG)
    caplog.clear()
    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert_fapi_failure_logs_are_sanitized(caplog)
    assert captured.err == f"FAIL {expected_stage}\n"
    assert [urlsplit(url).path for url in opener.urls] == (
        ["/v1/dev_browser"]
        if failure_path == "/v1/dev_browser"
        else ["/v1/dev_browser", "/v1/client"]
    )
    assert transport.events == [
        ("ticket", {"sign_in_token_id": SYNTHETIC_TICKET}),
    ]


def test_actual_make_entry_point_imports_and_rejects_an_invalid_target_first() -> None:
    """The root command fails closed before baseline, prompting, or provider work."""
    environment = {
        **os.environ,
        "API_BASE_URL": "https://development.tailtag.example/forbidden-path",
        "CLERK_SMOKE_USER_ID": SYNTHETIC_USER,
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "ALL_PROXY": "http://127.0.0.1:1",
    }
    completed = subprocess.run(
        ["make", "api-auth-smoke"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    rendered = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "target configuration invalid" in rendered
    assert "interactive" not in rendered
    assert "ModuleNotFoundError" not in rendered
    assert "No module named" not in rendered


def test_verifier_request_surface_does_not_require_django_settings() -> None:
    """The unchanged verifier accepts the tooling's headers-only request surface."""
    source = """
import socket
import time

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings

assert not settings.configured

def no_network(*_args, **_kwargs):
    raise AssertionError("network forbidden in verifier request-surface regression")

socket.create_connection = no_network
httpx.Client.request = no_network
httpx.Client.send = no_network
httpx.AsyncClient.request = no_network
httpx.AsyncClient.send = no_network

from authentication.clerk import ClerkSessionVerifier
from scripts import clerk_development_session as development_session

user_id = "user_subprocess_verifier_subject"
session_id = "sess_subprocess_verifier_session"
now = int(time.time())
signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key_pem = signing_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
token = jwt.encode(
    {
        "sid": session_id,
        "sub": user_id,
        "azp": "http://localhost:3000",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 30,
        "iss": "https://development-synthetic.clerk.accounts.dev",
    },
    signing_key,
    algorithm="RS256",
    headers={"kid": "subprocess-key"},
)

assert development_session.ClerkSessionVerifier is ClerkSessionVerifier
development_session.ClerkDevelopmentSession._matching_jwk_pem = (
    lambda _session, _kid: public_key_pem
)
session = development_session.ClerkDevelopmentSession(
    _user_id=user_id,
    _transport=object(),
    _fapi_authority="https://development-synthetic.clerk.accounts.dev",
    _session_id=session_id,
)
session._validate_claims_and_verifier(token)
assert not settings.configured
print("verified")
"""
    environment = dict(os.environ)
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(REPOSITORY_ROOT)
        if not python_path
        else f"{REPOSITORY_ROOT}{os.pathsep}{python_path}"
    )

    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPOSITORY_ROOT / "services/api",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "verified\n"
    assert completed.stderr == ""


@pytest.mark.parametrize("port", (443, 8443))
def test_exact_remote_root_with_an_explicit_port_is_accepted_without_normalization(
    port: int,
) -> None:
    root = f"https://development.tailtag.example:{port}"

    assert (
        auth_smoke.validate_api_target(
            {
                "API_BASE_URL": f"{root}/",
                "TAILTAG_DEVELOPMENT_API_BASE_URL": root,
            }
        )
        == root
    )


@pytest.mark.parametrize(
    "target, configured",
    (
        (
            "https://development.tailtag.example:443",
            "https://development.tailtag.example",
        ),
        (
            "https://development.tailtag.example:8443",
            "https://development.tailtag.example:443",
        ),
    ),
)
def test_remote_root_port_mismatches_remain_rejected(
    target: str, configured: str
) -> None:
    with pytest.raises(Exception, match="target configuration invalid"):
        auth_smoke.validate_api_target(
            {
                "API_BASE_URL": target,
                "TAILTAG_DEVELOPMENT_API_BASE_URL": configured,
            }
        )


@pytest.mark.parametrize(
    ("target", "configured"),
    (
        (
            "https://development.tailtag.example:",
            "https://development.tailtag.example:",
        ),
        (
            "https://development.tailtag.example",
            "https://development.tailtag.example:",
        ),
    ),
    ids=("matching-empty-port", "configured-empty-port"),
)
def test_explicit_empty_remote_port_is_rejected_before_any_smoke_operation(
    target: str, configured: str
) -> None:
    """An empty HTTPS port is malformed, even when the comparator is identical."""

    class Runtime:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def run_baseline(self, *, base_url: str) -> bool:
            self.calls.append(f"baseline:{base_url}")
            raise AssertionError("invalid target must stop before baseline smoke")

        def prompt_secret(self) -> str:
            self.calls.append("prompt")
            raise AssertionError("invalid target must stop before the secret prompt")

        def validate_clerk(
            self, *, secret: str, user_id: str
        ) -> development_session.ClerkDevelopmentSession:
            self.calls.append(f"provider:{secret}:{user_id}")
            raise AssertionError("invalid target must stop before provider access")

        def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
            self.calls.append(f"api:{base_url}:{bearer_token}")
            raise AssertionError(
                "invalid target must stop before authenticated API use"
            )

    runtime = Runtime()
    outcome = auth_smoke.run(
        {
            "API_BASE_URL": target,
            "TAILTAG_DEVELOPMENT_API_BASE_URL": configured,
            "CLERK_SMOKE_USER_ID": SYNTHETIC_USER,
        },
        runtime,
    )

    assert outcome.primary_stage == "target configuration invalid"
    assert not outcome.cleanup_incomplete
    assert runtime.calls == []


def test_invalid_prompted_credential_reports_its_exact_sanitized_stage() -> None:
    """The early credential-form guard must not be rewritten as instance failure."""

    class Runtime:
        def run_baseline(self, *, base_url: str) -> bool:
            assert base_url == "http://127.0.0.1:8000"
            return True

        def prompt_secret(self) -> str:
            return "not-a-development-secret"

        def validate_clerk(
            self, *, secret: str, user_id: str
        ) -> development_session.ClerkDevelopmentSession:
            return development_session.ClerkDevelopmentSession.validate(
                secret=secret,
                user_id=user_id,
            )

        def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
            raise AssertionError("invalid credential must stop before API use")

    outcome = auth_smoke.run({"CLERK_SMOKE_USER_ID": SYNTHETIC_USER}, Runtime())

    assert outcome.primary_stage == "credential form invalid"
    assert not outcome.cleanup_incomplete


@pytest.mark.parametrize("ticket_token", (None, ""), ids=("absent", "empty"))
def test_sign_in_ticket_credential_unavailable_has_one_sanitized_public_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ticket_token: object,
) -> None:
    """A provider ticket ID alone cannot authorize a Frontend API exchange."""
    session, transport = validated_session(_Ticket(token=ticket_token))

    def prohibit_frontend_api(**_kwargs: object) -> httpx.Client:
        raise AssertionError("missing ticket credential must stop before Frontend API")

    monkeypatch.setattr(development_session.httpx, "Client", prohibit_frontend_api)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider sign-in-ticket credential unavailable\n"
    assert transport.events == [
        ("ticket", {"sign_in_token_id": SYNTHETIC_TICKET}),
    ]


@pytest.mark.parametrize(
    "domain_data",
    (
        [_Domain(True, "https://satellite-synthetic.invalid")],
        [_Domain(False, None)],
        [_Domain(False, "https://untrusted-synthetic.invalid/frontend")],
    ),
    ids=("absent", "null", "invalid"),
)
def test_primary_domain_authority_unavailable_has_one_sanitized_public_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    domain_data: object,
) -> None:
    """Only the validated primary domain may authorize the Frontend API."""
    transport = _Transport(_Ticket(), domain_data=domain_data)

    def prohibit_frontend_api(**_kwargs: object) -> httpx.Client:
        raise AssertionError("invalid primary domain must stop before Frontend API")

    monkeypatch.setattr(development_session.httpx, "Client", prohibit_frontend_api)

    assert run_main_with_runtime(monkeypatch, _ValidationRuntime(transport)) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider Frontend API authority unavailable\n"
    assert "satellite-synthetic.invalid" not in captured.err
    assert "untrusted-synthetic.invalid" not in captured.err
    assert transport.sign_in_tokens.create_calls == []
    assert transport.events == []


@pytest.mark.parametrize(
    "authority",
    (
        "https://development-synthetic.clerk.accounts.dev/non-root",
        "https://development-synthetic.clerk.accounts.dev//",
        "https://development-synthetic.clerk.accounts.dev?synthetic-query",
        "https://development-synthetic.clerk.accounts.dev#synthetic-fragment",
        "https://development-synthetic.clerk.accounts.dev?",
        "https://development-synthetic.clerk.accounts.dev#",
        " https://development-synthetic.clerk.accounts.dev",
        "https://development-synthetic.clerk.accounts.dev ",
        "https://development-synthetic.clerk.accounts.dev:",
        "https://development-synthetic.clerk.accounts.dev:/",
        "https://development-synthetic.clerk.\naccounts.dev",
        "https://development-synthetic.clerk.\taccounts.dev",
    ),
    ids=(
        "non-root-path",
        "multiple-trailing-slashes",
        "query",
        "fragment",
        "empty-query-delimiter",
        "empty-fragment-delimiter",
        "leading-whitespace",
        "trailing-whitespace",
        "empty-port",
        "empty-port-root-path",
        "embedded-newline",
        "embedded-tab",
    ),
)
def test_noncanonical_primary_authority_fails_before_ticket_creation(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    authority: str,
) -> None:
    """A primary FAPI authority is an exact HTTPS root, never a relative target."""
    transport = _Transport(_Ticket(), domain_data=[_Domain(False, authority)])

    assert run_main_with_runtime(monkeypatch, _ValidationRuntime(transport)) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider Frontend API authority unavailable\n"
    assert authority not in captured.err
    assert transport.sign_in_tokens.create_calls == []
    assert transport.events == []


@pytest.mark.parametrize(
    "authority",
    (DEFAULT_PRIMARY_FRONTEND_API_URL, f"{DEFAULT_PRIMARY_FRONTEND_API_URL}/"),
    ids=("root", "single-trailing-slash"),
)
def test_canonical_primary_authority_roots_are_accepted(authority: str) -> None:
    """The one optional root slash remains valid without normalizing authority."""
    transport = _Transport(_Ticket(), domain_data=[_Domain(False, authority)])

    session = development_session.ClerkDevelopmentSession.validate(
        secret=SYNTHETIC_SECRET,
        user_id=SYNTHETIC_USER,
        transport=transport,
    )

    assert session is not None
    assert transport.sign_in_tokens.create_calls == []
    assert transport.events == []


def assert_first_fapi_request_is_development_browser(request: httpx.Request) -> None:
    """The classified boundary is the fixed, bodyless dev-browser request."""
    assert request.url.path == "/v1/dev_browser"
    assert request.method == "POST"
    assert request.content == b""


def assert_development_browser_failure_cleanup(
    transport: _Transport,
    urls: list[str],
) -> None:
    """A first-call failure revokes its known ticket without creating a session."""
    assert [urlsplit(url).path for url in urls] == ["/v1/dev_browser"]
    assert len(transport.sign_in_tokens.create_calls) == 1
    assert transport.events == [
        ("ticket", {"sign_in_token_id": SYNTHETIC_TICKET}),
    ]


def development_browser_error_body(field: str, message: str) -> bytes:
    """Build an adversarial, Clerk-shaped diagnostic body without live provider data."""
    message_value = message if field == "message" else "unrelated provider detail"
    long_message_value = (
        message if field == "long_message" else "unrelated provider detail"
    )
    return (
        '{"errors": [{'
        f'"message": "{message_value} {SYNTHETIC_SECRET} {SYNTHETIC_TICKET} '
        f'{SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}", '
        f'"long_message": "{long_message_value} {SYNTHETIC_SECRET} '
        f'{SYNTHETIC_TICKET} {SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}"'
        "}]}"
    ).encode()


@pytest.mark.parametrize(
    "status, body, headers, expected_stage, body_must_be_read",
    (
        (
            400,
            development_browser_error_body("message", "invalid request"),
            (),
            "provider development-browser request invalid",
            False,
        ),
        (
            401,
            development_browser_error_body("message", "unauthenticated request"),
            (),
            "provider development-browser request unauthenticated",
            False,
        ),
        (
            403,
            development_browser_error_body("long_message", "origin is not allowed"),
            (),
            "provider development-browser origin rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "origin is not allowed"),
            (),
            "provider development-browser origin rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "hostname is not allowed"),
            (),
            "provider development-browser hostname rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("long_message", "hostname is not allowed"),
            (),
            "provider development-browser hostname rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "host is not allowed"),
            (),
            "provider development-browser hostname rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("long_message", "host is not allowed"),
            (),
            "provider development-browser hostname rejected",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "bot verification required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("long_message", "bot verification required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "captcha required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("long_message", "captcha required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "challenge required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("long_message", "challenge required"),
            (),
            "provider development-browser browser challenge required",
            True,
        ),
        (
            403,
            development_browser_error_body("message", "unknown provider detail"),
            (("cf-mitigated", "challenge"),),
            "provider development-browser browser challenge required",
            False,
        ),
        (
            403,
            development_browser_error_body("message", "unknown provider detail"),
            (("x-vercel-mitigated", "challenge"),),
            "provider development-browser browser challenge required",
            False,
        ),
        (
            403,
            development_browser_error_body("message", "unknown provider detail"),
            (),
            "provider development-browser request forbidden",
            True,
        ),
        (
            403,
            f'{{"unexpected": "{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} '
            f'{SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}"}}'.encode(),
            (),
            "provider development-browser request forbidden",
            True,
        ),
        (
            403,
            f'{{"errors": [{{"message": "unknown {SYNTHETIC_SECRET} '
            f"{SYNTHETIC_TICKET} {SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}".encode(),
            (),
            "provider development-browser request forbidden",
            True,
        ),
        (
            500,
            development_browser_error_body("message", "provider rejected request"),
            (),
            "provider development-browser request rejected",
            False,
        ),
    ),
    ids=(
        "400-invalid",
        "401-unauthenticated",
        "403-origin-long-message",
        "403-origin-message",
        "403-hostname",
        "403-hostname-long-message",
        "403-host",
        "403-host-long-message",
        "403-bot",
        "403-bot-long-message",
        "403-captcha",
        "403-captcha-long-message",
        "403-challenge",
        "403-challenge-long-message",
        "403-cloudflare-challenge-header",
        "403-vercel-challenge-header",
        "403-unknown-error",
        "403-unknown-envelope",
        "403-malformed-envelope",
        "500-rejected",
    ),
)
def test_development_browser_http_errors_have_fixed_sanitized_stages(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: int,
    body: bytes,
    headers: tuple[tuple[str, str], ...],
    expected_stage: str,
    body_must_be_read: bool,
) -> None:
    """Only the first FAPI request classifies provider HTTP failures."""
    session, transport = validated_session(_Ticket())

    class DevelopmentBrowserHttpFailurePeer:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            assert_first_fapi_request_is_development_browser(request)
            return httpx.Response(status, content=body, headers=dict(headers))

    opener = DevelopmentBrowserHttpFailurePeer()
    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == f"FAIL {expected_stage}\n"
    assert_development_browser_failure_cleanup(transport, opener.urls)
    # HTTPX eagerly buffers transport responses; classification still may use
    # only the contract's bounded diagnostic prefix.
    assert isinstance(body_must_be_read, bool)


@pytest.mark.parametrize(
    ("body", "expected_stage"),
    (
        (
            b'{"errors":[{"message":"origin rejected '
            + SYNTHETIC_SECRET.encode()
            + b'"}]}',
            "provider development-browser origin rejected",
        ),
        (
            b'{"errors":[{"message":"unknown '
            + b"x" * (MAX_DEVELOPMENT_BROWSER_ERROR_BODY_BYTES + 64)
            + b" origin rejected "
            + SYNTHETIC_SECRET.encode()
            + b'"}]}',
            "provider development-browser request forbidden",
        ),
    ),
    ids=("marker-within-diagnostic-prefix", "marker-after-diagnostic-prefix"),
)
def test_development_browser_403_diagnostic_parsing_is_bounded_and_sanitized(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    body: bytes,
    expected_stage: str,
) -> None:
    """This bounds diagnostic parsing, not HTTPX's eager response buffering."""
    session, transport = validated_session(_Ticket())
    requests: list[httpx.Request] = []

    def peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, content=body)

    caplog.set_level(logging.DEBUG)
    install_fapi_mock(monkeypatch, peer)
    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()
    assert captured.err == f"FAIL {expected_stage}\n"
    assert_fapi_failure_output_is_sanitized(captured)
    assert_fapi_failure_logs_are_sanitized(caplog)
    assert len(requests) == 1
    assert transport.events == [("ticket", {"sign_in_token_id": SYNTHETIC_TICKET})]


@pytest.mark.parametrize(
    "error",
    (
        httpx.TransportError(
            f"{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} "
            f"{SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}"
        ),
    ),
    ids=("transport-error",),
)
def test_development_browser_transport_errors_are_sanitized_and_unavailable(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: httpx.TransportError,
) -> None:
    """Non-HTTP failures reveal only that the dev-browser transport is unavailable."""
    session, transport = validated_session(_Ticket())

    class DevelopmentBrowserTransportFailurePeer:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            assert_first_fapi_request_is_development_browser(request)
            raise error

    opener = DevelopmentBrowserTransportFailurePeer()
    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider development-browser transport unavailable\n"
    assert_development_browser_failure_cleanup(transport, opener.urls)


def test_development_browser_remote_disconnect_is_a_sanitized_transport_failure(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RemoteDisconnected retains its OSError transport classification at dev-browser."""
    assert_pre_sign_in_protocol_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        "/v1/dev_browser",
        httpx.NetworkError(token_failure_sensitive_material()),
        "provider development-browser transport unavailable",
    )


@pytest.mark.parametrize(
    "error",
    (httpx.ProtocolError(token_failure_sensitive_material()),),
    ids=("protocol-error",),
)
def test_development_browser_non_oserror_protocol_failures_remain_generic_ticket_failures(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    error: httpx.ProtocolError,
) -> None:
    """Only actual transport failures enter the existing dev-browser transport stage."""
    assert_pre_sign_in_protocol_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        "/v1/dev_browser",
        error,
        "provider development-browser transport unavailable",
    )


@pytest.mark.parametrize(
    "error",
    (httpx.ProtocolError(token_failure_sensitive_material()),),
    ids=("protocol-error",),
)
def test_client_non_oserror_protocol_failures_remain_generic_ticket_failures(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    error: httpx.ProtocolError,
) -> None:
    """Protocol parsing failures must not become client-initialization transport stages."""
    assert_pre_sign_in_protocol_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        "/v1/client",
        error,
        "provider ticket flow unsuccessful",
    )


@pytest.mark.parametrize(
    "response",
    (
        httpx.Response(200, content=b'{"raw_provider_body":"invalid'),
        httpx.Response(
            200,
            json=[
                SYNTHETIC_SECRET,
                SYNTHETIC_TICKET,
                SYNTHETIC_NEW_SESSION,
                SYNTHETIC_TOKEN,
            ],
        ),
        httpx.Response(
            200,
            json={
                "raw_provider_body": (
                    f"{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} "
                    f"{SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}"
                ),
            },
        ),
        httpx.Response(
            200,
            json={
                "id": "",
                "raw_provider_body": (
                    f"{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} "
                    f"{SYNTHETIC_NEW_SESSION} {SYNTHETIC_TOKEN}"
                ),
            },
        ),
    ),
    ids=("malformed-json", "non-dict", "missing-id", "empty-id"),
)
def test_invalid_development_browser_responses_have_one_sanitized_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    response: httpx.Response,
) -> None:
    """A 2xx first response must be an unredirected object with a nonempty ID."""
    session, transport = validated_session(_Ticket())

    class InvalidDevelopmentBrowserResponseOpener:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            assert_first_fapi_request_is_development_browser(request)
            return response

    opener = InvalidDevelopmentBrowserResponseOpener()

    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider development-browser response invalid\n"
    assert_development_browser_failure_cleanup(transport, opener.urls)


@pytest.mark.parametrize(
    "status, expected_stage",
    (
        (400, "provider session-token request invalid"),
        (401, "provider session-token request unauthenticated"),
        (403, "provider session-token request forbidden"),
        (404, "provider session-token request not found"),
        (429, "provider session-token request rejected"),
        (500, "provider session-token request rejected"),
    ),
)
def test_session_token_http_errors_have_fixed_sanitized_stages(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    status: int,
    expected_stage: str,
) -> None:
    """The final FAPI request classifies HTTP status without exposing diagnostics."""

    def token_result(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            content=token_failure_sensitive_material().encode(),
            headers={"x-synthetic-provider-debug": token_failure_sensitive_material()},
        )

    assert_final_token_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        token_result,
        expected_stage,
    )


@pytest.mark.parametrize(
    "error",
    (httpx.TransportError(token_failure_sensitive_material()),),
    ids=("transport-error",),
)
def test_session_token_transport_errors_have_one_sanitized_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    error: httpx.TransportError,
) -> None:
    """Non-HTTP token failures disclose only the transport category."""

    def token_result(_request: httpx.Request) -> httpx.Response:
        raise error

    assert_final_token_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        token_result,
        "provider session-token transport unavailable",
    )


@pytest.mark.parametrize(
    ("error_factory", "expected_stage"),
    (
        (
            lambda: httpx.DecodingError(token_failure_sensitive_material()),
            "provider session-token response invalid",
        ),
        (
            lambda: httpx.InvalidURL(token_failure_sensitive_material()),
            "provider session-token request invalid",
        ),
        (
            lambda: httpx.RequestError(token_failure_sensitive_material()),
            "provider session-token transport unavailable",
        ),
        (
            lambda: httpx.StreamError(token_failure_sensitive_material()),
            "provider session-token transport unavailable",
        ),
        (
            lambda: httpx.CookieConflict(token_failure_sensitive_material()),
            "provider session-token transport unavailable",
        ),
    ),
    ids=("decoding", "invalid-url", "request", "stream", "cookie-conflict"),
)
def test_final_token_httpx_diagnostic_exceptions_have_fixed_sanitized_stages(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    error_factory: Callable[[], Exception],
    expected_stage: str,
) -> None:
    """Final-token diagnostics classify HTTPX exceptions without exposing details."""

    def token_result(_request: httpx.Request) -> httpx.Response:
        raise error_factory()

    assert_final_token_failure_at_command_boundary(
        monkeypatch, capsys, caplog, token_result, expected_stage
    )


@pytest.mark.parametrize(
    "error",
    (httpx.ProtocolError(token_failure_sensitive_material()),),
    ids=("protocol-error",),
)
def test_session_token_http_protocol_errors_have_one_sanitized_transport_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    error: httpx.ProtocolError,
) -> None:
    """HTTP protocol failures are transport failures even when not OSError subclasses."""

    def token_result(_request: httpx.Request) -> httpx.Response:
        raise error

    assert_final_token_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        token_result,
        "provider session-token transport unavailable",
    )


@pytest.mark.parametrize(
    "response_kind",
    (
        "malformed-json",
        "non-dict",
        "missing-jwt",
        "empty-jwt",
        "non-string-jwt",
        "wrapped-jwt",
    ),
)
def test_invalid_session_token_responses_have_one_sanitized_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    response_kind: str,
) -> None:
    """A normal token response is an unredirected object with a nonempty string JWT."""

    def token_result(request: httpx.Request) -> httpx.Response:
        sensitive = token_failure_sensitive_material()
        if response_kind == "malformed-json":
            return httpx.Response(200, content=f'{{"token": "{sensitive}'.encode())
        if response_kind == "non-dict":
            return httpx.Response(200, json=[SYNTHETIC_JWT, sensitive])
        if response_kind == "missing-jwt":
            return httpx.Response(200, json={"sensitive_claims": sensitive})
        if response_kind == "empty-jwt":
            return httpx.Response(200, json={"jwt": "", "sensitive_claims": sensitive})
        if response_kind == "non-string-jwt":
            return httpx.Response(
                200, json={"jwt": [SYNTHETIC_JWT], "sensitive_claims": sensitive}
            )
        if response_kind == "wrapped-jwt":
            return httpx.Response(
                200,
                json={
                    "response": {"jwt": SYNTHETIC_JWT},
                    "sensitive_claims": sensitive,
                },
            )
        raise AssertionError(f"unsupported token response case {response_kind}")

    assert_final_token_failure_at_command_boundary(
        monkeypatch,
        capsys,
        caplog,
        token_result,
        "provider session-token response invalid",
    )


def test_development_browser_redirect_is_rejected_without_following_location(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session, transport = validated_session(_Ticket())
    requests: list[httpx.Request] = []

    def peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://attacker.invalid/"})

    install_fapi_mock(monkeypatch, peer)
    assert run_main_with_session(monkeypatch, session) == 1
    assert (
        capsys.readouterr().err
        == "FAIL provider development-browser request rejected\n"
    )
    assert len(requests) == 1
    assert transport.events == [("ticket", {"sign_in_token_id": SYNTHETIC_TICKET})]


def test_session_token_redirect_is_rejected_without_following_location(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session, transport = validated_session(_Ticket())
    peer = _FinalTokenFailurePeer(
        lambda _request: httpx.Response(
            302, headers={"location": "https://attacker.invalid/"}
        )
    )
    install_fapi_mock(monkeypatch, peer)
    assert run_main_with_session(monkeypatch, session) == 1
    assert capsys.readouterr().err == "FAIL provider session-token request rejected\n"
    assert len(peer.urls) == 4
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_client_initialization_failure_has_one_sanitized_public_stage(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After a valid dev-browser ID, client initialization has its own failure stage."""
    session, _transport = validated_session(_Ticket())

    class ClientInitializationFailurePeer:
        def __call__(self, request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/v1/dev_browser":
                return httpx.Response(200, json={"id": "dev_browser_synthetic"})
            if path == "/v1/client":
                raise OSError(
                    f"{SYNTHETIC_SECRET} {SYNTHETIC_TICKET} "
                    f"{SYNTHETIC_NEW_SESSION} "
                    "https://development-synthetic.clerk.accounts.dev/sensitive-path"
                )
            raise AssertionError(f"unexpected Frontend API path {path}")

    opener = ClientInitializationFailurePeer()
    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider client initialization unsuccessful\n"


def test_malformed_ticket_after_a_valid_id_is_still_revoked_during_cleanup() -> None:
    """Cleanup owns a provider-created ticket as soon as its valid ID is known."""
    session, transport = validated_session(_Ticket(token=None))

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()
    session.cleanup()

    assert transport.events == [
        ("ticket", {"sign_in_token_id": SYNTHETIC_TICKET}),
    ]


def test_ticket_create_disables_the_sdk_default_retry_for_the_nonidempotent_post() -> (
    None
):
    """An ambiguous POST must be attempted once, never retried by SDK defaults."""
    session, transport = validated_session(_Ticket())

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()
    assert len(transport.sign_in_tokens.create_calls) == 1
    retries = transport.sign_in_tokens.create_calls[0]["retries"]
    assert isinstance(retries, RetryConfig)
    assert retries.strategy == "none"
    assert retries.retry_connection_errors is False


def test_ambiguous_ticket_creation_marks_cleanup_incomplete_at_command_boundary() -> (
    None
):
    """A connection failure before a ticket ID is known cannot prove no ticket exists."""
    session, transport = validated_session(
        _Ticket(),
        create_error=OSError("synthetic ambiguous ticket creation failure"),
    )

    outcome = auth_smoke.run(
        {"CLERK_SMOKE_USER_ID": SYNTHETIC_USER},
        _OrchestrationRuntime(session),
    )

    assert outcome.primary_stage == "provider ticket flow unsuccessful"
    assert outcome.cleanup_incomplete
    assert transport.events == []


def test_ambiguous_ticket_sign_in_response_marks_cleanup_incomplete(
    monkeypatch: MonkeyPatch,
) -> None:
    """A request transport error cannot prove Clerk did not create a session."""
    session, transport = validated_session(_Ticket())

    class SignInTransportFailureOpener:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            path = request.url.path
            if path == "/v1/dev_browser":
                return httpx.Response(200, json={"id": "dev_browser_synthetic"})
            if path == "/v1/client":
                return httpx.Response(200, json={"sessions": []})
            if path == "/v1/client/sign_ins":
                raise httpx.TransportError("synthetic ambiguous ticket sign-in request")
            raise AssertionError(f"unexpected Frontend API path {path}")

    opener = SignInTransportFailureOpener()

    install_fapi_mock(monkeypatch, opener)

    outcome = auth_smoke.run(
        {"CLERK_SMOKE_USER_ID": SYNTHETIC_USER},
        _OrchestrationRuntime(session),
    )

    assert outcome.primary_stage == "provider ticket flow unsuccessful"
    assert outcome.cleanup_incomplete
    assert [urlsplit(url).path for url in opener.urls] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
    ]
    assert transport.events == [
        ("ticket", {"sign_in_token_id": SYNTHETIC_TICKET}),
    ]


def test_created_session_id_is_revoked_when_ticket_response_omits_sessions(
    monkeypatch: MonkeyPatch,
) -> None:
    """Provider ownership wins over malformed session listings during cleanup."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {},
            },
        }
    )

    install_fapi_mock(monkeypatch, opener)

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    session.cleanup()

    assert raised.value.stage.value == "provider ticket flow unsuccessful"
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_missing_created_session_id_makes_cleanup_incomplete_after_ticket_sign_in(
    monkeypatch: MonkeyPatch,
) -> None:
    """Successful ticket consumption without an owned session must fail closed."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {"status": "complete"},
                "client": {"sessions": []},
            },
        }
    )

    install_fapi_mock(monkeypatch, opener)

    outcome = auth_smoke.run(
        {"CLERK_SMOKE_USER_ID": SYNTHETIC_USER},
        _OrchestrationRuntime(session),
    )

    assert outcome.primary_stage == "provider ticket flow unsuccessful"
    assert outcome.cleanup_incomplete
    assert transport.events == []


def test_ticket_is_consumed_before_later_session_token_validation_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    """A completed one-use sign-in is not sent to an unsupported revoke endpoint."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {
                    "sessions": [
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user": {"id": SYNTHETIC_USER},
                        }
                    ]
                },
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {},
        }
    )

    install_fapi_mock(monkeypatch, opener)

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    session.cleanup()

    assert raised.value.stage.value == "provider session-token response invalid"
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_nested_created_session_owner_reaches_the_session_token_request(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A Clerk-shaped nested owner authorizes only the ticket-created session."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {
                    "sessions": [
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user": {"id": SYNTHETIC_USER},
                        }
                    ]
                },
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {},
        }
    )

    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider session-token response invalid\n"
    assert [urlsplit(url).path for url in opener.urls] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens",
    ]
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


@pytest.mark.parametrize(
    "nested_user",
    (
        {"id": "user_synthetic_someone_else"},
        {},
        "user_synthetic_not_an_object",
    ),
    ids=("wrong-id", "missing-id", "non-object"),
)
def test_invalid_nested_created_session_owner_fails_before_token_request(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    nested_user: object,
) -> None:
    """No flat user_id compatibility path may authorize an unowned session."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {
                    "sessions": [
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user": nested_user,
                            "user_id": SYNTHETIC_USER,
                        }
                    ]
                },
            },
        }
    )

    install_fapi_mock(monkeypatch, opener)

    assert run_main_with_session(monkeypatch, session) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert_fapi_failure_output_is_sanitized(captured)
    assert captured.err == "FAIL provider ticket flow unsuccessful\n"
    assert [urlsplit(url).path for url in opener.urls] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
    ]
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_created_session_id_prevents_an_older_active_session_from_being_used_or_revoked(
    monkeypatch: MonkeyPatch,
) -> None:
    """Ticket sign-in must stay bound to the session Clerk says it just created."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendPeer(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {
                    "sessions": [
                        {
                            "id": SYNTHETIC_OLD_SESSION,
                            "status": "active",
                            "user": {"id": SYNTHETIC_USER},
                        },
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user": {"id": SYNTHETIC_USER},
                        },
                    ]
                },
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {
                "jwt": "synthetic-malformed-session-token"
            },
        }
    )

    install_fapi_mock(monkeypatch, opener)

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    session.cleanup()

    assert raised.value.stage.value == "token claims or lifetime invalid"
    assert [urlsplit(url).path for url in opener.urls] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens",
    ]
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def accept_synthetic_session_token(
    _session: development_session.ClerkDevelopmentSession,
    _token: str,
) -> None:
    """Keep the header contract test independent of unrelated token cryptography."""


def test_every_frontend_api_request_has_fixed_headers_and_endpoint_form_contract(
    monkeypatch: MonkeyPatch,
) -> None:
    """Provider response data cannot change the permanent FAPI request identity."""
    session, transport = validated_session(_Ticket())
    untrusted_headers = {
        "User-Agent": SYNTHETIC_SECRET,
        "Accept": SYNTHETIC_TICKET,
        "Origin": SYNTHETIC_NEW_SESSION,
        "Clerk-API-Version": SYNTHETIC_TOKEN,
    }
    opener = _RequestCapturingFrontendPeer(
        {
            "/v1/dev_browser": {
                "id": "dev_browser_synthetic",
                "headers": untrusted_headers,
            },
            "/v1/client": {"sessions": [], "headers": untrusted_headers},
            "/v1/client/sign_ins": {
                "response": {
                    "status": "complete",
                    "created_session_id": SYNTHETIC_NEW_SESSION,
                },
                "client": {
                    "sessions": [
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user": {"id": SYNTHETIC_USER},
                        }
                    ]
                },
                "headers": untrusted_headers,
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {
                "jwt": SYNTHETIC_TOKEN,
                "headers": untrusted_headers,
            },
        }
    )

    clients = install_fapi_mock(monkeypatch, opener)
    monkeypatch.setattr(
        development_session.ClerkDevelopmentSession,
        "_validate_claims_and_verifier",
        accept_synthetic_session_token,
    )

    assert session.create_verified_token() == SYNTHETIC_TOKEN
    session.cleanup()

    assert len(clients) == 1
    assert [request.url.path for request in opener.requests] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens",
    ]
    dev_browser, client, sign_in, token = opener.requests
    assert dev_browser.content == b""
    assert client.content == b""
    assert client.headers["content-type"] == "application/x-www-form-urlencoded"
    assert token.content == b""
    for request in (sign_in, token):
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert sorted(parse_qsl(sign_in.content.decode("ascii"))) == [
        ("strategy", "ticket"),
        ("ticket", "ticket_synthetic_one_use_credential"),
    ]
    for request in opener.requests:
        assert request.headers["user-agent"] == FAPI_USER_AGENT
        assert request.headers["accept"] == FAPI_ACCEPT
        assert request.headers["origin"] == development_session.TOOLING_ORIGIN
        assert request.headers["clerk-api-version"] == "2026-05-12"
        rendered_headers = "\n".join(
            f"{name}: {value}" for name, value in request.headers.items()
        )
        for sensitive_value in (
            SYNTHETIC_SECRET,
            SYNTHETIC_TICKET,
            SYNTHETIC_NEW_SESSION,
            SYNTHETIC_TOKEN,
        ):
            assert sensitive_value not in rendered_headers
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_default_authenticated_api_http_disables_environment_proxies_and_redirects(
    monkeypatch: MonkeyPatch,
) -> None:
    """This narrow handler assertion is the observable proxy/redirect boundary."""
    captured: list[tuple[object, ...]] = []

    def observe_opener(*handlers: object) -> object:
        captured.append(handlers)
        return object()

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.synthetic.invalid:8080")
    monkeypatch.setattr(urllib.request, "build_opener", observe_opener)

    auth_smoke.DefaultSmokeRuntime()

    assert len(captured) == 1
    assert any(
        isinstance(handler, urllib.request.ProxyHandler)
        and getattr(handler, "proxies", None) == {}
        for handler in captured[0]
    )
    assert any(
        isinstance(handler, urllib.request.HTTPRedirectHandler)
        and type(handler) is not urllib.request.HTTPRedirectHandler
        for handler in captured[0]
    )


def test_frontend_api_http_disables_environment_proxies_and_redirects(
    monkeypatch: MonkeyPatch,
) -> None:
    """FAPI must not route a ticket or bearer token through ambient proxies."""
    session, _transport = validated_session(_Ticket())
    construction: list[dict[str, object]] = []

    def make_client(**kwargs: object) -> httpx.Client:
        construction.append(kwargs)
        return _REAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(503, content=b"synthetic error")
            ),
            **cast(Any, kwargs),
        )

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.synthetic.invalid:8080")
    monkeypatch.setattr(development_session.httpx, "Client", make_client)

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()

    assert len(construction) == 1
    assert construction[0]["trust_env"] is False
    assert construction[0]["follow_redirects"] is False
    assert construction[0]["timeout"] == 10


def test_backend_sdk_uses_a_client_that_disables_environment_proxies_and_redirects(
    monkeypatch: MonkeyPatch,
) -> None:
    """The SDK otherwise creates its own environment-sensitive HTTP client."""
    captured_client: list[object | None] = []

    class FakeClerk:
        def __init__(self, *, bearer_auth: str, client: object | None = None) -> None:
            assert bearer_auth == SYNTHETIC_SECRET
            captured_client.append(client)
            self.instance_settings = _InstanceSettings()
            self.users = _Users()
            self.domains = _DomainsResource(
                data=[_Domain(False, DEFAULT_PRIMARY_FRONTEND_API_URL)],
                error=None,
            )

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.synthetic.invalid:8080")
    monkeypatch.setattr(development_session, "Clerk", FakeClerk)

    development_session.ClerkDevelopmentSession.validate(
        secret=SYNTHETIC_SECRET,
        user_id=SYNTHETIC_USER,
    )

    assert len(captured_client) == 1
    assert isinstance(captured_client[0], _REAL_HTTPX_CLIENT)
    assert captured_client[0].trust_env is False
    assert captured_client[0].follow_redirects is False
    captured_client[0].close()


def test_contributor_docs_name_authoritative_metadata_and_every_sanitized_stage() -> (
    None
):
    """The manual-only workflow must publish the bounded failure vocabulary."""
    documentation = (REPOSITORY_ROOT / "services" / "api" / "README.md").read_text()

    assert "authoritative instance metadata" in documentation
    assert "authoritative environment type" in documentation
    for stage in (
        "target configuration invalid",
        "baseline smoke unsuccessful",
        "interactive terminal unavailable",
        "credential form invalid",
        "Clerk instance not validated as Development",
        "configured smoke user unavailable",
        "provider development-browser flow unsuccessful",
        "provider development-browser request invalid",
        "provider development-browser request unauthenticated",
        "provider development-browser request forbidden",
        "provider development-browser browser challenge required",
        "provider development-browser origin rejected",
        "provider development-browser hostname rejected",
        "provider development-browser request rejected",
        "provider development-browser transport unavailable",
        "provider development-browser response invalid",
        "provider ticket flow unsuccessful",
        "provider session-token flow unsuccessful",
        "provider session-token request invalid",
        "provider session-token request unauthenticated",
        "provider session-token request forbidden",
        "provider session-token request not found",
        "provider session-token request rejected",
        "provider session-token transport unavailable",
        "provider session-token response invalid",
        "token claims or lifetime invalid",
        "TailTag verifier rejected the token",
        "authenticated API response invalid",
        "cleanup incomplete",
    ):
        assert stage in documentation
