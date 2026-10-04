"""Behavioral tests for the headless acceptance journeys (#221 J-1 to J-10).

Boundaries substituted: Clerk and TailTag HTTP, the lease channel, the fixture
channel, the secret prompt and time (see pool_support, fixture_support and
journey_support). Target verification, identity opening, the 13 journeys and their
reporting all run for real against the in-memory gameplay API.

Output lines are fixed by these tests (after the #220 target, RUN and setup lines):

    PASS journey=<name>
    FAIL journey=<name> step=<step> expected=<status>/<code> observed=<status>/<code>
    PASS journeys passed=13 | FAIL journeys failed=<n>
    PASS reconciliation checks=14 | FAIL reconciliation ... (see test_reconciliation)
    PASS cleanup ... | RETAIN reason=<reason> quarantined=<n> (see test_run_lifecycle)
    PASS release

Reconciliation of a correct run is asserted here; what it reports for each kind of
fault is in test_reconciliation. The broken-API cases below assert only the journey
and release lines.
"""

import asyncio
import getpass
import re
import socket
import subprocess
from dataclasses import dataclass
from types import CoroutineType
from typing import Any, Final

import journey_support
import pool_support
import pytest
from fixture_support import (
    ACTIVE_PATH,
    CLEANUP_LINE,
    CONVENTION_ID,
    FakeFixtureChannel,
)
from journey_support import (
    AVATAR_PATH,
    CONFIRM_PATH,
    CREATE_PATH,
    CREDENTIAL,
    HISTORY_PATH,
    JOURNEY_LEAKS,
    RESOLVE_PATH,
    ROTATE,
    VALID_A,
    VALID_B,
    JourneyWorld,
    path_for,
)
from pool_support import POOL, RUN_ID, SECRET, SHA, FakeChannel, Slot
from reconciliation_support import (
    RECONCILIATION_LEAKS,
    Corrupt,
    FakeInspectionChannel,
)

from tailtag_simulator.__main__ import (
    INSPECTION_LAUNCHER_COMMAND,
    REPOSITORY_ROOT,
    main,
)
from tailtag_simulator.fixtures import FixtureFailed
from tailtag_simulator.journeys import JOURNEY_NAMES, JourneyImages, run_journeys
from tailtag_simulator.reconciliation import (
    InspectionFailed,
    InspectionLauncherChannel,
    Role,
)

world = pool_support.world  # the shared fixtures
journey_world = journey_support.journey_world

# Slot 0 is quarantined, so the run leases slots 1 to 7: owners 1 and 2 (fursuits
# 100, 101 and 200, 201), catchers 3 to 6 and the unprovisioned outsider 7.
O1, O2, C1, C2, C3, C4, OUTSIDER = 1, 2, 3, 4, 5, 6, 7
F1A, F1B, F2A, F2B = 100, 101, 200, 201
IMAGES: Final = JourneyImages(valid_a=VALID_A, valid_b=VALID_B)

NAMES: Final = (
    "unauthenticated",
    "catch",
    "retry",
    "stopped_session",
    "stale_credential",
    "deactivated",
    "self_catch",
    "convention_mismatch",
    "ineligible_catcher",
    "not_owner",
    "avatar",
    "fursuit_photo",
    "image_rejections",
)
BASE = [
    f"PASS target staging source_sha={SHA}",
    f"RUN run_id={RUN_ID}",
    "PASS setup identities=7 fursuits=4",
]
CHECKS: Final = (
    "inspect",
    "contamination",
    "duplicate",
    "missing",
    "unexpected",
    "catch_id",
    "caught_at",
    "provenance",
    "window",
    "history",
    "count",
    "fixture_photo",
    "created_fursuit",
    "avatar",
)
ROLES: Final = (
    "owner0",
    "owner1",
    "catcher0",
    "catcher1",
    "catcher2",
    "catcher3",
    "outsider",
)
CODE = (
    "(created|already_caught|catcher_ineligible|active_convention_mismatch"
    "|self_catch_not_allowed|catch_target_unavailable"
    "|unsupported_format|invalid_image|too_many_pixels|-)"
)
FIXED_LINES = re.compile(
    rf"PASS target staging source_sha={SHA}"
    r"|RUN run_id=[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    r"|PASS setup identities=7 fursuits=4"
    rf"|PASS journey=({'|'.join(NAMES)})"
    rf"|FAIL journey=({'|'.join(NAMES)}) step=[a-z_]+ expected=\d{{3}}/{CODE}"
    rf" observed=(\d{{3}}/({CODE[1:-1]}|other|shape)|error)"
    r"|PASS journeys passed=13|FAIL journeys failed=\d+"
    r"|PASS reconciliation checks=14"
    r"|FAIL reconciliation result=(FAIL_LEASE|FAIL_RUN_UNKNOWN|FAIL_LIMIT"
    r"|FAIL_REQUEST|FAIL_TARGET|FAIL_BOOTSTRAP|FAIL_LAUNCHER)"
    rf"|FAIL reconciliation check=({'|'.join(CHECKS)}) journey=({'|'.join(NAMES)}|-)"
    rf" role=({'|'.join(ROLES)}|-) expected=\d observed=\d"
    r"|FAIL reconciliation discrepancies=\d"
    r"|PASS release"
    r"|PASS cleanup( (convention|enrollment|fursuit|activation|catch|session"
    r"|credential|image)=\d+){8}"
    r"|RETAIN reason=(journeys|reconciliation|cleanup|interrupted) quarantined=\d+"
    r"|FAIL setup result=FAIL_[A-Z_]+"
)


@dataclass
class Rig:
    world: JourneyWorld
    leases: FakeChannel
    fixtures: FakeFixtureChannel
    inspection: FakeInspectionChannel


@dataclass
class Run:
    code: int
    lines: list[str]


def make_rig(
    world: JourneyWorld,
    *,
    fail: Exception | None = None,
    corrupt: Corrupt | None = None,
    inspection_fail: InspectionFailed | None = None,
) -> Rig:
    leases = FakeChannel(world, slots=8)
    leases.slots[0] = Slot("quarantined")
    fixtures = FakeFixtureChannel(world, leases, world.gameplay.state, fail=fail)
    inspection = FakeInspectionChannel(world, corrupt=corrupt, fail=inspection_fail)
    return Rig(world, leases, fixtures, inspection)


def journeys(rig: Rig, run_id: str | None = RUN_ID) -> Run:
    world = rig.world
    lines: list[str] = []

    def emit(line: str) -> None:
        lines.append(line)
        world.note("emit", line)

    code = asyncio.run(
        run_journeys(
            POOL,
            images=IMAGES,
            prompt_secret=lambda: SECRET,
            lease_channel=rig.leases,
            fixture_channel=rig.fixtures,
            inspection_channel=rig.inspection,
            emit=emit,
            clerk_transport=world.clerk_transport,
            api_transport=world.api_transport,
            clock=world.clock,
            run_id=run_id,
        )
    )
    return Run(code, lines)


def assert_released(rig: Rig, run_id: str = RUN_ID) -> None:
    assert rig.leases.indexes("leased") == set()
    assert rig.leases.calls_to("release") == [{"run_id": run_id}]
    assert set(rig.world.ended_sessions) == set(rig.world.opened_sessions)


def assert_only_fixed_output(run: Run) -> None:
    assert all(FIXED_LINES.fullmatch(line) for line in run.lines), run.lines
    text = "\n".join(run.lines)
    assert not any(leak in text for leak in (*JOURNEY_LEAKS, *RECONCILIATION_LEAKS))


@pytest.fixture
def happy(journey_world: JourneyWorld) -> tuple[Rig, Run]:
    rig = make_rig(journey_world)
    return rig, journeys(rig)


# -- FM2, FM3: a correct API passes everything and prints only fixed lines ---------


def test_journeys_run_in_the_documented_order() -> None:
    assert JOURNEY_NAMES == NAMES


def test_a_correct_api_passes_all_journeys_with_only_fixed_output(
    journey_world: JourneyWorld,
) -> None:
    # No run id is given, so the one the run generates must reach every channel.
    rig = make_rig(journey_world)
    run = journeys(rig, run_id=None)
    run_id = run.lines[1].removeprefix("RUN run_id=")

    assert run.code == 0
    assert run_id != RUN_ID
    assert run.lines == [
        *BASE[:1],
        f"RUN run_id={run_id}",
        *BASE[2:],
        *[f"PASS journey={name}" for name in NAMES],
        "PASS journeys passed=13",
        "PASS reconciliation checks=14",
        CLEANUP_LINE,
        "PASS release",
    ]
    assert_only_fixed_output(run)
    # Seven identities are leased; only the first six are provisioned.
    assert rig.leases.calls_to("allocate") == [
        {"run_id": run_id, "count": 7, "ttl_seconds": 1800}
    ]
    assert rig.fixtures.calls_to("provision") == [
        {
            "pool": POOL,
            "run_id": run_id,
            "owners": [O1, O2],
            "catchers": [C1, C2, C3, C4],
            "fursuits_per_owner": 2,
            "extras": [OUTSIDER],
        }
    ]
    assert [(pool, run) for pool, run, _ in rig.inspection.calls] == [(POOL, run_id)]
    assert_released(rig, run_id)
    # Only the two unauthenticated probes are ever turned away.
    assert rig.world.stray == ["unauthenticated GET /api/me/"] * 2


# -- FM1, FM3, FM7: each journey fails alone, on its own step ---------------------

# case -> (rule the fake breaks, journey, failed step, expected, observed)
BREAKS: dict[str, tuple[str, str, str, str, str]] = {
    "unauthenticated": (
        "unauthenticated",
        "unauthenticated",
        "malformed_token",
        "401/-",
        "200/-",
    ),
    "catch": ("catch", "catch", "confirm", "201/created", "200/already_caught"),
    "retry": (
        "retry",
        "retry",
        "confirm_stopped",
        "200/already_caught",
        "404/catch_target_unavailable",
    ),
    "stopped_session": (
        "stopped_session",
        "stopped_session",
        "confirm",
        "404/catch_target_unavailable",
        "201/created",
    ),
    "stale_credential": (
        "stale_credential",
        "stale_credential",
        "confirm_old",
        "404/catch_target_unavailable",
        "201/created",
    ),
    "deactivated": (
        "deactivated",
        "deactivated",
        "confirm",
        "404/catch_target_unavailable",
        "201/created",
    ),
    "self_catch": (
        "self_catch",
        "self_catch",
        "confirm",
        "409/self_catch_not_allowed",
        "201/created",
    ),
    "convention_mismatch": (
        "convention_mismatch",
        "convention_mismatch",
        "confirm",
        "409/active_convention_mismatch",
        "201/created",
    ),
    "ineligible_catcher": (
        "ineligible_catcher",
        "ineligible_catcher",
        "confirm",
        "403/catcher_ineligible",
        "201/created",
    ),
    "not_owner": ("not_owner", "not_owner", "credential", "404/-", "200/-"),
    "avatar": ("avatar", "avatar", "profile", "200/-", "200/shape"),
    "fursuit_photo": (
        "fursuit_photo",
        "fursuit_photo",
        "replace",
        "200/-",
        "200/shape",
    ),
    "image_rejections": (
        "image_rejections",
        "image_rejections",
        "gif",
        "400/unsupported_format",
        "200/-",
    ),
    # a step that gets no response, a failure outside HTTP, and a code outside the allowlist
    "avatar-redirect": ("avatar_redirect", "avatar", "put_a", "200/-", "error"),
    "avatar-unexpected": ("avatar_unexpected", "avatar", "put_a", "200/-", "error"),
    "unknown-code": (
        "self_catch_unknown_code",
        "self_catch",
        "confirm",
        "409/self_catch_not_allowed",
        "409/other",
    ),
}


def run_broken(world: JourneyWorld, rule: str) -> tuple[Rig, Run]:
    world.gameplay.break_rule(rule)
    rig = make_rig(world)
    return rig, journeys(rig)


def test_the_set_of_failure_cases_covers_every_journey() -> None:
    assert {journey for _, journey, *_ in BREAKS.values()} == set(NAMES)


@pytest.mark.parametrize("case", BREAKS)
def test_a_wrong_outcome_fails_only_its_journey_at_its_step_and_leaks_nothing(
    journey_world: JourneyWorld, case: str
) -> None:
    rule, journey, step, expected, observed = BREAKS[case]

    rig, run = run_broken(journey_world, rule)

    failed = (
        f"FAIL journey={journey} step={step} expected={expected} observed={observed}"
    )
    assert run.code == 1
    assert [line for line in run.lines if " reconciliation " not in line] == [
        *BASE,
        *[failed if name == journey else f"PASS journey={name}" for name in NAMES],
        "FAIL journeys failed=1",
        "RETAIN reason=journeys quarantined=7",
        "PASS release",
    ]
    assert_only_fixed_output(run)
    assert_released(rig)


def test_the_convention_restore_is_sent_even_when_the_mismatch_check_fails(
    journey_world: JourneyWorld,
) -> None:
    _, run = run_broken(journey_world, "convention_mismatch")

    assert any(
        line.startswith("FAIL journey=convention_mismatch step=confirm ")
        for line in run.lines
    )
    sent = [
        (method, identity)
        for method, path, identity in journey_world.gameplay.requests
        if path == ACTIVE_PATH and method != "GET"
    ]
    assert sent == [("DELETE", C4), ("PUT", C4)]


# -- FM4: only public clients with the assigned identities ----------------------------


def test_each_request_carries_the_identity_the_journey_assigns_and_nothing_privileged_runs(
    happy: tuple[Rig, Run],
) -> None:
    rig, _ = happy
    world = rig.world
    requests = set(world.gameplay.requests)
    assert {
        ("PUT", path_for(F1A, "catch-session/"), O1),
        ("GET", path_for(F1A, CREDENTIAL), O1),
        ("POST", RESOLVE_PATH, C1),
        ("POST", CONFIRM_PATH, C1),
        ("GET", HISTORY_PATH, C1),
        ("PUT", path_for(F1B, "catch-session/"), O1),
        ("POST", CONFIRM_PATH, C2),
        ("POST", path_for(F2A, ROTATE), O2),
        ("PUT", path_for(F2B, ""), O2),
        ("POST", CONFIRM_PATH, C3),
        ("POST", CONFIRM_PATH, O2),
        ("DELETE", ACTIVE_PATH, C4),
        ("PUT", ACTIVE_PATH, C4),
        ("POST", CONFIRM_PATH, C4),
        ("POST", CONFIRM_PATH, OUTSIDER),
        ("GET", path_for(F2A, CREDENTIAL), O1),
        ("PUT", path_for(F2A, "catch-session/"), O1),
        ("PUT", AVATAR_PATH, C3),
        ("DELETE", AVATAR_PATH, C3),
        ("POST", CREATE_PATH, O1),
    } <= requests

    def who(method: str, *paths: str) -> set[int | None]:
        return {i for m, p, i in requests if m == method and p in paths}

    # Only the two unauthenticated probes carry no identity.
    assert {(m, p) for m, p, i in requests if i is None} == {("GET", "/api/me/")}
    # Owners control sessions and credentials; catchers resolve and read history.
    assert who("GET", path_for(F1A, CREDENTIAL)) == {O1}
    assert who("POST", RESOLVE_PATH) <= {C1, C2, C3, C4}
    assert who("GET", HISTORY_PATH) == {O1, O2, C1, C2, C3, C4, OUTSIDER}
    assert who("POST", CONFIRM_PATH) == {O2, C1, C2, C3, C4, OUTSIDER}
    # No lease, fixture or Clerk admin call falls between provisioning and release,
    # except the one cleanup that follows reconciliation.
    log = world.log
    after = log[log.index(("fixture", "provision")) + 1 :]
    assert [
        d.split()[0] for k, d in after if k in ("channel", "fixture", "backend")
    ] == ["cleanup", "release"]

    # RECONCILIATION (#222) starts once the journeys have reported. Its only public
    # calls are one history read per role (catcher0's two journey reads precede its
    # own), and it calls `inspect` exactly once, between the journeys and the release.
    finished = log.index(("emit", "PASS journeys passed=13"))
    inspections = [at for at, entry in enumerate(log) if entry[0] == "inspection"]
    released = next(
        at
        for at, (k, d) in enumerate(log)
        if k == "channel" and d.startswith("release")
    )
    reconciling = log[finished + 1 :]
    assert len(inspections) == 1
    assert finished < inspections[0] < released
    assert sorted(d for k, d in reconciling if k == "api") == sorted(
        f"GET {HISTORY_PATH} {index}" for index in (O1, O2, C1, C2, C3, C4, OUTSIDER)
    )
    assert [
        (request.url.path, dict(request.url.params))
        for request in world.api_requests[-7:]
    ] == [(HISTORY_PATH, {"convention_id": str(CONVENTION_ID), "page_size": "100"})] * 7
    assert rig.inspection.calls == [
        (
            POOL,
            RUN_ID,
            {
                Role.OWNER0: O1,
                Role.OWNER1: O2,
                Role.CATCHER0: C1,
                Role.CATCHER1: C2,
                Role.CATCHER2: C3,
                Role.CATCHER3: C4,
                Role.OUTSIDER: OUTSIDER,
            },
        )
    ]


# -- FM5: image writes touch only run-owned records ---------------------------------


def test_image_writes_touch_only_the_created_fursuit_and_leased_avatars(
    happy: tuple[Rig, Run],
) -> None:
    rig, run = happy
    gameplay = rig.world.gameplay

    assert run.code == 0
    (created,) = gameplay.created
    assert created not in gameplay.fixture_fursuit_ids()
    # replace (journey 12) and the three rejections (journey 13)
    assert gameplay.photo_puts == [(O1, created)] * 4
    assert gameplay.avatar_puts == [C3, C3]
    # Valid uploads are images A then B for the avatar, then A (create) and B (replace).
    assert gameplay.stored == [VALID_A, VALID_B, VALID_A, VALID_B]


# -- FM8: setup failures never reach a journey -----------------------------------------


def test_a_failed_provision_prints_no_journey_lines_and_still_releases(
    journey_world: JourneyWorld,
) -> None:
    rig = make_rig(journey_world, fail=FixtureFailed("FAIL_LEASE"))

    run = journeys(rig)

    assert run.code == 1
    assert run.lines == [*BASE[:2], "FAIL setup result=FAIL_LEASE", "PASS release"]
    assert_only_fixed_output(run)
    assert_released(rig)
    assert rig.inspection.calls == []
    assert {p for _, p, _ in journey_world.gameplay.requests} <= {
        "/api/me/",
        "/api/profile/",
    }


# -- FM10: CLI wiring --------------------------------------------------------------------


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


def test_cli_passes_the_pool_and_the_committed_fixture_images_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = REPOSITORY_ROOT / "services/api/simulation_fixtures/images"
    files = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    seen = _capture_run(monkeypatch)

    assert main(["journeys", "--pool", POOL]) == 0

    (arguments,) = seen
    assert arguments["pool"] == POOL
    assert isinstance(arguments["inspection_channel"], InspectionLauncherChannel)
    assert INSPECTION_LAUNCHER_COMMAND[-1] == "api-sim-inspect-ssh"
    assert arguments["images"] == JourneyImages(
        valid_a=files[0].read_bytes(), valid_b=files[1 % len(files)].read_bytes()
    )


@pytest.mark.parametrize(
    "arguments",
    [["--pool", "Bad_Pool"], [], ["--pool", POOL, "--owners", "2"]],
)
def test_cli_rejects_bad_input_before_anything_is_reached(
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
        code = main(["journeys", *arguments])
    except SystemExit as exit_:
        code = exit_.code

    assert code not in (0, None)
    assert reached == []
