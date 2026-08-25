"""Acceptance, integration, and unit tests for convention enrollment and active selection."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, cast

import pytest
import yaml
from django.contrib import admin
from django.db import IntegrityError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions.admin import ConventionEnrollmentAdmin
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from profiles.models import PlayerProfile
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


def _setup_eligible_player(
    clerk_user_id: str, handle: str = "player_one"
) -> tuple[User, Client]:
    user = create_test_user(clerk_user_id=clerk_user_id)
    PlayerProfile.objects.create(
        user=user,
        handle=handle,
        display_name="Player One",
        onboarding_completed_at=timezone.now(),
        is_enabled=True,
    )
    client = force_authenticated_client(user=user)
    return user, client


def _create_convention(
    name: str = "Anthrocon 2026",
    status: str = ConventionStatus.ACTIVE,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> Convention:
    return Convention.objects.create(
        name=name,
        status=status,
        start_date=start_date or datetime.date(2026, 7, 2),
        end_date=end_date or datetime.date(2026, 7, 5),
    )


# --- Model and Constraint Tests ---


@pytest.mark.django_db
def test_convention_enrollment_creation_and_str() -> None:
    """ConventionEnrollment creates successfully with default is_active=False."""
    user, _ = _setup_eligible_player("user_enrollment_create")
    convention = _create_convention()

    enrollment = ConventionEnrollment.objects.create(
        user=user,
        convention=convention,
    )

    assert enrollment.pk is not None
    assert enrollment.user == user
    assert enrollment.convention == convention
    assert enrollment.is_active is False
    assert enrollment.created_at is not None
    assert enrollment.updated_at is not None
    assert str(enrollment) == f"Enrollment: {user.pk} -> {convention.pk} (active=False)"


@pytest.mark.django_db
def test_convention_enrollment_unique_user_convention_constraint() -> None:
    """Database constraint prevents a user from enrolling in the same convention twice."""
    user, _ = _setup_eligible_player("user_enrollment_duplicate")
    convention = _create_convention()

    ConventionEnrollment.objects.create(user=user, convention=convention)

    with pytest.raises(IntegrityError):
        ConventionEnrollment.objects.create(user=user, convention=convention)


@pytest.mark.django_db
def test_convention_enrollment_single_active_constraint() -> None:
    """Database partial unique constraint enforces at most one is_active=True enrollment per user."""
    user, _ = _setup_eligible_player("user_single_active")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")

    ConventionEnrollment.objects.create(user=user, convention=con1, is_active=True)

    with pytest.raises(IntegrityError):
        ConventionEnrollment.objects.create(user=user, convention=con2, is_active=True)


@pytest.mark.django_db
def test_convention_enrollment_multiple_inactive_allowed() -> None:
    """A user can have multiple inactive convention enrollments."""
    user, _ = _setup_eligible_player("user_multi_inactive")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")

    e1 = ConventionEnrollment.objects.create(
        user=user, convention=con1, is_active=False
    )
    e2 = ConventionEnrollment.objects.create(
        user=user, convention=con2, is_active=False
    )

    assert e1.pk is not None
    assert e2.pk is not None


# --- Authentication and Eligibility Tests ---


@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_enrollment_endpoints_require_authentication() -> None:
    """Unauthenticated requests to enrollment endpoints return 401."""
    client = Client()

    assert client.get("/api/conventions/enrollments/").status_code == 401
    assert (
        client.post("/api/conventions/enrollments/", {"convention_id": 1}).status_code
        == 401
    )
    assert client.get("/api/conventions/active/").status_code == 401
    assert (
        client.put("/api/conventions/active/", {"convention_id": 1}).status_code == 401
    )
    assert client.delete("/api/conventions/active/").status_code == 401


@pytest.mark.django_db
def test_enrollment_mutations_require_completed_eligible_profile() -> None:
    """Ineligible users (un-onboarded or disabled) are rejected with 403 on mutations."""
    # 1. Un-onboarded user (no profile)
    user_no_profile = create_test_user(clerk_user_id="user_unonboarded")
    client_unonboarded = force_authenticated_client(user=user_no_profile)
    convention = _create_convention()

    # GET is safe (returns empty list / null active)
    assert client_unonboarded.get("/api/conventions/enrollments/").status_code == 200
    assert client_unonboarded.get("/api/conventions/active/").status_code == 200

    # Mutations return 403
    enroll_res = client_unonboarded.post(
        "/api/conventions/enrollments/",
        {"convention_id": convention.pk},
        content_type="application/json",
    )
    assert enroll_res.status_code == 403

    set_active_res = client_unonboarded.put(
        "/api/conventions/active/",
        {"convention_id": convention.pk},
        content_type="application/json",
    )
    assert set_active_res.status_code == 403

    clear_active_res = client_unonboarded.delete("/api/conventions/active/")
    assert clear_active_res.status_code == 403

    # 2. Disabled profile
    user_disabled = create_test_user(clerk_user_id="user_disabled")
    PlayerProfile.objects.create(
        user=user_disabled,
        handle="disabled_user",
        display_name="Disabled User",
        onboarding_completed_at=timezone.now(),
        is_enabled=False,
    )
    client_disabled = force_authenticated_client(user=user_disabled)

    assert (
        client_disabled.post(
            "/api/conventions/enrollments/",
            {"convention_id": convention.pk},
            content_type="application/json",
        ).status_code
        == 403
    )
    assert (
        client_disabled.put(
            "/api/conventions/active/",
            {"convention_id": convention.pk},
            content_type="application/json",
        ).status_code
        == 403
    )


# --- Enrollment List and Create API Tests ---


@pytest.mark.django_db
def test_list_enrollments_returns_only_own_enrollments() -> None:
    """User can list only their own enrollments, ordered by newest first."""
    user1, client1 = _setup_eligible_player("user_1", handle="player1")
    user2, client2 = _setup_eligible_player("user_2", handle="player2")

    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")

    e1 = ConventionEnrollment.objects.create(
        user=user1, convention=con1, is_active=True
    )
    ConventionEnrollment.objects.create(user=user2, convention=con2, is_active=True)

    res1 = client1.get("/api/conventions/enrollments/")
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["id"] == e1.pk
    assert data1[0]["convention"]["id"] == con1.pk
    assert data1[0]["convention"]["name"] == "Con 1"
    assert data1[0]["is_active"] is True

    res2 = client2.get("/api/conventions/enrollments/")
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["convention"]["id"] == con2.pk


@pytest.mark.django_db
def test_enroll_in_active_convention_success() -> None:
    """Eligible user can enroll in an active convention."""
    user, client = _setup_eligible_player("user_enroll_ok")
    convention = _create_convention()

    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": convention.pk},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["convention"]["id"] == convention.pk
    assert data["convention"]["name"] == convention.name
    assert data["is_active"] is False

    enrollment = ConventionEnrollment.objects.get(user=user, convention=convention)
    assert enrollment.is_active is False


@pytest.mark.django_db
def test_enroll_with_set_active_flag() -> None:
    """Enrolling with set_active=True marks the new enrollment as active."""
    user, client = _setup_eligible_player("user_enroll_active")
    convention = _create_convention()

    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": convention.pk, "set_active": True},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["is_active"] is True

    enrollment = ConventionEnrollment.objects.get(user=user, convention=convention)
    assert enrollment.is_active is True


@pytest.mark.django_db
def test_enroll_idempotency_returns_existing_enrollment() -> None:
    """Duplicate enrollment request is idempotent, returning 200 with existing enrollment."""
    user, client = _setup_eligible_player("user_enroll_idem")
    convention = _create_convention()

    # First enrollment
    res1 = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": convention.pk},
        content_type="application/json",
    )
    assert res1.status_code == 201

    # Second enrollment (duplicate)
    res2 = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": convention.pk},
        content_type="application/json",
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == res1.json()["id"]
    assert (
        ConventionEnrollment.objects.filter(user=user, convention=convention).count()
        == 1
    )


@pytest.mark.django_db
def test_enroll_in_inactive_convention_fails() -> None:
    """Attempting to enroll in a non-active convention (draft, paused, completed, cancelled) fails with 400."""
    _, client = _setup_eligible_player("user_enroll_inactive")

    for status in [
        ConventionStatus.DRAFT,
        ConventionStatus.PAUSED,
        ConventionStatus.COMPLETED,
        ConventionStatus.CANCELLED,
    ]:
        con = _create_convention(name=f"Con {status}", status=status)
        response = client.post(
            "/api/conventions/enrollments/",
            {"convention_id": con.pk},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert (
            "convention_id" in response.json() or "non_field_errors" in response.json()
        )


@pytest.mark.django_db
def test_enroll_in_nonexistent_convention_returns_404() -> None:
    """Attempting to enroll in a non-existent convention ID returns 404."""
    _, client = _setup_eligible_player("user_enroll_404")

    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": 999999},
        content_type="application/json",
    )
    assert response.status_code == 404


# --- Active Convention Selection API Tests ---


@pytest.mark.django_db
def test_get_active_convention_when_none_selected() -> None:
    """GET /api/conventions/active/ returns 200 with enrollment=null when none selected."""
    _, client = _setup_eligible_player("user_no_active")

    response = client.get("/api/conventions/active/")
    assert response.status_code == 200
    assert response.json() == {"enrollment": None}


@pytest.mark.django_db
def test_get_active_convention_when_selected() -> None:
    """GET /api/conventions/active/ returns the active enrollment."""
    user, client = _setup_eligible_player("user_has_active")
    convention = _create_convention()
    enrollment = ConventionEnrollment.objects.create(
        user=user, convention=convention, is_active=True
    )

    response = client.get("/api/conventions/active/")
    assert response.status_code == 200
    data = response.json()
    assert data["enrollment"] is not None
    assert data["enrollment"]["id"] == enrollment.pk
    assert data["enrollment"]["convention"]["id"] == convention.pk
    assert data["enrollment"]["is_active"] is True


@pytest.mark.django_db
def test_select_active_convention_switches_active_atomically() -> None:
    """Selecting a new active convention deactivates any previously active convention."""
    user, client = _setup_eligible_player("user_switch_active")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")

    e1 = ConventionEnrollment.objects.create(user=user, convention=con1, is_active=True)
    e2 = ConventionEnrollment.objects.create(
        user=user, convention=con2, is_active=False
    )

    response = client.put(
        "/api/conventions/active/",
        {"convention_id": con2.pk},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["enrollment"]["convention"]["id"] == con2.pk
    assert response.json()["enrollment"]["is_active"] is True

    e1.refresh_from_db()
    e2.refresh_from_db()
    assert e1.is_active is False
    assert e2.is_active is True


@pytest.mark.django_db
def test_select_active_convention_not_enrolled_returns_400() -> None:
    """Attempting to select a convention as active without prior enrollment returns 400."""
    _, client = _setup_eligible_player("user_not_enrolled")
    con = _create_convention(name="Con Unenrolled")

    response = client.put(
        "/api/conventions/active/",
        {"convention_id": con.pk},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_select_active_convention_inactive_lifecycle_returns_400() -> None:
    """Attempting to activate an enrollment whose convention is no longer active returns 400."""
    user, client = _setup_eligible_player("user_paused_active")
    con = _create_convention(name="Paused Con", status=ConventionStatus.PAUSED)
    # Force enrollment creation (bypassing service validation)
    ConventionEnrollment.objects.create(user=user, convention=con, is_active=False)

    response = client.put(
        "/api/conventions/active/",
        {"convention_id": con.pk},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_clear_active_convention() -> None:
    """DELETE /api/conventions/active/ clears active selection and returns 204."""
    user, client = _setup_eligible_player("user_clear_active")
    con = _create_convention()
    enrollment = ConventionEnrollment.objects.create(
        user=user, convention=con, is_active=True
    )

    response = client.delete("/api/conventions/active/")
    assert response.status_code == 204

    enrollment.refresh_from_db()
    assert enrollment.is_active is False

    # Calling delete when none active is also 204 (idempotent)
    assert client.delete("/api/conventions/active/").status_code == 204


@pytest.mark.django_db
def test_active_convention_when_convention_becomes_inactive_or_ended() -> None:
    """When an active convention status becomes paused/completed/cancelled, GET still returns enrollment reflecting latest convention status."""
    user, client = _setup_eligible_player("user_con_ended")
    con = _create_convention(name="Ending Con", status=ConventionStatus.ACTIVE)
    enrollment = ConventionEnrollment.objects.create(
        user=user, convention=con, is_active=True
    )

    # Operator completes the convention
    con.status = ConventionStatus.COMPLETED
    con.save(update_fields=["status"])

    response = client.get("/api/conventions/active/")
    assert response.status_code == 200
    data = response.json()
    assert data["enrollment"]["id"] == enrollment.pk
    assert data["enrollment"]["convention"]["status"] == "completed"
    assert data["enrollment"]["is_active"] is True


# --- Django Admin Tests ---


def test_convention_enrollment_admin_registration() -> None:
    """ConventionEnrollment model is registered in Django admin with ConventionEnrollmentAdmin."""
    assert ConventionEnrollment in admin.site._registry  # pyright: ignore[reportUnknownMemberType, reportPrivateUsage]
    model_admin = admin.site._registry[ConventionEnrollment]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportPrivateUsage]
    assert isinstance(model_admin, ConventionEnrollmentAdmin)
    assert "user__clerk_user_id" in model_admin.search_fields
    assert "is_active" in model_admin.list_filter
    assert "id" in model_admin.list_display


@pytest.mark.django_db
def test_convention_enrollment_admin_operator_inspection(client: Client) -> None:
    """Operator can inspect enrollment list and change view in admin."""
    admin_user = User.objects.create_superuser(
        clerk_user_id="user_admin_enrollment",
        password="test-admin-password",
    )
    client.force_login(admin_user)

    player_user = create_test_user(clerk_user_id="player_in_admin")
    con = _create_convention()
    enrollment = ConventionEnrollment.objects.create(
        user=player_user, convention=con, is_active=True
    )

    list_url = reverse("admin:conventions_conventionenrollment_changelist")
    list_response = client.get(list_url)
    assert list_response.status_code == 200
    assert str(enrollment.pk).encode() in list_response.content

    change_url = reverse(
        "admin:conventions_conventionenrollment_change", args=(enrollment.pk,)
    )
    change_response = client.get(change_url)
    assert change_response.status_code == 200


# --- OpenAPI Contract Test ---


def test_enrollment_openapi_schema_contract(client: Client) -> None:
    """OpenAPI schema correctly defines enrollment and active convention endpoints."""
    schema = _schema(client)
    paths = schema["paths"]

    assert "/api/conventions/enrollments/" in paths
    assert "/api/conventions/active/" in paths

    # Enrollments list/create
    enrollments_path = paths["/api/conventions/enrollments/"]
    assert "get" in enrollments_path
    assert "post" in enrollments_path

    # Active convention get/put/delete
    active_path = paths["/api/conventions/active/"]
    assert "get" in active_path
    assert "put" in active_path
    assert "delete" in active_path

    # Verify enrollment list schema
    list_op = enrollments_path["get"]
    list_res_200 = list_op["responses"]["200"]
    list_schema = _dereference_schema(
        schema, list_res_200["content"]["application/json"]["schema"]
    )
    assert list_schema["type"] == "array"
    item_schema = _dereference_schema(schema, list_schema["items"])
    assert set(item_schema["properties"]) == {
        "id",
        "convention",
        "is_active",
        "created_at",
    }

    # Verify enroll request schema
    enroll_post = enrollments_path["post"]
    enroll_req_schema = _dereference_schema(
        schema, enroll_post["requestBody"]["content"]["application/json"]["schema"]
    )
    assert set(enroll_req_schema["properties"]) == {"convention_id", "set_active"}
