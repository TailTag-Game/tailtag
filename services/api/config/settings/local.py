"""Safe, explicit settings for local development and tests."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .base import *
from .base import BASE_DIR, database_from_url


def required_environment_value(name: str) -> str:
    """Return a required local setting without exposing its value."""
    value = os.environ.get(name)
    if not value:
        message = f"Missing required environment variable: {name}"
        raise RuntimeError(message)
    return value


load_dotenv(BASE_DIR / ".env")

DEBUG = True
SECRET_KEY = required_environment_value("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [
    item.strip()
    for item in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
    ).split(",")
    if item.strip()
]
CSRF_TRUSTED_ORIGINS = [
    item.strip()
    for item in os.environ.get(
        "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if item.strip()
]
DATABASES = {
    "default": database_from_url(required_environment_value("DATABASE_URL")),
}
