"""Generated OpenAPI contract for the three credential routes."""

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
    assert (
        "requestBody" not in paths[owner]["get"]
        and "requestBody" not in paths[rotate]["post"]
    )
    request = _deref(
        schema,
        paths[resolve]["post"]["requestBody"]["content"]["application/json"]["schema"],
    )
    assert request.get("additionalProperties") is False and request["required"] == [
        "payload"
    ]
    assert (
        request["properties"]["payload"]["pattern"]
        == r"^tailtag:catch:v1:[A-Za-z0-9_-]{43}$"
    )
    projection = _deref(
        schema,
        paths[resolve]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ],
    )
    assert projection.get("additionalProperties") is False and set(
        projection["properties"]
    ) == {"convention_id", "fursuit"}
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
