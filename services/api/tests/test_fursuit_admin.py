"""Restricted inspection-only fursuit administration acceptance contract."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Protocol, cast
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.files.storage import default_storage
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from accounts.models import User
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.catch_credential_test_support import create_credential
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import RECORDING_STORAGES


class _PermissionManager(Protocol):
    def add(self, *permissions: Permission) -> None: ...


class _UserWithPermissions(Protocol):
    user_permissions: _PermissionManager


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_admin_allows_only_enabled_toggle_and_never_exposes_key_or_clerk_identity() -> (
    None
):
    operator = User.objects.create_superuser(
        "operator", password="safe-local-admin-password"
    )
    record = create_fursuit_record(
        owner=create_eligible_user(),
        photo_key="images/0123456789abcdef0123456789abcdef.png",
    )
    client = Client()
    client.force_login(operator)
    list_response = client.get(reverse("admin:fursuits_fursuit_changelist"))
    storage = default_storage
    from tests.profile_test_support import RecordingStorage

    assert isinstance(storage, RecordingStorage)
    assert storage.url_calls == 0
    change = reverse("admin:fursuits_fursuit_change", args=(record.pk,))
    detail = client.get(change)
    assert storage.url_calls == 1
    before_update = record.updated_at
    tailtag_id_before = record.tailtag_id
    request = RequestFactory().get(change)
    request.user = operator
    model_admin: Any = cast(Any, admin.site)._registry[type(record)]
    form_class = model_admin.get_form(request, obj=record, change=True)
    assert "tailtag_id" in model_admin.get_readonly_fields(request, record)
    assert "tailtag_id" not in form_class.base_fields
    posted = client.post(change, {"is_enabled": ""})
    record.refresh_from_db()
    assert [response.status_code for response in (list_response, detail, posted)] == [
        200,
        200,
        302,
    ]
    assert (
        record.is_enabled is False
        and LogEntry.objects.filter(object_id=str(record.pk)).exists()
    )
    assert record.updated_at > before_update
    assert record.tailtag_id == tailtag_id_before
    after_toggle = record.updated_at
    repeated = client.post(change, {"is_enabled": ""})
    record.refresh_from_db()
    assert repeated.status_code == 302
    assert record.is_enabled is False and record.updated_at == after_toggle
    assert record.tailtag_id == tailtag_id_before
    forged = client.post(
        change,
        {"is_enabled": "", "tailtag_id": str(uuid.uuid4())},
    )
    record.refresh_from_db()
    assert forged.status_code == 302
    assert record.tailtag_id == tailtag_id_before
    rendered = list_response.content + detail.content
    assert (
        b"0123456789abcdef0123456789abcdef" not in rendered
        and record.owner.clerk_user_id.encode() not in rendered
    )
    assert client.get(reverse("admin:fursuits_fursuit_add")).status_code == 403
    assert (
        client.get(
            reverse("admin:fursuits_fursuit_delete", args=(record.pk,))
        ).status_code
        == 403
    )
    assert b'name="action"' not in list_response.content
    assert b"https://media.example.test/read/" not in list_response.content
    assert b"photo" in list_response.content.lower()
    assert str(tailtag_id_before).encode() in detail.content


@pytest.mark.django_db
def test_admin_search_excludes_clerk_and_opaque_key_but_finds_safe_record_identifiers() -> (
    None
):
    operator = User.objects.create_superuser(
        "search_operator", password="safe-local-admin-password"
    )
    owner = create_eligible_user(clerk_user_id="user_clerk_search_secret_115")
    record = create_fursuit_record(
        owner=owner,
        name="Searchable Character 115",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
    )
    if record.pk == owner.pk:
        record = create_fursuit_record(
            owner=owner,
            name="Searchable Character 115 Alternate",
            photo_key="images/fedcba9876543210fedcba9876543210.png",
        )
    assert str(record.pk) != str(owner.pk)
    client = Client()
    client.force_login(operator)
    changelist = reverse("admin:fursuits_fursuit_changelist")

    for forbidden in (owner.clerk_user_id, record.photo_key):
        response = client.get(changelist, {"q": forbidden})
        assert response.status_code == 200
        assert record.name.encode() not in response.content

    for allowed in (str(record.pk), str(owner.pk), record.name, str(record.tailtag_id)):
        response = client.get(changelist, {"q": allowed})
        assert response.status_code == 200
        assert record.name.encode() in response.content

    partial_tailtag_id = str(record.tailtag_id).split("-", maxsplit=1)[0]
    response = client.get(changelist, {"q": partial_tailtag_id})
    assert response.status_code == 200
    assert record.name.encode() not in response.content


@pytest.mark.django_db
def test_view_only_staff_cannot_toggle_and_change_staff_cannot_forge_hidden_fields() -> (
    None
):
    record = create_fursuit_record(owner=create_eligible_user())
    name_before = record.name
    photo_before = record.photo_key
    owner_before = record.owner_id
    created_before = record.created_at
    for codes, expected in (
        (["view_fursuit"], 403),
        (["view_fursuit", "change_fursuit"], 403),
        (["view_fursuit", "set_fursuit_enabled"], 302),
    ):
        staff = create_eligible_user()
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        cast(_UserWithPermissions, staff).user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="fursuits", codename__in=codes
            )
        )
        client = Client()
        client.force_login(staff)
        url = reverse("admin:fursuits_fursuit_change", args=(record.pk,))
        response = client.post(
            url,
            {
                "is_enabled": "",
                "name": "Forged",
                "photo_key": "forged",
                "owner": staff.pk,
                "created_at": "2000-01-01T00:00:00Z",
                "updated_at": "2000-01-01T00:00:00Z",
            },
        )
        assert response.status_code == expected
        record.refresh_from_db()
        assert record.name == name_before and record.photo_key == photo_before
        assert record.owner_id == owner_before and record.created_at == created_before
        assert record.updated_at.year != 2000


def _operator_staff(*permissions: tuple[str, str]) -> User:
    user = create_eligible_user()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    cast(_UserWithPermissions, user).user_permissions.add(
        *[
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
            for app_label, codename in permissions
        ]
    )
    return User.objects.get(pk=user.pk)


def _assert_fursuit_event(
    user: User,
    fursuit_id: int,
    actor_class: OperatorActorClass,
    outcome: OperatorAuditOutcome,
) -> None:
    events = list(
        OperatorAuditEvent.objects.filter(
            affected_record_id=fursuit_id, actor=user, outcome=outcome
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
        OperatorAction.SET_FURSUIT_ENABLED,
        actor_class,
        OperatorTargetType.FURSUIT,
        outcome,
    )


@pytest.mark.django_db
def test_fursuit_enablement_role_matrix_uses_only_the_explicit_operation_permission() -> (
    None
):
    """AC-1/2/4: all denied direct posts are evidence, and only exact authority mutates."""
    unrelated = _operator_staff(("profiles", "set_profile_enabled"))
    cases = (
        (
            _operator_staff(),
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
            _operator_staff(("fursuits", "change_fursuit")),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _operator_staff(("fursuits", "set_fursuit_enabled")),
            True,
            OperatorActorClass.OPERATOR,
            OperatorAuditOutcome.SUCCEEDED,
        ),
        (
            User.objects.create_superuser("fursuit_emergency", password="pw"),
            True,
            OperatorActorClass.EMERGENCY_SUPERUSER,
            OperatorAuditOutcome.SUCCEEDED,
        ),
    )
    player = create_eligible_user()
    player_target = create_fursuit_record(owner=create_eligible_user())
    player_url = reverse("admin:fursuits_fursuit_change", args=(player_target.pk,))
    player_client = Client()
    player_client.force_login(player)
    player_response = player_client.post(player_url, {"is_enabled": ""})
    assert player_response.status_code == 302
    assert player_response["Location"] == f"/admin/login/?next={player_url}"
    player_target.refresh_from_db()
    assert player_target.is_enabled is True
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=player_target.pk
    ).exists()

    for user, permitted, actor_class, outcome in cases:
        fursuit = create_fursuit_record(owner=create_eligible_user())
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:fursuits_fursuit_change", args=(fursuit.pk,)),
            {"is_enabled": ""},
        )
        assert response.status_code == (302 if permitted else 403)
        fursuit.refresh_from_db()
        assert fursuit.is_enabled is (not permitted)
        _assert_fursuit_event(user, fursuit.pk, actor_class, outcome)


@pytest.mark.django_db
def test_fursuit_view_permission_is_read_only_and_same_state_is_rejected() -> None:
    """AC-3/4: inspection does not accidentally expose the enablement control."""
    fursuit = create_fursuit_record(owner=create_eligible_user())
    viewer = _operator_staff(("fursuits", "view_fursuit"))
    client = Client()
    client.force_login(viewer)
    url = reverse("admin:fursuits_fursuit_change", args=(fursuit.pk,))
    assert client.get(url).status_code == 200
    assert OperatorAuditEvent.objects.count() == 0
    assert client.post(url, {"is_enabled": ""}).status_code == 403
    fursuit.refresh_from_db()
    assert fursuit.is_enabled is True
    _assert_fursuit_event(
        viewer,
        fursuit.pk,
        OperatorActorClass.UNAUTHORIZED_ACTOR,
        OperatorAuditOutcome.DENIED,
    )

    operator = _operator_staff(("fursuits", "set_fursuit_enabled"))
    client.force_login(operator)
    assert client.post(url, {"is_enabled": "on"}).status_code == 403
    _assert_fursuit_event(
        operator,
        fursuit.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
def test_emergency_superuser_terminal_disablement_is_rejected_and_audited() -> None:
    """AC-4/8: emergency authority still records an already-disabled fursuit retry."""
    fursuit = create_fursuit_record(owner=create_eligible_user())
    fursuit.is_enabled = False
    fursuit.save(update_fields=["is_enabled"])
    terminal = (fursuit.is_enabled, fursuit.updated_at)
    superuser = User.objects.create_superuser(
        "fursuit_terminal_emergency", password="pw"
    )
    client = Client()
    client.force_login(superuser)
    response = client.post(
        reverse("admin:fursuits_fursuit_change", args=(fursuit.pk,)),
        {"is_enabled": ""},
    )
    assert response.status_code == 403
    fursuit.refresh_from_db()
    assert (fursuit.is_enabled, fursuit.updated_at) == terminal
    assert OperatorAuditEvent.objects.filter(affected_record_id=fursuit.pk).count() == 1
    _assert_fursuit_event(
        superuser,
        fursuit.pk,
        OperatorActorClass.EMERGENCY_SUPERUSER,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
def test_fursuit_disablement_cascades_credential_and_session_once() -> None:
    """AC-7/8: lifecycle consequences occur without turning into audit intentions."""
    from conventions.models import Convention, ConventionEnrollment, ConventionStatus

    owner = create_eligible_user()
    fursuit = create_fursuit_record(owner=owner)
    convention = Convention.objects.create(
        name="Fursuit disable audit cascade",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 2),
    )
    ConventionEnrollment.objects.create(user=owner, convention=convention)
    activation = create_activation_row(
        fursuit=fursuit, convention=convention, active=True
    )
    credential = create_credential(activation=activation)
    session = create_catch_session(activation=activation)
    operator = _operator_staff(("fursuits", "set_fursuit_enabled"))
    client = Client()
    client.force_login(operator)
    url = reverse("admin:fursuits_fursuit_change", args=(fursuit.pk,))
    assert client.post(url, {"is_enabled": ""}).status_code == 302
    fursuit.refresh_from_db()
    credential.refresh_from_db()
    session.refresh_from_db()
    assert fursuit.is_enabled is False
    assert (
        credential.revoked_at is not None
        and credential.revocation_reason == "eligibility_lost"
    )
    assert session.ended_at is not None and session.end_reason == "eligibility_lost"
    _assert_fursuit_event(
        operator,
        fursuit.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.SUCCEEDED,
    )
    assert OperatorAuditEvent.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("after_service", [False, True])
def test_fursuit_enablement_failure_rolls_back_and_records_only_failed(
    after_service: bool,
) -> None:
    """AC-4/5: an error cannot retain enabled-state mutation or success evidence."""
    fursuit = create_fursuit_record(owner=create_eligible_user())
    operator = _operator_staff(("fursuits", "set_fursuit_enabled"))
    client = Client()
    client.force_login(operator)
    url = reverse("admin:fursuits_fursuit_change", args=(fursuit.pk,))
    target = (
        "fursuits.admin.FursuitAdmin.log_change"
        if after_service
        else "fursuits.admin.set_fursuit_enabled"
    )
    with (
        patch(target, side_effect=RuntimeError("forced fursuit failure")),
        pytest.raises(RuntimeError, match="forced fursuit failure"),
    ):
        client.post(url, {"is_enabled": ""})
    fursuit.refresh_from_db()
    assert fursuit.is_enabled is True
    _assert_fursuit_event(
        operator, fursuit.pk, OperatorActorClass.OPERATOR, OperatorAuditOutcome.FAILED
    )
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=fursuit.pk, outcome=OperatorAuditOutcome.SUCCEEDED
    ).exists()
