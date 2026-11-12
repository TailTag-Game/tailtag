"""Operator request administration and invalidation hooks (#507).

The criteria live in .refinement/507.md. The contract is
docs/specs/2026-11-09-reusable-tailtag-catch-request-contract.md.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.db.models import F
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catches.models import Catch, CatchBlock, CatchRequest, CatchRequestState
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from conventions.review_deadline import compute_review_deadline
from conventions.services import (
    deactivate_fursuit_activation_as_operator,
    remove_convention_enrollment,
    set_convention_admin_state,
    set_fursuit_activation_state,
)
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.authentication_support import create_test_user
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_tag_test_support import (
    PreviewScenario,
    create_convention,
    create_player,
    create_preview_scenario,
    create_suit,
    owner_client,
)

pytestmark = pytest.mark.django_db

REQUESTS_PATH = "/api/catches/requests/"
INCOMING_PATH = "/api/catches/incoming-requests/"
_STATE_TIMES = {
    CatchRequestState.APPROVED: ("approved_at",),
    CatchRequestState.DECLINED: ("declined_at",),
    CatchRequestState.WITHDRAWN: ("withdrawn_at",),
    CatchRequestState.INVALIDATED: ("invalidated_at",),
}


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


# --- Helpers ------------------------------------------------------------------


def _staff(*codenames: str, superuser: bool = False) -> Client:
    user = create_test_user()
    user.is_staff = True
    user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        *[
            Permission.objects.get(
                content_type__app_label=name.split(".")[0],
                codename=name.split(".")[1],
            )
            for name in codenames
        ]
    )
    client = Client()
    client.force_login(User.objects.get(pk=user.pk))
    return client


def _row(
    scenario: PreviewScenario,
    state: str = CatchRequestState.PENDING,
    *,
    player: User | None = None,
    convention: Convention | None = None,
    blocked: bool = False,
) -> CatchRequest:
    now = timezone.now()
    times = {name: now for name in _STATE_TIMES.get(CatchRequestState(state), ())}
    if blocked:
        times["declined_at"] = now
    return CatchRequest.objects.create(
        player=player or scenario.catcher,
        fursuit=scenario.fursuit,
        convention=convention or scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        state=state,
        requested_at=now,
        decline_blocked=blocked,
        **times,
    )


def _invalidate(client: Client, request_id: int) -> Any:
    url = reverse("admin:catches_catchrequest_change", args=(request_id,))
    return client.post(url, {"invalidate": "on"})


def _event(request_id: int) -> tuple[str, str, str, str]:
    event = OperatorAuditEvent.objects.get(affected_record_id=request_id)
    return (
        event.action,
        event.actor_class,
        event.affected_record_type,
        event.outcome,
    )


def _states(*rows: CatchRequest) -> list[str]:
    return [CatchRequest.objects.get(pk=row.pk).state for row in rows]


def _close_window(convention: Convention) -> None:
    Convention.objects.filter(pk=convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )


def _consistent_open_window(convention: Convention) -> Convention:
    """Make the stored deadline match the end date, so an admin save keeps it."""
    end_date = timezone.localdate()
    Convention.objects.filter(pk=convention.pk).update(
        end_date=end_date,
        review_deadline_at=compute_review_deadline(end_date, "America/New_York"),
    )
    return Convention.objects.get(pk=convention.pk)


# --- Operator view (AC1 to AC4) -----------------------------------------------


def test_operators_inspect_requests_and_blocks_without_any_mutation_path() -> None:
    """AC1 to AC4: view permissions show both lists, and nothing can change them."""
    scenario = create_preview_scenario("admin_view")
    request = _row(scenario, CatchRequestState.INVALIDATED)
    block = CatchBlock.objects.create(
        player=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        created_at=timezone.now(),
    )
    _close_window(scenario.convention)
    viewer = _staff("catches.view_catchrequest", "catches.view_catchblock")
    stranger = _staff()
    request_list = reverse("admin:catches_catchrequest_changelist")
    block_list = reverse("admin:catches_catchblock_changelist")

    listed = viewer.get(request_list, {"q": str(scenario.fursuit.tailtag_id)})
    detail = viewer.get(
        reverse("admin:catches_catchrequest_change", args=(request.pk,))
    )
    blocks = viewer.get(block_list)
    blocked_paths = [
        viewer.get(reverse("admin:catches_catchrequest_add")).status_code,
        viewer.get(reverse("admin:catches_catchblock_add")).status_code,
        viewer.post(
            reverse("admin:catches_catchrequest_delete", args=(request.pk,)),
            {"post": "yes"},
        ).status_code,
        viewer.post(
            reverse("admin:catches_catchblock_delete", args=(block.pk,)),
            {"post": "yes"},
        ).status_code,
        _invalidate(viewer, request.pk).status_code,
        stranger.get(request_list).status_code,
        stranger.get(block_list).status_code,
    ]

    assert (listed.status_code, detail.status_code, blocks.status_code) == (
        200,
        200,
        200,
    )
    assert request.pk in [row.pk for row in listed.context["cl"].result_list]
    assert "Invalidated" in detail.content.decode()
    assert block.pk in [row.pk for row in blocks.context["cl"].result_list]
    assert set(blocked_paths) == {403}
    assert _states(request) == [CatchRequestState.INVALIDATED]
    assert CatchBlock.objects.filter(pk=block.pk).exists()


# --- Invalidate action (AC5 to AC8) ---------------------------------------------


@pytest.mark.parametrize(
    "state", [CatchRequestState.PENDING, CatchRequestState.DECLINED]
)
def test_invalidate_ends_an_open_pending_or_declined_request(state: str) -> None:
    """AC5, AC33: the state changes, declined_at stays, and one audit row records it."""
    scenario = create_preview_scenario(f"invalidate_{state}")
    request = _row(scenario, state)
    operator = _staff("catches.invalidate_catch_request")

    response = _invalidate(operator, request.pk)

    request.refresh_from_db()
    assert response.status_code == 302
    assert request.state == CatchRequestState.INVALIDATED
    assert request.invalidated_at is not None
    assert (request.declined_at is not None) is (state == CatchRequestState.DECLINED)
    assert _event(request.pk) == (
        OperatorAction.INVALIDATE_CATCH_REQUEST,
        OperatorActorClass.OPERATOR,
        OperatorTargetType.CATCH_REQUEST,
        OperatorAuditOutcome.SUCCEEDED,
    )


@pytest.mark.parametrize(
    ("state", "window_open"),
    [
        (CatchRequestState.APPROVED, True),
        (CatchRequestState.WITHDRAWN, True),
        (CatchRequestState.INVALIDATED, True),
        (CatchRequestState.PENDING, False),
    ],
)
def test_invalidate_rejects_final_states_and_closed_windows(
    state: str, window_open: bool
) -> None:
    """AC6, AC7: nothing changes, and the audit row says rejected."""
    scenario = create_preview_scenario(f"reject_{state}_{window_open}")
    request = _row(scenario, state)
    if not window_open:
        _close_window(scenario.convention)

    response = _invalidate(_staff("catches.invalidate_catch_request"), request.pk)

    assert response.status_code == 403
    assert _states(request) == [state]
    assert _event(request.pk)[3] == OperatorAuditOutcome.REJECTED


def test_invalidate_needs_its_permission_and_labels_a_superuser() -> None:
    """AC8: a viewer is denied. A superuser succeeds as an emergency actor."""
    scenario = create_preview_scenario("invalidate_roles")
    denied = _row(scenario)
    denied_response = _invalidate(_staff("catches.view_catchrequest"), denied.pk)
    denied_event = _event(denied.pk)
    denied.delete()
    emergency = _row(scenario)

    emergency_response = _invalidate(_staff(superuser=True), emergency.pk)

    assert denied_response.status_code == 403
    assert denied_event[1:] == (
        OperatorActorClass.UNAUTHORIZED_ACTOR,
        OperatorTargetType.CATCH_REQUEST,
        OperatorAuditOutcome.DENIED,
    )
    assert emergency_response.status_code == 302
    assert _states(emergency) == [CatchRequestState.INVALIDATED]
    assert _event(emergency.pk)[1] == OperatorActorClass.EMERGENCY_SUPERUSER


# --- Invalidation hooks (AC9 to AC16) -------------------------------------------


def test_enrollment_removal_invalidates_the_user_as_player_and_as_owner() -> None:
    """AC9, AC13, AC14: both roles end in one action, with one audit row.

    The removed user catches one suit and owns another at the same convention.
    An approved request keeps its catch. A closed-window request elsewhere and
    another player's request on another suit stay unchanged.
    """
    scenario = create_preview_scenario("removal")
    dual = scenario.catcher
    as_player = _row(scenario, CatchRequestState.DECLINED)
    approved = _row(scenario, CatchRequestState.APPROVED)
    Catch.objects.create(
        catcher_user=dual,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        caught_at=approved.requested_at,
        approved_at=approved.requested_at,
    )
    owned_suit = create_suit(dual)
    owned_activation = create_activation_row(
        fursuit=owned_suit, convention=scenario.convention, active=True
    )
    other, _ = create_player("removal_other")
    ConventionEnrollment.objects.create(
        user=other, convention=scenario.convention, is_active=True
    )
    as_owner = CatchRequest.objects.create(
        player=other,
        fursuit=owned_suit,
        convention=scenario.convention,
        activation=owned_activation,
        catch_session=create_catch_session(activation=owned_activation),
        state=CatchRequestState.PENDING,
        requested_at=timezone.now(),
    )
    unrelated = _row(scenario, player=other)
    closed = create_convention("removal_closed", window_open=False)
    elsewhere = _row(scenario, convention=closed)
    operator = _staff(
        "conventions.remove_convention_enrollment",
        "conventions.view_conventionenrollment",
    )
    url = reverse(
        "admin:conventions_conventionenrollment_delete",
        args=(scenario.catcher_enrollment.pk,),
    )

    response = operator.post(url, {"post": "yes"})

    assert response.status_code == 302
    assert _states(as_player, as_owner, approved, unrelated, elsewhere) == [
        CatchRequestState.INVALIDATED,
        CatchRequestState.INVALIDATED,
        CatchRequestState.APPROVED,
        CatchRequestState.PENDING,
        CatchRequestState.PENDING,
    ]
    assert CatchRequest.objects.get(pk=as_player.pk).declined_at is not None
    assert Catch.objects.filter(catcher_user=dual).count() == 1
    assert list(OperatorAuditEvent.objects.values_list("action", "outcome")) == [
        (OperatorAction.REMOVE_CONVENTION_ENROLLMENT, OperatorAuditOutcome.SUCCEEDED)
    ]


def test_only_operator_activation_deactivation_invalidates() -> None:
    """AC10, AC15: an owner's own deactivation keeps the request approvable.

    Operator deactivation ends only that suit's requests at that convention.
    """
    scenario = create_preview_scenario("deactivation")
    request = _row(scenario)
    other_suit = create_suit(scenario.owner)
    other_activation = create_activation_row(
        fursuit=other_suit, convention=scenario.convention, active=True
    )
    other = CatchRequest.objects.create(
        player=scenario.catcher,
        fursuit=other_suit,
        convention=scenario.convention,
        activation=other_activation,
        catch_session=create_catch_session(activation=other_activation),
        state=CatchRequestState.PENDING,
        requested_at=timezone.now(),
    )

    set_fursuit_activation_state(
        scenario.owner,
        convention_id=scenario.convention.pk,
        fursuit_id=scenario.fursuit.pk,
        is_active=False,
    )
    after_owner = _states(request)
    type(scenario.activation).objects.filter(pk=scenario.activation.pk).update(
        is_active=True, deactivated_at=None
    )
    deactivate_fursuit_activation_as_operator(activation_id=scenario.activation.pk)

    assert after_owner == [CatchRequestState.PENDING]
    assert _states(request, other) == [
        CatchRequestState.INVALIDATED,
        CatchRequestState.PENDING,
    ]


def test_hooks_leave_closed_window_requests_unchanged() -> None:
    """AC13: removal, deactivation, and cancellation skip a closed window."""
    scenario = create_preview_scenario("hooks_closed")
    request = _row(scenario, CatchRequestState.DECLINED)
    _close_window(scenario.convention)
    convention = Convention.objects.get(pk=scenario.convention.pk)

    deactivate_fursuit_activation_as_operator(activation_id=scenario.activation.pk)
    remove_convention_enrollment(enrollment_id=scenario.catcher_enrollment.pk)
    set_convention_admin_state(
        convention_id=convention.pk,
        name=convention.name,
        status=ConventionStatus.CANCELLED,
        start_date=convention.start_date,
        end_date=convention.end_date,
        time_zone=convention.time_zone,
    )

    assert Convention.objects.get(pk=convention.pk).status == ConventionStatus.CANCELLED
    assert _states(request) == [CatchRequestState.DECLINED]


@pytest.mark.parametrize("start", [ConventionStatus.ACTIVE, ConventionStatus.PAUSED])
def test_a_move_into_cancelled_invalidates_and_leaving_restores_nothing(
    start: str,
) -> None:
    """AC11, AC12: every move into cancellation is audited and ends open requests."""
    scenario = create_preview_scenario(f"cancel_{start}")
    convention = _consistent_open_window(scenario.convention)
    Convention.objects.filter(pk=convention.pk).update(status=start)
    pending = _row(scenario)
    declined = _row(scenario, CatchRequestState.DECLINED, blocked=True)
    approved = _row(scenario, CatchRequestState.APPROVED)
    operator = _staff(
        "conventions.set_convention_playability", "conventions.view_convention"
    )
    url = reverse("admin:conventions_convention_change", args=(convention.pk,))
    data = {
        "name": convention.name,
        "start_date": convention.start_date.isoformat(),
        "end_date": convention.end_date.isoformat(),
        "time_zone": "America/New_York",
    }

    cancelled = operator.post(url, {**data, "status": ConventionStatus.CANCELLED})
    states = _states(pending, declined, approved)
    editor = _staff("conventions.change_convention", "conventions.view_convention")
    reopened = editor.post(url, {**data, "status": ConventionStatus.PAUSED})

    assert (cancelled.status_code, reopened.status_code) == (302, 302)
    assert states == [
        CatchRequestState.INVALIDATED,
        CatchRequestState.INVALIDATED,
        CatchRequestState.APPROVED,
    ]
    assert _states(pending, declined) == [CatchRequestState.INVALIDATED] * 2
    assert list(
        OperatorAuditEvent.objects.filter(affected_record_id=convention.pk).values_list(
            "action", "outcome"
        )
    ) == [(OperatorAction.SET_CONVENTION_PLAYABILITY, OperatorAuditOutcome.SUCCEEDED)]


def test_cancelling_without_the_playability_permission_is_denied() -> None:
    """AC12: change_convention alone can no longer cancel a convention."""
    scenario = create_preview_scenario("cancel_denied")
    convention = _consistent_open_window(scenario.convention)
    Convention.objects.filter(pk=convention.pk).update(status=ConventionStatus.PAUSED)
    pending = _row(scenario)
    editor = _staff("conventions.change_convention", "conventions.view_convention")

    response = editor.post(
        reverse("admin:conventions_convention_change", args=(convention.pk,)),
        {
            "name": convention.name,
            "status": ConventionStatus.CANCELLED,
            "start_date": convention.start_date.isoformat(),
            "end_date": convention.end_date.isoformat(),
            "time_zone": "America/New_York",
        },
    )

    assert response.status_code == 403
    assert Convention.objects.get(pk=convention.pk).status == ConventionStatus.PAUSED
    assert _states(pending) == [CatchRequestState.PENDING]
    assert list(OperatorAuditEvent.objects.values_list("actor_class", "outcome")) == [
        (OperatorActorClass.UNAUTHORIZED_ACTOR, OperatorAuditOutcome.DENIED)
    ]


# --- Re-enrollment (AC17, AC18) ---------------------------------------------------


def test_reenrollment_keeps_an_invalidated_request_and_its_decline_count() -> None:
    """AC17, AC18: the player sees unavailable, the owner cannot reopen it, and
    the counted decline still sets the cooldown for a new request."""
    scenario = create_preview_scenario("reenroll")
    submit = scenario.catcher_client().post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )
    request_id = int(submit.json()["request"]["id"])
    owner = owner_client(scenario.owner)
    path = f"{INCOMING_PATH}{request_id}/"
    declined = owner.post(
        f"{path}decline/", {"block": False}, content_type="application/json"
    )
    assert declined.status_code == 200, declined.content
    operator = _staff(
        "conventions.remove_convention_enrollment",
        "conventions.view_conventionenrollment",
    )
    operator.post(
        reverse(
            "admin:conventions_conventionenrollment_delete",
            args=(scenario.catcher_enrollment.pk,),
        ),
        {"post": "yes"},
    )
    ConventionEnrollment.objects.create(
        user=scenario.catcher, convention=scenario.convention, is_active=True
    )

    listed = scenario.catcher_client().get(REQUESTS_PATH).json()["results"]
    reopen = [owner.post(f"{path}{action}/") for action in ("undo-decline", "restore")]
    too_soon = scenario.catcher_client().post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )
    CatchRequest.objects.filter(pk=request_id).update(
        requested_at=F("requested_at") - datetime.timedelta(seconds=11),
        declined_at=F("declined_at") - datetime.timedelta(seconds=11),
    )
    later = scenario.catcher_client().post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert [(row["id"], row["state"]) for row in listed] == [
        (request_id, "unavailable")
    ]
    assert {(r.status_code, r.json()["code"]) for r in reopen} == {
        (409, "request_superseded")
    }
    assert (too_soon.status_code, too_soon.json()["code"]) == (429, "cooldown_active")
    assert (later.status_code, later.json()["outcome"]) == (201, "pending")
    assert _states(CatchRequest(pk=request_id)) == [CatchRequestState.INVALIDATED]
