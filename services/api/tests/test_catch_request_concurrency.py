"""Real PostgreSQL, lock-observed catch request races (#505 AC19, AC20).

A held PlayerProfile lock queues the workers. pg_blocking_pids proves the
queue, so no sleep picks a winner. The harness follows
test_fursuit_tag_concurrency.py.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction

from accounts.models import User
from catches.models import Catch, CatchRequest
from conventions.models import ConventionEnrollment
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
    profile_ids: Sequence[int], first: Callable[[], Any], second: Callable[[], Any]
) -> tuple[Any, Any]:
    """Hold *profile_ids*, queue *first* then *second* behind them, then release."""
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            list(
                PlayerProfile.objects.select_for_update()
                .filter(pk__in=profile_ids)
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
