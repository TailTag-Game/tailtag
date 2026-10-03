"""Behavioral tests for the fixture smoke run (#220 F-3, F-8, F-12, F-14).

Boundaries substituted: Clerk and TailTag HTTP, the lease channel, the fixture
channel, the secret prompt and time (see pool_support and fixture_support). Target
verification, identity opening, the phases, reconciliation and reporting all run
for real.

Stage lines are fixed by these tests:

    PASS target staging source_sha=<sha>
    RUN run_id=<uuid>
    PASS setup identities=<owners+catchers> fursuits=<owners*per owner>
    PASS simulation | PASS reconciliation | PASS release
    FAIL setup result=<CODE> [quarantined=<n>]    (provision refused or failed)
    FAIL setup needed=<n> available=<m>           (#219 setup, unchanged)
    FAIL setup quarantined=<i,j,...>              (#219 setup, unchanged)
    FAIL simulation | FAIL reconciliation | FAIL release
"""

import asyncio
import getpass
import logging
import re
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from types import CoroutineType
from typing import Any

import httpx
import pool_support
import pytest
from fixture_support import (
    ACTIVATIONS_PATH,
    ACTIVE_PATH,
    FURSUITS_PATH,
    LEAK_SENTINELS,
    OTHER_CONVENTION_ID,
    FakeFixtureChannel,
    FixtureState,
    enrollment_body,
)
from pool_support import (
    POOL,
    RUN_ID,
    SECRET,
    SENSITIVE_PREFIXES,
    SHA,
    FakeChannel,
    Slot,
    World,
)

from tailtag_simulator.__main__ import main
from tailtag_simulator.fixtures import FixtureFailed, run_fixture_smoke

world = pool_support.world  # the shared fixture

OWNERS, CATCHERS, PER_OWNER = 2, 2, 2
# Slot 0 is already quarantined, so the run is allocated slots 1 to 4 and the owner
# and catcher indexes differ from their positions.
OWNER_INDEXES, CATCHER_INDEXES = [1, 2], [3, 4]

TARGET_LINE = f"PASS target staging source_sha={SHA}"
RUN_LINE = f"RUN run_id={RUN_ID}"
SETUP_LINE = f"PASS setup identities={OWNERS + CATCHERS} fursuits={OWNERS * PER_OWNER}"
BASE = [TARGET_LINE, RUN_LINE, SETUP_LINE]
FIXED_LINES = re.compile(
    rf"PASS target staging source_sha={SHA}"
    r"|RUN run_id=[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    r"|PASS setup identities=\d+ fursuits=\d+"
    r"|PASS (simulation|reconciliation|release)"
    r"|FAIL (target|simulation|reconciliation|release)"
    r"|FAIL setup( needed=\d+ available=\d+"
    r"| quarantined=\d+(,\d+)*"
    r"| result=FAIL_[A-Z_]+( quarantined=\d+)?)?"
)
PUBLIC_READS = (ACTIVE_PATH, FURSUITS_PATH, ACTIVATIONS_PATH)


@dataclass
class Rig:
    world: World
    leases: FakeChannel
    fixtures: FakeFixtureChannel


@dataclass
class Run:
    code: int
    lines: list[str]
    prompts: int


def make_rig(
    world: World,
    *,
    slots: int = 6,
    fail: Exception | None = None,
    tamper: Callable[[FixtureState], None] | None = None,
    lease_fail: set[str] | None = None,
) -> Rig:
    leases = FakeChannel(world, slots=slots, fail=lease_fail)
    leases.slots[0] = Slot("quarantined")
    state = FixtureState()
    world.route = state.route
    return Rig(
        world,
        leases,
        FakeFixtureChannel(world, leases, state, fail=fail, tamper=tamper),
    )


def smoke(rig: Rig) -> Run:
    world = rig.world
    prompts: list[str] = []

    def prompt() -> str:
        prompts.append(SECRET)
        world.note("prompt")
        return SECRET

    lines: list[str] = []

    def emit(line: str) -> None:
        lines.append(line)
        world.note("emit", line)

    code = asyncio.run(
        run_fixture_smoke(
            POOL,
            OWNERS,
            PER_OWNER,
            CATCHERS,
            prompt_secret=prompt,
            lease_channel=rig.leases,
            fixture_channel=rig.fixtures,
            emit=emit,
            clerk_transport=world.clerk_transport,
            api_transport=world.api_transport,
            clock=world.clock,
            run_id=RUN_ID,
        )
    )
    return Run(code, lines, len(prompts))


def assert_released(rig: Rig) -> None:
    assert rig.leases.indexes("leased") == set()
    assert rig.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert set(rig.world.ended_sessions) == set(rig.world.opened_sessions)
    assert len(rig.world.ended_sessions) == len(rig.world.opened_sessions)


def assert_only_fixed_output(run: Run) -> None:
    assert all(FIXED_LINES.fullmatch(line) for line in run.lines), run.lines
    joined = "\n".join(run.lines)
    assert not any(s in joined for s in (*LEAK_SENTINELS, SECRET, *SENSITIVE_PREFIXES))


def public_reads(world: World) -> set[tuple[str, str, int | None]]:
    return {call for call in world.api_calls if call[1] in PUBLIC_READS}


def read_positions(world: World) -> list[int]:
    return [
        i
        for i, (kind, detail) in enumerate(world.log)
        if kind == "api" and any(path in detail for path in PUBLIC_READS)
    ]


# -- the happy path (F-1 hand-off, F-14) -------------------------------------------


def test_successful_run_provisions_once_reads_publicly_and_reports_only_fixed_lines(
    world: World,
) -> None:
    rig = make_rig(world)

    run = smoke(rig)

    assert run.code == 0
    assert run.lines == [
        *BASE,
        "PASS simulation",
        "PASS reconciliation",
        "PASS release",
    ]
    assert_only_fixed_output(run)
    assert rig.leases.calls_to("allocate") == [
        {"run_id": RUN_ID, "count": OWNERS + CATCHERS, "ttl_seconds": 1800}
    ]
    assert rig.fixtures.calls == [
        (
            "provision",
            {
                "pool": POOL,
                "run_id": RUN_ID,
                "owners": OWNER_INDEXES,
                "catchers": CATCHER_INDEXES,
                "fursuits_per_owner": PER_OWNER,
            },
        )
    ]
    assert_released(rig)
    assert rig.leases.calls_to("quarantine") == []
    assert rig.leases.indexes("free") == {5, *OWNER_INDEXES, *CATCHER_INDEXES}
    # SIMULATION: every identity reads its active Convention; only owners read their
    # fursuits and activations; nothing but GET reads follows onboarding.
    everyone = [*OWNER_INDEXES, *CATCHER_INDEXES]
    assert public_reads(world) == {
        *{("GET", ACTIVE_PATH, i) for i in everyone},
        *{("GET", FURSUITS_PATH, i) for i in OWNER_INDEXES},
        *{("GET", ACTIVATIONS_PATH, i) for i in OWNER_INDEXES},
    }
    assert {(m, p) for m, p, _ in world.api_calls if m != "GET"} == {
        ("PUT", "/api/profile/")
    }
    assert world.stray == []


# -- F-3: SIMULATION is public reads only; the secret stays in SETUP ------------------


def test_provision_follows_onboarding_and_nothing_privileged_runs_during_simulation(
    world: World,
) -> None:
    rig = make_rig(world)

    run = smoke(rig)

    assert run.code == 0 and run.prompts == 1
    log = world.log
    kinds = [kind for kind, _ in log]
    provision = log.index(("fixture", "provision"))
    reads = read_positions(world)
    first, last = reads[0], reads[-1]
    onboarding = [i for i, (_, d) in enumerate(log) if "/api/profile/" in d]
    allocate = next(
        i for i, (k, d) in enumerate(log) if k == "channel" and "allocate" in d
    )
    # SETUP: allocate, open and onboard every identity, then provision once.
    assert allocate < max(onboarding) < provision < first
    assert kinds.count("fixture") == 1
    # The Clerk secret exists only before provisioning: no admin call, prompt or
    # privileged call of any kind falls between the first and the last public read.
    assert max(i for i, k in enumerate(kinds) if k == "backend") < provision
    assert {kinds[i] for i in range(first, last + 1)} <= {"api", "frontend"}
    # Afterwards only the release runs; any heartbeat must follow provisioning.
    after = [
        (k, d) for k, d in log[last + 1 :] if k in ("channel", "fixture", "backend")
    ]
    assert [d.split()[0] for _, d in after] == ["release"]
    assert all(
        i > provision
        for i, (k, d) in enumerate(log)
        if k == "channel" and d.startswith("heartbeat")
    )
    # The secret reaches neither privileged channel nor any TailTag request.
    assert SECRET not in str(rig.fixtures.calls) + str(rig.leases.calls)
    for request in world.api_requests:
        assert SECRET not in f"{request.url}{dict(request.headers)}{request.content!r}"


# -- failures before or during provisioning ---------------------------------------


def test_an_unverified_target_fails_before_any_prompt_lease_or_provision(
    world: World,
) -> None:
    world.identity_environment = "development"
    rig = make_rig(world)

    run = smoke(rig)

    assert (run.code, run.lines, run.prompts) == (1, ["FAIL target"], 0)
    assert rig.leases.calls == [] and rig.fixtures.calls == []


def _shortfall(world: World) -> Rig:
    return make_rig(world, slots=4)  # slot 0 is quarantined: 3 available, 4 needed


def _bad_identity(world: World) -> Rig:
    del world.users[3]
    return make_rig(world)


# case -> (rig, expected tail after BASE[:2], quarantined slots, release expected)
SETUP_FAILURES: dict[str, tuple[Callable[[World], Rig], str, set[int], bool]] = {
    "shortfall": (_shortfall, "FAIL setup needed=4 available=3", {0}, False),
    "unusable-identity": (_bad_identity, "FAIL setup quarantined=3", {0, 3}, True),
}


@pytest.mark.parametrize("case", SETUP_FAILURES)
def test_a_failed_identity_setup_never_provisions_and_releases_what_it_leased(
    world: World, case: str
) -> None:
    build, failure, quarantined, released = SETUP_FAILURES[case]
    rig = build(world)

    run = smoke(rig)

    assert run.code == 1
    assert run.lines == [TARGET_LINE, RUN_LINE, failure, *(["PASS release"] * released)]
    assert rig.fixtures.calls == []
    assert rig.leases.indexes("quarantined") == quarantined
    assert rig.leases.indexes("leased") == set()
    assert len(rig.leases.calls_to("release")) == int(released)
    assert public_reads(world) == set()


# provision failure -> the one FAIL line, and the slots the relay itself quarantined
PROVISION_FAILURES: dict[str, tuple[Exception, str, set[int]]] = {
    "dirty": (
        FixtureFailed("FAIL_DIRTY", 2),
        "FAIL setup result=FAIL_DIRTY quarantined=2",
        {0, 1, 2},
    ),
    "lease": (FixtureFailed("FAIL_LEASE"), "FAIL setup result=FAIL_LEASE", {0}),
    "invariant": (
        FixtureFailed("FAIL_INVARIANT"),
        "FAIL setup result=FAIL_INVARIANT",
        {0},
    ),
    "launcher": (
        FixtureFailed("FAIL_LAUNCHER"),
        "FAIL setup result=FAIL_LAUNCHER",
        {0},
    ),
    "unexpected-exception": (
        RuntimeError("SENTINEL-DETAIL sp_p1_1 sk_live_X"),
        "FAIL setup",
        {0},
    ),
}


@pytest.mark.parametrize("case", PROVISION_FAILURES)
def test_a_failed_provision_reports_one_fixed_line_and_still_releases_the_leases(
    world: World, case: str
) -> None:
    failure, line, quarantined = PROVISION_FAILURES[case]
    rig = make_rig(world, fail=failure)

    run = smoke(rig)

    assert run.code == 1
    assert run.lines == [TARGET_LINE, RUN_LINE, line, "PASS release"]
    assert_only_fixed_output(run)
    assert len(rig.fixtures.calls) == 1
    assert_released(rig)
    assert public_reads(world) == set()
    # A dirty identity was already quarantined by the relay; the simulator does not
    # quarantine again, and the rest of the run's slots go back to the pool.
    assert rig.leases.calls_to("quarantine") == []
    assert rig.leases.indexes("quarantined") == quarantined
    assert rig.leases.indexes("free") == set(range(6)) - quarantined


# -- RECONCILIATION (F-14) --------------------------------------------------------


def _different_convention(state: FixtureState) -> None:
    state.enrollments[3] = enrollment_body(OTHER_CONVENTION_ID)


def _no_active_convention(state: FixtureState) -> None:
    state.enrollments[4] = enrollment_body(None)


def _missing_fursuit(state: FixtureState) -> None:
    state.fursuits[2].pop()


def _extra_fursuit(state: FixtureState) -> None:
    state.fursuits[1].append(dict(state.fursuits[1][0], id=999))


def _disabled_fursuit(state: FixtureState) -> None:
    state.fursuits[1][0]["is_enabled"] = False


def _fursuit_without_photo(state: FixtureState) -> None:
    state.fursuits[1][0]["photo_url"] = ""


def _missing_activation(state: FixtureState) -> None:
    state.activations[2].pop()


def _inactive_activation(state: FixtureState) -> None:
    state.activations[1][0]["is_active"] = False


def _activation_in_another_convention(state: FixtureState) -> None:
    state.activations[2][0]["convention_id"] = OTHER_CONVENTION_ID


def _fursuit_read_rejected(state: FixtureState) -> None:
    state.reply_override[("GET", FURSUITS_PATH, 1)] = httpx.Response(500, json={})


def _read_unreachable(state: FixtureState) -> None:
    state.reply_override[("GET", ACTIVE_PATH, 3)] = httpx.ConnectError("x")


MISMATCHES: dict[str, tuple[Callable[[FixtureState], None], list[str]]] = {
    "catcher-sees-another-convention": (_different_convention, ["PASS simulation"]),
    "catcher-has-no-active-convention": (_no_active_convention, ["PASS simulation"]),
    "owner-is-missing-a-fursuit": (_missing_fursuit, ["PASS simulation"]),
    "owner-has-an-extra-fursuit": (_extra_fursuit, ["PASS simulation"]),
    "fursuit-is-disabled": (_disabled_fursuit, ["PASS simulation"]),
    "fursuit-has-no-photo": (_fursuit_without_photo, ["PASS simulation"]),
    "fursuit-has-no-activation": (_missing_activation, ["PASS simulation"]),
    "activation-is-inactive": (_inactive_activation, ["PASS simulation"]),
    "activation-is-in-another-convention": (
        _activation_in_another_convention,
        ["PASS simulation"],
    ),
    "read-is-rejected": (_fursuit_read_rejected, ["PASS simulation"]),
    "read-cannot-complete": (_read_unreachable, []),
}


@pytest.mark.parametrize("case", MISMATCHES)
def test_provisioned_state_that_does_not_match_fails_and_still_releases(
    world: World, case: str
) -> None:
    tamper, passed = MISMATCHES[case]
    rig = make_rig(world, tamper=tamper)

    run = smoke(rig)

    failed = "FAIL reconciliation" if passed else "FAIL simulation"
    assert run.code == 1
    assert run.lines == [*BASE, *passed, failed, "PASS release"]
    assert_only_fixed_output(run)
    assert_released(rig)


def test_a_failed_release_is_reported_after_a_run_that_otherwise_passed(
    world: World,
) -> None:
    rig = make_rig(world, lease_fail={"release"})

    run = smoke(rig)

    assert run.code == 1
    assert run.lines == [
        *BASE,
        "PASS simulation",
        "PASS reconciliation",
        "FAIL release",
    ]
    assert len(rig.leases.calls_to("release")) == 1
    assert set(world.ended_sessions) == set(world.opened_sessions)


# -- CLI wiring: mirrors what test_pool.py proves for pool-smoke ------------------------


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


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ([], (2, 1, 2)),
        (["--owners", "3", "--fursuits", "4", "--catchers", "5"], (3, 4, 5)),
    ],
)
def test_cli_passes_the_pool_and_counts_through_with_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
    extra: list[str],
    expected: tuple[int, int, int],
) -> None:
    # httpx logs full URLs at INFO; main() must silence them before it starts the run.
    loggers = [logging.getLogger(name) for name in ("httpx", "httpcore")]
    for logger in loggers:
        monkeypatch.setattr(logger, "level", logging.NOTSET)
        monkeypatch.setattr(logger, "propagate", True)
    seen = _capture_run(monkeypatch)

    assert main(["fixture-smoke", "--pool", POOL, *extra]) == 0

    (arguments,) = seen
    assert (
        arguments["pool"],
        arguments["owners"],
        arguments["fursuits_per_owner"],
        arguments["catchers"],
    ) == (POOL, *expected)
    for logger in loggers:
        assert logger.level == logging.WARNING and logger.propagate is False


@pytest.mark.parametrize(
    "arguments",
    [
        ["--pool", "Bad_Pool"],
        ["--pool", "a" * 13],
        ["--pool", "p1\n"],
        [],
        ["--pool", POOL, "--owners", "many"],
        ["--pool", POOL, "--target", "staging"],
        ["--pool", POOL, "--base-url", "http://x"],
    ],
)
def test_cli_rejects_bad_input_and_offers_no_target_before_anything_is_reached(
    monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> None:
        reached.append("touched")
        raise RuntimeError

    monkeypatch.setattr(getpass, "getpass", trip)  # the secret prompt
    monkeypatch.setattr(subprocess, "Popen", trip)  # any launcher child
    monkeypatch.setattr(socket.socket, "connect", trip)  # any network call

    try:
        code = main(["fixture-smoke", *arguments])
    except SystemExit as exit_:
        code = exit_.code
    except ValueError:
        code = 1

    assert code not in (0, None)
    assert reached == []
