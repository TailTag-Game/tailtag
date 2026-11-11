"""Owner decisions, player withdrawal, and unblock for catch requests (#506).

The reusable TailTag contract is the source of truth: sections "Competing
actions", "Restore and undo rules", "Eligibility after submission", and
"Blocks". Each action runs in one transaction:

1. Lock the player's PlayerProfile first. Approve locks both profiles in pk
   order. This serializes every action with that player's submissions, so a
   restore cannot race a new request into the one-pending constraint (#506 G4).
2. Lock the other contract rows that the action needs, in contract order.
3. Read one database time after the locks, and check state and window.
4. Write the result.

A repeat of an action that already happened returns the current state. A
different action that won first gives ``RequestStateChangedError``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from accounts.models import User
from catches.catch_requests import approve_request_in_transaction
from catches.models import Catch, CatchBlock, CatchRequest, CatchRequestState
from conventions.models import Convention, ConventionStatus
from conventions.review_deadline import database_now, review_window_open
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

UNDO_WINDOW = datetime.timedelta(seconds=10)


class RequestActionError(Exception):
    """A refused request action. ``code`` is the public contract code."""

    code = "request_action_refused"
    status = 409

    def __init__(self, state: str | None = None) -> None:
        super().__init__()
        self.state = state


class RequestNotFoundError(RequestActionError):
    code = "request_not_found"
    status = 404


class RequestStateChangedError(RequestActionError):
    code = "request_state_changed"


class ReviewWindowClosedError(RequestActionError):
    code = "review_window_closed"


class ApprovalPausedError(RequestActionError):
    code = "approval_paused"


class RequestSupersededError(RequestActionError):
    code = "request_superseded"


class UndoExpiredError(RequestActionError):
    code = "undo_expired"


class _Party(StrEnum):
    OWNER = "owner"
    PLAYER = "player"


@dataclass(frozen=True)
class ActionResult:
    request: CatchRequest
    now: datetime.datetime
    catch: Catch | None = None


@dataclass(frozen=True)
class _Target:
    request_id: int
    player_id: int
    owner_id: int
    fursuit_id: int
    convention_id: int


def public_state(state: str) -> str:
    """Map the stored state to the state that players and owners see."""
    return "unavailable" if state == CatchRequestState.INVALIDATED.value else state


def approve(owner: User, request_id: int) -> ActionResult:
    target = _find(owner, request_id, _Party.OWNER)
    with transaction.atomic():
        profiles = _lock_profiles({target.player_id, target.owner_id})
        convention = _lock_convention(target)
        fursuit = (
            Fursuit.objects.select_for_update().filter(pk=target.fursuit_id).first()
        )
        request = _lock_request(target, convention)
        catch = _trio_catch(target, lock=True)
        now = _action_time(convention)
        if request.state == CatchRequestState.APPROVED.value:
            if catch is None:
                # An operator removed the catch. Nothing can be repeated.
                raise RequestStateChangedError(public_state(request.state))
            return ActionResult(request, now, catch)
        if request.state != CatchRequestState.PENDING.value:
            raise RequestStateChangedError(public_state(request.state))
        if _approval_paused(profiles, target, fursuit, convention):
            raise ApprovalPausedError
        if catch is not None:
            raise RequestSupersededError
        try:
            with transaction.atomic():
                catch = approve_request_in_transaction(request, approved_at=now)
        except IntegrityError:
            # Another writer created the trio catch without the profile lock.
            raise RequestSupersededError from None
        return ActionResult(request, now, catch)


def decline(owner: User, request_id: int, *, block: bool) -> ActionResult:
    target = _find(owner, request_id, _Party.OWNER)
    with transaction.atomic():
        _lock_profiles({target.player_id})
        convention = _lock_convention(target)
        request = _lock_request(target, convention)
        _trio_blocks(target).select_for_update().first()
        now = _action_time(convention)
        if request.state == CatchRequestState.PENDING.value:
            request.state = CatchRequestState.DECLINED
            request.declined_at = now
            request.decline_blocked = block
            request.save(update_fields=["state", "declined_at", "decline_blocked"])
        elif request.state == CatchRequestState.DECLINED.value:
            # A repeat. ``block: true`` adds the block and keeps the decline
            # time, so the cooldown does not move (#506 G11c).
            if block and not request.decline_blocked:
                request.decline_blocked = True
                request.save(update_fields=["decline_blocked"])
        else:
            raise RequestStateChangedError(public_state(request.state))
        if block:
            _ensure_block(target, now)
        return ActionResult(request, now)


def undo_decline(owner: User, request_id: int) -> ActionResult:
    return _reopen(owner, request_id, undo=True)


def restore(owner: User, request_id: int) -> ActionResult:
    return _reopen(owner, request_id, undo=False)


def withdraw(player: User, request_id: int) -> ActionResult:
    target = _find(player, request_id, _Party.PLAYER)
    with transaction.atomic():
        _lock_profiles({target.player_id})
        convention = _lock_convention(target)
        request = _lock_request(target, convention)
        now = _action_time(convention)
        if request.state == CatchRequestState.PENDING.value:
            request.state = CatchRequestState.WITHDRAWN
            request.withdrawn_at = now
            request.save(update_fields=["state", "withdrawn_at"])
        elif request.state != CatchRequestState.WITHDRAWN.value:
            raise RequestStateChangedError(public_state(request.state))
        return ActionResult(request, now)


def unblock(owner: User, request_id: int) -> None:
    """Remove the trio's block. No block in place is a success too."""
    target = _find(owner, request_id, _Party.OWNER)
    with transaction.atomic():
        _lock_profiles({target.player_id})
        convention = _lock_convention(target)
        _lock_request(target, convention)
        blocks = _trio_blocks(target)
        list(blocks.select_for_update())
        _action_time(convention)
        blocks.delete()


def is_approval_paused(
    *,
    player_profile: PlayerProfile | None,
    owner_profile: PlayerProfile | None,
    fursuit: Fursuit,
    convention: Convention,
) -> bool:
    """Return the contract paused condition. The cause stays private."""
    return (
        player_profile is None
        or not player_profile.is_enabled
        or owner_profile is None
        or not owner_profile.is_enabled
        or not fursuit.is_enabled
        or convention.status == ConventionStatus.PAUSED.value
    )


def _reopen(owner: User, request_id: int, *, undo: bool) -> ActionResult:
    """Undo or restore. Both share one set of eligibility rules."""
    target = _find(owner, request_id, _Party.OWNER)
    with transaction.atomic():
        _lock_profiles({target.player_id})
        convention = _lock_convention(target)
        request = _lock_request(target, convention)
        catch = _trio_catch(target, lock=True)
        now = _action_time(convention)
        if request.state == CatchRequestState.PENDING.value:
            return ActionResult(request, now)
        if request.state == CatchRequestState.INVALIDATED.value:
            raise RequestSupersededError
        if request.state != CatchRequestState.DECLINED.value:
            raise RequestStateChangedError(public_state(request.state))
        # A newer request or a catch decides first, so the client can tell that
        # the request is gone even after the undo window.
        if catch is not None or _has_newer_request(request):
            raise RequestSupersededError
        if undo and (
            request.decline_blocked
            or request.declined_at is None
            or now >= request.declined_at + UNDO_WINDOW
        ):
            raise UndoExpiredError
        request.state = CatchRequestState.PENDING
        request.declined_at = None
        request.decline_blocked = False
        request.save(update_fields=["state", "declined_at", "decline_blocked"])
        return ActionResult(request, now)


def _find(user: User, request_id: int, party: _Party) -> _Target:
    """Find the caller's request without a lock. Others' requests are not found."""
    rows = CatchRequest.objects.filter(pk=request_id)
    rows = (
        rows.filter(fursuit__owner=user)
        if party is _Party.OWNER
        else rows.filter(player=user)
    )
    row = rows.values_list(
        "player_id", "fursuit__owner_id", "fursuit_id", "convention_id"
    ).first()
    if row is None:
        raise RequestNotFoundError
    player_id, owner_id, fursuit_id, convention_id = row
    return _Target(request_id, player_id, owner_id, fursuit_id, convention_id)


def _lock_profiles(user_ids: set[int]) -> dict[int, PlayerProfile]:
    return {
        profile.user_id: profile
        for profile in PlayerProfile.objects.select_for_update()
        .filter(user_id__in=user_ids)
        .order_by("pk")
    }


def _lock_convention(target: _Target) -> Convention:
    return Convention.objects.select_for_update().get(pk=target.convention_id)


def _lock_request(target: _Target, convention: Convention) -> CatchRequest:
    request = (
        CatchRequest.objects.select_for_update().filter(pk=target.request_id).first()
    )
    if request is None:
        # Cleanup deleted the row after the lookup.
        raise RequestNotFoundError
    request.convention = convention
    return request


def _action_time(convention: Convention) -> datetime.datetime:
    """Read the one database time after every lock, then check the window."""
    now = database_now()
    if not review_window_open(convention, now):
        raise ReviewWindowClosedError
    return now


def _trio_blocks(target: _Target) -> QuerySet[CatchBlock]:
    return CatchBlock.objects.filter(
        player_id=target.player_id,
        fursuit_id=target.fursuit_id,
        convention_id=target.convention_id,
    )


def _approval_paused(
    profiles: dict[int, PlayerProfile],
    target: _Target,
    fursuit: Fursuit | None,
    convention: Convention,
) -> bool:
    if fursuit is None:  # pragma: no cover - PROTECT keeps the suit.
        return True
    return is_approval_paused(
        player_profile=profiles.get(target.player_id),
        owner_profile=profiles.get(target.owner_id),
        fursuit=fursuit,
        convention=convention,
    )


def _trio_catch(target: _Target, *, lock: bool) -> Catch | None:
    catches = Catch.objects.filter(
        catcher_user_id=target.player_id,
        fursuit_id=target.fursuit_id,
        convention_id=target.convention_id,
    ).select_related("fursuit")
    if lock:
        catches = catches.select_for_update(of=("self",))
    return catches.first()


def _has_newer_request(request: CatchRequest) -> bool:
    return (
        CatchRequest.objects.filter(
            player_id=request.player_id,
            fursuit_id=request.fursuit_id,
            convention_id=request.convention_id,
        )
        .filter(
            Q(requested_at__gt=request.requested_at)
            | Q(requested_at=request.requested_at, pk__gt=request.pk)
        )
        .exists()
    )


def _ensure_block(target: _Target, now: datetime.datetime) -> None:
    CatchBlock.objects.get_or_create(
        player_id=target.player_id,
        fursuit_id=target.fursuit_id,
        convention_id=target.convention_id,
        defaults={"created_at": now},
    )
