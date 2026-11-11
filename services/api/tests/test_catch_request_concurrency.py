"""Real PostgreSQL, lock-observed catch request races (#505 AC19, AC20, #506 AC36).

A held PlayerProfile lock queues the workers. pg_blocking_pids proves the
queue, so no sleep picks a winner. The harness follows
test_fursuit_tag_concurrency.py.
"""

from __future__ import annotations

import datetime
import math
import os
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from catches.models import Catch, CatchBlock, CatchRequest, CatchRequestState
from catches.request_cleanup import run_cleanup
from catches.request_invalidation import invalidate_request_as_operator
from conventions.models import Convention, ConventionEnrollment
from conventions.services import remove_convention_enrollment
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_tag_test_support import (
    PreviewScenario,
    create_convention,
    create_player,
    create_preview_scenario,
    create_suit,
    read_payload,
)

REQUESTS_PATH = "/api/catches/requests/"
INCOMING_PATH = "/api/catches/incoming-requests/"


def _wait_seconds() -> float:
    try:
        value = float(os.environ.get("TAILTAG_TEST_LOCK_WAIT_SECONDS", "5.0"))
    except ValueError:
        return 5.0
    return value if math.isfinite(value) and value > 0 else 5.0


_WAIT_SECONDS = _wait_seconds()
_RESULT_SECONDS = 25.0


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


def _configured_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', '18000ms', false)")
        cursor.execute("SELECT set_config('statement_timeout', '20000ms', false)")
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _worker(action: Callable[[], Any], pids: Queue[int]) -> Any:
    close_old_connections()
    try:
        pids.put(_configured_pid())
        return action()
    finally:
        connection.close()


def _pid(queue: Queue[int], future: Future[Any]) -> int:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        try:
            return queue.get_nowait()
        except Empty:
            if future.done():
                pytest.fail(
                    f"worker finished before lock evidence: {future.result()!r}"
                )
            sleep(0.01)
    pytest.fail("worker did not publish a backend PID")


def _blocked(waiter: int, holders: set[int], future: Future[Any]) -> None:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        if future.done():
            pytest.fail(f"worker finished before lock evidence: {future.result()!r}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", [waiter])
            row = cursor.fetchone()
        assert row is not None
        if holders & set(row[0]):
            return
        sleep(0.01)
    pytest.fail(f"backend {waiter} did not queue behind {holders}")


def _race(
    profile_ids: Sequence[int],
    first: Callable[[], Any],
    second: Callable[[], Any],
    *,
    convention_ids: Sequence[int] = (),
) -> tuple[Any, Any]:
    """Hold *profile_ids*, queue *first* then *second* behind them, then release.

    *convention_ids* are also held, for a worker that locks no profile.
    """
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            list(
                PlayerProfile.objects.select_for_update()
                .filter(pk__in=profile_ids)
                .order_by("pk")
            )
            list(
                Convention.objects.select_for_update()
                .filter(pk__in=convention_ids)
                .order_by("pk")
            )
            holder = _configured_pid()
            one = pool.submit(_worker, first, first_pids)
            one_pid = _pid(first_pids, one)
            _blocked(one_pid, {holder}, one)
            two = pool.submit(_worker, second, second_pids)
            two_pid = _pid(second_pids, two)
            _blocked(two_pid, {holder, one_pid}, two)
        return one.result(timeout=_RESULT_SECONDS), two.result(timeout=_RESULT_SECONDS)


def _submit(user: User, payload: str) -> Callable[[], Any]:
    def call() -> Any:
        return force_authenticated_client(user=User.objects.get(pk=user.pk)).post(
            REQUESTS_PATH, {"payload": payload}, content_type="application/json"
        )

    return call


def _scenario(label: str, mode: str) -> PreviewScenario:
    scenario = create_preview_scenario(label)
    Fursuit.objects.filter(pk=scenario.fursuit.pk).update(catch_approval_mode=mode)
    return scenario


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("mode", "created", "repeated"),
    [
        ("manual", "pending", "already_pending"),
        ("automatic", "approved", "already_caught"),
    ],
)
def test_two_submissions_for_one_trio_give_one_result(
    mode: str, created: str, repeated: str
) -> None:
    """AC19, AC20: a retry racing its lost first attempt gets the same result."""
    scenario = _scenario(f"race_{mode}", mode)
    submit = _submit(scenario.catcher, scenario.payload)

    one, two = _race([scenario.catcher_profile.pk], submit, submit)

    assert (one.status_code, one.json()["outcome"]) == (201, created)
    assert (two.status_code, two.json()["outcome"]) == (200, repeated)
    assert CatchRequest.objects.count() == 1
    assert Catch.objects.count() == (1 if mode == "automatic" else 0)
    if mode == "manual":
        assert one.json()["request"] == two.json()["request"]
    else:
        assert one.json()["catch"] == two.json()["catch"]


@pytest.mark.django_db(transaction=True)
def test_two_players_catching_each_others_suits_do_not_deadlock() -> None:
    """AC18, AC20: both profiles lock in pk order, so a crossing pair completes.

    The holder keeps both profile rows. When it commits, a catcher-first lock
    order would let each worker take its own row and wait on the other's row.
    """
    convention = create_convention("crossing")
    first, first_profile = create_player("crossing_first")
    second, second_profile = create_player("crossing_second")
    payloads: dict[int, str] = {}
    for user in (first, second):
        ConventionEnrollment.objects.create(
            user=user, convention=convention, is_active=True
        )
        fursuit = create_suit(user)
        create_catch_session(
            activation=create_activation_row(
                fursuit=fursuit, convention=convention, active=True
            )
        )
        payloads[user.pk] = read_payload(user, fursuit)

    one, two = _race(
        [first_profile.pk, second_profile.pk],
        _submit(first, payloads[second.pk]),
        _submit(second, payloads[first.pk]),
    )

    assert (one.status_code, two.status_code) == (201, 201)
    assert CatchRequest.objects.filter(state="pending").count() == 2


# --- #506 AC36, AC37: owner decisions, withdrawal, blocks, and the limit ---


def _owner_action(
    scenario: PreviewScenario, request_id: int, action: str, body: object = None
) -> Callable[[], Any]:
    def call() -> Any:
        client = force_authenticated_client(user=User.objects.get(pk=scenario.owner.pk))
        return client.post(
            f"{INCOMING_PATH}{request_id}/{action}/",
            {} if body is None else body,
            content_type="application/json",
        )

    return call


def _withdraw(scenario: PreviewScenario, request_id: int) -> Callable[[], Any]:
    def call() -> Any:
        client = force_authenticated_client(
            user=User.objects.get(pk=scenario.catcher.pk)
        )
        return client.post(f"{REQUESTS_PATH}{request_id}/withdraw/")

    return call


def _pending(label: str) -> tuple[PreviewScenario, int]:
    scenario = create_preview_scenario(label)
    response = _submit(scenario.catcher, scenario.payload)()
    assert response.status_code == 201, response.content
    return scenario, int(response.json()["request"]["id"])


def _both(scenario: PreviewScenario) -> list[int]:
    return [scenario.owner_profile.pk, scenario.catcher_profile.pk]


def _age(request_id: int) -> None:
    delta = datetime.timedelta(seconds=11)
    rows = CatchRequest.objects.filter(pk=request_id)
    rows.update(requested_at=F("requested_at") - delta)
    rows.filter(declined_at__isnull=False).update(declined_at=F("declined_at") - delta)


# These actions lock different profile sets, so PostgreSQL may grant either
# queued worker first. Each test accepts both valid orders and checks the
# invariants: one result, no duplicate row, and no server error.


@pytest.mark.django_db(transaction=True)
def test_approve_and_withdraw_give_one_result() -> None:
    scenario, request_id = _pending("race_approve_withdraw")

    approve, withdraw = _race(
        _both(scenario),
        _owner_action(scenario, request_id, "approve"),
        _withdraw(scenario, request_id),
    )

    state = CatchRequest.objects.get(pk=request_id).state
    if state == CatchRequestState.APPROVED.value:
        assert approve.status_code == 200, approve.content
        assert withdraw.json() | {"detail": ""} == {
            "code": "request_state_changed",
            "detail": "",
            "state": "approved",
        }
        assert Catch.objects.count() == 1
    else:
        assert state == CatchRequestState.WITHDRAWN.value
        assert withdraw.status_code == 200, withdraw.content
        assert (approve.status_code, approve.json()["state"]) == (409, "withdrawn")
        assert not Catch.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_approvals_create_one_catch() -> None:
    scenario, request_id = _pending("race_two_approvals")
    approve = _owner_action(scenario, request_id, "approve")

    one, two = _race(_both(scenario), approve, approve)

    assert (one.status_code, two.status_code) == (200, 200)
    assert one.json()["catch"] == two.json()["catch"]
    assert Catch.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_restore_and_resubmission_keep_one_pending_request() -> None:
    scenario, request_id = _pending("race_restore_submit")
    declined = _owner_action(scenario, request_id, "decline", {"block": False})()
    assert declined.status_code == 200
    _age(request_id)

    restore, submit = _race(
        _both(scenario),
        _owner_action(scenario, request_id, "restore"),
        _submit(scenario.catcher, scenario.payload),
    )

    pending = list(
        CatchRequest.objects.filter(state=CatchRequestState.PENDING).values_list(
            "pk", flat=True
        )
    )
    assert len(pending) == 1
    if pending == [request_id]:
        assert restore.status_code == 200, restore.content
        assert (submit.status_code, submit.json()["outcome"]) == (
            200,
            "already_pending",
        )
    else:
        assert (submit.status_code, submit.json()["outcome"]) == (201, "pending")
        assert (restore.status_code, restore.json()["code"]) == (
            409,
            "request_superseded",
        )


@pytest.mark.django_db(transaction=True)
def test_a_decline_with_block_and_a_racing_submission_create_no_request() -> None:
    scenario, request_id = _pending("race_block_submit")

    decline, submit = _race(
        _both(scenario),
        _owner_action(scenario, request_id, "decline", {"block": True}),
        _submit(scenario.catcher, scenario.payload),
    )

    assert decline.status_code == 200, decline.content
    assert (
        submit.status_code,
        submit.json().get("outcome", submit.json().get("code")),
    ) in {
        (200, "already_pending"),
        (404, "catch_target_unavailable"),
    }
    assert CatchRequest.objects.count() == 1
    assert CatchBlock.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_submissions_at_the_limit_create_one_request() -> None:
    scenario = create_preview_scenario("race_limit")
    second_suit = create_suit(scenario.owner)
    create_catch_session(
        activation=create_activation_row(
            fursuit=second_suit, convention=scenario.convention, active=True
        )
    )
    second_payload = read_payload(scenario.owner, second_suit)
    filler = create_suit(scenario.owner)
    activation = create_activation_row(
        fursuit=filler, convention=create_convention("race_limit_fill"), active=True
    )
    session = create_catch_session(activation=activation)
    now = timezone.now()
    CatchRequest.objects.bulk_create(
        CatchRequest(
            player=scenario.catcher,
            fursuit=filler,
            convention=activation.convention,
            activation=activation,
            catch_session=session,
            state=CatchRequestState.WITHDRAWN,
            requested_at=now,
            withdrawn_at=now,
        )
        for _ in range(29)
    )

    one, two = _race(
        _both(scenario),
        _submit(scenario.catcher, scenario.payload),
        _submit(scenario.catcher, second_payload),
    )

    assert sorted([one.status_code, two.status_code]) == [201, 429]
    refused = one if one.status_code == 429 else two
    assert refused.json()["code"] == "rate_limited"
    assert CatchRequest.objects.filter(player=scenario.catcher).count() == 30


# --- #507 operator invalidation and cleanup -------------------------------------


@pytest.mark.django_db(transaction=True)
def test_operator_invalidation_and_approval_give_one_result() -> None:
    """#507 AC37: no catch exists for an invalidated request."""
    scenario, request_id = _pending("race_invalidate_approve")

    invalidated, approve = _race(
        _both(scenario),
        lambda: invalidate_request_as_operator(request_id=request_id),
        _owner_action(scenario, request_id, "approve"),
    )

    state = CatchRequest.objects.get(pk=request_id).state
    if state == CatchRequestState.INVALIDATED.value:
        assert invalidated.changed is True
        assert (approve.status_code, approve.json()["state"]) == (409, "unavailable")
        assert not Catch.objects.exists()
    else:
        assert state == CatchRequestState.APPROVED.value
        assert approve.status_code == 200, approve.content
        assert invalidated.changed is False
        assert Catch.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_owner_enrollment_removal_and_approval_give_one_result() -> None:
    """#507 AC37: removal invalidates a pending request, or approval keeps its catch."""
    scenario, request_id = _pending("race_removal_approve")

    _, approve = _race(
        _both(scenario),
        lambda: remove_convention_enrollment(
            enrollment_id=scenario.owner_enrollment.pk
        ),
        _owner_action(scenario, request_id, "approve"),
    )

    state = CatchRequest.objects.get(pk=request_id).state
    assert not ConventionEnrollment.objects.filter(
        pk=scenario.owner_enrollment.pk
    ).exists()
    if state == CatchRequestState.INVALIDATED.value:
        assert approve.status_code == 409, approve.content
        assert not Catch.objects.exists()
    else:
        assert state == CatchRequestState.APPROVED.value
        assert approve.status_code == 200, approve.content
        assert Catch.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_cleanup_and_an_owner_action_at_the_deadline_give_one_result() -> None:
    """#507 AC37: the action sees a closed window or a deleted row, never a 500."""
    scenario, request_id = _pending("race_cleanup_decline")
    Convention.objects.filter(pk=scenario.convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )

    decline, result = _race(
        _both(scenario),
        _owner_action(scenario, request_id, "decline", {"block": True}),
        run_cleanup,
        convention_ids=[scenario.convention.pk],
    )

    assert (decline.status_code, decline.json()["code"]) in {
        (409, "review_window_closed"),
        (404, "request_not_found"),
    }
    assert (result.succeeded, sum(result.deleted_requests.values())) == (True, 1)
    assert not CatchRequest.objects.exists()
    assert not CatchBlock.objects.exists()
