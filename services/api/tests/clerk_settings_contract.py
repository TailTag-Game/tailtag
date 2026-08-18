"""Shared Clerk settings configuration assertions and fixtures."""

from __future__ import annotations

import subprocess

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

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

UNSUPPORTED_ALGORITHM_JWT_KEY_SENTINEL = "unsupported-public-key-sentinel"
UNSUPPORTED_ALGORITHM_REASON = "unsupported-algorithm-reason-sentinel"
UNSUPPORTED_ALGORITHM_PRE_IMPORT_PATCH = (
    "from cryptography.exceptions import UnsupportedAlgorithm; "
    "from config.settings import clerk as clerk_settings; "
    "clerk_settings.serialization.load_pem_public_key = "
    "lambda *args, **kwargs: (_ for _ in ()).throw("
    "UnsupportedAlgorithm('unsupported-' + 'algorithm-' + 'reason-' + 'sentinel')); "
)


def capture_improperly_configured_subprocess_script(command: str) -> str:
    """Return a child script that exposes only its final configuration error."""
    return (
        "import sys\n"
        "from django.core.exceptions import ImproperlyConfigured\n"
        "try:\n"
        f"    {command}\n"
        "except ImproperlyConfigured as error:\n"
        "    print(f'{type(error).__name__}: {error}', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
    )


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
    *additional_non_disclosable_values: str,
) -> None:
    """Configuration errors may identify a variable but never disclose its value."""
    assert completed.returncode != 0
    assert "ImproperlyConfigured" in completed.stderr
    names = (name,) if isinstance(name, str) else name
    assert any(candidate in completed.stderr for candidate in names)
    for value in (supplied_value, *additional_non_disclosable_values):
        if value:
            assert value not in completed.stderr
