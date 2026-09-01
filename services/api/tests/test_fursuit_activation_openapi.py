"""Exact generated OpenAPI acceptance contract for fursuit activation."""

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


def test_fursuit_activation_openapi_is_exact_closed_authenticated_and_documents_state_distinction(
    client: Client,
) -> None:
    response = client.get("/api/schema/")
    assert response.status_code == 200
    schema = cast(dict[str, Any], yaml.safe_load(response.content))
    paths = schema["paths"]
    list_path = "/api/conventions/{convention_id}/fursuit-activations/"
    detail_path = "/api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/"
    assert set(paths[list_path]) == {"get"}
    assert set(paths[detail_path]) == {"put"}
    bearer = [
        name
        for name, item in schema["components"]["securitySchemes"].items()
        if item.get("type") == "http" and item.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1
    get, put = paths[list_path]["get"], paths[detail_path]["put"]
    for operation in (get, put):
        assert operation["security"] == [{bearer[0]: []}]
    assert set(get["responses"]) == {"200", "401", "404", "405"}
    assert set(put["responses"]) == {"200", "400", "401", "403", "404", "405"}
    request = _dereference(
        schema, put["requestBody"]["content"]["application/json"]["schema"]
    )
    assert request.get("additionalProperties") is False
    assert request["required"] == ["is_active"]
    assert set(request["properties"]) == {"is_active"}
    assert request["properties"]["is_active"] == {"type": "boolean"}
    response_schema = _dereference(
        schema, put["responses"]["200"]["content"]["application/json"]["schema"]
    )
    list_schema = _dereference(
        schema, get["responses"]["200"]["content"]["application/json"]["schema"]
    )
    item_schema = _dereference(schema, list_schema["items"])
    for shape in (response_schema, item_schema):
        assert shape.get("additionalProperties") is False
        assert set(shape["properties"]) == {
            "fursuit_id",
            "convention_id",
            "is_active",
            "is_eligible",
            "activated_at",
            "deactivated_at",
        }
        assert set(shape["required"]) == set(shape["properties"])
        assert shape["properties"]["activated_at"]["format"] == "date-time"
        assert shape["properties"]["deactivated_at"]["format"] == "date-time"
        assert shape["properties"]["deactivated_at"].get("nullable") is True
        assert shape["properties"]["is_active"]["type"] == "boolean"
        assert shape["properties"]["is_eligible"]["type"] == "boolean"
    list_description = get.get("description", "").lower()
    assert "ascending" in list_description and "fursuit_id" in list_description
    put_description = put.get("description", "").lower()
    assert "idempot" in put_description
    descriptions = f"{list_description} {put_description}"
    for term in (
        "is_active",
        "stored",
        "is_eligible",
        "computed",
        "current",
        "operational participation",
    ):
        assert term in descriptions
