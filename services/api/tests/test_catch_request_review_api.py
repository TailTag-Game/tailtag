"""Owner decisions, withdrawal, blocks, cooldowns, and limits (#506).

The criteria live in .refinement/506.md. The contract is
docs/specs/2026-11-09-reusable-tailtag-catch-request-contract.md.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

import pytest
import yaml
from django.db import connection
from django.db.models import F
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catches.models import Catch, CatchBlock, CatchRequest, CatchRequestState
from catches.request_invalidation import invalidate_request_as_operator
from conventions.models import (
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchSession,
)
from fursuits.models import Fursuit, FursuitTag
from fursuits.tags import revoke_tag_as_operator
from profiles.models import PlayerProfile
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_tag_test_support import (
    GENERIC_NOT_FOUND,
    TARGET_UNAVAILABLE,
    PreviewScenario,
    create_convention,
    create_player,
    create_preview_scenario,
    create_suit,
    owner_client,
    read_payload,
    replace_path,
)

pytestmark = pytest.mark.django_db

REQUESTS_PATH = "/api/catches/requests/"
INCOMING_PATH = "/api/catches/incoming-requests/"
SUMMARY_PATH = f"{INCOMING_PATH}summary/"
PREVIEW_PATH = "/api/catches/preview/"


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


# --- Helpers ------------------------------------------------------------------


def _submit(scenario: PreviewScenario) -> Any:
    return scenario.catcher_client().post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )


def _pending(label: str) -> tuple[PreviewScenario, int]:
    scenario = create_preview_scenario(label)
    response = _submit(scenario)
    assert response.status_code == 201, response.content
    return scenario, int(response.json()["request"]["id"])


def _act(scenario: PreviewScenario, request_id: int, action: str, **body: Any) -> Any:
    """Run one owner action. ``decline`` sends ``block: false`` unless told."""
    path = f"{INCOMING_PATH}{request_id}/"
    client = owner_client(scenario.owner)
    if action == "unblock":
        return client.delete(f"{path}block/")
    if action == "decline":
        body = {"block": False, **body}
    if action == "decline_block":
        action, body = "decline", {"block": True}
    if action == "undo":
        action = "undo-decline"
    return client.post(f"{path}{action}/", body, content_type="application/json")


def _withdraw(scenario: PreviewScenario, request_id: int) -> Any:
    return scenario.catcher_client().post(f"{REQUESTS_PATH}{request_id}/withdraw/")


def _run(scenario: PreviewScenario, request_id: int, action: str) -> Any:
    if action == "withdraw":
        return _withdraw(scenario, request_id)
    if action == "invalidate":
        # The operator service from #507 (AC38).
        assert invalidate_request_as_operator(request_id=request_id).changed
        return None
    return _act(scenario, request_id, action)


def _state(response: Any) -> str:
    body = response.json()
    return str(body["request"]["state"] if "request" in body else body["state"])


def _age_trio(scenario: PreviewScenario, seconds: int) -> None:
    """Move the trio's request and decline times *seconds* into the past."""
    delta = datetime.timedelta(seconds=seconds)
    rows = CatchRequest.objects.filter(
        player=scenario.catcher, fursuit=scenario.fursuit
    )
    rows.update(requested_at=F("requested_at") - delta)
    rows.filter(declined_at__isnull=False).update(declined_at=F("declined_at") - delta)


def _close_window(scenario: PreviewScenario) -> None:
    type(scenario.convention).objects.filter(pk=scenario.convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )


def _utc(value: datetime.datetime | None) -> str:
    assert value is not None
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


def _stranger(label: str) -> Client:
    user, _ = create_player(label)
    return force_authenticated_client(user=user)


# --- Owner decisions ------------------------------------------------------------


def test_approve_creates_the_catch_with_the_request_time() -> None:
    """AC1: the catch time is the request time. Approval keeps its own time."""
    scenario, request_id = _pending("approve")
    CatchRequest.objects.filter(pk=request_id).update(
        requested_at=F("requested_at") - datetime.timedelta(minutes=5)
    )

    response = _act(scenario, request_id, "approve")

    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    row = CatchRequest.objects.get(pk=request_id)
    catch = Catch.objects.get()
    assert row.state == CatchRequestState.APPROVED
    assert catch.caught_at == row.requested_at
    assert catch.approved_at == row.approved_at
    assert catch.approved_at - catch.caught_at >= datetime.timedelta(minutes=5)
    body = response.json()
    assert body["request"]["state"] == "approved"
    assert body["catch"]["id"] == catch.pk
    assert body["catch"]["caught_at"] == _utc(row.requested_at)


def test_decline_needs_no_reason_and_offers_undo_for_ten_seconds() -> None:
    """AC2, AC10: an ordinary decline records its time and its undo deadline."""
    scenario, request_id = _pending("decline")

    response = _act(scenario, request_id, "decline")

    assert response.status_code == 200, response.content
    row = CatchRequest.objects.get(pk=request_id)
    assert row.state == CatchRequestState.DECLINED
    assert row.declined_at is not None
    assert not row.decline_blocked
    body = response.json()
    assert body["state"] == "declined"
    assert body["undo_available_until"] == _utc(
        row.declined_at + datetime.timedelta(seconds=10)
    )
    assert not CatchBlock.objects.exists()


def _disable_player(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.catcher_profile.pk).update(is_enabled=False)


def _disable_owner(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.owner_profile.pk).update(is_enabled=False)


def _disable_suit(s: PreviewScenario) -> None:
    Fursuit.objects.filter(pk=s.fursuit.pk).update(is_enabled=False)


def _pause_convention(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        status=ConventionStatus.PAUSED
    )


@pytest.mark.parametrize(
    "pause",
    [_disable_player, _disable_suit, _pause_convention],
    ids=lambda f: f.__name__,
)
def test_a_paused_request_refuses_approval_and_allows_other_actions(
    pause: Callable[[PreviewScenario], None],
) -> None:
    """AC3, AC11: approval waits. Decline, undo, restore, and unblock still work."""
    scenario, request_id = _pending("paused")
    pause(scenario)

    listed = owner_client(scenario.owner).get(INCOMING_PATH).json()["results"]
    approve = _act(scenario, request_id, "approve")

    assert listed[0]["approval_paused"] is True
    assert (approve.status_code, approve.json()["code"]) == (409, "approval_paused")
    assert CatchRequest.objects.get(pk=request_id).state == "pending"
    assert not Catch.objects.exists()
    assert _act(scenario, request_id, "decline_block").status_code == 200
    assert _act(scenario, request_id, "restore").status_code == 200
    assert _act(scenario, request_id, "unblock").status_code == 204
    assert _act(scenario, request_id, "decline").status_code == 200
    assert _act(scenario, request_id, "undo").status_code == 200


def test_a_disabled_owner_cannot_review() -> None:
    """AC3: a disabled owner gets the generic 403, as for other fursuit writes."""
    scenario, request_id = _pending("paused_owner")
    _disable_owner(scenario)

    responses = [
        owner_client(scenario.owner).get(INCOMING_PATH),
        _act(scenario, request_id, "approve"),
    ]

    assert [response.status_code for response in responses] == [403, 403]
    assert CatchRequest.objects.get(pk=request_id).state == "pending"


def _end_session(s: PreviewScenario) -> None:
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        ended_at=timezone.now(), end_reason="owner"
    )


def _expire_session(s: PreviewScenario) -> None:
    now = timezone.now()
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        started_at=now - datetime.timedelta(hours=2),
        expires_at=now - datetime.timedelta(seconds=1),
    )


def _end_convention(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        end_date=timezone.localdate() - datetime.timedelta(days=1),
        status=ConventionStatus.COMPLETED,
    )


def _replace_tag(s: PreviewScenario) -> None:
    response = owner_client(s.owner).post(
        replace_path(s.fursuit.pk),
        {"expected_version": 1},
        content_type="application/json",
    )
    assert response.status_code == 200


def _revoke_tag(s: PreviewScenario) -> None:
    revoke_tag_as_operator(FursuitTag.objects.get(fursuit=s.fursuit).pk)


def _owner_deactivates(s: PreviewScenario) -> None:
    FursuitActivation.objects.filter(pk=s.activation.pk).update(
        is_active=False, deactivated_at=timezone.now()
    )


@pytest.mark.parametrize(
    "change",
    [
        _end_session,
        _expire_session,
        _end_convention,
        _replace_tag,
        _revoke_tag,
        _owner_deactivates,
    ],
    ids=lambda f: f.__name__,
)
def test_a_request_stays_approvable_after_the_target_changes(
    change: Callable[[PreviewScenario], None],
) -> None:
    """AC4: session, convention end, tag, and owner deactivation keep approval."""
    scenario, request_id = _pending("approvable")
    change(scenario)

    response = _act(scenario, request_id, "approve")

    assert response.status_code == 200, response.content
    assert Catch.objects.count() == 1


def test_approve_after_a_catch_from_another_path_is_superseded() -> None:
    """AC5: the request stays pending, and no second catch appears."""
    scenario, request_id = _pending("superseded")
    now = timezone.now()
    Catch.objects.create(
        catcher_user=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        caught_at=now,
        approved_at=now,
    )

    response = _act(scenario, request_id, "approve")

    assert (response.status_code, response.json()["code"]) == (
        409,
        "request_superseded",
    )
    assert CatchRequest.objects.get(pk=request_id).state == "pending"
    assert Catch.objects.count() == 1


@pytest.mark.parametrize(
    "action", ["approve", "decline", "undo-decline", "restore", "block", "withdraw"]
)
def test_a_request_of_someone_else_is_not_found(action: str) -> None:
    """AC6, AC20: a stranger cannot tell that the request exists."""
    _, request_id = _pending(f"stranger_{action}")
    client = _stranger(f"stranger_caller_{action}")

    if action == "withdraw":
        response = client.post(f"{REQUESTS_PATH}{request_id}/withdraw/")
    elif action == "block":
        response = client.delete(f"{INCOMING_PATH}{request_id}/block/")
    else:
        response = client.post(
            f"{INCOMING_PATH}{request_id}/{action}/",
            {"block": False} if action == "decline" else {},
            content_type="application/json",
        )

    assert (response.status_code, response.json()["code"]) == (
        404,
        "request_not_found",
    )
    assert CatchRequest.objects.get(pk=request_id).state == "pending"


# --- Owner reads ----------------------------------------------------------------


def test_the_owner_list_shows_the_owner_request_fields() -> None:
    """AC7, AC9 to AC11: fields, order, history, and the unavailable mapping."""
    scenario, first_id = _pending("owner_list")
    assert _act(scenario, first_id, "decline").status_code == 200
    _age_trio(scenario, 30)
    second = _submit(scenario)
    assert second.status_code == 201, second.content
    second_id = int(second.json()["request"]["id"])
    other, _ = create_player("owner_list_other")
    ConventionEnrollment.objects.create(
        user=other, convention=scenario.convention, is_active=True
    )
    third = force_authenticated_client(user=other).post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )
    third_id = int(third.json()["request"]["id"])
    CatchRequest.objects.filter(pk=third_id).update(
        state=CatchRequestState.INVALIDATED, invalidated_at=timezone.now()
    )

    response = owner_client(scenario.owner).get(INCOMING_PATH)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    results = response.json()["results"]
    assert [row["id"] for row in results] == [third_id, second_id, first_id]
    by_id = {row["id"]: row for row in results}
    second_row = CatchRequest.objects.get(pk=second_id)
    assert by_id[second_id] == {
        "id": second_id,
        "fursuit": by_id[second_id]["fursuit"],
        "convention_id": scenario.convention.pk,
        "player": {
            "display_name": scenario.catcher_profile.display_name,
            "handle": scenario.catcher_profile.handle,
        },
        "state": "pending",
        "requested_at": _utc(second_row.requested_at),
        "undo_available_until": None,
        "prior_decline_count": 1,
        "player_blocked": False,
        "approval_paused": False,
        "review_deadline_at": _utc(scenario.convention.review_deadline_at),
    }
    assert by_id[second_id]["fursuit"]["id"] == scenario.fursuit.pk
    assert by_id[first_id]["state"] == "declined"
    assert by_id[first_id]["prior_decline_count"] == 0
    assert by_id[first_id]["undo_available_until"] is None
    assert by_id[third_id]["state"] == "unavailable"


def test_the_owner_list_filters_and_hides_closed_windows() -> None:
    """AC7, AC39: filters narrow the list. A closed window leaves it."""
    scenario, request_id = _pending("owner_filter")
    other_suit = create_suit(scenario.owner)
    client = owner_client(scenario.owner)

    def ids(query: str) -> list[int]:
        response = client.get(f"{INCOMING_PATH}{query}")
        assert response.status_code == 200, response.content
        return [row["id"] for row in response.json()["results"]]

    assert ids(f"?convention_id={scenario.convention.pk}") == [request_id]
    assert ids(f"?fursuit_id={scenario.fursuit.pk}") == [request_id]
    assert ids(f"?fursuit_id={other_suit.pk}") == []
    assert ids(f"?convention_id={scenario.convention.pk + 1000}") == []
    assert _stranger("owner_filter_stranger").get(INCOMING_PATH).json() == {
        "results": []
    }
    assert client.get(f"{INCOMING_PATH}?fursuit_id=x").status_code == 400
    _close_window(scenario)
    assert ids("") == []


def test_the_owner_summary_counts_pending_requests_per_suit() -> None:
    """AC8, AC39: only pending requests in open windows count."""
    scenario, request_id = _pending("summary")
    second_suit = create_suit(scenario.owner)
    create_catch_session(
        activation=create_activation_row(
            fursuit=second_suit, convention=scenario.convention, active=True
        )
    )
    second = scenario.catcher_client().post(
        REQUESTS_PATH,
        {"payload": read_payload(scenario.owner, second_suit)},
        content_type="application/json",
    )
    assert second.status_code == 201
    client = owner_client(scenario.owner)

    first = client.get(SUMMARY_PATH)
    assert _act(scenario, request_id, "decline").status_code == 200
    after = client.get(f"{SUMMARY_PATH}?convention_id={scenario.convention.pk}")

    assert first.status_code == 200
    assert first["Cache-Control"] == "no-store"
    assert first.json() == {
        "pending_count": 2,
        "fursuits": [
            {"fursuit_id": scenario.fursuit.pk, "pending_count": 1},
            {"fursuit_id": second_suit.pk, "pending_count": 1},
        ],
    }
    assert after.json() == {
        "pending_count": 1,
        "fursuits": [{"fursuit_id": second_suit.pk, "pending_count": 1}],
    }
    _close_window(scenario)
    assert client.get(SUMMARY_PATH).json() == {"pending_count": 0, "fursuits": []}


def test_the_owner_list_runs_a_fixed_number_of_queries() -> None:
    """AC12: more rows do not add queries."""
    scenario, _ = _pending("queries")
    client = owner_client(scenario.owner)

    def count() -> int:
        with CaptureQueriesContext(connection) as queries:
            assert client.get(INCOMING_PATH).status_code == 200
        return len(queries)

    one = count()
    for index in range(3):
        user, _ = create_player(f"queries_{index}")
        ConventionEnrollment.objects.create(
            user=user, convention=scenario.convention, is_active=True
        )
        response = force_authenticated_client(user=user).post(
            REQUESTS_PATH,
            {"payload": scenario.payload},
            content_type="application/json",
        )
        assert response.status_code == 201
        _act(scenario, int(response.json()["request"]["id"]), "decline_block")

    assert count() == one


# --- Undo and restore -----------------------------------------------------------


def test_undo_returns_a_fresh_decline_to_pending_and_then_expires() -> None:
    """AC13, AC17: undo works for 10 seconds. Restore still works after that."""
    scenario, request_id = _pending("undo")
    assert _act(scenario, request_id, "decline").status_code == 200

    undo = _act(scenario, request_id, "undo")
    repeat = _act(scenario, request_id, "undo")
    assert _act(scenario, request_id, "decline").status_code == 200
    _age_trio(scenario, 11)
    late = _act(scenario, request_id, "undo")
    restore = _act(scenario, request_id, "restore")

    assert (undo.status_code, _state(undo)) == (200, "pending")
    assert (repeat.status_code, _state(repeat)) == (200, "pending")
    assert (late.status_code, late.json()["code"]) == (409, "undo_expired")
    assert (restore.status_code, _state(restore)) == (200, "pending")
    assert CatchRequest.objects.get(pk=request_id).declined_at is None


def test_a_blocked_decline_has_no_undo_but_can_be_restored() -> None:
    """AC14, AC16: restore clears the decline and keeps the block."""
    scenario, request_id = _pending("blocked_restore")
    blocked = _act(scenario, request_id, "decline_block")

    undo = _act(scenario, request_id, "undo")
    restore = _act(scenario, request_id, "restore")
    approve = _act(scenario, request_id, "approve")

    assert blocked.json()["undo_available_until"] is None
    assert blocked.json()["player_blocked"] is True
    assert (undo.status_code, undo.json()["code"]) == (409, "undo_expired")
    assert restore.status_code == 200
    assert restore.json()["player_blocked"] is True
    assert approve.status_code == 200, approve.content
    row = CatchRequest.objects.get(pk=request_id)
    assert (row.declined_at, row.decline_blocked) == (None, False)
    assert CatchBlock.objects.count() == 1


def _newer_request(s: PreviewScenario, request_id: int) -> None:
    _age_trio(s, 30)
    assert _submit(s).status_code == 201


def _catch_for_trio(s: PreviewScenario, request_id: int) -> None:
    now = timezone.now()
    Catch.objects.create(
        catcher_user=s.catcher,
        fursuit=s.fursuit,
        convention=s.convention,
        activation=s.activation,
        catch_session=s.session,
        caught_at=now,
        approved_at=now,
    )


@pytest.mark.parametrize(
    "supersede",
    [_newer_request, _catch_for_trio],
    ids=lambda f: f.__name__,
)
@pytest.mark.parametrize("action", ["undo", "restore"])
def test_undo_and_restore_act_only_on_the_latest_request(
    supersede: Callable[[PreviewScenario, int], None], action: str
) -> None:
    """AC15: a newer request or a catch supersedes the decline.

    The outcome table covers invalidation.
    """
    scenario, request_id = _pending(f"latest_{action}")
    assert _act(scenario, request_id, "decline").status_code == 200
    supersede(scenario, request_id)

    response = _act(scenario, request_id, action)

    assert (response.status_code, response.json()["code"]) == (
        409,
        "request_superseded",
    )
    assert CatchRequest.objects.filter(state="pending").count() == (
        1 if supersede is _newer_request else 0
    )


def test_undo_and_restore_recalculate_the_cooldown() -> None:
    """Original AC6: removing a decline from the count shortens the wait."""
    scenario, first_id = _pending("recalculate")
    assert _act(scenario, first_id, "decline").status_code == 200
    _age_trio(scenario, 11)
    second = _submit(scenario)
    second_id = int(second.json()["request"]["id"])
    assert _act(scenario, second_id, "decline").status_code == 200
    long_wait = _submit(scenario)

    assert _act(scenario, second_id, "restore").status_code == 200
    assert _withdraw(scenario, second_id).status_code == 200
    short_wait = _submit(scenario)

    assert long_wait.status_code == 429
    assert long_wait.json()["retry_after_seconds"] > 590
    assert short_wait.status_code == 429
    assert short_wait.json()["retry_after_seconds"] <= 10


# --- Withdrawal -----------------------------------------------------------------


def test_withdraw_ends_a_pending_request_without_counting_a_decline() -> None:
    """AC18, AC19: withdrawal stops approval and keeps the submission floor."""
    scenario, request_id = _pending("withdraw")
    ConventionEnrollment.objects.filter(pk=scenario.catcher_enrollment.pk).update(
        is_active=False
    )

    response = _withdraw(scenario, request_id)
    approve = _act(scenario, request_id, "approve")
    ConventionEnrollment.objects.filter(pk=scenario.catcher_enrollment.pk).update(
        is_active=True
    )
    retry = _submit(scenario)

    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    assert response.json()["state"] == "withdrawn"
    row = CatchRequest.objects.get(pk=request_id)
    assert (row.withdrawn_at is not None, row.declined_at) == (True, None)
    assert (approve.status_code, approve.json()) == (
        409,
        {
            "code": "request_state_changed",
            "detail": approve.json()["detail"],
            "state": "withdrawn",
        },
    )
    assert retry.status_code == 429
    assert retry.json()["code"] == "cooldown_active"
    assert 1 <= retry.json()["retry_after_seconds"] <= 10


def test_an_ineligible_player_cannot_withdraw() -> None:
    """AC20: withdrawal needs participation eligibility only."""
    scenario, request_id = _pending("withdraw_ineligible")
    _disable_player(scenario)

    response = _withdraw(scenario, request_id)

    assert (response.status_code, response.json()["code"]) == (
        403,
        "catcher_ineligible",
    )
    assert CatchRequest.objects.get(pk=request_id).state == "pending"


# --- Competing and repeated actions ---------------------------------------------


@pytest.mark.parametrize(
    ("first", "second", "status", "code", "state"),
    [
        (("approve",), "withdraw", 409, "request_state_changed", "approved"),
        (("withdraw",), "approve", 409, "request_state_changed", "withdrawn"),
        (("approve",), "decline", 409, "request_state_changed", "approved"),
        (("decline",), "approve", 409, "request_state_changed", "declined"),
        (("decline",), "withdraw", 409, "request_state_changed", "declined"),
        (("withdraw",), "decline", 409, "request_state_changed", "withdrawn"),
        (("withdraw",), "restore", 409, "request_state_changed", "withdrawn"),
        (("decline",), "undo", 200, None, "pending"),
        (("decline",), "restore", 200, None, "pending"),
        (("decline", "restore"), "restore", 200, None, "pending"),
        (("approve",), "approve", 200, None, "approved"),
        (("decline",), "decline", 200, None, "declined"),
        (("withdraw",), "withdraw", 200, None, "withdrawn"),
        (("decline",), "decline_block", 200, None, "declined"),
        (("decline_block",), "decline", 200, None, "declined"),
        (("invalidate",), "approve", 409, "request_state_changed", "unavailable"),
        (("invalidate",), "decline", 409, "request_state_changed", "unavailable"),
        (("invalidate",), "withdraw", 409, "request_state_changed", "unavailable"),
        (("invalidate",), "undo", 409, "request_superseded", None),
        (("invalidate",), "restore", 409, "request_superseded", None),
    ],
)
def test_each_pair_of_actions_has_one_outcome(
    first: tuple[str, ...], second: str, status: int, code: str | None, state: str
) -> None:
    """AC35, AC38: a loser sees the current state. A repeat duplicates nothing."""
    scenario, request_id = _pending("pair")
    for step in first:
        response = _run(scenario, request_id, step)
        assert response is None or response.status_code == 200, response.content
    before = (Catch.objects.count(), CatchBlock.objects.count())

    response = _run(scenario, request_id, second)

    assert response.status_code == status, response.content
    if code is None:
        assert _state(response) == state
    else:
        assert response.json()["code"] == code
        assert response.json().get("state") == state
    if status == 409 or first[-1] == second:
        assert (Catch.objects.count(), CatchBlock.objects.count()) == before


def test_restore_and_resubmission_converge_on_one_pending_request() -> None:
    """AC35: a submission after a restore returns the restored request."""
    scenario, first_id = _pending("converge")
    assert _act(scenario, first_id, "decline").status_code == 200
    _age_trio(scenario, 11)
    assert _act(scenario, first_id, "restore").status_code == 200

    retry = _submit(scenario)
    assert _withdraw(scenario, first_id).status_code == 200
    _age_trio(scenario, 11)
    newer = _submit(scenario)

    assert (retry.status_code, retry.json()["outcome"]) == (200, "already_pending")
    assert retry.json()["request"]["id"] == first_id
    assert newer.status_code == 201


def test_every_action_in_a_closed_window_is_refused() -> None:
    """AC39: the window decides. A deleted request is not found."""
    scenario, request_id = _pending("closed")
    _close_window(scenario)

    responses = [
        _act(scenario, request_id, action)
        for action in ("approve", "decline", "undo", "restore", "unblock")
    ] + [_withdraw(scenario, request_id)]
    CatchRequest.objects.filter(pk=request_id).delete()
    gone = _act(scenario, request_id, "approve")

    assert {(r.status_code, r.json()["code"]) for r in responses} == {
        (409, "review_window_closed")
    }
    assert (gone.status_code, gone.json()["code"]) == (404, "request_not_found")


# --- Blocks ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["manual", "automatic"])
def test_a_block_refuses_later_attempts_with_the_neutral_target_code(
    mode: str,
) -> None:
    """AC28, AC30, AC31: the player sees declined, then the neutral 404."""
    scenario, request_id = _pending(f"block_{mode}")
    response = _act(scenario, request_id, "decline_block")
    Fursuit.objects.filter(pk=scenario.fursuit.pk).update(catch_approval_mode=mode)
    _age_trio(scenario, 11)

    submit = _submit(scenario)
    preview = scenario.catcher_client().post(
        PREVIEW_PATH, {"payload": scenario.payload}, content_type="application/json"
    )
    listed = scenario.catcher_client().get(REQUESTS_PATH).json()["results"]

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["player_blocked"]) == (
        "declined",
        True,
    )
    row = CatchRequest.objects.get(pk=request_id)
    assert row.decline_blocked
    assert (
        CatchBlock.objects.filter(
            player=scenario.catcher,
            fursuit=scenario.fursuit,
            convention=scenario.convention,
        ).count()
        == 1
    )
    assert (submit.status_code, submit.json()) == (404, TARGET_UNAVAILABLE)
    assert (preview.status_code, preview.json()) == (404, TARGET_UNAVAILABLE)
    assert [item["state"] for item in listed] == ["declined"]
    assert "block" not in str(listed)
    assert CatchRequest.objects.count() == 1
    assert not Catch.objects.exists()


def test_adding_a_block_to_a_decline_keeps_its_time() -> None:
    """AC29: the cooldown does not move. Undo is no longer offered."""
    scenario, request_id = _pending("block_later")
    assert _act(scenario, request_id, "decline").status_code == 200
    declined_at = CatchRequest.objects.get(pk=request_id).declined_at

    blocked = _act(scenario, request_id, "decline_block")
    again = _act(scenario, request_id, "decline_block")
    undo = _act(scenario, request_id, "undo")

    assert blocked.status_code == again.status_code == 200
    assert CatchRequest.objects.get(pk=request_id).declined_at == declined_at
    assert CatchBlock.objects.count() == 1
    assert undo.json()["code"] == "undo_expired"


def test_preview_ignores_cooldowns() -> None:
    """AC31: preview creates nothing, so only submit applies the cooldown."""
    scenario, request_id = _pending("preview_cooldown")
    assert _act(scenario, request_id, "decline").status_code == 200

    preview = scenario.catcher_client().post(
        PREVIEW_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert preview.status_code == 200
    assert _submit(scenario).status_code == 429


def test_unblock_removes_the_block_and_keeps_the_cooldown() -> None:
    """AC32: unblock is idempotent and leaves request history alone."""
    scenario, request_id = _pending("unblock")
    assert _act(scenario, request_id, "decline_block").status_code == 200

    first = _act(scenario, request_id, "unblock")
    second = _act(scenario, request_id, "unblock")
    retry = _submit(scenario)

    assert (first.status_code, first.content) == (204, b"")
    assert second.status_code == 204
    assert not CatchBlock.objects.exists()
    assert CatchRequest.objects.get(pk=request_id).decline_blocked
    assert (retry.status_code, retry.json()["code"]) == (429, "cooldown_active")


def test_a_retry_returns_the_existing_request_despite_a_block() -> None:
    """AC27: the existing-result check runs before the block and cooldown."""
    scenario, request_id = _pending("existing_blocked")
    assert _act(scenario, request_id, "decline_block").status_code == 200
    assert _act(scenario, request_id, "restore").status_code == 200

    retry = _submit(scenario)

    assert (retry.status_code, retry.json()["outcome"]) == (200, "already_pending")
    assert retry.json()["request"]["id"] == request_id


# --- Cooldowns and the per-player limit -----------------------------------------


def test_a_cooldown_refusal_uses_the_429_shape_and_header() -> None:
    """AC21, AC23: the first decline permits a retry after 10 seconds."""
    scenario, request_id = _pending("cooldown")
    assert _act(scenario, request_id, "decline").status_code == 200

    response = _submit(scenario)

    assert response.status_code == 429
    body = response.json()
    assert set(body) == {"code", "detail", "retry_after_seconds"}
    assert body["code"] == "cooldown_active"
    assert isinstance(body["retry_after_seconds"], int)
    assert 1 <= body["retry_after_seconds"] <= 10
    assert response["Retry-After"] == str(body["retry_after_seconds"])
    assert CatchRequest.objects.count() == 1
    _age_trio(scenario, 11)
    assert _submit(scenario).status_code == 201


def _fill_window(player: Any, count: int, *, age_seconds: int) -> None:
    """Give *player* *count* requests at other suits, *age_seconds* old."""
    convention = create_convention(f"limit_{player.pk}_{count}_{age_seconds}")
    owner, _ = create_player(f"limit_owner_{player.pk}_{count}_{age_seconds}")
    requested_at = timezone.now() - datetime.timedelta(seconds=age_seconds)
    for _ in range(count):
        suit = create_suit(owner)
        activation = create_activation_row(
            fursuit=suit, convention=convention, active=True
        )
        CatchRequest.objects.create(
            player=player,
            fursuit=suit,
            convention=convention,
            activation=activation,
            catch_session=create_catch_session(activation=activation),
            state=CatchRequestState.APPROVED,
            requested_at=requested_at,
            approved_at=requested_at,
        )


def test_the_per_player_limit_counts_requests_across_suits() -> None:
    """AC24, AC25: the 31st request in 10 minutes waits for the oldest to age."""
    scenario = create_preview_scenario("limit")
    _fill_window(scenario.catcher, 30, age_seconds=500)

    refused = _submit(scenario)
    again = _submit(scenario)
    CatchRequest.objects.filter(player=scenario.catcher).update(
        requested_at=F("requested_at") - datetime.timedelta(seconds=101)
    )
    accepted = _submit(scenario)

    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert 99 <= refused.json()["retry_after_seconds"] <= 100
    assert refused["Retry-After"] == str(refused.json()["retry_after_seconds"])
    assert again.status_code == 429
    assert accepted.status_code == 201, accepted.content


@pytest.mark.parametrize(
    ("declines", "limit_age", "code"),
    [
        pytest.param(2, 500, "cooldown_active", id="cooldown-longer"),
        pytest.param(1, 10, "rate_limited", id="limit-longer"),
    ],
)
def test_the_longer_refusal_wins_when_both_apply(
    declines: int, limit_age: int, code: str
) -> None:
    """AC26: one retry after Retry-After is enough."""
    scenario, request_id = _pending(f"both_{code}")
    assert _act(scenario, request_id, "decline").status_code == 200
    if declines == 2:
        _age_trio(scenario, 11)
        second = int(_submit(scenario).json()["request"]["id"])
        assert _act(scenario, second, "decline").status_code == 200
    _fill_window(scenario.catcher, 29, age_seconds=limit_age)

    response = _submit(scenario)

    assert response.status_code == 429
    assert response.json()["code"] == code
    expected_floor = 590 if code == "rate_limited" else 500
    assert response.json()["retry_after_seconds"] >= expected_floor


# --- Gate and schema ------------------------------------------------------------


def test_the_gate_off_hides_every_new_operation(settings: Any) -> None:
    """AC41: each new operation returns the generic not-found shape."""
    scenario, request_id = _pending("gate")
    settings.CATCH_REQUESTS_ENABLED = False
    owner = owner_client(scenario.owner)
    base = f"{INCOMING_PATH}{request_id}/"

    responses = [
        owner.get(INCOMING_PATH),
        owner.get(SUMMARY_PATH),
        owner.post(f"{base}approve/"),
        owner.post(
            f"{base}decline/", {"block": False}, content_type="application/json"
        ),
        owner.post(f"{base}undo-decline/"),
        owner.post(f"{base}restore/"),
        owner.delete(f"{base}block/"),
        scenario.catcher_client().post(f"{REQUESTS_PATH}{request_id}/withdraw/"),
    ]

    assert {(r.status_code, str(r.json())) for r in responses} == {
        (404, str(GENERIC_NOT_FOUND))
    }
    assert CatchRequest.objects.get(pk=request_id).state == "pending"


@pytest.mark.parametrize("body", [{}, {"block": "yes"}, {"block": True, "extra": 1}])
def test_decline_rejects_a_body_without_one_boolean_block(body: object) -> None:
    scenario, request_id = _pending("decline_body")

    response = owner_client(scenario.owner).post(
        f"{INCOMING_PATH}{request_id}/decline/", body, content_type="application/json"
    )

    assert response.status_code == 400
    assert CatchRequest.objects.get(pk=request_id).state == "pending"


def test_the_schema_documents_the_review_operations() -> None:
    """AC44: the client can decode every documented body."""
    schema = yaml.safe_load(Client().get("/api/schema/").content)
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    def body(path: str, method: str, status: str) -> dict[str, Any]:
        content = paths[path][method]["responses"][status]["content"]
        return content["application/json"]["schema"]

    action = "/api/catches/incoming-requests/{id}/"
    assert body(INCOMING_PATH, "get", "200") == {
        "$ref": "#/components/schemas/OwnerRequestList"
    }
    assert body(SUMMARY_PATH, "get", "200") == {
        "$ref": "#/components/schemas/OwnerRequestSummary"
    }
    assert body(f"{action}approve/", "post", "200") == {
        "$ref": "#/components/schemas/OwnerApproval"
    }
    for name in ("decline/", "undo-decline/", "restore/"):
        assert body(f"{action}{name}", "post", "200") == {
            "$ref": "#/components/schemas/OwnerRequest"
        }
        assert body(f"{action}{name}", "post", "409") == {
            "$ref": "#/components/schemas/CatchRequestActionError"
        }
    # The gate-off 404 carries detail only, so the shape must allow it (#523).
    not_found = {"$ref": "#/components/schemas/CatchRequestActionNotFound"}
    for name, method in (("approve/", "post"), ("block/", "delete")):
        assert body(f"{action}{name}", method, "404") == not_found
    assert components["CatchRequestActionNotFound"]["required"] == ["detail"]
    assert "204" in paths[f"{action}block/"]["delete"]["responses"]
    withdraw = "/api/catches/requests/{id}/withdraw/"
    assert body(withdraw, "post", "200") == {
        "$ref": "#/components/schemas/PlayerRequest"
    }
    assert body(REQUESTS_PATH, "post", "429") == {
        "$ref": "#/components/schemas/CatchRequestRefusal"
    }
    assert "Retry-After" in paths[REQUESTS_PATH]["post"]["responses"]["429"]["headers"]
    assert set(components["OwnerRequest"]["required"]) == {
        "id",
        "fursuit",
        "convention_id",
        "player",
        "state",
        "requested_at",
        "undo_available_until",
        "prior_decline_count",
        "player_blocked",
        "approval_paused",
        "review_deadline_at",
    }
