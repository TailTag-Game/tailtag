"""Production-style Django static delivery contracts."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from django.core.management import call_command
from django.http import StreamingHttpResponse
from django.test import Client, override_settings

PRODUCTION_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


def test_collected_admin_css_is_served_without_public_media(tmp_path: Path) -> None:
    """WhiteNoise serves collected admin files, never the private media namespace."""
    static_root = tmp_path / "staticfiles"
    with override_settings(
        DEBUG=False,
        STATIC_ROOT=static_root,
        MIDDLEWARE=PRODUCTION_MIDDLEWARE,
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
            },
        },
    ):
        call_command("collectstatic", interactive=False, verbosity=0)

        client = Client()
        response = client.get("/static/admin/css/base.css")

        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("text/css")
        streaming_content = cast(
            Iterable[bytes], cast(StreamingHttpResponse, response).streaming_content
        )
        assert b"html" in b"".join(streaming_content)
        assert client.get("/media/private-sentinel.jpg").status_code == 404
