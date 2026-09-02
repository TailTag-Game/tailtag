"""Generated OpenAPI acceptance contract for catch sessions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.test import Client


def _deref(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    while "$ref" in result:
        name = cast(str, result["$ref"]).removeprefix("#/components/schemas/")
        result = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return result


@pytest.mark.django_db
def test_catch_session_openapi_is_exact_closed_authenticated_and_documents_non_authorization() -> (
    None
):
    """AC-05/15: rejects extra paths, open schemas, wrong nullability/enum, or omitted semantics."""
    response = Client().get("/api/schema/")
    assert response.status_code == 200
    schema = cast(dict[str, Any], yaml.safe_load(response.content))
    paths = schema["paths"]
    path = "/api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-session/"
    matches = [name for name in paths if "catch-session" in name]
    assert matches == [path] and set(paths[path]) == {"put"}
    put = paths[path]["put"]
    bearer = [
        name
        for name, item in schema["components"]["securitySchemes"].items()
        if item.get("type") == "http" and item.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1 and put["security"] == [{bearer[0]: []}]
    assert set(put["responses"]) == {"200", "400", "401", "403", "404", "405"}
    assert put["requestBody"]["required"] is True
    request = _deref(
        schema, put["requestBody"]["content"]["application/json"]["schema"]
    )
    assert request.get("additionalProperties") is False and request["required"] == [
        "is_active"
    ]
    assert request["properties"] == {"is_active": {"type": "boolean"}}
    projection = _deref(
        schema, put["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert projection.get("additionalProperties") is False
    assert set(projection["properties"]) == {
        "fursuit_id",
        "convention_id",
        "is_active",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
    }
    assert set(projection["required"]) == set(projection["properties"])
    for name in ("started_at", "expires_at", "ended_at", "end_reason"):
        assert projection["properties"][name].get("nullable") is True
    assert projection["properties"]["end_reason"]["enum"] == [
        "owner",
        "operator",
        "eligibility_lost",
        "expired",
    ]
    description = put.get("description", "").lower()
    for term in ("idempot", "12", "expire", "computed", "catch authorization"):
        assert term in description
