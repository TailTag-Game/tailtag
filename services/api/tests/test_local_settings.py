"""Local settings configuration contract."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.clerk_settings_contract import (
    INVALID_AUTHORIZED_PARTY_ORIGIN_IDS,
    INVALID_AUTHORIZED_PARTY_ORIGINS,
    assert_sanitized_configuration_error,
    assert_unsupported_public_key_loader_is_sanitized,
)
from tests.clerk_settings_contract import (
    non_rsa_public_key as _non_rsa_public_key,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from tests.clerk_settings_contract import (
    valid_clerk_public_key as _valid_clerk_public_key,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)

SERVICE_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENVIRONMENT_FILE = SERVICE_ROOT / ".env"


@contextmanager
def local_environment(contents: str) -> Generator[None]:
    """Provide a temporary native-development environment file."""
    previous_contents = (
        LOCAL_ENVIRONMENT_FILE.read_text() if LOCAL_ENVIRONMENT_FILE.exists() else None
    )
    LOCAL_ENVIRONMENT_FILE.write_text(contents)
    try:
        yield
    finally:
        if previous_contents is None:
            LOCAL_ENVIRONMENT_FILE.unlink()
        else:
            LOCAL_ENVIRONMENT_FILE.write_text(previous_contents)


def import_local_settings(
    *, inspect_clerk_configuration: bool = False
) -> subprocess.CompletedProcess[str]:
    """Import local settings in an environment without inherited configuration."""
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
            else "from django.conf import settings; print(settings.DATABASES['default']['HOST'])",
        ],
        cwd=SERVICE_ROOT,
        env={
            "PATH": os.environ["PATH"],
            "DJANGO_SETTINGS_MODULE": "config.settings.local",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def dotenv_value(value: str) -> str:
    """Encode a configuration value without writing secret-looking test text verbatim."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def local_dotenv(*extra_lines: str) -> str:
    """Return the minimum local configuration plus Clerk-specific test values."""
    return "\n".join(
        (
            "DATABASE_URL=postgresql://local_user:local_password@127.0.0.1:5432/local_db",
            "DJANGO_SECRET_KEY=local-secret-key",
            *extra_lines,
            "",
        )
    )


def test_local_settings_load_database_url_from_dotenv() -> None:
    """Native settings use the database URL from the ignored local environment file."""
    with local_environment(
        "DATABASE_URL=postgresql://local_user:local_password@127.0.0.1:5432/local_db\n"
        "DJANGO_SECRET_KEY=local-secret-key\n"
    ):
        completed = import_local_settings()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "127.0.0.1\n"


def test_local_settings_reject_missing_database_url_without_echoing_secret() -> None:
    """Native settings identify a missing database URL without disclosing another value."""
    with local_environment("DJANGO_SECRET_KEY=local-secret-that-must-not-leak\n"):
        completed = import_local_settings()

    assert completed.returncode != 0
    assert "DATABASE_URL" in completed.stderr
    assert "local-secret-that-must-not-leak" not in completed.stderr


@pytest.mark.parametrize(
    "database_url, expected_message",
    (
        ("mysql://local_user:local_password@127.0.0.1:5432/local_db", "scheme"),
        ("postgresql://local_user:local_password@127.0.0.1", "host and database"),
    ),
)
def test_local_settings_reject_invalid_database_url_without_echoing_it(
    database_url: str, expected_message: str
) -> None:
    """Native settings show a safe diagnostic when the database URL is invalid."""
    with local_environment(
        f"DATABASE_URL={database_url}\nDJANGO_SECRET_KEY=local-secret-key\n"
    ):
        completed = import_local_settings()

    assert completed.returncode != 0
    assert "DATABASE_URL" in completed.stderr
    assert expected_message in completed.stderr
    assert database_url not in completed.stderr


@pytest.mark.parametrize(
    "enabled_line",
    ("", "CLERK_AUTHENTICATION_ENABLED=false", "CLERK_AUTHENTICATION_ENABLED=FALSE"),
    ids=(
        "missing-defaults-disabled",
        "explicitly-disabled",
        "case-insensitive-disabled",
    ),
)
def test_local_settings_disable_clerk_authentication_by_default(
    enabled_line: str,
) -> None:
    """Local settings expose no Clerk authentication configuration until enabled."""
    extra_lines = (enabled_line,) if enabled_line else ()
    with local_environment(local_dotenv(*extra_lines)):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "none\n"


def test_local_settings_reject_invalid_clerk_enabled_flag_without_echoing_value() -> (
    None
):
    """A typo cannot silently select an authentication configuration."""
    invalid_value = "not-a-clerk-boolean-sentinel"
    with local_environment(
        local_dotenv(f"CLERK_AUTHENTICATION_ENABLED={invalid_value}")
    ):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert_sanitized_configuration_error(
        completed, "CLERK_AUTHENTICATION_ENABLED", invalid_value
    )


@pytest.mark.parametrize(
    "additional_value",
    (
        "CLERK_JWT_KEY=ignored-key-sentinel",
        "CLERK_AUTHORIZED_PARTIES=https://ignored-origin.invalid",
    ),
)
def test_local_settings_reject_clerk_values_when_authentication_is_disabled(
    additional_value: str,
) -> None:
    """Disabled configuration cannot silently retain unused authentication values."""
    supplied_value = additional_value.partition("=")[2]
    with local_environment(
        local_dotenv("CLERK_AUTHENTICATION_ENABLED=false", additional_value)
    ):
        completed = import_local_settings(inspect_clerk_configuration=True)

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
    "missing_name, extra_lines",
    (
        (
            "CLERK_JWT_KEY",
            (
                "CLERK_AUTHENTICATION_ENABLED=true",
                "CLERK_AUTHORIZED_PARTIES=https://app.example.test",
            ),
        ),
        (
            "CLERK_AUTHORIZED_PARTIES",
            ("CLERK_AUTHENTICATION_ENABLED=true",),
        ),
    ),
    ids=("jwt-key", "authorized-parties"),
)
def test_local_settings_require_each_enabled_clerk_value(
    missing_name: str,
    extra_lines: tuple[str, ...],
    valid_clerk_public_key: str,
) -> None:
    """Enabling Clerk is fail-closed until both verification inputs are present."""
    required_inputs = extra_lines
    if missing_name == "CLERK_AUTHORIZED_PARTIES":
        required_inputs = (
            *extra_lines,
            f'CLERK_JWT_KEY="{dotenv_value(valid_clerk_public_key)}"',
        )

    with local_environment(local_dotenv(*required_inputs)):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert_sanitized_configuration_error(completed, missing_name, "")


@pytest.mark.parametrize(
    "key_fixture_name",
    ("malformed", "non-rsa"),
)
def test_local_settings_reject_malformed_or_non_rsa_jwt_public_key(
    key_fixture_name: str,
    non_rsa_public_key: str,
) -> None:
    """Only a parseable RSA public key can become the offline trust anchor."""
    supplied_key = (
        "malformed-public-key-sentinel"
        if key_fixture_name == "malformed"
        else non_rsa_public_key
    )
    with local_environment(
        local_dotenv(
            "CLERK_AUTHENTICATION_ENABLED=TrUe",
            f'CLERK_JWT_KEY="{dotenv_value(supplied_key)}"',
            "CLERK_AUTHORIZED_PARTIES=https://app.example.test",
        )
    ):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert_sanitized_configuration_error(completed, "CLERK_JWT_KEY", supplied_key)


@pytest.mark.parametrize(
    "origins",
    INVALID_AUTHORIZED_PARTY_ORIGINS,
    ids=INVALID_AUTHORIZED_PARTY_ORIGIN_IDS,
)
def test_local_settings_reject_empty_or_invalid_authorized_party_origins(
    valid_clerk_public_key: str, origins: str
) -> None:
    """Every configured authorized party is a plain HTTP(S) origin."""
    with local_environment(
        local_dotenv(
            "CLERK_AUTHENTICATION_ENABLED=TrUe",
            f'CLERK_JWT_KEY="{dotenv_value(valid_clerk_public_key)}"',
            f'CLERK_AUTHORIZED_PARTIES="{dotenv_value(origins)}"',
        )
    ):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert_sanitized_configuration_error(completed, "CLERK_AUTHORIZED_PARTIES", origins)


def test_local_settings_sanitize_unsupported_public_key_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local Clerk settings map loader-specific crypto errors to the JWT key."""
    assert_unsupported_public_key_loader_is_sanitized(monkeypatch)


def test_local_settings_expose_immutable_clerk_configuration_when_enabled(
    valid_clerk_public_key: str,
) -> None:
    """A complete valid local configuration creates a secret-safe frozen object."""
    with local_environment(
        local_dotenv(
            "CLERK_AUTHENTICATION_ENABLED=TrUe",
            f'CLERK_JWT_KEY="{dotenv_value(valid_clerk_public_key)}"',
            "CLERK_AUTHORIZED_PARTIES=https://app.example.test,http://localhost:3000",
        )
    ):
        completed = import_local_settings(inspect_clerk_configuration=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith(
        "ClerkVerificationConfiguration|('https://app.example.test', "
        "'http://localhost:3000')|True|True|True|"
    )
    assert valid_clerk_public_key.splitlines()[1] not in completed.stdout
