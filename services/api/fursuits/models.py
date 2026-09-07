"""Durable participating-character records."""

from __future__ import annotations

import datetime
import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models

from accounts.models import User


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
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )
    updated_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="fursuits_fursuit_name_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(photo_key=""),
                name="fursuits_fursuit_photo_key_not_empty",
            ),
        ]

    @property
    def photo_present(self) -> bool:
        """Return whether this record has an opaque photo reference."""
        return bool(self.photo_key)
