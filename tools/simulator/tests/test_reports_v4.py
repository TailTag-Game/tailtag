"""#227 U3: strict sanitized schema4, historical meaning, and durable abort truth."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from report_support import RUN_ID, literal_report, read_report
from safety_report_support import POLICY, literal_safety

from tailtag_simulator.client import open_client
from tailtag_simulator.reports import ReportFailed, RunReport, validate_report
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    "historical",
    ["report-v1-smoke.json", "report-v1-journeys.json", "report-v2-convention.json"],
)
def test_guarded_schema_preserves_historical_scenario_and_results(
    historical: str,
) -> None:
    original: dict[str, Any] = json.loads((DATA / historical).read_text())
    assert validate_report(original) == original
    guarded = {**original, "schema_version": 4, "safety": literal_safety()}
    validated = cast(dict[str, Any], validate_report(guarded))
    assert validated == guarded
    assert validated["scenario"] == original["scenario"]
    assert validated["results"] == original["results"]
    assert "safety" not in validated["scenario"]["configuration"]


def test_recorder_safety_snapshot_is_durable_bounded_and_abort_cannot_finish_as_pass(
    tmp_path: Path,
) -> None:
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=POLICY,
    )
    snapshot = literal_safety()
    report.record_safety(snapshot)
    for _ in range(20):
        report.record_safety(snapshot)
    value = read_report(report.path)
    assert value["schema_version"] == 4
    assert value["safety"] == snapshot
    snapshot["abort"] = {"reason": "resource_saturation", "elapsed_seconds": 6.0}
    report.record_safety(snapshot)
    assert report.finish(0) != 0
    result = read_report(report.path)
    assert result["outcome"] == "aborted"
    assert result["safety"]["abort"] == {
        "reason": "resource_saturation",
        "elapsed_seconds": 6.0,
    }
    assert result["safety"]["resources"] == {"monitoring": "unavailable"}
    assert (
        result["scenario"]["descriptor"] == literal_report()["scenario"]["descriptor"]
    )
    assert not list(tmp_path.glob(".snapshot-*"))


CLOSED_SAFETY = [
    (),
    ("policy",),
    ("target",),
    ("target", "identity"),
    ("preflight",),
    ("probes",),
    ("execution",),
    ("finalization",),
    ("errors",),
    ("abort",),
    ("resources",),
    ("concurrency",),
]


@pytest.mark.parametrize("path", CLOSED_SAFETY)
def test_each_new_closed_safety_object_rejects_private_unknown_fields(
    path: tuple[str, ...],
    tmp_path: Path,
) -> None:
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=POLICY,
    )
    snapshot = literal_safety()
    snapshot["abort"] = {"reason": "correctness", "elapsed_seconds": 6.0}
    report.record_safety(snapshot)
    report.finish(1)
    value = read_report(report.path)
    assert validate_report(value) == value
    current = value["safety"]
    for key in path:
        current = current[key]
    current["SENTINEL-secret"] = "private-provider-ID"
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("policy", "requests"), True),
        (("execution", "requests"), -1),
        (("execution", "elapsed_seconds"), float("nan")),
        (("execution", "ordinary_peak"), 11),
        (("execution", "ordinary_active"), 2),
        (("probes", "last"), "SENTINEL-raw-error"),
        (("finalization", "release"), "SENTINEL-provider-message"),
        (("resources", "monitoring"), "healthy"),
        (("errors", "current_catastrophic"), 3),
        (("concurrency", "combined_limit"), 10),
        (("target", "evidence"), "production"),
        (("target", "identity", "source_sha"), "b" * 40),
        (
            ("preflight",),
            {"checks": 1, "passed": 0, "failed": 1, "last": "unavailable"},
        ),
        (("abort",), {"reason": "SENTINEL-response-body", "elapsed_seconds": 6}),
        (("abort",), {"reason": "resource_saturation", "elapsed_seconds": 6}),
    ],
)
def test_safety_counter_enum_and_abort_truth_tampering_cannot_validate(
    path: tuple[str, ...],
    replacement: object,
) -> None:
    value: dict[str, Any] = {
        **literal_report(),
        "schema_version": 4,
        "safety": literal_safety(),
    }
    assert validate_report(value) == value
    current = value["safety"]
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_safety_persistence_failure_latches_abort_before_more_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=POLICY,
    )
    armed = False
    original = os.replace

    def replace(source: Any, destination: Any) -> None:
        if armed:
            raise OSError("SENTINEL-private-filesystem-error")
        original(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    sent: list[str] = []

    async def execute() -> None:
        nonlocal armed
        runtime = SafetyRuntime(POLICY, observe=report.record_safety)

        async def probe() -> dict[str, object]:
            return dict(literal_safety()["target"]["identity"])

        runtime.bind_probe(probe)
        with runtime.scope():
            await runtime.check_target()
            armed = True
            async with open_client(
                "https://staging.tailtag.app",
                transport=httpx.MockTransport(
                    lambda r: (sent.append(r.url.path), httpx.Response(200, json={}))[1]
                ),
            ) as client:
                with pytest.raises(SafetyAborted):
                    await client.get("/after-failed-snapshot")
                assert runtime.abort_reason == "report_failure"
                assert (
                    cast(dict[str, object], runtime.snapshot()["execution"])["requests"]
                    == 0
                )
                with pytest.raises(SafetyAborted):
                    await client.get("/must-not-restart")
            assert sent == []
        armed = False
        report.record_safety(runtime.snapshot())
        assert report.finish(0) != 0

    asyncio.run(execute())
    assert read_report(report.path)["outcome"] == "aborted"
    assert "SENTINEL" not in report.path.read_text()
    assert not list(tmp_path.glob(".snapshot-*"))


def test_terminal_abort_evidence_cannot_be_reported_as_ordinary_failure(
    tmp_path: Path,
) -> None:
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=POLICY,
    )
    snapshot = literal_safety()
    snapshot["abort"] = {"reason": "correctness", "elapsed_seconds": 6}
    report.record_safety(snapshot)
    report.finish(1)
    value = read_report(report.path)
    assert value["outcome"] == "aborted"
    value["outcome"] = "failed"
    with pytest.raises(ReportFailed):
        validate_report(value)
