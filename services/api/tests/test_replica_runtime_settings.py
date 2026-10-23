"""Replica database TLS options, migrate-only settings and build identity artifact (#355 U1)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import cast
from urllib.parse import quote

import pytest
from django.db import connection

from config.settings.base import database_from_url
from tests.process_support import minimal_environment

API_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = API_ROOT / "docker" / "write_build_identity.py"
SHA = "c070f413eec1518459f1fef21b471642765a54e9"
OTHER_SHA = "d" * 40
SECRET_QUERY_VALUE = "url-secret-must-not-leak"


# --- A4: database_from_url ---


def test_database_url_without_query_keeps_exact_existing_configuration() -> None:
    """Failure mode 10: adding option parsing must not alter Railway and local URLs."""
    assert database_from_url("postgresql://user:p%40ss@db.internal:5432/app") == {
        "ENGINE": "observability.postgresql",
        "NAME": "app",
        "USER": "user",
        "PASSWORD": "p@ss",
        "HOST": "db.internal",
        "PORT": "5432",
        "OPTIONS": {"connect_timeout": 5},
    }


def test_database_url_passes_only_the_three_tls_parameters_to_psycopg() -> None:
    """Failure mode 10: TLS parameters reach OPTIONS and nothing else does."""
    configuration = database_from_url(
        "postgresql://user:secret@db.internal:5432/app"
        "?sslmode=verify-full&sslrootcert=%2Fetc%2Fca.pem&channel_binding=require"
        "&application_name=other&options=-csearch_path%3Devil"
    )

    assert configuration["OPTIONS"] == {
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ca.pem",
        "channel_binding": "require",
    }


@pytest.mark.parametrize(
    "query",
    (
        pytest.param(
            f"sslmode=verify-full&sslmode={SECRET_QUERY_VALUE}", id="repeated-parameter"
        ),
        pytest.param("sslrootcert=", id="empty-value"),
    ),
)
def test_database_url_rejects_ambiguous_tls_parameters_without_echoing_the_url(
    query: str,
) -> None:
    """Failure mode 10: a repeated or empty TLS parameter fails with a fixed message."""
    url = f"postgresql://user:{SECRET_QUERY_VALUE}@db.internal:5432/app?{query}"

    with pytest.raises(ValueError) as caught:
        database_from_url(url)

    assert SECRET_QUERY_VALUE not in str(caught.value)
    assert "db.internal" not in str(caught.value)


# --- A5: migrate-only settings ---


def _run_with_migrate_settings(
    script: str, extra_environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    # replacement_target_binding resolves Path.home() at import. Windows needs
    # USERPROFILE for that; POSIX falls back to the password database.
    home = (
        {"USERPROFILE": os.environ["USERPROFILE"]}
        if "USERPROFILE" in os.environ
        else {}
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env={
            **minimal_environment(),
            **home,
            "DJANGO_SETTINGS_MODULE": "config.settings.migrate",
            **extra_environment,
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.django_db
def test_migrate_settings_run_migrations_with_only_database_url() -> None:
    """Failure mode 11: no runtime secret is read, no Clerk or media is loaded."""
    database = cast(dict[str, str], connection.settings_dict)
    url = (
        f"postgresql://{quote(database['USER'])}:{quote(database['PASSWORD'])}"
        f"@{database['HOST']}:{database['PORT']}/{database['NAME']}"
    )
    script = textwrap.dedent(
        """
        import django
        django.setup()
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured
        from django.core.management import call_command
        from health.configuration import validate_configuration

        call_command("migrate", check_unapplied=True, verbosity=0)
        assert settings.DEBUG is False
        assert settings.ALLOWED_HOSTS == [] and settings.CSRF_TRUSTED_ORIGINS == []
        assert not hasattr(settings, "CLERK_AUTHENTICATION")
        assert not hasattr(settings, "MEDIA_STORAGE_CONFIGURATION")
        try:
            validate_configuration()
        except ImproperlyConfigured:
            print("migrate-settings-ok")
        """
    )

    result = _run_with_migrate_settings(
        script,
        {
            "DATABASE_URL": url,
            # Any read of these would raise: they are malformed or incomplete on purpose.
            "CLERK_AUTHENTICATION_ENABLED": "true",
            "MEDIA_STORAGE_ENDPOINT_URL": "not-a-url",
            "SENTRY_DSN": "not-a-dsn",
            "SENTRY_TRACES_SAMPLE_RATE": "bogus",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "migrate-settings-ok"


def test_migrate_settings_require_database_url() -> None:
    """Failure mode 11: a missing DATABASE_URL stops settings import clearly."""
    result = _run_with_migrate_settings("import django; django.setup()", {})

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


# --- A6: build identity artifact script ---


def _write_identity(
    tmp_path: Path, **build_arguments: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    assert BUILD_SCRIPT.is_file()
    output = tmp_path / "build-identity.json"
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), str(output)],
        env={**minimal_environment(), **build_arguments},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result, output


@pytest.mark.parametrize(
    ("build_arguments", "expected"),
    (
        pytest.param(
            {"TAILTAG_SOURCE_SHA": SHA, "RAILWAY_GIT_COMMIT_SHA": ""},
            SHA,
            id="neutral-argument",
        ),
        pytest.param(
            {"TAILTAG_SOURCE_SHA": "", "RAILWAY_GIT_COMMIT_SHA": SHA},
            SHA,
            id="railway-only",
        ),
        pytest.param({}, None, id="no-argument"),
    ),
)
def test_build_identity_script_writes_the_one_field_artifact(
    tmp_path: Path, build_arguments: dict[str, str], expected: str | None
) -> None:
    """Failure mode 12: either build argument bakes the SHA; none bakes null."""
    result, output = _write_identity(tmp_path, **build_arguments)

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == {"source_sha": expected}


@pytest.mark.parametrize(
    "build_arguments",
    (
        pytest.param(
            {"TAILTAG_SOURCE_SHA": SHA, "RAILWAY_GIT_COMMIT_SHA": OTHER_SHA},
            id="differing-arguments",
        ),
        pytest.param({"TAILTAG_SOURCE_SHA": SHA.upper()}, id="malformed-neutral-sha"),
    ),
)
def test_build_identity_script_fails_without_writing_for_conflicting_or_malformed_sha(
    tmp_path: Path, build_arguments: dict[str, str]
) -> None:
    """Failure mode 12: ambiguity or a malformed SHA stops the image build."""
    result, output = _write_identity(tmp_path, **build_arguments)

    assert result.returncode != 0
    assert not output.exists()
