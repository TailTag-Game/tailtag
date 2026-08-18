"""Shared Clerk settings configuration assertions and fixtures."""

from __future__ import annotations

import subprocess
from typing import NoReturn

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.core.exceptions import ImproperlyConfigured

from config.settings import clerk as clerk_settings

INVALID_AUTHORIZED_PARTY_ORIGINS = (
    "",
    " , ",
    "ftp://app.example.test",
    "https://app.example.test/path",
    "https://app.example.test/",
    "https://user:password@app.example.test",
    "https://app.example.test?unexpected=query",
    "https://app.example.test?",
    "https://app.example.test#unexpected-fragment",
    "https://app.example.test#",
    r"https://app.example.test\not-a-path",
    "https://exa mple.test",
)

INVALID_AUTHORIZED_PARTY_ORIGIN_IDS = (
    "empty",
    "whitespace-only",
    "unsupported-scheme",
    "non-root-path",
    "trailing-slash",
    "credentials",
    "query",
    "empty-query",
    "fragment",
    "empty-fragment",
    "backslash-authority-or-path",
    "space-in-hostname",
)

_UNSUPPORTED_JWT_KEY_SENTINEL = "unsupported-public-key-sentinel"
_UNSUPPORTED_ALGORITHM_REASON = "unsupported-algorithm-reason-sentinel"


@pytest.fixture(scope="module", name="valid_clerk_public_key")
def valid_clerk_public_key() -> str:
    """Create an ephemeral RSA public key suitable only for settings tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


@pytest.fixture(scope="module", name="non_rsa_public_key")
def non_rsa_public_key() -> str:
    """Create an ephemeral PEM public key that must not satisfy the RSA contract."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def assert_sanitized_configuration_error(
    completed: subprocess.CompletedProcess[str],
    name: str | tuple[str, ...],
    supplied_value: str,
) -> None:
    """Configuration errors may identify a variable but never disclose its value."""
    assert completed.returncode != 0
    assert "ImproperlyConfigured" in completed.stderr
    names = (name,) if isinstance(name, str) else name
    assert any(candidate in completed.stderr for candidate in names)
    if supplied_value:
        assert supplied_value not in completed.stderr


def assert_unsupported_public_key_loader_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify loader failures are mapped to the public JWT-key configuration error."""

    def raise_unsupported_algorithm(*args: object, **kwargs: object) -> NoReturn:
        raise UnsupportedAlgorithm(_UNSUPPORTED_ALGORITHM_REASON)

    monkeypatch.setattr(
        clerk_settings.serialization,
        "load_pem_public_key",
        raise_unsupported_algorithm,
    )

    with pytest.raises(ImproperlyConfigured) as raised:
        clerk_settings.load_clerk_authentication_configuration(
            {
                "CLERK_AUTHENTICATION_ENABLED": "true",
                "CLERK_JWT_KEY": _UNSUPPORTED_JWT_KEY_SENTINEL,
                "CLERK_AUTHORIZED_PARTIES": "https://app.example.test",
            }
        )

    assert str(raised.value) == "Invalid environment variable: CLERK_JWT_KEY"
    assert _UNSUPPORTED_JWT_KEY_SENTINEL not in str(raised.value)
    assert _UNSUPPORTED_ALGORITHM_REASON not in str(raised.value)
