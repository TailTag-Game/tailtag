"""Compose-only adapter for the Django PostgreSQL URL."""

from __future__ import annotations

import os
from urllib.parse import quote


def required_environment_value(name: str) -> str:
    """Return a required Compose setting without exposing its value."""
    value = os.environ.get(name)
    if not value:
        message = f"Missing required environment variable: {name}"
        raise RuntimeError(message)
    return value


def compose_database_url() -> str:
    """Build Django's container-network URL from Compose PostgreSQL settings."""
    database = quote(required_environment_value("POSTGRES_DB"), safe="")
    username = quote(required_environment_value("POSTGRES_USER"), safe="")
    password = quote(required_environment_value("POSTGRES_PASSWORD"), safe="")
    return f"postgresql://{username}:{password}@db:5432/{database}"


if __name__ == "__main__":
    print(compose_database_url())
