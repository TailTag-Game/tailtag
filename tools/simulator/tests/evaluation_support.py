"""#229 U2 inputs: a real passing schema-5 report plus hand-written contract files.

Reports come from the real recorder fixtures and change only through edits that
`load_report` still accepts. Threshold, baseline, companion and context files
are literal contract-shaped JSON, because those are the inputs under test.
"""

import copy
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from report_support import RUN_ID
from test_reports_v3 import successful_report

from tailtag_simulator.reports import unavailable

PLATFORM = "linux/amd64"
IMAGE = "sha256:" + "1" * 64
OTHER_IMAGE = "sha256:" + "2" * 64
CONTEXT_SIGNALS = (
    "http_5xx",
    "server_latency",
    "db_connections",
    "worker_timeouts",
    "restarts_or_oom",
    "runtime_resources",
    "domain_outcomes",
)
DEFAULT: Any = object()  # "use the standard fixture"; None means "omit the file"
Edit = Callable[[dict[str, Any]], object]

# The fixed report has 6 responses of 5/10/20/30/40/50 ms: total p95 = p99 = 50.
STATEMENT = (
    "Thresholds and baselines are documented assumptions for regression "
    "evidence; they are not production SLOs or capacity claims."
)


class Inputs(NamedTuple):
    report: Path
    baselines: Path
    companion: Path | None
    context: Path | None
    key: dict[str, Any]


def limit(value: float) -> dict[str, Any]:
    return {"value": value, "assumption": "Test assumption for this limit."}


def thresholds_file(key: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "thresholds",
        "key": key,
        "minimum_samples": {"p95": limit(1), "p99": limit(1)},
        "operations": {
            "total": {
                "p95_ms": limit(100),
                "p99_ms": limit(100),
                "error_rate": limit(0.5),
                "timeout_rate": limit(0.01),
            }
        },
        "regression": {
            "p95_percent": limit(25),
            "p99_percent": limit(50),
            "minimum_delta_ms": limit(20),
        },
        "saturation": {
            "peak_cpu_percent": limit(160),
            "lag_seconds": limit(1.0),
            "steal_ticks_delta": limit(1500),
        },
    }


def baseline_file(key: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    performance = report["performance"]
    throughput = performance["throughput"]["value"]
    metrics = {
        name: {
            "samples": block["samples"],
            **{q: block[q]["value"] for q in ("p50", "p95", "p99", "max")},
            "error_rate": 0.0,
            "timeout_rate": 0.0,
            "throughput": throughput[name],
        }
        for name, block in performance["latency_percentiles"]["value"].items()
    }
    return {
        "schema_version": 1,
        "kind": "baseline",
        "key": key,
        "report": {
            "run_id": "323e4567-e89b-42d3-a456-426614174000",
            "sha256": "b" * 64,
            "started_at": "2026-10-01T12:00:00Z",
            "simulator_sha": report["source"]["simulator_sha"]["value"],
            "dependency_lock_sha256": report["source"]["runtime"][
                "dependency_lock_sha256"
            ]["value"],
            "backend": {
                "deployment_id": "423e4567-e89b-42d3-a456-426614174000",
                "source_sha": "0123456789abcdef0123456789abcdef01234567",
                "environment": "staging",
            },
            "execution": {"image_id": IMAGE, "platform": PLATFORM},
        },
        "metrics": metrics,
        "rationale": "Reviewed Staging reference run.",
        "supersedes": None,
    }


def companion_file(samples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    quiet = [
        {"cpu_percent": 40.0, "memory_percent": 10.0, "cpu_steal_ticks": 10},
        {"cpu_percent": 42.0, "memory_percent": 11.0, "cpu_steal_ticks": 20},
    ]
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "completed_at": 1_790_000_000.0,
        "evidence": {
            "schema_version": 1,
            "run_id": RUN_ID,
            "image_id": IMAGE,
            "platform": PLATFORM,
            "container_id": "c" * 64,
            "stop_reason": None,
            "hard_stop": False,
            "container_exit_code": 0,
            "recovery": "uncertain",
            "samples": quiet if samples is None else samples,
            "report_attribution": "matched",
        },
    }


def context_file() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "signals": dict.fromkeys(CONTEXT_SIGNALS, "observed_normal"),
    }


def sample(cpu: Any, memory: float | None, steal: int | None) -> dict[str, Any]:
    return {"cpu_percent": cpu, "memory_percent": memory, "cpu_steal_ticks": steal}


def as_schema_4(value: dict[str, Any]) -> None:
    """The historical shape `load_report` still accepts, as test_reports_v5 builds it."""
    value["schema_version"] = 4
    value["performance"] = {
        "duration_seconds": value["performance"]["duration_seconds"],
        "throughput": unavailable("not_implemented"),
        "latency_percentiles": unavailable("not_implemented"),
        "resource_context": unavailable(),
    }


def failed_run(value: dict[str, Any]) -> None:
    value["outcome"] = "failed"
    value["correctness"] = "failed"
    value["failure"] = {"stage": "simulation", "code": "FAIL_SIMULATION"}
    value["phases"]["simulation"]["status"] = "failed"


def stopped_failed_run(value: dict[str, Any]) -> None:
    failed_run(value)
    value["results"]["traffic"]["value"]["stop_reason"] = "generation"


def execution_mode(mode: str | None) -> Edit:
    def edit(value: dict[str, Any]) -> None:
        value["performance"]["execution_mode"] = (
            unavailable() if mode is None else {"value": mode, "reason": None}
        )

    return edit


def write(path: Path, value: object) -> Path:
    text = value if isinstance(value, str) else json.dumps(value, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
    return path


def _spec(spec: Any, default: dict[str, Any]) -> dict[str, Any] | str | None:
    if spec is DEFAULT:
        return default
    if callable(spec):
        edited = copy.deepcopy(default)
        spec(edited)
        return edited
    return spec  # None omits the file; a dict or raw text is written as given


def build(
    root: Path,
    *,
    report: Edit | None = None,
    thresholds: Any = DEFAULT,
    baseline: Any = DEFAULT,
    companion: Any = None,
    context: Any = None,
    mode: str | None = "container",
) -> Inputs:
    """Write one run's inputs; the files are matched to its comparable key."""
    scratch = root / "scratch"
    scratch.mkdir(parents=True)
    value = successful_report(scratch)
    execution_mode(mode)(value)
    reference = copy.deepcopy(value)  # a baseline is always a measured schema-5 run
    if report is not None:
        report(value)
    traffic = value["results"]["traffic"]["value"]
    mode_block = value["performance"].get("execution_mode")
    observed_mode = mode_block["value"] if mode_block else None
    context_key = (
        f"external_host:{PLATFORM}"
        if companion is not None and observed_mode == "container"
        else observed_mode or "unknown"
    )
    key = {
        "scenario_id": value["scenario"]["id"],
        "scenario_version": value["scenario"]["version"],
        "descriptor_digest": value["scenario"]["descriptor_digest"],
        "plan_digest": traffic["plan_digest"] if traffic else None,
        "environment": "staging",
        "execution_context": context_key,
    }
    run = root / "run"
    report_path = write(run / f"{value['run_id']}.json", value)
    baselines = root / "baselines"
    baselines.mkdir()
    for name, spec, default in (
        ("thresholds", thresholds, thresholds_file(key)),
        ("baseline", baseline, baseline_file(key, reference)),
    ):
        content = _spec(spec, default)
        if content is not None:
            write(baselines / f"fixture.{name}.json", content)
    optional: list[Path | None] = []
    for name, spec, default in (
        ("host.json", companion, companion_file()),
        ("context.json", context, context_file()),
    ):
        content = None if spec is None else _spec(spec, default)
        optional.append(None if content is None else write(run / name, content))
    return Inputs(report_path, baselines, optional[0], optional[1], key)
