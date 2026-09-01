"""Real PostgreSQL lock-observed #118 catch-session race acceptance tests."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction
from django.urls import reverse
from django.utils import timezone

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


def _owner(*, user_id: int, convention_id: int, fursuit_id: int, active: bool) -> Any:
    user = User.objects.get(pk=user_id)
    return force_authenticated_client(user=user).put(
        catch_session_path(convention_id, fursuit_id),
        {"is_active": active},
        content_type="application/json",
    )


def _activation_state(
    *, user_id: int, convention_id: int, fursuit_id: int, active: bool
) -> Any:
    """Use Issue #117's owner activation route, not the catch-session route."""
    user = User.objects.get(pk=user_id)
    return force_authenticated_client(user=user).put(
        activation_detail_path(convention_id, fursuit_id),
        {"is_active": active},
        content_type="application/json",
    )


def _operator(*, user_id: int, session_id: int) -> Any:
    """The parent-approved `terminate` form control is a real admin UI seam."""
    user = User.objects.get(pk=user_id)
    client = force_authenticated_client(user=user)
    client.force_login(user)
    return client.post(
        reverse("admin:conventions_fursuitcatchsession_change", args=(session_id,)),
        {"terminate": "1"},
    )


# Delayed imports make missing #118 service behavior an ordinary RED failure.
def _fursuit_enabled(fursuit_id: int, value: bool) -> Any:
    from fursuits.services import set_fursuit_enabled

    return set_fursuit_enabled(fursuit_id=fursuit_id, is_enabled=value)


def _profile_enabled(profile_id: int, value: bool) -> Any:
    from profiles.services import set_profile_enabled

    return set_profile_enabled(profile_id=profile_id, is_enabled=value)


def _remove_enrollment(enrollment_id: int) -> Any:
    from conventions.services import remove_convention_enrollment

    return remove_convention_enrollment(enrollment_id=enrollment_id)


def _convention_admin_state(
    *,
    convention_id: int,
    name: str,
    status: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> Any:
    from conventions.services import set_convention_admin_state

    return set_convention_admin_state(
        convention_id=convention_id,
        name=name,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )


def _pid(queue: Queue[int], future: Future[Any]) -> int:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        try:
            return queue.get_nowait()
        except Empty:
            if future.done():
                pytest.fail(
                    f"worker completed before lock evidence: {future.result()!r}"
                )
            sleep(0.01)
    pytest.fail("worker did not publish a backend PID")


def _blocked(waiter: int, holder: int, future: Future[Any]) -> None:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        if future.done():
            pytest.fail(f"worker completed before lock evidence: {future.result()!r}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [holder, waiter])
            row = cursor.fetchone()
        assert row is not None
        if row[0]:
            return
        sleep(0.01)
    pytest.fail(f"backend {waiter} did not block behind holder {holder}")


def _race(
    lock: Callable[[], Any],
    first_action: Callable[[], Any],
    second_action: Callable[[], Any],
) -> tuple[Any, Any]:
    """The holder and pg_blocking_pids form the deterministic barrier; no sleep picks a winner."""
    one_pids: Queue[int] = Queue()
    two_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            holder = lock()
            holder_pid = _configured_pid()
            assert holder.pk
            one = pool.submit(_worker, first_action, one_pids)
            _blocked(_pid(one_pids, one), holder_pid, one)
            two = pool.submit(_worker, second_action, two_pids)
            _blocked(_pid(two_pids, two), holder_pid, two)
        return one.result(timeout=_RESULT_SECONDS), two.result(timeout=_RESULT_SECONDS)


def _rows(activation: FursuitActivation) -> list[Any]:
    rows = list(catch_session_model().objects.filter(activation=activation))
    assert sum(row.ended_at is None for row in rows) <= 1
    assert all(
        row.end_reason in {"owner", "operator", "eligibility_lost", "expired"}
        for row in rows
        if row.ended_at is not None
    )
    return rows


def _terminate_profile_disable_worker(profile_id: int, pids: Queue[int]) -> int:
    """Run the approved package-internal profile termination seam in one transaction."""
    from conventions.catch_sessions import terminate_for_profile_disable

    close_old_connections()
    try:
        with transaction.atomic():
            pids.put(_configured_pid())
            profile = PlayerProfile.objects.select_for_update().get(pk=profile_id)
            return terminate_for_profile_disable(profile, now=timezone.now())
    finally:
        connection.close()


def _terminate_enrollment_removal_worker(enrollment_id: int, pids: Queue[int]) -> int:
    """Run the approved package-internal enrollment termination seam in one transaction."""
    from conventions.catch_sessions import terminate_for_enrollment_removal

    close_old_connections()
    try:
        with transaction.atomic():
            pids.put(_configured_pid())
            enrollment = ConventionEnrollment.objects.select_for_update().get(
                pk=enrollment_id
            )
            return terminate_for_enrollment_removal(enrollment, now=timezone.now())
    finally:
        connection.close()


def _blocks_on_holder(waiter_pid: int, holder_pid: int, worker: Future[Any]) -> bool:
    """Observe whether the activation query locks an unrelated joined fursuit row."""
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s = ANY(pg_blocking_pids(%s))", [holder_pid, waiter_pid]
            )
            row = cursor.fetchone()
        assert row is not None
        if row[0]:
            return True
        if worker.done():
            return False
        sleep(0.01)
    pytest.fail("termination worker neither completed nor reached its activation query")


def _setup(name: str) -> tuple[Any, FursuitActivation]:
    scenario = create_activation_scenario(clerk_user_id=name)
    return scenario, create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("seam", ("profile", "enrollment"))
def test_multiscope_termination_does_not_lock_joined_fursuit_before_activation_session(
    seam: str,
) -> None:
    """AC-13: rejects implicit joined-Fursuit locks that violate frozen lock order."""
    scenario, activation = _setup(f"catch_join_lock_{seam}")
    session = create_catch_session(activation=activation)
    assert scenario.enrollment is not None
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            held_fursuit = Fursuit.objects.select_for_update().get(
                pk=scenario.fursuit.pk
            )
            holder_pid = _configured_pid()
            if seam == "profile":
                worker = executor.submit(
                    _terminate_profile_disable_worker, scenario.profile.pk, pids
                )
            else:
                worker = executor.submit(
                    _terminate_enrollment_removal_worker,
                    scenario.enrollment.pk,
                    pids,
                )
            worker_pid = _pid(pids, worker)
            blocked_on_fursuit = _blocks_on_holder(worker_pid, holder_pid, worker)
            del held_fursuit
        terminated = worker.result(timeout=_RESULT_SECONDS)
    assert not blocked_on_fursuit, (
        f"{seam} termination locked the joined Fursuit row before its "
        "activation/session traversal; use select_for_update(of=('self',))."
    )
    assert terminated == 1
    session.refresh_from_db()
    assert session.ended_at is not None and session.end_reason == "eligibility_lost"


def _start(s: Any) -> Callable[[], Any]:
    return lambda: _owner(
        user_id=s.user.pk,
        convention_id=s.convention.pk,
        fursuit_id=s.fursuit.pk,
        active=True,
    )


def _stop(s: Any) -> Callable[[], Any]:
    return lambda: _owner(
        user_id=s.user.pk,
        convention_id=s.convention.pk,
        fursuit_id=s.fursuit.pk,
        active=False,
    )


@pytest.mark.django_db(transaction=True)
def test_race_1_two_starts_create_exactly_one_unended_row() -> None:
    """AC-13 race 1: rejects unprotected duplicate first starts."""
    s, activation = _setup("catch_race_one")
    a, b = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _start(s),
        _start(s),
    )
    assert a.status_code == b.status_code == 200
    rows = _rows(activation)
    assert len(rows) == 1 and rows[0].ended_at is None


@pytest.mark.django_db(transaction=True)
def test_race_2_two_stops_have_one_owner_terminal_transition() -> None:
    """AC-12 race 2: rejects duplicate/incorrect terminal reasons."""
    s, activation = _setup("catch_race_two")
    session = create_catch_session(activation=activation)
    a, b = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _stop(s),
        _stop(s),
    )
    assert a.status_code == b.status_code == 200
    session.refresh_from_db()
    assert session.ended_at is not None and session.end_reason == "owner"
    assert len(_rows(activation)) == 1


@pytest.mark.django_db(transaction=True)
def test_race_3_start_and_stop_produce_only_owner_terminal_history_or_one_new_live_row() -> (
    None
):
    """AC-12 race 3: rejects stale start or a rewritten terminal row."""
    s, activation = _setup("catch_race_three")
    create_catch_session(activation=activation)
    a, b = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _start(s),
        _stop(s),
    )
    assert a.status_code == b.status_code == 200
    rows = _rows(activation)
    assert any(row.end_reason == "owner" for row in rows)
    assert all(row.end_reason in {None, "owner"} for row in rows)


@pytest.mark.django_db(transaction=True)
def test_race_4_restart_vs_lazy_expiration_finalization_creates_one_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04/06/13 race 4: rejects a restart that races lazy finalization incorrectly."""
    s, activation = _setup("catch_race_four")
    expiry = timezone.now()
    from conventions import services

    monkeypatch.setattr(services.timezone, "now", lambda: expiry)
    old = create_catch_session(
        activation=activation,
        started_at=expiry - CATCH_SESSION_LIFETIME,
        expires_at=expiry,
    )
    a, b = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _stop(s),
        _start(s),
    )
    assert a.status_code == b.status_code == 200
    old.refresh_from_db()
    rows = _rows(activation)
    assert (
        old.ended_at == expiry
        and old.end_reason == "expired"
        and len(rows) == 2
        and sum(row.ended_at is None for row in rows) == 1
    )


@pytest.mark.django_db(transaction=True)
def test_race_12_two_expired_restarts_finalize_once_and_create_one_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04/06/13 race 12: rejects duplicate replacement rows after expiry."""
    s, activation = _setup("catch_race_twelve")
    expiry = timezone.now()
    from conventions import services

    monkeypatch.setattr(services.timezone, "now", lambda: expiry)
    old = create_catch_session(
        activation=activation,
        started_at=expiry - CATCH_SESSION_LIFETIME,
        expires_at=expiry,
    )
    a, b = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _start(s),
        _start(s),
    )
    assert a.status_code == b.status_code == 200
    old.refresh_from_db()
    rows = _rows(activation)
    assert (
        old.ended_at == expiry
        and old.end_reason == "expired"
        and len(rows) == 2
        and sum(row.ended_at is None for row in rows) == 1
    )


@pytest.mark.django_db(transaction=True)
def test_race_5_owner_stop_vs_admin_termination_preserves_the_winning_reason() -> None:
    """AC-11/12 race 5: rejects owner/operator terminal overwrite."""
    s, activation = _setup("catch_race_five")
    session = create_catch_session(activation=activation)
    operator = User.objects.create_superuser(
        "catch_race_five_operator", password="password"
    )
    owner, admin = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _stop(s),
        lambda: _operator(user_id=operator.pk, session_id=session.pk),
    )
    assert owner.status_code == 200 and admin.status_code == 302
    session.refresh_from_db()
    assert session.ended_at is not None and session.end_reason in {"owner", "operator"}
    assert len(_rows(activation)) == 1


@pytest.mark.django_db(transaction=True)
def test_race_6_start_vs_owner_activation_deactivation_leaves_no_unended_session() -> (
    None
):
    """AC-10/13 race 6: rejects a start left catchable after durable deactivation."""
    s, activation = _setup("catch_race_six")
    start, deactivate = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        _start(s),
        lambda: _activation_state(
            user_id=s.user.pk,
            convention_id=s.convention.pk,
            fursuit_id=s.fursuit.pk,
            active=False,
        ),
    )
    assert start.status_code in {200, 400} and deactivate.status_code == 200
    activation.refresh_from_db()
    assert activation.is_active is False
    assert not any(row.ended_at is None for row in _rows(activation))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("label", "locker", "transition"),
    (
        ("7 fursuit", "fursuit", "fursuit"),
        ("8 profile", "profile", "profile"),
        ("9 enrollment", "enrollment", "enrollment"),
        ("10 Convention", "convention", "convention"),
    ),
)
def test_races_7_to_10_start_vs_each_real_eligibility_service_leaves_no_live_row(
    label: str, locker: str, transition: str
) -> None:
    """AC-09/13/14 races 7–10: rejects stale start after each upstream boundary."""
    s, activation = _setup(f"catch_race_{locker}")
    if locker == "fursuit":
        lock = lambda: Fursuit.objects.select_for_update().get(pk=s.fursuit.pk)
        operation = lambda: _fursuit_enabled(s.fursuit.pk, False)
    elif locker == "profile":
        lock = lambda: PlayerProfile.objects.select_for_update().get(pk=s.profile.pk)
        operation = lambda: _profile_enabled(s.profile.pk, False)
    elif locker == "enrollment":
        assert s.enrollment is not None
        lock = lambda: ConventionEnrollment.objects.select_for_update().get(
            pk=s.enrollment.pk
        )
        operation = lambda: _remove_enrollment(s.enrollment.pk)
    else:
        lock = lambda: Convention.objects.select_for_update().get(pk=s.convention.pk)
        operation = lambda: _convention_admin_state(
            convention_id=s.convention.pk,
            name=s.convention.name,
            status=ConventionStatus.PAUSED,
            start_date=s.convention.start_date,
            end_date=s.convention.end_date,
        )
    start, _ = _race(lock, _start(s), operation)
    assert start.status_code in {200, 400, 403}, label
    rows = _rows(activation)
    assert not any(row.ended_at is None for row in rows), label
    assert all(row.end_reason == "eligibility_lost" for row in rows), label


@pytest.mark.django_db(transaction=True)
def test_race_11_profile_restoration_vs_restart_never_resurrects_prior_session() -> (
    None
):
    """AC-09 race 11: rejects restore rewriting the historical terminal row."""
    s, activation = _setup("catch_race_eleven")
    now = timezone.now()
    prior = create_catch_session(
        activation=activation,
        started_at=now - CATCH_SESSION_LIFETIME,
        ended_at=now,
        end_reason="eligibility_lost",
    )
    s.profile.is_enabled = False
    s.profile.save(update_fields=["is_enabled"])
    restart, _ = _race(
        lambda: PlayerProfile.objects.select_for_update().get(pk=s.profile.pk),
        _start(s),
        lambda: _profile_enabled(s.profile.pk, True),
    )
    assert restart.status_code in {200, 403}
    s.profile.refresh_from_db()
    assert s.profile.is_enabled is True
    explicit_restart = _owner(
        user_id=s.user.pk,
        convention_id=s.convention.pk,
        fursuit_id=s.fursuit.pk,
        active=True,
    )
    assert explicit_restart.status_code == 200
    prior.refresh_from_db()
    assert prior.ended_at is not None and prior.end_reason == "eligibility_lost"
    assert len(_rows(activation)) == 2


@pytest.mark.django_db(transaction=True)
def test_race_13_eligibility_loss_at_expiration_boundary_keeps_expired_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04/09/12 race 13: rejects eligibility_lost relabeling of an expired row."""
    s, activation = _setup("catch_race_thirteen")
    expiry = timezone.now()
    from conventions import services

    monkeypatch.setattr(services.timezone, "now", lambda: expiry)
    session = create_catch_session(
        activation=activation,
        started_at=expiry - CATCH_SESSION_LIFETIME,
        expires_at=expiry,
    )
    stop, _ = _race(
        lambda: Fursuit.objects.select_for_update().get(pk=s.fursuit.pk),
        _stop(s),
        lambda: _fursuit_enabled(s.fursuit.pk, False),
    )
    assert stop.status_code == 200
    session.refresh_from_db()
    assert session.ended_at == expiry and session.end_reason == "expired"
    _rows(activation)
