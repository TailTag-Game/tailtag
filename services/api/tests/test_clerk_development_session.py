"""Offline behavioural contract for the Clerk Development session adapter."""

from __future__ import annotations

import http.client
import json
import logging
import socket
import sys
import time
import urllib.request
from base64 import urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import HttpRequest
from pytest import LogCaptureFixture, MonkeyPatch
from rest_framework.exceptions import AuthenticationFailed

from authentication.clerk import ClerkSessionVerifier, VerifiedClerkIdentity

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import clerk_development_session as development_session

_REAL_HTTPX_CLIENT = httpx.Client

SENSITIVE_VALUES = (
    "sk_test_synthetic_credential_material",
    "ticket_synthetic_sensitive_material",
    "eyJsynthetic.header.payload",
    "user_synthetic_sensitive_identifier",
    "sess_synthetic_sensitive_identifier",
    '"private_claim":"synthetic-sensitive-value"',
)


class SensitiveSyntheticError(Exception):
    """An external failure whose content must never cross the CLI boundary."""


@dataclass
class TicketRequest:
    user_id: str
    expires_in_seconds: int


def prohibit_network(monkeypatch: MonkeyPatch) -> None:
    """Adapter tests may cross only faked provider and HTTP boundaries."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError(
            "ordinary Clerk Development adapter tests must remain offline"
        )

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", no_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    # MockTransport-backed clients below exercise the live-tool HTTP boundary
    # without leaving the process. Socket-level guards above still reject any
    # accidental real client traffic.
    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_network(monkeypatch)


def assert_sanitized(
    error: BaseException,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    captured = capsys.readouterr()
    rendered = "\n".join(
        (str(error), repr(error), captured.out, captured.err, caplog.text)
    )
    for sensitive in SENSITIVE_VALUES:
        assert sensitive not in rendered


@dataclass
class _Metadata:
    environment_type: str


@dataclass
class _User:
    id: str


@dataclass
class _Domain:
    is_satellite: object
    frontend_api_url: object


@dataclass
class _Domains:
    data: object


DEFAULT_PRIMARY_FRONTEND_API_URL = "https://development-synthetic.clerk.accounts.dev"
MISSING_TICKET_URL = object()


class _DomainsResource:
    def __init__(
        self,
        transport: RecordingTransport,
        *,
        data: object,
        error: BaseException | None,
    ) -> None:
        self._transport = transport
        self._data = data
        self._error = error

    def list(self, **_kwargs: object) -> _Domains:
        self._transport.events.append(("domains-list", None))
        if self._error is not None:
            raise self._error
        return _Domains(self._data)


class RecordingTransport:
    """A minimal, non-network Clerk boundary that records public operations."""

    def __init__(
        self,
        *,
        environment_type: str = "development",
        user_id: str = "user_synthetic_sensitive_identifier",
        domain_data: object | None = None,
        domains_error: BaseException | None = None,
    ) -> None:
        self.events: list[tuple[str, object]] = []
        self.environment_type = environment_type
        self.user_id = user_id
        self.instance_settings = self
        self.users = self
        self.sign_in_tokens = self
        self.sessions = self
        self.jwks = _JwksResource(self)
        self.domains = _DomainsResource(
            self,
            data=(
                [
                    _Domain(
                        is_satellite=True,
                        frontend_api_url="https://satellite-synthetic.invalid",
                    ),
                    _Domain(
                        is_satellite=False,
                        frontend_api_url=DEFAULT_PRIMARY_FRONTEND_API_URL,
                    ),
                ]
                if domain_data is None
                else domain_data
            ),
            error=domains_error,
        )

    def get(self, **kwargs: object) -> _Metadata | _User:
        if kwargs:
            self.events.append(("user-get", kwargs))
            return _User(self.user_id)
        self.events.append(("instance-settings", None))
        return _Metadata(self.environment_type)

    def create(self, **kwargs: object) -> NoReturn:
        raise AssertionError(f"unexpected provider resource creation: {kwargs!r}")

    def delete(self, **kwargs: object) -> NoReturn:
        raise AssertionError(f"persistent user deletion is forbidden: {kwargs!r}")

    def update(self, **kwargs: object) -> NoReturn:
        raise AssertionError(f"persistent user update is forbidden: {kwargs!r}")

    def revoke(self, **kwargs: object) -> NoReturn:
        raise AssertionError(f"unexpected cleanup before a resource exists: {kwargs!r}")


def validate_with(
    transport: RecordingTransport,
) -> development_session.ClerkDevelopmentSession:
    """The planned public transport seam keeps provider tests layout-independent."""
    return development_session.ClerkDevelopmentSession.validate(
        secret="sk_test_synthetic_credential_material",
        user_id="user_synthetic_sensitive_identifier",
        transport=transport,
    )


@dataclass
class _Jwk:
    kid: str
    kty: str
    n: str
    e: str


@dataclass
class _Jwks:
    keys: list[_Jwk]


class _JwksResource:
    def __init__(self, transport: RecordingTransport) -> None:
        self.transport = transport

    def get_jwks(self) -> _Jwks:
        self.transport.events.append(("jwks-get", None))
        return _Jwks([synthetic_jwk()])


def base64url(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def synthetic_jwk() -> _Jwk:
    public_numbers = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_numbers()
    )

    def encode_integer(value: int) -> str:
        return base64url(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    return _Jwk(
        kid="synthetic-key-id",
        kty="RSA",
        n=encode_integer(public_numbers.n),
        e=encode_integer(public_numbers.e),
    )


def synthetic_token(claims: dict[str, object]) -> str:
    header = {"alg": "RS256", "kid": "synthetic-key-id", "typ": "JWT"}
    encoded_header = base64url(json.dumps(header).encode())
    encoded_claims = base64url(json.dumps(claims).encode())
    return f"{encoded_header}.{encoded_claims}.synthetic-signature"


class SuccessfulFrontendPeer:
    """Offline FAPI boundary with only the approved normal-token flow."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        session: dict[str, object] = {
            "object": "session",
            "id": "sess_synthetic_sensitive_identifier",
            "status": "active",
            "user": {"id": "user_synthetic_sensitive_identifier"},
        }
        sign_in: dict[str, object] = {
            "object": "sign_in_attempt",
            "status": "complete",
            "created_session_id": "sess_synthetic_sensitive_identifier",
            "user_data": {"id": "user_synthetic_sensitive_identifier"},
        }
        client: dict[str, object] = {
            "object": "client",
            "id": "client_synthetic",
            "sessions": [session],
        }
        responses: dict[str, dict[str, object]] = {
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": client,
            "/v1/client/sign_ins": {"response": sign_in, "client": client},
            "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens": {
                "object": "token",
                "jwt": self.token,
            },
        }
        if path not in responses:
            raise AssertionError(f"unsupported Frontend API operation: {path}")
        response = responses[path]
        return httpx.Response(200, json=response)


class OfficialEnvelopeFrontendPeer:
    """FAPI responses shaped like Clerk's 2026-05-12 client/OpenAPI contract."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        created_session: dict[str, object] = {
            "object": "session",
            "id": "sess_synthetic_created_by_ticket",
            "status": "active",
            "user": {"id": "user_synthetic_sensitive_identifier"},
        }
        older_session: dict[str, object] = {
            "object": "session",
            "id": "sess_synthetic_older_active_session",
            "status": "active",
            "user": {"id": "user_synthetic_sensitive_identifier"},
        }
        responses: dict[str, dict[str, object]] = {
            # clerk-js createDevBrowser() reads the top-level `id` value.
            "/v1/dev_browser": {"id": "dev_browser_synthetic"},
            "/v1/client": {"object": "client", "sessions": []},
            # ClientWrappedSignIn preserves the direct sign-in under `response`
            # and the updated client (including sessions) as a sibling.
            "/v1/client/sign_ins": {
                "response": {
                    "object": "sign_in_attempt",
                    "status": "complete",
                    "created_session_id": "sess_synthetic_created_by_ticket",
                },
                "client": {
                    "object": "client",
                    "sessions": [older_session, created_session],
                },
            },
            "/v1/client/sessions/sess_synthetic_created_by_ticket/tokens": {
                "object": "token",
                "jwt": self.token,
            },
        }
        if path not in responses:
            raise AssertionError(f"unsupported Frontend API operation: {path}")
        return httpx.Response(200, json=responses[path])


@dataclass
class _Ticket:
    id: str = "ticket_synthetic_sensitive_material"
    token: str = "ticket_synthetic_one_use_credential"
    url: object = None


def configure_successful_provider(
    transport: RecordingTransport,
    *,
    ticket_url: object = None,
) -> tuple[list[TicketRequest], list[dict[str, object]]]:
    ticket_requests: list[TicketRequest] = []
    revocations: list[dict[str, object]] = []

    def create_ticket(**kwargs: object) -> _Ticket:
        request = cast(TicketRequest, kwargs["request"])
        assert request.user_id == "user_synthetic_sensitive_identifier"
        assert request.expires_in_seconds == 60
        ticket_requests.append(request)
        transport.events.append(("ticket-create", None))
        ticket = _Ticket(url=ticket_url)
        if ticket_url is MISSING_TICKET_URL:
            del ticket.url
        return ticket

    def revoke_resource(**kwargs: object) -> None:
        revocations.append(kwargs)
        transport.events.append(("revoke", kwargs))

    transport.create = create_ticket  # type: ignore[method-assign]
    transport.revoke = revoke_resource  # type: ignore[method-assign]
    return ticket_requests, revocations


def install_frontend_mock(
    monkeypatch: MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Client]:
    """Install one real synchronous client at the FAPI-only outbound boundary."""
    clients: list[httpx.Client] = []

    def make_client(**kwargs: object) -> httpx.Client:
        client = _REAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(handler),
            **cast(Any, kwargs),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(development_session.httpx, "Client", make_client)
    return clients


def run_successful_frontend_flow(
    monkeypatch: MonkeyPatch,
    *,
    claims: dict[str, object],
    verifier_rejects: bool = False,
    ticket_url: object = None,
) -> tuple[
    development_session.ClerkDevelopmentSession,
    RecordingTransport,
    SuccessfulFrontendPeer,
    list[HttpRequest],
]:
    transport = RecordingTransport()
    configure_successful_provider(transport, ticket_url=ticket_url)
    opener = SuccessfulFrontendPeer(synthetic_token(claims))
    install_frontend_mock(monkeypatch, opener)
    verifier_requests: list[HttpRequest] = []

    def verify(
        _verifier: ClerkSessionVerifier, request: HttpRequest
    ) -> VerifiedClerkIdentity:
        verifier_requests.append(request)
        if verifier_rejects:
            raise AuthenticationFailed()
        return VerifiedClerkIdentity(subject="user_synthetic_sensitive_identifier")

    monkeypatch.setattr(ClerkSessionVerifier, "verify", verify)
    session = validate_with(transport)
    return session, transport, opener, verifier_requests


def test_non_development_secret_form_is_rejected_before_any_provider_connection(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(Exception) as raised:
        development_session.ClerkDevelopmentSession.validate(
            secret="sk_live_synthetic_credential_material",
            user_id="user_synthetic_sensitive_identifier",
        )

    assert "credential form invalid" in str(raised.value)
    assert_sanitized(raised.value, capsys, caplog)


def test_metadata_is_authoritative_and_opaque_user_lookup_is_exact(
    monkeypatch: MonkeyPatch,
) -> None:
    clerk = RecordingTransport()
    session = validate_with(clerk)

    assert session is not None
    assert clerk.events == [
        ("instance-settings", None),
        ("user-get", {"user_id": "user_synthetic_sensitive_identifier"}),
        ("domains-list", None),
    ]


def test_non_development_metadata_fails_closed_before_ticket_creation(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clerk = RecordingTransport(environment_type="production")

    with pytest.raises(Exception) as raised:
        validate_with(clerk)

    assert "Clerk instance not validated as Development" in str(raised.value)
    assert clerk.events == [("instance-settings", None)]
    assert_sanitized(raised.value, capsys, caplog)


def test_missing_or_mismatched_opaque_user_fails_without_auto_provisioning(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clerk = RecordingTransport(user_id="user_someone_else")

    with pytest.raises(Exception) as raised:
        validate_with(clerk)

    assert "configured smoke user unavailable" in str(raised.value)
    assert [event[0] for event in clerk.events] == ["instance-settings", "user-get"]
    assert_sanitized(raised.value, capsys, caplog)


@pytest.mark.parametrize(
    "domain_data, domains_error",
    (
        (None, SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))),
        (
            [
                _Domain(
                    is_satellite=True,
                    frontend_api_url="https://satellite-synthetic.invalid",
                )
            ],
            None,
        ),
        (
            [
                _Domain(
                    is_satellite=False,
                    frontend_api_url=DEFAULT_PRIMARY_FRONTEND_API_URL,
                ),
                _Domain(
                    is_satellite=False,
                    frontend_api_url=DEFAULT_PRIMARY_FRONTEND_API_URL,
                ),
            ],
            None,
        ),
        (
            [
                _Domain(
                    is_satellite=False,
                    frontend_api_url="https://development-synthetic.clerk.accounts.dev:443",
                )
            ],
            None,
        ),
    ),
    ids=("lookup-failure", "no-primary", "multiple-primaries", "invalid-url"),
)
def test_primary_frontend_authority_is_required_before_ticket_creation(
    domain_data: object | None,
    domains_error: BaseException | None,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """Only one strict primary Development domain authorizes the FAPI flow."""
    caplog.set_level(logging.DEBUG)
    clerk = RecordingTransport(
        domain_data=domain_data,
        domains_error=domains_error,
    )

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        validate_with(clerk)

    assert raised.value.stage.value == "provider Frontend API authority unavailable"
    assert clerk.events == [
        ("instance-settings", None),
        ("user-get", {"user_id": "user_synthetic_sensitive_identifier"}),
        ("domains-list", None),
    ]
    assert_sanitized(raised.value, capsys, caplog)


def test_ticket_flow_uses_fixed_origin_and_exact_sixty_second_ticket(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """The first FAPI operation exposes the fixed-origin, same-instance contract."""
    clerk = RecordingTransport()
    ticket_requests: list[object] = []
    frontend_requests: list[httpx.Request] = []

    @dataclass
    class Ticket:
        id: str = "ticket_synthetic_sensitive_material"
        token: str = "ticket_synthetic_one_use_credential"
        url: str = "https://development-synthetic.clerk.accounts.dev/sign-in-tokens/ticket_synthetic_sensitive_identifier"

    def create_ticket(**kwargs: object) -> Ticket:
        ticket_requests.append(kwargs["request"])
        return Ticket()

    def fail_frontend_request(request: httpx.Request) -> httpx.Response:
        frontend_requests.append(request)
        raise httpx.TransportError(" ".join(SENSITIVE_VALUES))

    clerk.create = create_ticket  # type: ignore[method-assign]

    install_frontend_mock(monkeypatch, fail_frontend_request)
    session = validate_with(clerk)

    caplog.set_level(logging.DEBUG)
    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    assert_sanitized(raised.value, capsys, caplog)

    request = cast(TicketRequest, ticket_requests[0])
    assert request.user_id == "user_synthetic_sensitive_identifier"
    assert request.expires_in_seconds == 60
    assert len(frontend_requests) == 1
    assert str(frontend_requests[0].url).startswith(
        "https://development-synthetic.clerk.accounts.dev/"
    )
    assert frontend_requests[0].headers["origin"] == "http://localhost:3000"


def test_cleanup_revokes_an_unconsumed_ticket_but_never_deletes_persistent_user(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    clerk = RecordingTransport()
    revoked: list[dict[str, object]] = []

    @dataclass
    class Ticket:
        id: str = "ticket_synthetic_sensitive_material"
        token: str = "ticket_synthetic_one_use_credential"
        url: str = "https://development-synthetic.clerk.accounts.dev/sign-in-tokens/ticket_synthetic_sensitive_identifier"

    def create_ticket(**_kwargs: object) -> Ticket:
        return Ticket()

    def revoke_ticket(**kwargs: object) -> None:
        revoked.append(kwargs)

    def fail_frontend_request(_request: httpx.Request) -> httpx.Response:
        raise httpx.TransportError("ticket exchange failed")

    clerk.create = create_ticket  # type: ignore[method-assign]
    clerk.revoke = revoke_ticket  # type: ignore[method-assign]

    install_frontend_mock(monkeypatch, fail_frontend_request)
    session = validate_with(clerk)

    caplog.set_level(logging.DEBUG)
    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    assert_sanitized(raised.value, capsys, caplog)
    session.cleanup()

    assert revoked == [{"sign_in_token_id": "ticket_synthetic_sensitive_material"}]


def test_successful_normal_session_token_is_verified_and_cleaned_up(
    monkeypatch: MonkeyPatch,
) -> None:
    now = int(time.time())
    claims: dict[str, object] = {
        "sid": "sess_synthetic_sensitive_identifier",
        "sub": "user_synthetic_sensitive_identifier",
        "azp": "http://localhost:3000",
        "iat": now,
        "exp": now + 60,
    }
    session, transport, opener, verifier_requests = run_successful_frontend_flow(
        monkeypatch, claims=claims
    )

    token = session.create_verified_token()  # type: ignore[attr-defined]
    session.cleanup()  # type: ignore[attr-defined]

    assert token == opener.token
    assert len(verifier_requests) == 1
    assert verifier_requests[0].headers["Authorization"] == f"Bearer {token}"
    paths = [request.url.path for request in opener.requests]
    assert paths == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens",
    ]
    assert {request.url.netloc.decode("ascii") for request in opener.requests} == {
        "development-synthetic.clerk.accounts.dev"
    }
    assert all(
        request.headers["clerk-api-version"] == "2026-05-12"
        for request in opener.requests
    )
    assert all(
        "__clerk_api_version" not in str(request.url) for request in opener.requests
    )
    assert all("/tokens/" not in path for path in paths)
    assert all(
        request.headers["origin"] == "http://localhost:3000"
        for request in opener.requests
    )
    sign_in_request = opener.requests[2]
    assert parse_qs(sign_in_request.content.decode()) == {
        "strategy": ["ticket"],
        "ticket": ["ticket_synthetic_one_use_credential"],
    }
    assert [event[0] for event in transport.events] == [
        "instance-settings",
        "user-get",
        "domains-list",
        "ticket-create",
        "jwks-get",
        "revoke",
    ]
    assert transport.events[-1] == (
        "revoke",
        {"session_id": "sess_synthetic_sensitive_identifier"},
    )


@pytest.mark.parametrize(
    "ticket_url",
    (
        MISSING_TICKET_URL,
        None,
        "https://untrusted-synthetic.invalid/ignored-ticket-url",
    ),
    ids=("absent", "null", "untrusted"),
)
def test_validated_primary_domain_not_ticket_url_controls_frontend_api(
    monkeypatch: MonkeyPatch,
    ticket_url: object,
) -> None:
    """Optional ticket URLs cannot redirect a validated Development flow."""
    now = int(time.time())
    claims: dict[str, object] = {
        "sid": "sess_synthetic_sensitive_identifier",
        "sub": "user_synthetic_sensitive_identifier",
        "azp": "http://localhost:3000",
        "iat": now,
        "exp": now + 60,
    }
    session, _transport, opener, _requests = run_successful_frontend_flow(
        monkeypatch,
        claims=claims,
        ticket_url=ticket_url,
    )

    session.create_verified_token()
    session.cleanup()

    assert {request.url.netloc.decode("ascii") for request in opener.requests} == {
        "development-synthetic.clerk.accounts.dev"
    }


def test_official_fapi_envelopes_preserve_created_session_ownership(
    monkeypatch: MonkeyPatch,
) -> None:
    """The ticket flow consumes Clerk's documented id/sign-in/client envelopes."""
    now = int(time.time())
    token = synthetic_token(
        {
            "sid": "sess_synthetic_created_by_ticket",
            "sub": "user_synthetic_sensitive_identifier",
            "azp": "http://localhost:3000",
            "iat": now,
            "exp": now + 60,
        }
    )
    transport = RecordingTransport()
    _ticket_requests, revocations = configure_successful_provider(transport)
    opener = OfficialEnvelopeFrontendPeer(token)

    def verify(
        _verifier: ClerkSessionVerifier, _request: HttpRequest
    ) -> VerifiedClerkIdentity:
        return VerifiedClerkIdentity(subject="user_synthetic_sensitive_identifier")

    install_frontend_mock(monkeypatch, opener)
    monkeypatch.setattr(ClerkSessionVerifier, "verify", verify)
    session = validate_with(transport)

    assert session.create_verified_token() == token
    session.cleanup()

    assert [request.url.path for request in opener.requests] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        "/v1/client/sessions/sess_synthetic_created_by_ticket/tokens",
    ]
    assert revocations == [{"session_id": "sess_synthetic_created_by_ticket"}]


_MISSING = object()


@pytest.mark.parametrize(
    ("claim", "value", "verifier_rejects"),
    (
        ("sid", _MISSING, False),
        ("sid", "sess_someone_else", False),
        ("sub", _MISSING, False),
        ("sub", "user_someone_else", False),
        ("azp", _MISSING, False),
        ("azp", "http://localhost:3001", False),
        ("iat", True, False),
        ("exp", False, False),
        ("iat", _MISSING, False),
        ("iat", "2000000000", False),
        ("exp", _MISSING, False),
        ("exp", 2000000060.0, False),
        ("iat", 1.5, False),
        ("exp", "2000000060", False),
        ("expired", None, False),
        ("nonpositive", None, False),
        ("overlong", None, False),
        ("verifier", None, True),
    ),
    ids=(
        "missing-sid",
        "mismatched-sid",
        "missing-sub",
        "mismatched-sub",
        "missing-azp",
        "mismatched-azp",
        "bool-iat",
        "bool-exp",
        "missing-iat",
        "string-iat",
        "missing-exp",
        "float-exp",
        "non-int-iat",
        "non-int-exp",
        "expired",
        "nonpositive-lifetime",
        "over-60-second-lifetime",
        "unchanged-verifier-rejection",
    ),
)
def test_invalid_token_claims_or_verifier_rejection_fail_closed(
    monkeypatch: MonkeyPatch,
    claim: str,
    value: object,
    verifier_rejects: bool,
) -> None:
    now = int(time.time())
    claims: dict[str, object] = {
        "sid": "sess_synthetic_sensitive_identifier",
        "sub": "user_synthetic_sensitive_identifier",
        "azp": "http://localhost:3000",
        "iat": now,
        "exp": now + 60,
    }
    if claim == "expired":
        claims.update(iat=now - 60, exp=now - 1)
    elif claim == "nonpositive":
        claims["exp"] = claims["iat"]
    elif claim == "overlong":
        claims["exp"] = now + 61
    elif claim != "verifier":
        if value is _MISSING:
            del claims[claim]
        else:
            claims[claim] = value

    session, transport, _opener, verifier_requests = run_successful_frontend_flow(
        monkeypatch,
        claims=claims,
        verifier_rejects=verifier_rejects,
    )

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()  # type: ignore[attr-defined]
    session.cleanup()  # type: ignore[attr-defined]

    expected_stage = (
        "TailTag verifier rejected the token"
        if verifier_rejects
        else "token claims or lifetime invalid"
    )
    assert str(raised.value) == expected_stage
    assert len(verifier_requests) == int(verifier_rejects)
    assert transport.events[-1] == (
        "revoke",
        {"session_id": "sess_synthetic_sensitive_identifier"},
    )


def test_frontend_api_uses_one_persistent_httpx_client_with_the_spike_wire_contract(
    monkeypatch: MonkeyPatch,
) -> None:
    """The browser, client, sign-in, and token exchange share cookie state."""
    now = int(time.time())
    session, transport, _opener, verifier_requests = run_successful_frontend_flow(
        monkeypatch,
        claims={
            "sid": "sess_synthetic_sensitive_identifier",
            "sub": "user_synthetic_sensitive_identifier",
            "azp": "http://localhost:3000",
            "iat": now,
            "exp": now + 60,
        },
    )
    # The legacy urllib fixture above is deliberately bypassed: this is the
    # observable FAPI boundary required by the transport correction.
    requests: list[httpx.Request] = []
    clients: list[httpx.Client] = []

    def fapi_peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/v1/dev_browser":
            assert "cookie" not in request.headers
            return httpx.Response(
                200,
                json={"id": "dev_browser_synthetic"},
                headers={"set-cookie": "__clerk_db_jwt=synthetic; Path=/"},
            )
        assert request.headers.get("cookie") == "__clerk_db_jwt=synthetic"
        if path == "/v1/client":
            return httpx.Response(200, json={"sessions": []})
        if path == "/v1/client/sign_ins":
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "complete",
                        "created_session_id": "sess_synthetic_sensitive_identifier",
                    },
                    "client": {
                        "sessions": [
                            {
                                "id": "sess_synthetic_sensitive_identifier",
                                "status": "active",
                                "user": {"id": "user_synthetic_sensitive_identifier"},
                            }
                        ]
                    },
                },
            )
        if path == "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens":
            return httpx.Response(
                200,
                json={
                    "jwt": synthetic_token(
                        {
                            "sid": "sess_synthetic_sensitive_identifier",
                            "sub": "user_synthetic_sensitive_identifier",
                            "azp": "http://localhost:3000",
                            "iat": now,
                            "exp": now + 60,
                        }
                    )
                },
            )
        raise AssertionError(f"unexpected Frontend API operation: {path}")

    def make_fapi_client(**kwargs: object) -> httpx.Client:
        assert kwargs == {
            "base_url": DEFAULT_PRIMARY_FRONTEND_API_URL,
            "headers": {
                "Clerk-API-Version": "2026-05-12",
                "Origin": development_session.TOOLING_ORIGIN,
                "User-Agent": "TailTag-Issue-99-Development-Smoke",
                "Accept": "application/json",
            },
            "trust_env": False,
            "follow_redirects": False,
            "timeout": 10,
        }
        client = _REAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(fapi_peer), **cast(Any, kwargs)
        )
        clients.append(client)
        return client

    monkeypatch.setattr(development_session.httpx, "Client", make_fapi_client)

    token = session.create_verified_token()
    session.cleanup()

    assert len(clients) == 1
    assert clients[0].is_closed
    assert cast(Any, session)._fapi_client is None
    assert token
    assert len(verifier_requests) == 1
    assert [request.method for request in requests] == ["POST"] * 4
    assert [request.url.path for request in requests] == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens",
    ]
    assert [request.url.query for request in requests] == [
        b"",
        b"__dev_session=dev_browser_synthetic",
        b"__dev_session=dev_browser_synthetic",
        b"__dev_session=dev_browser_synthetic",
    ]
    for request in requests:
        assert request.headers["origin"] == development_session.TOOLING_ORIGIN
        assert request.headers["clerk-api-version"] == "2026-05-12"
        assert request.headers["user-agent"] == "TailTag-Issue-99-Development-Smoke"
        assert request.headers["accept"] == "application/json"
    assert requests[0].content == b""
    assert requests[1].content == b""
    assert requests[1].headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(requests[2].content.decode("ascii")) == {
        "strategy": ["ticket"],
        "ticket": ["ticket_synthetic_one_use_credential"],
    }
    assert requests[2].headers["content-type"] == "application/x-www-form-urlencoded"
    assert requests[3].content == b""
    assert requests[3].headers["content-type"] == "application/x-www-form-urlencoded"
    assert transport.events[-1] == (
        "revoke",
        {"session_id": "sess_synthetic_sensitive_identifier"},
    )


def test_frontend_api_client_is_closed_after_a_failure_and_close_failure_is_cleanup_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """FAPI transport lifetime is cleanup-critical on every failure exit."""
    # Keep the external SDK fake simple; only the FAPI client lifecycle matters.
    transport = RecordingTransport()
    session = validate_with(transport)
    transport.events.clear()
    configure_successful_provider(transport)
    clients: list[httpx.Client] = []
    close_calls: list[None] = []

    def fapi_peer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"synthetic provider diagnostic")

    def make_fapi_client(**kwargs: object) -> httpx.Client:
        client = _REAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(fapi_peer), **cast(Any, kwargs)
        )

        def fail_close() -> None:
            close_calls.append(None)
            raise RuntimeError("synthetic close failure")

        client.close = fail_close  # type: ignore[method-assign]
        clients.append(client)
        return client

    monkeypatch.setattr(development_session.httpx, "Client", make_fapi_client)

    with pytest.raises(development_session.ClerkFlowFailure) as primary:
        session.create_verified_token()
    assert (
        primary.value.stage
        is development_session.ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_REJECTED
    )

    with pytest.raises(development_session.ClerkFlowFailure) as cleanup:
        session.cleanup()
    assert cleanup.value.stage is development_session.ClerkFlowStage.CLEANUP
    assert len(clients) == 1
    assert close_calls == [None]
    assert cast(Any, session)._fapi_client is None
    assert transport.events == [
        ("ticket-create", None),
        ("revoke", {"sign_in_token_id": "ticket_synthetic_sensitive_material"}),
    ]


def test_fapi_client_construction_failure_is_a_sanitized_transport_failure_and_revokes_ticket(
    monkeypatch: MonkeyPatch,
) -> None:
    """A client that cannot be constructed creates no browser state but still cleans up."""
    transport = RecordingTransport()
    session = validate_with(transport)
    transport.events.clear()
    configure_successful_provider(transport)

    def fail_client_construction(**_kwargs: object) -> httpx.Client:
        raise RuntimeError("synthetic fapi client construction failure")

    monkeypatch.setattr(development_session.httpx, "Client", fail_client_construction)

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    assert (
        raised.value.stage
        is development_session.ClerkFlowStage.DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE
    )

    session.cleanup()
    assert transport.events == [
        ("ticket-create", None),
        ("revoke", {"sign_in_token_id": "ticket_synthetic_sensitive_material"}),
    ]


def test_cleanup_attempts_provider_revoke_and_fapi_close_before_reporting_incomplete() -> (
    None
):
    """Independent cleanup failures cannot short-circuit the remaining invalidation work."""
    transport = RecordingTransport()
    session = validate_with(transport)
    attempts: list[str] = []

    def fail_session_revoke(**_kwargs: object) -> None:
        attempts.append("session-revoke")
        raise RuntimeError("synthetic provider revoke failure")

    class FailingFapiClient:
        def close(self) -> None:
            attempts.append("fapi-close")
            raise RuntimeError("synthetic fapi close failure")

    transport.revoke = fail_session_revoke  # type: ignore[method-assign]
    cast(Any, session)._session_id = "sess_synthetic_sensitive_identifier"
    cast(Any, session)._fapi_client = FailingFapiClient()

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.cleanup()
    assert raised.value.stage is development_session.ClerkFlowStage.CLEANUP
    assert attempts == ["session-revoke", "fapi-close"]
    assert cast(Any, session)._fapi_client is None


@pytest.mark.parametrize("fails", (False, True), ids=("success", "transport-failure"))
def test_fapi_calls_suppress_httpx_and_httpcore_debug_logs_and_restore_states(
    monkeypatch: MonkeyPatch,
    caplog: LogCaptureFixture,
    fails: bool,
) -> None:
    """Provider debug suppression covers the locked HTTPX/httpcore logger families."""
    session = validate_with(RecordingTransport())
    sensitive = "sk_test_log cookie=sensitive sess_synthetic token.synthetic.value"
    logger_names = ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2")
    loggers = [logging.getLogger(name) for name in logger_names]
    prior = [logger.disabled for logger in loggers]
    for logger in loggers:
        logger.disabled = False

    def peer(_request: httpx.Request) -> httpx.Response:
        for logger in loggers:
            logger.debug(sensitive)
        if fails:
            raise httpx.TransportError(sensitive)
        return httpx.Response(200, json={"id": "dev_browser_synthetic"})

    client = _REAL_HTTPX_CLIENT(
        base_url=DEFAULT_PRIMARY_FRONTEND_API_URL,
        transport=httpx.MockTransport(peer),
    )
    cast(Any, session)._fapi_client = client
    cast(Any, session)._fapi_authority = DEFAULT_PRIMARY_FRONTEND_API_URL
    caplog.set_level(logging.DEBUG)
    try:
        if fails:
            with pytest.raises(development_session.ClerkFlowFailure):
                cast(Any, session)._frontend_request(
                    "/v1/dev_browser",
                    failure_stage=development_session.ClerkFlowStage.DEVELOPMENT_BROWSER,
                    development_browser_diagnostics=True,
                )
        else:
            assert cast(Any, session)._frontend_request(
                "/v1/dev_browser",
                failure_stage=development_session.ClerkFlowStage.DEVELOPMENT_BROWSER,
                development_browser_diagnostics=True,
            ) == {"id": "dev_browser_synthetic"}
    finally:
        client.close()
        for logger, disabled in zip(loggers, prior, strict=True):
            logger.disabled = disabled

    assert sensitive not in caplog.text
    assert all(sensitive not in record.getMessage() for record in caplog.records)
    assert [logger.disabled for logger in loggers] == prior


def test_cleanup_releases_sensitive_provider_references_after_success() -> None:
    """A completed live-session object must not remain a credential/provider holder."""
    transport = RecordingTransport()
    session = validate_with(transport)
    session.cleanup()

    retained = [getattr(session, field.name) for field in fields(session)]
    assert transport not in retained
    assert all(
        value
        not in {
            "sk_test_synthetic_credential_material",
            "user_synthetic_sensitive_identifier",
            DEFAULT_PRIMARY_FRONTEND_API_URL,
        }
        for value in retained
        if isinstance(value, str)
    )
    assert all(value in (None, False) for value in retained)


def test_cleanup_failure_still_releases_sensitive_provider_references() -> None:
    """Failed revocation/close paths cannot leave a reusable provider session object."""
    transport = RecordingTransport()
    session = validate_with(transport)
    attempts: list[str] = []

    def fail_revoke(**kwargs: object) -> None:
        attempts.append("session" if "session_id" in kwargs else "ticket")
        raise RuntimeError("synthetic provider failure")

    class FailingClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            attempts.append(self.name)
            raise RuntimeError("synthetic close failure")

    transport.revoke = fail_revoke  # type: ignore[method-assign]
    state = cast(Any, session)
    state._session_id = "sess_synthetic_sensitive_identifier"
    state._ticket_id = "ticket_synthetic_sensitive_material"
    state._ticket_consumed = False
    state._ticket_cleanup_uncertain = True
    state._session_cleanup_uncertain = True
    state._fapi_client = FailingClient("fapi-close")
    state._http_client = FailingClient("backend-close")

    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.cleanup()
    assert raised.value.stage is development_session.ClerkFlowStage.CLEANUP
    assert attempts == ["session", "ticket", "fapi-close", "backend-close"]

    retained = [getattr(session, field.name) for field in fields(session)]
    assert transport not in retained
    assert all(
        value
        not in {
            "sk_test_synthetic_credential_material",
            "user_synthetic_sensitive_identifier",
            "sess_synthetic_sensitive_identifier",
            "ticket_synthetic_sensitive_material",
            DEFAULT_PRIMARY_FRONTEND_API_URL,
        }
        for value in retained
        if isinstance(value, str)
    )
    assert all(value in (None, False) for value in retained)
