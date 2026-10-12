"""Real PostgreSQL concurrency acceptance for synthetic identity pool allocation."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from django.db import close_old_connections, connection, transaction

from simulation_pool import services
from simulation_pool.models import PoolSlot

POOL = "race"
_TIMEOUT_SECONDS = 20.0

pytestmark = pytest.mark.django_db(transaction=True)


def _run_id() -> str:
    return str(uuid.uuid4())


def test_concurrent_allocations_never_lease_a_slot_to_two_runs() -> None:
    """P-2: simultaneous runs get disjoint all-or-nothing leases."""
    services.register(POOL, 6)
    workers = 4
    barrier = Barrier(workers)

    def allocate(run_id: str) -> tuple[str, tuple[int, ...] | int]:
        close_old_connections()
        try:
            barrier.wait(timeout=_TIMEOUT_SECONDS)
            return run_id, services.allocate(POOL, run_id, 2, 600)
        except services.InsufficientPool as shortage:
            return run_id, shortage.available
        finally:
            connection.close()

    run_ids = [_run_id() for _ in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        outcomes = [
            future.result(timeout=_TIMEOUT_SECONDS)
            for future in [executor.submit(allocate, run_id) for run_id in run_ids]
        ]

    granted = {
        run_id: indexes for run_id, indexes in outcomes if isinstance(indexes, tuple)
    }
    assert granted, "at least one run must be able to allocate"
    assert all(len(indexes) == 2 for indexes in granted.values())
    leased = [index for indexes in granted.values() for index in indexes]
    assert len(leased) == len(set(leased))
    stored = {
        (row.index, row.run_id)
        for row in PoolSlot.objects.filter(pool=POOL, run_id__isnull=False)
    }
    assert stored == {
        (index, run_id) for run_id, indexes in granted.items() for index in indexes
    }


def test_allocation_skips_slots_locked_by_another_transaction() -> None:
    """P-2: a locked slot is neither waited on nor double-leased."""
    services.register(POOL, 4)
    locked = Event()
    release_lock = Event()

    def hold_first_two_slots() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                rows = list(
                    PoolSlot.objects.select_for_update()
                    .filter(pool=POOL, index__in=(0, 1))
                    .order_by("index")
                )
                assert len(rows) == 2
                locked.set()
                assert release_lock.wait(timeout=_TIMEOUT_SECONDS)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        holder = executor.submit(hold_first_two_slots)
        try:
            assert locked.wait(timeout=_TIMEOUT_SECONDS)
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '3s'")

            assert services.allocate(POOL, _run_id(), 2, 600) == (2, 3)
            with pytest.raises(services.InsufficientPool):
                services.allocate(POOL, _run_id(), 1, 600)
        finally:
            release_lock.set()
            holder.result(timeout=_TIMEOUT_SECONDS)

    assert PoolSlot.objects.filter(pool=POOL, run_id__isnull=False).count() == 2
