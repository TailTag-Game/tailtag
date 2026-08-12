"""Production settings startup validation tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

import pytest

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
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Import production settings in a new process with the supplied environment."""
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=".",
        env={"PATH": os.environ["PATH"], **environment},
        capture_output=True,
        text=True,
        check=False,
    )


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
