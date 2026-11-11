"""Convention local time zones and the catch request review deadline (#503).

The frozen contract is
docs/specs/2026-11-09-reusable-tailtag-catch-request-contract.md, section
"Convention review deadline".
"""

from __future__ import annotations

import datetime
import functools
import zoneinfo
from typing import TYPE_CHECKING

from django.db import connection

if TYPE_CHECKING:
    from conventions.models import Convention

_REVIEW_DAYS_AFTER_END = 3


@functools.cache
def time_zone_names() -> frozenset[str]:
    """Return every IANA zone name that the pinned tzdata package knows."""
    return frozenset(zoneinfo.available_timezones())


def compute_review_deadline(
    end_date: datetime.date, time_zone: str
) -> datetime.datetime:
    """Return the start of the third local calendar day after ``end_date``, in UTC.

    ``fold=0`` gives the first occurrence of a repeated midnight. For a skipped
    midnight it applies the offset before the gap, which is the first instant
    at or after local midnight.
    """
    local_day = end_date + datetime.timedelta(days=_REVIEW_DAYS_AFTER_END)
    local_midnight = datetime.datetime.combine(
        local_day, datetime.time.min, tzinfo=zoneinfo.ZoneInfo(time_zone)
    )
    return local_midnight.astimezone(datetime.UTC)


def database_now() -> datetime.datetime:
    """Return the database clock with ``clock_timestamp()``.

    Call it after taking row locks. The contract forbids ``now()``, which is
    the transaction start time, and the application clock for window checks.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def review_window_open(convention: Convention, at: datetime.datetime) -> bool:
    """Return whether the review window is open at ``at``.

    An unknown zone keeps the window closed. The deadline wins a tie.
    """
    deadline = convention.review_deadline_at
    return deadline is not None and at < deadline


def review_deadline_local_date(convention: Convention) -> datetime.date | None:
    """Return the local calendar day that starts at the stored deadline."""
    if convention.time_zone is None or convention.review_deadline_at is None:
        return None
    zone = zoneinfo.ZoneInfo(convention.time_zone)
    return convention.review_deadline_at.astimezone(zone).date()


def apply_review_schedule(
    convention: Convention,
    *,
    end_date: datetime.date,
    time_zone: str | None,
) -> None:
    """Set the end date, zone, and deadline under the contract change rules.

    A stored deadline at or before the database time is permanent, so the new
    date or zone is saved and the deadline does not move. Otherwise the
    deadline is recomputed, and a past value closes the window at once.

    When the convention already has a deadline, the caller must hold the
    Convention row lock.
    """
    stored = convention.review_deadline_at
    closed = stored is not None and database_now() >= stored
    convention.end_date = end_date
    convention.time_zone = time_zone
    if closed:
        return
    convention.review_deadline_at = (
        None if time_zone is None else compute_review_deadline(end_date, time_zone)
    )
