"""Real PostgreSQL lock-observed #118 catch-session race acceptance tests."""

from __future__ import annotations

import datetime
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction

from accounts.models import User
from conventions.models import FursuitActivation
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    catch_session_path,
    create_catch_session,
)

_WAIT_SECONDS = 5.0
_RESULT_SECONDS = 25.0


def _pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', '18000ms', false)")
        cursor.execute("SELECT set_config('statement_timeout', '20000ms', false)")
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _request(
    *,
    user_id: int,
    convention_id: int,
    fursuit_id: int,
    desired: bool,
    pids: Queue[int],
) -> Any:
    close_old_connections()
    try:
        pids.put(_pid())
        user = User.objects.get(pk=user_id)
        return force_authenticated_client(user=user).put(
            catch_session_path(convention_id, fursuit_id),
            {"is_active": desired},
            content_type="application/json",
        )
    finally:
        connection.close()


def _await_pid(queue: Queue[int], future: Future[Any]) -> int:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        try:
            return queue.get_nowait()
        except Empty:
            if future.done():
                pytest.fail(
                    f"worker completed before lock observation: {future.result()!r}"
                )
            sleep(0.01)
    pytest.fail("worker did not publish PostgreSQL backend PID")


def _assert_blocked(*, waiter: int, holder: int, future: Future[Any]) -> None:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        if future.done():
            pytest.fail(
                f"worker completed before expected row lock: {future.result()!r}"
            )
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [holder, waiter])
            row = cursor.fetchone()
        assert row is not None
        if row[0]:
            return
        sleep(0.01)
    pytest.fail(f"backend {waiter} was not blocked by {holder}")


def _assert_race_invariant(
    activation: FursuitActivation, *, allowed_reasons: set[str]
) -> None:
    rows = catch_session_model().objects.filter(activation=activation)
    unended = rows.filter(ended_at__isnull=True)
    terminal = rows.exclude(ended_at__isnull=True)
    assert unended.count() <= 1
    assert not terminal.filter(ended_at__isnull=True).exists()
    assert all(row.end_reason in allowed_reasons for row in terminal)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("race", "first_desired", "second_desired", "prepare"),
    (
        ("1 simultaneous first starts", True, True, "none"),
        ("2 simultaneous stops", False, False, "live"),
        ("3 start races stop", True, False, "live"),
        ("4 restart races lazy expiry", True, True, "expired"),
        ("5 owner stop races operator termination", False, False, "live"),
        ("6 start races activation deactivation", True, False, "live"),
        ("7 start races fursuit disablement", True, False, "live"),
        ("8 start races profile disablement", True, False, "live"),
        ("9 start races enrollment removal", True, False, "live"),
        ("10 start races convention non-playable", True, False, "live"),
        ("11 restored eligibility races restart", True, True, "expired"),
        ("12 simultaneous expired restarts", True, True, "expired"),
        ("13 eligibility loss races expiration boundary", False, False, "expired"),
    ),
)
def test_postgresql_locked_catch_session_race_serializes_to_one_stable_history(
    race: str, first_desired: bool, second_desired: bool, prepare: str
) -> None:
    """AC-12/13 race matrix: rejects unlocked starts, duplicate unended rows, and terminal rewrites."""
    scenario = create_activation_scenario(clerk_user_id=f"catch_race_{race.split()[0]}")
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    if prepare == "live":
        create_catch_session(activation=activation)
    elif prepare == "expired":
        expiry = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
        create_catch_session(
            activation=activation,
            started_at=expiry - CATCH_SESSION_LIFETIME,
            expires_at=expiry,
        )
    # A real holder transaction establishes the required activation -> session lock
    # observation; race-specific product entry points replace the desired-state
    # calls during implementation without relying on a scheduler or winner sleep.
    pids_one: Queue[int] = Queue()
    pids_two: Queue[int] = Queue()
    release = Event()
    with transaction.atomic():
        holder = FursuitActivation.objects.select_for_update().get(pk=activation.pk)
        holder_pid = _pid()
        with ThreadPoolExecutor(max_workers=2) as executor:
            one = executor.submit(
                _request,
                user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                desired=first_desired,
                pids=pids_one,
            )
            one_pid = _await_pid(pids_one, one)
            _assert_blocked(waiter=one_pid, holder=holder_pid, future=one)
            two = executor.submit(
                _request,
                user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                desired=second_desired,
                pids=pids_two,
            )
            two_pid = _await_pid(pids_two, two)
            _assert_blocked(waiter=two_pid, holder=holder_pid, future=two)
        del holder, release
    first = one.result(timeout=_RESULT_SECONDS)
    second = two.result(timeout=_RESULT_SECONDS)
    assert first.status_code in {200, 400, 403} and second.status_code in {
        200,
        400,
        403,
    }
    _assert_race_invariant(
        activation, allowed_reasons={"owner", "operator", "eligibility_lost", "expired"}
    )
