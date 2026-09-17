"""Persistent Staging-only reset identity registry."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from accounts.models import User
    from conventions.models import Convention
    from fursuits.models import Fursuit


class StagingResetIdentity(models.Model):
    """The explicitly provisioned roots permitted to be reconciled by #204."""

    id: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        primary_key=True
    )
    pk: int
    environment_id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField()
    cluster_identifier: models.CharField[str, str] = models.CharField(max_length=32)
    database_name: models.CharField[str, str] = models.CharField(max_length=63)
    owner_id: int
    owner: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    catcher_id: int
    catcher: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    media_key: models.TextField[str, str] = models.TextField()
    convention_id: int | None
    convention: models.ForeignKey[Convention | None, Convention | None] = (
        models.ForeignKey(
            "conventions.Convention",
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="+",
        )
    )
    first_fursuit_id: int | None
    first_fursuit: models.ForeignKey[Fursuit | None, Fursuit | None] = (
        models.ForeignKey(
            "fursuits.Fursuit",
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="+",
        )
    )
    second_fursuit_id: int | None
    second_fursuit: models.ForeignKey[Fursuit | None, Fursuit | None] = (
        models.ForeignKey(
            "fursuits.Fursuit",
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name="+",
        )
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="rehearsal_reset_identity_singleton"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        convention__isnull=True,
                        first_fursuit__isnull=True,
                        second_fursuit__isnull=True,
                    )
                    | models.Q(
                        convention__isnull=False,
                        first_fursuit__isnull=False,
                        second_fursuit__isnull=False,
                    )
                ),
                name="rehearsal_reset_identity_roots_complete",
            ),
        ]
