"""#229 U1 (AC11): schema 5 carries measured performance, strictly and honestly."""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from convention_support import CONFIG
from performance_support import CLASSES, measured_performance, traffic_snapshot
from report_support import RUN_ID, read_report

from tailtag_simulator.reports import (
    ReportFailed,
    RunReport,
    unavailable,
    validate_report,
)

RESPONSES = ("success", "expected_rejection", "client_error", "server_error")
NOT_OBSERVED = {"value": None, "reason": "not_observed"}


def recorder(root: Path) -> RunReport:
    return RunReport(
        root,
        "convention-baseline",
        scenario_version=2,
        config=CONFIG,
        seed=-42,
        run_id=RUN_ID,
    )


def recorded(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = recorder(root)
    snapshot = traffic_snapshot()
    measured = measured_performance(snapshot)
    report.record_execution_mode("container")
    report.record_traffic(snapshot, measured)
    return read_report(report.path), measured


def test_recorder_writes_schema_5_with_the_measurement_and_honest_gaps(
    tmp_path: Path,
) -> None:
    report = recorder(tmp_path)
    initial = read_report(report.path)
    assert initial["schema_version"] == 5
    assert initial["performance"] == {
        key: unavailable()
        for key in (
            "duration_seconds",
            "window_seconds",
            "execution_mode",
            "attempts",
            "throughput",
            "latency_percentiles",
            "resource_context",
        )
    }
    snapshot = traffic_snapshot()
    measured = measured_performance(snapshot)
    report.record_execution_mode("container")
    report.record_traffic(snapshot, measured)
    performance = read_report(report.path)["performance"]
    assert performance["execution_mode"] == {"value": "container", "reason": None}
    assert performance["window_seconds"] == {
        "value": pytest.approx(2.1),
        "reason": None,
    }
    for key in ("attempts", "throughput", "latency_percentiles"):
        assert performance[key] == {"value": measured[key], "reason": None}
    assert performance["resource_context"] == unavailable()
    report.finish(1)
    final = read_report(report.path)
    assert (
        final["performance"]["duration_seconds"] == final["timing"]["duration_seconds"]
    )
    assert final["performance"]["duration_seconds"]["value"] is not None


def bump(
    value: dict[str, Any], names: tuple[str, ...], outcome: str, amount: int
) -> None:
    """Change counts while keeping samples and throughput consistent with them."""
    performance = value["performance"]
    window = performance["window_seconds"]["value"]
    for name in names:
        counts = performance["attempts"]["value"][name]
        counts[outcome] += amount
        responses = sum(counts[key] for key in RESPONSES)
        performance["latency_percentiles"]["value"][name]["samples"] = responses
        performance["throughput"]["value"][name] = responses / window


def drop(container: dict[str, Any], key: str) -> None:
    del container[key]


def retime(value: dict[str, Any]) -> None:
    performance = value["performance"]
    performance["window_seconds"]["value"] = 3.0
    for name, counts in performance["attempts"]["value"].items():
        responses = sum(counts[key] for key in RESPONSES)
        performance["throughput"]["value"][name] = responses / 3.0


def attempts(value: dict[str, Any]) -> dict[str, Any]:
    return value["performance"]["attempts"]["value"]


def latency(value: dict[str, Any]) -> dict[str, Any]:
    return value["performance"]["latency_percentiles"]["value"]


MUTATIONS: dict[str, Callable[[dict[str, Any]], object]] = {
    "unknown-key": lambda v: v["performance"].update(SENTINEL=1),
    "missing-key": lambda v: drop(v["performance"], "window_seconds"),
    "unknown-operation": lambda v: attempts(v).update(SENTINEL=attempts(v)["read"]),
    "missing-operation": lambda v: drop(attempts(v), "auxiliary"),
    "unknown-class": lambda v: attempts(v)["resolve"].update(SENTINEL=0),
    "missing-class": lambda v: drop(attempts(v)["resolve"], "timeout"),
    "total-is-not-the-sum": lambda v: bump(v, ("total",), "success", 1),
    "injected-differs-from-traffic": lambda v: bump(
        v, ("resolve", "total"), "injected", 1
    ),
    "rejections-differ-from-traffic": lambda v: (
        bump(v, ("resolve", "total"), "success", -1),
        bump(v, ("resolve", "total"), "expected_rejection", 1),
    ),
    "responses-exceed-what-was-sent": lambda v: bump(
        v, ("resolve", "total"), "success", 2
    ),
    "samples-differ-from-responses": lambda v: latency(v)["resolve"].update(samples=9),
    "percentiles-not-monotonic": lambda v: latency(v)["resolve"].update(
        p50={"value": 99.0, "reason": None}
    ),
    "negative-percentile": lambda v: latency(v)["resolve"].update(
        p50={"value": -1.0, "reason": None}
    ),
    "null-percentile-with-samples": lambda v: latency(v)["resolve"].update(
        p99=NOT_OBSERVED
    ),
    "percentile-without-samples": lambda v: latency(v)["read"].update(
        samples=0, p50={"value": 1.0, "reason": None}
    ),
    "throughput-differs": lambda v: v["performance"]["throughput"]["value"].update(
        total=99.0
    ),
    "window-differs-from-traffic": retime,
    "resource-context-observed": lambda v: v["performance"].update(
        resource_context={"value": {"cpu": 1}, "reason": None}
    ),
    "free-text-execution-mode": lambda v: v["performance"].update(
        execution_mode={"value": "SENTINEL-host-name", "reason": None}
    ),
    "performance-without-observed-traffic": lambda v: v["results"].update(
        traffic=unavailable()
    ),
}


def test_valid_schema_5_report_validates_and_round_trips(tmp_path: Path) -> None:
    value, _ = recorded(tmp_path)
    assert validate_report(value) == value
    assert set(attempts(value)) == {"auxiliary", "resolve", "confirm", "read", "total"}
    assert set(attempts(value)["total"]) == set(CLASSES)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_schema_5_rejects_every_inconsistent_or_unclosed_performance_block(
    tmp_path: Path, mutation: str
) -> None:
    value, _ = recorded(tmp_path)
    MUTATIONS[mutation](value)
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_schema_4_convention_reports_keep_their_contract_and_never_mix(
    tmp_path: Path,
) -> None:
    value, _ = recorded(tmp_path)
    historical = copy.deepcopy(value)
    historical["schema_version"] = 4
    historical["performance"] = {
        "duration_seconds": value["performance"]["duration_seconds"],
        "throughput": unavailable("not_implemented"),
        "latency_percentiles": unavailable("not_implemented"),
        "resource_context": unavailable(),
    }
    assert validate_report(historical) == historical
    new_shape_as_4 = {**value, "schema_version": 4}
    old_shape_as_5 = {**historical, "schema_version": 5}
    for mixed in (new_shape_as_4, old_shape_as_5):
        with pytest.raises(ReportFailed):
            validate_report(mixed)
