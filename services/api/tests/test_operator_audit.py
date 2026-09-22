"""Acceptance contract for durable, privacy-safe operator audit evidence."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, models, transaction
from django.http import HttpResponse
from django.test import RequestFactory
from operator_audit.admin_actions import (
    execute_bound_operator_transition,
    run_sensitive_admin_attempt,
)
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from operator_audit.services import OperatorTransition

from accounts.models import User
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user

PROFILE_PERMISSION = "profiles.set_profile_enabled"


def _request(user: User, method: str = "post") -> Any:
    """Build one authenticated request at the public coordinator boundary."""
    factory = RequestFactory()
    request = getattr(factory, method)("/admin/profiles/playerprofile/1/change/")
    request.user = user
    return request


def _operator() -> User:
    """Create the normal non-superuser operator path with its one authority."""
    user = create_test_user()
    user.is_staff = True
    user.save(update_fields={"is_staff"})
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="profiles", codename="set_profile_enabled"
        )
    )
    return user


def _profile() -> PlayerProfile:
    return PlayerProfile.objects.create(user=create_test_user())


def _run(
    request: Any,
    profile: PlayerProfile,
    handler: Callable[[], HttpResponse],
    *,
    rejected_exceptions: tuple[type[Exception], ...] = (),
) -> HttpResponse:
    return run_sensitive_admin_attempt(
        request,
        permission=PROFILE_PERMISSION,
        action=OperatorAction.SET_PROFILE_ENABLED,
        target_type=OperatorTargetType.PLAYER_PROFILE,
        target_id=profile.pk,
        handler=handler,
        rejected_exceptions=rejected_exceptions,
    )


def _event_values() -> list[dict[str, object]]:
    return list(
        OperatorAuditEvent.objects.order_by("occurred_at").values(
            "action",
            "actor_id",
            "actor_class",
            "affected_record_type",
            "affected_record_id",
            "outcome",
        )
    )


@pytest.mark.django_db
def test_audit_schema_is_closed_and_uses_server_generated_identity_and_time() -> None:
    """AC-6/10: audit evidence is a minimal durable record, not a request dump."""
    operator = _operator()
    profile = _profile()

    event = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=operator,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=profile.pk,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )

    assert isinstance(event.pk, uuid.UUID) and event.pk.version == 4
    assert event.occurred_at is not None
    assert {field.name for field in OperatorAuditEvent._meta.fields} == {
        "id",
        "action",
        "actor",
        "actor_class",
        "affected_record_type",
        "affected_record_id",
        "outcome",
        "occurred_at",
    }
    id_field = OperatorAuditEvent._meta.get_field("id")
    assert id_field.default is uuid.uuid4 and id_field.editable is False
    assert OperatorAuditEvent._meta.get_field("occurred_at").auto_now_add is True
    assert (
        OperatorAuditEvent._meta.get_field("actor").remote_field.on_delete
        is models.PROTECT
    )


@pytest.mark.django_db
def test_audit_enums_are_the_closed_sensitive_action_and_target_vocabulary() -> None:
    """AC-6: future request text cannot expand audit action or target vocabulary."""
    assert tuple(OperatorAction.values) == (
        "remove_catch",
        "revoke_catch_credential",
        "terminate_catch_session",
        "deactivate_fursuit_activation",
        "remove_convention_enrollment",
        "set_profile_enabled",
        "set_fursuit_enabled",
        "set_convention_playability",
    )
    assert tuple(OperatorTargetType.values) == (
        "catches.catch",
        "conventions.fursuitcatchcredential",
        "conventions.fursuitcatchsession",
        "conventions.fursuitactivation",
        "conventions.conventionenrollment",
        "profiles.playerprofile",
        "fursuits.fursuit",
        "conventions.convention",
    )
    assert tuple(OperatorActorClass.values) == (
        "operator",
        "emergency_superuser",
        "unauthorized_actor",
    )
    assert tuple(OperatorAuditOutcome.values) == (
        "succeeded",
        "denied",
        "rejected",
        "failed",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("actor_class", "outcome"),
    (
        (OperatorActorClass.UNAUTHORIZED_ACTOR, OperatorAuditOutcome.SUCCEEDED),
        (OperatorActorClass.OPERATOR, OperatorAuditOutcome.DENIED),
        (OperatorActorClass.EMERGENCY_SUPERUSER, OperatorAuditOutcome.DENIED),
    ),
)
def test_database_rejects_invalid_actor_and_outcome_pairings(
    actor_class: OperatorActorClass, outcome: OperatorAuditOutcome
) -> None:
    """AC-4/6: a denied attempt can never be persisted as operator activity."""
    with pytest.raises(IntegrityError), transaction.atomic():
        OperatorAuditEvent.objects.create(
            action=OperatorAction.SET_PROFILE_ENABLED,
            actor=create_test_user(),
            actor_class=actor_class,
            affected_record_type=OperatorTargetType.PLAYER_PROFILE,
            affected_record_id=1,
            outcome=outcome,
        )
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_only_the_seven_sensitive_permissions_and_catch_delete_permission_exist() -> (
    None
):
    """AC-4: the audit foundation creates the exact operation authorities it records."""
    expected = {
        (
            "conventions",
            "revoke_catch_credential",
            "Can revoke a current catch credential",
        ),
        (
            "conventions",
            "terminate_catch_session",
            "Can terminate an active catch session",
        ),
        (
            "conventions",
            "deactivate_fursuit_activation",
            "Can deactivate a fursuit activation",
        ),
        (
            "conventions",
            "remove_convention_enrollment",
            "Can remove a convention enrollment",
        ),
        (
            "conventions",
            "set_convention_playability",
            "Can change Convention playability",
        ),
        ("profiles", "set_profile_enabled", "Can set player profile enabled state"),
        ("fursuits", "set_fursuit_enabled", "Can set fursuit enabled state"),
        ("catches", "delete_catch", "Can delete catch"),
    }
    codenames = {codename for _, codename, _ in expected}
    permissions = Permission.objects.filter(codename__in=codenames).select_related(
        "content_type"
    )

    assert {
        (permission.content_type.app_label, permission.codename, permission.name)
        for permission in permissions
    } == expected


@pytest.mark.django_db
def test_audit_evidence_survives_deletion_of_its_domain_target() -> None:
    """AC-7/10: audit keeps one top-level intent without target-FK reset coupling."""
    operator = _operator()
    profile = _profile()
    event = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=operator,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=profile.pk,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    profile_id = profile.pk

    profile.delete()

    persisted = OperatorAuditEvent.objects.get(pk=event.pk)
    assert persisted.affected_record_type == OperatorTargetType.PLAYER_PROFILE
    assert persisted.affected_record_id == profile_id
    assert persisted.actor_id == operator.pk


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("user_factory", "expected_actor_class"),
    (
        (_operator, OperatorActorClass.OPERATOR),
        (
            lambda: User.objects.create_superuser(
                "emergency-superuser", password="safe-local-admin-password"
            ),
            OperatorActorClass.EMERGENCY_SUPERUSER,
        ),
    ),
)
def test_authorized_paths_commit_one_success_event_with_the_correct_actor_class(
    user_factory: Callable[[], User], expected_actor_class: OperatorActorClass
) -> None:
    """AC-4/5/7: normal operators and bypassing superusers retain distinct evidence."""
    user = user_factory()
    profile = _profile()
    committed: list[str] = []

    def operation() -> OperatorTransition[None]:
        profile.is_enabled = False
        profile.save(update_fields={"is_enabled"})
        transaction.on_commit(lambda: committed.append("domain-and-audit"))
        return OperatorTransition(value=None, changed=True)

    # The transition must be bound to this exact request, not a lookalike request.
    request = _request(user)

    def bound_handler() -> HttpResponse:
        execute_bound_operator_transition(request, operation)
        return HttpResponse(status=204)

    response = _run(request, profile, bound_handler)
    profile.refresh_from_db()

    assert response.status_code == 204
    assert profile.is_enabled is False
    assert committed == ["domain-and-audit"]
    assert _event_values() == [
        {
            "action": OperatorAction.SET_PROFILE_ENABLED,
            "actor_id": user.pk,
            "actor_class": expected_actor_class,
            "affected_record_type": OperatorTargetType.PLAYER_PROFILE,
            "affected_record_id": profile.pk,
            "outcome": OperatorAuditOutcome.SUCCEEDED,
        }
    ]


@pytest.mark.django_db(transaction=True)
def test_missing_permission_records_denied_before_calling_the_domain_handler() -> None:
    """AC-4: staff without this operation authority is an unauthorized actor."""
    unauthorized_staff = create_test_user()
    unauthorized_staff.is_staff = True
    unauthorized_staff.save(update_fields={"is_staff"})
    profile = _profile()

    def handler() -> HttpResponse:
        pytest.fail("denied mutations must not invoke their domain handler")

    with pytest.raises(PermissionDenied):
        _run(_request(unauthorized_staff), profile, handler)

    assert _event_values() == [
        {
            "action": OperatorAction.SET_PROFILE_ENABLED,
            "actor_id": unauthorized_staff.pk,
            "actor_class": OperatorActorClass.UNAUTHORIZED_ACTOR,
            "affected_record_type": OperatorTargetType.PLAYER_PROFILE,
            "affected_record_id": profile.pk,
            "outcome": OperatorAuditOutcome.DENIED,
        }
    ]


@pytest.mark.django_db(transaction=True)
def test_changed_false_rolls_back_and_records_rejected() -> None:
    """AC-4/5: a no-op must not become a success audit event."""
    operator = _operator()
    profile = _profile()

    def handler() -> HttpResponse:
        execute_bound_operator_transition(
            request,
            lambda: OperatorTransition(value=None, changed=False),
        )
        pytest.fail("a changed=False transition must not return normally")

    request = _request(operator)
    with pytest.raises(PermissionDenied):
        _run(request, profile, handler)

    assert profile.is_enabled is True
    assert _event_values()[0]["outcome"] == OperatorAuditOutcome.REJECTED
    assert OperatorAuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_form_response_without_a_bound_transition_records_rejected() -> None:
    """AC-4: invalid form handling cannot silently omit a submitted attempt."""
    operator = _operator()
    profile = _profile()

    with pytest.raises(PermissionDenied):
        _run(
            _request(operator),
            profile,
            lambda: HttpResponse("invalid form", status=200),
        )

    assert _event_values()[0]["outcome"] == OperatorAuditOutcome.REJECTED
    assert OperatorAuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_unexpected_exception_after_state_write_rolls_back_and_records_only_failed() -> (
    None
):
    """AC-4/5: failure after a write cannot commit state, callbacks, or success evidence."""
    operator = _operator()
    profile = _profile()
    committed: list[str] = []
    request = _request(operator)

    def operation() -> OperatorTransition[None]:
        profile.is_enabled = False
        profile.save(update_fields={"is_enabled"})
        transaction.on_commit(lambda: committed.append("must-not-commit"))
        raise RuntimeError("simulated unexpected failure")

    def handler() -> HttpResponse:
        execute_bound_operator_transition(request, operation)
        return HttpResponse(status=204)

    with pytest.raises(RuntimeError, match="simulated unexpected failure"):
        _run(request, profile, handler)

    profile.refresh_from_db()
    assert profile.is_enabled is True
    assert committed == []
    assert _event_values()[0]["outcome"] == OperatorAuditOutcome.FAILED
    assert OperatorAuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_get_never_creates_an_operator_audit_event() -> None:
    """AC-4: a coordinator accidentally reached by a browse request emits no evidence."""
    operator = _operator()
    profile = _profile()

    try:
        _run(_request(operator, "get"), profile, lambda: HttpResponse(status=200))
    except PermissionDenied:
        pass

    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_audit_insert_failure_cannot_commit_the_domain_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5: writing audit after separately committed domain work is forbidden."""
    operator = _operator()
    profile = _profile()
    request = _request(operator)

    def audit_insert_fails(*_: object, **__: object) -> None:
        raise IntegrityError("simulated audit persistence failure")

    monkeypatch.setattr(OperatorAuditEvent, "save", audit_insert_fails)

    def operation() -> OperatorTransition[None]:
        profile.is_enabled = False
        profile.save(update_fields={"is_enabled"})
        return OperatorTransition(value=None, changed=True)

    def handler() -> HttpResponse:
        execute_bound_operator_transition(request, operation)
        return HttpResponse(status=204)

    with pytest.raises(IntegrityError, match="simulated audit persistence failure"):
        _run(request, profile, handler)

    profile.refresh_from_db()
    assert profile.is_enabled is True
    assert not OperatorAuditEvent.objects.filter(
        outcome=OperatorAuditOutcome.SUCCEEDED
    ).exists()
