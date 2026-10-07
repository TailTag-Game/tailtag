"""Closed-world population reconciliation with sanitized logical actor diagnostics."""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tailtag_simulator.client import ApiClient
from tailtag_simulator.gameplay import HistoryEntry, read_history
from tailtag_simulator.pool import (
    LAUNCHER_ERRORS,
    LAUNCHER_TIMEOUT_SECONDS,
    run_launcher,
)
from tailtag_simulator.reconciliation import (
    Check,
    InspectionFailed,
    Made,
    _inspection,  # pyright: ignore[reportPrivateUsage]
)


@dataclass
class PopulationExpectations:
    target_owners: dict[int, str] = field(default_factory=dict[int, str])
    attempts: set[tuple[str, int]] = field(default_factory=set[tuple[str, int]])
    made: dict[tuple[str, int], Made] = field(
        default_factory=dict[tuple[str, int], Made]
    )
    seen: dict[tuple[str, int], list[Made]] = field(
        default_factory=dict[tuple[str, int], list[Made]]
    )


class PopulationInspectionChannel(Protocol):
    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]: ...


class PopulationInspectionLauncherChannel:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: float = LAUNCHER_TIMEOUT_SECONDS,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._timeout_seconds = timeout_seconds

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        request = json.dumps(
            {
                "operation": "inspect-population-v1",
                "arguments": {
                    "pool": pool,
                    "run_id": run_id,
                    "identities": dict(identities),
                },
            }
        ).encode()
        try:
            result, data = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise InspectionFailed("FAIL_LAUNCHER") from None
        if result != "PASS":
            raise InspectionFailed(result)
        return data


@dataclass(frozen=True)
class PopulationDiscrepancy:
    check: str
    actor: str | None
    expected: int
    observed: int


@dataclass(frozen=True)
class PopulationReconciliationResult:
    discrepancies: tuple[PopulationDiscrepancy, ...]
    count: int

    @property
    def passed(self) -> bool:
        return not self.discrepancies


def _actor_key(actor: str | None) -> tuple[int, int]:
    if actor is None:
        return (2, 0)
    match = re.fullmatch(r"(owner|attendee)(0|[1-9][0-9]*)", actor)
    if match is None:
        return (2, 0)
    ordinal = int(match[2])
    if ordinal >= (50 if match[1] == "owner" else 200):
        return (2, 0)
    return (0 if match[1] == "owner" else 1, ordinal)


def population_reconciliation_lines(
    result: PopulationReconciliationResult,
) -> list[str]:
    if result.passed:
        return [f"PASS reconciliation checks={result.count}"]
    lines: list[str] = []
    for each in result.discrepancies:
        check = each.check if each.check in set(Check) else "inspect"
        actor = each.actor if _actor_key(each.actor)[0] < 2 else "-"
        lines.append(
            f"FAIL reconciliation check={check} actor={actor} expected={each.expected} observed={each.observed}"
        )
    return lines + [f"FAIL reconciliation discrepancies={len(result.discrepancies)}"]


async def reconcile_population(
    expectations: PopulationExpectations,
    clients: Mapping[str, ApiClient],
    indexes: Mapping[str, int],
    channel: PopulationInspectionChannel,
    *,
    pool: str,
    run_id: str,
    convention: int,
) -> PopulationReconciliationResult:
    """Compare persisted rows, confirm facts and every actor's complete public history."""
    found: list[PopulationDiscrepancy] = []

    def add(check: Check, actor: str | None, expected: int, observed: int) -> None:
        found.append(PopulationDiscrepancy(check.value, actor, expected, observed))

    histories: dict[str, tuple[HistoryEntry, ...] | None] = {}
    for actor in indexes:
        try:
            histories[actor] = await read_history(clients[actor], convention)
        except Exception:  # noqa: BLE001 - unreadable history fails correctness
            histories[actor] = None
    try:
        inspected = _inspection(await channel.inspect(pool, run_id, indexes))
        if (
            len(inspected.catches) > 200
            or len(inspected.fursuits) > 200
            or any(
                row.id <= 0 or row.fursuit <= 0 or not row.caught_at
                for row in inspected.catches
            )
        ):
            raise InspectionFailed("FAIL_LAUNCHER")
    except Exception:  # noqa: BLE001 - inspection boundary must fail closed
        return PopulationReconciliationResult(
            (PopulationDiscrepancy("inspect", None, 1, 0),), 1
        )

    role_of = {index: actor for actor, index in indexes.items()}
    pairs: dict[tuple[str, int], list[int]] = {}
    catch_ids: set[int] = set()
    for position, row in enumerate(inspected.catches):
        actor, owner = (
            (role_of.get(row.catcher) if row.catcher is not None else None),
            (role_of.get(row.owner) if row.owner is not None else None),
        )
        expected_owner = expectations.target_owners.get(row.fursuit)
        if (
            actor is None
            or owner is None
            or expected_owner not in indexes
            or _actor_key(expected_owner)[0] != 0
            or owner != expected_owner
            or not actor.startswith("attendee")
            or not owner.startswith("owner")
            or not row.run_convention
        ):
            add(Check.CONTAMINATION, actor, 0, 1)
            continue
        if row.id in catch_ids:
            add(Check.DUPLICATE, actor, 1, 2)
        catch_ids.add(row.id)
        pairs.setdefault((actor, row.fursuit), []).append(position)
    for pair, positions in pairs.items():
        actor, _ = pair
        made = expectations.made.get(pair)
        if len(positions) > 1:
            add(Check.DUPLICATE, actor, 1, len(positions))
        if pair not in expectations.attempts and made is None:
            add(Check.UNEXPECTED, actor, 0, len(positions))
        for position in positions:
            row = inspected.catches[position]
            reported = list(expectations.seen.get(pair, []))
            if made is not None:
                reported.append(made)
            if any(item.catch_id != row.id for item in reported):
                add(Check.CATCH_ID, actor, 1, 0)
            if any(item.caught_at != row.caught_at for item in reported):
                add(Check.CAUGHT_AT, actor, 1, 0)
            if not row.provenance:
                add(Check.PROVENANCE, actor, 1, 0)
            if not row.in_window:
                add(Check.WINDOW, actor, 1, 0)
    for pair in expectations.made:
        if pair not in pairs:
            add(Check.MISSING, pair[0], 1, 0)
    for actor, history in histories.items():
        stored = sorted(
            (row.id, row.fursuit, row.caught_at)
            for row in inspected.catches
            if (role_of.get(row.catcher) if row.catcher is not None else None) == actor
            and row.run_convention
        )
        listed = sorted(
            (row.catch_id, row.fursuit, row.caught_at) for row in history or ()
        )
        if history is None or listed != stored:
            add(Check.HISTORY, actor, len(stored), len(listed))
        if history is None or len(history) != len(stored):
            add(Check.COUNT, actor, len(stored), len(listed))
    if not inspected.fixture_photos_unchanged:
        add(Check.FIXTURE_PHOTO, None, 1, 0)
    if inspected.fursuits:
        add(Check.CREATED_FURSUIT, None, 0, len(inspected.fursuits))
    for index in inspected.avatars:
        add(Check.AVATAR, role_of.get(index), 0, 1)
    checks = [check.value for check in Check]
    return PopulationReconciliationResult(
        tuple(
            sorted(
                found,
                key=lambda item: (checks.index(item.check), _actor_key(item.actor)),
            )
        ),
        len(Check),
    )
