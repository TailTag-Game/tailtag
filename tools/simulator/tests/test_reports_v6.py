"""#508 AC27, AC28: schema 6 carries the catch request operations and counters."""

import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from convention_support import CONFIG
from performance_support import traffic_snapshot
from report_support import RUN_ID, read_report
from test_reports_v5 import recorded as recorded_v5
from traffic_support import ManualClock

from tailtag_simulator.client import Reply
from tailtag_simulator.reports import ReportFailed, RunReport, validate_report
from tailtag_simulator.reports_v2 import V6_COUNTERS
from tailtag_simulator.traffic import TrafficRuntime
from tailtag_simulator.traffic_config import resolve_request_traffic_config

V6_NAMES = {"auxiliary", "preview", "submit", "review", "decide", "read", "total"}


def request_performance(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Six responses and one injected attempt, like the schema 5 fixture."""
    time = ManualClock()
    runtime = TrafficRuntime(
        resolve_request_traffic_config({"pool": "alpha"}),
        clock=time.clock,
        request_flow=True,
    )
    runtime.generation_seconds = snapshot["generation_seconds"]
    runtime.drain_seconds = snapshot["drain_seconds"]

    async def attempt(operation: str, status: int, milliseconds: float) -> None:
        async def send() -> Reply:
            time.now += milliseconds / 1000
            return Reply(status, None)

        await runtime.request(send, operation=operation)

    async def measure() -> None:
        await attempt("preview", 200, 10)
        await attempt("submit", 201, 30)
        await attempt("submit", 200, 20)
        await attempt("review", 200, 15)
        await attempt("decide", 200, 25)
        await attempt("read", 200, 5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, measure()).result()
    return runtime.performance()


def recorded(root: Path) -> dict[str, Any]:
    report = RunReport(
        root,
        "convention-baseline",
        scenario_version=3,
        config=CONFIG,
        seed=-42,
        run_id=RUN_ID,
    )
    snapshot = traffic_snapshot()
    snapshot.update(attempts=6, sent=6, injected=0, retries=0)
    report.record_execution_mode("container")
    report.record_traffic(snapshot, request_performance(snapshot))
    summaries = {
        persona: dict.fromkeys(V6_COUNTERS, 0)
        for persona in (
            "casual",
            "active",
            "heavy",
            "retry_prone",
            "normal_owner",
            "popular_owner",
        )
    }
    for persona, actors in (
        ("casual", 2),
        ("active", 1),
        ("heavy", 1),
        ("retry_prone", 2),
        ("normal_owner", 1),
        ("popular_owner", 1),
    ):
        summaries[persona]["actors"] = actors
    report.record_behavior(summaries, None)
    return read_report(report.path)


def test_scenario_v3_writes_a_valid_schema_6_report(tmp_path: Path) -> None:
    value = recorded(tmp_path)

    assert value["schema_version"] == 6
    assert value["profile"]["review"]["approve_rate"] == 0.85
    assert set(value["performance"]["attempts"]["value"]) == V6_NAMES
    assert validate_report(value) == value


def test_schema_5_and_schema_6_never_mix(tmp_path: Path) -> None:
    v6 = recorded(tmp_path / "v6")
    v5, _ = recorded_v5(tmp_path / "v5")
    for mixed in ({**v6, "schema_version": 5}, {**v5, "schema_version": 6}):
        with pytest.raises(ReportFailed):
            validate_report(mixed)


def test_schema_6_rejects_the_v1_counters(tmp_path: Path) -> None:
    value = recorded(tmp_path)
    old = copy.deepcopy(value)
    for item in old["results"]["behavior"]["items"].values():
        item.pop("pending")
        item["created"] = 0
    with pytest.raises(ReportFailed):
        validate_report(old)
