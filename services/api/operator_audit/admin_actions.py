"""Transaction coordinator for sensitive Django-admin POST attempts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn, TypeVar, cast

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse

from accounts.models import User

from . import services as audit_services
from .models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from .services import OperatorTransition

T = TypeVar("T")
_ATTEMPT_ATTRIBUTE = "_operator_audit_attempt"
logger = logging.getLogger(__name__)


class _RejectedOperatorAttempt(Exception):
    """Signal a known, sanitized rejection after rolling back the outer unit."""


@dataclass
class _BoundAttempt:
    action: OperatorAction
    actor: User
    actor_class: OperatorActorClass
    target_type: OperatorTargetType
    target_id: int
    transition_executed: bool = False


def _raise_rejected() -> NoReturn:
    raise PermissionDenied("The requested operator action was rejected.")


def _persist_outcome(attempt: _BoundAttempt, outcome: OperatorAuditOutcome) -> None:
    audit_services._write_audit_event(  # pyright: ignore[reportPrivateUsage]
        action=attempt.action,
        actor=attempt.actor,
        actor_class=attempt.actor_class,
        target_type=attempt.target_type,
        target_id=attempt.target_id,
        outcome=outcome,
    )


def _log_failed_attempt(attempt: _BoundAttempt) -> None:
    logger.error(
        "Sensitive operator attempt failed after rollback.",
        extra={
            "action": attempt.action,
            "actor_class": attempt.actor_class,
            "target_type": attempt.target_type,
            "actor_id": attempt.actor.pk,
            "target_id": attempt.target_id,
        },
    )


def _persisted_tailtag_user(request: HttpRequest) -> User | None:
    user = getattr(request, "user", None)
    if not isinstance(user, User):
        return None
    if not User.objects.filter(pk=user.pk).exists():
        return None
    return user


def execute_bound_operator_transition[T](
    request: HttpRequest,
    operation: Callable[[], OperatorTransition[T]],
) -> T:
    """Execute one bound domain transition and record its successful outcome."""
    attempt = getattr(request, _ATTEMPT_ATTRIBUTE, None)
    if not isinstance(attempt, _BoundAttempt) or attempt.transition_executed:
        raise _RejectedOperatorAttempt

    transition = operation()
    if not transition.changed:
        raise _RejectedOperatorAttempt

    _persist_outcome(attempt, OperatorAuditOutcome.SUCCEEDED)
    attempt.transition_executed = True
    return transition.value


def run_sensitive_admin_attempt(
    request: HttpRequest,
    *,
    permission: str,
    action: OperatorAction,
    target_type: OperatorTargetType,
    target_id: int,
    handler: Callable[[], HttpResponse],
    rejected_exceptions: tuple[type[Exception], ...] = (),
) -> HttpResponse:
    """Authorize, execute, and durably classify one sensitive admin POST."""
    if request.method != "POST":
        raise PermissionDenied

    actor = _persisted_tailtag_user(request)
    if actor is None:
        raise PermissionDenied

    if cast(bool, actor.is_superuser):  # pyright: ignore[reportUnknownMemberType]
        actor_class = OperatorActorClass.EMERGENCY_SUPERUSER
    elif actor.is_staff and actor.has_perm(permission):
        actor_class = OperatorActorClass.OPERATOR
    else:
        audit_services._write_audit_event(  # pyright: ignore[reportPrivateUsage]
            action=action,
            actor=actor,
            actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
            target_type=target_type,
            target_id=target_id,
            outcome=OperatorAuditOutcome.DENIED,
        )
        raise PermissionDenied

    attempt = _BoundAttempt(
        action=action,
        actor=actor,
        actor_class=actor_class,
        target_type=target_type,
        target_id=target_id,
    )
    setattr(request, _ATTEMPT_ATTRIBUTE, attempt)
    try:
        try:
            with transaction.atomic():
                response = handler()
                if not attempt.transition_executed:
                    raise _RejectedOperatorAttempt
                return response
        except (_RejectedOperatorAttempt, *rejected_exceptions):
            _persist_outcome(attempt, OperatorAuditOutcome.REJECTED)
            _raise_rejected()
        except Exception:
            try:
                _persist_outcome(attempt, OperatorAuditOutcome.FAILED)
            except Exception:  # noqa: BLE001
                _log_failed_attempt(attempt)
            raise
    finally:
        delattr(request, _ATTEMPT_ATTRIBUTE)
