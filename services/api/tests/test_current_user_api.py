"""Acceptance contract for the V0 authenticated current-user API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

import pytest
import yaml
from django.conf import settings
from django.test import Client, override_settings
from django.urls import resolve
from pytest import MonkeyPatch
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    create_test_user,
    fake_clerk_session_verification,
    force_authenticated_client,
)


class _PermissionDeclaringView(Protocol):
    permission_classes: Sequence[type[IsAuthenticated]]


def _schema(client: Client) -> dict[str, Any]:
    response = client.get("/api/schema/")

    assert response.status_code == 200
    return cast(dict[str, Any], yaml.safe_load(response.content))


def _dereference_schema(
    schema: Mapping[str, Any], value: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve local component references used by the generated OpenAPI document."""
    resolved = dict(value)
    while "$ref" in resolved:
        reference = cast(str, resolved["$ref"])
        assert reference.startswith("#/components/schemas/")
        component_name = reference.removeprefix("#/components/schemas/")
        components = cast(Mapping[str, Any], schema["components"])
        component_schemas = cast(Mapping[str, Any], components["schemas"])
        component = cast(Mapping[str, Any], component_schemas[component_name])
        resolved = dict(component)
    return resolved


@pytest.mark.django_db
def test_current_user_view_returns_exactly_the_tailtag_user_id_and_declares_permission() -> (
    None
):
    """The representation is isolated from Clerk and profile concerns."""
    user = create_test_user(clerk_user_id="user_current_user_view")

    response = force_authenticated_client(user=user).get("/api/me/")

    assert response.status_code == 200
    assert response.json() == {"id": user.pk}
    assert type(response.json()["id"]) is int

    view_class = cast(
        _PermissionDeclaringView,
        cast(Any, resolve("/api/me/").func).view_class,
    )
    assert list(view_class.permission_classes) == [IsAuthenticated]
    assert "DEFAULT_PERMISSION_CLASSES" not in settings.REST_FRAMEWORK


@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_current_user_requires_authentication_with_a_bearer_challenge() -> None:
    """Headerless production requests are rejected without fixing error prose."""
    response = Client().get("/api/me/")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert set(body) == {"detail"}
    assert isinstance(body["detail"], str)


@pytest.mark.django_db
def test_current_user_composes_bearer_verification_resolution_and_request_identity(
    monkeypatch: MonkeyPatch,
) -> None:
    """Only the Clerk verification boundary is faked; DRF and resolution stay real."""
    verified_requests = fake_clerk_session_verification(
        monkeypatch,
        subject="user_current_user_composed",
    )

    response = Client().get("/api/me/", HTTP_AUTHORIZATION="Bearer test-token")
    resolved_user = User.objects.get(clerk_user_id="user_current_user_composed")

    assert response.status_code == 200
    assert response.json() == {"id": resolved_user.pk}
    assert len(verified_requests) == 1
    assert verified_requests[0].headers["Authorization"] == "Bearer test-token"


def test_current_user_openapi_contract_is_authenticated_and_exact(
    client: Client,
) -> None:
    schema = _schema(client)

    operation = schema["paths"]["/api/me/"]["get"]
    components = schema["components"]
    security_schemes = components["securitySchemes"]
    bearer_schemes = [
        name
        for name, definition in security_schemes.items()
        if definition.get("type") == "http" and definition.get("scheme") == "bearer"
    ]

    assert len(bearer_schemes) == 1
    assert operation["security"] == [{bearer_schemes[0]: []}]

    successful_response = operation["responses"]["200"]
    successful_schema = _dereference_schema(
        schema, successful_response["content"]["application/json"]["schema"]
    )
    assert successful_schema["type"] == "object"
    assert set(successful_schema["properties"]) == {"id"}
    assert successful_schema["properties"]["id"]["type"] == "integer"
    assert successful_schema["required"] == ["id"]
    assert successful_schema.get("additionalProperties") is False

    unauthenticated_response = operation["responses"]["401"]
    unauthenticated_schema = _dereference_schema(
        schema, unauthenticated_response["content"]["application/json"]["schema"]
    )
    assert unauthenticated_schema["type"] == "object"
    assert set(unauthenticated_schema["properties"]) == {"detail"}
    assert unauthenticated_schema["properties"]["detail"]["type"] == "string"
    assert unauthenticated_schema["required"] == ["detail"]


@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_public_infrastructure_routes_remain_public_and_schema_has_no_security_requirement(
    client: Client,
) -> None:
    """The protected product operation does not change public infrastructure."""
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/docs/").status_code == 200

    schema = _schema(client)
    schema_operation = schema["paths"]["/api/schema/"]["get"]
    assert {} in schema_operation["security"]


def test_product_routes_remain_unversioned_and_do_not_add_public_user_surfaces(
    client: Client,
) -> None:
    schema = _schema(client)

    assert set(schema["paths"]) == {
        "/api/me/",
        "/api/profile/",
        "/api/profile/avatar/",
        "/api/conventions/",
        "/api/conventions/{id}/",
        "/api/conventions/active/",
        "/api/conventions/enrollments/",
        "/api/conventions/{convention_id}/fursuit-activations/",
        "/api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/",
        "/api/fursuits/",
        "/api/fursuits/{id}/",
        "/api/fursuits/{id}/photo/",
        "/api/schema/",
    }
    assert client.get("/api/v0/me/").status_code == 404
    assert client.get("/api/v1/me/").status_code == 404
    assert client.get("/api/users/me/").status_code == 404
    assert client.get("/api/profiles/").status_code == 404
    assert client.get("/api/profile/finn_42/").status_code == 404
    assert client.post("/api/auth/signup", data={}).status_code == 404
    assert client.get("/api/fursuits").status_code == 404
