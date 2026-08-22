"""Acceptance and unit tests for the V0 convention domain."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from conventions.admin import ConventionAdmin
from conventions.models import Convention, ConventionStatus
from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    create_test_user,
    force_authenticated_client,
)


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
def test_convention_creation_and_defaults() -> None:
    """Convention model sets default draft status and custom __str__ format."""
    start = datetime.date(2026, 7, 2)
    end = datetime.date(2026, 7, 5)
    convention = Convention.objects.create(
        name="Anthrocon 2026",
        start_date=start,
        end_date=end,
    )

    assert convention.pk is not None
    assert convention.status == ConventionStatus.DRAFT
    assert convention.name == "Anthrocon 2026"
    assert convention.start_date == start
    assert convention.end_date == end
    assert convention.created_at is not None
    assert convention.updated_at is not None
    assert str(convention) == f"Anthrocon 2026 ({convention.pk})"


@pytest.mark.django_db
def test_convention_is_playable_property() -> None:
    """is_playable returns True only when convention status is ACTIVE."""
    start = datetime.date(2026, 7, 2)
    end = datetime.date(2026, 7, 5)

    draft_con = Convention.objects.create(
        name="Con Draft",
        status=ConventionStatus.DRAFT,
        start_date=start,
        end_date=end,
    )
    assert not draft_con.is_playable

    active_con = Convention.objects.create(
        name="Con Active",
        status=ConventionStatus.ACTIVE,
        start_date=start,
        end_date=end,
    )
    assert active_con.is_playable

    paused_con = Convention.objects.create(
        name="Con Paused",
        status=ConventionStatus.PAUSED,
        start_date=start,
        end_date=end,
    )
    assert not paused_con.is_playable

    completed_con = Convention.objects.create(
        name="Con Completed",
        status=ConventionStatus.COMPLETED,
        start_date=start,
        end_date=end,
    )
    assert not completed_con.is_playable

    cancelled_con = Convention.objects.create(
        name="Con Cancelled",
        status=ConventionStatus.CANCELLED,
        start_date=start,
        end_date=end,
    )
    assert not cancelled_con.is_playable


def test_convention_model_clean_validation() -> None:
    """Model clean() rejects conventions where end_date is before start_date."""
    convention = Convention(
        name="Invalid Date Con",
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2026, 7, 5),
        end_date=datetime.date(2026, 7, 2),
    )
    with pytest.raises(ValidationError) as exc_info:
        convention.clean()

    assert "end_date" in exc_info.value.message_dict


@pytest.mark.django_db
def test_convention_database_rejects_empty_name() -> None:
    """Database check constraint rejects empty convention name."""
    with pytest.raises(IntegrityError):
        Convention.objects.create(
            name="",
            start_date=datetime.date(2026, 7, 2),
            end_date=datetime.date(2026, 7, 5),
        )


@pytest.mark.django_db
def test_convention_database_rejects_end_date_before_start_date() -> None:
    """Database check constraint rejects end_date < start_date."""
    with pytest.raises(IntegrityError):
        Convention.objects.create(
            name="Invalid Con",
            start_date=datetime.date(2026, 7, 5),
            end_date=datetime.date(2026, 7, 2),
        )


@pytest.mark.django_db
def test_convention_database_rejects_invalid_status() -> None:
    """Database check constraint rejects status values outside ConventionStatus."""
    with pytest.raises(IntegrityError):
        Convention.objects.create(
            name="Invalid Status Con",
            status="unexpected",
            start_date=datetime.date(2026, 7, 2),
            end_date=datetime.date(2026, 7, 5),
        )


def test_convention_admin_is_registered() -> None:
    """Convention model is registered with ConventionAdmin in Django admin."""
    assert Convention in admin.site._registry  # pyright: ignore[reportUnknownMemberType, reportPrivateUsage]
    model_admin = admin.site._registry[Convention]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportPrivateUsage]
    assert isinstance(model_admin, ConventionAdmin)
    assert "name" in model_admin.search_fields
    assert "status" in model_admin.list_filter
    assert "id" in model_admin.list_display


@pytest.mark.django_db
def test_convention_admin_operator_workflow_and_validation(client: Client) -> None:
    """Operators can create, inspect, edit lifecycle status, and receive date validation in admin."""
    admin_user = User.objects.create_superuser(
        clerk_user_id="user_admin_operator",
        password="test-admin-password",
    )
    client.force_login(admin_user)

    # 1. Add View: Create a convention in draft status
    add_url = reverse("admin:conventions_convention_add")
    add_response = client.post(
        add_url,
        {
            "name": "Midwest FurFest 2026",
            "status": ConventionStatus.DRAFT,
            "start_date": "2026-12-03",
            "end_date": "2026-12-06",
        },
    )
    assert add_response.status_code == 302
    convention = Convention.objects.get(name="Midwest FurFest 2026")
    assert convention.status == ConventionStatus.DRAFT
    assert convention.start_date == datetime.date(2026, 12, 3)
    assert convention.end_date == datetime.date(2026, 12, 6)

    # 2. Change View: Edit lifecycle state from draft -> active -> paused
    change_url = reverse("admin:conventions_convention_change", args=(convention.pk,))
    active_response = client.post(
        change_url,
        {
            "name": "Midwest FurFest 2026",
            "status": ConventionStatus.ACTIVE,
            "start_date": "2026-12-03",
            "end_date": "2026-12-06",
        },
    )
    assert active_response.status_code == 302
    convention.refresh_from_db()
    assert convention.status == ConventionStatus.ACTIVE
    assert convention.is_playable

    paused_response = client.post(
        change_url,
        {
            "name": "Midwest FurFest 2026",
            "status": ConventionStatus.PAUSED,
            "start_date": "2026-12-03",
            "end_date": "2026-12-06",
        },
    )
    assert paused_response.status_code == 302
    convention.refresh_from_db()
    assert convention.status == ConventionStatus.PAUSED
    assert not convention.is_playable

    # 3. Form Validation: Invalid date range (end_date < start_date) is rejected
    invalid_date_response = client.post(
        change_url,
        {
            "name": "Midwest FurFest 2026",
            "status": ConventionStatus.PAUSED,
            "start_date": "2026-12-06",
            "end_date": "2026-12-03",
        },
    )
    assert invalid_date_response.status_code == 200
    assert b"End date must be on or after start date." in invalid_date_response.content


@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_convention_endpoints_require_authentication() -> None:
    """Unauthenticated requests to convention endpoints return 401 with Bearer challenge."""
    client = Client()

    list_response = client.get("/api/conventions/")
    assert list_response.status_code == 401
    assert list_response["WWW-Authenticate"] == "Bearer"

    detail_response = client.get("/api/conventions/1/")
    assert detail_response.status_code == 401
    assert detail_response["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
def test_convention_list_authenticated_returns_active_conventions() -> None:
    """Authenticated player can list only active conventions with safe serialized fields."""
    user = create_test_user(clerk_user_id="user_conventions_list")
    client = force_authenticated_client(user=user)

    con_active = Convention.objects.create(
        name="Alpha Con 2026",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 4),
    )
    # Inactive conventions should be excluded from player list
    Convention.objects.create(
        name="Draft Con 2026",
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2026, 8, 1),
        end_date=datetime.date(2026, 8, 4),
    )
    Convention.objects.create(
        name="Paused Con 2026",
        status=ConventionStatus.PAUSED,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2026, 9, 4),
    )
    Convention.objects.create(
        name="Completed Con 2025",
        status=ConventionStatus.COMPLETED,
        start_date=datetime.date(2025, 6, 1),
        end_date=datetime.date(2025, 6, 4),
    )
    Convention.objects.create(
        name="Cancelled Con 2026",
        status=ConventionStatus.CANCELLED,
        start_date=datetime.date(2026, 10, 1),
        end_date=datetime.date(2026, 10, 4),
    )

    response = client.get("/api/conventions/")
    assert response.status_code == 200

    data = cast(list[dict[str, Any]], response.json())
    assert isinstance(data, list)
    assert len(data) == 1

    first_item = data[0]
    expected_fields = {"id", "name", "status", "start_date", "end_date"}
    assert set(first_item.keys()) == expected_fields
    assert first_item["id"] == con_active.pk
    assert first_item["name"] == "Alpha Con 2026"
    assert first_item["status"] == "active"
    assert first_item["start_date"] == "2026-06-01"
    assert first_item["end_date"] == "2026-06-04"


@pytest.mark.django_db
def test_convention_detail_authenticated_returns_convention() -> None:
    """Authenticated player can retrieve convention details by ID."""
    user = create_test_user(clerk_user_id="user_conventions_detail")
    client = force_authenticated_client(user=user)

    convention = Convention.objects.create(
        name="Midwest FurFest 2026",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 12, 3),
        end_date=datetime.date(2026, 12, 6),
    )

    response = client.get(f"/api/conventions/{convention.pk}/")
    assert response.status_code == 200
    assert response.json() == {
        "id": convention.pk,
        "name": "Midwest FurFest 2026",
        "status": "active",
        "start_date": "2026-12-03",
        "end_date": "2026-12-06",
    }


@pytest.mark.django_db
def test_convention_detail_not_found_returns_404() -> None:
    """Requesting non-existent convention ID returns 404."""
    user = create_test_user(clerk_user_id="user_conventions_404")
    client = force_authenticated_client(user=user)

    response = client.get("/api/conventions/999999/")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_conventions_openapi_schema_contract(client: Client) -> None:
    """OpenAPI schema correctly describes /api/conventions/ and /api/conventions/{id}/."""
    schema = _schema(client)

    paths = schema["paths"]
    assert "/api/conventions/" in paths
    assert "/api/conventions/{id}/" in paths

    # Verify List endpoint schema
    list_op = paths["/api/conventions/"]["get"]
    assert list_op["summary"] == "List conventions"
    list_response_200 = list_op["responses"]["200"]
    list_schema = _dereference_schema(
        schema, list_response_200["content"]["application/json"]["schema"]
    )
    assert list_schema["type"] == "array"
    item_schema = _dereference_schema(schema, list_schema["items"])
    assert set(item_schema["properties"]) == {
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
    }

    # Verify Detail endpoint schema
    detail_op = paths["/api/conventions/{id}/"]["get"]
    assert detail_op["summary"] == "Retrieve convention"
    detail_response_200 = detail_op["responses"]["200"]
    detail_schema = _dereference_schema(
        schema, detail_response_200["content"]["application/json"]["schema"]
    )
    assert set(detail_schema["properties"]) == {
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
    }
    assert "404" in detail_op["responses"]
