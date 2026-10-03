"""Lease operations for the Staging synthetic identity pool.

Every function validates its inputs before touching the database and runs as one
transaction. Errors never carry request values.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from simulation_pool.models import AVAILABLE, QUARANTINED, PoolSlot

_POOL = re.compile(r"[a-z0-9]{1,12}")
_MAX_SLOTS = 1000
_MIN_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 86400


class InsufficientPool(Exception):
    """Fewer usable slots than requested; carries the usable count only."""

    def __init__(self, available: int) -> None:
        super().__init__("insufficient pool")
        self.available = available


class SlotNotLeased(Exception):
    """The caller does not hold a live lease on the slot."""


class UnknownSlot(Exception):
    """The slot was never registered."""


@dataclass(frozen=True)
class PoolStatus:
    """Counts only: no indexes, run IDs, or identities."""

    total: int
    available: int
    leased: int
    quarantined: int


def _pool(value: object) -> str:
    if not isinstance(value, str) or _POOL.fullmatch(value) is None:
        raise ValueError("pool invalid")
    return value


def _run_id(value: object) -> str:
    try:
        if isinstance(value, str) and str(uuid.UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ValueError("run_id invalid")


def _integer(value: object, minimum: int, maximum: int | None, name: str) -> int:
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise ValueError(f"{name} invalid")
    return value


def _count(value: object) -> int:
    return _integer(value, 1, _MAX_SLOTS, "count")


def _ttl(value: object) -> dt.timedelta:
    return dt.timedelta(
        seconds=_integer(value, _MIN_TTL_SECONDS, _MAX_TTL_SECONDS, "ttl_seconds")
    )


def _index(value: object) -> int:
    return _integer(value, 0, None, "index")


def register(pool: str, size: int) -> int:
    """Create the missing slots up to ``size`` and return how many were created."""
    pool = _pool(pool)
    size = _count(size)
    with transaction.atomic():
        existing = set(
            PoolSlot.objects.filter(pool=pool).values_list("index", flat=True)
        )
        missing = [index for index in range(size) if index not in existing]
        PoolSlot.objects.bulk_create(
            [PoolSlot(pool=pool, index=index) for index in missing],
            ignore_conflicts=True,
        )
    return len(missing)


def allocate(
    pool: str,
    run_id: str,
    count: int,
    ttl_seconds: int,
    *,
    now: dt.datetime | None = None,
) -> tuple[int, ...]:
    """Lease the lowest ``count`` usable slots to the run, all or none."""
    pool = _pool(pool)
    run_id = _run_id(run_id)
    count = _count(count)
    ttl = _ttl(ttl_seconds)
    now = now or timezone.now()
    with transaction.atomic():
        slots = list(
            PoolSlot.objects.select_for_update(skip_locked=True)
            .filter(pool=pool, state=AVAILABLE)
            .filter(Q(run_id__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("index")[:count]
        )
        if len(slots) < count:
            raise InsufficientPool(len(slots))
        PoolSlot.objects.filter(pk__in=[slot.pk for slot in slots]).update(
            run_id=run_id, lease_expires_at=now + ttl, updated_at=now
        )
    return tuple(slot.index for slot in slots)


def heartbeat(
    pool: str, run_id: str, ttl_seconds: int, *, now: dt.datetime | None = None
) -> int:
    """Extend the run's live leases and return how many were extended."""
    pool = _pool(pool)
    run_id = _run_id(run_id)
    ttl = _ttl(ttl_seconds)
    now = now or timezone.now()
    with transaction.atomic():
        return PoolSlot.objects.filter(
            pool=pool, run_id=run_id, lease_expires_at__gt=now
        ).update(lease_expires_at=now + ttl, updated_at=now)


def release(pool: str, run_id: str) -> int:
    """Clear every lease the run holds and return how many were cleared."""
    pool = _pool(pool)
    run_id = _run_id(run_id)
    with transaction.atomic():
        return PoolSlot.objects.filter(pool=pool, run_id=run_id).update(
            run_id=None, lease_expires_at=None, updated_at=timezone.now()
        )


def quarantine(
    pool: str, index: int, run_id: str, *, now: dt.datetime | None = None
) -> None:
    """Exclude a slot the run holds live from allocation and clear its lease."""
    pool = _pool(pool)
    index = _index(index)
    run_id = _run_id(run_id)
    now = now or timezone.now()
    with transaction.atomic():
        slot = _locked_slot(pool, index)
        if (
            slot.run_id != run_id
            or slot.lease_expires_at is None
            or slot.lease_expires_at <= now
        ):
            raise SlotNotLeased
        slot.state = QUARANTINED
        slot.run_id = None
        slot.lease_expires_at = None
        slot.save()


def readmit(pool: str, index: int) -> None:
    """Make a quarantined slot allocatable again."""
    pool = _pool(pool)
    index = _index(index)
    with transaction.atomic():
        slot = _locked_slot(pool, index)
        slot.state = AVAILABLE
        slot.save()


def status(pool: str, *, now: dt.datetime | None = None) -> PoolStatus:
    """Count slots; an expired lease counts as available."""
    pool = _pool(pool)
    now = now or timezone.now()
    counts = PoolSlot.objects.filter(pool=pool).aggregate(
        total=Count("pk"),
        quarantined=Count("pk", filter=Q(state=QUARANTINED)),
        leased=Count("pk", filter=Q(state=AVAILABLE, lease_expires_at__gt=now)),
    )
    total, quarantined, leased = (
        counts["total"],
        counts["quarantined"],
        counts["leased"],
    )
    return PoolStatus(
        total=total,
        available=total - quarantined - leased,
        leased=leased,
        quarantined=quarantined,
    )


def _locked_slot(pool: str, index: int) -> PoolSlot:
    try:
        return PoolSlot.objects.select_for_update().get(pool=pool, index=index)
    except PoolSlot.DoesNotExist:
        raise UnknownSlot from None
