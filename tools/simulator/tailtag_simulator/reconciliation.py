"""Post-run reconciliation of the journeys' expected state against Staging (#222).

RECONCILIATION runs after SIMULATION and before RELEASE. It proves three views of the
run agree: what the journeys expected, the Catch rows persisted on Staging (read through
the privileged, read-only `inspect` channel), and each run identity's public catch
history. Expected state lives only in memory (`Expectations`); the world is closed, so
any catch the journeys did not account for is a discrepancy.

Output is the fixed `reconciliation_lines`: check names, journey names, role labels and
counts only. No id, pool index, timestamp, URL or body ever reaches a line.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, cast

from tailtag_simulator.client import ApiClient, RequestFailed, TransportFailed
from tailtag_simulator.fixtures import ACTIVE_PATH
from tailtag_simulator.gameplay import IntegrityFailed
from tailtag_simulator.pool import (
    LAUNCHER_ERRORS,
    LAUNCHER_TIMEOUT_SECONDS,
    run_launcher,
)
from tailtag_simulator.safety import SafetyAborted, active_runtime

HISTORY_PATH: Final = "/api/catches/"
HISTORY_PAGE_SIZE: Final = 100

# Journeys meant to produce a catch; every other journey must produce none.
_POSITIVE_JOURNEYS: Final = frozenset({"catch", "retry"})
_FURSUIT_JOURNEY: Final = "fursuit_photo"
_AVATAR_JOURNEY: Final = "avatar"
# The relay's fixed result codes; anything else is printed as a launcher failure.
_RESULTS: Final = frozenset(
    {
        "FAIL_LEASE",
        "FAIL_RUN_UNKNOWN",
        "FAIL_LIMIT",
        "FAIL_REQUEST",
        "FAIL_TARGET",
        "FAIL_BOOTSTRAP",
        "FAIL_LAUNCHER",
    }
)


class Role(StrEnum):
    """The run's identities, fixed by lease order."""

    OWNER0 = "owner0"
    OWNER1 = "owner1"
    CATCHER0 = "catcher0"
    CATCHER1 = "catcher1"
    CATCHER2 = "catcher2"
    CATCHER3 = "catcher3"
    OUTSIDER = "outsider"


class Check(StrEnum):
    """Every reconciliation check, in output order."""

    INSPECT = "inspect"
    CONTAMINATION = "contamination"
    DUPLICATE = "duplicate"
    MISSING = "missing"
    UNEXPECTED = "unexpected"
    CATCH_ID = "catch_id"
    CAUGHT_AT = "caught_at"
    PROVENANCE = "provenance"
    WINDOW = "window"
    HISTORY = "history"
    COUNT = "count"
    FIXTURE_PHOTO = "fixture_photo"
    CREATED_FURSUIT = "created_fursuit"
    AVATAR = "avatar"


_Pair = tuple[Role, int]  # confirming role, fursuit id


@dataclass(frozen=True)
class Made:
    """What a confirm response reported for a pair."""

    catch_id: int
    caught_at: str


@dataclass
class Expectations:
    """What the journeys expect to have written, recorded as they run.

    A pair is a confirming role and a fursuit. `attempt` is recorded before every
    confirm. `created` (a 201) and `confirmed` (a 200 `already_caught`) are recorded
    only by the positive journeys, `catch` and `retry`.
    """

    journeys: list[str] = field(default_factory=list[str], init=False)
    attempts: dict[_Pair, list[str]] = field(
        default_factory=dict[_Pair, list[str]], init=False
    )
    made: dict[_Pair, Made] = field(default_factory=dict[_Pair, Made], init=False)
    seen: dict[_Pair, list[Made]] = field(
        default_factory=dict[_Pair, list[Made]], init=False
    )

    def begin(self, journey: str) -> None:
        self.journeys.append(journey)

    def attempt(self, role: Role, fursuit: int) -> None:
        self.attempts.setdefault((role, fursuit), []).append(self.journeys[-1])

    def created(self, role: Role, fursuit: int, catch_id: int, caught_at: str) -> None:
        self.made[(role, fursuit)] = Made(catch_id, caught_at)

    def confirmed(
        self, role: Role, fursuit: int, catch_id: int, caught_at: str
    ) -> None:
        self.seen.setdefault((role, fursuit), []).append(Made(catch_id, caught_at))


# -- the privileged inspection channel ---------------------------------------------


class InspectionFailed(Exception):
    """`inspect` failed. Carries one fixed result code, never detail."""

    def __init__(self, result: str) -> None:
        known = result if result in _RESULTS else "FAIL_LAUNCHER"
        super().__init__(known)
        self.result = known


class InspectionChannel(Protocol):
    """One privileged, read-only inspection: the `PASS` data, or raises InspectionFailed."""

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[Role, int]
    ) -> Mapping[str, object]: ...


class InspectionLauncherChannel:
    """Drives the inspection launcher as a subprocess: request on stdin, one JSON on stdout.

    The launcher plumbing is `pool.run_launcher`, as for the fixture channel. Any
    deviation, or a result code outside the relay's fixed set, is `FAIL_LAUNCHER`.
    """

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
        self, pool: str, run_id: str, identities: Mapping[Role, int]
    ) -> Mapping[str, object]:
        envelope: dict[str, object] = {
            "operation": "inspect",
            "arguments": {
                "pool": pool,
                "run_id": run_id,
                "identities": {role.value: index for role, index in identities.items()},
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
        if result == "PASS":
            return data
        raise InspectionFailed(result) from None


# -- the result --------------------------------------------------------------------


@dataclass(frozen=True)
class Discrepancy:
    check: Check
    journey: str | None
    role: Role | None
    expected: int
    observed: int


@dataclass(frozen=True)
class ReconciliationResult:
    """Every discrepancy, sorted; `inspect_result` is set only when `inspect` failed."""

    discrepancies: tuple[Discrepancy, ...]
    inspect_result: str | None = None
    integrity_failed: bool = False

    @property
    def passed(self) -> bool:
        return not self.discrepancies


def reconciliation_lines(result: ReconciliationResult) -> list[str]:
    """The fixed output lines. Only check, journey and role names and counts appear."""
    if result.inspect_result is not None:
        known = result.inspect_result
        return [
            f"FAIL reconciliation result={known if known in _RESULTS else 'FAIL_LAUNCHER'}"
        ]
    if result.passed:
        return [f"PASS reconciliation checks={len(Check)}"]
    return [
        f"FAIL reconciliation check={d.check} journey={d.journey or '-'}"
        f" role={d.role or '-'} expected={d.expected} observed={d.observed}"
        for d in result.discrepancies
    ] + [f"FAIL reconciliation discrepancies={len(result.discrepancies)}"]


# -- reading the inspection data and the public history ---------------------------


@dataclass(frozen=True)
class _Row:
    id: int
    catcher: int | None
    fursuit: int
    owner: int | None
    run_convention: bool
    provenance: bool
    in_window: bool
    caught_at: str


@dataclass(frozen=True)
class _Inspection:
    catches: tuple[_Row, ...]
    fursuits: frozenset[tuple[int, int]]  # (id, owner pool index)
    fixture_photos_unchanged: bool
    avatars: tuple[int, ...]


@dataclass(frozen=True)
class _History:
    """One role's public history; None marks what could not be read."""

    count: int | None
    rows: tuple[tuple[int, int, str], ...] | None  # (id, fursuit id, caught_at)
    integrity_failed: bool = False


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError
    return cast(list[object], value)


def _int(value: object) -> int:
    if type(value) is not int:
        raise ValueError
    return value


def _maybe_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError
    return value


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _inspection(data: Mapping[str, object]) -> _Inspection:
    """Parse the relay's `PASS` data; anything off-shape is a launcher failure."""
    try:
        rows: list[_Row] = []
        for item in _list(data["catches"]):
            each = _object(item)
            rows.append(
                _Row(
                    _int(each["id"]),
                    _maybe_int(each["catcher"]),
                    _int(each["fursuit"]),
                    _maybe_int(each["fursuit_owner"]),
                    _flag(each["run_convention"]),
                    _flag(each["provenance"]),
                    _flag(each["in_window"]),
                    _str(each["caught_at"]),
                )
            )
        fursuits = frozenset(
            (_int(_object(item)["id"]), _int(_object(item)["owner"]))
            for item in _list(data["fursuits"])
        )
        return _Inspection(
            tuple(rows),
            fursuits,
            _flag(data["fixture_photos_unchanged"]),
            tuple(_int(index) for index in _list(data["avatars"])),
        )
    except (KeyError, TypeError, ValueError):
        raise InspectionFailed("FAIL_LAUNCHER") from None


async def _history(client: ApiClient, convention: int) -> _History:
    path = f"{HISTORY_PATH}?convention_id={convention}&page_size={HISTORY_PAGE_SIZE}"
    try:
        reply = await client.get(path)
    except SafetyAborted:
        raise
    except TransportFailed:
        return _History(None, None)
    except RequestFailed:
        raise IntegrityFailed("history", "200/-", "error") from None
    except Exception:  # noqa: BLE001 - unavailable history remains ordinary failed evidence
        return _History(None, None)
    if reply.status != 200 and not 200 <= reply.status < 300:
        return _History(None, None)
    try:
        if reply.status != 200:
            raise ValueError
        body = _object(reply.body)
        count = body.get("catch_count")
        if type(count) is not int or count < 0:
            raise ValueError
        rows = tuple(
            (
                _int(_object(item)["id"]),
                _int(_object(_object(item)["fursuit"])["id"]),
                _str(_object(item)["caught_at"]),
            )
            for item in _list(body["results"])
        )
    except Exception:  # noqa: BLE001 - malformed actual success is observed integrity evidence
        failure = IntegrityFailed("history", "200/-", f"{reply.status}/shape")
        runtime = active_runtime()
        if runtime is not None and not bool(
            cast(Mapping[str, object], runtime.snapshot()["finalization"])["started"]
        ):
            raise failure from None
        return _History(None, None, integrity_failed=True)
    return _History(count, rows)


async def _active_convention(client: ApiClient) -> int:
    """The run Convention as catcher0 sees it; any failure raises (fail closed)."""
    reply = await client.get(ACTIVE_PATH)
    if not 200 <= reply.status < 300:
        raise ValueError
    try:
        if reply.status != 200:
            raise ValueError
        enrollment = _object(_object(reply.body)["enrollment"])
        convention = _int(_object(enrollment["convention"])["id"])
        if convention <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise IntegrityFailed("active", "200/-", f"{reply.status}/shape") from None
    return convention


# -- the comparison ----------------------------------------------------------------


def _compare(
    expectations: Expectations,
    indexes: Mapping[Role, int],
    inspected: _Inspection,
    histories: Mapping[Role, _History],
    created_fursuit: int | None,
) -> list[Discrepancy]:
    role_of = {index: role for role, index in indexes.items()}
    found: list[Discrepancy] = []

    def add(
        check: Check,
        journey: str | None,
        role: Role | None,
        expected: int,
        observed: int,
    ) -> None:
        found.append(Discrepancy(check, journey, role, expected, observed))

    pairs: dict[_Pair, list[_Row]] = {}
    contaminating = 0
    for row in inspected.catches:
        if (
            row.catcher not in role_of
            or row.owner not in role_of
            or not row.run_convention
        ):
            contaminating += 1
        else:
            pairs.setdefault((role_of[row.catcher], row.fursuit), []).append(row)
    if contaminating:
        add(Check.CONTAMINATION, None, None, 0, contaminating)

    for pair, rows in pairs.items():
        role, _ = pair
        attempted = expectations.attempts.get(pair, [])
        journey = attempted[0] if attempted else None
        made = expectations.made.get(pair)
        if len(rows) > 1:
            add(Check.DUPLICATE, journey, role, 1, len(rows))
        if made is None and not _POSITIVE_JOURNEYS.intersection(attempted):
            add(Check.UNEXPECTED, journey, role, 0, len(rows))
        if len(rows) > 1:
            continue
        (row,) = rows
        if made is not None and made.catch_id != row.id:
            add(Check.CATCH_ID, journey, role, 1, 0)
        reported = {row.caught_at}
        reported.update(item.caught_at for item in expectations.seen.get(pair, []))
        if made is not None:
            reported.add(made.caught_at)
        listed = histories[role].rows
        reported.update(
            at
            for id_, fursuit, at in listed or ()
            if (id_, fursuit) == (row.id, row.fursuit)
        )
        if len(reported) > 1:
            add(Check.CAUGHT_AT, journey, role, 1, 0)
        if not row.provenance:
            add(Check.PROVENANCE, journey, role, 1, 0)
        if not row.in_window:
            add(Check.WINDOW, journey, role, 1, 0)

    for pair in expectations.made:
        if pair not in pairs:
            add(Check.MISSING, expectations.attempts[pair][0], pair[0], 1, 0)

    for role, history in histories.items():
        stored = sorted(
            (row.id, row.fursuit)
            for row in inspected.catches
            if row.catcher is not None
            and role_of.get(row.catcher) == role
            and row.run_convention
        )
        listed = history.rows
        if listed is None or sorted((i, f) for i, f, _ in listed) != stored:
            add(Check.HISTORY, None, role, len(stored), len(listed or ()))
        if history.count != len(stored):
            add(Check.COUNT, None, role, len(stored), history.count or 0)

    if not inspected.fixture_photos_unchanged:
        add(Check.FIXTURE_PHOTO, None, None, 1, 0)

    wanted = (
        frozenset({(created_fursuit, indexes[Role.OWNER0])})
        if created_fursuit
        else frozenset[tuple[int, int]]()
    )
    if inspected.fursuits != wanted:
        add(
            Check.CREATED_FURSUIT,
            _FURSUIT_JOURNEY,
            Role.OWNER0,
            len(wanted),
            len(inspected.fursuits),
        )

    for index in inspected.avatars:
        add(Check.AVATAR, _AVATAR_JOURNEY, role_of.get(index), 0, 1)

    return found


def _sorted(
    found: Sequence[Discrepancy], expectations: Expectations
) -> tuple[Discrepancy, ...]:
    """By check order, then journey order (unnamed last), then role order."""
    checks, roles = list(Check), list(Role)
    journeys = {name: rank for rank, name in enumerate(expectations.journeys)}

    def key(each: Discrepancy) -> tuple[int, int, int]:
        return (
            checks.index(each.check),
            len(journeys) if each.journey is None else journeys[each.journey],
            len(roles) if each.role is None else roles.index(each.role),
        )

    return tuple(sorted(found, key=key))


async def reconcile_run(
    expectations: Expectations,
    clients: Mapping[Role, ApiClient],
    indexes: Mapping[Role, int],
    channel: InspectionChannel,
    *,
    pool: str,
    run_id: str,
    convention: int,
    created_fursuit: int | None,
) -> ReconciliationResult:
    """Read each role's public history, inspect once, and compare.

    `convention` is 0 when SIMULATION never learned it; it is then read through
    catcher0 and any failure to do so raises. A failed `inspect` is the single
    `Check.INSPECT` discrepancy with the relay's result code.
    """
    if not convention:
        convention = await _active_convention(clients[Role.CATCHER0])
    histories = {role: await _history(clients[role], convention) for role in Role}
    try:
        inspected = _inspection(await channel.inspect(pool, run_id, indexes))
    except InspectionFailed as failed:
        return ReconciliationResult(
            (Discrepancy(Check.INSPECT, None, None, 1, 0),), failed.result
        )
    discrepancies = _sorted(
        _compare(expectations, indexes, inspected, histories, created_fursuit),
        expectations,
    )
    integrity = any(history.integrity_failed for history in histories.values()) or any(
        item.check not in (Check.HISTORY, Check.COUNT)
        or (item.role is not None and histories[item.role].rows is not None)
        for item in discrepancies
    )
    return ReconciliationResult(discrepancies, integrity_failed=integrity)
