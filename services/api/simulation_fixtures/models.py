"""Run ledger for Staging simulation fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Final

from django.db import models

PROVISIONED = "provisioned"
FAILED = "failed"
RETAINED = "retained"
CLEANED = "cleaned"
STATUSES: Final = (PROVISIONED, FAILED, RETAINED, CLEANED)

# Why a run was retained; kept after cleaning as history.
REASONS: Final = ("journeys", "reconciliation", "cleanup", "interrupted")

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
        choices=[
            (PROVISIONED, "Provisioned"),
            (FAILED, "Failed"),
            (RETAINED, "Retained"),
            (CLEANED, "Cleaned"),
        ],
    )
    reason: models.CharField[str | None, str | None] = models.CharField(
        max_length=14, null=True, choices=[(reason, reason) for reason in REASONS]
    )
    cleaned_at: models.DateTimeField[datetime | None, datetime | None] = (
        models.DateTimeField(null=True)
    )
    # Deleted-object counts per kind; setting them marks the database phase complete.
    cleanup_counts: models.JSONField[dict[str, int] | None] = models.JSONField(
        null=True
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
                condition=models.Q(status__in=list(STATUSES)),
                name="simulation_fixtures_run_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(reason__isnull=True)
                | models.Q(reason__in=list(REASONS)),
                name="simulation_fixtures_run_reason_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=RETAINED) | models.Q(reason__isnull=False),
                name="simulation_fixtures_run_retained_has_reason",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=CLEANED, cleaned_at__isnull=False)
                    | (~models.Q(status=CLEANED) & models.Q(cleaned_at__isnull=True))
                ),
                name="simulation_fixtures_run_cleaned_at_iff_cleaned",
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


class FixtureIdentity(models.Model):
    """One pool index leased to a run: an owner, a catcher, or an extra."""

    run: models.ForeignKey[FixtureRun, FixtureRun] = models.ForeignKey(
        FixtureRun, on_delete=models.CASCADE
    )
    index: models.PositiveIntegerField[int, int] = models.PositiveIntegerField()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["run", "index"], name="simulation_fixtures_identity_unique"
            ),
        ]


class FixturePendingImage(models.Model):
    """An image key whose rows are deleted but whose storage object is not yet gone."""

    run: models.ForeignKey[FixtureRun, FixtureRun] = models.ForeignKey(
        FixtureRun, on_delete=models.CASCADE
    )
    key: models.TextField[str, str] = models.TextField(unique=True)
