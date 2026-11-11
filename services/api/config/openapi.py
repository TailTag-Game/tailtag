"""Narrow OpenAPI postprocessing for existing API components and request bodies."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from config.openapi_components import CATCH_REQUEST_COMPONENTS

_ISSUE_120_CLOSED_COMPONENTS = frozenset(
    {
        "ActiveConventionResponse",
        "Convention",
        "ConventionEnrollRequest",
        "ConventionEnrollment",
        "PatchedProfilePatch",
        "ProfilePut",
        "SelectActiveConventionRequest",
    }
)


def close_issue_120_component_schemas(
    result: dict[str, Any], **_: object
) -> dict[str, Any]:
    """Close the pre-existing Wave 2 object components without changing their shape."""
    components = result.get("components")
    if not isinstance(components, dict):
        return result
    schemas = cast(dict[str, Any], components).get("schemas")
    if not isinstance(schemas, dict):
        return result
    schema_components = cast(dict[str, Any], schemas)
    for name in _ISSUE_120_CLOSED_COMPONENTS:
        schema = schema_components.get(name)
        if isinstance(schema, dict):
            schema["additionalProperties"] = False
    return result


# drf-spectacular never marks a raw dict request schema as required. These
# operations reject a missing body with 400, so the schema must say so (#504).
_REQUIRED_BODY_OPERATIONS = frozenset(
    {
        "catch_preview",
        "fursuit_tag_replace",
        "catch_requests_create",
        "fursuits_update",
        "catch_incoming_requests_decline",
    }
)


def add_catch_request_components(result: dict[str, Any], **_: object) -> dict[str, Any]:
    """Add the named catch request components that the operations reference."""
    components = result.setdefault("components", {})
    schemas = cast(dict[str, Any], components).setdefault("schemas", {})
    for name, schema in CATCH_REQUEST_COMPONENTS.items():
        if name in schemas:
            message = f"OpenAPI component {name!r} already exists."
            raise ValueError(message)
        cast(dict[str, Any], schemas)[name] = deepcopy(schema)
    return result


def require_reusable_tag_request_bodies(
    result: dict[str, Any], **_: object
) -> dict[str, Any]:
    """Mark the reusable tag and catch request bodies as required."""
    paths = result.get("paths")
    if not isinstance(paths, dict):
        return result
    for path_item in cast(dict[str, Any], paths).values():
        if not isinstance(path_item, dict):
            continue
        for operation in cast(dict[str, Any], path_item).values():
            if not isinstance(operation, dict):
                continue
            operation_map = cast(dict[str, Any], operation)
            body = operation_map.get("requestBody")
            if operation_map.get(
                "operationId"
            ) in _REQUIRED_BODY_OPERATIONS and isinstance(body, dict):
                cast(dict[str, Any], body)["required"] = True
    return result
