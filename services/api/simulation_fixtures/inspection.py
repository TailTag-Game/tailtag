"""Read-only inspection of the state a simulation run left behind.

``inspect`` is the privileged read behind the simulator's reconciliation. It runs
in one PostgreSQL read-only transaction, answers with pool indexes instead of user
IDs, and carries no names, handles, or media keys.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, cast

from django.db import connection, transaction
from django.db.models import BooleanField, ExpressionWrapper, F, Q
from django.db.models.functions import Now

from catches.models import Catch
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from simulation_fixtures.models import (
    CONVENTION,
    FURSUIT,
    PROVISIONED,
    FixtureObject,
    FixtureRun,
)
from simulation_fixtures.services import (
    _MAX_INDEX,  # pyright: ignore[reportPrivateUsage]
    _POOL,  # pyright: ignore[reportPrivateUsage]
    _leased_to,  # pyright: ignore[reportPrivateUsage]
    _run_id,  # pyright: ignore[reportPrivateUsage]
)
from simulation_pool.models import PoolSlot

ROLES: Final = (
    "owner0",
    "owner1",
    "catcher0",
    "catcher1",
    "catcher2",
    "catcher3",
    "outsider",
)
MAX_RECORDS: Final = 200


@dataclass(frozen=True)
class InspectionOutcome:
    """A result code and, for ``PASS`` only, the fixed-shape data."""

    result: str
    data: dict[str, object] = field(default_factory=dict[str, object])


def _validated(
    pool: object, run_id: object, identities: object
) -> tuple[str, str, dict[str, int]]:
    indexes = (
        dict(cast(Mapping[str, object], identities))
        if isinstance(identities, Mapping)
        else {}
    )
    if (
        not isinstance(pool, str)
        or _POOL.fullmatch(pool) is None
        or frozenset(indexes) != frozenset(ROLES)
        or len(set(indexes.values())) != len(indexes)
        or not all(
            type(index) is int and 0 <= index <= _MAX_INDEX
            for index in indexes.values()
        )
    ):
        raise ValueError("request invalid")
    return pool, _run_id(run_id), cast(dict[str, int], indexes)


def _caught_at(value: dt.datetime) -> str:
    # Formatted exactly as ``catches.serializers.catch_history_entry_data`` does.
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def inspect(pool: str, run_id: str, identities: Mapping[str, int]) -> InspectionOutcome:
    """Report the catches, extra fursuits, photos, and avatars a run can have touched.

    The lease guard runs first: only indexes leased to ``run_id`` are read.
    """
    try:
        pool, run_id, by_role = _validated(pool, run_id, identities)
    except ValueError:
        return InspectionOutcome("FAIL_REQUEST")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        return _read(pool, run_id, sorted(by_role.values()))


def _population_validated(
    pool: object, run_id: object, identities: object
) -> tuple[str, str, dict[str, int]]:
    if not isinstance(identities, Mapping):
        raise TypeError
    indexes = dict(cast(Mapping[str, object], identities))
    owners = len(set(indexes).intersection(f"owner{n}" for n in range(50)))
    attendees = len(indexes) - owners
    labels = {f"owner{n}" for n in range(owners)} | {
        f"attendee{n}" for n in range(attendees)
    }
    if (
        not isinstance(pool, str)
        or _POOL.fullmatch(pool) is None
        or not 1 <= owners <= 50
        or not 1 <= attendees <= 200
        or set(indexes) != labels
        or not all(
            type(index) is int and 0 <= index <= _MAX_INDEX
            for index in indexes.values()
        )
        or len(set(indexes.values())) != len(indexes)
    ):
        raise ValueError("request invalid")
    return pool, _run_id(run_id), cast(dict[str, int], indexes)


def inspect_population(
    pool: str, run_id: str, identities: Mapping[str, int]
) -> InspectionOutcome:
    """Inspect a bounded owner/attendee population using the existing read scope."""
    try:
        pool, run_id, indexes = _population_validated(pool, run_id, identities)
    except (TypeError, ValueError):
        return InspectionOutcome("FAIL_REQUEST")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        return _read(pool, run_id, sorted(indexes.values()))


def _read(pool: str, run_id: str, indexes: list[int]) -> InspectionOutcome:
    slots = {
        slot.index: slot
        for slot in PoolSlot.objects.filter(pool=pool, index__in=indexes)
    }
    now = dt.datetime.now(dt.UTC)
    handles = {f"sp_{pool}_{index}": index for index in indexes}
    profiles = dict(
        PlayerProfile.objects.filter(handle__in=handles).values_list(
            "user_id", "handle"
        )
    )
    if len(profiles) != len(indexes) or not all(
        index in slots and _leased_to(slots[index], run_id, now) for index in indexes
    ):
        return InspectionOutcome("FAIL_LEASE")
    run = FixtureRun.objects.filter(
        run_id=run_id, pool=pool, status=PROVISIONED
    ).first()
    if run is None:
        return InspectionOutcome("FAIL_RUN_UNKNOWN")
    index_of = {user_id: handles[handle] for user_id, handle in profiles.items()}
    ledger = FixtureObject.objects.filter(run=run)
    convention_id = ledger.get(kind=CONVENTION).object_id
    ledger_photos = dict(
        ledger.filter(kind=FURSUIT).values_list("object_id", "media_key")
    )

    rows = list(
        Catch.objects.filter(
            Q(catcher_user_id__in=index_of)
            | Q(convention_id=convention_id)
            | Q(fursuit__owner_id__in=index_of)
        )
        .annotate(
            owner_id=F("fursuit__owner_id"),
            provenance=ExpressionWrapper(
                Q(catch_session__activation_id=F("activation_id"))
                & Q(activation__fursuit_id=F("fursuit_id"))
                & Q(activation__convention_id=F("convention_id")),
                output_field=BooleanField(),
            ),
            in_window=ExpressionWrapper(
                Q(caught_at__gte=run.created_at) & Q(caught_at__lte=Now()),
                output_field=BooleanField(),
            ),
        )
        .order_by("id")
        .values_list(
            "id",
            "catcher_user_id",
            "fursuit_id",
            "owner_id",
            "convention_id",
            "provenance",
            "in_window",
            "caught_at",
        )[: MAX_RECORDS + 1]
    )
    extra = list(
        Fursuit.objects.filter(owner_id__in=index_of)
        .exclude(pk__in=ledger_photos)
        .order_by("id")
        .values_list("id", "owner_id")[: MAX_RECORDS + 1]
    )
    if len(rows) > MAX_RECORDS or len(extra) > MAX_RECORDS:
        return InspectionOutcome("FAIL_LIMIT")

    current_photos = dict(
        Fursuit.objects.filter(pk__in=ledger_photos).values_list("id", "photo_key")
    )
    avatar_owners = PlayerProfile.objects.filter(
        user_id__in=index_of, avatar_key__isnull=False
    ).values_list("user_id", flat=True)
    return InspectionOutcome(
        "PASS",
        {
            "catches": [
                {
                    "id": catch_id,
                    "catcher": index_of.get(catcher_id),
                    "fursuit": fursuit_id,
                    "fursuit_owner": index_of.get(owner_id),
                    "run_convention": catch_convention == convention_id,
                    "provenance": provenance,
                    "in_window": in_window,
                    "caught_at": _caught_at(caught_at),
                }
                for (
                    catch_id,
                    catcher_id,
                    fursuit_id,
                    owner_id,
                    catch_convention,
                    provenance,
                    in_window,
                    caught_at,
                ) in rows
            ],
            "fursuits": [
                {"id": fursuit_id, "owner": index_of[owner_id]}
                for fursuit_id, owner_id in extra
            ],
            "fixture_photos_unchanged": current_photos == ledger_photos,
            "avatars": sorted(index_of[user_id] for user_id in avatar_owners),
        },
    )
