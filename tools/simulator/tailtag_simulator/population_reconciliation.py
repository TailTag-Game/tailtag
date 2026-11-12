"""Closed-world population reconciliation with sanitized logical actor diagnostics."""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, cast

from tailtag_simulator.client import ApiClient
from tailtag_simulator.gameplay import HistoryEntry, IntegrityFailed, read_history
from tailtag_simulator.pool import (
    LAUNCHER_ERRORS,
    LAUNCHER_TIMEOUT_SECONDS,
    run_launcher,
)
from tailtag_simulator.reconciliation import (
    Check,
    InspectionFailed,
    Made,
    _flag,  # pyright: ignore[reportPrivateUsage]
    _inspection,  # pyright: ignore[reportPrivateUsage]
    _int,  # pyright: ignore[reportPrivateUsage]
    _list,  # pyright: ignore[reportPrivateUsage]
    _maybe_int,  # pyright: ignore[reportPrivateUsage]
    _object,  # pyright: ignore[reportPrivateUsage]
    _Row,  # pyright: ignore[reportPrivateUsage]
    _str,  # pyright: ignore[reportPrivateUsage]
)


class RequestCheck(StrEnum):
    """Catch request checks: population reconciliation in request mode only (#508)."""

    REQUEST_STATE = "request_state"
    REQUEST_DUPLICATE = "request_duplicate"
    REQUEST_CREDIT = "request_credit"


REQUEST_STATES = frozenset(
    {"pending", "approved", "declined", "withdrawn", "invalidated"}
)


@dataclass(frozen=True)
class _RequestRow:
    id: int
    player: int | None
    fursuit: int
    run_convention: bool
    state: str
    requested_at: str


def _request_rows(data: Mapping[str, object]) -> tuple[_RequestRow, ...]:
    """Parse inspect-population-v2 requests; anything off-shape fails closed."""
    try:
        rows: list[_RequestRow] = []
        for item in _list(data["requests"]):
            each = _object(item)
            row = _RequestRow(
                _int(each["id"]),
                _maybe_int(each["player"]),
                _int(each["fursuit"]),
                _flag(each["run_convention"]),
                _str(each["state"]),
                _str(each["requested_at"]),
            )
            if row.state not in REQUEST_STATES or not row.requested_at:
                raise ValueError
            rows.append(row)
        if len(rows) > 120 or len({row.id for row in rows}) != len(rows):
            raise ValueError
        return tuple(rows)
    except (KeyError, TypeError, ValueError):
        raise InspectionFailed("FAIL_LAUNCHER") from None


from tailtag_simulator.safety import SafetyAborted, active_runtime


@dataclass
class RequestFact:
    """One trio's catch request as the simulator last observed it (#508)."""

    id: int
    state: str
    requested_at: str


@dataclass
class PopulationExpectations:
    # `pending` is the catch request flow only: a request waits for its owner.
    pairs: dict[
        tuple[str, int], Literal["required", "forbidden", "unresolved", "pending"]
    ] = field(
        default_factory=dict[
            tuple[str, int], Literal["required", "forbidden", "unresolved", "pending"]
        ]
    )
    target_owners: dict[int, str] = field(default_factory=dict[int, str])
    attempts: set[tuple[str, int]] = field(default_factory=set[tuple[str, int]])
    made: dict[tuple[str, int], Made] = field(
        default_factory=dict[tuple[str, int], Made]
    )
    seen: dict[tuple[str, int], list[Made]] = field(
        default_factory=dict[tuple[str, int], list[Made]]
    )
    # Catch request flow only: the latest request per trio.
    requests: dict[tuple[str, int], RequestFact] = field(
        default_factory=dict[tuple[str, int], RequestFact]
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
        operation: str = "inspect-population-v2",
    ) -> None:
        """v2 adds catch requests (#508). v1 stays for older scenario versions."""
        if operation not in ("inspect-population-v1", "inspect-population-v2"):
            raise ValueError("unsupported inspection operation")
        self._command = list(command)
        self._cwd = cwd
        self._timeout_seconds = timeout_seconds
        self._operation = operation

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        envelope: dict[str, object] = {
            "operation": self._operation,
            "arguments": {
                "pool": pool,
                "run_id": run_id,
                "identities": dict(identities),
            },
        }
        runtime = active_runtime()
        if runtime is not None:
            envelope["expected_identity"] = await runtime.privileged_identity()
        request = json.dumps(envelope).encode()
        try:
            result, data = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise InspectionFailed("FAIL_LAUNCHER") from None
        if result == "FAIL_TARGET" and runtime is not None:
            runtime.abort("identity_mismatch")
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
    integrity_failed: bool = False

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
        known = {*Check, *RequestCheck}
        check = each.check if each.check in known else "inspect"
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
    request_flow: bool = False,
) -> PopulationReconciliationResult:
    """Compare persisted rows, confirm facts and every actor's complete public history.

    ``request_flow`` also compares the run's catch requests with the requests the
    simulator observed, and catch credit with request state (#508).
    """
    found: list[PopulationDiscrepancy] = []
    integrity = False

    def add(
        check: Check | RequestCheck,
        actor: str | None,
        expected: int,
        observed: int,
        *,
        actual: bool = True,
    ) -> None:
        nonlocal integrity
        integrity = integrity or actual
        found.append(PopulationDiscrepancy(check.value, actor, expected, observed))

    histories: dict[str, tuple[HistoryEntry, ...] | None] = {}
    for actor in indexes:
        try:
            histories[actor] = await read_history(clients[actor], convention)
        except SafetyAborted:
            raise
        except IntegrityFailed:
            runtime = active_runtime()
            if runtime is not None and not bool(
                cast(Mapping[str, object], runtime.snapshot()["finalization"])[
                    "started"
                ]
            ):
                raise
            integrity = True
            histories[actor] = None
        except Exception:  # noqa: BLE001 - unavailable history fails the run without asserting corruption
            histories[actor] = None
    try:
        data = await channel.inspect(pool, run_id, indexes)
        inspected = _inspection(data)
        request_rows = _request_rows(data) if request_flow else ()
        if (
            len(inspected.catches) > 200
            or len(inspected.fursuits) > 200
            or any(
                row.id <= 0 or row.fursuit <= 0 or not row.caught_at
                for row in inspected.catches
            )
        ):
            raise InspectionFailed("FAIL_LAUNCHER")
    except SafetyAborted:
        raise
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
        explicit = expectations.pairs.get(pair)
        if (
            expectations.pairs
            and (explicit == "forbidden" or explicit is None)
            or not expectations.pairs
            and pair not in expectations.attempts
            and made is None
        ):
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
    for pair, expected in expectations.pairs.items():
        if (
            expected in ("unresolved", "pending")
            or expected == "required"
            and pair not in expectations.made
        ):
            add(Check.INSPECT, pair[0], 1, 0, actual=False)
    if request_flow:
        _compare_requests(expectations, request_rows, inspected.catches, role_of, add)
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
            add(
                Check.HISTORY,
                actor,
                len(stored),
                len(listed),
                actual=history is not None,
            )
        if history is None or len(history) != len(stored):
            add(
                Check.COUNT, actor, len(stored), len(listed), actual=history is not None
            )
    if not inspected.fixture_photos_unchanged:
        add(Check.FIXTURE_PHOTO, None, 1, 0)
    if inspected.fursuits:
        add(Check.CREATED_FURSUIT, None, 0, len(inspected.fursuits))
    for index in inspected.avatars:
        add(Check.AVATAR, role_of.get(index), 0, 1)
    checks = [check.value for check in Check] + [check.value for check in RequestCheck]
    return PopulationReconciliationResult(
        tuple(
            sorted(
                found,
                key=lambda item: (checks.index(item.check), _actor_key(item.actor)),
            )
        ),
        len(Check) + (len(RequestCheck) if request_flow else 0),
        integrity_failed=integrity,
    )


class _Add(Protocol):
    def __call__(
        self,
        check: Check | RequestCheck,
        actor: str | None,
        expected: int,
        observed: int,
        *,
        actual: bool = True,
    ) -> None: ...


def _compare_requests(
    expectations: PopulationExpectations,
    rows: Sequence[_RequestRow],
    catches: Sequence[_Row],
    role_of: Mapping[int, str],
    add: _Add,
) -> None:
    """Request rows against observed facts; catch credit against request state."""
    by_pair: dict[tuple[str, int], list[_RequestRow]] = {}
    for row in rows:
        actor = role_of.get(row.player) if row.player is not None else None
        if actor is None or not actor.startswith("attendee") or not row.run_convention:
            add(Check.CONTAMINATION, actor, 0, 1)
            continue
        by_pair.setdefault((actor, row.fursuit), []).append(row)
    credits: dict[tuple[str, int], list[str]] = {}
    for catch in catches:
        actor = role_of.get(catch.catcher) if catch.catcher is not None else None
        if actor is not None:
            credits.setdefault((actor, catch.fursuit), []).append(catch.caught_at)
    for pair, stored in by_pair.items():
        actor = pair[0]
        if sum(row.state == "pending" for row in stored) > 1 or len(stored) > 1:
            add(RequestCheck.REQUEST_DUPLICATE, actor, 1, len(stored))
        fact = expectations.requests.get(pair)
        if fact is None:
            add(
                Check.INSPECT if pair in expectations.attempts else Check.UNEXPECTED,
                actor,
                0,
                len(stored),
                actual=pair not in expectations.attempts,
            )
            continue
        match = next((row for row in stored if row.id == fact.id), None)
        if match is None or match.state != fact.state:
            add(RequestCheck.REQUEST_STATE, actor, 1, 0)
        approved = [row for row in stored if row.state == "approved"]
        credited = credits.get(pair, [])
        if approved:
            if len(credited) != 1 or credited[0] != approved[0].requested_at:
                add(RequestCheck.REQUEST_CREDIT, actor, 1, len(credited))
        elif credited:
            add(RequestCheck.REQUEST_CREDIT, actor, 0, len(credited))
    for pair, fact in expectations.requests.items():
        if pair not in by_pair:
            add(RequestCheck.REQUEST_STATE, pair[0], 1, 0)
    for pair, credited in credits.items():
        if pair not in by_pair and credited:
            add(RequestCheck.REQUEST_CREDIT, pair[0], 0, len(credited))
