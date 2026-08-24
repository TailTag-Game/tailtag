"""Schema-level contract for the five unversioned player profile operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import yaml
from django.test import Client


def _schema(client: Client) -> dict[str, Any]:
    response = client.get("/api/schema/")
    assert response.status_code == 200
    return cast(dict[str, Any], yaml.safe_load(response.content))


def _dereference(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    resolved = dict(value)
    while "$ref" in resolved:
        name = cast(str, resolved["$ref"]).removeprefix("#/components/schemas/")
        resolved = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return resolved


def test_profile_openapi_documents_exact_paths_methods_representation_and_media_boundary(
    client: Client,
) -> None:
    """Rejects undocumented routes, JSON avatar uploads, or mutable lifecycle flags."""
    schema = _schema(client)
    assert set(schema["paths"]) == {
        "/api/conventions/",
        "/api/conventions/{id}/",
        "/api/me/",
        "/api/profile/",
        "/api/profile/avatar/",
        "/api/schema/",
    }
    profile = schema["paths"]["/api/profile/"]
    avatar = schema["paths"]["/api/profile/avatar/"]
    assert set(profile) == {"get", "put", "patch"}
    assert set(avatar) == {"put", "delete"}
    bearer = [
        name
        for name, definition in schema["components"]["securitySchemes"].items()
        if definition.get("type") == "http" and definition.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1
    for operation in (*profile.values(), *avatar.values()):
        assert operation["security"] == [{bearer[0]: []}]
        assert {"401", "403"}.issubset(operation["responses"])

    successful = _dereference(
        schema,
        profile["get"]["responses"]["200"]["content"]["application/json"]["schema"],
    )
    assert set(successful["properties"]) == {
        "handle",
        "display_name",
        "avatar_url",
        "onboarding_complete",
        "is_enabled",
    }
    assert successful.get("additionalProperties") is False
    assert successful["required"] == [
        "handle",
        "display_name",
        "avatar_url",
        "onboarding_complete",
        "is_enabled",
    ]
    assert successful["properties"]["handle"]["nullable"] is True
    assert successful["properties"]["display_name"]["nullable"] is True
    assert successful["properties"]["avatar_url"]["nullable"] is True
    assert successful["properties"]["onboarding_complete"]["readOnly"] is True
    assert successful["properties"]["is_enabled"]["readOnly"] is True
    put_body = _dereference(
        schema, profile["put"]["requestBody"]["content"]["application/json"]["schema"]
    )
    assert set(put_body["required"]) == {"handle", "display_name"}
    put_description = str(profile["put"].get("description", "")).lower()
    assert "avatar" in put_description
    assert "preserv" in put_description or "retain" in put_description
    patch_body = _dereference(
        schema,
        profile["patch"]["requestBody"]["content"]["application/json"]["schema"],
    )
    assert {"handle", "display_name"}.issubset(patch_body["properties"])
    assert not patch_body.get("required")
    for operation in (profile["put"], profile["patch"], avatar["put"]):
        response_schema = _dereference(
            schema,
            operation["responses"]["200"]["content"]["application/json"]["schema"],
        )
        assert response_schema == successful
    avatar_body = _dereference(
        schema, avatar["put"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    )
    assert avatar_body["required"] == ["avatar"]
    assert avatar_body["properties"]["avatar"]["format"] == "binary"
    assert (
        "200" in avatar["put"]["responses"] and "204" in avatar["delete"]["responses"]
    )
    for operation in (profile["put"], profile["patch"], avatar["put"]):
        assert "400" in operation["responses"]
