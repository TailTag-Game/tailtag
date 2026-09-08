from .base import *
from .base import STORAGES

DEBUG = False
SECRET_KEY = "tailtag-static-build-only-not-a-runtime-secret"
ALLOWED_HOSTS: list[str] = []
CSRF_TRUSTED_ORIGINS: list[str] = []
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
