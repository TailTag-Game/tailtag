"""Durable catch records."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

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
        models.DateTimeField(
            default=timezone.now,
            editable=False,
            help_text="The server request time. Services always pass it.",
        )
    )
    approved_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField(
            db_default=Now(),
            editable=False,
            help_text="The server approval time. Equals caught_at for an immediate catch.",
        )
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


class CatchRequestState(models.TextChoices):
    """Stored request states. ``expired`` is derived and never stored."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"
    INVALIDATED = "invalidated", "Invalidated"


def _only_times(
    state: str, *, required: str, allowed: tuple[str, ...] = ()
) -> models.Q:
    """Match *state* rows with *required* set and every other decision time null."""
    condition = models.Q(state=state, **{f"{required}__isnull": False})
    for field in _DECISION_TIMES:
        if field != required and field not in allowed:
            condition &= models.Q(**{f"{field}__isnull": True})
    return condition


_DECISION_TIMES = ("approved_at", "declined_at", "withdrawn_at", "invalidated_at")
_PENDING_HAS_NO_DECISION_TIME = models.Q(
    state=CatchRequestState.PENDING,
    approved_at__isnull=True,
    declined_at__isnull=True,
    withdrawn_at__isnull=True,
    invalidated_at__isnull=True,
)


class CatchRequest(models.Model):
    """One catch attempt at one convention, kept for the owner decision.

    See the reusable TailTag contract, section "Catch requests". Cleanup deletes
    every row after the review deadline, so no foreign key points at a row and no
    row points at its catch. The trio's unique catch identifies it.
    """

    id: int
    pk: int
    player_id: int
    player: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catch_requests",
    )
    fursuit_id: int
    fursuit: models.ForeignKey[Fursuit, Fursuit] = models.ForeignKey(
        "fursuits.Fursuit",
        on_delete=models.PROTECT,
        related_name="catch_requests",
    )
    convention_id: int
    convention: models.ForeignKey[Convention, Convention] = models.ForeignKey(
        "conventions.Convention",
        on_delete=models.PROTECT,
        related_name="catch_requests",
    )
    activation_id: int
    activation: models.ForeignKey[FursuitActivation, FursuitActivation] = (
        models.ForeignKey(
            "conventions.FursuitActivation",
            on_delete=models.PROTECT,
            related_name="catch_requests",
        )
    )
    catch_session_id: int
    catch_session: models.ForeignKey[FursuitCatchSession, FursuitCatchSession] = (
        models.ForeignKey(
            "conventions.FursuitCatchSession",
            on_delete=models.PROTECT,
            related_name="catch_requests",
        )
    )
    state: models.CharField[str, str] = models.CharField(
        max_length=16, choices=CatchRequestState.choices
    )
    requested_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField()
    )
    approved_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    declined_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set while the decline counts. Undo and restore clear it.",
    )
    withdrawn_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    invalidated_at: models.DateTimeField[
        datetime.datetime | None, datetime.datetime | None
    ] = models.DateTimeField(null=True, blank=True)
    decline_blocked: models.BooleanField[bool, bool] = models.BooleanField(
        default=False, db_default=False
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-requested_at", "-id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["player", "fursuit", "convention"],
                condition=models.Q(state=CatchRequestState.PENDING),
                name="catches_request_one_pending_per_trio",
            ),
            models.CheckConstraint(
                condition=(
                    _PENDING_HAS_NO_DECISION_TIME
                    | _only_times(CatchRequestState.APPROVED, required="approved_at")
                    | _only_times(CatchRequestState.DECLINED, required="declined_at")
                    | _only_times(
                        CatchRequestState.WITHDRAWN,
                        required="withdrawn_at",
                        allowed=("declined_at",),
                    )
                    | _only_times(
                        CatchRequestState.INVALIDATED,
                        required="invalidated_at",
                        allowed=("declined_at",),
                    )
                ),
                name="catches_request_state_times",
            ),
            models.CheckConstraint(
                condition=models.Q(decline_blocked=False)
                | models.Q(declined_at__isnull=False),
                name="catches_request_block_needs_decline",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["player", "requested_at"], name="catches_request_player_time"
            ),
            models.Index(
                fields=["player", "fursuit", "convention", "requested_at"],
                name="catches_request_trio_time",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"CatchRequest {self.pk}: player {self.player_id}, "
            f"fursuit {self.fursuit_id}, convention {self.convention_id}, {self.state}"
        )


class CatchBlock(models.Model):
    """An owner's block of one player for one suit at one convention (#506).

    A block refuses new attempts only. It never changes a request. Cleanup
    deletes blocks with request history after the review deadline.
    """

    id: int
    pk: int
    player_id: int
    player: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catch_blocks",
    )
    fursuit_id: int
    fursuit: models.ForeignKey[Fursuit, Fursuit] = models.ForeignKey(
        "fursuits.Fursuit",
        on_delete=models.PROTECT,
        related_name="catch_blocks",
    )
    convention_id: int
    convention: models.ForeignKey[Convention, Convention] = models.ForeignKey(
        "conventions.Convention",
        on_delete=models.PROTECT,
        related_name="catch_blocks",
    )
    created_at: models.DateTimeField[datetime.datetime, datetime.datetime] = (
        models.DateTimeField()
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["player", "fursuit", "convention"],
                name="catches_block_one_per_trio",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"CatchBlock {self.pk}: player {self.player_id}, "
            f"fursuit {self.fursuit_id}, convention {self.convention_id}"
        )
