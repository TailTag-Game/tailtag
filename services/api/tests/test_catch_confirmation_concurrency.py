"""Real PostgreSQL races for authoritative Catch confirmation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from threading import Barrier, Event
from time import monotonic, sleep
from typing import Any

import pytest
from catches.services import (
    CatchActiveConventionMismatchError,
    CatchConfirmationStatus,
    CatchParticipationIneligibleError,
    CatchTargetInvalidError,
    confirm_catch,
)
from django.db import IntegrityError, close_old_connections, connection, transaction

from accounts.models import User
from catches import services as catch_services
from conventions.catch_credentials import (
    revoke_catch_credential_as_operator,
    rotate_owner_catch_credential,
)
from conventions.catch_sessions import set_fursuit_catch_session_state
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from conventions.services import (
    clear_active_convention,
    remove_convention_enrollment,
    set_convention_admin_state,
    set_fursuit_activation_state,
)
from fursuits.models import Fursuit
from fursuits.services import set_fursuit_enabled
from profiles.models import PlayerProfile
from profiles.services import set_profile_enabled
from tests.catch_credential_test_support import TOKEN_B, create_credential
from tests.catch_test_support import catch_model, create_catch_confirmation_scenario
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session

_LOCK_TIMEOUT = "18000ms"
_STATEMENT_TIMEOUT = "20000ms"
_FUTURE_TIMEOUT = 25.0
_OBSERVE_TIMEOUT = 5.0


def _configure_worker() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', %s, false)", [_LOCK_TIMEOUT])
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, false)", [_STATEMENT_TIMEOUT]
        )
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _worker(action: Callable[[], Any], pids: Queue[int]) -> Any:
    """Run one participant on its own bounded PostgreSQL connection."""
    close_old_connections()
    try:
        pids.put(_configure_worker())
        return action()
    finally:
        connection.close()


def _pid(queue: Queue[int], future: Future[Any]) -> int:
    deadline = monotonic() + _OBSERVE_TIMEOUT
    while monotonic() < deadline:
        try:
            return queue.get_nowait()
        except Empty:
            if future.done():
                pytest.fail(f"worker completed before lock evidence: {future.result()!r}")
            sleep(0.01)
    pytest.fail("worker did not publish a PostgreSQL backend PID")


def _assert_blocked(*, waiter: int, holder: int, future: Future[Any]) -> None:
    deadline = monotonic() + _OBSERVE_TIMEOUT
    while monotonic() < deadline:
        if future.done():
            pytest.fail(f"worker completed before lock evidence: {future.result()!r}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [holder, waiter])
            row = cursor.fetchone()
        assert row is not None
        if bool(row[0]):
            return
        sleep(0.01)
    pytest.fail(f"backend {waiter} was not blocked behind holder {holder}")


def _assert_blocked_behind_chain(
    *, waiter: int, holder: int, predecessor: int, future: Future[Any]
) -> None:
    deadline = monotonic() + _OBSERVE_TIMEOUT
    while monotonic() < deadline:
        if future.done():
            pytest.fail("second participant completed before serialized lock evidence")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_blocking_pids(%s), pg_blocking_pids(%s)",
                [waiter, predecessor],
            )
            row = cursor.fetchone()
        assert row is not None
        blockers, predecessor_blockers = map(set, row)
        if holder in blockers or (
            predecessor in blockers and holder in predecessor_blockers
        ):
            return
        sleep(0.01)
    pytest.fail("second participant did not join the intended PostgreSQL lock chain")


def _run_forced_order(
    *,
    lock: Callable[[], Any],
    first: Callable[[], Any],
    second: Callable[[], Any],
) -> tuple[Any, Any]:
    """Force a serial order with a real held row and observed blocker chain."""
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            held = lock()
            assert held.pk
            holder_pid = _configure_worker()
            first_future = pool.submit(_worker, first, first_pids)
            first_pid = _pid(first_pids, first_future)
            _assert_blocked(waiter=first_pid, holder=holder_pid, future=first_future)
            second_future = pool.submit(_worker, second, second_pids)
            second_pid = _pid(second_pids, second_future)
            _assert_blocked_behind_chain(
                waiter=second_pid,
                holder=holder_pid,
                predecessor=first_pid,
                future=second_future,
            )
        return (
            first_future.result(timeout=_FUTURE_TIMEOUT),
            second_future.result(timeout=_FUTURE_TIMEOUT),
        )


def _confirmation(scenario: Any) -> Any:
    user = User.objects.get(pk=scenario.catcher_user.pk)
    return confirm_catch(user, payload=scenario.payload)


def _assert_serial_lifecycle_outcome(
    *, scenario: Any, catch_first: bool, results: tuple[Any, Any]
) -> None:
    catch_result = results[0] if catch_first else results[1]
    if catch_first:
        assert catch_result.status is CatchConfirmationStatus.CREATED
        assert catch_model().objects.count() == 1
    else:
        assert catch_model().objects.count() == 0
        assert isinstance(
            catch_result,
            (
                CatchTargetInvalidError,
                CatchParticipationIneligibleError,
                CatchActiveConventionMismatchError,
            ),
        )
    assert not any(isinstance(result, (IntegrityError, TimeoutError)) for result in results)


def _confirmation_outcome(scenario: Any) -> Any:
    try:
        return _confirmation(scenario)
    except (
        CatchTargetInvalidError,
        CatchParticipationIneligibleError,
        CatchActiveConventionMismatchError,
    ) as error:
        return error


def _mutation_for(scenario: Any, operation: str) -> tuple[Callable[[], Any], Callable[[], Any]]:
    """Return the real lifecycle write and its earliest shared-row lock."""
    if operation == "credential_rotation":
        return (
            lambda: rotate_owner_catch_credential(
                User.objects.get(pk=scenario.target_user.pk),
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
            ),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.target_profile.pk),
        )
    if operation == "credential_operator_revocation":
        return (
            lambda: revoke_catch_credential_as_operator(scenario.credential.pk),
            lambda: FursuitActivation.objects.select_for_update().get(pk=scenario.activation.pk),
        )
    if operation == "session_stop":
        return (
            lambda: set_fursuit_catch_session_state(
                User.objects.get(pk=scenario.target_user.pk),
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                is_active=False,
            ),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.target_profile.pk),
        )
    if operation == "activation_deactivation":
        return (
            lambda: set_fursuit_activation_state(
                User.objects.get(pk=scenario.target_user.pk),
                convention_id=scenario.convention.pk,
                fursuit_id=scenario.fursuit.pk,
                is_active=False,
            ),
            lambda: Fursuit.objects.select_for_update().get(pk=scenario.fursuit.pk),
        )
    if operation == "target_profile_disablement":
        return (
            lambda: set_profile_enabled(profile_id=scenario.target_profile.pk, is_enabled=False),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.target_profile.pk),
        )
    if operation == "catcher_profile_disablement":
        return (
            lambda: set_profile_enabled(profile_id=scenario.catcher_profile.pk, is_enabled=False),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.catcher_profile.pk),
        )
    if operation == "fursuit_disablement":
        return (
            lambda: set_fursuit_enabled(fursuit_id=scenario.fursuit.pk, is_enabled=False),
            lambda: Fursuit.objects.select_for_update().get(pk=scenario.fursuit.pk),
        )
    if operation == "target_enrollment_removal":
        return (
            lambda: remove_convention_enrollment(enrollment_id=scenario.target_enrollment.pk),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.target_profile.pk),
        )
    if operation == "catcher_enrollment_removal":
        return (
            lambda: remove_convention_enrollment(enrollment_id=scenario.catcher_enrollment.pk),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.catcher_profile.pk),
        )
    if operation == "catcher_active_convention_clear":
        return (
            lambda: clear_active_convention(User.objects.get(pk=scenario.catcher_user.pk)),
            lambda: PlayerProfile.objects.select_for_update().get(pk=scenario.catcher_profile.pk),
        )
    if operation == "convention_paused":
        return (
            lambda: set_convention_admin_state(
                convention_id=scenario.convention.pk,
                name=scenario.convention.name,
                status=ConventionStatus.PAUSED,
                start_date=scenario.convention.start_date,
                end_date=scenario.convention.end_date,
            ),
            lambda: Convention.objects.select_for_update().get(pk=scenario.convention.pk),
        )
    raise AssertionError(f"unknown lifecycle operation: {operation}")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "operation",
    [
        "credential_rotation",
        "credential_operator_revocation",
        "session_stop",
        "activation_deactivation",
        "target_profile_disablement",
        "catcher_profile_disablement",
        "fursuit_disablement",
        "target_enrollment_removal",
        "catcher_enrollment_removal",
        "catcher_active_convention_clear",
        "convention_paused",
    ],
)
@pytest.mark.parametrize("catch_first", [True, False])
def test_confirm_catch_and_every_lifecycle_mutation_have_a_valid_serial_outcome(
    operation: str, catch_first: bool
) -> None:
    """AC-09/15: reject a lifecycle race that creates after a winning mutation."""
    assert connection.vendor == "postgresql"
    scenario = create_catch_confirmation_scenario(
        catcher_clerk_user_id=f"race_catcher_{operation}_{catch_first}",
        target_owner_clerk_user_id=f"race_target_{operation}_{catch_first}",
    )
    mutation, lock = _mutation_for(scenario, operation)
    results = _run_forced_order(
        lock=lock,
        first=(lambda: _confirmation_outcome(scenario)) if catch_first else mutation,
        second=mutation if catch_first else (lambda: _confirmation_outcome(scenario)),
    )
    _assert_serial_lifecycle_outcome(
        scenario=scenario, catch_first=catch_first, results=results
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_canonical_confirmations_converge_on_one_unchanged_catch() -> None:
    """AC-11/13/15: reject duplicate services that create two rows or rewrite provenance."""
    assert connection.vendor == "postgresql"
    scenario = create_catch_confirmation_scenario()
    barrier = Barrier(2)
    pids: Queue[int] = Queue()

    def confirm_after_barrier() -> Any:
        barrier.wait(timeout=10)
        return _confirmation(scenario)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, confirm_after_barrier, pids) for _ in range(2)]
        results = [future.result(timeout=_FUTURE_TIMEOUT) for future in futures]

    assert {result.catch.pk for result in results} == {results[0].catch.pk}
    assert sorted(result.status.value for result in results) == ["already_caught", "created"]
    row = catch_model().objects.values().get(pk=results[0].catch.pk)
    assert catch_model().objects.count() == 1
    assert row["activation_id"] == scenario.activation.pk
    assert row["catch_session_id"] == scenario.catch_session.pk
    assert row["caught_at"] == results[0].catch.caught_at


@pytest.mark.django_db(transaction=True)
def test_named_duplicate_constraint_recovers_the_raw_competing_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14/15: reject string matching or broad IntegrityError duplicate recovery."""
    assert connection.vendor == "postgresql"
    scenario = create_catch_confirmation_scenario()
    inspected, resume = Event(), Event()

    def pause_after_inspection() -> None:
        inspected.set()
        assert resume.wait(timeout=10), "duplicate competitor was never committed"

    monkeypatch.setattr(catch_services, "_after_existing_catch_inspection", pause_after_inspection)
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_worker, lambda: _confirmation(scenario), pids)
        _pid(pids, future)
        assert inspected.wait(timeout=10)
        winner = catch_model().objects.create(
            catcher_user=scenario.catcher_user,
            fursuit=scenario.fursuit,
            convention=scenario.convention,
            activation=scenario.activation,
            catch_session=scenario.catch_session,
        )
        original = catch_model().objects.values().get(pk=winner.pk)
        resume.set()
        result = future.result(timeout=_FUTURE_TIMEOUT)

    assert result.status is CatchConfirmationStatus.ALREADY_CAUGHT
    assert result.catch.pk == winner.pk
    assert catch_model().objects.values().get(pk=winner.pk) == original


@pytest.mark.django_db(transaction=True)
def test_reciprocal_confirmations_create_two_catches_without_deadlock() -> None:
    """AC-09/15: reject caller-target profile locking that deadlocks reciprocal catches."""
    assert connection.vendor == "postgresql"
    first = create_catch_confirmation_scenario()
    ConventionEnrollment.objects.filter(pk=first.target_enrollment.pk).update(is_active=True)
    owner_fursuit = Fursuit.objects.create(
        owner=first.catcher_user,
        name="Reciprocal Catcher Fursuit",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
        is_enabled=True,
    )
    owner_activation = create_activation_row(
        fursuit=owner_fursuit, convention=first.convention, active=True
    )
    owner_credential = create_credential(activation=owner_activation, token=TOKEN_B)
    owner_session = create_catch_session(activation=owner_activation)
    payload = f"tailtag:catch:v1:{owner_credential.token}"
    barrier = Barrier(2)
    pids: Queue[int] = Queue()

    def a_to_b() -> Any:
        barrier.wait(timeout=10)
        return _confirmation(first)

    def b_to_a() -> Any:
        barrier.wait(timeout=10)
        return confirm_catch(User.objects.get(pk=first.target_user.pk), payload=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(_worker, a_to_b, pids)
        two = pool.submit(_worker, b_to_a, pids)
        results = [one.result(timeout=_FUTURE_TIMEOUT), two.result(timeout=_FUTURE_TIMEOUT)]

    assert [result.status for result in results] == [
        CatchConfirmationStatus.CREATED,
        CatchConfirmationStatus.CREATED,
    ]
    assert catch_model().objects.count() == 2
    assert catch_model().objects.filter(
        activation_id__in=(first.activation.pk, owner_activation.pk),
        catch_session_id__in=(first.catch_session.pk, owner_session.pk),
    ).count() == 2
