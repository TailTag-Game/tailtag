"""Focused setup and assertions for fursuit-activation acceptance tests."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import cast

from django.test import Client
from django.utils import timezone

from accounts.models import User
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user, force_authenticated_client


@dataclass(frozen=True)
class ActivationScenario:
    user: User
    client: Client
    profile: PlayerProfile
    convention: Convention
    fursuit: Fursuit
    enrollment: ConventionEnrollment | None


def create_activation_scenario(
    *,
    clerk_user_id: str = "activation_owner",
    convention_status: str = ConventionStatus.ACTIVE,
    profile_enabled: bool = True,
    fursuit_enabled: bool = True,
    enrolled: bool = True,
    enrollment_is_active: bool = False,
) -> ActivationScenario:
    """Create only the upstream state relevant to a single activation pair."""
    user = create_test_user(clerk_user_id=clerk_user_id)
    profile = PlayerProfile.objects.create(
        user=user,
        handle=f"activation_{user.pk}",
        display_name="Activation Owner",
        onboarding_completed_at=timezone.now(),
        is_enabled=profile_enabled,
    )
    convention = Convention.objects.create(
        name=f"Activation Convention {user.pk}",
        status=convention_status,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )
    fursuit = Fursuit.objects.create(
        owner=user,
        name=f"Activation Fursuit {user.pk}",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
        is_enabled=fursuit_enabled,
    )
    enrollment = (
        ConventionEnrollment.objects.create(
            user=user, convention=convention, is_active=enrollment_is_active
        )
        if enrolled
        else None
    )
    return ActivationScenario(
        user=user,
        client=force_authenticated_client(user=user),
        profile=profile,
        convention=convention,
        fursuit=fursuit,
        enrollment=enrollment,
    )


def activation_list_path(convention_id: int) -> str:
    return f"/api/conventions/{convention_id}/fursuit-activations/"


def activation_detail_path(convention_id: int, fursuit_id: int) -> str:
    return f"{activation_list_path(convention_id)}{fursuit_id}/"


def assert_activation_data(data: object) -> dict[str, object]:
    assert isinstance(data, dict)
    result = cast(dict[str, object], data)
    assert set(result) == {
        "fursuit_id",
        "convention_id",
        "is_active",
        "is_eligible",
        "activated_at",
        "deactivated_at",
    }
    assert isinstance(result["fursuit_id"], int)
    assert isinstance(result["convention_id"], int)
    assert isinstance(result["is_active"], bool)
    assert isinstance(result["is_eligible"], bool)
    assert isinstance(result["activated_at"], str)
    assert result["deactivated_at"] is None or isinstance(result["deactivated_at"], str)
    return result
