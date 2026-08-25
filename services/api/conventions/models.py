"""Convention domain models for TailTag."""

from __future__ import annotations

import datetime
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import User


class ConventionStatus(models.TextChoices):
    """Operational lifecycle status of a Convention."""

    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Convention(models.Model):
    """A real-world furry convention setting for TailTag gameplay."""

    id: int
    pk: int
    name: models.CharField[str, str] = models.CharField(
        max_length=255,
        help_text="The official name of the convention.",
    )
    status: models.CharField[str, str] = models.CharField(
        max_length=32,
        choices=ConventionStatus.choices,
        default=ConventionStatus.DRAFT,
        db_index=True,
        help_text="Operational lifecycle state of the convention.",
    )
    start_date: models.DateField[datetime.date, datetime.date] = models.DateField(
        help_text="Start date of the convention.",
    )
    end_date: models.DateField[datetime.date, datetime.date] = models.DateField(
        help_text="End date of the convention.",
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(
            auto_now_add=True,
        )
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(
            auto_now=True,
        )
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-start_date", "name"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="conventions_convention_name_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ConventionStatus.values),
                name="conventions_convention_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="conventions_convention_end_date_gte_start_date",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["status", "start_date", "end_date"],
                name="conventions_status_dates_idx",
            ),
        ]

    def clean(self) -> None:
        """Validate date invariants across fields."""
        super().clean()
        start_date: datetime.date | None = getattr(self, "start_date", None)
        end_date: datetime.date | None = getattr(self, "end_date", None)
        if start_date is not None and end_date is not None and end_date < start_date:
            raise ValidationError(
                {"end_date": "End date must be on or after start date."}
            )

    @property
    def is_playable(self) -> bool:
        """Return whether the convention is in an active playable state."""
        return self.status == ConventionStatus.ACTIVE.value

    def __str__(self) -> str:
        """Return the convention name and identifier."""
        return f"{self.name} ({self.pk})"


class ConventionEnrollment(models.Model):
    """Player-owned enrollment in a convention for TailTag gameplay."""

    id: int
    pk: int
    user_id: int
    user: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="convention_enrollments",
    )
    convention_id: int
    convention: models.ForeignKey[Convention, Convention] = models.ForeignKey(
        Convention,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    is_active: models.BooleanField[bool, bool] = models.BooleanField(
        default=False,
        help_text="Whether this convention is the player's selected active gameplay convention.",
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(
            auto_now_add=True,
        )
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(
            auto_now=True,
        )
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["user", "convention"],
                name="conventions_enrollment_user_convention_unique",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="conventions_enrollment_user_single_active",
            ),
        ]

    def __str__(self) -> str:
        """Return human-readable enrollment representation."""
        return f"Enrollment: {self.user_id} -> {self.convention_id} (active={self.is_active})"
