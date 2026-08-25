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
    successful = _dereference(
        schema, post["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert set(successful["properties"]) == {"id", "name", "photo_url", "is_enabled"}
    assert successful["required"] == ["id", "name", "photo_url", "is_enabled"]
    assert successful.get("additionalProperties") is False
    assert all(
        not successful["properties"][field].get("nullable", False)
        for field in successful["properties"]
    )
    assert not any(
        term in str(schema).lower()
        for term in ("photo_key", "owner", "activation", "catch", " qr")
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
