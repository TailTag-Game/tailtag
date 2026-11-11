"""Operator invalidation of catch requests (#507).

The reusable TailTag contract is the source of truth: sections "Transitions",
"Eligibility after submission", and "Operator operations". An operator action
turns a pending or declined request into ``invalidated``. Final states stay.

Invalidation acts only while the convention's review window is open (#507 G5).
A closed-window row is already hidden, and cleanup deletes it soon.

The hooks run inside the existing operator transactions. Each hook already
holds the contract locks that come before CatchRequest, so the UPDATE here
takes the request row locks last (#507 G6).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import QuerySet

from catches.models import CatchRequest, CatchRequestState
from conventions.models import Convention
from conventions.review_deadline import database_now, review_window_open
from operator_audit.services import OperatorTransition
from profiles.models import PlayerProfile

INVALIDATABLE_STATES = (CatchRequestState.PENDING, CatchRequestState.DECLINED)


def invalidate_request_as_operator(
    *, request_id: int
) -> OperatorTransition[CatchRequest]:
    """Invalidate one pending or declined request in an open window.

    Lock order follows the contract: the player's PlayerProfile, the
    Convention, then the CatchRequest. Any other state or a closed window is no
    change, which the operator audit records as ``rejected``.
    """
    candidate = (
        CatchRequest.objects.filter(pk=request_id)
        .values("player_id", "convention_id")
        .first()
    )
    if candidate is None:
        raise CatchRequest.DoesNotExist()
    with transaction.atomic():
        # A request's player always has a profile, but the lock stays optional
        # like enrollment removal, so a missing profile cannot hide the request.
        profile = (
            PlayerProfile.objects.select_for_update()
            .filter(user_id=candidate["player_id"])
            .first()
        )
        convention = Convention.objects.select_for_update().get(
            pk=candidate["convention_id"]
        )
        request = CatchRequest.objects.select_for_update().filter(pk=request_id).first()
        if request is None:
            # Cleanup deleted the row after the lookup.
            raise CatchRequest.DoesNotExist()
        now = database_now()
        if request.state not in INVALIDATABLE_STATES or not review_window_open(
            convention, now
        ):
            return OperatorTransition(value=request, changed=False)
        request.state = CatchRequestState.INVALIDATED
        request.invalidated_at = now
        request.save(update_fields=["state", "invalidated_at"])
        # Keep the profile lock until commit.
        del profile
        return OperatorTransition(value=request, changed=True)


def invalidate_open_requests(
    requests: QuerySet[CatchRequest], *, convention: Convention
) -> int:
    """Invalidate the pending and declined *requests* at *convention*.

    The caller runs inside its operator transaction and holds the contract
    locks above CatchRequest. Nothing changes when the window is closed. The
    return value is the number of invalidated rows.
    """
    now = database_now()
    if not review_window_open(convention, now):
        return 0
    return requests.filter(
        convention_id=convention.pk, state__in=INVALIDATABLE_STATES
    ).update(state=CatchRequestState.INVALIDATED, invalidated_at=now)
