"""Blocks, cooldowns, and the per-player limit for catch submissions (#506).

The reusable TailTag contract is the source of truth: section "Cooldowns and
limits". The caller holds the submission locks, so every read here is
serialized for the submitting player.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Count, Max, Q

from catches.models import CatchBlock, CatchRequest
from observability.outcomes import Reason

SUBMISSION_FLOOR = datetime.timedelta(seconds=10)
FIRST_DECLINE_FLOOR = datetime.timedelta(seconds=10)
LATER_DECLINE_FLOOR = datetime.timedelta(minutes=10)


@dataclass(frozen=True)
class TrioHistory:
    """The trio values that the contract cooldown formula reads."""

    last_requested_at: datetime.datetime | None
    counted_declines: int
    last_declined_at: datetime.datetime | None


class SubmissionRefusedError(Exception):
    """HTTP 429 ``cooldown_active`` or ``rate_limited``.

    ``reason`` is the telemetry reason, which matches the public code here.
    """

    def __init__(self, reason: Reason, retry_after_seconds: int) -> None:
        super().__init__()
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds

    @property
    def code(self) -> str:
        return str(self.reason)


def earliest_next_submission(history: TrioHistory) -> datetime.datetime | None:
    """Return the later of the submission floor and the decline floor."""
    if history.last_requested_at is None:
        return None
    earliest = history.last_requested_at + SUBMISSION_FLOOR
    if history.counted_declines >= 1 and history.last_declined_at is not None:
        wait = (
            FIRST_DECLINE_FLOOR
            if history.counted_declines == 1
            else LATER_DECLINE_FLOOR
        )
        earliest = max(earliest, history.last_declined_at + wait)
    return earliest


def is_blocked(*, player_id: int, fursuit_id: int, convention_id: int) -> bool:
    return CatchBlock.objects.filter(
        player_id=player_id, fursuit_id=fursuit_id, convention_id=convention_id
    ).exists()


def check_submission_allowed(
    *, player_id: int, fursuit_id: int, convention_id: int, now: datetime.datetime
) -> None:
    """Raise ``SubmissionRefusedError`` while a cooldown or the limit applies.

    When both apply, the longer wait wins, so one retry is enough. A tie gives
    ``cooldown_active`` (#506 G8).
    """
    refusals: list[tuple[int, Reason]] = []
    cooldown_until = earliest_next_submission(
        trio_history(
            player_id=player_id, fursuit_id=fursuit_id, convention_id=convention_id
        )
    )
    if cooldown_until is not None and now < cooldown_until:
        refusals.append(
            (_retry_after_seconds(cooldown_until, now), Reason.COOLDOWN_ACTIVE)
        )
    limit_until = _limit_until(player_id=player_id, now=now)
    if limit_until is not None and now < limit_until:
        refusals.append((_retry_after_seconds(limit_until, now), Reason.RATE_LIMITED))
    refusal = pick_refusal(refusals)
    if refusal is not None:
        raise refusal


def pick_refusal(refusals: list[tuple[int, Reason]]) -> SubmissionRefusedError | None:
    """Pick the refusal with the larger retry value. A tie gives the cooldown.

    The comparison uses the rounded seconds that the client sees (#506 G8).
    """
    if not refusals:
        return None
    seconds, reason = max(
        refusals, key=lambda item: (item[0], item[1] == Reason.COOLDOWN_ACTIVE)
    )
    return SubmissionRefusedError(reason, seconds)


def trio_history(*, player_id: int, fursuit_id: int, convention_id: int) -> TrioHistory:
    values = CatchRequest.objects.filter(
        player_id=player_id, fursuit_id=fursuit_id, convention_id=convention_id
    ).aggregate(
        last_requested_at=Max("requested_at"),
        counted_declines=Count("pk", filter=Q(declined_at__isnull=False)),
        last_declined_at=Max("declined_at"),
    )
    return TrioHistory(
        last_requested_at=values["last_requested_at"],
        counted_declines=int(values["counted_declines"]),
        last_declined_at=values["last_declined_at"],
    )


def _limit_until(*, player_id: int, now: datetime.datetime) -> datetime.datetime | None:
    """Return when the player's rolling window next has room, if it is full."""
    limit = int(settings.CATCH_REQUEST_LIMIT_COUNT)
    window = datetime.timedelta(
        seconds=int(settings.CATCH_REQUEST_LIMIT_WINDOW_SECONDS)
    )
    # The limit-th newest request in the window leaves it last among the ones
    # that fill it. Refused submissions create no row, so they never count.
    times = list(
        CatchRequest.objects.filter(player_id=player_id, requested_at__gt=now - window)
        .order_by("-requested_at")
        .values_list("requested_at", flat=True)[:limit]
    )
    if len(times) < limit:
        return None
    return times[-1] + window


def _retry_after_seconds(until: datetime.datetime, now: datetime.datetime) -> int:
    return max(1, math.ceil((until - now).total_seconds()))
