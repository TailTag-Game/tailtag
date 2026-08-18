"""Independent regressions for Issue #99 review remediation.

These tests exercise only offline, synthetic provider and HTTP boundaries.  They
deliberately retain no credentials and prohibit every real network path.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Self
from urllib.parse import urlsplit

import httpx
import pytest
from clerk_backend_api.utils import RetryConfig
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_auth_smoke as auth_smoke
from scripts import clerk_development_session as development_session

SYNTHETIC_SECRET = "sk_test_synthetic_credential_material"
SYNTHETIC_USER = "user_synthetic_review_subject"
SYNTHETIC_TICKET = "ticket_synthetic_review_value"
SYNTHETIC_OLD_SESSION = "sess_synthetic_old"
SYNTHETIC_NEW_SESSION = "sess_synthetic_new"
DEVELOPMENT_FAPI_URL = (
    "https://development-synthetic.clerk.accounts.dev/"
    "sign-in-tokens/ticket_synthetic_review_value"
)


def prohibit_network(monkeypatch: MonkeyPatch) -> None:
    """Fail instead of allowing an ordinary test to make an outbound request."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("Issue #99 regression tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    for client_type in (httpx.Client, httpx.AsyncClient):
        monkeypatch.setattr(client_type, "request", no_network)
        monkeypatch.setattr(client_type, "send", no_network)


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
class _Ticket:
    id: str = SYNTHETIC_TICKET
    token: object = "ticket_synthetic_one_use_credential"
    url: object = DEVELOPMENT_FAPI_URL


class _InstanceSettings:
    def get(self) -> _Metadata:
        return _Metadata()


class _Users:
    def get(self, *, user_id: str) -> _User:
        assert user_id == SYNTHETIC_USER
        return _User()


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
        self, ticket: _Ticket, *, create_error: BaseException | None = None
    ) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.instance_settings = _InstanceSettings()
        self.users = _Users()
        self.sign_in_tokens = _SignInTokens(ticket, self.events, create_error)
        self.sessions = _Sessions(self.events)


def validated_session(
    ticket: _Ticket,
    *,
    create_error: BaseException | None = None,
) -> tuple[development_session.ClerkDevelopmentSession, _Transport]:
    transport = _Transport(ticket, create_error=create_error)
    session = development_session.ClerkDevelopmentSession.validate(
        secret=SYNTHETIC_SECRET,
        user_id=SYNTHETIC_USER,
        transport=transport,
    )
    return session, transport


@dataclass
class _FrontendResponse:
    payload: dict[str, object]
    url: str
    status: int = 200

    def read(self) -> bytes:
        import json

        return json.dumps(self.payload).encode("utf-8")

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _FrontendOpener:
    def __init__(
        self,
        responses: dict[str, dict[str, object]],
    ) -> None:
        self._responses = responses
        self.urls: list[str] = []

    def open(
        self, request: urllib.request.Request, **_kwargs: object
    ) -> _FrontendResponse:
        path = urlsplit(request.full_url).path
        self.urls.append(request.full_url)
        try:
            payload = self._responses[path]
        except KeyError as error:
            raise AssertionError(f"unexpected FAPI path {path}") from error
        return _FrontendResponse(payload, request.full_url)


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
    session, transport = validated_session(_Ticket(url="not-a-development-url"))

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()

    assert raised.value.stage.value == "provider ticket flow unsuccessful"
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


def test_created_session_id_is_revoked_when_ticket_response_omits_sessions(
    monkeypatch: MonkeyPatch,
) -> None:
    """Provider ownership wins over malformed session listings during cleanup."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendOpener(
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

    def build_opener(*_handlers: urllib.request.BaseHandler) -> _FrontendOpener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

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
    opener = _FrontendOpener(
        {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"sessions": []},
            "/v1/client/sign_ins": {
                "response": {"status": "complete"},
                "client": {"sessions": []},
            },
        }
    )

    def build_opener(*_handlers: urllib.request.BaseHandler) -> _FrontendOpener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

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
    opener = _FrontendOpener(
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
                            "user_id": SYNTHETIC_USER,
                        }
                    ]
                },
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {},
        }
    )

    def build_opener(*_handlers: urllib.request.BaseHandler) -> _FrontendOpener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    session.cleanup()

    assert raised.value.stage.value == "provider session-token flow unsuccessful"
    assert transport.events == [("session", {"session_id": SYNTHETIC_NEW_SESSION})]


def test_created_session_id_prevents_an_older_active_session_from_being_used_or_revoked(
    monkeypatch: MonkeyPatch,
) -> None:
    """Ticket sign-in must stay bound to the session Clerk says it just created."""
    session, transport = validated_session(_Ticket())
    opener = _FrontendOpener(
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
                            "user_id": SYNTHETIC_USER,
                        },
                        {
                            "id": SYNTHETIC_NEW_SESSION,
                            "status": "active",
                            "user_id": SYNTHETIC_USER,
                        },
                    ]
                },
            },
            f"/v1/client/sessions/{SYNTHETIC_NEW_SESSION}/tokens": {
                "jwt": "synthetic-malformed-session-token"
            },
        }
    )

    def build_opener(*_handlers: urllib.request.BaseHandler) -> _FrontendOpener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

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
    """FAPI must not route the ticket or bearer token through an ambient proxy."""
    session, _transport = validated_session(_Ticket())
    captured: list[tuple[object, ...]] = []

    def observe_opener(*handlers: object) -> object:
        captured.append(handlers)
        return _FrontendOpener(
            {
                "/v1/dev_browser": {"id": "dev_browser_synthetic"},
                "/v1/client": {"sessions": []},
                "/v1/client/sign_ins": {
                    "response": {"status": "complete"},
                    "client": {"sessions": []},
                },
            }
        )

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.synthetic.invalid:8080")
    monkeypatch.setattr(urllib.request, "build_opener", observe_opener)

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()

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

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.synthetic.invalid:8080")
    monkeypatch.setattr(development_session, "Clerk", FakeClerk)

    development_session.ClerkDevelopmentSession.validate(
        secret=SYNTHETIC_SECRET,
        user_id=SYNTHETIC_USER,
    )

    assert len(captured_client) == 1
    assert isinstance(captured_client[0], httpx.Client)
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
        "provider ticket flow unsuccessful",
        "provider session-token flow unsuccessful",
        "token claims or lifetime invalid",
        "TailTag verifier rejected the token",
        "authenticated API response invalid",
        "cleanup incomplete",
    ):
        assert stage in documentation
