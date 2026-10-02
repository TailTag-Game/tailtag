"""Lease store for the Staging synthetic simulation identity pool."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from django.db import models

AVAILABLE = "available"
QUARANTINED = "quarantined"


class PoolSlot(models.Model):
    """One pool identity index, leased to at most one run at a time.

    The row holds an index only; Clerk user IDs never reach this database.
    """

    pool: models.CharField[str, str] = models.CharField(max_length=12)
    index: models.PositiveIntegerField[int, int] = models.PositiveIntegerField()
    state: models.CharField[str, str] = models.CharField(
        max_length=11,
        choices=[(AVAILABLE, "Available"), (QUARANTINED, "Quarantined")],
        default=AVAILABLE,
    )
    run_id: models.CharField[str | None, str | None] = models.CharField(
        max_length=36, null=True, blank=True
    )
    lease_expires_at: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True, blank=True)
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["pool", "index"], name="simulation_pool_slot_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=[AVAILABLE, QUARANTINED]),
                name="simulation_pool_slot_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(run_id__isnull=True, lease_expires_at__isnull=True)
                    | models.Q(run_id__isnull=False, lease_expires_at__isnull=False)
                ),
                name="simulation_pool_slot_lease_complete",
            ),
        ]
