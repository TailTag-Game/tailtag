"""Generated OpenAPI contract for the three credential routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.test import Client

from tests.catch_credential_test_support import PAYLOAD_A, TOKEN_A


def _deref(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    while "$ref" in result:
        name = cast(str, result["$ref"]).removeprefix("#/components/schemas/")
        result = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return result


def _assert_detail_error(
    schema: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    error = _deref(schema, response["content"]["application/json"]["schema"])
    assert error.get("additionalProperties") is False
    assert error["required"] == ["detail"]
    assert error["properties"] == {"detail": {"type": "string"}}


def _assert_payload_validation_error(
    schema: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    """The closed resolution request always reports validation against `payload`."""
    error = _deref(schema, response["content"]["application/json"]["schema"])
    assert error.get("additionalProperties") is False
    assert error["required"] == ["payload"]
    assert error["properties"] == {
        "payload": {"type": "array", "items": {"type": "string"}}
    }


def _without_generator_presentation_metadata(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Descriptions/titles are generator presentation metadata, not API semantics."""
    return {
        key: item for key, item in value.items() if key not in {"description", "title"}
    }


def _serialized_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [
            item
            for child in cast(Mapping[object, object], value).values()
            for item in _serialized_strings(child)
        ]
    if isinstance(value, list):
        return [
            item
            for child in cast(list[object], value)
            for item in _serialized_strings(child)
        ]
    return []


@pytest.mark.django_db
def test_credential_openapi_is_exact_closed_authenticated_and_has_no_rendering_boundary() -> (
    None
):
    """AC-13/16/17/18: rejects extra methods, request bodies, open schemas, or QR routes."""
    response = Client().get("/api/schema/")
    assert response.status_code == 200
    schema = cast(dict[str, Any], yaml.safe_load(response.content))
    paths = schema["paths"]
    owner = "/api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/"
    rotate = owner + "rotate/"
    resolve = "/api/conventions/{convention_id}/catch-credentials/resolve/"
    credential_paths = [path for path in paths if "catch-credential" in path]
    assert credential_paths == [resolve, owner, rotate]
    assert (
        set(paths[owner]) == {"get"}
        and set(paths[rotate]) == {"post"}
        and set(paths[resolve]) == {"post"}
    )
    bearer = [
        name
        for name, item in schema["components"]["securitySchemes"].items()
        if item.get("type") == "http" and item.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1
    for operation in (
        paths[owner]["get"],
        paths[rotate]["post"],
        paths[resolve]["post"],
    ):
        assert operation["security"] == [{bearer[0]: []}]
    assert set(paths[owner]["get"]["responses"]) == {
        "200",
        "400",
        "401",
        "403",
        "404",
        "405",
    }
    assert set(paths[rotate]["post"]["responses"]) == {
        "200",
        "400",
        "401",
        "403",
        "404",
        "405",
    }
    assert set(paths[resolve]["post"]["responses"]) == {
        "200",
        "400",
        "401",
        "403",
        "404",
        "405",
    }
    assert (
        "requestBody" not in paths[owner]["get"]
        and "requestBody" not in paths[rotate]["post"]
    )
    owner_payload = _deref(
        schema,
        paths[owner]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ],
    )
    assert owner_payload.get("additionalProperties") is False
    assert owner_payload["required"] == ["payload"]
    assert owner_payload["properties"] == {
        "payload": {
            "type": "string",
            "pattern": r"^tailtag:catch:v1:[A-Za-z0-9_-]{43}$",
        }
    }
    rotation_payload = _deref(
        schema,
        paths[rotate]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ],
    )
    assert rotation_payload == owner_payload
    request = _deref(
        schema,
        paths[resolve]["post"]["requestBody"]["content"]["application/json"]["schema"],
    )
    assert request.get("additionalProperties") is False and request["required"] == [
        "payload"
    ]
    assert _without_generator_presentation_metadata(
        request["properties"]["payload"]
    ) == {
        "type": "string",
        "pattern": r"^tailtag:catch:v1:[A-Za-z0-9_-]{43}$",
    }
    projection = _deref(
        schema,
        paths[resolve]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ],
    )
    assert projection.get("additionalProperties") is False and set(
        projection["properties"]
    ) == {"convention_id", "fursuit"}
    assert set(projection["required"]) == {"convention_id", "fursuit"}
    assert projection["properties"]["convention_id"] == {
        "type": "integer",
        "readOnly": True,
    }
    fursuit = _deref(schema, projection["properties"]["fursuit"])
    assert fursuit.get("additionalProperties") is False
    assert set(fursuit["required"]) == {"tailtag_id", "name", "photo_url"}
    assert fursuit["properties"] == {
        "tailtag_id": {"type": "string", "format": "uuid", "readOnly": True},
        "name": {"type": "string", "readOnly": True},
        "photo_url": {"type": "string", "format": "uri", "readOnly": True},
    }
    for operation in (
        paths[owner]["get"],
        paths[rotate]["post"],
        paths[resolve]["post"],
    ):
        for status in ("401", "403", "404", "405"):
            _assert_detail_error(schema, operation["responses"][status])
    for operation in (paths[owner]["get"], paths[rotate]["post"]):
        _assert_detail_error(schema, operation["responses"]["400"])
    _assert_payload_validation_error(schema, paths[resolve]["post"]["responses"]["400"])
    generic_not_found = paths[resolve]["post"]["responses"]["404"]
    assert "catch credential not found" in str(generic_not_found).lower()
    rendered = " ".join(paths).lower()
    assert not any(
        term in rendered for term in ("qr", "png", "svg", "base64", "render")
    )
    description = str(paths[resolve]["post"]).lower()
    assert (
        "not" in description
        and "authorization" in description
        and "wave 3" in description
    )
    serialized = _serialized_strings(schema)
    assert TOKEN_A not in serialized and PAYLOAD_A not in serialized
