"""Exact OpenAPI and global product-boundary contract for fursuit APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import yaml
from django.test import Client


def _dereference(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    while "$ref" in result:
        name = cast(str, result["$ref"]).removeprefix("#/components/schemas/")
        result = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return result


def test_fursuit_openapi_is_exact_closed_authenticated_and_has_safe_media_shapes(
    client: Client,
) -> None:
    response = client.get("/api/schema/")
    assert response.status_code == 200
    schema = cast(dict[str, Any], yaml.safe_load(response.content))
    paths = schema["paths"]
    assert set(paths["/api/fursuits/"]) == {"get", "post"}
    assert set(paths["/api/fursuits/{id}/"]) == {"get", "patch"}
    assert set(paths["/api/fursuits/{id}/photo/"]) == {"put"}
    bearer = [
        name
        for name, item in schema["components"]["securitySchemes"].items()
        if item.get("type") == "http" and item.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1
    operations = [
        operation
        for path in (
            "/api/fursuits/",
            "/api/fursuits/{id}/",
            "/api/fursuits/{id}/photo/",
        )
        for operation in paths[path].values()
    ]
    for operation in operations:
        assert operation["security"] == [{bearer[0]: []}]
        assert {"401", "405"}.issubset(operation["responses"])
    post, patch, photo = (
        paths["/api/fursuits/"]["post"],
        paths["/api/fursuits/{id}/"]["patch"],
        paths["/api/fursuits/{id}/photo/"]["put"],
    )
    assert set(post["requestBody"]["content"]) == {"multipart/form-data"}
    assert set(photo["requestBody"]["content"]) == {"multipart/form-data"}
    assert set(patch["requestBody"]["content"]) == {"application/json"}
    for operation in (post, patch, photo):
        assert {"400", "403"}.issubset(operation["responses"])
    assert {"200", "401", "405"}.issubset(paths["/api/fursuits/"]["get"]["responses"])
    assert {"200", "401", "404", "405"}.issubset(
        paths["/api/fursuits/{id}/"]["get"]["responses"]
    )
    assert {"200", "400", "401", "403", "404", "405"}.issubset(patch["responses"])
    assert {"200", "400", "401", "403", "404", "405"}.issubset(photo["responses"])
    successful = _dereference(
        schema, post["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert set(successful["properties"]) == {
        "id",
        "tailtag_id",
        "name",
        "photo_url",
        "is_enabled",
    }
    assert successful["required"] == [
        "id",
        "tailtag_id",
        "name",
        "photo_url",
        "is_enabled",
    ]
    assert successful.get("additionalProperties") is False
    assert all(
        not successful["properties"][field].get("nullable", False)
        for field in successful["properties"]
    )
    create_body = _dereference(
        schema, post["requestBody"]["content"]["multipart/form-data"]["schema"]
    )
    photo_body = _dereference(
        schema, photo["requestBody"]["content"]["multipart/form-data"]["schema"]
    )
    assert (
        set(create_body["required"]) == {"name", "photo"}
        and create_body["properties"]["photo"]["format"] == "binary"
    )
    assert (
        photo_body["required"] == ["photo"]
        and photo_body["properties"]["photo"]["format"] == "binary"
    )
    patch_body = _dereference(
        schema, patch["requestBody"]["content"]["application/json"]["schema"]
    )
    assert patch_body.get("additionalProperties") is False
    assert set(patch_body["properties"]) == {"name"}
    assert patch_body["required"] == ["name"]
    for body, expected in (
        (create_body, {"name", "photo"}),
        (photo_body, {"photo"}),
    ):
        assert body.get("additionalProperties") is False
        assert set(body["properties"]) == expected
    for request_schema in (create_body, photo_body, patch_body):
        assert not {
            "id",
            "tailtag_id",
            "owner",
            "photo_url",
            "photo_key",
            "is_enabled",
            "created_at",
            "updated_at",
        }.intersection(request_schema["properties"])
    list_response = _dereference(
        schema,
        paths["/api/fursuits/"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"],
    )
    list_item = _dereference(schema, cast(Mapping[str, Any], list_response["items"]))
    detail_response = _dereference(
        schema,
        paths["/api/fursuits/{id}/"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"],
    )
    canonical_response_schemas = (
        successful,
        list_item,
        detail_response,
        _dereference(
            schema,
            patch["responses"]["200"]["content"]["application/json"]["schema"],
        ),
        _dereference(
            schema,
            photo["responses"]["200"]["content"]["application/json"]["schema"],
        ),
    )
    for response_schema in canonical_response_schemas:
        assert set(response_schema["properties"]) == {
            "id",
            "tailtag_id",
            "name",
            "photo_url",
            "is_enabled",
        }
        assert response_schema["required"] == [
            "id",
            "tailtag_id",
            "name",
            "photo_url",
            "is_enabled",
        ]
        assert response_schema["properties"]["tailtag_id"] == {
            "type": "string",
            "format": "uuid",
            "readOnly": True,
        }
        assert response_schema.get("additionalProperties") is False
    fursuit_schema_surface = str(
        (
            operations,
            successful,
            list_response,
            list_item,
            detail_response,
            create_body,
            photo_body,
            patch_body,
        )
    ).lower()
    assert not any(
        term in fursuit_schema_surface
        for term in ("photo_key", "owner", "activation", "catch", " qr")
    )
