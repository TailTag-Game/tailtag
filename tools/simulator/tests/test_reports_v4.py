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
from traffic_support import ManualClock

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
        runtime = SafetyRuntime(
            POLICY, observe=report.cache_safety, persist=report.record_safety
        )

        async def probe() -> dict[str, object]:
            return dict(literal_safety()["target"]["identity"])

        runtime.bind_probe(probe)
        with runtime.scope():
            await runtime.check_target()
            armed = True
            # Hot request updates are cached; an explicit probe is a durable boundary.
            with pytest.raises(SafetyAborted):
                await runtime.check_target()
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


def test_hot_http_caches_evidence_until_phase_tick_abort_or_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durability checkpoints retain latest evidence without hotpath disk writes."""
    time = ManualClock()
    policy = {**POLICY, "error_window_seconds": 5}
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=policy,
    )
    writes: list[str] = []
    original_fsync, original_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        writes.append("fsync")
        original_fsync(fd)

    def replace(source: Any, destination: Any) -> None:
        writes.append("replace")
        original_replace(source, destination)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    async def execute() -> None:
        runtime = SafetyRuntime(
            policy,
            monotonic=lambda: time.now,
            sleep=time.sleep,
            observe=report.cache_safety,
            persist=report.record_safety,
        )

        async def probe() -> dict[str, object]:
            return dict(literal_safety()["target"]["identity"])

        runtime.bind_probe(probe)
        entered, released = asyncio.Event(), asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/blocked":
                entered.set()
                await released.wait()
            return httpx.Response(
                503 if request.url.path == "/unavailable" else 200, json={}
            )

        with runtime.scope():
            await runtime.check_target()
            assert read_report(report.path)["safety"]["preflight"]["passed"] == 1
            async with open_client(
                "https://staging.tailtag.app", transport=httpx.MockTransport(respond)
            ) as client:
                with runtime.phase("simulation"):
                    checkpoint = len(writes)
                    await client.get("/ok")
                    await client.get("/unavailable")
                    assert len(writes) == checkpoint
                    assert (
                        read_report(report.path)["safety"]["execution"]["requests"] == 0
                    )
                persisted = read_report(report.path)["safety"]
                assert persisted["execution"]["requests"] == 2
                assert persisted["execution"]["ordinary_active"] == 0
                assert persisted["errors"]["current_completed"] == 2
                assert persisted["errors"]["current_catastrophic"] == 1

                with runtime.phase("simulation"):
                    await runtime.start_monitor()
                    blocked = asyncio.create_task(client.get("/blocked"))
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=3)
                        await time.settle()
                        checkpoint = len(writes)
                        await time.advance(5)  # Before the ten-second identity poll.
                        assert len(writes) > checkpoint
                        persisted = read_report(report.path)["safety"]
                        assert persisted["probes"]["checks"] == 0
                        assert persisted["execution"]["requests"] == 3
                        assert persisted["execution"]["ordinary_active"] == 1
                        assert persisted["errors"]["last_completed"] == 2
                        assert persisted["errors"]["last_catastrophic"] == 1
                        checkpoint = len(writes)
                        released.set()
                        await asyncio.wait_for(blocked, timeout=3)
                        assert len(writes) == checkpoint
                        runtime.abort("resource_saturation")
                        persisted = read_report(report.path)["safety"]
                        assert persisted["abort"] == {
                            "reason": "resource_saturation",
                            "elapsed_seconds": 5.0,
                        }
                        assert persisted["execution"]["ordinary_active"] == 0
                        assert persisted["errors"]["current_completed"] == 1
                    finally:
                        if not blocked.done():
                            blocked.cancel()
                        await asyncio.gather(blocked, return_exceptions=True)
                        await runtime.stop_monitor()
                assert await runtime.begin_finalization()
                with runtime.phase("finalization"):
                    await client.get("/retain")
                    runtime.record_finalization("retention", "passed")
                    persisted = read_report(report.path)["safety"]
                    assert persisted["finalization"]["retention"] == "passed"
                    assert persisted["finalization"]["requests"] == 1
                # After the phase checkpoint, finish must flush this latest cache.
                checkpoint = len(writes)
                await client.get("/closure")
                assert len(writes) == checkpoint
                assert (
                    read_report(report.path)["safety"]["finalization"]["requests"] == 1
                )
                assert report.finish(0) != 0
                persisted = read_report(report.path)["safety"]
                assert persisted["finalization"]["requests"] == 2
                assert persisted["finalization"]["ordinary_active"] == 0
                assert persisted["errors"]["current_completed"] == 1
        assert not time.waiters

    asyncio.run(execute())
    assert writes.count("fsync") == writes.count("replace") > 0
    assert read_report(report.path)["outcome"] == "aborted"
    assert not list(tmp_path.glob(".snapshot-*"))


def test_invalid_cached_safety_latches_failure_and_preserves_last_valid_evidence(
    tmp_path: Path,
) -> None:
    report = RunReport(
        tmp_path,
        "smoke",
        config={"target": "staging"},
        run_id=RUN_ID,
        safety_policy=POLICY,
    )
    report.cache_safety(literal_safety())
    invalid = literal_safety()
    invalid["execution"]["SENTINEL-secret"] = "private-provider-ID"
    with pytest.raises(ReportFailed):
        report.cache_safety(invalid)
    assert report.write_failed
    later = literal_safety()
    later["execution"]["requests"] = 5
    # Valid evidence is rejected because recorder failure is already latched.
    validate_report({**literal_report(), "schema_version": 4, "safety": later})
    with pytest.raises(ReportFailed):
        report.cache_safety(later)
    assert report.finish(0) != 0
    value = read_report(report.path)
    assert value["outcome"] == "failed"
    assert value["failure"] == {"stage": "report", "code": "FAIL_REPORT"}
    assert value["safety"] == literal_safety()
    assert "SENTINEL" not in report.path.read_text()
