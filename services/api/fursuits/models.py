"""Durable participating-character records."""

from __future__ import annotations

import datetime
import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models

from accounts.models import User
from fursuits.tag_protocol import TAG_TOKEN_LENGTH


class CatchApprovalMode(models.TextChoices):
    """Whether a new catch request waits for the owner or becomes a catch at once."""

    MANUAL = "manual", "Manual"
    AUTOMATIC = "automatic", "Automatic"


class Fursuit(models.Model):
    """A player-owned, operator-moderated participating character."""

    id: int
    pk: int
    owner_id: int
    owner: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="fursuits",
    )
    name: models.CharField[str, str] = models.CharField(max_length=50)
    tailtag_id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    photo_key: models.TextField[str, str] = models.TextField()
    is_enabled: models.BooleanField[bool, bool] = models.BooleanField(default=True)
    tag_version: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        default=0,
        db_default=0,
        editable=False,
        help_text="Raised by one on each tag creation, replacement, and revocation.",
    )
    catch_approval_mode: models.CharField[str, str] = models.CharField(
        max_length=16,
        choices=CatchApprovalMode.choices,
        default=CatchApprovalMode.MANUAL,
        db_default=CatchApprovalMode.MANUAL,
        help_text="Applies only to new catch requests.",
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        permissions: ClassVar[list[tuple[str, str]]] = [
            ("set_fursuit_enabled", "Can set fursuit enabled state"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="fursuits_fursuit_name_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(photo_key=""),
                name="fursuits_fursuit_photo_key_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(catch_approval_mode__in=CatchApprovalMode.values),
                name="fursuits_fursuit_catch_approval_mode_valid",
            ),
        ]

    @property
    def photo_present(self) -> bool:
        """Return whether this record has an opaque photo reference."""
        return bool(self.photo_key)


class FursuitTagRevocationReason(models.TextChoices):
    """The bounded causes that end a tag."""

    OWNER_REPLACEMENT = "owner_replacement", "Owner replacement"
    OPERATOR = "operator", "Operator"


class FursuitTag(models.Model):
    """One append-only reusable tag record for a fursuit.

    At most one row per fursuit is current (``revoked_at`` is null). The token is
    secret: only the owner tag read and the replacement response return it.
    """

    id: int
    pk: int
    fursuit_id: int
    fursuit: models.ForeignKey[Fursuit, Fursuit] = models.ForeignKey(
        Fursuit,
        on_delete=models.PROTECT,
        related_name="tags",
    )
    token: models.CharField[str, str] = models.CharField(
        max_length=TAG_TOKEN_LENGTH, editable=False
    )
    created_version: models.PositiveIntegerField[int, int] = (
        models.PositiveIntegerField(editable=False)
    )
    revoked_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    revocation_reason: models.CharField[str | None, str | None] = models.CharField(
        max_length=32,
        choices=FursuitTagRevocationReason.choices,
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
        permissions: ClassVar[list[tuple[str, str]]] = [
            ("revoke_fursuit_tag", "Can revoke a current fursuit tag"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(revoked_at__isnull=True, revocation_reason__isnull=True)
                    | models.Q(
                        revoked_at__isnull=False, revocation_reason__isnull=False
                    )
                ),
                name="fursuits_tag_revocation_fields_paired",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(revocation_reason__isnull=True)
                    | models.Q(revocation_reason__in=FursuitTagRevocationReason.values)
                ),
                name="fursuits_tag_revocation_reason_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(created_version__gte=1),
                name="fursuits_tag_created_version_positive",
            ),
            models.UniqueConstraint(
                fields=["token"],
                name="fursuits_tag_token_unique",
            ),
            models.UniqueConstraint(
                fields=["fursuit", "created_version"],
                name="fursuits_tag_fursuit_version_unique",
            ),
            models.UniqueConstraint(
                fields=["fursuit"],
                condition=models.Q(revoked_at__isnull=True),
                name="fursuits_tag_one_current_per_fursuit",
            ),
        ]

    @property
    def is_current(self) -> bool:
        """Derive current state solely from the terminal timestamp."""
        return self.revoked_at is None
