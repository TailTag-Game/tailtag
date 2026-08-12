"""Local settings configuration contract."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENVIRONMENT_FILE = SERVICE_ROOT / ".env"


@contextmanager
def local_environment(contents: str) -> Iterator[None]:
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


def import_local_settings() -> subprocess.CompletedProcess[str]:
    """Import local settings in an environment without inherited configuration."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from django.conf import settings; "
                "print(settings.DATABASES['default']['HOST'])"
            ),
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
