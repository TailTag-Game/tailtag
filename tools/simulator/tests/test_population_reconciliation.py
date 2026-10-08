"""AC12/15: closed-world population comparison with variable actor labels.

Real comparator, history parser and API client; only HTTP and privileged inspection
are substitutes. Literal expected state is independent of the inspection fixture.
"""

import asyncio
import copy
import json
import re
import sys
from collections.abc import Mapping
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest

from tailtag_simulator.client import open_client
from tailtag_simulator.population_reconciliation import (
    PopulationExpectations,
    PopulationInspectionLauncherChannel,
    PopulationReconciliationResult,
    population_reconciliation_lines,
    reconcile_population,
)
from tailtag_simulator.reconciliation import InspectionFailed, Made

AT = "2026-10-06T12:00:00Z"
INDEXES = {"owner0": 17, "owner1": 19, **{f"attendee{n}": 30 + n for n in range(5)}}
ROW: dict[str, object] = {
    "id": 7001,
    "catcher": 34,
    "fursuit": 8001,
    "fursuit_owner": 17,
    "run_convention": True,
    "provenance": True,
    "in_window": True,
    "caught_at": AT,
}
DATA: dict[str, Any] = {
    "catches": [ROW],
    "fursuits": [],
    "fixture_photos_unchanged": True,
    "avatars": [],
}
POOL = "alpha"
RUN_ID = "aaaaaaaa-1111-4111-8111-111111111111"


class Inspection:
    """The approved privileged launcher boundary, with its exact request contract."""

    def __init__(self, data: Mapping[str, object]) -> None:
        self.data = data

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        assert (pool, run_id, dict(identities)) == (POOL, RUN_ID, INDEXES)
        return self.data


def reconcile(
    data: dict[str, Any],
    *,
    expectations: PopulationExpectations | None = None,
    history_fault: bool = False,
    public_history_entry: dict[str, object] | None = None,
    target_owners: dict[int, str] | None = None,
) -> tuple[PopulationReconciliationResult, set[str]]:
    if expectations is None:
        expectations = PopulationExpectations()
        expectations.attempts.add(("attendee4", 8001))
        expectations.made[("attendee4", 8001)] = Made(7001, AT)
        expectations.seen[("attendee4", 8001)] = [Made(7001, AT)]
    # Public owner-fixture facts are independently authored, never reconstructed
    # from the privileged inspection's claimed owner. Dynamic assignment provides
    # meaningful red against the older dataclass that has not gained this field.
    expectations.target_owners = (
        {8001: "owner0"} if target_owners is None else target_owners
    )
    read_actors: set[str] = set()

    def serve(request: httpx.Request) -> httpx.Response:
        actor = request.headers["Authorization"].removeprefix("Bearer ")
        assert actor in INDEXES
        assert request.url.path == "/api/catches/"
        assert request.url.params["convention_id"] == "42"
        assert request.url.params["page_size"] == "20"
        read_actors.add(actor)
        rows = [
            row
            for row in data["catches"]
            if row["catcher"] == INDEXES[actor] and row["run_convention"]
        ]
        results = [
            {
                "id": row["id"],
                "fursuit": {
                    "id": row["fursuit"],
                    "name": "SENTINEL-name",
                    "photo_url": "https://media.example.test/SENTINEL",
                },
                "convention": {"id": 42, "name": "Private"},
                "caught_at": row["caught_at"],
            }
            for row in rows
        ]
        if history_fault and actor == "attendee4":
            results = []
        if public_history_entry is not None and actor == "attendee4":
            results = [public_history_entry]
        return httpx.Response(
            200,
            json={
                "catch_count": len(rows),
                "results": results,
                "next": None,
                "previous": None,
            },
        )

    async def run() -> PopulationReconciliationResult:
        async with AsyncExitStack() as stack:
            clients = {
                actor: await stack.enter_async_context(
                    open_client(
                        "https://api.example.test",
                        token=actor,
                        transport=httpx.MockTransport(serve),
                    )
                )
                for actor in INDEXES
            }
            assert expectations is not None
            return await reconcile_population(
                expectations,
                clients,
                INDEXES,
                Inspection(data),
                pool=POOL,
                run_id=RUN_ID,
                convention=42,
            )

    return asyncio.run(run()), read_actors


def test_population_compares_the_fifth_attendee_and_every_actors_public_history() -> (
    None
):
    result, actors = reconcile(copy.deepcopy(DATA))

    assert result.passed
    assert result.discrepancies == ()
    assert result.count == 14
    assert actors == set(INDEXES)


@pytest.mark.parametrize(
    "ambiguous_positive", [False, True], ids=("made", "ambiguous-positive")
)
def test_known_target_cannot_move_to_another_configured_owner(
    ambiguous_positive: bool,
) -> None:
    """AC12 HIGH review finding: allocated-owner membership is insufficient."""
    expected = PopulationExpectations()
    expected.attempts.add(("attendee4", 8001))
    if not ambiguous_positive:
        expected.made[("attendee4", 8001)] = Made(7001, AT)
    control, _ = reconcile(copy.deepcopy(DATA), expectations=expected)
    assert control.passed
    wrong_owner = copy.deepcopy(DATA)
    wrong_owner["catches"][0]["fursuit_owner"] = INDEXES["owner1"]

    result, _ = reconcile(wrong_owner, expectations=expected)

    assert not result.passed
    assert "contamination" in {item.check for item in result.discrepancies}
    output = "\n".join(population_reconciliation_lines(result))
    assert "8001" not in output and "7001" not in output and AT not in output


@pytest.mark.parametrize(
    "owner_facts",
    [{}, {8001: "attendee0"}],
    ids=("missing-target", "invalid-owner-role"),
)
def test_persisted_target_requires_valid_public_owner_facts(
    owner_facts: dict[int, str],
) -> None:
    result, _ = reconcile(copy.deepcopy(DATA), target_owners=owner_facts)

    assert not result.passed


@pytest.mark.parametrize(
    ("catch_id", "fursuit", "caught_at"),
    [(7002, 8001, AT), (7001, 8002, AT), (7001, 8001, "2026-10-06T12:00:01Z")],
    ids=("wrong-catch-id", "wrong-target", "wrong-timestamp"),
)
def test_valid_same_count_public_history_must_match_authoritative_values(
    catch_id: int, fursuit: int, caught_at: str
) -> None:
    """Reviewer finding: count-only comparison must not hide valid wrong history.

    The API response is independently authored, with count=1 and one unique valid
    row. Inspection and confirmation expectations retain the original literal pair.
    """
    public_entry: dict[str, object] = {
        "id": catch_id,
        "fursuit": {
            "id": fursuit,
            "name": "Public fixture",
            "photo_url": "https://media.example.test/private",
        },
        "convention": {"id": 42, "name": "Convention"},
        "caught_at": caught_at,
    }

    result, _ = reconcile(copy.deepcopy(DATA), public_history_entry=public_entry)

    assert not result.passed
    assert [
        (item.check, item.actor, item.expected, item.observed)
        for item in result.discrepancies
    ] == [("history", "attendee4", 1, 1)]


@pytest.mark.parametrize(
    ("fault", "check"),
    [
        ("missing", "missing"),
        ("duplicate", "duplicate"),
        ("unattempted", "unexpected"),
        ("catch_id", "catch_id"),
        ("caught_at", "caught_at"),
        ("retry_id", "catch_id"),
        ("retry_time", "caught_at"),
        ("contamination", "contamination"),
        ("provenance", "provenance"),
        ("window", "window"),
        ("history", "history"),
        ("fixture_photo", "fixture_photo"),
        ("created_fursuit", "created_fursuit"),
        ("avatar", "avatar"),
    ],
)
def test_population_discrepancies_fail_and_emit_only_fixed_labels(
    fault: str, check: str
) -> None:
    data = copy.deepcopy(DATA)
    expected = PopulationExpectations()
    expected.attempts.add(("attendee4", 8001))
    expected.made[("attendee4", 8001)] = Made(7001, AT)
    expected.seen[("attendee4", 8001)] = [Made(7001, AT)]
    if fault == "missing":
        data["catches"] = []
    elif fault == "duplicate":
        data["catches"].append({**ROW, "id": 7002})
    elif fault == "unattempted":
        data["catches"].append({**ROW, "id": 7002, "catcher": 30})
    elif fault == "catch_id":
        data["catches"][0]["id"] = 7002
    elif fault == "caught_at":
        data["catches"][0]["caught_at"] = "2026-10-06T12:00:01Z"
    elif fault == "retry_id":
        expected.seen[("attendee4", 8001)] = [Made(7002, AT)]
    elif fault == "retry_time":
        expected.seen[("attendee4", 8001)] = [Made(7001, "2026-10-06T12:00:01Z")]
    elif fault == "contamination":
        data["catches"].append({**ROW, "id": 7002, "catcher": None})
    elif fault in {"provenance", "window"}:
        data["catches"][0]["in_window" if fault == "window" else fault] = False
    elif fault == "fixture_photo":
        data["fixture_photos_unchanged"] = False
    elif fault == "created_fursuit":
        data["fursuits"] = [{"id": 9999, "owner": 17}]
    elif fault == "avatar":
        data["avatars"] = [34]

    result, _ = reconcile(data, expectations=expected, history_fault=fault == "history")

    assert not result.passed
    assert check in {item.check for item in result.discrepancies}
    output = "\n".join(population_reconciliation_lines(result))
    assert not any(
        secret in output
        for secret in ("7001", "7002", "8001", AT, POOL, RUN_ID, "SENTINEL", "https://")
    )
    assert re.fullmatch(r"[A-Za-z0-9_= \-\n]+", output)


@pytest.mark.parametrize("wrong_role", ["catcher-is-owner", "target-owner-is-attendee"])
def test_allocated_identity_does_not_grant_the_other_population_role(
    wrong_role: str,
) -> None:
    data = copy.deepcopy(DATA)
    expected = PopulationExpectations()
    if wrong_role == "catcher-is-owner":
        data["catches"][0]["catcher"] = 17
        expected.attempts.add(("owner0", 8001))
        expected.made[("owner0", 8001)] = Made(7001, AT)
    else:
        data["catches"][0]["fursuit_owner"] = 30
        expected.attempts.add(("attendee4", 8001))
        expected.made[("attendee4", 8001)] = Made(7001, AT)

    result, _ = reconcile(data, expectations=expected)

    assert not result.passed


def test_discrepancy_order_uses_check_then_logical_actor_not_row_order() -> None:
    data = copy.deepcopy(DATA)
    data["catches"].extend(
        [
            {**ROW, "id": 7002, "catcher": 31},
            {**ROW, "id": 7003, "catcher": 30},
        ]
    )
    data["fixture_photos_unchanged"] = False

    result, _ = reconcile(data)

    assert [(item.check, item.actor) for item in result.discrepancies] == [
        ("unexpected", "attendee0"),
        ("unexpected", "attendee1"),
        ("fixture_photo", None),
    ]


@pytest.mark.parametrize("persisted", [0, 1, 2])
def test_ambiguous_positive_attempt_allows_at_most_one_persisted_pair(
    persisted: int,
) -> None:
    expected = PopulationExpectations()
    expected.attempts.add(("attendee4", 8001))
    data = copy.deepcopy(DATA)
    data["catches"] = [{**ROW, "id": 7001 + number} for number in range(persisted)]

    result, _ = reconcile(data, expectations=expected)

    assert result.passed is (persisted <= 1)
    assert "missing" not in {item.check for item in result.discrepancies}


def test_population_launcher_uses_the_versioned_operation_on_stdin(
    tmp_path: Path,
) -> None:
    record = tmp_path / "request.json"
    script = f"import sys; open({str(record)!r}, 'w').write(sys.stdin.read()); print({json.dumps({'result': 'PASS', 'data': DATA})!r})"
    channel = PopulationInspectionLauncherChannel([sys.executable, "-c", script])

    result = asyncio.run(channel.inspect(POOL, RUN_ID, INDEXES))

    assert result == DATA
    assert json.loads(record.read_text()) == {
        "operation": "inspect-population-v1",
        "arguments": {"pool": POOL, "run_id": RUN_ID, "identities": INDEXES},
    }


def test_population_launcher_sanitizes_unknown_provider_failure(tmp_path: Path) -> None:
    channel = PopulationInspectionLauncherChannel(
        [sys.executable, "-c", 'print(\'{"result": "SENTINEL-private", "data": {}}\')']
    )

    with pytest.raises(InspectionFailed) as caught:
        asyncio.run(channel.inspect(POOL, RUN_ID, INDEXES))

    assert caught.value.result == "FAIL_LAUNCHER"
    assert "SENTINEL" not in repr(caught.value)


@pytest.mark.parametrize(
    ("expectation", "persisted", "known", "passed", "check"),
    [
        ("required", 1, True, True, None),
        ("required", 1, False, False, "inspect"),
        ("forbidden", 0, False, True, None),
        ("forbidden", 1, False, False, "unexpected"),
        ("unresolved", 0, False, False, "inspect"),
        ("unresolved", 1, False, False, "inspect"),
    ],
    ids=[
        "required-canonical",
        "required-needs-observation",
        "forbidden-empty",
        "forbidden-attempt-is-not-permission",
        "unresolved-empty-never-passes",
        "unresolved-commit-never-passes",
    ],
)
def test_explicit_pair_expectations_never_authorize_negative_or_unobserved_writes(
    expectation: Literal["required", "forbidden", "unresolved"],
    persisted: int,
    known: bool,
    passed: bool,
    check: str | None,
) -> None:
    """#226 AC20–22: generic attempts cannot grant negative writes or hide doubt."""
    expected = PopulationExpectations()
    pair = ("attendee4", 8001)
    expected.attempts.add(pair)
    # Deliberately assign to the approved additive seam: the legacy comparator
    # executes and fails behaviorally when it ignores the new expectation.
    expected.pairs = {pair: expectation}
    if known:
        expected.made[pair] = Made(7001, AT)
    data = copy.deepcopy(DATA)
    data["catches"] = [{**ROW, "id": 7001 + n} for n in range(persisted)]

    result, actors = reconcile(data, expectations=expected)

    assert result.passed is passed
    assert actors == set(INDEXES)
    if check is not None:
        assert check in {item.check for item in result.discrepancies}
    output = "\n".join(population_reconciliation_lines(result))
    assert not any(secret in output for secret in ("7001", "8001", AT, "SENTINEL"))
