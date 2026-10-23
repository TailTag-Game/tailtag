"""Migration-only settings: the database URL is the only runtime input."""

from __future__ import annotations

import os

from .base import *
from .base import database_from_url


def required_environment_value(name: str) -> str:
    """Return a required environment variable or stop startup with a clear error."""
    value = os.environ.get(name)
    if not value:
        message = f"Missing required environment variable: {name}"
        raise RuntimeError(message)
    return value


DEBUG = False
SECRET_KEY = "tailtag-migrate-only-not-a-runtime-secret"
ALLOWED_HOSTS: list[str] = []
CSRF_TRUSTED_ORIGINS: list[str] = []
DATABASES = {
    "default": database_from_url(required_environment_value("DATABASE_URL")),
}
