"""Convention domain models for TailTag."""

from __future__ import annotations

import datetime
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import User
from fursuits.models import Fursuit

from .catch_credential_protocol import CATCH_CREDENTIAL_TOKEN_LENGTH


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


class FursuitActivation(models.Model):
    """A fursuit owner's durable participation selection for a convention."""

    id: int
    pk: int
    fursuit_id: int
    fursuit: models.ForeignKey[Fursuit, Fursuit] = models.ForeignKey(
        "fursuits.Fursuit",
        on_delete=models.PROTECT,
        related_name="convention_activations",
    )
    convention_id: int
    convention: models.ForeignKey[Convention, Convention] = models.ForeignKey(
        Convention,
        on_delete=models.PROTECT,
        related_name="fursuit_activations",
    )
    is_active: models.BooleanField[bool, bool] = models.BooleanField()
    activated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField()
    )
    deactivated_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["fursuit_id", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["fursuit", "convention"],
                name="conventions_activation_fursuit_convention_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=True, deactivated_at__isnull=True)
                    | models.Q(is_active=False, deactivated_at__isnull=False)
                ),
                name="conventions_activation_state_timestamps_valid",
            ),
        ]


class FursuitCatchSessionEndReason(models.TextChoices):
    """The bounded set of terminal causes for a catch session."""

    OWNER = "owner", "Owner"
    OPERATOR = "operator", "Operator"
    ELIGIBILITY_LOST = "eligibility_lost", "Eligibility lost"
    EXPIRED = "expired", "Expired"


class FursuitCatchSession(models.Model):
    """One append-only owner declaration that a fursuit is currently out."""

    id: int
    pk: int
    activation_id: int
    activation: models.ForeignKey[FursuitActivation, FursuitActivation] = (
        models.ForeignKey(
            FursuitActivation,
            on_delete=models.PROTECT,
            related_name="catch_sessions",
        )
    )
    started_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField()
    )
    expires_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField()
    )
    ended_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    end_reason: models.CharField[str | None, str | None] = models.CharField(
        max_length=32,
        choices=FursuitCatchSessionEndReason.choices,
        null=True,
        blank=True,
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-started_at", "-id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("started_at")),
                name="conventions_catch_session_expiry_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(ended_at__isnull=True, end_reason__isnull=True)
                    | models.Q(ended_at__isnull=False, end_reason__isnull=False)
                ),
                name="conventions_catch_session_end_fields_paired",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(ended_at__isnull=True)
                    | models.Q(ended_at__gte=models.F("started_at"))
                ),
                name="conventions_catch_session_end_not_before_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(end_reason__isnull=True)
                    | models.Q(end_reason__in=FursuitCatchSessionEndReason.values)
                ),
                name="conventions_catch_session_end_reason_valid",
            ),
            models.UniqueConstraint(
                fields=["activation"],
                condition=models.Q(ended_at__isnull=True),
                name="conventions_catch_session_one_unended_per_activation",
            ),
        ]


class FursuitCatchCredentialRevocationReason(models.TextChoices):
    """The bounded terminal causes for a catch credential."""

    OWNER_ROTATION = "owner_rotation", "Owner rotation"
    OPERATOR = "operator", "Operator"
    ELIGIBILITY_LOST = "eligibility_lost", "Eligibility lost"


class FursuitCatchCredential(models.Model):
    """One append-only opaque catch-credential record for an activation."""

    id: int
    pk: int
    activation_id: int
    activation: models.ForeignKey[FursuitActivation, FursuitActivation] = (
        models.ForeignKey(
            FursuitActivation,
            on_delete=models.PROTECT,
            related_name="catch_credentials",
        )
    )
    token: models.CharField[str, str] = models.CharField(
        max_length=CATCH_CREDENTIAL_TOKEN_LENGTH
    )
    revoked_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    revocation_reason: models.CharField[str | None, str | None] = models.CharField(
        max_length=32,
        choices=FursuitCatchCredentialRevocationReason.choices,
        null=True,
        blank=True,
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at", "-id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(revoked_at__isnull=True, revocation_reason__isnull=True)
                    | models.Q(
                        revoked_at__isnull=False, revocation_reason__isnull=False
                    )
                ),
                name="conventions_catch_credential_revocation_fields_paired",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(revocation_reason__isnull=True)
                    | models.Q(
                        revocation_reason__in=FursuitCatchCredentialRevocationReason.values
                    )
                ),
                name="conventions_catch_credential_revocation_reason_valid",
            ),
            models.UniqueConstraint(
                fields=["token"],
                name="conventions_catch_credential_token_unique",
            ),
            models.UniqueConstraint(
                fields=["activation"],
                condition=models.Q(revoked_at__isnull=True),
                name="conventions_catch_credential_one_current_per_activation",
            ),
        ]

    def __str__(self) -> str:
        """Return a safe diagnostic representation without the opaque token."""
        return f"Catch credential {self.pk}"
