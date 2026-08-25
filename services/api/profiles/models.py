"""Durable TailTag-owned player profile state."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from django.conf import settings
from django.db import models

from accounts.models import User


class PlayerProfile(models.Model):
    """One conceptual product profile, keyed by its application user."""

    user_id: int
    pk: int
    user: models.OneToOneField[User, User] = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="player_profile",
    )
    handle: models.CharField[str | None, str | None] = models.CharField(
        max_length=32, null=True
    )
    display_name: models.CharField[str | None, str | None] = models.CharField(
        max_length=50, null=True
    )
    avatar_key: models.TextField[str | None, str | None] = models.TextField(null=True)
    onboarding_completed_at: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True)
    )
    is_enabled: models.BooleanField[bool, bool] = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("handle",),
                name="profiles_player_profile_handle_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(handle__isnull=True)
                | models.Q(handle__regex=r"^[a-z0-9][a-z0-9_]{1,31}$"),
                name="profiles_player_profile_handle_format",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        handle__isnull=True,
                        display_name__isnull=True,
                        onboarding_completed_at__isnull=True,
                    )
                    | (
                        models.Q(
                            handle__isnull=False,
                            display_name__isnull=False,
                            onboarding_completed_at__isnull=False,
                        )
                        & ~models.Q(display_name="")
                    )
                ),
                name="profiles_player_profile_onboarding_state_consistent",
            ),
        ]

    @property
    def onboarding_complete(self) -> bool:
        """Return whether initial text onboarding is durably complete."""
        return self.onboarding_completed_at is not None

    @property
    def avatar_present(self) -> bool:
        """Return whether the profile has an opaque stored avatar reference."""
        return self.avatar_key is not None
