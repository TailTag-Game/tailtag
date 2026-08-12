"""Safe, explicit settings for local development and tests."""

from __future__ import annotations

from .base import *
from .base import database_from_url

DEBUG = True
SECRET_KEY = "local-development-only-secret-key"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
DATABASES = {
    "default": database_from_url("postgresql://tailtag:tailtag@localhost:5432/tailtag"),
}
