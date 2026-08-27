"""Real PostgreSQL serialization and lock-order acceptance tests for conventions."""

from __future__ import annotations

import datetime
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction

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


def _postgres_backend_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _assert_backend_blocked_by(
    *, waiter_pid: int, holder_pid: int, timeout: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s = ANY(pg_blocking_pids(%s))",
                [holder_pid, waiter_pid],
            )
            row = cursor.fetchone()
        assert row is not None
        if bool(row[0]):
            return
        if time.monotonic() >= deadline:
            pytest.fail(
                f"PostgreSQL backend {waiter_pid} was not blocked by {holder_pid}"
            )


def _gate_first_profile_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Event, Event]:
    first_holds_profile = Event()
    release_first = Event()
    original_locked_profile = services._locked_eligible_profile  # pyright: ignore[reportPrivateUsage]
    first_call = True

    def hold_first_profile_lock(db_user: User) -> PlayerProfile:
        nonlocal first_call
        profile = original_locked_profile(db_user)
        if first_call:
            first_call = False
            first_holds_profile.set()
            assert release_first.wait(10)
        return profile

    monkeypatch.setattr(
        services,
        "_locked_eligible_profile",
        hold_first_profile_lock,
    )
    return first_holds_profile, release_first


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
    first_holds_profile, release_first = _gate_first_profile_lock(monkeypatch)

    def enroll(con_id: int) -> int:
        close_old_connections()
        try:
            backend_pids.put(_postgres_backend_pid())
            db_user = User.objects.get(pk=user.pk)
            response = force_authenticated_client(user=db_user).post(
                "/api/conventions/enrollments/",
                {"convention_id": con_id, "set_active": True},
                content_type="application/json",
            )
            return response.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first = executor.submit(enroll, con1.pk)
            first_pid = backend_pids.get(timeout=10)
            assert first_holds_profile.wait(10)
            second = executor.submit(enroll, con2.pk)
            second_pid = backend_pids.get(timeout=10)
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
            )
            release_first.set()
            assert first.result(timeout=15) in (200, 201)
            assert second.result(timeout=15) in (200, 201)
        finally:
            release_first.set()

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
    first_holds_profile, release_first = _gate_first_profile_lock(monkeypatch)

    def switch_active(con_id: int) -> Any:
        close_old_connections()
        try:
            backend_pids.put(_postgres_backend_pid())
            db_user = User.objects.get(pk=user.pk)
            client = force_authenticated_client(user=db_user)
            return client.put(
                "/api/conventions/active/",
                {"convention_id": con_id},
                content_type="application/json",
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first = executor.submit(switch_active, con1.pk)
            first_pid = backend_pids.get(timeout=10)
            assert first_holds_profile.wait(10)
            second = executor.submit(switch_active, con2.pk)
            second_pid = backend_pids.get(timeout=10)
            _assert_backend_blocked_by(
                waiter_pid=second_pid,
                holder_pid=first_pid,
            )
            release_first.set()
            assert first.result(timeout=15).status_code == 200
            assert second.result(timeout=15).status_code == 200
        finally:
            release_first.set()

    # Exactly one enrollment is active
    assert ConventionEnrollment.objects.filter(user=user, is_active=True).count() == 1


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
        assert release_after_disable.wait(10)

    def enroll() -> int:
        close_old_connections()
        try:
            db_user = User.objects.get(pk=user.pk)
            return (
                force_authenticated_client(user=db_user)
                .post(
                    "/api/conventions/enrollments/",
                    {"convention_id": con.pk},
                    content_type="application/json",
                )
                .status_code
            )
        finally:
            connection.close()

    monkeypatch.setattr(
        services,
        "require_convention_participation_eligible",
        pause_after_preflight,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            request = executor.submit(enroll)
            assert preflight_passed.wait(10)
            with transaction.atomic():
                assert (
                    PlayerProfile.objects.filter(user=user).update(is_enabled=False)
                    == 1
                )
            release_after_disable.set()
            assert request.result(timeout=15) == 403
        finally:
            release_after_disable.set()

    assert not ConventionEnrollment.objects.filter(user=user).exists()


@pytest.mark.django_db(transaction=True)
def test_convention_paused_during_enrollment_is_rejected() -> None:
    """Selecting or enrolling in a convention that is paused is rejected with 400."""
    user = _setup_eligible_player("user_paused_race")
    con = _create_convention(status=ConventionStatus.ACTIVE)
    pause_row_updated = Event()
    commit_pause = Event()
    pause_backend_pids: Queue[int] = Queue()
    enrollment_backend_pids: Queue[int] = Queue()

    def pause_convention() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                pause_backend_pids.put(_postgres_backend_pid())
                locked_convention = Convention.objects.select_for_update().get(
                    pk=con.pk
                )
                locked_convention.status = ConventionStatus.PAUSED
                locked_convention.save(update_fields=["status", "updated_at"])
                pause_row_updated.set()
                assert commit_pause.wait(10)
        finally:
            connection.close()

    def enroll() -> int:
        close_old_connections()
        try:
            enrollment_backend_pids.put(_postgres_backend_pid())
            db_user = User.objects.get(pk=user.pk)
            return (
                force_authenticated_client(user=db_user)
                .post(
                    "/api/conventions/enrollments/",
                    {"convention_id": con.pk},
                    content_type="application/json",
                )
                .status_code
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            pause = executor.submit(pause_convention)
            pause_pid = pause_backend_pids.get(timeout=10)
            assert pause_row_updated.wait(10)

            enrollment = executor.submit(enroll)
            enrollment_pid = enrollment_backend_pids.get(timeout=10)
            _assert_backend_blocked_by(
                waiter_pid=enrollment_pid,
                holder_pid=pause_pid,
            )

            commit_pause.set()
            assert pause.result(timeout=15) is None
            assert enrollment.result(timeout=15) == 400
        finally:
            commit_pause.set()

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
