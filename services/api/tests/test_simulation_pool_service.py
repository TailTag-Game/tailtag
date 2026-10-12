"""Acceptance coverage for the Staging synthetic identity pool lease store (#219)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import pytest

from simulation_pool import services
from simulation_pool.models import PoolSlot

NOW = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.UTC)
RUN_A = "aaaaaaaa-1111-4111-8111-111111111111"
RUN_B = "22222222-2222-4222-8222-222222222222"
POOL = "alpha"

pytestmark = pytest.mark.django_db


def slot(pool: str, index: int) -> PoolSlot:
    return PoolSlot.objects.get(pool=pool, index=index)


def test_register_creates_only_missing_slots_and_never_shrinks() -> None:
    """P-1: provisioning is idempotent, expands, and never deletes a slot."""
    assert services.register(POOL, 3) == 3
    assert services.register(POOL, 3) == 0
    assert services.register(POOL, 5) == 2
    assert services.register(POOL, 2) == 0
    assert services.register("beta", 1) == 1

    assert sorted(
        PoolSlot.objects.filter(pool=POOL).values_list("index", flat=True)
    ) == [0, 1, 2, 3, 4]
    assert all(
        row.state == "available" and row.run_id is None
        for row in PoolSlot.objects.all()
    )


def test_allocate_leases_lowest_indexes_and_isolates_pools_and_runs() -> None:
    """P-2: lowest available slots are leased with the requested expiry."""
    services.register(POOL, 4)
    services.register("beta", 2)

    assert services.allocate(POOL, RUN_A, 2, 600, now=NOW) == (0, 1)
    assert services.allocate(POOL, RUN_B, 2, 600, now=NOW) == (2, 3)

    for index in (0, 1):
        row = slot(POOL, index)
        assert row.run_id == RUN_A
        assert row.lease_expires_at == NOW + dt.timedelta(seconds=600)
    assert slot(POOL, 2).run_id == RUN_B
    assert PoolSlot.objects.filter(pool="beta", run_id__isnull=False).count() == 0


def test_short_pool_fails_without_leasing_anything() -> None:
    """P-2: allocation is all-or-nothing, and shortfall excludes unusable slots."""
    services.register(POOL, 5)
    services.allocate(POOL, RUN_B, 1, 600, now=NOW)  # live lease on 0
    services.allocate(POOL, RUN_B, 1, 600, now=NOW)  # live lease on 1
    services.quarantine(POOL, 1, RUN_B, now=NOW)  # quarantined 1
    before = list(PoolSlot.objects.order_by("index").values())

    with pytest.raises(services.InsufficientPool) as caught:
        services.allocate(POOL, RUN_A, 4, 600, now=NOW)

    assert caught.value.available == 3
    assert list(PoolSlot.objects.order_by("index").values()) == before


@pytest.mark.parametrize(
    ("expires_offset_seconds", "reclaimable"),
    ((1, False), (0, True), (-1, True)),
    ids=("live-lease-is-protected", "expiry-instant-reclaims", "expired-reclaims"),
)
def test_lease_expiry_decides_whether_another_run_can_take_the_slot(
    expires_offset_seconds: int, reclaimable: bool
) -> None:
    """P-3: expired leases are reclaimable and live leases are never stolen."""
    services.register(POOL, 1)
    PoolSlot.objects.update(
        run_id=RUN_A,
        lease_expires_at=NOW + dt.timedelta(seconds=expires_offset_seconds),
    )

    if reclaimable:
        assert services.allocate(POOL, RUN_B, 1, 600, now=NOW) == (0,)
        assert slot(POOL, 0).run_id == RUN_B
    else:
        with pytest.raises(services.InsufficientPool):
            services.allocate(POOL, RUN_B, 1, 600, now=NOW)
        assert slot(POOL, 0).run_id == RUN_A


def test_heartbeat_extends_only_the_runs_live_leases() -> None:
    """P-3: a heartbeat keeps this run's leases alive and touches nothing else."""
    services.register(POOL, 3)
    services.allocate(POOL, RUN_A, 2, 60, now=NOW)  # 0, 1
    services.allocate(POOL, RUN_B, 1, 60, now=NOW)  # 2
    later = NOW + dt.timedelta(seconds=30)

    assert services.heartbeat(POOL, RUN_A, 600, now=later) == 2

    assert slot(POOL, 0).lease_expires_at == later + dt.timedelta(seconds=600)
    assert slot(POOL, 1).lease_expires_at == later + dt.timedelta(seconds=600)
    assert slot(POOL, 2).lease_expires_at == NOW + dt.timedelta(seconds=60)
    after_expiry = NOW + dt.timedelta(seconds=10_000)
    assert services.heartbeat(POOL, RUN_A, 600, now=after_expiry) == 0


def test_release_clears_only_the_runs_leases_and_frees_them() -> None:
    """P-3: release ends exactly this run's leases and is repeatable."""
    services.register(POOL, 3)
    services.allocate(POOL, RUN_A, 2, 600, now=NOW)
    services.allocate(POOL, RUN_B, 1, 600, now=NOW)

    assert services.release(POOL, RUN_A) == 2
    assert services.release(POOL, RUN_A) == 0

    for index in (0, 1):
        row = slot(POOL, index)
        assert (row.run_id, row.lease_expires_at) == (None, None)
    assert slot(POOL, 2).run_id == RUN_B
    assert services.allocate(POOL, RUN_B, 2, 600, now=NOW) == (0, 1)


def test_quarantine_excludes_slot_until_readmitted() -> None:
    """P-6: a broken identity is never allocated until explicitly readmitted."""
    services.register(POOL, 2)
    services.allocate(POOL, RUN_A, 2, 600, now=NOW)

    services.quarantine(POOL, 0, RUN_A, now=NOW)

    row = slot(POOL, 0)
    assert (row.state, row.run_id, row.lease_expires_at) == ("quarantined", None, None)
    assert services.release(POOL, RUN_A) == 1  # only slot 1 is still leased
    assert services.allocate(POOL, RUN_B, 1, 600, now=NOW) == (1,)
    with pytest.raises(services.InsufficientPool):
        services.allocate(POOL, RUN_A, 1, 600, now=NOW)

    services.readmit(POOL, 0)

    assert slot(POOL, 0).state == "available"
    assert services.allocate(POOL, RUN_A, 1, 600, now=NOW) == (0,)


@pytest.mark.parametrize(
    "caller",
    (
        lambda: services.quarantine(POOL, 0, RUN_B, now=NOW),
        lambda: services.quarantine(POOL, 1, RUN_A, now=NOW),
    ),
    ids=("leased-by-another-run", "not-leased"),
)
def test_quarantine_requires_the_callers_live_lease(
    caller: Callable[[], None],
) -> None:
    """P-6: a run cannot quarantine a slot it does not hold."""
    services.register(POOL, 2)
    services.allocate(POOL, RUN_A, 1, 600, now=NOW)
    before = list(PoolSlot.objects.order_by("index").values())

    with pytest.raises(services.SlotNotLeased):
        caller()

    assert list(PoolSlot.objects.order_by("index").values()) == before


def test_readmit_unknown_slot_is_reported() -> None:
    """P-6: recovery of a slot that was never registered is a clear error."""
    services.register(POOL, 1)

    with pytest.raises(services.UnknownSlot):
        services.readmit(POOL, 7)


def test_status_counts_available_leased_and_quarantined_slots() -> None:
    """P-2/P-6: status reports counts only, treating expired leases as available."""
    services.register(POOL, 5)
    services.allocate(POOL, RUN_A, 3, 600, now=NOW)  # 0, 1, 2
    services.quarantine(POOL, 2, RUN_A, now=NOW)
    PoolSlot.objects.filter(index=1).update(lease_expires_at=NOW)  # expired

    status = services.status(POOL, now=NOW)

    assert (status.total, status.available, status.leased, status.quarantined) == (
        5,
        3,
        1,
        1,
    )


_VALID_ARGUMENTS: dict[str, Any] = {
    "pool": POOL,
    "run_id": RUN_A,
    "count": 1,
    "size": 1,
    "ttl_seconds": 600,
    "index": 0,
}
_OPERATIONS: dict[str, tuple[Callable[..., object], tuple[str, ...]]] = {
    "register": (services.register, ("pool", "size")),
    "allocate": (services.allocate, ("pool", "run_id", "count", "ttl_seconds")),
    "heartbeat": (services.heartbeat, ("pool", "run_id", "ttl_seconds")),
    "release": (services.release, ("pool", "run_id")),
    "quarantine": (services.quarantine, ("pool", "index", "run_id")),
    "readmit": (services.readmit, ("pool", "index")),
    "status": (services.status, ("pool",)),
}
_INVALID_VALUES: dict[str, tuple[Any, ...]] = {
    "pool": ("", "Alpha", "alpha_1", "a" * 13, "../etc"),
    "run_id": (
        RUN_A.upper(),
        RUN_A.replace("-", ""),
        "not-a-uuid",
        RUN_A + "\n",
        "",
    ),
    "count": (0, 1001),
    "size": (0, 1001),
    "ttl_seconds": (59, 86401),
    "index": (-1,),
}


_REPRESENTATIVE_INVALID = {
    name: values[0] for name, values in _INVALID_VALUES.items()
} | {"run_id": RUN_A.upper()}
# Every invalid value against one operation that takes all the validated kinds,
# plus one invalid value for each remaining (operation, parameter) pair.
_INVALID_CASES = [
    ("allocate", parameter, value)
    for parameter in _OPERATIONS["allocate"][1]
    for value in _INVALID_VALUES[parameter]
] + [
    (operation, parameter, _REPRESENTATIVE_INVALID[parameter])
    for operation, (_, parameters) in _OPERATIONS.items()
    if operation != "allocate"
    for parameter in parameters
]


@pytest.mark.parametrize(("operation", "parameter", "value"), _INVALID_CASES)
def test_invalid_inputs_are_rejected_before_any_change(
    operation: str, parameter: str, value: Any
) -> None:
    """P-7/P-12: untrusted values never reach a lease, row, or query."""
    services.register(POOL, 3)
    services.allocate(POOL, RUN_A, 1, 600, now=NOW)
    before = list(PoolSlot.objects.order_by("pool", "index").values())
    function, parameters = _OPERATIONS[operation]
    arguments = {**_VALID_ARGUMENTS, parameter: value}

    with pytest.raises(ValueError):
        function(*(arguments[name] for name in parameters))

    assert list(PoolSlot.objects.order_by("pool", "index").values()) == before


def test_inclusive_bounds_and_maximum_pool_name_are_accepted() -> None:
    """Boundary partition: the documented limits themselves are valid."""
    long_pool = "a1b2c3d4e5f6"
    services.register(long_pool, 2)

    assert services.allocate(long_pool, RUN_A, 1, 60, now=NOW) == (0,)
    assert services.allocate(long_pool, RUN_B, 1, 86400, now=NOW) == (1,)
