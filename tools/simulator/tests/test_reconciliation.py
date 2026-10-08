"""Behavioral tests for the post-run reconciliation (#222 R-1, R-2, R-5 to R-8, R-10 to R-12).

The substitutes are the same as test_journeys plus the inspection channel (see
reconciliation_support). Reconciliation, the journeys and their reporting run for
real. Each fault is injected into the fake API or the inspection data, and the test
reads only the printed lines and the exit code.

Conventions these tests pin (the spec fixes the line shape and the check order, and
leaves these open; each is one row of CASES to change):

- `expected` is what the authoritative side (the database) requires; `observed` is
  what was found or what the API reported. Value checks print 1 for "agrees" and 0
  for "disagrees".
- A pair-based discrepancy names the first journey, in journey order, that attempted
  the pair (`catch` for catcher0 x o0f0, which `retry` also attempts) and the
  confirming role. A discrepancy no journey attempted has journey `-`.
- A catch that is not a run pair at all (no run catcher, no run fursuit owner, other
  Convention) is `contamination` only, never also `unexpected`.
- Where a journey or role is not meaningful the line prints `-`.
"""

import asyncio
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import httpx
import journey_support
import pool_support
import pytest
from journey_support import Catch, Gameplay, JourneyWorld, failure
from pool_support import POOL, RUN_ID
from reconciliation_support import (
    FOREIGN_CATCH,
    SHIFTED_CAUGHT_AT,
    Data,
    add_catch,
    chain,
    change_reconciliation_history,
    edit,
    edit_catch,
)
from report_support import read_report, recorder
from test_journeys import (
    BASE,
    C1,
    C2,
    C3,
    C4,
    F1B,
    F2A,
    NAMES,
    O1,
    O2,
    OUTSIDER,
    assert_only_fixed_output,
    assert_released,
    journeys,
    make_rig,
)

from tailtag_simulator.client import open_client
from tailtag_simulator.gameplay import IntegrityFailed
from tailtag_simulator.reconciliation import (
    Check,
    Expectations,
    InspectionFailed,
    InspectionLauncherChannel,
    Role,
    reconcile_run,
)
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime

world = pool_support.world  # the shared fixtures
journey_world = journey_support.journey_world

Setup = Callable[[pytest.MonkeyPatch, JourneyWorld], None]

PASSED: Final = [
    *BASE,
    *[f"PASS journey={name}" for name in NAMES],
    "PASS journeys passed=13",
]


def test_checks_and_roles_follow_the_specified_order() -> None:
    assert [check.value for check in Check] == [
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
    ]
    assert [role.value for role in Role] == [
        "owner0",
        "owner1",
        "catcher0",
        "catcher1",
        "catcher2",
        "catcher3",
        "outsider",
    ]


# -- faults injected into the fake API (the database and the API stay consistent) ----


def _break(rule: str) -> Setup:
    return lambda _monkeypatch, world: world.gameplay.break_rule(rule)


def _preseed(*pairs: tuple[int, int]) -> Setup:
    """Catches by pool index and fursuit that no journey will make."""

    def setup(_monkeypatch: pytest.MonkeyPatch, world: JourneyWorld) -> None:
        for number, (catcher, fursuit) in enumerate(pairs, start=1):
            world.gameplay.catches.append(Catch(8000 + number, catcher, fursuit))

    return setup


def _write_a_duplicate_row(
    monkeypatch: pytest.MonkeyPatch, world: JourneyWorld
) -> None:
    """The API answers `already_caught` correctly but also writes a second row."""
    gameplay = world.gameplay
    original = gameplay.confirm
    written: list[Catch] = []

    def confirm(index: int) -> httpx.Response:
        response = original(index)
        if index == C1 and response.status_code == 200 and not written:
            first = next(c for c in gameplay.catches if c.catcher == C1)
            written.append(
                Catch(7000 + len(gameplay.catches) + 1, C1, first.fursuit_id)
            )
            gameplay.catches.append(written[0])
        return response

    monkeypatch.setattr(gameplay, "confirm", confirm)


def _report_another_catch_id(
    monkeypatch: pytest.MonkeyPatch, world: JourneyWorld
) -> None:
    """The 201 names an id that is not the one the row was stored under."""
    gameplay = world.gameplay
    original = gameplay.confirm

    def confirm(index: int) -> httpx.Response:
        response = original(index)
        if response.status_code != 201:
            return response
        body = json.loads(response.content)
        body["catch"]["id"] += 500
        return httpx.Response(201, json=body)

    monkeypatch.setattr(gameplay, "confirm", confirm)


def _lose_the_rows_before_reconciling(
    monkeypatch: pytest.MonkeyPatch, world: JourneyWorld
) -> None:
    """Every journey passes, then the stored catches are gone when reconciliation reads."""
    change_reconciliation_history(
        monkeypatch, world.gameplay, before=lambda g: g.catches.clear()
    )


def _history(monkeypatch: pytest.MonkeyPatch, world: JourneyWorld) -> None:
    """catcher0's history results are empty while its stored catch is not."""
    change_reconciliation_history(
        monkeypatch,
        world.gameplay,
        edit_body=lambda index, body: {**body, "results": []} if index == C1 else body,
    )


def _history_outsider(monkeypatch: pytest.MonkeyPatch, world: JourneyWorld) -> None:
    """The outsider's history shows a catch (count still 0) that the database lacks."""
    phantom = {"id": 7777, "fursuit": {"id": F1B}, "caught_at": SHIFTED_CAUGHT_AT}
    change_reconciliation_history(
        monkeypatch,
        world.gameplay,
        edit_body=lambda index, body: (
            {**body, "results": [phantom]} if index == OUTSIDER else body
        ),
    )


def _count(monkeypatch: pytest.MonkeyPatch, world: JourneyWorld) -> None:
    """catcher0's history results are right but its `catch_count` is not."""
    change_reconciliation_history(
        monkeypatch,
        world.gameplay,
        edit_body=lambda index, body: (
            {**body, "catch_count": 3} if index == C1 else body
        ),
    )


# -- FM8: every check fails on its own condition and on nothing else ---------------

# A catch the broken rule lets through: journey -> the role that confirmed it.
FORBIDDEN_PAIRS: Final = {
    "stopped_session": "catcher1",
    "stale_credential": "catcher1",
    "deactivated": "catcher2",
    "self_catch": "owner1",
    "convention_mismatch": "catcher3",
    "ineligible_catcher": "outsider",
}
CATCHER0: Final = "journey=catch role=catcher0"

# case -> (fault in the fake API, fault in the inspection data, the one check line)
CASES: Final[dict[str, tuple[Setup | None, Callable[[Data], Data] | None, str]]] = {
    "contamination": (
        None,
        add_catch(FOREIGN_CATCH),
        "check=contamination journey=- role=- expected=0 observed=1",
    ),
    "duplicate": (
        _write_a_duplicate_row,
        None,
        f"check=duplicate {CATCHER0} expected=1 observed=2",
    ),
    "missing": (
        _lose_the_rows_before_reconciling,
        None,
        f"check=missing {CATCHER0} expected=1 observed=0",
    ),
    "unexpected-unattempted": (
        _preseed((C4, F1B)),
        None,
        "check=unexpected journey=- role=catcher3 expected=0 observed=1",
    ),
    **{
        f"unexpected-{journey}": (
            _break(journey),
            None,
            f"check=unexpected journey={journey} role={role} expected=0 observed=1",
        )
        for journey, role in FORBIDDEN_PAIRS.items()
    },
    "catch_id": (
        _report_another_catch_id,
        None,
        f"check=catch_id {CATCHER0} expected=1 observed=0",
    ),
    "caught_at": (
        None,
        edit_catch(C1, caught_at=SHIFTED_CAUGHT_AT),
        f"check=caught_at {CATCHER0} expected=1 observed=0",
    ),
    "provenance": (
        None,
        edit_catch(C1, provenance=False),
        f"check=provenance {CATCHER0} expected=1 observed=0",
    ),
    "window": (
        None,
        edit_catch(C1, in_window=False),
        f"check=window {CATCHER0} expected=1 observed=0",
    ),
    "history": (
        _history,
        None,
        "check=history journey=- role=catcher0 expected=1 observed=0",
    ),
    "history-outsider": (
        _history_outsider,
        None,
        "check=history journey=- role=outsider expected=0 observed=1",
    ),
    "count": (
        _count,
        None,
        "check=count journey=- role=catcher0 expected=1 observed=3",
    ),
    "fixture_photo": (
        None,
        edit(fixture_photos_unchanged=False),
        "check=fixture_photo journey=- role=- expected=1 observed=0",
    ),
    "created_fursuit": (
        None,
        edit(fursuits=[]),
        "check=created_fursuit journey=fursuit_photo role=owner0 expected=1 observed=0",
    ),
    "avatar": (
        _break("avatar"),
        None,
        "check=avatar journey=avatar role=catcher2 expected=0 observed=1",
    ),
}


def test_every_check_but_inspect_has_a_case() -> None:
    covered = {line.split()[0].removeprefix("check=") for *_, line in CASES.values()}
    assert covered == {check.value for check in Check} - {"inspect"}


@pytest.mark.parametrize("case", CASES)
def test_each_check_reports_exactly_its_discrepancy_and_fails_the_run(
    monkeypatch: pytest.MonkeyPatch,
    journey_world: JourneyWorld,
    case: str,
    tmp_path: Path,
) -> None:
    setup, corrupt, line = CASES[case]
    if setup is not None:
        setup(monkeypatch, journey_world)
    rig = make_rig(journey_world, corrupt=corrupt)

    report = recorder(tmp_path, "journeys", config={"pool": POOL})
    run = journeys(rig, report=report)
    value = read_report(report.path)
    assert value["outcome"] == "aborted"
    assert value["safety"]["abort"]["reason"] == "correctness"

    assert run.code == 1
    assert [x for x in run.lines if " reconciliation " in x] == [
        f"FAIL reconciliation {line}",
        "FAIL reconciliation discrepancies=1",
    ]
    assert [line for line in run.lines if not line.startswith("FAIL safety reason=")][
        -1
    ] == "PASS release"
    assert_only_fixed_output(run)
    assert_released(rig)


# -- FM10: partial failures --------------------------------------------------------


@pytest.mark.parametrize("rows_lost", [False, True])
def test_a_catch_whose_response_was_wrong_is_at_most_one_row_not_missing(
    monkeypatch: pytest.MonkeyPatch, journey_world: JourneyWorld, rows_lost: bool
) -> None:
    """`catch` answers 200 for the row it wrote: no `created`, so the pair is at most one."""
    journey_world.gameplay.break_rule("catch")
    if rows_lost:
        _lose_the_rows_before_reconciling(monkeypatch, journey_world)
    rig = make_rig(journey_world)

    run = journeys(rig)

    assert run.code == 1
    assert [
        line for line in run.lines if not line.startswith("FAIL safety reason=")
    ] == [
        *BASE,
        "PASS journey=unauthenticated",
        "FAIL journey=catch step=confirm expected=201/created observed=200/already_caught",
        "FAIL journeys failed=1",
        "PASS reconciliation checks=14",
        "RETAIN reason=journeys quarantined=7",
        "PASS release",
    ]
    assert "FAIL safety reason=correctness" in run.lines
    assert_only_fixed_output(run)
    assert_released(rig)


def test_a_failed_fursuit_create_does_not_expect_a_created_fursuit(
    monkeypatch: pytest.MonkeyPatch, journey_world: JourneyWorld
) -> None:
    gameplay = journey_world.gameplay

    def create_fursuit(_index: int) -> httpx.Response:
        return failure(500, "SENTINEL_BOOM")

    monkeypatch.setattr(gameplay, "create_fursuit", create_fursuit)
    rig = make_rig(journey_world)

    run = journeys(rig)

    assert run.code == 1
    assert [x for x in run.lines if " reconciliation " in x] == [
        "PASS reconciliation checks=14"
    ]
    assert_only_fixed_output(run)


def test_discrepancies_are_ordered_by_check_then_journey_then_role(
    monkeypatch: pytest.MonkeyPatch, journey_world: JourneyWorld
) -> None:
    gameplay = journey_world.gameplay

    # Inject stored/API-consistent anomalies at the external reconciliation boundary.
    # Gameplay completes normally; both named forbidden pairs remain observable
    # without continuing workload after an integrity abort.
    def persist(g: Gameplay) -> None:
        g.catches.extend(
            [
                Catch(8001, C3, F1B),
                Catch(8002, O1, F2A),
                Catch(8003, O2, F2A),
                Catch(8004, C2, F2A),
            ]
        )

    change_reconciliation_history(monkeypatch, gameplay, before=persist)
    rig = make_rig(
        journey_world,
        corrupt=chain(
            edit(fixture_photos_unchanged=False),
            edit_catch(C1, in_window=False),
            add_catch(FOREIGN_CATCH),
        ),
    )

    run = journeys(rig)

    found = [
        m.groups()
        for line in run.lines
        if (
            m := re.fullmatch(
                r"FAIL reconciliation check=(\w+) journey=([\w-]+) role=(\w+|-)"
                r" expected=\d observed=\d",
                line,
            )
        )
    ]
    assert [check for check, _, _ in found] == [
        "contamination",
        *["unexpected"] * 4,
        "window",
        "fixture_photo",
    ]
    # Named journeys come in journey order, which is not role order (owner1 < catcher1).
    assert [(j, r) for c, j, r in found if c == "unexpected" and j != "-"] == [
        ("stale_credential", "catcher1"),
        ("self_catch", "owner1"),
    ]
    # Catches no journey made are in lease role order: not the order they were stored
    # and not alphabetical (owner0 comes before catcher2).
    assert [r for c, j, r in found if c == "unexpected" and j == "-"] == [
        "owner0",
        "catcher2",
    ]
    assert "FAIL reconciliation discrepancies=7" in run.lines
    assert_only_fixed_output(run)


# -- FM12: the inspection itself fails ---------------------------------------------


@pytest.mark.parametrize(
    ("raised", "printed"),
    [
        ("FAIL_LEASE", "FAIL_LEASE"),
        ("FAIL_BOOTSTRAP", "FAIL_BOOTSTRAP"),
        ("FAIL_SENTINEL_UNKNOWN", "FAIL_LAUNCHER"),
    ],
)
def test_a_failed_inspection_fails_the_run_with_a_known_code_and_still_releases(
    journey_world: JourneyWorld,
    raised: str,
    printed: str,
    tmp_path: Path,
) -> None:
    rig = make_rig(journey_world, inspection_fail=InspectionFailed(raised))

    report = recorder(tmp_path, "journeys", config={"pool": POOL})
    run = journeys(rig, report=report)
    value = read_report(report.path)
    assert value["outcome"] == "failed"
    assert value["safety"]["abort"] is None

    assert run.code == 1
    assert run.lines == [
        *PASSED,
        f"FAIL reconciliation result={printed}",
        "RETAIN reason=reconciliation quarantined=7",
        "PASS release",
    ]
    assert_only_fixed_output(run)
    assert_released(rig)


# -- the launcher channel (see test_fixture_channel for the shared launcher rules) --


@pytest.mark.parametrize("status", [503, 201])
def test_reconciliation_history_distinguishes_provider_failure_from_success_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    journey_world: JourneyWorld,
    status: int,
) -> None:
    gameplay = journey_world.gameplay
    original = gameplay.history

    def history(index: int) -> httpx.Response:
        assert gameplay.request is not None
        if "page_size" in gameplay.request.url.params:
            response = original(index)
            return httpx.Response(status, content=response.content)
        return original(index)

    monkeypatch.setattr(gameplay, "history", history)
    rig = make_rig(journey_world)
    report = recorder(tmp_path, "journeys", config={"pool": POOL})
    run = journeys(rig, report=report)
    value = read_report(report.path)
    assert run.code != 0
    assert value["outcome"] == ("failed" if status == 503 else "aborted")
    if status == 503:
        assert value["safety"]["abort"] is None
    else:
        assert value["safety"]["abort"]["reason"] == "correctness"
        assert "FAIL reconciliation" in run.lines
        assert any(
            line.startswith("FAIL reconciliation check=history ") for line in run.lines
        )
    assert any(line.startswith("FAIL reconciliation") for line in run.lines)
    assert_only_fixed_output(run)
    assert_released(rig)


@pytest.mark.parametrize("status", [200, 201, 503])
def test_reconciliation_fallback_classifies_actual_success_independently(
    journey_world: JourneyWorld, status: int
) -> None:
    runtime = SafetyRuntime({})
    requests: list[str] = []
    rig = make_rig(journey_world)

    async def probe() -> dict[str, object]:
        return {
            "source_sha": pool_support.SHA,
            "deployment_id": pool_support.DEPLOYMENT_ID,
            "environment": "staging",
        }

    runtime.bind_probe(probe)

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(
            status,
            json={"enrollment": {"convention": {"id": 1}}} if status == 201 else {},
        )

    async def execute() -> None:
        with runtime.scope():
            await runtime.check_target()
            with runtime.phase("reconciliation"):
                async with open_client(
                    "https://staging.tailtag.app",
                    transport=httpx.MockTransport(respond),
                ) as client:
                    with pytest.raises(
                        (ValueError, KeyError, IntegrityFailed, SafetyAborted)
                    ):
                        await runtime.run_phase(
                            reconcile_run(
                                Expectations(),
                                {role: client for role in Role},
                                {role: index for index, role in enumerate(Role)},
                                rig.inspection,
                                pool=POOL,
                                run_id=RUN_ID,
                                convention=0,
                                created_fursuit=None,
                            )
                        )

    asyncio.run(execute())
    assert requests == ["/api/conventions/active/"]
    assert not rig.inspection.calls
    assert runtime.abort_reason == (None if status == 503 else "correctness")


IDENTITIES = {
    Role.OWNER0: 1,
    Role.OWNER1: 2,
    Role.CATCHER0: 3,
    Role.CATCHER1: 4,
    Role.CATCHER2: 5,
    Role.CATCHER3: 6,
    Role.OUTSIDER: 7,
}
DATA: Final[Data] = {
    "catches": [],
    "fursuits": [],
    "fixture_photos_unchanged": True,
    "avatars": [],
}


def launcher(
    tmp_path: Path, stdout: str, *, code: int = 0
) -> tuple[InspectionLauncherChannel, Path]:
    record = tmp_path / "record.json"
    script = (
        "import json, sys\n"
        "stdin = sys.stdin.read()\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': stdin}}))\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({code})\n"
    )
    return InspectionLauncherChannel([sys.executable, "-c", script]), record


def test_the_request_goes_on_stdin_as_an_inspect_operation_and_pass_returns_the_data(
    tmp_path: Path,
) -> None:
    channel, record = launcher(
        tmp_path, json.dumps({"data": DATA, "result": "PASS"}) + "\n"
    )

    data = asyncio.run(channel.inspect(POOL, RUN_ID, IDENTITIES))

    assert data == DATA
    seen = json.loads(record.read_text())
    assert seen["argv"] == []
    assert json.loads(seen["stdin"]) == {
        "operation": "inspect",
        "arguments": {
            "pool": POOL,
            "run_id": RUN_ID,
            "identities": {role.value: index for role, index in IDENTITIES.items()},
        },
    }


# stdout, exit code -> the result the failure carries
FAILURES: Final = {
    "failure-result": ('{"data": {}, "result": "FAIL_LEASE"}\n', 1, "FAIL_LEASE"),
    "unknown-code": (
        '{"data": {}, "result": "FAIL_SENTINEL_UNKNOWN"}\n',
        1,
        "FAIL_LAUNCHER",
    ),
    "not-json": ("SENTINEL-OUTPUT not json\n", 0, "FAIL_LAUNCHER"),
}


@pytest.mark.parametrize("case", FAILURES)
def test_a_failed_or_malformed_inspection_becomes_a_detail_free_failure(
    tmp_path: Path, case: str
) -> None:
    stdout, code, result = FAILURES[case]
    channel, _ = launcher(tmp_path, stdout, code=code)

    with pytest.raises(InspectionFailed) as exc:
        asyncio.run(channel.inspect(POOL, RUN_ID, IDENTITIES))

    assert exc.value.result == result
    assert "SENTINEL" not in f"{exc.value}{exc.value!r}"
