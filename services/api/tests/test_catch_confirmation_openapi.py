"""Generated OpenAPI acceptance contract for catch confirmation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.test import Client

from conventions.catch_credential_protocol import CATCH_CREDENTIAL_PAYLOAD_PATTERN
from tests.catch_credential_test_support import PAYLOAD_A, TOKEN_A


def _deref(schema: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    while "$ref" in result:
        name = cast(str, result["$ref"]).removeprefix("#/components/schemas/")
        result = dict(cast(Mapping[str, Any], schema["components"])["schemas"][name])
    return result


def _without_generator_presentation_metadata(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Ignore only generator-added labels, never schema semantics."""
    return {
        key: item for key, item in value.items() if key not in {"description", "title"}
    }


def _serialized_operation_material(
    schema: Mapping[str, Any], operation: Mapping[str, Any]
) -> str:
    """Serialize this operation and only its transitively referenced components.

    Traversing reference siblings makes this conservative for the raw-value and
    diagnostic-text checks without changing the repository-standard `_deref`
    helper's pure-reference behavior. Every local OpenAPI component reference
    below this operation must resolve, regardless of component category.
    """
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


def _load_schema() -> dict[str, Any]:
    response = Client().get("/api/schema/")
    assert response.status_code == 200
    return cast(dict[str, Any], yaml.safe_load(response.content))


def _response_schema(
    response: Mapping[str, Any],
) -> Mapping[str, Any]:
    content = cast(Mapping[str, Any], response["content"])
    assert set(content) == {"application/json"}
    return cast(Mapping[str, Any], content["application/json"])["schema"]


def _assert_payload_validation_error(
    schema: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    error = _deref(schema, _response_schema(response))
    assert error.get("additionalProperties") is False
    assert error["required"] == ["payload"]
    assert error["properties"] == {
        "payload": {"type": "array", "items": {"type": "string"}}
    }


def _assert_authentication_error(
    schema: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    error = _deref(schema, _response_schema(response))
    assert error.get("additionalProperties") is False
    assert error["required"] == ["detail"]
    assert error["properties"] == {"detail": {"type": "string"}}


def _documented_domain_codes(
    response: Mapping[str, Any], error: Mapping[str, Any]
) -> set[str]:
    """Accept a status-specific code enum or status-specific JSON examples."""
    code = _without_generator_presentation_metadata(
        cast(Mapping[str, Any], error["properties"])["code"]
    )
    enum = code.pop("enum", None)
    assert code == {"type": "string"}
    if enum is not None:
        enum_values = cast(list[object], enum)
        assert isinstance(enum, list) and all(
            isinstance(item, str) for item in enum_values
        )
        return set(cast(list[str], enum_values))

    media_type = cast(Mapping[str, object], response["content"])["application/json"]
    examples = cast(Mapping[str, object], media_type).get("examples")
    assert isinstance(examples, Mapping)
    codes: set[str] = set()
    for example in cast(Mapping[str, object], examples).values():
        value = cast(Mapping[str, Any], example)["value"]
        code_value = cast(Mapping[str, Any], value)["code"]
        assert isinstance(code_value, str)
        codes.add(code_value)
    return codes


def _assert_domain_error(
    schema: Mapping[str, Any], response: Mapping[str, Any], *, codes: set[str]
) -> None:
    error = _deref(schema, _response_schema(response))
    assert error.get("additionalProperties") is False
    assert set(error["required"]) == {"code", "detail"}
    properties = cast(Mapping[str, Any], error["properties"])
    assert set(properties) == {"code", "detail"}
    assert _without_generator_presentation_metadata(properties["detail"]) == {
        "type": "string"
    }
    assert _documented_domain_codes(response, error) == codes


@pytest.mark.django_db
def test_catch_confirmation_openapi_has_only_the_closed_bearer_post_contract() -> None:
    """AC-12: reject a missing route, extra method, non-Bearer auth, or status drift."""
    schema = _load_schema()
    path = "/api/catches/confirm/"

    assert path in schema["paths"]
    assert set(schema["paths"][path]) == {"post"}
    operation = schema["paths"][path]["post"]
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
    assert set(operation["responses"]) == {
        "200",
        "201",
        "400",
        "401",
        "403",
        "404",
        "409",
        "500",
    }


@pytest.mark.django_db
def test_catch_confirmation_openapi_has_a_closed_request_and_shared_safe_success_schema() -> (
    None
):
    """AC-12: reject permissive input, different success refs, or unsafe projections."""
    schema = _load_schema()
    operation = schema["paths"]["/api/catches/confirm/"]["post"]
    request_body = cast(Mapping[str, Any], operation["requestBody"])

    assert request_body["required"] is True
    content = cast(Mapping[str, Any], request_body["content"])
    assert set(content) == {"application/json"}
    request = _deref(
        schema, cast(Mapping[str, Any], content["application/json"])["schema"]
    )
    assert request.get("additionalProperties") is False
    assert request["required"] == ["payload"]
    request_properties = cast(Mapping[str, Any], request["properties"])
    assert set(request_properties) == {"payload"}
    assert _without_generator_presentation_metadata(request_properties["payload"]) == {
        "type": "string",
        "pattern": CATCH_CREDENTIAL_PAYLOAD_PATTERN,
    }

    responses = cast(Mapping[str, Any], operation["responses"])
    success_200 = _response_schema(responses["200"])
    success_201 = _response_schema(responses["201"])
    assert set(success_200) == {"$ref"}
    assert success_200 == success_201
    success = _deref(schema, success_200)
    assert success.get("additionalProperties") is False
    assert set(success["required"]) == {"outcome", "catch"}
    assert set(success["properties"]) == {"outcome", "catch"}
    outcome = _without_generator_presentation_metadata(success["properties"]["outcome"])
    assert outcome == {
        "allOf": [{"$ref": "#/components/schemas/OutcomeEnum"}],
        "readOnly": True,
    }
    outcome_enum = _deref(schema, cast(Mapping[str, Any], outcome["allOf"][0]))
    assert _without_generator_presentation_metadata(outcome_enum) == {
        "type": "string",
        "enum": ["created", "already_caught"],
    }

    catch = _deref(schema, success["properties"]["catch"])
    assert catch.get("additionalProperties") is False
    assert set(catch["required"]) == {"id", "caught_at", "convention_id", "fursuit"}
    assert set(catch["properties"]) == {
        "id",
        "caught_at",
        "convention_id",
        "fursuit",
    }
    assert _without_generator_presentation_metadata(catch["properties"]["id"]) == {
        "type": "integer",
        "readOnly": True,
    }
    assert _without_generator_presentation_metadata(
        catch["properties"]["caught_at"]
    ) == {"type": "string", "format": "date-time", "readOnly": True}
    assert _without_generator_presentation_metadata(
        catch["properties"]["convention_id"]
    ) == {"type": "integer", "readOnly": True}

    fursuit = _deref(schema, catch["properties"]["fursuit"])
    assert fursuit.get("additionalProperties") is False
    assert set(fursuit["required"]) == {"tailtag_id", "name", "photo_url"}
    assert fursuit["properties"] == {
        "tailtag_id": {"type": "string", "format": "uuid", "readOnly": True},
        "name": {"type": "string", "readOnly": True},
        "photo_url": {"type": "string", "format": "uri", "readOnly": True},
    }


@pytest.mark.django_db
def test_catch_confirmation_openapi_is_deterministic_and_resolves_references() -> None:
    """AC-12: reject shared-schema mutation or dangling route-schema references."""
    first_schema = _load_schema()
    second_schema = _load_schema()
    path = "/api/catches/confirm/"

    first_operation = cast(Mapping[str, Any], first_schema["paths"][path]["post"])
    second_operation = cast(Mapping[str, Any], second_schema["paths"][path]["post"])
    assert _serialized_operation_material(
        first_schema, first_operation
    ) == _serialized_operation_material(second_schema, second_operation)


@pytest.mark.django_db
def test_catch_confirmation_openapi_closes_errors_and_documents_privacy_collapse() -> (
    None
):
    """AC-12: reject open error envelopes, wrong codes, or revealing 404 documentation."""
    schema = _load_schema()
    operation = schema["paths"]["/api/catches/confirm/"]["post"]
    responses = cast(Mapping[str, Any], operation["responses"])

    _assert_payload_validation_error(schema, responses["400"])
    _assert_authentication_error(schema, responses["401"])
    _assert_domain_error(schema, responses["403"], codes={"catcher_ineligible"})
    _assert_domain_error(schema, responses["404"], codes={"catch_target_unavailable"})
    _assert_domain_error(
        schema,
        responses["409"],
        codes={"active_convention_mismatch", "self_catch_not_allowed"},
    )
    _assert_domain_error(schema, responses["500"], codes={"server_error"})

    description = cast(str, responses["404"]["description"]).lower()
    assert "target" in description and "unavailable" in description
    assert "privacy" in description and "collaps" in description
    route_material = _serialized_operation_material(schema, operation)
    assert TOKEN_A not in route_material and PAYLOAD_A not in route_material
    diagnostic_text = route_material.lower()
    for approved_public_value in (
        "catcher_ineligible",
        "you are not eligible to catch this target.",
    ):
        diagnostic_text = diagnostic_text.replace(f'"{approved_public_value}"', "")
    assert all(
        hidden_detail not in diagnostic_text
        for hidden_detail in (
            "owner",
            "ownership",
            "provenance",
            "catcher",
            "activation",
            "catch_session",
            "credential row",
            "credential_id",
            "token",
            "user_id",
            "user id",
            '"user"',
            "revok",
            "stale",
            "stopp",
            "expir",
            "disabl",
            "ineligib",
            "delet",
            "remov",
            "lifecycle",
            "moderation",
            "eligibility",
        )
    )
