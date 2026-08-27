"""Real PostgreSQL serialization and lock-order acceptance tests for conventions."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event, Lock
from time import monotonic, sleep
from typing import Any, cast

import pytest
from django.db import close_old_connections, connection, transaction
from django.db.models import QuerySet

from accounts.models import User
from conventions import services
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user, force_authenticated_client


def _record_call[**P, R](
    label: str, calls: list[str], function: Callable[P, R]
) -> Callable[P, R]:
    def recorded(*args: P.args, **kwargs: P.kwargs) -> R:
        calls.append(label)
        return function(*args, **kwargs)

    return recorded


_OBSERVER_TIMEOUT_SECONDS = 5.0
_HOLDER_GATE_TIMEOUT_SECONDS = 15.0
_SESSION_LOCK_TIMEOUT_MS = 18_000
_SESSION_STATEMENT_TIMEOUT_MS = 20_000
_FUTURE_RESULT_TIMEOUT_SECONDS = 25.0
_INITIAL_POLL_SECONDS = 0.005
_MAX_POLL_SECONDS = 0.050


def _configure_worker_session_and_get_pid() -> int:
    """Install bounded PostgreSQL settings on this fresh test-worker session."""
    with connection.cursor() as cursor:
        cursor.execute("SET lock_timeout TO 18000")
        cursor.execute("SET statement_timeout TO 20000")
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _request_in_bounded_worker(
    *,
    user_id: int,
    request: Callable[[Any], Any],
    backend_pids: Queue[int],
) -> Any:
    close_old_connections()
    try:
        backend_pids.put(_configure_worker_session_and_get_pid())
        db_user = User.objects.get(pk=user_id)
        return request(force_authenticated_client(user=db_user))
    finally:
        connection.close()


def _raise_if_worker_finished_early(
    future: Future[Any],
    *,
    expected: str,
) -> None:
    if not future.done():
        return
    try:
        result = future.result()
    except BaseException as exc:
        raise AssertionError(f"worker failed before {expected}") from exc
    status_code = getattr(result, "status_code", None)
    pytest.fail(
        f"worker completed before {expected}; response status was {status_code!r}"
    )


def _wait_for_pid_or_worker_finish(
    *,
    backend_pids: Queue[int],
    future: Future[Any],
    expected: str,
) -> int:
    deadline = monotonic() + _OBSERVER_TIMEOUT_SECONDS
    delay = _INITIAL_POLL_SECONDS
    while monotonic() < deadline:
        try:
            return backend_pids.get_nowait()
        except Empty:
            _raise_if_worker_finished_early(future, expected=expected)
            sleep(delay)
            delay = min(delay * 2, _MAX_POLL_SECONDS)
    _raise_if_worker_finished_early(future, expected=expected)
    pytest.fail(f"worker did not publish a backend PID before {expected}")


def _wait_for_event_or_worker_finish(
    *,
    event: Event,
    future: Future[Any],
    expected: str,
) -> None:
    deadline = monotonic() + _OBSERVER_TIMEOUT_SECONDS
    delay = _INITIAL_POLL_SECONDS
    while monotonic() < deadline:
        if event.is_set():
            return
        _raise_if_worker_finished_early(future, expected=expected)
        sleep(delay)
        delay = min(delay * 2, _MAX_POLL_SECONDS)
    _raise_if_worker_finished_early(future, expected=expected)
    pytest.fail(f"worker did not reach {expected}")


def _assert_backend_blocked_by(
    *, waiter_pid: int, holder_pid: int, worker: Future[Any]
) -> None:
    deadline = monotonic() + _OBSERVER_TIMEOUT_SECONDS
    delay = _INITIAL_POLL_SECONDS
    while monotonic() < deadline:
        _raise_if_worker_finished_early(
            worker,
            expected="the expected profile-row lock block",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s = ANY(pg_blocking_pids(%s))",
                [holder_pid, waiter_pid],
            )
            row = cursor.fetchone()
        assert row is not None
        if bool(row[0]):
            return
        sleep(delay)
        delay = min(delay * 2, _MAX_POLL_SECONDS)
    _raise_if_worker_finished_early(
        worker,
        expected="the expected profile-row lock block",
    )
    pytest.fail(f"PostgreSQL backend {waiter_pid} was not blocked by {holder_pid}")


def _assert_blocked_by_holder_before_downstream(
    *,
    waiter_pid: int,
    holder_pid: int,
    downstream_reached: Event,
    worker: Future[Any],
) -> None:
    """Require an explicit SQL block before enrollment reaches its insert seam."""
    deadline = monotonic() + _OBSERVER_TIMEOUT_SECONDS
    delay = _INITIAL_POLL_SECONDS
    while monotonic() < deadline:
        if downstream_reached.is_set():
            pytest.fail(
                "enrollment reached ConventionEnrollment.get_or_create before "
                "the pause holder released the Convention row lock"
            )
        _raise_if_worker_finished_early(
            worker,
            expected="the expected Convention-row lock block",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s = ANY(pg_blocking_pids(%s))",
                [holder_pid, waiter_pid],
            )
            row = cursor.fetchone()
        assert row is not None
        if bool(row[0]):
            if downstream_reached.is_set():
                pytest.fail(
                    "observed only a post-downstream lock, not the required "
                    "pre-insert Convention row lock"
                )
            return
        sleep(delay)
        delay = min(delay * 2, _MAX_POLL_SECONDS)
    _raise_if_worker_finished_early(
        worker,
        expected="the expected Convention-row lock block",
    )
    if downstream_reached.is_set():
        pytest.fail(
            "enrollment reached the downstream insert seam without first "
            "blocking on the pause holder"
        )
    pytest.fail(
        f"PostgreSQL backend {waiter_pid} was not blocked by {holder_pid} "
        "before the downstream enrollment seam"
    )


def _cancel_if_unfinished(
    *, future: Future[Any] | None, backend_pid: int | None
) -> None:
    if future is None or future.done() or backend_pid is None:
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_cancel_backend(%s)", [backend_pid])


def _pause_first_downstream_call[**P, R](
    function: Callable[P, R],
) -> tuple[Callable[P, R], Event, Event]:
    """Pause only the first invocation immediately before `function` runs."""
    first_call_guard = Lock()
    first_call = True
    first_at_downstream_seam = Event()
    release_first = Event()

    def paused(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal first_call
        with first_call_guard:
            pause_this_call = first_call
            first_call = False
        if pause_this_call:
            first_at_downstream_seam.set()
            if not release_first.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                raise TimeoutError("first downstream request was never released")
        return function(*args, **kwargs)

    return paused, first_at_downstream_seam, release_first


def _setup_eligible_player(clerk_id: str) -> User:
    """Create an authenticated, onboarding-complete, enabled user."""
    user = create_test_user(clerk_user_id=clerk_id)
    PlayerProfile.objects.create(
        user=user,
        handle=clerk_id,
        display_name=f"Player {clerk_id}",
        is_enabled=True,
        onboarding_completed_at=datetime.datetime.now(datetime.UTC),
    )
    return user


def _create_convention(
    name: str = "Test Con", status: str = ConventionStatus.ACTIVE
) -> Convention:
    return Convention.objects.create(
        name=name,
        status=status,
        start_date=datetime.date(2026, 8, 1),
        end_date=datetime.date(2026, 8, 5),
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_enrollments_same_user_serialize_cleanly_and_leave_exactly_one_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simultaneous set_active=True enrollments for the same user serialize without IntegrityError and leave exactly one active."""
    user = _setup_eligible_player("user_concurrent_enroll")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")
    backend_pids: Queue[int] = Queue()
    original_get_or_create = cast(
        Callable[..., tuple[ConventionEnrollment, bool]],
        ConventionEnrollment.objects.get_or_create,
    )
    gated_get_or_create, first_at_enrollment_create, release_first = (
        _pause_first_downstream_call(original_get_or_create)
    )
    monkeypatch.setattr(
        ConventionEnrollment.objects,
        "get_or_create",
        cast(Any, gated_get_or_create),
    )

    def enroll(con_id: int) -> Any:
        return _request_in_bounded_worker(
            user_id=user.pk,
            backend_pids=backend_pids,
            request=lambda client: client.post(
                "/api/conventions/enrollments/",
                {"convention_id": con_id, "set_active": True},
                content_type="application/json",
            ),
        )

    first: Future[Any] | None = None
    second: Future[Any] | None = None
    first_pid: int | None = None
    second_pid: int | None = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first = executor.submit(enroll, con1.pk)
            first_pid = _wait_for_pid_or_worker_finish(
                backend_pids=backend_pids,
                future=first,
                expected="the first enrollment request setup",
            )
            _wait_for_event_or_worker_finish(
                event=first_at_enrollment_create,
                future=first,
                expected="the first enrollment downstream gate",
            )
            second = executor.submit(enroll, con2.pk)
            second_pid = _wait_for_pid_or_worker_finish(
                backend_pids=backend_pids,
                future=second,
                expected="the second enrollment request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
                worker=second,
            )
            release_first.set()
            assert first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code in (
                200,
                201,
            )
            assert second.result(
                timeout=_FUTURE_RESULT_TIMEOUT_SECONDS
            ).status_code in (200, 201)
        finally:
            release_first.set()
            _cancel_if_unfinished(future=first, backend_pid=first_pid)
            _cancel_if_unfinished(future=second, backend_pid=second_pid)

    # Both enrollments must exist
    assert ConventionEnrollment.objects.filter(user=user).count() == 2
    # Exactly one enrollment is active
    assert ConventionEnrollment.objects.filter(user=user, is_active=True).count() == 1
    assert ConventionEnrollment.objects.filter(user=user, is_active=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_selections_same_user_serialize_cleanly_and_leave_exactly_one_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simultaneous active selection switches for the same user serialize cleanly and leave exactly one active."""
    user = _setup_eligible_player("user_concurrent_switch")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")
    ConventionEnrollment.objects.create(user=user, convention=con1, is_active=False)
    ConventionEnrollment.objects.create(user=user, convention=con2, is_active=False)
    backend_pids: Queue[int] = Queue()
    original_target_lookup = cast(
        Callable[..., QuerySet[ConventionEnrollment]],
        ConventionEnrollment.objects.select_for_update,
    )
    gated_target_lookup, first_at_target_lookup, release_first = (
        _pause_first_downstream_call(original_target_lookup)
    )
    monkeypatch.setattr(
        ConventionEnrollment.objects,
        "select_for_update",
        cast(Any, gated_target_lookup),
    )

    def switch_active(con_id: int) -> Any:
        return _request_in_bounded_worker(
            user_id=user.pk,
            backend_pids=backend_pids,
            request=lambda client: client.put(
                "/api/conventions/active/",
                {"convention_id": con_id},
                content_type="application/json",
            ),
        )

    first: Future[Any] | None = None
    second: Future[Any] | None = None
    first_pid: int | None = None
    second_pid: int | None = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first = executor.submit(switch_active, con1.pk)
            first_pid = _wait_for_pid_or_worker_finish(
                backend_pids=backend_pids,
                future=first,
                expected="the first selection request setup",
            )
            _wait_for_event_or_worker_finish(
                event=first_at_target_lookup,
                future=first,
                expected="the first selection downstream gate",
            )
            second = executor.submit(switch_active, con2.pk)
            second_pid = _wait_for_pid_or_worker_finish(
                backend_pids=backend_pids,
                future=second,
                expected="the second selection request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
                worker=second,
            )
            release_first.set()
            assert (
                first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code == 200
            )
            assert (
                second.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code == 200
            )
        finally:
            release_first.set()
            _cancel_if_unfinished(future=first, backend_pid=first_pid)
            _cancel_if_unfinished(future=second, backend_pid=second_pid)

    # Exactly one enrollment is active
    assert ConventionEnrollment.objects.filter(user=user, is_active=True).count() == 1
    assert ConventionEnrollment.objects.filter(user=user, is_active=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_disablement_committed_before_locked_validation_forbids_enrollment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabling the player profile before transaction lock validation fails closed with 403."""
    user = _setup_eligible_player("user_toctou_disable")
    con = _create_convention()

    preflight_passed = Event()
    release_after_disable = Event()
    original_preflight = services.require_convention_participation_eligible

    def pause_after_preflight(db_user: User) -> None:
        original_preflight(db_user)
        preflight_passed.set()
        if not release_after_disable.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
            raise TimeoutError("enrollment was never resumed after disablement")

    backend_pids: Queue[int] = Queue()

    def enroll() -> Any:
        return _request_in_bounded_worker(
            user_id=user.pk,
            backend_pids=backend_pids,
            request=lambda client: client.post(
                "/api/conventions/enrollments/",
                {"convention_id": con.pk},
                content_type="application/json",
            ),
        )

    monkeypatch.setattr(
        services,
        "require_convention_participation_eligible",
        pause_after_preflight,
    )

    enrollment: Future[Any] | None = None
    enrollment_pid: int | None = None
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            enrollment = executor.submit(enroll)
            enrollment_pid = _wait_for_pid_or_worker_finish(
                backend_pids=backend_pids,
                future=enrollment,
                expected="the enrollment request setup",
            )
            _wait_for_event_or_worker_finish(
                event=preflight_passed,
                future=enrollment,
                expected="the successful enrollment preflight",
            )
            with transaction.atomic():
                assert (
                    PlayerProfile.objects.filter(user=user).update(is_enabled=False)
                    == 1
                )
            release_after_disable.set()
            assert (
                enrollment.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == 403
            )
        finally:
            release_after_disable.set()
            _cancel_if_unfinished(future=enrollment, backend_pid=enrollment_pid)

    assert not ConventionEnrollment.objects.filter(user=user).exists()


@pytest.mark.django_db(transaction=True)
def test_convention_paused_during_enrollment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting or enrolling in a convention that is paused is rejected with 400."""
    user = _setup_eligible_player("user_paused_race")
    con = _create_convention(status=ConventionStatus.ACTIVE)
    original_get_or_create = cast(
        Callable[..., tuple[ConventionEnrollment, bool]],
        ConventionEnrollment.objects.get_or_create,
    )
    gated_get_or_create, downstream_reached, release_downstream = (
        _pause_first_downstream_call(original_get_or_create)
    )
    monkeypatch.setattr(
        ConventionEnrollment.objects,
        "get_or_create",
        cast(Any, gated_get_or_create),
    )
    pause_row_updated = Event()
    release_pause = Event()
    pause_pids: Queue[int] = Queue()
    enrollment_pids: Queue[int] = Queue()

    def pause_convention() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                pause_pids.put(_configure_worker_session_and_get_pid())
                locked_convention = Convention.objects.select_for_update().get(
                    pk=con.pk
                )
                locked_convention.status = ConventionStatus.PAUSED
                locked_convention.save(update_fields=["status", "updated_at"])
                pause_row_updated.set()
                if not release_pause.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                    raise TimeoutError("pause transaction was never released")
        finally:
            connection.close()

    def enroll() -> Any:
        return _request_in_bounded_worker(
            user_id=user.pk,
            backend_pids=enrollment_pids,
            request=lambda client: client.post(
                "/api/conventions/enrollments/",
                {"convention_id": con.pk},
                content_type="application/json",
            ),
        )

    pause: Future[Any] | None = None
    enrollment: Future[Any] | None = None
    pause_pid: int | None = None
    enrollment_pid: int | None = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            pause = executor.submit(pause_convention)
            pause_pid = _wait_for_pid_or_worker_finish(
                backend_pids=pause_pids,
                future=pause,
                expected="the pause transaction setup",
            )
            _wait_for_event_or_worker_finish(
                event=pause_row_updated,
                future=pause,
                expected="the uncommitted PAUSED Convention update",
            )

            enrollment = executor.submit(enroll)
            enrollment_pid = _wait_for_pid_or_worker_finish(
                backend_pids=enrollment_pids,
                future=enrollment,
                expected="the enrollment request setup",
            )
            _assert_blocked_by_holder_before_downstream(
                waiter_pid=enrollment_pid,
                holder_pid=pause_pid,
                downstream_reached=downstream_reached,
                worker=enrollment,
            )

            release_pause.set()
            assert pause.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
            assert (
                enrollment.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == 400
            )
        finally:
            release_pause.set()
            release_downstream.set()
            _cancel_if_unfinished(future=pause, backend_pid=pause_pid)
            _cancel_if_unfinished(future=enrollment, backend_pid=enrollment_pid)

    con.refresh_from_db()
    assert con.status == ConventionStatus.PAUSED
    assert not ConventionEnrollment.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_enrollment_transactions_lock_profile_before_convention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify lock acquisition hierarchy orders PlayerProfile before Convention."""
    user = _setup_eligible_player("user_lock_order")
    con = _create_convention()
    order: list[str] = []

    profile_lock = PlayerProfile.objects.select_for_update
    convention_lock = Convention.objects.select_for_update

    record_profile_lock = _record_call("profile", order, profile_lock)
    record_convention_lock = _record_call("convention", order, convention_lock)

    monkeypatch.setattr(PlayerProfile.objects, "select_for_update", record_profile_lock)
    monkeypatch.setattr(Convention.objects, "select_for_update", record_convention_lock)

    client = force_authenticated_client(user=user)
    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": con.pk},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert order[:2] == ["profile", "convention"]
