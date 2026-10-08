"""#226 AC19–20: versioned traffic evidence, privacy and accounting integrity."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from convention_support import CONFIG
from report_support import RUN_ID, commit, literal_report, read_report, repository
from safety_report_support import literal_safety

from tailtag_simulator.reports import ReportFailed, RunReport, validate_report
from tailtag_simulator.scenarios import (
    ScenarioRejected,
    resolve_scenario,
    validate_catalog,
)

DATA = Path(__file__).parent / "data"
FAMILIES = ("baseline", "post-event", "hotspot", "retry", "soak")


def traffic_snapshot() -> dict[str, Any]:
    # Independent observed evidence: one offered arrival was skipped, two finished.
    return {
        "plan_digest": "a" * 64,
        "offered": 3,
        "admitted": 2,
        "skipped": 1,
        "completed": 2,
        "active_peak": 2,
        "in_flight_peak": 1,
        "attempts": 8,
        "sent": 7,
        "injected": 1,
        "transient": 0,
        "retries": 1,
        "expected_rejections": 0,
        "exhausted": 0,
        "unresolved": 0,
        "generation_seconds": 2.0,
        "drain_seconds": 0.1,
        "lag_seconds": 0.01,
        "stop_reason": None,
        "buckets": [
            {
                "at_seconds": 0.0,
                "offered": 2,
                "admitted": 1,
                "skipped": 1,
                "completed": 1,
            },
            {
                "at_seconds": 1.0,
                "offered": 1,
                "admitted": 1,
                "skipped": 0,
                "completed": 1,
            },
        ],
    }


def traffic_report(root: Path) -> RunReport:
    return RunReport(
        root,
        "convention-baseline",
        scenario_version=2,
        config=CONFIG,
        seed=-42,
        run_id=RUN_ID,
    )


def successful_report(root: Path) -> dict[str, Any]:
    report = traffic_report(root)
    report.record_traffic(traffic_snapshot())
    initial = read_report(report.path)
    value: dict[str, Any] = json.loads((DATA / "report-v2-convention.json").read_text())
    # Reuse independently authored attribution/lifecycle proof. Version-specific
    # catalog/config/limits originate from the real recorder, never a fake validator.
    for key in ("schema_version", "scenario", "profile", "limits", "population"):
        value[key] = initial[key]
    value["safety"] = literal_safety()
    value["results"]["traffic"] = {"value": traffic_snapshot(), "reason": None}
    # Traffic summaries are observations, not the legacy fixed cycle equations.
    value["results"]["behavior"]["items"]["casual"].update(
        completed=1,
        created=1,
        cycles=1,
        history_reads=1,
    )
    assert validate_report(value) == value
    return value


def test_v3_recorder_preserves_resolved_profiles_and_observed_traffic(
    tmp_path: Path,
) -> None:
    report = traffic_report(tmp_path)
    before = read_report(report.path)
    assert before["schema_version"] == 4
    assert before["scenario"]["version"] == 2
    assert before["results"]["traffic"] == {"value": None, "reason": "not_observed"}
    assert set(before["profile"]) == {"operations", "traffic", "failure", "retry"}
    for key in ("traffic", "failure", "retry"):
        assert before["profile"][key] == before["scenario"]["configuration"][key]
    assert {
        key: before["limits"][key]
        for key in (
            "request_ceiling",
            "duration_ceiling",
            "concurrency_ceiling",
            "active_ceiling",
            "drain_ceiling",
        )
    } == {
        "request_ceiling": {
            "value": 5000,
            "reason": None,
            "unit": "attempts",
            "scope": "simulation",
        },
        "duration_ceiling": {
            "value": 300,
            "reason": None,
            "unit": "seconds",
            "scope": "generation",
        },
        "concurrency_ceiling": {
            "value": 10,
            "reason": None,
            "unit": "requests",
            "scope": "simulation",
        },
        "active_ceiling": {
            "value": 10,
            "reason": None,
            "unit": "actors",
            "scope": "simulation",
        },
        "drain_ceiling": {
            "value": 15,
            "reason": None,
            "unit": "seconds",
            "scope": "drain",
        },
    }
    sample = traffic_snapshot()
    report.record_traffic(sample)
    sample["offered"] = 999  # The caller cannot later mutate persisted evidence.
    assert read_report(report.path)["results"]["traffic"] == {
        "value": traffic_snapshot(),
        "reason": None,
    }
    assert set(before) == set(literal_report()) | {"safety"}
    for old in (
        "report-v1-smoke.json",
        "report-v1-journeys.json",
        "report-v2-convention.json",
    ):
        historical = json.loads((DATA / old).read_text())
        assert validate_report(historical) == historical
    successful_report(tmp_path / "passed")


FAULTS: list[tuple[tuple[str | int, ...], object]] = [
    (("offered",), 4),
    (("completed",), 3),
    (("sent",), 9),
    (("attempts",), True),
    (("attempts",), 1_000_001),
    (("active_peak",), 11),
    (("in_flight_peak",), 11),
    (("generation_seconds",), float("inf")),
    (("drain_seconds",), -1),
    (("plan_digest",), "private-SENTINEL"),
    (("unresolved",), 1),
    (("exhausted",), 1),
    (("stop_reason",), "attempts"),
    (("stop_reason",), "SENTINEL-private-exception"),
    (("buckets", 0, "offered"), 3),
    (("buckets", 1, "at_seconds"), 0.0),
    (
        ("buckets",),
        [{"at_seconds": 0.0, "offered": 0, "admitted": 0, "skipped": 0, "completed": 0}]
        * 1001,
    ),
    (
        ("buckets",),
        [
            {
                "at_seconds": 0.0,
                "offered": 2,
                "admitted": 1,
                "skipped": 1,
                "completed": 2,
            },
            {
                "at_seconds": 1.0,
                "offered": 1,
                "admitted": 1,
                "skipped": 0,
                "completed": 0,
            },
        ],
    ),
]


@pytest.mark.parametrize(("path", "replacement"), FAULTS)
def test_v3_success_rejects_inconsistent_or_incomplete_traffic(
    tmp_path: Path,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    value = successful_report(tmp_path)
    current = value["results"]["traffic"]["value"]
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


@pytest.mark.parametrize(
    "path",
    [
        ("profile",),
        ("profile", "traffic"),
        ("profile", "failure"),
        ("profile", "retry"),
        ("limits",),
        ("results",),
        ("results", "traffic"),
        ("results", "traffic", "value"),
        ("results", "traffic", "value", "buckets", 0),
    ],
)
def test_v3_new_evidence_objects_reject_private_fields(
    tmp_path: Path,
    path: tuple[str | int, ...],
) -> None:
    value = successful_report(tmp_path)
    current: Any = value
    for key in path:
        current = current[key]
    current["token"] = "SENTINEL-sk_live_SECRET"
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_traffic_adapter_rejects_private_payload_without_altering_report(
    tmp_path: Path,
) -> None:
    report = traffic_report(tmp_path)
    prior = report.path.read_bytes()
    sample = traffic_snapshot()
    sample["response_body"] = "SENTINEL-secret"
    with pytest.raises(ReportFailed):
        report.record_traffic(sample)
    assert report.path.read_bytes() == prior


@pytest.mark.parametrize("family", FAMILIES)
def test_five_v2_recipes_are_additive_and_committed_versions_remain_immutable(
    tmp_path: Path,
    family: str,
) -> None:
    scenario = f"convention-{family}"
    old = cast(dict[str, Any], resolve_scenario(scenario, 1, {"pool": "p1"}))
    new = cast(dict[str, Any], resolve_scenario(scenario, 2, {"pool": "p1"}))
    assert old["version"] == 1 and new["version"] == 2
    assert new["descriptor"]["api_contract"] == "tailtag-public-v0"
    assert new["descriptor_digest"] != old["descriptor_digest"]
    assert set(new["configuration"]) - set(old["configuration"]) == {
        "traffic",
        "failure",
        "retry",
        "limits",
    }
    relative = "tools/simulator/tailtag_simulator/scenarios"
    files: dict[str, str | bytes] = {
        f"{relative}/{scenario}-v{version}.json": json.dumps(
            {
                **resolved["descriptor"],
                "descriptor_digest": resolved["descriptor_digest"],
            }
        )
        for version, resolved in ((1, old), (2, new))
    }
    root = repository(tmp_path / "catalog", files)
    validate_catalog(root)
    path = root / relative / f"{scenario}-v2.json"
    path.unlink()
    commit(root, "Remove previously admitted v2 recipe")
    with pytest.raises(ScenarioRejected):
        validate_catalog(root)
    assert resolve_scenario(scenario, 1, {"pool": "p1"}) == old


def test_v3_success_cannot_omit_observed_traffic(tmp_path: Path) -> None:
    value = successful_report(tmp_path)
    value["results"]["traffic"] = {"value": None, "reason": "not_observed"}
    with pytest.raises(ReportFailed):
        validate_report(value)


@pytest.mark.parametrize("fault", ["profile", "limit", "persona", "check"])
def test_v3_metadata_and_correctness_labels_cannot_be_tampered(
    tmp_path: Path,
    fault: str,
) -> None:
    value = successful_report(tmp_path)
    if fault == "profile":
        value["profile"]["retry"]["attempts"] = 4
    elif fault == "limit":
        value["limits"]["request_ceiling"]["value"] = 5001
    elif fault == "persona":
        items = value["results"]["behavior"]["items"]
        items["SENTINEL-private-actor"] = items.pop("casual")
    else:
        value["results"]["checks"]["items"] = [
            {
                "check": "SENTINEL-private-check",
                "actor": "attendee0",
                "expected": 1,
                "observed": 0,
            }
        ]
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_historical_schema3_retains_traffic_evidence_meaning(tmp_path: Path) -> None:
    value = successful_report(tmp_path)
    historical = {key: item for key, item in value.items() if key != "safety"}
    historical["schema_version"] = 3
    assert validate_report(historical) == historical
    assert historical["results"]["traffic"]["value"] == traffic_snapshot()
