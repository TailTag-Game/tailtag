"""The maintainer commands `cleanup` and `retained` (#223).

Both drive the fixture channel only: no target check, Clerk secret or lease. Output is
fixed lines, counts, and the run ids and pools of listed runs. A reply that deviates from
the frozen wire shape becomes a fixed `FAIL_LAUNCHER`; nothing from it is printed unless
it matched a strict pattern first.
"""

import re
from collections.abc import Callable, Mapping
from typing import Final, cast

from tailtag_simulator.fixtures import (
    MAX_RETAINED_RUNS,
    RETAINED_REASONS,
    FixtureChannel,
    FixtureFailed,
    cleanup_counts,
    count_of,
)

_RUN_ID: Final = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_POOL: Final = re.compile(r"[a-z0-9]{1,12}")
_RUN_KEYS: Final = frozenset({"run_id", "pool", "reason", "age_days"})


async def run_cleanup(
    pool: str, run_id: str, *, channel: FixtureChannel, emit: Callable[[str], None]
) -> int:
    """Clean one run's state; readmit its slots only when the cleanup is verified."""
    try:
        data = await channel.call("cleanup", {"pool": pool, "run_id": run_id})
        line = f"PASS cleanup {cleanup_counts(data)} readmitted={count_of(data, 'readmitted')}"
    except FixtureFailed as failure:
        emit(f"FAIL cleanup result={failure.result}")
        return 1
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        emit("FAIL cleanup result=FAIL_ERROR")
        return 1
    emit(line)
    return 0


def _listed(entry: object) -> str:
    """One `RETAINED` line from a run entry of exactly the frozen shape."""
    if not isinstance(entry, dict):
        raise FixtureFailed("FAIL_LAUNCHER")
    run = cast(dict[str, object], entry)
    run_id, pool, reason = run.get("run_id"), run.get("pool"), run.get("reason")
    if (
        frozenset(run) != _RUN_KEYS
        or not isinstance(run_id, str)
        or _RUN_ID.fullmatch(run_id) is None
        or not isinstance(pool, str)
        or _POOL.fullmatch(pool) is None
        or reason not in RETAINED_REASONS
    ):
        raise FixtureFailed("FAIL_LAUNCHER")
    return (
        f"RETAINED run_id={run_id} pool={pool} reason={reason}"
        f" age_days={count_of(run, 'age_days')}"
    )


def _listing(data: Mapping[str, object]) -> list[str]:
    runs = data.get("runs")
    if not isinstance(runs, list) or len(cast(list[object], runs)) > MAX_RETAINED_RUNS:
        raise FixtureFailed("FAIL_LAUNCHER")
    lines = [_listed(entry) for entry in cast(list[object], runs)]
    retained, unfinished = count_of(data, "retained"), count_of(data, "unfinished")
    lines.append(f"PASS retained retained={retained} unfinished={unfinished}")
    return lines


async def run_retained(*, channel: FixtureChannel, emit: Callable[[str], None]) -> int:
    """List retained and unfinished runs, then the counts; nothing prints on a bad reply."""
    try:
        lines = _listing(await channel.call("retained", {}))
    except FixtureFailed as failure:
        emit(f"FAIL retained result={failure.result}")
        return 1
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        emit("FAIL retained result=FAIL_ERROR")
        return 1
    for line in lines:
        emit(line)
    return 0
