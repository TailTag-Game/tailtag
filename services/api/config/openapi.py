"""Narrow OpenAPI postprocessing for Issue #120's existing API components."""

from __future__ import annotations

from typing import Any, cast

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
