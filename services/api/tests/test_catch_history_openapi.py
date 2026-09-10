"""Generated OpenAPI acceptance contract for player catch history."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.test import Client

_HISTORY_PATH = "/api/catches/"
_CONFIRMATION_PATH = "/api/catches/confirm/"


def _load_schema() -> dict[str, Any]:
    response = Client().get("/api/schema/")
    assert response.status_code == 200
    return cast(dict[str, Any], yaml.safe_load(response.content))


def _history_operation(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    paths = cast(Mapping[str, Any], schema["paths"])
    assert _HISTORY_PATH in paths, "Catch history must be generated at /api/catches/."
    path_item = cast(Mapping[str, Any], paths[_HISTORY_PATH])
    assert set(path_item) == {"get"}
    return cast(Mapping[str, Any], path_item["get"])


def _deref(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    while "$ref" in result:
        name = cast(str, result["$ref"]).removeprefix("#/components/schemas/")
        result = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return result


def _without_generator_presentation_metadata(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Ignore labels while retaining every schema semantic."""
    return {
        key: item for key, item in value.items() if key not in {"description", "title"}
    }


def _response_schema(response: Mapping[str, Any]) -> Mapping[str, Any]:
    content = cast(Mapping[str, Any], response["content"])
    assert set(content) == {"application/json"}
    return cast(Mapping[str, Any], content["application/json"])["schema"]


def _serialized_operation_material(
    schema: Mapping[str, Any], operation: Mapping[str, Any]
) -> str:
    """Serialize the operation and its transitive local component references."""
    components = cast(
        Mapping[str, object], cast(Mapping[str, Any], schema["components"])
    )
    relevant: list[Mapping[str, Any]] = [operation]
    seen_references: set[tuple[str, str]] = set()

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            mapping = cast(Mapping[str, object], value)
            reference = mapping.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/"):
                component_path = reference.removeprefix("#/components/").split("/")
                assert len(component_path) == 2 and all(component_path), (
                    f"Component reference must name a category and component: {reference}"
                )
                category, name = component_path
                component_reference = (category, name)
                if component_reference not in seen_references:
                    seen_references.add(component_reference)
                    assert category in components, (
                        f"Dangling component category: {reference}"
                    )
                    category_components = cast(
                        Mapping[str, object], components[category]
                    )
                    assert name in category_components, (
                        f"Dangling component reference: {reference}"
                    )
                    component = cast(Mapping[str, Any], category_components[name])
                    relevant.append(component)
                    collect(component)
            for child in mapping.values():
                collect(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                collect(child)

    collect(operation)
    return json.dumps(relevant, sort_keys=True)


def _assert_closed_object(
    schema: Mapping[str, Any], value: Mapping[str, Any], *, fields: set[str]
) -> dict[str, Any]:
    result = _deref(schema, value)
    assert result.get("additionalProperties") is False
    assert set(result["required"]) == fields
    assert set(cast(Mapping[str, Any], result["properties"])) == fields
    return result


def _documented_domain_codes(error: Mapping[str, Any]) -> set[str]:
    """Require each status to close its public domain-code vocabulary."""
    code = _without_generator_presentation_metadata(
        cast(Mapping[str, Any], error["properties"])["code"]
    )
    enum = code.pop("enum", None)
    assert code == {"type": "string"}
    assert isinstance(enum, list)
    enum_values = cast(list[object], enum)
    assert all(isinstance(item, str) for item in enum_values)
    return set(cast(list[str], enum_values))


def _assert_domain_error(
    schema: Mapping[str, Any], response: Mapping[str, Any], *, codes: set[str]
) -> None:
    error = _assert_closed_object(
        schema, _response_schema(response), fields={"code", "detail"}
    )
    properties = cast(Mapping[str, Any], error["properties"])
    assert _without_generator_presentation_metadata(properties["detail"]) == {
        "type": "string"
    }
    assert _documented_domain_codes(error) == codes


@pytest.mark.django_db
def test_catch_history_openapi_has_one_closed_bearer_get_contract() -> None:
    """AC-01/AC-13: reject alternate routes, methods, auth, and request bodies."""
    schema = _load_schema()
    paths = cast(Mapping[str, Any], schema["paths"])

    catch_paths = {
        path: cast(Mapping[str, Any], path_item)
        for path, path_item in paths.items()
        if path.startswith(_HISTORY_PATH)
    }
    assert set(catch_paths) == {_HISTORY_PATH, _CONFIRMATION_PATH}
    assert set(catch_paths[_HISTORY_PATH]) == {"get"}
    assert set(catch_paths[_CONFIRMATION_PATH]) == {"post"}
    assert all("collection" not in path.lower() for path in paths)

    operation = _history_operation(schema)
    security_schemes = cast(
        Mapping[str, Mapping[str, Any]], schema["components"]["securitySchemes"]
    )
    bearer = [
        name
        for name, item in security_schemes.items()
        if item.get("type") == "http" and item.get("scheme") == "bearer"
    ]
    assert len(bearer) == 1
    assert operation["security"] == [{bearer[0]: []}]
    assert "requestBody" not in operation


@pytest.mark.django_db
def test_catch_history_openapi_documents_only_the_frozen_query_parameters() -> None:
    """AC-02/AC-06/AC-08/AC-13: reject selectors or permissive pagination input."""
    operation = _history_operation(_load_schema())
    parameters = cast(list[Mapping[str, Any]], operation["parameters"])
    parameter_locations = {
        (cast(str, parameter["name"]), cast(str, parameter["in"]))
        for parameter in parameters
    }
    assert len(parameters) == 3
    assert len(parameter_locations) == 3
    by_name = {cast(str, parameter["name"]): parameter for parameter in parameters}

    assert set(by_name) == {"convention_id", "page", "page_size"}
    expected_schemas = {
        "convention_id": {"type": "integer", "minimum": 1},
        "page": {"type": "integer", "minimum": 1, "default": 1},
        "page_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20,
        },
    }
    for name, parameter in by_name.items():
        assert parameter["in"] == "query"
        assert parameter.get("required") is False
        assert parameter.get("style", "form") == "form"
        assert parameter.get("explode", True) is True
        parameter_schema = _without_generator_presentation_metadata(
            cast(Mapping[str, Any], parameter["schema"])
        )
        assert parameter_schema == expected_schemas[name]
        description = cast(str, parameter.get("description", "")).lower()
        assert "ascii" in description and "decimal" in description

    forbidden_selector_fragments = (
        "ordering",
        "order",
        "player",
        "catcher",
        "owner",
        "provider",
    )
    assert all(
        fragment not in name.lower()
        for name in by_name
        for fragment in forbidden_selector_fragments
    )


@pytest.mark.django_db
def test_catch_history_openapi_has_the_exact_closed_success_projection() -> None:
    """AC-09/AC-10/AC-13: reject open, unsafe, mutable, or expanded projections."""
    schema = _load_schema()
    operation = _history_operation(schema)
    responses = cast(Mapping[str, Any], operation["responses"])
    success = _assert_closed_object(
        schema,
        _response_schema(cast(Mapping[str, Any], responses["200"])),
        fields={"catch_count", "next", "previous", "results"},
    )
    properties = cast(Mapping[str, Any], success["properties"])
    assert _without_generator_presentation_metadata(properties["catch_count"]) == {
        "type": "integer",
        "minimum": 0,
    }
    for link_name in ("next", "previous"):
        assert _without_generator_presentation_metadata(properties[link_name]) == {
            "type": "string",
            "format": "uri",
            "nullable": True,
        }

    results = _without_generator_presentation_metadata(properties["results"])
    assert set(results) == {"type", "items"}
    assert results["type"] == "array"
    catch = _assert_closed_object(
        schema,
        cast(Mapping[str, Any], results["items"]),
        fields={"id", "fursuit", "convention", "caught_at"},
    )
    catch_properties = cast(Mapping[str, Any], catch["properties"])
    assert _without_generator_presentation_metadata(catch_properties["id"]) == {
        "type": "integer",
        "readOnly": True,
    }
    assert _without_generator_presentation_metadata(catch_properties["caught_at"]) == {
        "type": "string",
        "format": "date-time",
        "readOnly": True,
    }

    fursuit = _assert_closed_object(
        schema,
        cast(Mapping[str, Any], catch_properties["fursuit"]),
        fields={"id", "name", "photo_url"},
    )
    assert {
        name: _without_generator_presentation_metadata(field)
        for name, field in cast(
            Mapping[str, Mapping[str, Any]], fursuit["properties"]
        ).items()
    } == {
        "id": {"type": "integer", "readOnly": True},
        "name": {"type": "string", "readOnly": True},
        "photo_url": {"type": "string", "format": "uri", "readOnly": True},
    }
    convention = _assert_closed_object(
        schema,
        cast(Mapping[str, Any], catch_properties["convention"]),
        fields={"id", "name"},
    )
    assert {
        name: _without_generator_presentation_metadata(field)
        for name, field in cast(
            Mapping[str, Mapping[str, Any]], convention["properties"]
        ).items()
    } == {
        "id": {"type": "integer", "readOnly": True},
        "name": {"type": "string", "readOnly": True},
    }

    material = _serialized_operation_material(schema, operation).lower()
    assert all(
        forbidden not in material
        for forbidden in (
            '"catcher"',
            '"catcher_id"',
            '"catcher_user"',
            '"owner"',
            '"owner_id"',
            '"provider"',
            '"provider_id"',
            '"user"',
            '"user_id"',
            "clerk",
            "credential",
            "session",
            "activation",
            "lifecycle",
            "progression",
            "rarity",
            "leaderboard",
            "denominator",
            "collection_entry",
            "collection entry",
            "writeonly",
        )
    )


@pytest.mark.django_db
def test_catch_history_openapi_documents_every_closed_response() -> None:
    """AC-05/AC-07/AC-11/AC-13: reject incomplete errors or missing semantics."""
    schema = _load_schema()
    operation = _history_operation(schema)
    responses = cast(Mapping[str, Any], operation["responses"])

    assert set(responses) == {"200", "400", "401", "404", "500"}
    _assert_domain_error(
        schema, cast(Mapping[str, Any], responses["400"]), codes={"invalid_query"}
    )
    _assert_domain_error(
        schema,
        cast(Mapping[str, Any], responses["404"]),
        codes={"convention_not_found", "invalid_page"},
    )
    _assert_domain_error(
        schema, cast(Mapping[str, Any], responses["500"]), codes={"server_error"}
    )
    authentication = _assert_closed_object(
        schema,
        _response_schema(cast(Mapping[str, Any], responses["401"])),
        fields={"detail"},
    )
    assert _without_generator_presentation_metadata(
        authentication["properties"]["detail"]
    ) == {"type": "string"}

    operation_description = cast(str, operation["description"]).lower()
    success_description = cast(str, responses["200"]["description"]).lower()
    not_found_description = cast(str, responses["404"]["description"]).lower()
    server_error_description = cast(str, responses["500"]["description"]).lower()

    assert "nonexistent convention returns http 404" in not_found_description
    assert (
        "existing convention with no matching catch rows returns http 200"
        in success_description
    )
    assert (
        "catch_count is the total number of matching catch rows before pagination"
        in success_description
    )
    assert "ordered by -caught_at, -id" in operation_description
    assert (
        "photo url signing failure fails the whole request" in server_error_description
    )
