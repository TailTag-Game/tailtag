"""Fail-fast production settings."""

from __future__ import annotations

import os

from .base import *
from .base import database_from_url
from .clerk import load_clerk_authentication_configuration
from .media import load_s3_media_configuration


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

CLERK_AUTHENTICATION = load_clerk_authentication_configuration(os.environ)

MEDIA_STORAGE_CONFIGURATION = load_s3_media_configuration(os.environ)
STORAGES = {  # pyright: ignore[reportConstantRedefinition]
    **STORAGES,
    "default": {
        "BACKEND": "media.storage.S3MediaStorage",
        "OPTIONS": {
            "endpoint_url": MEDIA_STORAGE_CONFIGURATION.endpoint_url,
            "bucket_name": MEDIA_STORAGE_CONFIGURATION.bucket_name,
            "region": MEDIA_STORAGE_CONFIGURATION.region,
            "access_key_id": MEDIA_STORAGE_CONFIGURATION.access_key_id,
            "secret_access_key": MEDIA_STORAGE_CONFIGURATION.secret_access_key,
            "url_expiry_seconds": 600,
        },
    },
}

LOGGING: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "botocore": {"handlers": [], "level": "WARNING", "propagate": False},
        "botocore.auth": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
        "boto3": {"handlers": [], "level": "WARNING", "propagate": False},
        "s3transfer": {"handlers": [], "level": "WARNING", "propagate": False},
    },
}

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
