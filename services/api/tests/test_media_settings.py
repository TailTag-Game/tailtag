"""Acceptance contract for media storage selection and fail-closed settings."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

import pytest
from django.core.files.storage import default_storage

from tests.test_production_settings import VALID_ENVIRONMENT, run_settings_import

MEDIA_ENVIRONMENT = {
    "MEDIA_STORAGE_ENDPOINT_URL": "https://media.example.test",
    "MEDIA_STORAGE_BUCKET_NAME": "development-media",
    "MEDIA_STORAGE_REGION": "auto",
    "MEDIA_STORAGE_ACCESS_KEY_ID": "test-access-key",
    "MEDIA_STORAGE_SECRET_ACCESS_KEY": "test-" + "secret-" + "value",
}


def inspect_storage_settings(
    settings_module: str, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Load settings in isolation and print only non-secret storage facts."""
    command = (
        "from django.conf import settings; "
        "print('|'.join((settings.STORAGES['default']['BACKEND'], "
        "str(settings.STORAGES['default'].get('OPTIONS', {}).get('url_expiry_seconds', '')))))"
    )
    return subprocess.run(
        [sys.executable, "-c", command],
        cwd=".",
        env={
            "PATH": os.environ["PATH"],
            "DJANGO_SETTINGS_MODULE": settings_module,
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def assert_configuration_values_are_sanitized(
    standard_error: str, environment: Mapping[str, str]
) -> None:
    """Require startup failures to name a variable, never render its supplied values."""
    assert all(value not in standard_error for value in environment.values() if value)


@pytest.mark.parametrize("missing_variable", tuple(MEDIA_ENVIRONMENT))
def test_production_settings_require_each_media_variable_without_echoing_values(
    missing_variable: str,
) -> None:
    environment = {**VALID_ENVIRONMENT, **MEDIA_ENVIRONMENT}
    del environment[missing_variable]

    completed = run_settings_import(environment)

    assert completed.returncode != 0
    assert missing_variable in completed.stderr
    assert_configuration_values_are_sanitized(completed.stderr, environment)


@pytest.mark.parametrize(
    "invalid_endpoint",
    (
        "http://media.example.test",
        "https://access:password@media.example.test",
        "https://media.example.test/?query=forbidden",
        "https://media.example.test/#fragment",
        "https://media.example.test/media/path",
        "https://media.example.test:not-a-port",
        "https://media.example.test:99999",
        "https://media.example.test with-space",
    ),
)
def test_production_settings_reject_non_root_or_non_https_media_endpoints_without_echoing_them(
    invalid_endpoint: str,
) -> None:
    environment = {
        **VALID_ENVIRONMENT,
        **MEDIA_ENVIRONMENT,
        "MEDIA_STORAGE_ENDPOINT_URL": invalid_endpoint,
    }
    completed = run_settings_import(environment)

    assert completed.returncode != 0
    assert "MEDIA_STORAGE_ENDPOINT_URL" in completed.stderr
    assert_configuration_values_are_sanitized(completed.stderr, environment)


@pytest.mark.parametrize(
    "variable",
    (
        "MEDIA_STORAGE_BUCKET_NAME",
        "MEDIA_STORAGE_REGION",
        "MEDIA_STORAGE_ACCESS_KEY_ID",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY",
    ),
)
@pytest.mark.parametrize("invalid_value", ("", "\t \t"), ids=("empty", "whitespace"))
def test_production_settings_reject_empty_or_whitespace_media_credentials(
    variable: str, invalid_value: str
) -> None:
    environment = {**VALID_ENVIRONMENT, **MEDIA_ENVIRONMENT, variable: invalid_value}

    completed = run_settings_import(environment)

    assert completed.returncode != 0
    assert variable in completed.stderr
    assert_configuration_values_are_sanitized(completed.stderr, environment)


def test_local_settings_select_filesystem_media_storage() -> None:
    environment = {
        "DATABASE_URL": "postgresql://local_user:local_password@127.0.0.1:5432/local_db",
        "DJANGO_SECRET_KEY": "local-secret-key",
    }

    completed = inspect_storage_settings("config.settings.local", environment)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "django.core.files.storage.FileSystemStorage|\n"


def test_production_settings_select_s3_media_storage_with_fixed_read_expiry() -> None:
    completed = inspect_storage_settings(
        "config.settings.production", {**VALID_ENVIRONMENT, **MEDIA_ENVIRONMENT}
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "media.storage.S3MediaStorage|600\n"


def test_ordinary_pytest_storage_is_in_memory() -> None:
    assert default_storage.__class__.__name__ == "InMemoryStorage"
