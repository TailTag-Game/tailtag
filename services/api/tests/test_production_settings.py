"""Production settings startup validation tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

REQUIRED_SETTINGS = (
    "DATABASE_URL",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
)

VALID_ENVIRONMENT = {
    "DATABASE_URL": "postgresql://tailtag:password@localhost:5432/tailtag",
    "DJANGO_SECRET_KEY": "test-secret-key",
    "DJANGO_ALLOWED_HOSTS": "api.example.test,admin.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://api.example.test,https://admin.example.test",
}


def run_settings_import(
    environment: Mapping[str, str], *, inspect_clerk_configuration: bool = False
) -> subprocess.CompletedProcess[str]:
    """Import production settings in a new process with the supplied environment."""
    inspection = (
        "from dataclasses import is_dataclass; "
        "from django.conf import settings; "
        "configuration = settings.CLERK_AUTHENTICATION; "
        "print('none' if configuration is None else '|'.join(("
        "type(configuration).__name__, "
        "repr(configuration.authorized_parties), "
        "str(is_dataclass(configuration)), "
        "str(configuration.__dataclass_params__.frozen), "
        "str(not hasattr(configuration, '__dict__')), "
        "repr(configuration)"
        ")))"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            inspection
            if inspect_clerk_configuration
            else "import config.settings.production",
        ],
        cwd=".",
        env={
            "PATH": os.environ["PATH"],
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
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


@pytest.fixture(scope="module")
def non_rsa_public_key() -> str:
    """Create an ephemeral PEM public key that cannot become a JWT trust anchor."""
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
    """Configuration errors may identify variables but must not disclose values."""
    assert completed.returncode != 0
    assert "ImproperlyConfigured" in completed.stderr
    names = (name,) if isinstance(name, str) else name
    assert any(candidate in completed.stderr for candidate in names)
    if supplied_value:
        assert supplied_value not in completed.stderr


@pytest.mark.parametrize("missing_variable", REQUIRED_SETTINGS)
def test_production_settings_reject_each_missing_required_value(
    missing_variable: str,
) -> None:
    """A production process must not boot without a required configuration value."""
    environment = {
        key: value
        for key, value in VALID_ENVIRONMENT.items()
        if key != missing_variable
    }

    completed = run_settings_import(environment)

    assert completed.returncode != 0
    assert missing_variable in completed.stderr


def test_production_settings_accept_all_required_values() -> None:
    """A complete non-secret production configuration can initialize settings."""
    completed = run_settings_import(VALID_ENVIRONMENT)

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("invalid_value", (",", "   "))
@pytest.mark.parametrize(
    "setting_name", ("DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS")
)
def test_production_settings_reject_required_lists_without_values(
    setting_name: str, invalid_value: str
) -> None:
    """Required comma-separated settings must contain at least one value."""
    environment = {**VALID_ENVIRONMENT, setting_name: invalid_value}

    completed = run_settings_import(environment)

    assert completed.returncode != 0
    assert setting_name in completed.stderr


@pytest.mark.parametrize(
    "environment",
    (
        VALID_ENVIRONMENT,
        {**VALID_ENVIRONMENT, "CLERK_AUTHENTICATION_ENABLED": "false"},
        {**VALID_ENVIRONMENT, "CLERK_AUTHENTICATION_ENABLED": "FALSE"},
    ),
    ids=(
        "missing-defaults-disabled",
        "explicitly-disabled",
        "case-insensitive-disabled",
    ),
)
def test_production_settings_disable_clerk_authentication_by_default(
    environment: Mapping[str, str],
) -> None:
    """Production keeps Clerk request authentication off until explicitly enabled."""
    completed = run_settings_import(environment, inspect_clerk_configuration=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "none\n"


def test_production_settings_reject_invalid_clerk_enabled_flag_without_echoing_value() -> (
    None
):
    """An unrecognized enabled flag cannot silently select a security posture."""
    invalid_value = "not-a-clerk-boolean-sentinel"
    completed = run_settings_import(
        {**VALID_ENVIRONMENT, "CLERK_AUTHENTICATION_ENABLED": invalid_value},
        inspect_clerk_configuration=True,
    )

    assert_sanitized_configuration_error(
        completed, "CLERK_AUTHENTICATION_ENABLED", invalid_value
    )


@pytest.mark.parametrize(
    "additional_value",
    (
        ("CLERK_JWT_KEY", "ignored-key-sentinel"),
        ("CLERK_AUTHORIZED_PARTIES", "https://ignored-origin.invalid"),
    ),
)
def test_production_settings_reject_clerk_values_when_authentication_is_disabled(
    additional_value: tuple[str, str],
) -> None:
    """Disabled production authentication refuses Clerk values rather than ignoring them."""
    variable_name, supplied_value = additional_value
    completed = run_settings_import(
        {
            **VALID_ENVIRONMENT,
            "CLERK_AUTHENTICATION_ENABLED": "false",
            variable_name: supplied_value,
        },
        inspect_clerk_configuration=True,
    )

    assert_sanitized_configuration_error(
        completed,
        (
            "CLERK_AUTHENTICATION_ENABLED",
            "CLERK_JWT_KEY",
            "CLERK_AUTHORIZED_PARTIES",
        ),
        supplied_value,
    )


@pytest.mark.parametrize(
    "missing_name, additional_environment",
    (
        (
            "CLERK_JWT_KEY",
            {
                "CLERK_AUTHENTICATION_ENABLED": "true",
                "CLERK_AUTHORIZED_PARTIES": "https://app.example.test",
            },
        ),
        (
            "CLERK_AUTHORIZED_PARTIES",
            {"CLERK_AUTHENTICATION_ENABLED": "true"},
        ),
    ),
    ids=("jwt-key", "authorized-parties"),
)
def test_production_settings_require_each_enabled_clerk_value(
    missing_name: str, additional_environment: Mapping[str, str]
) -> None:
    """Enabled production configuration fails closed until both inputs are present."""
    completed = run_settings_import(
        {**VALID_ENVIRONMENT, **additional_environment},
        inspect_clerk_configuration=True,
    )

    assert_sanitized_configuration_error(completed, missing_name, "")


@pytest.mark.parametrize("key_fixture_name", ("malformed", "non-rsa"))
def test_production_settings_reject_malformed_or_non_rsa_jwt_public_key(
    key_fixture_name: str, non_rsa_public_key: str
) -> None:
    """Production accepts only a parseable RSA public key as an offline trust anchor."""
    supplied_key = (
        "malformed-public-key-sentinel"
        if key_fixture_name == "malformed"
        else non_rsa_public_key
    )
    completed = run_settings_import(
        {
            **VALID_ENVIRONMENT,
            "CLERK_AUTHENTICATION_ENABLED": "TrUe",
            "CLERK_JWT_KEY": supplied_key,
            "CLERK_AUTHORIZED_PARTIES": "https://app.example.test",
        },
        inspect_clerk_configuration=True,
    )

    assert_sanitized_configuration_error(completed, "CLERK_JWT_KEY", supplied_key)


@pytest.mark.parametrize(
    "origins",
    (
        "",
        " , ",
        "ftp://app.example.test",
        "https://app.example.test/path",
        "https://user:password@app.example.test",
        "https://app.example.test?unexpected=query",
        "https://app.example.test#unexpected-fragment",
    ),
    ids=(
        "empty",
        "whitespace-only",
        "unsupported-scheme",
        "non-root-path",
        "credentials",
        "query",
        "fragment",
    ),
)
def test_production_settings_reject_empty_or_invalid_authorized_party_origins(
    valid_clerk_public_key: str, origins: str
) -> None:
    """An authorized party must be a plain HTTP(S) origin with no hidden parts."""
    completed = run_settings_import(
        {
            **VALID_ENVIRONMENT,
            "CLERK_AUTHENTICATION_ENABLED": "TrUe",
            "CLERK_JWT_KEY": valid_clerk_public_key,
            "CLERK_AUTHORIZED_PARTIES": origins,
        },
        inspect_clerk_configuration=True,
    )

    assert_sanitized_configuration_error(completed, "CLERK_AUTHORIZED_PARTIES", origins)


def test_production_settings_expose_immutable_clerk_configuration_when_enabled(
    valid_clerk_public_key: str,
) -> None:
    """Complete production inputs create a frozen configuration without key repr leakage."""
    completed = run_settings_import(
        {
            **VALID_ENVIRONMENT,
            "CLERK_AUTHENTICATION_ENABLED": "TrUe",
            "CLERK_JWT_KEY": valid_clerk_public_key,
            "CLERK_AUTHORIZED_PARTIES": "https://app.example.test,http://localhost:3000",
        },
        inspect_clerk_configuration=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith(
        "ClerkVerificationConfiguration|('https://app.example.test', "
        "'http://localhost:3000')|True|True|True|"
    )
    assert valid_clerk_public_key.splitlines()[1] not in completed.stdout
