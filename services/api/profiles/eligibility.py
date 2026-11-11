"""Fail-closed participation eligibility for downstream domains."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from accounts.models import User
from profiles.models import PlayerProfile


def eligible_player_profiles() -> QuerySet[PlayerProfile]:
    """Return the enabled, completed profiles whose users may participate."""
    return PlayerProfile.objects.filter(
        onboarding_completed_at__isnull=False,
        handle__isnull=False,
        display_name__isnull=False,
        is_enabled=True,
    ).exclude(display_name="")


def is_participation_eligible(user: User | AnonymousUser) -> bool:
    """Return whether a persisted user has an enabled completed profile."""
    if isinstance(user, AnonymousUser) or not user.is_authenticated:
        return False
    return eligible_player_profiles().filter(user_id=user.pk).exists()
