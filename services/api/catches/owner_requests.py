"""Owner request reads (#506).

The reusable TailTag contract is the source of truth: sections "Owner request
fields" and "Owner review operations". Each row carries the trio values that
the owner fields need, so the list runs a fixed number of queries.
"""

from __future__ import annotations

import datetime

from django.db.models import (
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
)
from django.db.models.functions import Coalesce

from accounts.models import User
from catches.models import CatchBlock, CatchRequest, CatchRequestState

_COUNT: IntegerField[int, int] = IntegerField()


def owner_request_rows(owner: User) -> QuerySet[CatchRequest]:
    """Return the owner's requests with the annotations that the fields read."""
    trio = {
        "player_id": OuterRef("player_id"),
        "fursuit_id": OuterRef("fursuit_id"),
        "convention_id": OuterRef("convention_id"),
    }
    earlier_declines = (
        CatchRequest.objects.filter(**trio, declined_at__isnull=False)
        .filter(
            Q(requested_at__lt=OuterRef("requested_at"))
            | Q(requested_at=OuterRef("requested_at"), pk__lt=OuterRef("pk"))
        )
        .order_by()
        .values("player_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return (
        CatchRequest.objects.filter(fursuit__owner=owner)
        .select_related("fursuit", "convention", "player__player_profile")
        .annotate(
            prior_decline_count=Coalesce(
                Subquery(earlier_declines, output_field=_COUNT), 0
            ),
            player_blocked=Exists(CatchBlock.objects.filter(**trio)),
        )
    )


def open_owner_request_rows(
    owner: User,
    *,
    now: datetime.datetime,
    convention_id: int | None = None,
    fursuit_id: int | None = None,
) -> QuerySet[CatchRequest]:
    """The owner list: open windows only, newest first."""
    rows = owner_request_rows(owner).filter(convention__review_deadline_at__gt=now)
    if convention_id is not None:
        rows = rows.filter(convention_id=convention_id)
    if fursuit_id is not None:
        rows = rows.filter(fursuit_id=fursuit_id)
    return rows.order_by("-requested_at", "-id")


def pending_summary(
    owner: User, *, now: datetime.datetime, convention_id: int | None = None
) -> dict[str, object]:
    """Count pending requests per suit, in open windows only."""
    rows = CatchRequest.objects.filter(
        fursuit__owner=owner,
        state=CatchRequestState.PENDING,
        convention__review_deadline_at__gt=now,
    )
    if convention_id is not None:
        rows = rows.filter(convention_id=convention_id)
    per_suit = list(
        rows.order_by("fursuit_id")
        .values("fursuit_id")
        .annotate(pending_count=Count("pk"))
        .values_list("fursuit_id", "pending_count")
    )
    return {
        "pending_count": sum(count for _, count in per_suit),
        "fursuits": [
            {"fursuit_id": fursuit_id, "pending_count": count}
            for fursuit_id, count in per_suit
        ],
    }
