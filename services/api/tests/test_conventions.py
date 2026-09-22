"""Acceptance and unit tests for the V0 convention domain."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, cast
from unittest.mock import patch

import pytest
import yaml
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from conventions.admin import ConventionAdmin
from conventions.models import Convention, ConventionStatus
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
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


def test_convention_model_clean_handles_missing_dates_safely() -> None:
    """Model clean() handles missing start_date or end_date without raising TypeError."""
    convention_no_end = Convention(
        name="No End Date Con",
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2026, 7, 5),
    )
    convention_no_end.clean()

    convention_no_start = Convention(
        name="No Start Date Con",
        status=ConventionStatus.DRAFT,
        end_date=datetime.date(2026, 7, 5),
    )
    convention_no_start.clean()


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


@pytest.mark.django_db
def test_convention_admin_rejects_missing_and_malformed_dates(client: Client) -> None:
    """Admin form validation gracefully rejects missing and malformed dates without crashing."""
    admin_user = User.objects.create_superuser(
        clerk_user_id="user_admin_date_validation",
        password="test-admin-password",
    )
    client.force_login(admin_user)

    add_url = reverse("admin:conventions_convention_add")

    # Missing required end_date
    missing_end_date_response = client.post(
        add_url,
        {
            "name": "Missing End Date Con",
            "status": ConventionStatus.DRAFT,
            "start_date": "2026-12-03",
            "end_date": "",
        },
    )
    assert missing_end_date_response.status_code == 200
    assert b"This field is required." in missing_end_date_response.content

    # Malformed start_date
    malformed_date_response = client.post(
        add_url,
        {
            "name": "Malformed Date Con",
            "status": ConventionStatus.DRAFT,
            "start_date": "not-a-real-date",
            "end_date": "2026-12-06",
        },
    )
    assert malformed_date_response.status_code == 200
    assert b"Enter a valid date." in malformed_date_response.content


def _convention_staff(*permissions: tuple[str, str]) -> User:
    user = create_test_user()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        *[
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
            for app_label, codename in permissions
        ]
    )
    return User.objects.get(pk=user.pk)


def _convention_post_data(
    convention: Convention,
    *,
    status: ConventionStatus,
    name: str | None = None,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> dict[str, str]:
    return {
        "name": name or convention.name,
        "status": status,
        "start_date": (start_date or convention.start_date).isoformat(),
        "end_date": (end_date or convention.end_date).isoformat(),
    }


def _new_non_playable_convention() -> Convention:
    return Convention.objects.create(
        name="Convention admin permission target",
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 2),
    )


def _assert_convention_event(
    user: User,
    convention_id: int,
    actor_class: OperatorActorClass,
    outcome: OperatorAuditOutcome,
) -> None:
    events = list(
        OperatorAuditEvent.objects.filter(
            affected_record_id=convention_id, actor=user, outcome=outcome
        )
    )
    assert len(events) == 1
    event = events[0]
    assert (
        event.action,
        event.actor_class,
        event.affected_record_type,
        event.outcome,
    ) == (
        OperatorAction.SET_CONVENTION_PLAYABILITY,
        actor_class,
        OperatorTargetType.CONVENTION,
        outcome,
    )


@pytest.mark.django_db
def test_convention_playability_role_matrix_requires_its_exact_permission() -> None:
    """AC-1/2/4: staff, generic change, and other sensitive authority cannot make playability live."""
    unrelated = _convention_staff(("conventions", "remove_convention_enrollment"))
    cases = (
        (
            _convention_staff(),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            unrelated,
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _convention_staff(("conventions", "change_convention")),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _convention_staff(("conventions", "set_convention_playability")),
            True,
            OperatorActorClass.OPERATOR,
            OperatorAuditOutcome.SUCCEEDED,
        ),
        (
            User.objects.create_superuser("convention_emergency", password="pw"),
            True,
            OperatorActorClass.EMERGENCY_SUPERUSER,
            OperatorAuditOutcome.SUCCEEDED,
        ),
    )
    player = create_test_user()
    player_target = _new_non_playable_convention()
    player_url = reverse(
        "admin:conventions_convention_change", args=(player_target.pk,)
    )
    player_client = Client()
    player_client.force_login(player)
    response = player_client.post(
        player_url, _convention_post_data(player_target, status=ConventionStatus.ACTIVE)
    )
    assert response.status_code == 302
    assert response["Location"] == f"/admin/login/?next={player_url}"
    player_target.refresh_from_db()
    assert player_target.is_playable is False
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=player_target.pk
    ).exists()
    for user, permitted, actor_class, outcome in cases:
        convention = _new_non_playable_convention()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:conventions_convention_change", args=(convention.pk,)),
            _convention_post_data(convention, status=ConventionStatus.ACTIVE),
        )
        assert response.status_code == (302 if permitted else 403)
        convention.refresh_from_db()
        assert convention.is_playable is permitted
        _assert_convention_event(user, convention.pk, actor_class, outcome)


@pytest.mark.django_db
def test_convention_admin_keeps_non_playable_edits_ordinary_and_playability_operator_metadata_read_only() -> (
    None
):
    """AC-1/4/9: ordinary corrections need no audit; narrow playability authority cannot edit metadata."""
    convention = _new_non_playable_convention()
    editor = _convention_staff(("conventions", "change_convention"))
    client = Client()
    client.force_login(editor)
    url = reverse("admin:conventions_convention_change", args=(convention.pk,))
    assert (
        client.post(
            url,
            _convention_post_data(
                convention, status=ConventionStatus.PAUSED, name="Ordinary correction"
            ),
        ).status_code
        == 302
    )
    convention.refresh_from_db()
    assert (convention.name, convention.status, OperatorAuditEvent.objects.count()) == (
        "Ordinary correction",
        ConventionStatus.PAUSED,
        0,
    )
    playability_operator = _convention_staff(
        ("conventions", "set_convention_playability")
    )
    client.force_login(playability_operator)
    forged = client.post(
        url,
        _convention_post_data(
            convention,
            status=ConventionStatus.ACTIVE,
            name="Forged metadata",
            start_date=datetime.date(2026, 6, 10),
            end_date=datetime.date(2026, 6, 12),
        ),
    )
    assert forged.status_code == 403
    convention.refresh_from_db()
    assert (
        convention.name,
        convention.start_date,
        convention.end_date,
        convention.status,
        convention.is_playable,
    ) == (
        "Ordinary correction",
        datetime.date(2026, 6, 1),
        datetime.date(2026, 6, 2),
        ConventionStatus.PAUSED,
        False,
    )
    _assert_convention_event(
        playability_operator,
        convention.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
def test_change_convention_can_correct_active_metadata_without_sensitive_audit() -> (
    None
):
    """AC-1/4: ordinary metadata correction stays ordinary while a convention is playable."""
    convention = Convention.objects.create(
        name="Active metadata source",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 2),
    )
    editor = _convention_staff(("conventions", "change_convention"))
    client = Client()
    client.force_login(editor)
    response = client.post(
        reverse("admin:conventions_convention_change", args=(convention.pk,)),
        _convention_post_data(
            convention,
            status=ConventionStatus.ACTIVE,
            name="Active metadata correction",
            start_date=datetime.date(2026, 6, 3),
            end_date=datetime.date(2026, 6, 6),
        ),
    )
    assert response.status_code == 302
    convention.refresh_from_db()
    assert (
        convention.name,
        convention.start_date,
        convention.end_date,
        convention.status,
        convention.is_playable,
    ) == (
        "Active metadata correction",
        datetime.date(2026, 6, 3),
        datetime.date(2026, 6, 6),
        ConventionStatus.ACTIVE,
        True,
    )
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=convention.pk
    ).exists()


@pytest.mark.django_db
def test_playability_only_operator_cannot_make_nonplayable_status_edits() -> None:
    """AC-1/4/9: narrow playability authority cannot repurpose ordinary status edits."""
    convention = _new_non_playable_convention()
    original = (
        convention.name,
        convention.start_date,
        convention.end_date,
        convention.status,
        convention.is_playable,
    )
    operator = _convention_staff(("conventions", "set_convention_playability"))
    client = Client()
    client.force_login(operator)
    response = client.post(
        reverse("admin:conventions_convention_change", args=(convention.pk,)),
        _convention_post_data(convention, status=ConventionStatus.PAUSED),
    )
    assert response.status_code == 403
    convention.refresh_from_db()
    assert (
        convention.name,
        convention.start_date,
        convention.end_date,
        convention.status,
        convention.is_playable,
    ) == original
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=convention.pk
    ).exists()


@pytest.mark.django_db
def test_missing_convention_playability_post_is_rejected_and_audited() -> None:
    """AC-4: missing targets do not bypass the Convention sensitive POST boundary."""
    operator = _convention_staff(("conventions", "set_convention_playability"))
    missing_id = 999_999
    client = Client()
    client.force_login(operator)

    response = client.post(
        reverse("admin:conventions_convention_change", args=(missing_id,)),
        {
            "name": "Missing Convention",
            "status": ConventionStatus.ACTIVE,
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 403
    assert not Convention.objects.filter(pk=missing_id).exists()
    _assert_convention_event(
        operator,
        missing_id,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
def test_convention_bulk_delete_cannot_bypass_playable_delete_boundary() -> None:
    """AC-4/9: confirmed bulk deletion cannot bypass the per-object playable denial."""
    convention = Convention.objects.create(
        name="Bulk delete protected active convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 2),
    )
    deleter = _convention_staff(
        ("conventions", "view_convention"), ("conventions", "delete_convention")
    )
    client = Client()
    client.force_login(deleter)
    response = client.post(
        reverse("admin:conventions_convention_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": str(convention.pk),
            "post": "yes",
        },
    )
    assert response.status_code == 403
    assert Convention.objects.filter(pk=convention.pk).exists()
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=convention.pk
    ).exists()


@pytest.mark.django_db
def test_convention_admin_closes_playable_create_delete_and_same_state_paths() -> None:
    """AC-4/9: playable creation/deletion stays closed while ACTIVE no-ops stay ordinary."""
    superuser = User.objects.create_superuser("convention_closed_paths", password="pw")
    client = Client()
    client.force_login(superuser)
    add_url = reverse("admin:conventions_convention_add")
    active_add = client.post(
        add_url,
        {
            "name": "Must not start playable",
            "status": ConventionStatus.ACTIVE,
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
        },
    )
    assert active_add.status_code == 200
    assert not Convention.objects.filter(name="Must not start playable").exists()
    assert OperatorAuditEvent.objects.count() == 0
    playable = _new_non_playable_convention()
    client.post(
        reverse("admin:conventions_convention_change", args=(playable.pk,)),
        _convention_post_data(playable, status=ConventionStatus.ACTIVE),
    )
    playable.refresh_from_db()
    assert playable.is_playable
    assert (
        client.post(
            reverse("admin:conventions_convention_delete", args=(playable.pk,)),
            {"post": "yes"},
        ).status_code
        == 403
    )
    assert Convention.objects.filter(pk=playable.pk).exists()
    audit_count = OperatorAuditEvent.objects.filter(
        affected_record_id=playable.pk
    ).count()
    assert (
        client.post(
            reverse("admin:conventions_convention_change", args=(playable.pk,)),
            _convention_post_data(playable, status=ConventionStatus.ACTIVE),
        ).status_code
        == 302
    )
    playable.refresh_from_db()
    assert playable.status == ConventionStatus.ACTIVE and playable.is_playable
    assert (
        OperatorAuditEvent.objects.filter(affected_record_id=playable.pk).count()
        == audit_count
    )


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


@pytest.mark.django_db
def test_convention_active_to_non_playable_requires_sensitive_permission() -> None:
    convention = _new_non_playable_convention()
    client = Client()
    client.force_login(
        User.objects.create_superuser("convention_reverse_seed", password="pw")
    )
    url = reverse("admin:conventions_convention_change", args=(convention.pk,))
    assert (
        client.post(
            url, _convention_post_data(convention, status=ConventionStatus.ACTIVE)
        ).status_code
        == 302
    )
    ordinary = _convention_staff(("conventions", "change_convention"))
    client.force_login(ordinary)
    assert (
        client.post(
            url, _convention_post_data(convention, status=ConventionStatus.PAUSED)
        ).status_code
        == 403
    )
    convention.refresh_from_db()
    assert convention.status == ConventionStatus.ACTIVE
    _assert_convention_event(
        ordinary,
        convention.pk,
        OperatorActorClass.UNAUTHORIZED_ACTOR,
        OperatorAuditOutcome.DENIED,
    )
    operator = _convention_staff(("conventions", "set_convention_playability"))
    client.force_login(operator)
    assert (
        client.post(
            url, _convention_post_data(convention, status=ConventionStatus.PAUSED)
        ).status_code
        == 302
    )
    convention.refresh_from_db()
    assert convention.status == ConventionStatus.PAUSED
    _assert_convention_event(
        operator,
        convention.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.SUCCEEDED,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("after_service", [False, True])
def test_convention_playability_failure_rolls_back_and_records_only_failed(
    after_service: bool,
) -> None:
    convention = _new_non_playable_convention()
    original = (
        convention.name,
        convention.status,
        convention.start_date,
        convention.end_date,
    )
    operator = _convention_staff(("conventions", "set_convention_playability"))
    client = Client()
    client.force_login(operator)
    url = reverse("admin:conventions_convention_change", args=(convention.pk,))
    target = (
        "conventions.admin.ConventionAdmin.log_change"
        if after_service
        else "conventions.admin.set_convention_admin_state"
    )
    with (
        patch(target, side_effect=RuntimeError("forced convention failure")),
        pytest.raises(RuntimeError, match="forced convention failure"),
    ):
        client.post(
            url, _convention_post_data(convention, status=ConventionStatus.ACTIVE)
        )
    convention.refresh_from_db()
    assert (
        convention.name,
        convention.status,
        convention.start_date,
        convention.end_date,
    ) == original
    _assert_convention_event(
        operator,
        convention.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.FAILED,
    )
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=convention.pk, outcome=OperatorAuditOutcome.SUCCEEDED
    ).exists()
