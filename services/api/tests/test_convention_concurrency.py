"""Real PostgreSQL serialization and lock-order acceptance tests for conventions."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from django.db import close_old_connections, connection

from accounts.models import User
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
def test_concurrent_active_enrollments_same_user_serialize_cleanly_and_leave_exactly_one_active() -> (
    None
):
    """Simultaneous set_active=True enrollments for the same user serialize without IntegrityError and leave exactly one active."""
    user = _setup_eligible_player("user_concurrent_enroll")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")
    start = Barrier(2)

    def enroll(con_id: int) -> int:
        close_old_connections()
        try:
            db_user = User.objects.get(pk=user.pk)
            client = force_authenticated_client(user=db_user)
            start.wait(timeout=10)
            response = client.post(
                "/api/conventions/enrollments/",
                {"convention_id": con_id, "set_active": True},
                content_type="application/json",
            )
            return response.status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        t1 = executor.submit(enroll, con1.pk)
        t2 = executor.submit(enroll, con2.pk)
        res1 = t1.result(timeout=15)
        res2 = t2.result(timeout=15)

    assert res1 in (200, 201)
    assert res2 in (200, 201)

    # Both enrollments must exist
    assert ConventionEnrollment.objects.filter(user=user).count() == 2
    # Exactly one enrollment is active
    assert ConventionEnrollment.objects.filter(user=user, is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_active_selections_same_user_serialize_cleanly_and_leave_exactly_one_active() -> (
    None
):
    """Simultaneous active selection switches for the same user serialize cleanly and leave exactly one active."""
    user = _setup_eligible_player("user_concurrent_switch")
    con1 = _create_convention(name="Con 1")
    con2 = _create_convention(name="Con 2")
    ConventionEnrollment.objects.create(user=user, convention=con1, is_active=False)
    ConventionEnrollment.objects.create(user=user, convention=con2, is_active=False)
    start = Barrier(2)

    def switch_active(con_id: int) -> Any:
        close_old_connections()
        try:
            db_user = User.objects.get(pk=user.pk)
            client = force_authenticated_client(user=db_user)
            start.wait(timeout=10)
            return client.put(
                "/api/conventions/active/",
                {"convention_id": con_id},
                content_type="application/json",
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        t1 = executor.submit(switch_active, con1.pk)
        t2 = executor.submit(switch_active, con2.pk)
        res1 = t1.result(timeout=15)
        res2 = t2.result(timeout=15)

    assert res1.status_code == 200
    assert res2.status_code == 200

    # Exactly one enrollment is active
    assert ConventionEnrollment.objects.filter(user=user, is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_disablement_committed_before_locked_validation_forbids_enrollment() -> None:
    """Disabling the player profile before transaction lock validation fails closed with 403."""
    user = _setup_eligible_player("user_toctou_disable")
    con = _create_convention()

    # Preflight / operator disablement occurs
    PlayerProfile.objects.filter(user=user).update(is_enabled=False)

    client = force_authenticated_client(user=user)
    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": con.pk},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not ConventionEnrollment.objects.filter(user=user).exists()


@pytest.mark.django_db(transaction=True)
def test_convention_paused_during_enrollment_is_rejected() -> None:
    """Selecting or enrolling in a convention that is paused is rejected with 400."""
    user = _setup_eligible_player("user_paused_race")
    con = _create_convention(status=ConventionStatus.PAUSED)

    client = force_authenticated_client(user=user)
    response = client.post(
        "/api/conventions/enrollments/",
        {"convention_id": con.pk},
        content_type="application/json",
    )
    assert response.status_code == 400
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
