"""Real PostgreSQL race acceptance tests for per-Convention fursuit activation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event, Lock
from time import monotonic, sleep
from typing import Any, Protocol, cast

import pytest
from django.db import close_old_connections, connection, transaction
from django.db.models import F
from django.db.models.signals import pre_save

from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import (
    activation_detail_path,
    assert_activation_data,
    create_activation_scenario,
)

_OBSERVER_TIMEOUT_SECONDS = 5.0
_HOLDER_GATE_TIMEOUT_SECONDS = 15.0
_FUTURE_RESULT_TIMEOUT_SECONDS = 25.0
_SESSION_LOCK_TIMEOUT_MS = 18_000
_SESSION_STATEMENT_TIMEOUT_MS = 20_000
_INITIAL_POLL_SECONDS = 0.005
_MAX_POLL_SECONDS = 0.050


class _SignalConnection(Protocol):
    """The narrow Django signal capability exercised by these race tests."""

    def connect(
        self,
        receiver: Callable[..., object],
        sender: object | None = None,
        weak: bool = True,
    ) -> None: ...

    def disconnect(
        self,
        receiver: Callable[..., object] | None = None,
        sender: object | None = None,
    ) -> bool | None: ...


def _configure_worker_session_and_get_pid() -> int:
    """Install bounded PostgreSQL settings on a fresh worker connection."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('lock_timeout', %s, false)",
            [f"{_SESSION_LOCK_TIMEOUT_MS}ms"],
        )
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            [f"{_SESSION_STATEMENT_TIMEOUT_MS}ms"],
        )
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _request_in_bounded_worker(
    *,
    user_id: int,
    convention_id: int,
    fursuit_id: int,
    is_active: bool,
    backend_pids: Queue[int],
) -> Any:
    close_old_connections()
    try:
        backend_pids.put(_configure_worker_session_and_get_pid())
        user = User.objects.get(pk=user_id)
        return force_authenticated_client(user=user).put(
            activation_detail_path(convention_id, fursuit_id),
            {"is_active": is_active},
            content_type="application/json",
        )
    finally:
        connection.close()


def _wait_for_pid_or_worker_finish(
    *, backend_pids: Queue[int], future: Future[Any], expected: str
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
    *, event: Event, future: Future[Any], expected: str
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


def _raise_if_worker_finished_early(future: Future[Any], *, expected: str) -> None:
    if not future.done():
        return
    try:
        result = future.result()
    except BaseException as exc:
        raise AssertionError(f"worker failed before {expected}") from exc
    pytest.fail(
        f"worker completed before {expected}; response status was "
        f"{getattr(result, 'status_code', None)!r}"
    )


def _assert_backend_blocked_by(
    *, waiter_pid: int, holder_pid: int, worker: Future[Any], expected: str
) -> None:
    deadline = monotonic() + _OBSERVER_TIMEOUT_SECONDS
    delay = _INITIAL_POLL_SECONDS
    while monotonic() < deadline:
        _raise_if_worker_finished_early(worker, expected=expected)
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
    _raise_if_worker_finished_early(worker, expected=expected)
    pytest.fail(f"PostgreSQL backend {waiter_pid} was not blocked by {holder_pid}")


def _cancel_if_unfinished(
    *, future: Future[Any] | None, backend_pid: int | None
) -> None:
    if future is None or future.done() or backend_pid is None:
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_cancel_backend(%s)", [backend_pid])


def _activation_request(
    *,
    scenario_user_id: int,
    convention_id: int,
    fursuit_id: int,
    backend_pids: Queue[int],
) -> Any:
    return _request_in_bounded_worker(
        user_id=scenario_user_id,
        convention_id=convention_id,
        fursuit_id=fursuit_id,
        is_active=True,
        backend_pids=backend_pids,
    )


@pytest.mark.django_db(transaction=True)
def test_simultaneous_first_activations_converge_to_one_active_relationship() -> None:
    """Two same-pair creates return success without an IntegrityError or duplicate row."""
    scenario = create_activation_scenario(clerk_user_id="activation_first_race")
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    first_save_entered, release_first_save = Event(), Event()
    first_save_guard = Lock()
    pause_first_save = True
    activation_pre_save = cast(_SignalConnection, pre_save)

    def pause_first_new_activation(
        *, sender: type[Any], instance: Any, **kwargs: Any
    ) -> None:
        nonlocal pause_first_save
        del sender, instance, kwargs
        with first_save_guard:
            pause_this_save = pause_first_save
            pause_first_save = False
        if not pause_this_save:
            return
        first_save_entered.set()
        if not release_first_save.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
            raise TimeoutError("first activation request was never released")

    first: Future[Any] | None = None
    second: Future[Any] | None = None
    first_pid: int | None = None
    second_pid: int | None = None
    activation_pre_save.connect(
        pause_first_new_activation, sender=FursuitActivation, weak=False
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=first_pids,
            )
            first_pid = _wait_for_pid_or_worker_finish(
                backend_pids=first_pids,
                future=first,
                expected="the first activation request setup",
            )
            _wait_for_event_or_worker_finish(
                event=first_save_entered,
                future=first,
                expected="the first activation after upstream locks",
            )
            second = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=second_pids,
            )
            second_pid = _wait_for_pid_or_worker_finish(
                backend_pids=second_pids,
                future=second,
                expected="the second activation request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
                worker=second,
                expected="the first activation transaction",
            )
            release_first_save.set()
            first_response = first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS)
            second_response = second.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS)
        finally:
            release_first_save.set()
            _cancel_if_unfinished(future=first, backend_pid=first_pid)
            _cancel_if_unfinished(future=second, backend_pid=second_pid)
            activation_pre_save.disconnect(
                pause_first_new_activation, sender=FursuitActivation
            )

    for response in (first_response, second_response):
        assert response.status_code == 200
        data = assert_activation_data(response.json())
        assert data["fursuit_id"] == scenario.fursuit.pk
        assert data["convention_id"] == scenario.convention.pk
        assert data["is_active"] is True
        assert data["deactivated_at"] is None
    rows = FursuitActivation.objects.filter(
        fursuit=scenario.fursuit, convention=scenario.convention
    )
    assert rows.count() == 1
    activation = rows.get()
    assert activation.is_active and activation.activated_at is not None
    assert activation.deactivated_at is None


def _hold_upstream_mutation(
    *,
    mutation: str,
    scenario_user_id: int,
    profile_id: int,
    convention_id: int,
    enrollment_id: int,
    fursuit_id: int,
    backend_pids: Queue[int],
    changed: Event,
    release: Event,
) -> None:
    close_old_connections()
    try:
        with transaction.atomic():
            backend_pids.put(_configure_worker_session_and_get_pid())
            if mutation == "profile":
                profile = PlayerProfile.objects.select_for_update().get(pk=profile_id)
                profile.is_enabled = False
                profile.save(update_fields=["is_enabled"])
            elif mutation == "convention":
                convention = Convention.objects.select_for_update().get(
                    pk=convention_id
                )
                convention.status = ConventionStatus.PAUSED
                convention.save(update_fields=["status", "updated_at"])
            elif mutation == "fursuit":
                fursuit = Fursuit.objects.select_for_update().get(pk=fursuit_id)
                fursuit.is_enabled = False
                fursuit.save(update_fields=["is_enabled", "updated_at"])
            else:
                enrollment = ConventionEnrollment.objects.select_for_update().get(
                    pk=enrollment_id, user_id=scenario_user_id
                )
                enrollment.delete()
            changed.set()
            if not release.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                raise TimeoutError("upstream mutation was never released")
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    (
        ("fursuit", 400),
        ("convention", 400),
        ("profile", 403),
        ("enrollment", 400),
    ),
)
def test_activation_waits_for_committed_upstream_mutation_then_rejects_stale_eligibility(
    mutation: str, expected_status: int
) -> None:
    """A committed upstream invalidation cannot be bypassed by a stale activation read."""
    scenario = create_activation_scenario(clerk_user_id=f"activation_{mutation}_race")
    assert scenario.enrollment is not None
    holder_pids: Queue[int] = Queue()
    activation_pids: Queue[int] = Queue()
    holder_changed, release_holder = Event(), Event()
    holder: Future[Any] | None = None
    activation: Future[Any] | None = None
    holder_pid: int | None = None
    activation_pid: int | None = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            holder = executor.submit(
                _hold_upstream_mutation,
                mutation=mutation,
                scenario_user_id=scenario.user.pk,
                profile_id=scenario.profile.pk,
                convention_id=scenario.convention.pk,
                enrollment_id=scenario.enrollment.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=holder_pids,
                changed=holder_changed,
                release=release_holder,
            )
            holder_pid = _wait_for_pid_or_worker_finish(
                backend_pids=holder_pids,
                future=holder,
                expected="the upstream mutation session setup",
            )
            _wait_for_event_or_worker_finish(
                event=holder_changed,
                future=holder,
                expected="the uncommitted upstream mutation",
            )
            activation = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=activation_pids,
            )
            activation_pid = _wait_for_pid_or_worker_finish(
                backend_pids=activation_pids,
                future=activation,
                expected="the activation request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=activation_pid,
                holder_pid=holder_pid,
                worker=activation,
                expected="the authoritative upstream row lock",
            )
            release_holder.set()
            assert holder.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
            assert (
                activation.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == expected_status
            )
        finally:
            release_holder.set()
            _cancel_if_unfinished(future=holder, backend_pid=holder_pid)
            _cancel_if_unfinished(future=activation, backend_pid=activation_pid)

    assert not FursuitActivation.objects.filter(
        fursuit=scenario.fursuit, convention=scenario.convention, is_active=True
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_activation_waits_for_convention_cancellation_then_rejects_stale_eligibility() -> (
    None
):
    """Cancellation is independently fail-closed, just like a Convention pause."""
    scenario = create_activation_scenario(clerk_user_id="activation_cancellation_race")
    holder_pids: Queue[int] = Queue()
    activation_pids: Queue[int] = Queue()
    changed, release = Event(), Event()

    def cancel_convention() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                holder_pids.put(_configure_worker_session_and_get_pid())
                convention = Convention.objects.select_for_update().get(
                    pk=scenario.convention.pk
                )
                convention.status = ConventionStatus.CANCELLED
                convention.save(update_fields=["status", "updated_at"])
                changed.set()
                if not release.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                    raise TimeoutError("cancellation transaction was never released")
        finally:
            connection.close()

    cancellation: Future[Any] | None = None
    activation: Future[Any] | None = None
    cancellation_pid: int | None = None
    activation_pid: int | None = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            cancellation = executor.submit(cancel_convention)
            cancellation_pid = _wait_for_pid_or_worker_finish(
                backend_pids=holder_pids,
                future=cancellation,
                expected="the cancellation transaction setup",
            )
            _wait_for_event_or_worker_finish(
                event=changed,
                future=cancellation,
                expected="the uncommitted cancellation",
            )
            activation = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=activation_pids,
            )
            activation_pid = _wait_for_pid_or_worker_finish(
                backend_pids=activation_pids,
                future=activation,
                expected="the activation request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=activation_pid,
                holder_pid=cancellation_pid,
                worker=activation,
                expected="the cancellation Convention row lock",
            )
            release.set()
            assert cancellation.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
            assert (
                activation.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == 400
            )
        finally:
            release.set()
            _cancel_if_unfinished(future=cancellation, backend_pid=cancellation_pid)
            _cancel_if_unfinished(future=activation, backend_pid=activation_pid)

    assert not FursuitActivation.objects.filter(
        fursuit=scenario.fursuit, convention=scenario.convention, is_active=True
    ).exists()


def _create_activation(*, scenario: Any, is_active: bool) -> FursuitActivation:
    from django.utils import timezone

    now = timezone.now()
    return FursuitActivation.objects.create(
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        is_active=is_active,
        activated_at=now,
        deactivated_at=None if is_active else now,
    )


def _hold_activation_row(
    *, activation_id: int, backend_pids: Queue[int], locked: Event, release: Event
) -> None:
    close_old_connections()
    try:
        with transaction.atomic():
            backend_pids.put(_configure_worker_session_and_get_pid())
            FursuitActivation.objects.select_for_update().get(pk=activation_id)
            locked.set()
            if not release.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                raise TimeoutError("activation-row holder was never released")
    finally:
        connection.close()


def _run_desired_state_race_under_activation_holder(
    *,
    scenario: Any,
    activation: FursuitActivation,
    first_state: bool,
    second_state: bool,
) -> tuple[Any, Any]:
    holder_pids: Queue[int] = Queue()
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    holder_locked, release_holder = Event(), Event()
    holder: Future[Any] | None = None
    first: Future[Any] | None = None
    second: Future[Any] | None = None
    holder_pid: int | None = None
    first_pid: int | None = None
    second_pid: int | None = None
    with ThreadPoolExecutor(max_workers=3) as executor:
        try:
            holder = executor.submit(
                _hold_activation_row,
                activation_id=activation.pk,
                backend_pids=holder_pids,
                locked=holder_locked,
                release=release_holder,
            )
            holder_pid = _wait_for_pid_or_worker_finish(
                backend_pids=holder_pids,
                future=holder,
                expected="the activation-row holder setup",
            )
            _wait_for_event_or_worker_finish(
                event=holder_locked,
                future=holder,
                expected="the held activation row",
            )
            first = executor.submit(
                _request_in_bounded_worker,
                user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                is_active=first_state,
                backend_pids=first_pids,
            )
            first_pid = _wait_for_pid_or_worker_finish(
                backend_pids=first_pids,
                future=first,
                expected="the first desired-state request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=first_pid,
                holder_pid=holder_pid,
                worker=first,
                expected="the externally held activation row",
            )
            second = executor.submit(
                _request_in_bounded_worker,
                user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                is_active=second_state,
                backend_pids=second_pids,
            )
            second_pid = _wait_for_pid_or_worker_finish(
                backend_pids=second_pids,
                future=second,
                expected="the second desired-state request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
                worker=second,
                expected="the first in-flight desired-state request",
            )
            release_holder.set()
            assert holder.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
            return (
                first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS),
                second.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS),
            )
        finally:
            release_holder.set()
            _cancel_if_unfinished(future=holder, backend_pid=holder_pid)
            _cancel_if_unfinished(future=first, backend_pid=first_pid)
            _cancel_if_unfinished(future=second, backend_pid=second_pid)


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_retries_preserve_existing_active_timestamps() -> None:
    scenario = create_activation_scenario(clerk_user_id="activation_active_retry_race")
    activation = _create_activation(scenario=scenario, is_active=True)
    before = (activation.activated_at, activation.deactivated_at, activation.updated_at)
    responses = _run_desired_state_race_under_activation_holder(
        scenario=scenario,
        activation=activation,
        first_state=True,
        second_state=True,
    )

    assert all(response.status_code == 200 for response in responses)
    assert (
        FursuitActivation.objects.filter(
            fursuit=scenario.fursuit, convention=scenario.convention
        ).count()
        == 1
    )
    activation.refresh_from_db()
    assert activation.is_active
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_and_inactive_requests_leave_only_real_transition_timestamps() -> (
    None
):
    scenario = create_activation_scenario(clerk_user_id="activation_mixed_desired_race")
    activation = _create_activation(scenario=scenario, is_active=False)
    original_activated_at = activation.activated_at
    responses = _run_desired_state_race_under_activation_holder(
        scenario=scenario,
        activation=activation,
        first_state=True,
        second_state=False,
    )

    assert all(response.status_code == 200 for response in responses)
    assert (
        FursuitActivation.objects.filter(
            fursuit=scenario.fursuit, convention=scenario.convention
        ).count()
        == 1
    )
    activation.refresh_from_db()
    assert activation.activated_at > original_activated_at
    if activation.is_active:
        assert activation.deactivated_at is None
    else:
        assert activation.deactivated_at is not None
        assert activation.deactivated_at >= activation.activated_at
    assert activation.updated_at >= activation.activated_at


@pytest.mark.django_db(transaction=True)
def test_concurrent_inactive_retries_preserve_existing_inactive_timestamps() -> None:
    scenario = create_activation_scenario(
        clerk_user_id="activation_inactive_retry_race"
    )
    activation = _create_activation(scenario=scenario, is_active=False)
    before = (activation.activated_at, activation.deactivated_at, activation.updated_at)
    responses = _run_desired_state_race_under_activation_holder(
        scenario=scenario,
        activation=activation,
        first_state=False,
        second_state=False,
    )

    assert all(response.status_code == 200 for response in responses)
    assert (
        FursuitActivation.objects.filter(
            fursuit=scenario.fursuit, convention=scenario.convention
        ).count()
        == 1
    )
    activation.refresh_from_db()
    assert not activation.is_active
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == before


def _hold_later_activation_lock(
    *, target: str, row_id: int, backend_pids: Queue[int], locked: Event, release: Event
) -> None:
    close_old_connections()
    try:
        with transaction.atomic():
            backend_pids.put(_configure_worker_session_and_get_pid())
            if target == "convention":
                Convention.objects.select_for_update().get(pk=row_id)
            elif target == "enrollment":
                ConventionEnrollment.objects.select_for_update().get(pk=row_id)
            elif target == "fursuit":
                Fursuit.objects.select_for_update().get(pk=row_id)
            else:
                FursuitActivation.objects.select_for_update().get(pk=row_id)
            locked.set()
            if not release.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                raise TimeoutError("later-row holder was never released")
    finally:
        connection.close()


def _observe_noop_update(*, target: str, row_id: int, backend_pids: Queue[int]) -> None:
    """Request a real PostgreSQL write lock while preserving every field value."""
    close_old_connections()
    try:
        with transaction.atomic():
            backend_pids.put(_configure_worker_session_and_get_pid())
            if target == "profile":
                field = "is_enabled"
                assert PlayerProfile._meta.get_field(field).name == field
                assert (
                    PlayerProfile.objects.filter(pk=row_id).update(**{field: F(field)})
                    == 1
                )
            elif target == "convention":
                field = "status"
                assert Convention._meta.get_field(field).name == field
                assert (
                    Convention.objects.filter(pk=row_id).update(**{field: F(field)})
                    == 1
                )
            elif target == "enrollment":
                field = "is_active"
                assert ConventionEnrollment._meta.get_field(field).name == field
                assert (
                    ConventionEnrollment.objects.filter(pk=row_id).update(
                        **{field: F(field)}
                    )
                    == 1
                )
            else:
                field = "is_enabled"
                assert Fursuit._meta.get_field(field).name == field
                assert (
                    Fursuit.objects.filter(pk=row_id).update(**{field: F(field)}) == 1
                )
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("later", "earlier"),
    (
        ("convention", "profile"),
        ("enrollment", "convention"),
        ("fursuit", "enrollment"),
        ("activation", "fursuit"),
    ),
)
def test_activation_acquires_each_adjacent_lock_in_frozen_order(
    later: str, earlier: str
) -> None:
    """Each earlier lock is held before activation can wait on its adjacent later row."""
    scenario = create_activation_scenario(clerk_user_id=f"activation_lock_{later}")
    assert scenario.enrollment is not None
    existing_activation = (
        _create_activation(scenario=scenario, is_active=False)
        if later == "activation"
        else None
    )
    later_row_id = {
        "convention": scenario.convention.pk,
        "enrollment": scenario.enrollment.pk,
        "fursuit": scenario.fursuit.pk,
        "activation": existing_activation.pk if existing_activation else None,
    }[later]
    earlier_row_id = {
        "profile": scenario.profile.pk,
        "convention": scenario.convention.pk,
        "enrollment": scenario.enrollment.pk,
        "fursuit": scenario.fursuit.pk,
    }[earlier]
    assert later_row_id is not None
    holder_pids: Queue[int] = Queue()
    activation_pids: Queue[int] = Queue()
    holder_locked, release_holder = Event(), Event()
    holder: Future[Any] | None = None
    activation: Future[Any] | None = None
    holder_pid: int | None = None
    activation_pid: int | None = None
    observer: Future[Any] | None = None
    observer_pid: int | None = None
    observer_pids: Queue[int] = Queue()

    with ThreadPoolExecutor(max_workers=3) as executor:
        try:
            holder = executor.submit(
                _hold_later_activation_lock,
                target=later,
                row_id=later_row_id,
                backend_pids=holder_pids,
                locked=holder_locked,
                release=release_holder,
            )
            holder_pid = _wait_for_pid_or_worker_finish(
                backend_pids=holder_pids,
                future=holder,
                expected=f"the held {later} row setup",
            )
            _wait_for_event_or_worker_finish(
                event=holder_locked,
                future=holder,
                expected=f"the held {later} row",
            )
            activation = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=activation_pids,
            )
            activation_pid = _wait_for_pid_or_worker_finish(
                backend_pids=activation_pids,
                future=activation,
                expected="the activation request setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=activation_pid,
                holder_pid=holder_pid,
                worker=activation,
                expected=f"the later {later} row lock",
            )
            observer = executor.submit(
                _observe_noop_update,
                target=earlier,
                row_id=earlier_row_id,
                backend_pids=observer_pids,
            )
            observer_pid = _wait_for_pid_or_worker_finish(
                backend_pids=observer_pids,
                future=observer,
                expected=f"the {earlier} no-op update observer setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=observer_pid,
                holder_pid=activation_pid,
                worker=observer,
                expected=f"the activation-held {earlier} row before {later}",
            )
            release_holder.set()
            assert holder.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
            assert (
                activation.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == 200
            )
            assert observer.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
        finally:
            release_holder.set()
            _cancel_if_unfinished(future=holder, backend_pid=holder_pid)
            _cancel_if_unfinished(future=activation, backend_pid=activation_pid)
            _cancel_if_unfinished(future=observer, backend_pid=observer_pid)


@pytest.mark.django_db(transaction=True)
def test_activation_committed_before_lifecycle_update_stays_active_but_becomes_ineligible() -> (
    None
):
    """An activation holding upstream locks wins legitimately; lifecycle state still wins eligibility."""
    scenario = create_activation_scenario(clerk_user_id="activation_first_lifecycle")
    activation_pids: Queue[int] = Queue()
    lifecycle_pids: Queue[int] = Queue()
    activation_saved, release_activation = Event(), Event()

    def pause_new_activation(
        *, sender: type[Any], instance: Any, **kwargs: Any
    ) -> None:
        del sender, instance, kwargs
        activation_saved.set()
        if not release_activation.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
            raise TimeoutError("activation request was never released")

    def pause_convention() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                lifecycle_pids.put(_configure_worker_session_and_get_pid())
                convention = Convention.objects.select_for_update().get(
                    pk=scenario.convention.pk
                )
                convention.status = ConventionStatus.PAUSED
                convention.save(update_fields=["status", "updated_at"])
        finally:
            connection.close()

    activation: Future[Any] | None = None
    lifecycle: Future[Any] | None = None
    activation_pid: int | None = None
    lifecycle_pid: int | None = None
    activation_pre_save = cast(_SignalConnection, pre_save)
    activation_pre_save.connect(
        pause_new_activation, sender=FursuitActivation, weak=False
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            activation = executor.submit(
                _activation_request,
                scenario_user_id=scenario.user.pk,
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                backend_pids=activation_pids,
            )
            activation_pid = _wait_for_pid_or_worker_finish(
                backend_pids=activation_pids,
                future=activation,
                expected="the activation request setup",
            )
            _wait_for_event_or_worker_finish(
                event=activation_saved,
                future=activation,
                expected="activation after its upstream locks",
            )
            lifecycle = executor.submit(pause_convention)
            lifecycle_pid = _wait_for_pid_or_worker_finish(
                backend_pids=lifecycle_pids,
                future=lifecycle,
                expected="the lifecycle update session setup",
            )
            _assert_backend_blocked_by(
                waiter_pid=lifecycle_pid,
                holder_pid=activation_pid,
                worker=lifecycle,
                expected="the activation-held Convention row lock",
            )
            release_activation.set()
            assert (
                activation.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
                == 200
            )
            assert lifecycle.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
        finally:
            release_activation.set()
            _cancel_if_unfinished(future=activation, backend_pid=activation_pid)
            _cancel_if_unfinished(future=lifecycle, backend_pid=lifecycle_pid)
            activation_pre_save.disconnect(
                pause_new_activation, sender=FursuitActivation
            )

    activation_row = FursuitActivation.objects.get(
        fursuit=scenario.fursuit, convention=scenario.convention
    )
    assert activation_row.is_active
    response = scenario.client.get(
        f"/api/conventions/{scenario.convention.pk}/fursuit-activations/"
    )
    assert response.status_code == 200
    data = assert_activation_data(response.json()[0])
    assert data["is_active"] is True
    assert data["is_eligible"] is False
