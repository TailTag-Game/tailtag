"""Shared seeding and state snapshots for simulation fixture provisioning tests."""

from __future__ import annotations

from typing import Any

from django.core.files.storage import default_storage
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from simulation_fixtures.models import FixtureObject, FixtureRun
from simulation_pool import services as pool_services
from simulation_pool.models import PoolSlot
from tests.authentication_support import create_test_user

POOL = "alpha"
RUN_A = "aaaaaaaa-1111-4111-8111-111111111111"
RUN_B = "bbbbbbbb-2222-4222-8222-222222222222"
OTHER_RUN = "99999999-9999-4999-8999-999999999999"


def create_pool_identity(pool: str, index: int) -> User:
    """Create the onboarded profile the #219 setup gives a pool identity."""
    user = create_test_user()
    PlayerProfile.objects.create(
        user=user,
        handle=f"sp_{pool}_{index}",
        display_name=f"Sim {index}",
        onboarding_completed_at=timezone.now(),
        is_enabled=True,
    )
    return user


def lease_pool(pool: str, run_id: str, count: int) -> dict[int, User]:
    """Lease ``count`` fresh slots to the run and onboard an identity for each."""
    pool_services.register(pool, PoolSlot.objects.filter(pool=pool).count() + count)
    indexes = pool_services.allocate(pool, run_id, count, 600)
    return {index: create_pool_identity(pool, index) for index in indexes}


def stored_keys() -> set[str]:
    """Every image object currently held by the default storage backend."""
    try:
        _, names = default_storage.listdir("images")
    except FileNotFoundError:
        return set()
    return {f"images/{name}" for name in names}


def world(*, slots: bool = True) -> dict[str, Any]:
    """A comparable snapshot of every table and object a provision may touch."""
    snapshot: dict[str, Any] = {
        "conventions": list(Convention.objects.order_by("pk").values()),
        "enrollments": list(ConventionEnrollment.objects.order_by("pk").values()),
        "fursuits": list(Fursuit.objects.order_by("pk").values()),
        "activations": list(FursuitActivation.objects.order_by("pk").values()),
        "sessions": FursuitCatchSession.objects.count(),
        "credentials": FursuitCatchCredential.objects.count(),
        "catches": Catch.objects.count(),
        "avatars": sorted(
            PlayerProfile.objects.values_list("avatar_key", flat=True),
            key=str,
        ),
        "runs": list(FixtureRun.objects.order_by("pk").values()),
        "objects": list(FixtureObject.objects.order_by("pk").values()),
        "storage": stored_keys(),
    }
    if slots:
        snapshot["slots"] = list(PoolSlot.objects.order_by("pool", "index").values())
    return snapshot
