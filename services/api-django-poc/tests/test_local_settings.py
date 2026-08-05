"""Local settings behavior."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping


def run_local_settings_import(
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Import local settings in a clean process with supplied environment."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import config.settings.local as s; "
                "print(s.DATABASES['default']['HOST']); "
                "print(s.SECRET_KEY); "
                "print(s.SESSION_COOKIE_SECURE); "
                "print(s.CSRF_COOKIE_SECURE)"
            ),
        ],
        cwd=".",
        env={"PATH": os.environ["PATH"], **environment},
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_settings_use_environment_overrides_and_http_safe_cookies() -> None:
    """Docker Compose can point local Django at its PostgreSQL service over HTTP."""
    completed = run_local_settings_import(
        {
            "DATABASE_URL": "postgresql://tailtag:password@db:5432/tailtag",
            "DJANGO_SECRET_KEY": "local-test-secret",
        }
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "db",
        "local-test-secret",
        "False",
        "False",
    ]
