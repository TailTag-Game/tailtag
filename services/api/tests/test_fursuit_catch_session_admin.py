"""Restricted support-admin acceptance contract for catch sessions."""

from __future__ import annotations

import datetime
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.authentication_support import create_test_user
from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    create_catch_session,
)


def _listed_session_ids(response: object) -> set[int]:
    context = cast(dict[str, object], response.context)  # type: ignore[attr-defined]
    changelist = cast(ChangeList, context["cl"])
    return {row.pk for row in changelist.result_list}


@pytest.mark.django_db
def test_catch_session_admin_inspects_history_but_prohibits_add_delete_bulk_and_raw_lifecycle_edits() -> (
    None
):
    """AC-01/11: rejects an editable, deletable, or bulk-mutable session admin."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session = create_catch_session(activation=activation)
    nonmatching = create_activation_scenario(clerk_user_id="catch_session_search_other")
    nonmatching_activation = create_activation_row(
        fursuit=nonmatching.fursuit,
        convention=nonmatching.convention,
        active=True,
    )
    historical_now = timezone.now()
    historical = create_catch_session(
        activation=nonmatching_activation,
        started_at=historical_now - CATCH_SESSION_LIFETIME,
        ended_at=historical_now,
        end_reason="owner",
    )
    session_model = catch_session_model()
    model_admin: Any = admin.site._registry[session_model]  # type: ignore[reportPrivateUsage]
    assert model_admin.actions is None
    assert model_admin.search_fields and model_admin.list_filter
    operator = User.objects.create_superuser(
        "catch_session_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    change = reverse("admin:conventions_fursuitcatchsession_change", args=(session.pk,))
    changelist = reverse("admin:conventions_fursuitcatchsession_changelist")
    searched = client.get(changelist, {"q": scenario.fursuit.name})
    assert searched.status_code == 200
    assert _listed_session_ids(searched) == {session.pk}
    searched_changelist = cast(ChangeList, searched.context["cl"])
    listed_session = next(iter(searched_changelist.result_list))
    assert model_admin.is_effectively_active(listed_session) is True
    assert model_admin.is_effectively_active(session) is False
    filtered = client.get(changelist, {"is_effectively_active": "1"})
    assert filtered.status_code == 200
    assert _listed_session_ids(filtered) == {session.pk}
    assert historical.pk not in _listed_session_ids(searched)
    assert historical.pk not in _listed_session_ids(filtered)
    detail = client.get(change)
    assert detail.status_code == 200
    for field in (
        "activation",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "created_at",
        "updated_at",
    ):
        assert f'name="{field}"'.encode() not in detail.content
    assert (
        client.get(reverse("admin:conventions_fursuitcatchsession_add")).status_code
        == 403
    )
    assert (
        client.get(
            reverse("admin:conventions_fursuitcatchsession_delete", args=(session.pk,))
        ).status_code
        == 403
    )
    assert (
        b'name="action"'
        not in client.get(
            reverse("admin:conventions_fursuitcatchsession_changelist")
        ).content
    )


@pytest.mark.django_db
def test_admin_per_object_operator_termination_ends_only_live_row_and_never_relables_expired_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11/12: rejects raw field editing or rewriting an expired terminal reason."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    live = create_catch_session(activation=activation)
    operator = User.objects.create_superuser(
        "catch_session_terminator", password="password"
    )
    client = Client()
    client.force_login(operator)
    change = reverse("admin:conventions_fursuitcatchsession_change", args=(live.pk,))
    assert client.post(change, {"terminate": "1"}).status_code == 302
    live.refresh_from_db()
    assert live.ended_at is not None and live.end_reason == "operator"
    before = (live.ended_at, live.end_reason, live.updated_at)
    assert client.post(change, {"terminate": "1"}).status_code in {200, 302, 403}
    live.refresh_from_db()
    assert (live.ended_at, live.end_reason, live.updated_at) == before
    # A separate stale unended row is allowed only after the live row is terminal.
    from conventions import services

    now = timezone.now()
    monkeypatch.setattr(services.timezone, "now", lambda: now)
    expired = create_catch_session(
        activation=activation,
        started_at=now - datetime.timedelta(hours=12),
        expires_at=now,
    )
    expired_change = reverse(
        "admin:conventions_fursuitcatchsession_change", args=(expired.pk,)
    )
    assert client.post(expired_change, {"terminate": "1"}).status_code == 302
    expired.refresh_from_db()
    assert expired.ended_at == now and expired.end_reason == "expired"


def _session_staff(*permissions: tuple[str, str]) -> User:
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


def _assert_session_event(
    user: User,
    session_id: int,
    actor_class: OperatorActorClass,
    outcome: OperatorAuditOutcome,
) -> None:
    events = list(
        OperatorAuditEvent.objects.filter(
            affected_record_id=session_id, actor=user, outcome=outcome
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
        OperatorAction.TERMINATE_CATCH_SESSION,
        actor_class,
        OperatorTargetType.FURSUIT_CATCH_SESSION,
        outcome,
    )


@pytest.mark.django_db
def test_session_termination_role_matrix_requires_exact_permission() -> None:
    """AC-1/2/4: terminal-session authority has no generic or cross-action bypass."""
    unrelated = _session_staff(("conventions", "revoke_catch_credential"))
    cases = (
        (
            _session_staff(),
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
            _session_staff(("conventions", "change_fursuitcatchsession")),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _session_staff(("conventions", "terminate_catch_session")),
            True,
            OperatorActorClass.OPERATOR,
            OperatorAuditOutcome.SUCCEEDED,
        ),
        (
            User.objects.create_superuser("session_emergency", password="pw"),
            True,
            OperatorActorClass.EMERGENCY_SUPERUSER,
            OperatorAuditOutcome.SUCCEEDED,
        ),
    )
    player = create_test_user(clerk_user_id="session_matrix_player")
    player_scenario = create_activation_scenario(
        clerk_user_id="session_matrix_player_target"
    )
    player_activation = create_activation_row(
        fursuit=player_scenario.fursuit,
        convention=player_scenario.convention,
        active=True,
    )
    player_session = create_catch_session(activation=player_activation)
    player_url = reverse(
        "admin:conventions_fursuitcatchsession_change", args=(player_session.pk,)
    )
    player_client = Client()
    player_client.force_login(player)
    player_response = player_client.post(player_url, {"terminate": "1"})
    assert player_response.status_code == 302
    assert player_response["Location"] == f"/admin/login/?next={player_url}"
    player_session.refresh_from_db()
    assert player_session.ended_at is None
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=player_session.pk
    ).exists()

    for index, (user, permitted, actor_class, outcome) in enumerate(cases):
        scenario = create_activation_scenario(
            clerk_user_id=f"session_matrix_case_{index}"
        )
        activation = create_activation_row(
            fursuit=scenario.fursuit, convention=scenario.convention, active=True
        )
        session = create_catch_session(activation=activation)
        client = Client()
        client.force_login(user)
        url = reverse(
            "admin:conventions_fursuitcatchsession_change", args=(session.pk,)
        )
        response = client.post(url, {"terminate": "1"})
        assert response.status_code == (302 if permitted else 403)
        session.refresh_from_db()
        assert (session.ended_at is not None) is permitted
        _assert_session_event(user, session.pk, actor_class, outcome)


@pytest.mark.django_db
def test_session_view_permission_is_read_only_and_terminal_session_rejects_repeat() -> (
    None
):
    """AC-3/4/8: GET is not an audit attempt and cannot grant a terminate control."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session = create_catch_session(activation=activation)
    viewer = _session_staff(("conventions", "view_fursuitcatchsession"))
    client = Client()
    client.force_login(viewer)
    url = reverse("admin:conventions_fursuitcatchsession_change", args=(session.pk,))
    detail = client.get(url)
    assert detail.status_code == 200 and b'name="terminate"' not in detail.content
    assert OperatorAuditEvent.objects.count() == 0
    assert client.post(url, {"terminate": "1"}).status_code == 403
    _assert_session_event(
        viewer,
        session.pk,
        OperatorActorClass.UNAUTHORIZED_ACTOR,
        OperatorAuditOutcome.DENIED,
    )
    operator = _session_staff(("conventions", "terminate_catch_session"))
    client.force_login(operator)
    assert client.get(url).status_code == 200
    assert OperatorAuditEvent.objects.filter(affected_record_id=session.pk).count() == 1
    assert client.post(url, {"terminate": "1"}).status_code == 302
    assert client.post(url, {"terminate": "1"}).status_code == 403
    _assert_session_event(
        operator,
        session.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
def test_emergency_superuser_terminal_termination_is_rejected_and_audited() -> None:
    """AC-4/8: emergency authority still records a terminal-session retry."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    ended_at = timezone.now()
    session = create_catch_session(
        activation=activation,
        started_at=ended_at - datetime.timedelta(seconds=1),
        ended_at=ended_at,
        end_reason="operator",
    )
    terminal = (session.ended_at, session.end_reason, session.updated_at)
    superuser = User.objects.create_superuser(
        "session_terminal_emergency", password="pw"
    )
    client = Client()
    client.force_login(superuser)
    response = client.post(
        reverse("admin:conventions_fursuitcatchsession_change", args=(session.pk,)),
        {"terminate": "1"},
    )
    assert response.status_code == 403
    session.refresh_from_db()
    assert (session.ended_at, session.end_reason, session.updated_at) == terminal
    assert OperatorAuditEvent.objects.filter(affected_record_id=session.pk).count() == 1
    _assert_session_event(
        superuser,
        session.pk,
        OperatorActorClass.EMERGENCY_SUPERUSER,
        OperatorAuditOutcome.REJECTED,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("after_service", [False, True])
def test_session_termination_failure_rolls_back_and_records_only_failed(
    after_service: bool,
) -> None:
    """AC-4/5: session terminal state and success evidence roll back together."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session = create_catch_session(activation=activation)
    operator = _session_staff(("conventions", "terminate_catch_session"))
    client = Client()
    client.force_login(operator)
    url = reverse("admin:conventions_fursuitcatchsession_change", args=(session.pk,))
    failure_target = (
        "conventions.admin.FursuitCatchSessionAdmin.log_change"
        if after_service
        else "conventions.admin.terminate_session_as_operator"
    )
    with (
        patch(failure_target, side_effect=RuntimeError("forced session failure")),
        pytest.raises(RuntimeError, match="forced session failure"),
    ):
        client.post(url, {"terminate": "1"})
    session.refresh_from_db()
    assert session.ended_at is None
    _assert_session_event(
        operator,
        session.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.FAILED,
    )
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=session.pk, outcome=OperatorAuditOutcome.SUCCEEDED
    ).exists()
