"""Shared deterministic storage test configuration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pytest_django.fixtures import SettingsWrapper


@pytest.fixture(autouse=True)
def deterministic_storage(settings: SettingsWrapper) -> None:
    """Keep media and static storage independent of the selected settings profile."""
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


# These modules exercise POSIX-only operator tooling: pty/termios sessions,
# gunicorn (fcntl), owner-and-mode checks (os.getuid, 0o700), and SSH relays.
# They cannot run on native Windows; Linux CI runs them. The report header
# names them so the skip is visible.
WINDOWS_SKIPPED_MODULES = frozenset(
    {
        "test_api_staging_reset_ssh.py",
        "test_api_staging_restore_drill.py",
        "test_http_runtime_telemetry.py",
        "test_replacement_candidate_origin.py",
        "test_replacement_migrate.py",
        "test_replacement_target_binding.py",
        "test_staging_emergency_operator.py",
        "test_staging_emergency_operator_ssh.py",
        "test_staging_managed_auth_diagnose_ssh.py",
        "test_staging_managed_operator_recovery.py",
        "test_staging_managed_password_rotate_ssh.py",
        "test_staging_operator_matrix.py",
        "test_staging_validation_operator.py",
    }
)


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Skip POSIX-only modules on native Windows; collect normally elsewhere."""
    if sys.platform == "win32" and collection_path.name in WINDOWS_SKIPPED_MODULES:
        return True
    return None


def pytest_report_header() -> str | None:
    """Name the POSIX-only modules that native Windows does not collect."""
    if sys.platform != "win32":
        return None
    return "Windows: skipping POSIX-only test modules: " + ", ".join(
        sorted(WINDOWS_SKIPPED_MODULES)
    )
