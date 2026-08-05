"""Safe, explicit settings for local development and tests."""

from __future__ import annotations

import os

from .base import *
from .base import database_from_url

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-only-secret-key")
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
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if item.strip()
]
DATABASES = {
    "default": database_from_url(
        os.environ.get(
            "DATABASE_URL", "postgresql://tailtag:tailtag@localhost:5432/tailtag"
        )
    ),
}
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
