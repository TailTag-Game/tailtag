"""Provision and report a simulation run's synthetic Convention state.

``provision`` acts through the existing domain services as the pool identities
leased to the run, and records every object it creates in the run ledger.
Documented failures are returned as result codes; none carries request values.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count

from accounts.models import User
from catches.models import Catch
from conventions import services as convention_services
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from fursuits import services as fursuit_services
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from simulation_fixtures import images
from simulation_fixtures.models import (
    ACTIVATION,
    CONVENTION,
    ENROLLMENT,
    FAILED,
    FURSUIT,
    KINDS,
    PROVISIONED,
    FixtureIdentity,
    FixtureObject,
    FixtureRun,
)
from simulation_pool import services as pool_services
from simulation_pool.models import AVAILABLE, PoolSlot

_LOGGER = logging.getLogger(__name__)
_CLEANUP_WARNING = "Fixture image cleanup failed after a rolled-back provision."

_POOL = re.compile(r"[a-z0-9]{1,12}")
_MAX_INDEX: Final = 2**31 - 1  # PoolSlot.index is a PositiveIntegerField.
_OWNERS: Final = (1, 50)
_CATCHERS: Final = (1, 200)
_EXTRAS: Final = (0, 10)
_FURSUITS_PER_OWNER: Final = (1, 5)

# Service-defined rejections of the requested state; anything else is an error.
_DOMAIN_REJECTIONS: Final = (
    convention_services.ConventionParticipationIneligibleError,
    convention_services.ConventionNotEligibleForEnrollmentError,
    convention_services.ConventionNotEnrolledError,
    convention_services.ConventionNotActiveError,
    convention_services.FursuitActivationNotEligibleError,
    convention_services.ConventionPlayabilityBoundaryError,
    fursuit_services.FursuitWriteIneligibleError,
    ValidationError,
)


@dataclass(frozen=True)
class ProvisionResult:
    """A result code with counts only: no IDs, handles, or media keys."""

    result: str
    counts: dict[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True)
class RunStatus:
    """A run's ledger status and object counts per kind."""

    status: str
    counts: dict[str, int]


class _Rejected(Exception):
    """A documented failure decided before any creation step."""

    def __init__(self, result: str, dirty: Sequence[int] = ()) -> None:
        super().__init__(result)
        self.result = result
        self.dirty = tuple(dirty)


class _CreationFailed(Exception):
    """A creation step failed; carries the cause for classification only."""

    def __init__(self, cause: Exception) -> None:
        super().__init__("creation failed")
        self.cause = cause


def _run_id(value: object) -> str:
    try:
        if isinstance(value, str) and str(uuid.UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ValueError("run_id invalid")


def _indexes(value: object, bounds: tuple[int, int]) -> list[int]:
    items = (
        list(cast(Sequence[object], value))
        if isinstance(value, (list, tuple))
        else None
    )
    if (
        items is None
        or not bounds[0] <= len(items) <= bounds[1]
        or not all(type(item) is int and 0 <= item <= _MAX_INDEX for item in items)
    ):
        raise ValueError("indexes invalid")
    return cast(list[int], items)


def _validated(
    pool: object,
    run_id: object,
    owners: object,
    catchers: object,
    fursuits_per_owner: object,
    extras: object,
) -> tuple[str, str, list[int], list[int], int, list[int]]:
    if not isinstance(pool, str) or _POOL.fullmatch(pool) is None:
        raise ValueError("pool invalid")
    owner_indexes = _indexes(owners, _OWNERS)
    catcher_indexes = _indexes(catchers, _CATCHERS)
    extra_indexes = _indexes(extras, _EXTRAS)
    combined = owner_indexes + catcher_indexes + extra_indexes
    if len(set(combined)) != len(combined):
        raise ValueError("indexes overlap")
    if (
        type(fursuits_per_owner) is not int
        or not _FURSUITS_PER_OWNER[0] <= fursuits_per_owner <= _FURSUITS_PER_OWNER[1]
    ):
        raise ValueError("fursuits_per_owner invalid")
    return (
        pool,
        _run_id(run_id),
        owner_indexes,
        catcher_indexes,
        fursuits_per_owner,
        extra_indexes,
    )


def provision(
    pool: str,
    run_id: str,
    owners: Sequence[int],
    catchers: Sequence[int],
    fursuits_per_owner: int,
    extras: Sequence[int] = (),
) -> ProvisionResult:
    """Create the run's Convention, enrollments, fursuits, and activations.

    ``extras`` are leased identities that get no state; they are bound, dirty-checked
    and recorded like owners and catchers. Everything is written in one transaction.
    A failure after creation starts rolls it back, deletes the images it stored, and
    records a ``failed`` run.
    """
    try:
        (
            pool,
            run_id,
            owner_indexes,
            catcher_indexes,
            fursuits_per_owner,
            extra_indexes,
        ) = _validated(pool, run_id, owners, catchers, fursuits_per_owner, extras)
    except ValueError:
        return ProvisionResult("FAIL_REQUEST")
    stored_keys: list[str] = []
    try:
        with transaction.atomic():
            leased = owner_indexes + catcher_indexes + extra_indexes
            users = _bind_identities(pool, run_id, leased)
            try:
                counts = _create(
                    pool,
                    run_id,
                    [users[index] for index in owner_indexes],
                    [users[index] for index in catcher_indexes],
                    fursuits_per_owner,
                    stored_keys,
                    leased,
                )
            except Exception as error:  # noqa: BLE001 - classified after rollback.
                raise _CreationFailed(error) from None
    except _Rejected as rejected:
        if not rejected.dirty:
            return ProvisionResult(rejected.result)
        # The transaction above wrote nothing; each quarantine commits on its own.
        try:
            for index in rejected.dirty:
                pool_services.quarantine(pool, index, run_id)
        except (pool_services.SlotNotLeased, pool_services.UnknownSlot):
            return ProvisionResult("FAIL_LEASE")
        return ProvisionResult("FAIL_DIRTY", {"quarantined": len(rejected.dirty)})
    except _CreationFailed as failed:
        _discard_images(stored_keys)
        with transaction.atomic():
            FixtureRun.objects.get_or_create(
                run_id=run_id, defaults={"pool": pool, "status": FAILED}
            )
        rejection = isinstance(failed.cause, _DOMAIN_REJECTIONS)
        return ProvisionResult("FAIL_INVARIANT" if rejection else "FAIL_ERROR")
    return ProvisionResult("PASS", counts)


def status(run_id: str) -> RunStatus | None:
    """Report a run's ledger status and counts, or ``None`` if it never ran."""
    run_id = _run_id(run_id)
    run = FixtureRun.objects.filter(run_id=run_id).first()
    if run is None:
        return None
    grouped = dict(
        FixtureObject.objects.filter(run=run)
        .values_list("kind")
        .annotate(total=Count("pk"))
    )
    return RunStatus(run.status, {kind: grouped.get(kind, 0) for kind in KINDS})


def _leased_to(slot: PoolSlot, run_id: str, now: dt.datetime) -> bool:
    return (
        slot.state == AVAILABLE
        and slot.run_id == run_id
        and slot.lease_expires_at is not None
        and slot.lease_expires_at > now
    )


def _bind_identities(pool: str, run_id: str, indexes: list[int]) -> dict[int, User]:
    """Lock the run's slots and resolve each to its onboarded, clean identity."""
    slots = {
        slot.index: slot
        for slot in PoolSlot.objects.select_for_update()
        .filter(pool=pool, index__in=indexes)
        .order_by("index")
    }
    if FixtureRun.objects.filter(run_id=run_id).exists():
        raise _Rejected("FAIL_RUN_EXISTS")
    now = dt.datetime.now(dt.UTC)
    if not all(
        index in slots and _leased_to(slots[index], run_id, now) for index in indexes
    ):
        raise _Rejected("FAIL_LEASE")
    profiles = {
        profile.handle: profile
        for profile in PlayerProfile.objects.select_related("user").filter(
            handle__in=[f"sp_{pool}_{index}" for index in indexes],
            onboarding_completed_at__isnull=False,
        )
    }
    if any(f"sp_{pool}_{index}" not in profiles for index in indexes):
        raise _Rejected("FAIL_LEASE")
    users = {index: profiles[f"sp_{pool}_{index}"].user for index in indexes}
    dirty = dirty_indexes(users)
    if dirty:
        raise _Rejected("FAIL_DIRTY", dirty)
    return users


def dirty_indexes(users: Mapping[int, User]) -> list[int]:
    """The indexes whose identity owns or has made anything a run could leave."""
    # Catch sessions belong to the identity's fursuits, so owning none rules them out.
    user_ids = [user.pk for user in users.values()]
    dirty_ids = (
        set(
            Fursuit.objects.filter(owner_id__in=user_ids).values_list(
                "owner_id", flat=True
            )
        )
        | set(
            ConventionEnrollment.objects.filter(user_id__in=user_ids).values_list(
                "user_id", flat=True
            )
        )
        | set(
            PlayerProfile.objects.filter(
                user_id__in=user_ids, avatar_key__isnull=False
            ).values_list("user_id", flat=True)
        )
        | set(
            Catch.objects.filter(catcher_user_id__in=user_ids).values_list(
                "catcher_user_id", flat=True
            )
        )
    )
    return sorted(index for index, user in users.items() if user.pk in dirty_ids)


def _create(
    pool: str,
    run_id: str,
    owners: list[User],
    catchers: list[User],
    fursuits_per_owner: int,
    stored_keys: list[str],
    leased: list[int],
) -> dict[str, int]:
    """Create the run state and its ledger; record each stored image key at once."""
    today = dt.datetime.now(dt.UTC).date()
    name = f"Sim {run_id[:8]}"
    start_date, end_date = today, today + dt.timedelta(days=1)
    convention = Convention(
        name=name,
        status=ConventionStatus.DRAFT,
        start_date=start_date,
        end_date=end_date,
    )
    convention.full_clean()
    convention.save()
    convention_services.set_convention_admin_state(
        convention_id=convention.pk,
        name=name,
        status=ConventionStatus.ACTIVE.value,
        start_date=start_date,
        end_date=end_date,
    )
    enrollment_ids = [
        convention_services.enroll_in_convention(
            user, convention_id=convention.pk, set_active=True
        )[0].pk
        for user in (*owners, *catchers)
    ]
    fursuits: list[tuple[User, Fursuit]] = []
    for position, owner in enumerate(owners, start=1):
        for number in range(1, fursuits_per_owner + 1):
            fursuit = fursuit_services.create_fursuit(
                owner,
                name=f"Sim Fursuit {position}-{number}",
                photo=images.fixture_image(len(fursuits)),
            )
            stored_keys.append(fursuit.photo_key)
            fursuits.append((owner, fursuit))
    activation_ids = [
        convention_services.set_fursuit_activation_state(
            owner, convention_id=convention.pk, fursuit_id=fursuit.pk, is_active=True
        ).pk
        for owner, fursuit in fursuits
    ]
    run = FixtureRun.objects.create(run_id=run_id, pool=pool, status=PROVISIONED)
    FixtureIdentity.objects.bulk_create(
        [FixtureIdentity(run=run, index=index) for index in leased]
    )
    FixtureObject.objects.bulk_create(
        [
            FixtureObject(run=run, kind=CONVENTION, object_id=convention.pk),
            *(
                FixtureObject(run=run, kind=ENROLLMENT, object_id=pk)
                for pk in enrollment_ids
            ),
            *(
                FixtureObject(
                    run=run,
                    kind=FURSUIT,
                    object_id=fursuit.pk,
                    media_key=fursuit.photo_key,
                )
                for _, fursuit in fursuits
            ),
            *(
                FixtureObject(run=run, kind=ACTIVATION, object_id=pk)
                for pk in activation_ids
            ),
        ]
    )
    return {
        CONVENTION: 1,
        ENROLLMENT: len(enrollment_ids),
        FURSUIT: len(fursuits),
        ACTIVATION: len(activation_ids),
    }


def _discard_images(keys: list[str]) -> None:
    """Best-effort delete of images stored by a rolled-back attempt."""
    for key in keys:
        try:
            default_storage.delete(key)
        except Exception:  # noqa: BLE001 - a leftover object must not mask the failure.
            _LOGGER.warning(_CLEANUP_WARNING)
