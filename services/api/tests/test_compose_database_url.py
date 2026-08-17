"""Compose database URL adapter behavior."""

from __future__ import annotations

import os
import subprocess
import sys


def test_compose_database_url_percent_encodes_reserved_password_characters() -> None:
    """Compose preserves reserved PostgreSQL password characters in Django's URL."""
    completed = subprocess.run(
        [sys.executable, "-m", "config.compose_database_url"],
        cwd=".",
        env={
            "PATH": os.environ["PATH"],
            "POSTGRES_DB": "tailtag",
            "POSTGRES_USER": "tailtag",
            "POSTGRES_PASSWORD": "pa/ss?word#%25",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (
        completed.stdout
        == "postgresql://tailtag:pa%2Fss%3Fword%23%2525@db:5432/tailtag\n"
    )
