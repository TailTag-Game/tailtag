"""Clean, retain and list Staging simulation runs.

``cleanup`` deletes exactly the state a run's provisioned identities own, under a
closed-world attribution rule, and refuses with no writes when anything is
ambiguous. ``retain`` keeps a failed run's state and quarantines its slots, and
``retained`` lists the runs that are still clutter. Failures are fixed result
codes: no IDs, image keys, or handles reach a result or a log message.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Exists, Model, OuterRef, Q, QuerySet
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from rehearsal.models import StagingResetIdentity
from simulation_fixtures.models import (
    CLEANED,
    CONVENTION,
    ENROLLMENT,
    FURSUIT,
    PROVISIONED,
    REASONS,
    RETAINED,
    FixtureIdentity,
    FixtureObject,
    FixturePendingImage,
    FixtureRun,
)
from simulation_fixtures.services import (
    _POOL,  # pyright: ignore[reportPrivateUsage]
    _run_id,  # pyright: ignore[reportPrivateUsage]
    dirty_indexes,
)
from simulation_pool.models import AVAILABLE, QUARANTINED, PoolSlot

_LOGGER = logging.getLogger(__name__)
_ERROR_WARNING = "Fixture run cleanup failed."
_STORAGE_WARNING = "Fixture image deletion was not confirmed."

MAX_LISTED: Final = 100
_UNFINISHED: Final = "unfinished"
_LIVE_STATUSES: Final = (PROVISIONED, RETAINED)


@dataclass(frozen=True)
class Outcome:
    """A result code and, for ``PASS`` only, the fixed-shape data."""

    result: str
    data: dict[str, object] = field(default_factory=dict[str, object])


class _Failure(Exception):
    """A documented failure; raised inside a transaction to roll it back."""

    def __init__(self, result: str) -> None:
        super().__init__(result)
        self.result = result


def _refuse() -> _Failure:
    return _Failure("FAIL_ATTRIBUTION")


def _is_live(slot: PoolSlot, now: dt.datetime) -> bool:
    return slot.lease_expires_at is not None and slot.lease_expires_at > now


def _locked_run(pool: str, run_id: str) -> FixtureRun:
    """Lock the run; only a provisioned or retained run of this pool can proceed."""
    run = FixtureRun.objects.select_for_update().filter(run_id=run_id).first()
    if run is None:
        raise _Failure("FAIL_RUN_UNKNOWN")
    if run.pool != pool or run.status not in _LIVE_STATUSES:
        raise _refuse()
    return run


def _users_by_index(pool: str, indexes: list[int]) -> dict[int, User]:
    profiles = {
        profile.handle: profile.user
        for profile in PlayerProfile.objects.select_related("user").filter(
            handle__in=[f"sp_{pool}_{index}" for index in indexes]
        )
    }
    if any(f"sp_{pool}_{index}" not in profiles for index in indexes):
        raise _refuse()
    return {index: profiles[f"sp_{pool}_{index}"] for index in indexes}


def _ledger_enrollment_user_ids(run: FixtureRun) -> set[int]:
    """The owners and catchers: the users of the run's ledgered enrollments."""
    ledgered = list(
        FixtureObject.objects.filter(run=run, kind=ENROLLMENT).values_list(
            "object_id", flat=True
        )
    )
    user_ids = set(
        ConventionEnrollment.objects.filter(pk__in=ledgered).values_list(
            "user_id", flat=True
        )
    )
    if not ledgered or len(user_ids) != len(ledgered):
        raise _refuse()
    return user_ids


def _legacy_identities(run: FixtureRun) -> list[int]:
    """A run from before #223 recorded no identities; derive them from enrollments."""
    handle = re.compile(rf"sp_{run.pool}_(\d+)")
    user_ids = _ledger_enrollment_user_ids(run)
    handles = list(
        PlayerProfile.objects.filter(user_id__in=user_ids).values_list(
            "handle", flat=True
        )
    )
    matches = [handle.fullmatch(value or "") for value in handles]
    if len(matches) != len(user_ids) or not all(matches):
        raise _refuse()
    return sorted(int(match.group(1)) for match in matches if match is not None)


def _locked_slots(run: FixtureRun, indexes: list[int]) -> list[PoolSlot]:
    slots = list(
        PoolSlot.objects.select_for_update()
        .filter(pool=run.pool, index__in=indexes)
        .order_by("index")
    )
    if [slot.index for slot in slots] != sorted(indexes):
        raise _refuse()
    return slots


def _delete(queryset: QuerySet[Model]) -> int:
    deleted, _ = queryset.delete()
    return deleted


def _delete_run_state(run: FixtureRun, indexes: list[int]) -> None:
    """Delete the run's deletion set in PROTECT order and record the pending images."""
    users = _users_by_index(run.pool, indexes)
    provisioned_ids = _ledger_enrollment_user_ids(run)
    all_ids = [user.pk for user in users.values()]
    if not provisioned_ids <= set(all_ids):
        raise _refuse()
    extras = {
        index: user for index, user in users.items() if user.pk not in provisioned_ids
    }
    convention_ids = list(
        FixtureObject.objects.filter(run=run, kind=CONVENTION).values_list(
            "object_id", flat=True
        )
    )
    if len(convention_ids) != 1 or dirty_indexes(extras):
        raise _refuse()
    convention_id = convention_ids[0]
    in_other_convention = (
        ConventionEnrollment.objects.filter(user_id__in=all_ids)
        .exclude(convention_id=convention_id)
        .exists()
        or FursuitActivation.objects.filter(fursuit__owner_id__in=all_ids)
        .exclude(convention_id=convention_id)
        .exists()
        or Catch.objects.filter(catcher_user_id__in=all_ids)
        .exclude(convention_id=convention_id)
        .exists()
        or Catch.objects.filter(fursuit__owner_id__in=all_ids)
        .exclude(convention_id=convention_id)
        .exists()
    )
    if in_other_convention:
        raise _refuse()

    fursuits = Fursuit.objects.filter(owner_id__in=provisioned_ids)
    activations = FursuitActivation.objects.filter(
        Q(fursuit__in=fursuits) | Q(convention_id=convention_id)
    )
    keys = {
        key
        for key in (
            *FixtureObject.objects.filter(run=run, kind=FURSUIT).values_list(
                "media_key", flat=True
            ),
            *fursuits.values_list("photo_key", flat=True),
            *PlayerProfile.objects.filter(user_id__in=provisioned_ids).values_list(
                "avatar_key", flat=True
            ),
        )
        if key
    }
    shared = (
        Fursuit.objects.filter(photo_key__in=keys)
        .exclude(owner_id__in=provisioned_ids)
        .exists()
        or PlayerProfile.objects.filter(avatar_key__in=keys)
        .exclude(user_id__in=provisioned_ids)
        .exists()
        or StagingResetIdentity.objects.filter(media_key__in=keys).exists()
    )
    if shared:
        raise _refuse()

    try:
        # Every foreign key into these tables is PROTECT, so a row outside the set
        # that still references one of them blocks the delete and refuses the run.
        counts = {
            "catch": _delete(
                Catch.objects.filter(
                    Q(catcher_user_id__in=provisioned_ids)
                    | Q(fursuit__in=fursuits)
                    | Q(convention_id=convention_id)
                )
            ),
            "credential": _delete(
                FursuitCatchCredential.objects.filter(activation__in=activations)
            ),
            "session": _delete(
                FursuitCatchSession.objects.filter(activation__in=activations)
            ),
            "activation": _delete(activations),
            "enrollment": _delete(
                ConventionEnrollment.objects.filter(
                    Q(user_id__in=provisioned_ids) | Q(convention_id=convention_id)
                )
            ),
            "fursuit": _delete(fursuits),
            "convention": _delete(Convention.objects.filter(pk=convention_id)),
        }
    except ProtectedError:
        raise _refuse() from None
    PlayerProfile.objects.filter(user_id__in=provisioned_ids).update(avatar_key=None)
    FixtureObject.objects.filter(run=run).delete()
    FixturePendingImage.objects.bulk_create(
        [FixturePendingImage(run=run, key=key) for key in sorted(keys)]
    )
    run.cleanup_counts = {**counts, "image": len(keys)}
    run.save(update_fields=["cleanup_counts", "updated_at"])


def _database_phase(pool: str, run_id: str) -> tuple[FixtureRun, dict[str, int]]:
    """Check attribution and, until it has run once, delete the run's state."""
    with transaction.atomic():
        run = _locked_run(pool, run_id)
        recorded = sorted(
            FixtureIdentity.objects.filter(run=run).values_list("index", flat=True)
        )
        deleting = run.cleanup_counts is None
        legacy = deleting and not recorded
        indexes = _legacy_identities(run) if legacy else recorded
        now = timezone.now()
        if not indexes or any(
            slot.run_id not in (None, run.run_id) and _is_live(slot, now)
            for slot in _locked_slots(run, indexes)
        ):
            raise _refuse()
        if deleting:
            if legacy:
                # The ledger rows are deleted below; later phases need the identities.
                FixtureIdentity.objects.bulk_create(
                    [FixtureIdentity(run=run, index=index) for index in indexes]
                )
            _delete_run_state(run, indexes)
        return run, dict(run.cleanup_counts or {})


def _gone(key: str) -> bool:
    """Delete one image and report whether the store confirms it is gone."""
    try:
        default_storage.delete(key)
    except Exception:  # noqa: BLE001 - confirmation below decides, not the delete.
        _LOGGER.warning(_STORAGE_WARNING)
    try:
        return not default_storage.exists(key)
    except Exception:  # noqa: BLE001 - an unconfirmed object stays pending.
        _LOGGER.warning(_STORAGE_WARNING)
        return False


def _images_removed(run: FixtureRun) -> bool:
    """Try every pending key; a key leaves the list only once it is confirmed gone."""
    pending = FixturePendingImage.objects.filter(run=run).order_by("pk")
    removed = True
    for row in list(pending):
        if _gone(row.key):
            row.delete()
        else:
            removed = False
    return removed


def _verified(run: FixtureRun) -> bool:
    """The run's identities pass the provision dirty predicate.

    No row can still reference the deleted Convention: every foreign key to it is
    PROTECT, so its deletion in the database phase already proved that.
    """
    indexes = list(
        FixtureIdentity.objects.filter(run=run).values_list("index", flat=True)
    )
    try:
        return bool(indexes) and not dirty_indexes(_users_by_index(run.pool, indexes))
    except _Failure:
        return False


def _complete(run: FixtureRun) -> int:
    """Mark the run cleaned and free its slots; return how many slots changed."""
    with transaction.atomic():
        locked = FixtureRun.objects.select_for_update().get(pk=run.pk)
        if locked.status not in _LIVE_STATUSES:
            raise _refuse()
        now = timezone.now()
        changed = 0
        for slot in (
            PoolSlot.objects.select_for_update()
            .filter(
                pool=locked.pool,
                index__in=FixtureIdentity.objects.filter(run=locked).values("index"),
            )
            .order_by("index")
        ):
            readmit = slot.state == QUARANTINED
            expired = slot.lease_expires_at is not None and not _is_live(slot, now)
            if readmit or expired:
                # A lease that is live for this run stays: RELEASE clears it.
                slot.state = AVAILABLE
                if expired:
                    slot.run_id = None
                    slot.lease_expires_at = None
                slot.save()
                changed += 1
        locked.status = CLEANED
        locked.cleaned_at = now
        locked.save(update_fields=["status", "cleaned_at", "updated_at"])
        return changed


def _pool(value: object) -> str:
    if not isinstance(value, str) or _POOL.fullmatch(value) is None:
        raise ValueError("pool invalid")
    return value


def cleanup(pool: str, run_id: str) -> Outcome:
    """Delete a run's state and images, verify, and readmit its slots.

    The database phase is all-or-nothing and runs once; a rerun after a storage
    failure resumes at the images. Slots are freed only on a verified ``cleaned``.
    """
    pool, run_id = _pool(pool), _run_id(run_id)
    return _guarded(lambda: _cleanup(pool, run_id))


def _guarded(operation: Callable[[], Outcome]) -> Outcome:
    """Turn an unexpected failure into a fixed code; its transactions rolled back."""
    try:
        return operation()
    except Exception:  # noqa: BLE001 - report a fixed code, never the cause.
        _LOGGER.warning(_ERROR_WARNING)
        return Outcome("FAIL_ERROR")


def _cleanup(pool: str, run_id: str) -> Outcome:
    try:
        run, counts = _database_phase(pool, run_id)
    except _Failure as failure:
        return Outcome(failure.result)
    if not _images_removed(run):
        return Outcome("FAIL_STORAGE")
    if not _verified(run):
        return Outcome("FAIL_VERIFY")
    try:
        readmitted = _complete(run)
    except _Failure as failure:
        return Outcome(failure.result)
    return Outcome("PASS", {**counts, "readmitted": readmitted})


def retain(pool: str, run_id: str, reason: str) -> Outcome:
    """Keep a run's state: quarantine its live slots and mark it retained.

    Retaining a retained run is a pass that keeps its first reason.
    """
    pool, run_id = _pool(pool), _run_id(run_id)
    if reason not in REASONS:
        raise ValueError("reason invalid")
    return _guarded(lambda: _retain(pool, run_id, reason))


def _retain(pool: str, run_id: str, reason: str) -> Outcome:
    try:
        with transaction.atomic():
            run = _locked_run(pool, run_id)
            now = timezone.now()
            slots = list(
                PoolSlot.objects.select_for_update()
                .filter(
                    pool=pool,
                    state=AVAILABLE,
                    run_id=run_id,
                    lease_expires_at__gt=now,
                    index__in=FixtureIdentity.objects.filter(run=run).values("index"),
                )
                .order_by("index")
            )
            for slot in slots:
                slot.state = QUARANTINED
                slot.run_id = None
                slot.lease_expires_at = None
                slot.save()
            if run.status == PROVISIONED:
                run.status = RETAINED
                run.reason = reason
                run.save(update_fields=["status", "reason", "updated_at"])
    except _Failure as failure:
        return Outcome(failure.result)
    return Outcome("PASS", {"quarantined": len(slots)})


def _entry(run: FixtureRun, now: dt.datetime) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "pool": run.pool,
        "reason": run.reason or _UNFINISHED,
        "age_days": max(0, (now - run.created_at).days),
    }


def retained(*, now: dt.datetime | None = None) -> Outcome:
    """List retained runs, then unfinished ones, each oldest first (at most 100).

    An unfinished run is provisioned with no recorded slot still leased to it:
    a crashed run, or one from before #223.
    """
    return _guarded(lambda: _retained(now or timezone.now()))


def _retained(now: dt.datetime) -> Outcome:
    leased = PoolSlot.objects.filter(
        pool=OuterRef("run__pool"),
        index=OuterRef("index"),
        run_id=OuterRef("run__run_id"),
        state=AVAILABLE,
        lease_expires_at__gt=now,
    )
    live = FixtureIdentity.objects.filter(run=OuterRef("pk")).filter(Exists(leased))
    retained_runs = FixtureRun.objects.filter(status=RETAINED)
    unfinished_runs = FixtureRun.objects.filter(status=PROVISIONED).filter(
        ~Exists(live)
    )
    total = retained_runs.count(), unfinished_runs.count()
    if sum(total) > MAX_LISTED:
        return Outcome("FAIL_LIMIT")
    runs = [
        _entry(run, now)
        for queryset in (retained_runs, unfinished_runs)
        for run in queryset.order_by("created_at", "pk")
    ]
    return Outcome("PASS", {"runs": runs, "retained": total[0], "unfinished": total[1]})
