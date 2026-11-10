"""Real PostgreSQL, lock-observed reusable tag races (#504 AC12).

A held Fursuit row lock queues both workers. pg_blocking_pids proves the queue
order, so no sleep picks a winner. The harness follows
test_fursuit_catch_credential_concurrency.py.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from accounts.models import User
from fursuits.models import Fursuit, FursuitTag
from fursuits.services import set_fursuit_enabled
from fursuits.tags import revoke_tag_as_operator
from tests.authentication_support import force_authenticated_client
from tests.fursuit_tag_test_support import (
    create_player,
    create_suit,
    read_payload,
    replace_path,
    tag_path,
)


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
    fursuit_id: int, first: Callable[[], Any], second: Callable[[], Any]
) -> tuple[Any, Any]:
    """Hold the Fursuit row, queue *first* then *second*, then release."""
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            Fursuit.objects.select_for_update().get(pk=fursuit_id)
            holder = _configured_pid()
            one = pool.submit(_worker, first, first_pids)
            one_pid = _pid(first_pids, one)
            _blocked(one_pid, {holder}, one)
            two = pool.submit(_worker, second, second_pids)
            two_pid = _pid(second_pids, two)
            _blocked(two_pid, {holder, one_pid}, two)
        try:
            return one.result(timeout=_RESULT_SECONDS), two.result(
                timeout=_RESULT_SECONDS
            )
        except IntegrityError as error:
            pytest.fail(f"tag race leaked IntegrityError: {error}")


def _current_rows(fursuit_id: int) -> int:
    return FursuitTag.objects.filter(
        fursuit_id=fursuit_id, revoked_at__isnull=True
    ).count()


def _get(owner: User, fursuit_id: int) -> Callable[[], Any]:
    def call() -> Any:
        return force_authenticated_client(user=User.objects.get(pk=owner.pk)).get(
            tag_path(fursuit_id)
        )

    return call


def _replace(owner: User, fursuit_id: int, version: int) -> Callable[[], Any]:
    def call() -> Any:
        return force_authenticated_client(user=User.objects.get(pk=owner.pk)).post(
            replace_path(fursuit_id),
            {"expected_version": version},
            content_type="application/json",
        )

    return call


@pytest.mark.django_db(transaction=True)
def test_two_first_reads_converge_on_one_tag() -> None:
    owner, _ = create_player("race_first")
    fursuit = create_suit(owner)

    one, two = _race(fursuit.pk, _get(owner, fursuit.pk), _get(owner, fursuit.pk))

    assert one.status_code == two.status_code == 200
    assert one.json() == two.json()
    assert FursuitTag.objects.filter(fursuit=fursuit).count() == 1
    assert Fursuit.objects.get(pk=fursuit.pk).tag_version == 1


@pytest.mark.django_db(transaction=True)
def test_two_replacements_with_the_same_version_have_one_winner() -> None:
    owner, _ = create_player("race_replace")
    fursuit = create_suit(owner)
    read_payload(owner, fursuit)

    one, two = _race(
        fursuit.pk, _replace(owner, fursuit.pk, 1), _replace(owner, fursuit.pk, 1)
    )

    assert one.status_code == 200
    assert two.status_code == 409
    assert two.json()["current"]["tag_version"] == 2
    assert "payload" not in two.json()
    assert _current_rows(fursuit.pk) == 1
    assert Fursuit.objects.get(pk=fursuit.pk).tag_version == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("replace_first", [True, False])
def test_replacement_against_revocation_gives_one_valid_serial_result(
    replace_first: bool,
) -> None:
    owner, _ = create_player(f"race_revoke_{replace_first}")
    fursuit = create_suit(owner)
    read_payload(owner, fursuit)
    first_tag = FursuitTag.objects.get(fursuit=fursuit)

    def revoke() -> Any:
        return revoke_tag_as_operator(first_tag.pk)

    replace = _replace(owner, fursuit.pk, 1)
    first, second = (replace, revoke) if replace_first else (revoke, replace)
    one, two = _race(fursuit.pk, first, second)

    replace_result, revoke_result = (one, two) if replace_first else (two, one)
    fursuit.refresh_from_db()
    if replace_first:
        # The replacement ended the first tag, so the stale revoke changes nothing.
        assert replace_result.status_code == 200
        assert revoke_result.changed is False
        assert _current_rows(fursuit.pk) == 1
        assert fursuit.tag_version == 2
    else:
        # The revocation raised the version, so the replacement is stale.
        assert revoke_result.changed is True
        assert replace_result.status_code == 409
        assert replace_result.json()["current"]["state"] == "revoked"
        assert _current_rows(fursuit.pk) == 0
        assert fursuit.tag_version == 2


@pytest.mark.django_db(transaction=True)
def test_creation_queued_behind_suit_disable_creates_no_tag() -> None:
    owner, _ = create_player("race_disable")
    fursuit = create_suit(owner)

    disabled, read = _race(
        fursuit.pk,
        lambda: set_fursuit_enabled(fursuit_id=fursuit.pk, is_enabled=False),
        _get(owner, fursuit.pk),
    )

    assert disabled.changed is True
    assert read.status_code == 409
    assert read.json()["code"] == "fursuit_disabled"
    assert not FursuitTag.objects.filter(fursuit=fursuit).exists()


@pytest.mark.django_db
def test_named_constraints_reject_a_second_current_tag_and_a_duplicate_token() -> None:
    owner, _ = create_player("constraints")
    fursuit = create_suit(owner)
    other = create_suit(owner)
    read_payload(owner, fursuit)
    token = FursuitTag.objects.get(fursuit=fursuit).token

    with (
        pytest.raises(IntegrityError, match="fursuits_tag_one_current_per_fursuit"),
        transaction.atomic(),
    ):
        FursuitTag.objects.create(fursuit=fursuit, token="b" * 43, created_version=2)
    with (
        pytest.raises(IntegrityError, match="fursuits_tag_token_unique"),
        transaction.atomic(),
    ):
        FursuitTag.objects.create(fursuit=other, token=token, created_version=1)
