"""Run ledger for Staging simulation fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from django.db import models

PROVISIONED = "provisioned"
FAILED = "failed"

CONVENTION = "convention"
ENROLLMENT = "enrollment"
FURSUIT = "fursuit"
ACTIVATION = "activation"
KINDS = (CONVENTION, ENROLLMENT, FURSUIT, ACTIVATION)


class FixtureRun(models.Model):
    """One simulation run's provisioning attempt; a run ID is used at most once."""

    run_id: models.CharField[str, str] = models.CharField(max_length=36, unique=True)
    pool: models.CharField[str, str] = models.CharField(max_length=12)
    status: models.CharField[str, str] = models.CharField(
        max_length=11,
        choices=[(PROVISIONED, "Provisioned"), (FAILED, "Failed")],
    )
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(status__in=[PROVISIONED, FAILED]),
                name="simulation_fixtures_run_status_valid",
            ),
        ]


class FixtureObject(models.Model):
    """One domain object a provisioned run created, found later by run ID."""

    run: models.ForeignKey[FixtureRun, FixtureRun] = models.ForeignKey(
        FixtureRun, on_delete=models.CASCADE
    )
    kind: models.CharField[str, str] = models.CharField(
        max_length=10,
        choices=[
            (CONVENTION, "Convention"),
            (ENROLLMENT, "Enrollment"),
            (FURSUIT, "Fursuit"),
            (ACTIVATION, "Activation"),
        ],
    )
    object_id: models.PositiveBigIntegerField[int, int] = (
        models.PositiveBigIntegerField()
    )
    media_key: models.TextField[str | None, str | None] = models.TextField(null=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["kind", "object_id"], name="simulation_fixtures_object_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=list(KINDS)),
                name="simulation_fixtures_object_kind_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind=FURSUIT, media_key__isnull=False)
                    | (~models.Q(kind=FURSUIT) & models.Q(media_key__isnull=True))
                ),
                name="simulation_fixtures_object_media_key_fursuit_only",
            ),
        ]
