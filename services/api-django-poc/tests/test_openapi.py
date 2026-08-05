"""Published OpenAPI documentation behavior."""

from __future__ import annotations

import yaml
from django.test import Client


def test_openapi_schema_includes_account_and_fursuit_routes(client: Client) -> None:
    """The schema is public and includes the POC workflow."""
    response = client.get("/api/schema/")

    assert response.status_code == 200
    schema = yaml.safe_load(response.content)
    paths = schema["paths"]

    assert "/api/auth/csrf" in paths
    csrf = paths["/api/auth/csrf"]["get"]
    assert csrf["operationId"] == "auth_csrf_retrieve"
    assert csrf.get("security", []) == []
    assert csrf["responses"]["204"]["description"] == "No response body"

    signup = paths["/api/auth/signup"]["post"]
    assert signup.get("security", []) == []
    assert signup["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Signup"
    }
    assert signup["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicUser"
    }

    login = paths["/api/auth/login"]["post"]
    assert login.get("security", []) == []
    assert login["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Login"
    }
    assert login["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicUser"
    }
    assert login["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorDetail"
    }

    logout = paths["/api/auth/logout"]["post"]
    assert logout["security"] == [{"cookieAuth": []}]
    assert logout["responses"]["204"]["description"] == "No response body"

    current_user = paths["/api/auth/me"]["get"]
    assert current_user["security"] == [{"cookieAuth": []}]
    assert current_user["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/PublicUser"}

    fursuits = paths["/api/fursuits"]
    fursuit_list = fursuits["get"]
    assert fursuit_list["security"] == [{"cookieAuth": []}]
    assert fursuit_list["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"type": "array", "items": {"$ref": "#/components/schemas/Fursuit"}}

    fursuit_create = fursuits["post"]
    assert fursuit_create["security"] == [{"cookieAuth": []}]
    assert fursuit_create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Fursuit"
    }
    assert fursuit_create["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Fursuit"}

    fursuit_detail = paths["/api/fursuits/{fursuit_id}"]
    for operation in ("get", "patch", "delete"):
        assert fursuit_detail[operation]["security"] == [{"cookieAuth": []}]
    assert fursuit_detail["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Fursuit"}
    assert fursuit_detail["patch"]["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/PatchedFursuit"}
    assert fursuit_detail["patch"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Fursuit"}
    assert fursuit_detail["delete"]["responses"]["204"]["description"] == (
        "No response body"
    )
