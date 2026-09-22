"""Closed persistence contract for operator authorization audit events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

from django.conf import settings
from django.db import models

from accounts.models import User


class OperatorAction(models.TextChoices):
    """The only sensitive operator actions that may be recorded."""

    REMOVE_CATCH = "remove_catch", "Remove catch"
    REVOKE_CATCH_CREDENTIAL = "revoke_catch_credential", "Revoke catch credential"
    TERMINATE_CATCH_SESSION = "terminate_catch_session", "Terminate catch session"
    DEACTIVATE_FURSUIT_ACTIVATION = (
        "deactivate_fursuit_activation",
        "Deactivate fursuit activation",
    )
    REMOVE_CONVENTION_ENROLLMENT = (
        "remove_convention_enrollment",
        "Remove convention enrollment",
    )
    SET_PROFILE_ENABLED = "set_profile_enabled", "Set profile enabled"
    SET_FURSUIT_ENABLED = "set_fursuit_enabled", "Set fursuit enabled"
    SET_CONVENTION_PLAYABILITY = (
        "set_convention_playability",
        "Set convention playability",
    )


class OperatorActorClass(models.TextChoices):
    """The authorization category of the actor that submitted an attempt."""

    OPERATOR = "operator", "Operator"
    EMERGENCY_SUPERUSER = "emergency_superuser", "Emergency superuser"
    UNAUTHORIZED_ACTOR = "unauthorized_actor", "Unauthorized actor"


class OperatorAuditOutcome(models.TextChoices):
    """The bounded outcome vocabulary for an operator attempt."""

    SUCCEEDED = "succeeded", "Succeeded"
    DENIED = "denied", "Denied"
    REJECTED = "rejected", "Rejected"
    FAILED = "failed", "Failed"


class OperatorTargetType(models.TextChoices):
    """Stable domain target labels for the sensitive action matrix."""

    CATCH = "catches.catch", "Catch"
    FURSUIT_CATCH_CREDENTIAL = (
        "conventions.fursuitcatchcredential",
        "Fursuit catch credential",
    )
    FURSUIT_CATCH_SESSION = (
        "conventions.fursuitcatchsession",
        "Fursuit catch session",
    )
    FURSUIT_ACTIVATION = "conventions.fursuitactivation", "Fursuit activation"
    CONVENTION_ENROLLMENT = "conventions.conventionenrollment", "Convention enrollment"
    PLAYER_PROFILE = "profiles.playerprofile", "Player profile"
    FURSUIT = "fursuits.fursuit", "Fursuit"
    CONVENTION = "conventions.convention", "Convention"


class OperatorAuditEvent(models.Model):
    """One durable, minimal record of a top-level operator attempt."""

    id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    action: models.CharField[str, str] = models.CharField(
        max_length=32,
        choices=OperatorAction.choices,
    )
    actor: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    actor_class: models.CharField[str, str] = models.CharField(
        max_length=32,
        choices=OperatorActorClass.choices,
    )
    affected_record_type: models.CharField[str, str] = models.CharField(
        max_length=64,
        choices=OperatorTargetType.choices,
    )
    affected_record_id: models.PositiveBigIntegerField[int, int] = (
        models.PositiveBigIntegerField()
    )
    outcome: models.CharField[str, str] = models.CharField(
        max_length=16,
        choices=OperatorAuditOutcome.choices,
    )
    occurred_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
                        outcome=OperatorAuditOutcome.DENIED,
                    )
                    | (
                        models.Q(
                            actor_class__in=(
                                OperatorActorClass.OPERATOR,
                                OperatorActorClass.EMERGENCY_SUPERUSER,
                            )
                        )
                        & ~models.Q(outcome=OperatorAuditOutcome.DENIED)
                    )
                ),
                name="operator_audit_actor_outcome_valid",
            ),
        ]
