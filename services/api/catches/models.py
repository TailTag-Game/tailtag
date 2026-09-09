"""Durable catch records."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from accounts.models import User
    from conventions.models import Convention, FursuitActivation, FursuitCatchSession
    from fursuits.models import Fursuit


class Catch(models.Model):
    """A durable player catch with its original provenance."""

    id: int
    pk: int
    catcher_user_id: int
    catcher_user: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catches",
    )
    fursuit_id: int
    fursuit: models.ForeignKey[Fursuit, Fursuit] = models.ForeignKey(
        "fursuits.Fursuit",
        on_delete=models.PROTECT,
        related_name="catches",
    )
    convention_id: int
    convention: models.ForeignKey[Convention, Convention] = models.ForeignKey(
        "conventions.Convention",
        on_delete=models.PROTECT,
        related_name="catches",
    )
    activation_id: int
    activation: models.ForeignKey[FursuitActivation, FursuitActivation] = (
        models.ForeignKey(
            "conventions.FursuitActivation",
            on_delete=models.PROTECT,
            related_name="catches",
        )
    )
    catch_session_id: int
    catch_session: models.ForeignKey[FursuitCatchSession, FursuitCatchSession] = (
        models.ForeignKey(
            "conventions.FursuitCatchSession",
            on_delete=models.PROTECT,
            related_name="catches",
        )
    )
    caught_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(auto_now_add=True)
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-caught_at", "-id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["catcher_user", "fursuit", "convention"],
                name="catches_catcher_fursuit_convention_unique",
            )
        ]

    def __str__(self) -> str:
        return (
            f"Catch {self.pk}: catcher {self.catcher_user_id}, "
            f"fursuit {self.fursuit_id}, convention {self.convention_id}"
        )
