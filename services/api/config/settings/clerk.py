"""Fail-closed Clerk request-authentication configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NoReturn
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from django.core.exceptions import ImproperlyConfigured

from authentication.clerk import ClerkVerificationConfiguration

_ENABLED_VARIABLE = "CLERK_AUTHENTICATION_ENABLED"
_JWT_KEY_VARIABLE = "CLERK_JWT_KEY"
_AUTHORIZED_PARTIES_VARIABLE = "CLERK_AUTHORIZED_PARTIES"


def load_clerk_authentication_configuration(
    environment: Mapping[str, str],
) -> ClerkVerificationConfiguration | None:
    """Load a complete Clerk verification configuration or disable authentication."""
    enabled = _authentication_is_enabled(environment)
    if not enabled:
        _reject_disabled_verification_values(environment)
        return None

    jwt_key = _required_value(environment, _JWT_KEY_VARIABLE)
    authorized_parties = _authorized_parties(
        _required_value(environment, _AUTHORIZED_PARTIES_VARIABLE)
    )
    _validate_rsa_public_key(jwt_key)
    return ClerkVerificationConfiguration(
        jwt_key=jwt_key,
        authorized_parties=authorized_parties,
    )


def _authentication_is_enabled(environment: Mapping[str, str]) -> bool:
    value = environment.get(_ENABLED_VARIABLE)
    if value is None:
        return False
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    _invalid_variable(_ENABLED_VARIABLE)


def _reject_disabled_verification_values(environment: Mapping[str, str]) -> None:
    for name in (_JWT_KEY_VARIABLE, _AUTHORIZED_PARTIES_VARIABLE):
        if name in environment:
            _invalid_variable(name)


def _required_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not value:
        _invalid_variable(name)
    return value


def _authorized_parties(value: str) -> tuple[str, ...]:
    parties = tuple(item.strip() for item in value.split(","))
    if not parties or any(
        not party or not _is_plain_origin(party) for party in parties
    ):
        _invalid_variable(_AUTHORIZED_PARTIES_VARIABLE)
    return parties


def _is_plain_origin(value: str) -> bool:
    if any(character.isspace() or character in {"?", "#", "\\"} for character in value):
        return False

    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False

    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and (port is None or port >= 0)
    ) and (
        parsed.username is None
        and parsed.password is None
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )


def _validate_rsa_public_key(value: str) -> None:
    try:
        public_key = serialization.load_pem_public_key(value.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError):
        _invalid_variable(_JWT_KEY_VARIABLE)
    if not isinstance(public_key, RSAPublicKey):
        _invalid_variable(_JWT_KEY_VARIABLE)


def _invalid_variable(name: str) -> NoReturn:
    raise ImproperlyConfigured(f"Invalid environment variable: {name}")
