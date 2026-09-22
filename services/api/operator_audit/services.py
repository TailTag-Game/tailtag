"""Typed transition and persistence primitives for operator audit coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from accounts.models import User

from .models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)

T = TypeVar("T")


@dataclass(frozen=True)
class OperatorTransition[T]:
    """A domain operation's value and lock-authoritative change result."""

    value: T
    changed: bool


def _write_audit_event(  # pyright: ignore[reportUnusedFunction]
    *,
    action: OperatorAction,
    actor: User,
    actor_class: OperatorActorClass,
    target_type: OperatorTargetType,
    target_id: int,
    outcome: OperatorAuditOutcome,
) -> OperatorAuditEvent:
    """Persist one closed audit event without request or free-text inputs."""
    return OperatorAuditEvent.objects.create(
        action=action,
        actor=actor,
        actor_class=actor_class,
        affected_record_type=target_type,
        affected_record_id=target_id,
        outcome=outcome,
    )
