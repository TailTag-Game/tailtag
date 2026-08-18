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
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Self, cast
from urllib.parse import parse_qs, urlsplit

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
    for client_type in (httpx.Client, httpx.AsyncClient):
        monkeypatch.setattr(client_type, "request", no_network)
        monkeypatch.setattr(client_type, "send", no_network)


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


class RecordingTransport:
    """A minimal, non-network Clerk boundary that records public operations."""

    def __init__(
        self,
        *,
        environment_type: str = "development",
        user_id: str = "user_synthetic_sensitive_identifier",
    ) -> None:
        self.events: list[tuple[str, object]] = []
        self.environment_type = environment_type
        self.user_id = user_id
        self.instance_settings = self
        self.users = self
        self.sign_in_tokens = self
        self.sessions = self
        self.jwks = _JwksResource(self)

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


def validate_with(transport: RecordingTransport) -> object:
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


@dataclass
class _JsonResponse:
    body: dict[str, object]
    status: int = 200
    url: str = ""

    def read(self) -> bytes:
        return json.dumps(self.body).encode()

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class SuccessfulFrontendOpener:
    """Offline FAPI boundary with only the approved normal-token flow."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **_kwargs: object) -> _JsonResponse:
        self.requests.append(request)
        path = urlsplit(request.full_url).path
        session = {
            "object": "session",
            "id": "sess_synthetic_sensitive_identifier",
            "status": "active",
            "user_id": "user_synthetic_sensitive_identifier",
            "user": {"id": "user_synthetic_sensitive_identifier"},
        }
        sign_in = {
            "object": "sign_in_attempt",
            "status": "complete",
            "created_session_id": "sess_synthetic_sensitive_identifier",
            "user_data": {"id": "user_synthetic_sensitive_identifier"},
        }
        client = {
            "object": "client",
            "id": "client_synthetic",
            "sessions": [session],
            "sign_in": sign_in,
        }
        responses = {
            "/v1/dev_browser": {
                "object": "dev_browser",
                "token": "dev_browser_synthetic",
            },
            "/v1/client": client,
            "/v1/client/sign_ins": client,
            "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens": {
                "object": "token",
                "jwt": self.token,
            },
        }
        if path not in responses:
            raise AssertionError(f"unsupported Frontend API operation: {path}")
        response = responses[path]
        return _JsonResponse({**response, "response": response}, url=request.full_url)


@dataclass
class _Ticket:
    id: str = "ticket_synthetic_sensitive_material"
    token: str = "ticket_synthetic_one_use_credential"
    url: str = "https://development-synthetic.clerk.accounts.dev/sign-in-tokens/ticket_synthetic_sensitive_identifier"


def configure_successful_provider(
    transport: RecordingTransport,
) -> tuple[list[TicketRequest], list[dict[str, object]]]:
    ticket_requests: list[TicketRequest] = []
    revocations: list[dict[str, object]] = []

    def create_ticket(**kwargs: object) -> _Ticket:
        request = cast(TicketRequest, kwargs["request"])
        assert request.user_id == "user_synthetic_sensitive_identifier"
        assert request.expires_in_seconds == 60
        ticket_requests.append(request)
        transport.events.append(("ticket-create", None))
        return _Ticket()

    def revoke_resource(**kwargs: object) -> None:
        revocations.append(kwargs)
        transport.events.append(("revoke", kwargs))

    transport.create = create_ticket  # type: ignore[method-assign]
    transport.revoke = revoke_resource  # type: ignore[method-assign]
    return ticket_requests, revocations


def run_successful_frontend_flow(
    monkeypatch: MonkeyPatch,
    *,
    claims: dict[str, object],
    verifier_rejects: bool = False,
) -> tuple[object, RecordingTransport, SuccessfulFrontendOpener, list[HttpRequest]]:
    transport = RecordingTransport()
    configure_successful_provider(transport)
    opener = SuccessfulFrontendOpener(synthetic_token(claims))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_handlers: opener)
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


def test_ticket_flow_uses_fixed_origin_and_exact_sixty_second_ticket(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """The first FAPI operation exposes the fixed-origin, same-instance contract."""
    clerk = RecordingTransport()
    ticket_requests: list[object] = []
    frontend_requests: list[urllib.request.Request] = []

    @dataclass
    class Ticket:
        id: str = "ticket_synthetic_sensitive_material"
        token: str = "ticket_synthetic_one_use_credential"
        url: str = "https://development-synthetic.clerk.accounts.dev/sign-in-tokens/ticket_synthetic_sensitive_identifier"

    def create_ticket(**kwargs: object) -> Ticket:
        ticket_requests.append(kwargs["request"])
        return Ticket()

    class FailingOpener:
        def open(self, request: urllib.request.Request, **_kwargs: object) -> NoReturn:
            frontend_requests.append(request)
            raise SensitiveSyntheticError(" ".join(SENSITIVE_VALUES))

    clerk.create = create_ticket  # type: ignore[method-assign]
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *_handlers: FailingOpener()
    )
    session = validate_with(clerk)

    caplog.set_level(logging.DEBUG)
    with pytest.raises(development_session.ClerkFlowFailure) as raised:
        session.create_verified_token()
    assert_sanitized(raised.value, capsys, caplog)

    request = cast(TicketRequest, ticket_requests[0])
    assert request.user_id == "user_synthetic_sensitive_identifier"
    assert request.expires_in_seconds == 60
    assert len(frontend_requests) == 1
    assert frontend_requests[0].full_url.startswith(
        "https://development-synthetic.clerk.accounts.dev/"
    )
    assert frontend_requests[0].get_header("Origin") == "http://localhost:3000"


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

    class FailingOpener:
        def open(self, _request: urllib.request.Request, **_kwargs: object) -> NoReturn:
            raise SensitiveSyntheticError("ticket exchange failed")

    clerk.create = create_ticket  # type: ignore[method-assign]
    clerk.revoke = revoke_ticket  # type: ignore[method-assign]
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *_handlers: FailingOpener()
    )
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
    paths = [urlsplit(request.full_url).path for request in opener.requests]
    assert paths == [
        "/v1/dev_browser",
        "/v1/client",
        "/v1/client/sign_ins",
        "/v1/client/sessions/sess_synthetic_sensitive_identifier/tokens",
    ]
    assert {urlsplit(request.full_url).netloc for request in opener.requests} == {
        "development-synthetic.clerk.accounts.dev"
    }
    assert all(
        request.get_header("Clerk-api-version") == "2026-05-12"
        for request in opener.requests
    )
    assert all(
        "__clerk_api_version" not in request.full_url for request in opener.requests
    )
    assert all("/tokens/" not in path for path in paths)
    assert all(
        request.get_header("Origin") == "http://localhost:3000"
        for request in opener.requests
    )
    sign_in_request = opener.requests[2]
    assert parse_qs(cast(bytes, sign_in_request.data).decode()) == {
        "strategy": ["ticket"],
        "ticket": ["ticket_synthetic_one_use_credential"],
    }
    assert [event[0] for event in transport.events] == [
        "instance-settings",
        "user-get",
        "ticket-create",
        "jwks-get",
        "revoke",
    ]
    assert transport.events[-1] == (
        "revoke",
        {"session_id": "sess_synthetic_sensitive_identifier"},
    )


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
