"""Offline safety contract for the Clerk Development session adapter."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

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


def prohibit_network(monkeypatch: MonkeyPatch) -> None:
    """The adapter may contact Clerk only through explicitly installed fakes."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError(
            "ordinary Clerk Development adapter tests must remain offline"
        )

    monkeypatch.setattr(socket, "create_connection", no_network)


def assert_sanitized(value: object) -> None:
    rendered = repr(value)
    for sensitive in SENSITIVE_VALUES:
        assert sensitive not in rendered


def test_non_development_secret_form_is_rejected_before_any_provider_connection(
    monkeypatch: MonkeyPatch,
) -> None:
    prohibit_network(monkeypatch)

    with pytest.raises(Exception) as raised:
        development_session.ClerkDevelopmentSession.validate(
            secret="sk_live_synthetic_credential_material",
            user_id="user_synthetic_sensitive_identifier",
        )

    assert "credential form invalid" in str(raised.value)
    assert_sanitized(raised.value)


def test_adapter_state_does_not_render_credential_or_provider_identifiers() -> None:
    """Invocation-local secrets and identifiers cannot leak through diagnostics."""
    session = development_session.ClerkDevelopmentSession(
        _secret="sk_test_synthetic_credential_material",
        _user_id="user_synthetic_sensitive_identifier",
        _ticket_id="ticket_synthetic_sensitive_material",
        _session_id="sess_synthetic_sensitive_identifier",
        _token="eyJsynthetic.header.payload",
    )

    assert_sanitized(session)


def test_adapter_has_only_fixed_development_origin_and_lifetime_constants() -> None:
    """Callers cannot choose an arbitrary browser origin or token lifetime."""
    assert development_session.TOOLING_ORIGIN == "http://localhost:3000"
    assert development_session.SIGN_IN_TICKET_LIFETIME_SECONDS == 60
    assert development_session.MAX_SESSION_TOKEN_LIFETIME_SECONDS == 60
