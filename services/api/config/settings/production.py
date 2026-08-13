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


def comma_separated_values(value: str, *, name: str) -> list[str]:
    """Parse a required comma-separated environment value."""
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values:
        message = f"Required environment variable {name} must contain a value."
        raise RuntimeError(message)
    return values


DEBUG = False
SECRET_KEY = required_environment_value("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = comma_separated_values(
    required_environment_value("DJANGO_ALLOWED_HOSTS"), name="DJANGO_ALLOWED_HOSTS"
)
CSRF_TRUSTED_ORIGINS = comma_separated_values(
    required_environment_value("DJANGO_CSRF_TRUSTED_ORIGINS"),
    name="DJANGO_CSRF_TRUSTED_ORIGINS",
)
DATABASES = {
    "default": database_from_url(required_environment_value("DATABASE_URL")),
}

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
