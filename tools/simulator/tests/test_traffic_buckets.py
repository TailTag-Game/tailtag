"""PR300: decimal bucket boundaries stay consistent through report readback."""

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest
from report_support import RUN_ID, ReportClock, read_report
from traffic_support import ManualClock

from tailtag_simulator.reports import ReportFailed, RunReport
from tailtag_simulator.traffic import Entry, TrafficRuntime, run_schedule
from tailtag_simulator.traffic_config import resolve_traffic_config


def scheduled_traffic(
    duration: float, width: float
) -> tuple[dict[str, object], dict[str, object]]:
    resolved = resolve_traffic_config(
        {
            "pool": "alpha",
            "traffic": {
                "segments": [{"duration_seconds": duration, "start": 0, "end": 0}],
                "bucket_seconds": width,
                "bursts": [{"at_seconds": 0, "count": 1}],
                "think_seconds": 0,
            },
        }
    )

    async def execute() -> dict[str, object]:
        time = ManualClock()
        runtime = TrafficRuntime(resolved, clock=time.clock)

        async def entry(_: Entry) -> bool:
            return True

        task = asyncio.create_task(
            run_schedule(resolved, 42, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.settle()
            await time.advance(duration)
            assert task.done(), "finite profile did not finish"
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return resolved, asyncio.run(execute())


def traffic_report(root: Path, config: dict[str, object]) -> RunReport:
    clock = ReportClock()
    return RunReport(
        root,
        "convention-baseline",
        scenario_version=2,
        config=config,
        seed=42,
        run_id=RUN_ID,
        wall_clock=clock.wall_clock,
        monotonic=clock.monotonic,
    )


@pytest.mark.parametrize(
    ("duration", "width", "expected_count"),
    [
        pytest.param(0.07, 0.01, 7, id="decimal-whole-boundary"),
        # Python's binary quotient is 1000.0000000000001 for these decimals.
        pytest.param(2.1, 0.0021, 1000, id="decimal-hard-cap-boundary"),
        pytest.param(1.15, 0.1, 12, id="genuine-partial-final-interval"),
        pytest.param(1e-10, 1.0, 1, id="positive-profile-below-tolerance"),
    ],
)
def test_bucket_boundaries_survive_configuration_scheduling_and_report_readback(
    tmp_path: Path, duration: float, width: float, expected_count: int
) -> None:
    config, snapshot = scheduled_traffic(duration, width)
    report = traffic_report(tmp_path, config)
    report.record_traffic(snapshot)
    assert read_report(report.path)["results"]["traffic"] == {
        "value": snapshot,
        "reason": None,
    }
    buckets = cast(list[dict[str, object]], snapshot["buckets"])
    assert len(buckets) == expected_count
    assert snapshot["offered"] == snapshot["admitted"] == snapshot["completed"] == 1
    assert snapshot["skipped"] == 0
    assert snapshot["stop_reason"] is None


@pytest.mark.parametrize("tamper", ["append-terminal", "replace-last"])
def test_report_rejects_terminal_bucket_even_with_valid_grid_and_accounting(
    tmp_path: Path,
    tamper: str,
) -> None:
    config, snapshot = scheduled_traffic(1.0, 0.1)
    report = traffic_report(tmp_path, config)
    report.record_traffic(snapshot)
    value = read_report(report.path)
    buckets = value["results"]["traffic"]["value"]["buckets"]
    if tamper == "append-terminal":
        buckets.append(
            {
                "at_seconds": 1.0,
                "offered": 0,
                "admitted": 0,
                "skipped": 0,
                "completed": 0,
            }
        )
    else:
        buckets[-1]["at_seconds"] = 1.0
    report.path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ReportFailed):
        read_report(report.path)
