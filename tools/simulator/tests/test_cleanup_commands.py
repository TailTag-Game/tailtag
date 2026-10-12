"""The maintainer commands `cleanup` and `retained` (#223 C-10, C-11, C-14).

Assumed interfaces (the implementation plan allows `cleanup.py` or `fixtures.py`; these
tests assume a new module):

    tailtag_simulator/cleanup.py
        async def run_cleanup(pool: str, run_id: str, *,
                              channel: FixtureChannel, emit: Callable[[str], None]) -> int
        async def run_retained(*, channel: FixtureChannel,
                               emit: Callable[[str], None]) -> int

    python -m tailtag_simulator cleanup --pool <p> --run-id <canonical uuid>
    python -m tailtag_simulator retained

`main` builds a `FixtureLauncherChannel` for both and hands it to the run function as
`channel`. Neither command takes a target or a Clerk secret.

Output lines pinned here (exit code 0 after PASS, 1 after FAIL):

    PASS cleanup convention=<n> enrollment=<n> fursuit=<n> activation=<n> catch=<n>
        session=<n> credential=<n> image=<n> readmitted=<n>          (one line)
    FAIL cleanup result=<FAIL_CODE>
    RETAINED run_id=<id> pool=<p> reason=<r> age_days=<d>            (per run, in the order
                                                                      the channel gives)
    PASS retained retained=<n> unfinished=<m>
    FAIL retained result=<FAIL_CODE>

The in-run CLEANUP line is pinned in test_run_lifecycle.
"""

import asyncio
import getpass
import socket
import subprocess
from collections.abc import Mapping
from types import CoroutineType
from typing import Any, Final

import pytest
from fixture_support import CLEANUP_DATA
from pool_support import POOL, RUN_ID

from tailtag_simulator.__main__ import main
from tailtag_simulator.cleanup import run_cleanup, run_retained
from tailtag_simulator.fixtures import FixtureFailed, FixtureLauncherChannel

OTHER_RUN_ID: Final = "99999999-9999-4999-8999-999999999999"
RUNS: Final[list[dict[str, object]]] = [
    {"run_id": RUN_ID, "pool": POOL, "reason": "journeys", "age_days": 0},
    {"run_id": OTHER_RUN_ID, "pool": "p2", "reason": "interrupted", "age_days": 12},
    {"run_id": OTHER_RUN_ID, "pool": POOL, "reason": "unfinished", "age_days": 400},
]


class ScriptedChannel:
    """The fixture channel's far end: answers every call with `reply` or raises it."""

    def __init__(self, reply: Mapping[str, object] | Exception) -> None:
        self._reply = reply
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        self.calls.append((operation, dict(arguments)))
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def cleanup(channel: ScriptedChannel) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = asyncio.run(run_cleanup(POOL, RUN_ID, channel=channel, emit=lines.append))
    return code, lines


def retained(channel: ScriptedChannel) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = asyncio.run(run_retained(channel=channel, emit=lines.append))
    return code, lines


# -- sim-cleanup (C-10) ----------------------------------------------------------------


def test_cleanup_asks_for_this_run_and_prints_every_count_including_readmitted() -> (
    None
):
    channel = ScriptedChannel(CLEANUP_DATA)

    code, lines = cleanup(channel)

    assert channel.calls == [("cleanup", {"pool": POOL, "run_id": RUN_ID})]
    assert (code, lines) == (
        0,
        [
            (
                "PASS cleanup convention=1 enrollment=2 fursuit=3 activation=4"
                " catch=5 session=6 credential=7 image=8 readmitted=9"
            )
        ],
    )


@pytest.mark.parametrize(
    "result",
    [
        "FAIL_ATTRIBUTION",
        "FAIL_RUN_UNKNOWN",
        "FAIL_STORAGE",
        "FAIL_VERIFY",
        "FAIL_ERROR",
        "FAIL_LAUNCHER",
    ],
)
def test_a_failed_cleanup_prints_only_its_code_and_exits_nonzero(result: str) -> None:
    code, lines = cleanup(ScriptedChannel(FixtureFailed(result)))

    assert (code, lines) == (1, [f"FAIL cleanup result={result}"])


# -- sim-retained (C-11) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("runs", "retained_count", "unfinished", "expected"),
    [
        ([], 0, 0, ["PASS retained retained=0 unfinished=0"]),
        (
            RUNS,
            2,
            1,
            [
                f"RETAINED run_id={RUN_ID} pool={POOL} reason=journeys age_days=0",
                f"RETAINED run_id={OTHER_RUN_ID} pool=p2 reason=interrupted age_days=12",
                (
                    f"RETAINED run_id={OTHER_RUN_ID} pool={POOL} reason=unfinished"
                    " age_days=400"
                ),
                "PASS retained retained=2 unfinished=1",
            ],
        ),
    ],
)
def test_retained_lists_each_run_in_the_order_given_then_the_counts(
    runs: list[dict[str, object]],
    retained_count: int,
    unfinished: int,
    expected: list[str],
) -> None:
    channel = ScriptedChannel(
        {"runs": runs, "retained": retained_count, "unfinished": unfinished}
    )

    code, lines = retained(channel)

    assert channel.calls == [("retained", {})]
    assert (code, lines) == (0, expected)


@pytest.mark.parametrize("result", ["FAIL_LIMIT", "FAIL_LAUNCHER"])
def test_a_failed_retained_prints_only_its_code_and_exits_nonzero(result: str) -> None:
    code, lines = retained(ScriptedChannel(FixtureFailed(result)))

    assert (code, lines) == (1, [f"FAIL retained result={result}"])


# -- command line --------------------------------------------------------------------


@pytest.fixture
def nothing_reached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Trip on the secret prompt, any launcher child and any network call."""
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> None:
        reached.append("touched")
        raise RuntimeError

    monkeypatch.setattr(getpass, "getpass", trip)
    monkeypatch.setattr(subprocess, "Popen", trip)
    monkeypatch.setattr(socket.socket, "connect", trip)
    return reached


def _capture_run(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stub asyncio.run; record the arguments the unstarted coroutine was built with."""
    seen: list[dict[str, Any]] = []

    def run(coroutine: CoroutineType[Any, Any, int]) -> int:
        assert coroutine.cr_frame is not None
        seen.append(dict(coroutine.cr_frame.f_locals))
        coroutine.close()
        return 0

    monkeypatch.setattr(asyncio, "run", run)
    return seen


def test_the_commands_run_through_the_fixture_launcher_with_what_the_user_named(
    nothing_reached: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _capture_run(monkeypatch)

    assert main(["cleanup", "--pool", POOL, "--run-id", RUN_ID]) == 0
    assert main(["retained"]) == 0

    cleaning, listing = seen
    assert (cleaning["pool"], cleaning["run_id"]) == (POOL, RUN_ID)
    assert isinstance(cleaning["channel"], FixtureLauncherChannel)
    assert isinstance(listing["channel"], FixtureLauncherChannel)
    assert nothing_reached == []


CLEANUP_ARGUMENTS: Final = ["--pool", POOL, "--run-id", RUN_ID]
BAD_INPUT: Final[dict[str, list[str]]] = {
    "cleanup-bad-pool": ["cleanup", "--pool", "Bad_Pool", "--run-id", RUN_ID],
    "cleanup-no-pool": ["cleanup", "--run-id", RUN_ID],
    "cleanup-no-run-id": ["cleanup", "--pool", POOL],
    "cleanup-not-a-uuid": ["cleanup", "--pool", POOL, "--run-id", "not-a-uuid"],
    "cleanup-empty": ["cleanup", "--pool", POOL, "--run-id", ""],
    "cleanup-uppercase": ["cleanup", "--pool", POOL, "--run-id", RUN_ID.upper()],
    "cleanup-no-hyphens": [
        "cleanup",
        "--pool",
        POOL,
        "--run-id",
        RUN_ID.replace("-", ""),
    ],
    "cleanup-newline": ["cleanup", "--pool", POOL, "--run-id", f"{RUN_ID}\n"],
    "cleanup-offers-a-target": ["cleanup", *CLEANUP_ARGUMENTS, "--target", "staging"],
    "retained-takes-no-pool": ["retained", "--pool", POOL],
    "retained-offers-a-target": ["retained", "--target", "staging"],
}


@pytest.mark.parametrize("case", BAD_INPUT)
def test_bad_input_is_rejected_before_any_prompt_launcher_or_network(
    nothing_reached: list[str], monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    # Positive control: the same commands are accepted when the input is good.
    seen = _capture_run(monkeypatch)
    assert main(["cleanup", *CLEANUP_ARGUMENTS]) == 0
    assert main(["retained"]) == 0
    assert len(seen) == 2

    seen.clear()
    try:
        code = main(BAD_INPUT[case])
    except SystemExit as exit_:
        code = exit_.code
    except ValueError:
        code = 1

    assert code not in (0, None)
    assert seen == []  # the run function was never even built
    assert nothing_reached == []
