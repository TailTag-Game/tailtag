"""Fail-fast production settings."""

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


def comma_separated_values(value: str) -> list[str]:
    """Parse a comma-separated environment value without accepting blanks."""
    return [item.strip() for item in value.split(",") if item.strip()]


DEBUG = False
SECRET_KEY = required_environment_value("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = comma_separated_values(
    required_environment_value("DJANGO_ALLOWED_HOSTS")
)
CSRF_TRUSTED_ORIGINS = comma_separated_values(
    required_environment_value("DJANGO_CSRF_TRUSTED_ORIGINS"),
)
DATABASES = {
    "default": database_from_url(required_environment_value("DATABASE_URL")),
}

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
