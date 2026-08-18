"""Offline behavioural contract for the Clerk Development session adapter."""

from __future__ import annotations

import http.client
import logging
import socket
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

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
    sign_in_url: str = "https://development.clerk.example"


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

    def revoke(self, **kwargs: object) -> NoReturn:
        raise AssertionError(f"unexpected cleanup before a resource exists: {kwargs!r}")


def validate_with(transport: RecordingTransport) -> object:
    """The planned public transport seam keeps provider tests layout-independent."""
    return development_session.ClerkDevelopmentSession.validate(
        secret="sk_test_synthetic_credential_material",
        user_id="user_synthetic_sensitive_identifier",
        transport=transport,
    )


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
) -> None:
    """The first FAPI operation exposes the fixed-origin, same-instance contract."""
    clerk = RecordingTransport()
    ticket_requests: list[object] = []
    frontend_requests: list[urllib.request.Request] = []

    @dataclass
    class Ticket:
        id: str = "ticket_synthetic_sensitive_material"

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

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()

    request = cast(TicketRequest, ticket_requests[0])
    assert request.user_id == "user_synthetic_sensitive_identifier"
    assert request.expires_in_seconds == 60
    assert len(frontend_requests) == 1
    assert frontend_requests[0].full_url.startswith(
        "https://development.clerk.example/"
    )
    assert frontend_requests[0].get_header("Origin") == "http://localhost:3000"


def test_cleanup_revokes_an_unconsumed_ticket_but_never_deletes_persistent_user(
    monkeypatch: MonkeyPatch,
) -> None:
    clerk = RecordingTransport()
    revoked: list[dict[str, object]] = []

    @dataclass
    class Ticket:
        id: str = "ticket_synthetic_sensitive_material"

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

    with pytest.raises(development_session.ClerkFlowFailure):
        session.create_verified_token()
    session.cleanup()

    assert revoked == [{"sign_in_token_id": "ticket_synthetic_sensitive_material"}]
