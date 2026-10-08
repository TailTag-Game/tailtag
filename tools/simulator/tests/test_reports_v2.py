"""#225 AC4/14/17: strict population evidence through real files and adapters.

The JSON fixture is independently authored; legacy atomic/parser/lifecycle tests
already protect shared infrastructure. Only new version-specific faults live here.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from report_support import RUN_ID, recorder

from tailtag_simulator.reports import ReportFailed, load_report, validate_report

DATA = Path(__file__).parent / "data/report-v2-convention.json"


def literal_population_report() -> dict[str, Any]:
    return json.loads(DATA.read_text())


def test_variable_population_report_round_trips_without_reinterpreting_v1() -> None:
    value = literal_population_report()
    assert validate_report(value) == value
    assert value["schema_version"] == 2
    assert value["population"]["identities"] == 8
    assert value["scenario"]["seed"] == -42
    for old in ("report-v1-smoke.json", "report-v1-journeys.json"):
        legacy = json.loads((DATA.parent / old).read_text())
        assert validate_report(legacy) == legacy


def test_v2_recorder_persists_safe_behavior_checks_and_resolved_assumptions(
    tmp_path: Path,
) -> None:
    value = literal_population_report()
    report = recorder(
        tmp_path,
        "convention-baseline",
        config=value["scenario"]["configuration"],
    )
    initial = load_report(report.path)
    assert initial["schema_version"] == 4
    assert initial["population"] == value["population"]
    assert initial["profile"] == value["profile"]
    report.record_behavior(value["results"]["behavior"]["items"], None)
    report.record_population_checks(value["results"]["checks"])
    saved = load_report(report.path)
    assert saved["results"] == {
        "behavior": value["results"]["behavior"],
        "checks": value["results"]["checks"],
        "cleanup": {"value": None, "reason": "not_observed"},
    }
    assert report.run_id == RUN_ID


CLOSED_V2 = [
    ("population",),
    ("population", "roles"),
    ("population", "fixtures"),
    ("profile",),
    ("results",),
    ("results", "behavior"),
    ("results", "behavior", "items"),
    ("results", "behavior", "items", "casual"),
]


@pytest.mark.parametrize("path", CLOSED_V2)
def test_v2_private_fields_cannot_enter_new_population_objects(
    path: tuple[str, ...],
) -> None:
    value = literal_population_report()
    current = value
    for key in path:
        current = current[key]
    current["SENTINEL-private"] = "sk_live_SECRET"
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


V2_FAULTS: list[tuple[tuple[str, ...], object]] = [
    (("schema_version",), 1),
    (("scenario", "consumes_randomness"), False),
    (("population", "identities"), 7),
    (("population", "roles", "casual"), 1),
    (("population", "fixtures", "fursuits"), 7),
    (("profile", "concurrency"), {"value": 8, "reason": None}),
    (("results", "behavior", "items", "casual", "actors"), True),
    (("results", "behavior", "items", "casual", "actions"), 1_000_001),
    (("results", "behavior", "items", "casual", "actors"), 1),
    (("results", "behavior", "items", "casual", "completed"), 0),
    (("results", "behavior", "items", "retry_prone", "retries"), 0),
    (("results", "behavior", "items", "heavy", "unused_budget"), 0),
    (("results", "behavior", "items", "normal_owner", "cycles"), 0),
    (("results", "behavior", "failure"), "SENTINEL-exception"),
    (("results", "behavior", "failure"), "FAIL_SIMULATION"),
    (("results", "checks"), {"items": [], "count": 0, "reason": "not_observed"}),
    (("results", "cleanup"), {"value": None, "reason": "not_observed"}),
]


@pytest.mark.parametrize(("path", "replacement"), V2_FAULTS)
def test_v2_cannot_claim_success_with_unobserved_inconsistent_or_unsafe_evidence(
    path: tuple[str, ...], replacement: object
) -> None:
    value = literal_population_report()
    current = value
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def failed_report() -> dict[str, Any]:
    value = literal_population_report()
    value["outcome"] = "failed"
    value["correctness"] = "failed"
    value["phases"]["reconciliation"].update(
        status="failed", code="FAIL_RECONCILIATION"
    )
    value["failure"] = {"stage": "reconciliation", "code": "FAIL_RECONCILIATION"}
    value["results"]["checks"] = {
        "items": [
            {"check": "duplicate", "actor": "attendee5", "expected": 1, "observed": 2}
        ],
        "count": 14,
        "reason": None,
    }
    return value


@pytest.mark.parametrize(
    "fault", [None, "owner-range", "attendee-range", "private", "count"]
)
def test_v2_failed_evidence_supports_variable_actor_labels_but_remains_closed(
    fault: str | None,
) -> None:
    value = failed_report()
    if fault is None:
        assert validate_report(value) == value
        return
    item = value["results"]["checks"]["items"][0]
    if fault == "owner-range":
        item["actor"] = "owner2"
    elif fault == "attendee-range":
        item["actor"] = "attendee6"
    elif fault == "private":
        item["response"] = "SENTINEL-secret"
    else:
        value["results"]["checks"]["count"] = 0
    with pytest.raises(ReportFailed):
        validate_report(value)


@pytest.mark.parametrize("adapter", ["behavior", "checks"])
def test_v2_adapters_refuse_private_payload_before_writing(
    tmp_path: Path, adapter: str
) -> None:
    value = literal_population_report()
    report = recorder(
        tmp_path, "convention-baseline", config=value["scenario"]["configuration"]
    )
    prior = report.path.read_bytes()
    with pytest.raises(ReportFailed):
        if adapter == "behavior":
            summaries = copy.deepcopy(value["results"]["behavior"]["items"])
            summaries["casual"]["token"] = "SENTINEL-secret"
            report.record_behavior(summaries, None)
        else:
            checks = copy.deepcopy(value["results"]["checks"])
            checks["raw_body"] = "SENTINEL-secret"
            report.record_population_checks(checks)
    assert report.path.read_bytes() == prior


@pytest.mark.parametrize("outcome", ["passed", "failed"])
def test_zero_actor_persona_cannot_report_actions_even_in_failed_evidence(
    outcome: str,
) -> None:
    value = literal_population_report()
    value["scenario"]["configuration"]["casual"] = 0
    value["population"]["roles"]["casual"] = 0
    value["population"]["identities"] = 6
    value["population"]["fixtures"]["attendees"] = 4
    value["results"]["behavior"]["items"]["casual"] = {
        "actors": 0,
        "actions": 0,
        "completed": 0,
        "created": 0,
        "already_caught": 0,
        "expected_rejections": 0,
        "retries": 0,
        "history_reads": 0,
        "exhausted": 0,
        "unused_budget": 0,
        "cycles": 0,
    }
    if outcome == "failed":
        value["outcome"] = "failed"
        value["correctness"] = "failed"
        value["phases"]["reconciliation"].update(
            status="failed", code="FAIL_RECONCILIATION"
        )
        value["failure"] = {"stage": "reconciliation", "code": "FAIL_RECONCILIATION"}
        value["results"]["checks"]["items"] = [
            {"check": "duplicate", "actor": "attendee3", "expected": 1, "observed": 2}
        ]
    # Zero counts are supported synthetic configuration, not a missing-results
    # error. Establish valid evidence before injecting impossible activity.
    assert validate_report(value) == value
    value["results"]["behavior"]["items"]["casual"]["actions"] = 1
    with pytest.raises(ReportFailed):
        validate_report(value)
