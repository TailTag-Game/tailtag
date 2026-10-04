"""The per-run lifecycle of `sim-fixture-smoke` and `sim-journeys` (#223 C-1, C-3, C-8, C-11).

Both commands share `fixtures.run_provisioned`, so every test here runs against both.
Boundaries substituted: Clerk and TailTag HTTP, the lease channel, the fixture channel
(now also answering `retained`, `cleanup` and `retain`), the inspection channel, the
secret prompt and time. The run, its outcome tracking, CLEANUP, RETAIN and RELEASE are
real.

Contract pinned here (the spec fixes the line shapes; these tests fix the rest):

    PASS target ... / RUN run_id=...
    WARN retained=<n> unfinished=<m>     after RUN, before SETUP; only if n or m > 0
    FAIL setup result=FAIL_RETAINED_LIMIT  after RUN, when retained >= 5; nothing leased
    ... SETUP, SIMULATION, RECONCILIATION as before ...
    PASS cleanup convention=.. enrollment=.. fursuit=.. activation=.. catch=..
        session=.. credential=.. image=..   passing run only; `readmitted` is not printed
    FAIL cleanup result=<CODE>             cleanup failed; the run is then retained
    RETAIN reason=<reason> quarantined=<n> any other outcome once provision passed
    FAIL retain                            the retain call failed
    PASS release | FAIL release            always last, as before

Fixture channel calls, in order: `retained {}`, `provision {..., extras}`, then either
`cleanup {pool, run_id}` (pass) or `retain {pool, run_id, reason}` (anything else).
`extras` is every leased index beyond owners and catchers: the outsider for journeys,
none for the fixture smoke.

Outcome to reason: a failed journey is `journeys` (even if reconciliation also failed),
a failed or erroring reconciliation is `reconciliation`, a failed cleanup is `cleanup`,
and an interrupt is `interrupted`. A simulation-stage failure of the fixture smoke is
not pinned: the spec does not say which reason it gets.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import journey_support
import pool_support
import pytest
from fixture_support import (
    CLEANUP_LINE,
    RETAIN_REASONS,
    FakeFixtureChannel,
    FixtureState,
)
from journey_support import VALID_A, VALID_B
from pool_support import POOL, RUN_ID, SECRET, SHA, FakeChannel, Slot, World
from reconciliation_support import FakeInspectionChannel, edit

from tailtag_simulator.fixtures import FixtureFailed, run_fixture_smoke
from tailtag_simulator.journeys import JourneyImages, run_journeys
from tailtag_simulator.reconciliation import InspectionFailed

world = pool_support.world  # the shared fixtures
journey_world = journey_support.journey_world

TARGET_LINE: Final = f"PASS target staging source_sha={SHA}"
RUN_LINE: Final = f"RUN run_id={RUN_ID}"
INTERRUPTED: Final = 130  # what a run that raised KeyboardInterrupt is reported as here


@dataclass
class Run:
    code: int
    lines: list[str]
    prompts: int


@dataclass
class Rig:
    kind: str
    world: World
    leases: FakeChannel
    fixtures: FakeFixtureChannel
    run: Callable[[], Run]
    # what differs between the two commands
    base: list[str]  # lines up to and including SETUP
    run_indexes: set[int]  # every slot the run leases
    extras: list[int]


def _lose_a_fursuit(state: FixtureState) -> None:
    state.fursuits[2].pop()


def _interrupt(*_args: object) -> None:
    raise KeyboardInterrupt


def build(
    kind: str,
    request: pytest.FixtureRequest,
    *,
    scenario: str | None = None,
    retained: tuple[int, int] = (0, 0),
    ops_fail: dict[str, BaseException] | None = None,
    provision_fail: Exception | None = None,
) -> Rig:
    """A rig for `smoke` or `journeys`, with at most one injected `scenario`.

    Scenarios: `journeys_fail` and `both_fail` and `reconcile_mismatch` (journeys only),
    `reconcile_error` and `interrupt` (both). `cleanup_<CODE>` fails the cleanup call.
    """
    is_journeys = kind == "journeys"
    the_world: Any = request.getfixturevalue(
        "journey_world" if is_journeys else "world"
    )
    leases = FakeChannel(the_world, slots=8 if is_journeys else 6)
    leases.slots[0] = Slot("quarantined")
    ops = dict(ops_fail or {})
    if scenario is not None and scenario.startswith("cleanup_"):
        ops["cleanup"] = FixtureFailed(scenario.removeprefix("cleanup_"))
    tamper = None
    corrupt = None
    inspection_fail = None
    if scenario in ("journeys_fail", "both_fail"):
        the_world.gameplay.break_rule("catch")
    if scenario in ("reconcile_mismatch", "both_fail"):
        corrupt = edit(fixture_photos_unchanged=False)
    if scenario == "reconcile_error":
        if is_journeys:
            inspection_fail = InspectionFailed("FAIL_LEASE")
        else:
            tamper = _lose_a_fursuit

    if is_journeys:
        state = the_world.gameplay.state
    else:
        state = FixtureState()
        the_world.route = state.route
    fixtures = FakeFixtureChannel(
        the_world,
        leases,
        state,
        fail=provision_fail,
        tamper=tamper,
        retained=retained,
        ops_fail=ops,
    )
    if scenario == "interrupt":
        the_world.route = _interrupt  # the first read of SIMULATION

    def run() -> Run:
        lines: list[str] = []
        prompts: list[int] = []

        def emit(line: str) -> None:
            lines.append(line)
            the_world.note("emit", line)

        def prompt() -> str:
            prompts.append(1)
            return SECRET

        common: dict[str, Any] = {
            "prompt_secret": prompt,
            "lease_channel": leases,
            "fixture_channel": fixtures,
            "emit": emit,
            "clerk_transport": the_world.clerk_transport,
            "api_transport": the_world.api_transport,
            "clock": the_world.clock,
            "run_id": RUN_ID,
        }
        if is_journeys:
            coroutine = run_journeys(
                POOL,
                images=JourneyImages(valid_a=VALID_A, valid_b=VALID_B),
                inspection_channel=FakeInspectionChannel(
                    the_world, corrupt=corrupt, fail=inspection_fail
                ),
                **common,
            )
        else:
            coroutine = run_fixture_smoke(POOL, 2, 2, 2, **common)
        try:
            code = asyncio.run(coroutine)
        except (KeyboardInterrupt, asyncio.CancelledError):
            code = INTERRUPTED
        return Run(code, lines, len(prompts))

    identities = 7 if is_journeys else 4
    return Rig(
        kind,
        the_world,
        leases,
        fixtures,
        run,
        [TARGET_LINE, RUN_LINE, f"PASS setup identities={identities} fursuits=4"],
        set(range(1, identities + 1)),
        [7] if is_journeys else [],
    )


KINDS: Final = ["smoke", "journeys"]
both_commands = pytest.mark.parametrize("kind", KINDS)


def assert_released(rig: Rig) -> None:
    assert rig.leases.indexes("leased") == set()
    assert rig.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert set(rig.world.ended_sessions) == set(rig.world.opened_sessions)
    assert len(rig.world.ended_sessions) == len(rig.world.opened_sessions) > 0


def position(rig: Rig, entry: tuple[str, str]) -> int:
    return rig.world.log.index(entry)


def release_position(rig: Rig) -> int:
    return next(
        at
        for at, (kind, detail) in enumerate(rig.world.log)
        if kind == "channel" and detail.startswith("release")
    )


# -- C-3: a passing run cleans itself before release -------------------------------


@both_commands
def test_a_passing_run_cleans_up_while_still_leased_before_release_and_never_retains(
    request: pytest.FixtureRequest, kind: str
) -> None:
    rig = build(kind, request)

    run = rig.run()

    assert run.code == 0
    assert run.lines[:3] == rig.base
    assert run.lines[-2:] == [CLEANUP_LINE, "PASS release"]
    assert not [x for x in run.lines if x.startswith(("WARN", "RETAIN", "FAIL"))]
    assert rig.fixtures.operations == ["retained", "provision", "cleanup"]
    assert rig.fixtures.calls_to("retained") == [{}]
    (provision,) = rig.fixtures.calls_to("provision")
    assert provision["extras"] == rig.extras
    assert rig.fixtures.calls_to("cleanup") == [{"pool": POOL, "run_id": RUN_ID}]
    # Every slot is still leased when cleanup runs; release comes after it.
    leased = dict(rig.fixtures.leased_during)["cleanup"]
    assert leased == rig.run_indexes
    log = rig.world.log
    allocate = next(
        at
        for at, (kind_, detail) in enumerate(log)
        if kind_ == "channel" and detail.startswith("allocate")
    )
    cleaned = position(rig, ("fixture", "cleanup"))
    assert position(rig, ("fixture", "retained")) < allocate
    assert cleaned < position(rig, ("emit", CLEANUP_LINE)) < release_position(rig)
    assert_released(rig)
    assert rig.leases.indexes("quarantined") == {0}


# -- C-8: any failure after provision retains instead of cleaning --------------------

# case -> (retain reason, the commands that can inject it)
OUTCOMES: Final[dict[str, tuple[str, set[str]]]] = {
    "journeys_fail": ("journeys", {"journeys"}),
    "both_fail": ("journeys", {"journeys"}),
    "reconcile_mismatch": ("reconciliation", {"journeys"}),
    "reconcile_error": ("reconciliation", {"smoke", "journeys"}),
    "interrupt": ("interrupted", {"smoke", "journeys"}),
    "cleanup_FAIL_STORAGE": ("cleanup", {"smoke", "journeys"}),
    "cleanup_FAIL_ATTRIBUTION": ("cleanup", {"smoke", "journeys"}),
}
OUTCOME_CASES: Final = [
    pytest.param(kind, case, id=f"{kind}-{case}")
    for case, (_, kinds) in OUTCOMES.items()
    for kind in KINDS
    if kind in kinds
]


def test_every_retain_reason_has_a_case() -> None:
    assert {reason for reason, _ in OUTCOMES.values()} == RETAIN_REASONS


@pytest.mark.parametrize(("kind", "case"), OUTCOME_CASES)
def test_a_failing_run_is_retained_with_its_reason_not_cleaned_and_still_released(
    request: pytest.FixtureRequest, kind: str, case: str
) -> None:
    reason, _ = OUTCOMES[case]
    rig = build(kind, request, scenario=case)

    run = rig.run()

    assert run.code != 0
    cleanup_failed = case.startswith("cleanup_")
    assert rig.fixtures.operations == [
        "retained",
        "provision",
        *["cleanup"] * cleanup_failed,
        "retain",
    ]
    assert rig.fixtures.calls_to("retain") == [
        {"pool": POOL, "run_id": RUN_ID, "reason": reason}
    ]
    assert run.lines[:3] == rig.base
    assert run.lines[-2:] == [
        f"RETAIN reason={reason} quarantined={len(rig.run_indexes)}",
        "PASS release",
    ]
    assert not [x for x in run.lines if x.startswith("PASS cleanup")]
    if cleanup_failed:
        assert run.lines[-3] == f"FAIL cleanup result={case.removeprefix('cleanup_')}"
    else:
        assert not [x for x in run.lines if x.startswith("FAIL cleanup")]
    # RETAIN quarantines the live slots, so it must come before release frees them.
    assert position(rig, ("fixture", "retain")) < release_position(rig)
    assert_released(rig)
    assert rig.leases.indexes("quarantined") == {0, *rig.run_indexes}


@both_commands
def test_a_failed_retain_is_reported_without_detail_and_release_still_runs(
    request: pytest.FixtureRequest, kind: str
) -> None:
    rig = build(
        kind,
        request,
        scenario="reconcile_error",
        ops_fail={"retain": FixtureFailed("FAIL_ERROR")},
    )

    run = rig.run()

    assert run.code != 0
    assert run.lines[-2:] == ["FAIL retain", "PASS release"]
    assert not [x for x in run.lines if x.startswith("RETAIN")]
    assert rig.fixtures.operations[-1] == "retain"
    assert_released(rig)


@both_commands
def test_an_interrupt_during_cleanup_retains_the_run_as_interrupted_and_releases(
    request: pytest.FixtureRequest, kind: str
) -> None:
    rig = build(kind, request, ops_fail={"cleanup": KeyboardInterrupt()})

    run = rig.run()

    assert run.code != 0
    assert rig.fixtures.operations == ["retained", "provision", "cleanup", "retain"]
    assert rig.fixtures.calls_to("retain") == [
        {"pool": POOL, "run_id": RUN_ID, "reason": "interrupted"}
    ]
    assert run.lines[-2:] == [
        f"RETAIN reason=interrupted quarantined={len(rig.run_indexes)}",
        "PASS release",
    ]
    assert_released(rig)


@both_commands
@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, asyncio.CancelledError])
def test_an_interrupt_during_retain_still_ends_sessions_and_releases_the_leases(
    request: pytest.FixtureRequest, kind: str, interrupt: type[BaseException]
) -> None:
    rig = build(
        kind,
        request,
        scenario="reconcile_error",
        ops_fail={"retain": interrupt()},
    )

    run = rig.run()

    assert run.code != 0
    assert rig.fixtures.operations[-1] == "retain"
    assert run.lines[-1] == "PASS release"
    assert_released(rig)


# -- C-8: a setup failure before provision passes behaves as it did ------------------


def _dirty_provision(request: pytest.FixtureRequest, kind: str) -> Rig:
    return build(kind, request, provision_fail=FixtureFailed("FAIL_DIRTY", 1))


def _unusable_identity(request: pytest.FixtureRequest, kind: str) -> Rig:
    rig = build(kind, request)
    del rig.world.users[3]
    return rig


SETUP_FAILURES: Final = {
    "provision-refused": (_dirty_provision, ["retained", "provision"]),
    "identity-unusable": (_unusable_identity, ["retained"]),
}


@both_commands
@pytest.mark.parametrize("case", SETUP_FAILURES)
def test_a_setup_failure_neither_cleans_nor_retains_and_still_releases(
    request: pytest.FixtureRequest, kind: str, case: str
) -> None:
    build_rig, operations = SETUP_FAILURES[case]
    rig = build_rig(request, kind)

    run = rig.run()

    assert run.code != 0
    assert rig.fixtures.operations == operations
    assert run.lines[:2] == rig.base[:2]
    assert run.lines[-2].startswith("FAIL setup")
    assert run.lines[-1] == "PASS release"
    assert not [
        x
        for x in run.lines
        if x.startswith(("RETAIN", "FAIL retain", "PASS cleanup", "FAIL cleanup"))
    ]
    assert rig.leases.indexes("leased") == set()


# -- C-11: the retained cap and the WARN line ------------------------------------------


@both_commands
@pytest.mark.parametrize("counts", [(5, 0), (9, 2)])
def test_a_run_at_the_retained_cap_leases_nothing_and_never_touches_clerk(
    request: pytest.FixtureRequest, kind: str, counts: tuple[int, int]
) -> None:
    rig = build(kind, request, retained=counts)

    run = rig.run()

    assert run.code != 0
    # Whether the WARN line also precedes the refusal is the implementation's choice.
    assert run.lines[:2] == rig.base[:2]
    assert run.lines[-1] == "FAIL setup result=FAIL_RETAINED_LIMIT"
    assert set(run.lines[2:-1]) <= {f"WARN retained={counts[0]} unfinished={counts[1]}"}
    assert rig.fixtures.operations == ["retained"]
    assert rig.leases.calls == []
    assert run.prompts == 0
    assert rig.world.kinds("backend", "frontend") == []
    assert {call[1:] for call in rig.world.api_calls} == {("/health/identity", None)}


@both_commands
@pytest.mark.parametrize(
    ("counts", "warning"),
    [
        ((0, 0), None),
        ((1, 0), "WARN retained=1 unfinished=0"),
        ((0, 3), "WARN retained=0 unfinished=3"),
        ((4, 2), "WARN retained=4 unfinished=2"),
    ],
)
def test_the_warn_line_appears_only_when_something_is_retained_or_unfinished(
    request: pytest.FixtureRequest,
    kind: str,
    counts: tuple[int, int],
    warning: str | None,
) -> None:
    rig = build(kind, request, retained=counts)

    run = rig.run()

    # Below the cap the run goes on and still cleans itself.
    assert run.code == 0
    expected = [*rig.base[:2], *([warning] if warning else []), rig.base[2]]
    assert run.lines[: len(expected)] == expected
    assert [x for x in run.lines if x.startswith("WARN")] == (
        [warning] if warning else []
    )
    assert rig.fixtures.operations == ["retained", "provision", "cleanup"]
