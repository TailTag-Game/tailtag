"""Public behavior of the minimal V0 API foundation."""

from __future__ import annotations

import yaml
from django.apps import apps
from django.conf import settings
from django.test import Client


def test_foundation_exposes_profile_current_user_and_infrastructure_routes(
    client: Client,
) -> None:
    """The promoted service has only the identity proof, not POC player resources."""
    schema_response = client.get("/api/schema/")

    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert len(settings.AUTH_PASSWORD_VALIDATORS) == 4
    assert {"accounts", "fursuits", "profiles"}.issubset(apps.app_configs)
    assert client.get("/admin/").status_code == 302
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/docs/").status_code == 200
    assert client.post("/api/auth/signup", data={}).status_code == 404
    assert client.get("/api/fursuits").status_code == 404

    schema = yaml.safe_load(schema_response.content)
    assert schema_response.status_code == 200
    assert set(schema["paths"]) == {
        "/api/me/",
        "/api/profile/",
        "/api/profile/avatar/",
        "/api/schema/",
    }
