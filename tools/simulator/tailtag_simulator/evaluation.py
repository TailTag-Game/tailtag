"""Offline, read-only evaluation of one schema-4/5 run report (#229).

Judgment lives here, never in the report: an evaluation reads an immutable
report plus versioned threshold and baseline records and returns a separate
artifact. Every input is strictly validated and bounded; nothing is echoed back
on refusal, and no network request is made.
"""

# pyright: reportPrivateUsage=false
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from tailtag_simulator import reports
from tailtag_simulator.reports import ReportFailed, utc_now, validate_report
from tailtag_simulator.traffic_metrics import OPERATIONS

count = reports._count
hex_digest = reports._hex
number = reports._number
closed_object = reports._object
no_duplicates = reports._pairs
require = reports._require
timestamp = reports._timestamp
uuid_text = reports._uuid

REPORT_LIMIT = 1024 * 1024
RECORD_LIMIT = 64 * 1024
NAMES = (*OPERATIONS, "total")
ERRORS = ("client_error", "server_error", "transport_error")
LIMITS = ("p95_ms", "p99_ms", "error_rate", "timeout_rate")
SATURATION = ("peak_cpu_percent", "lag_seconds", "steal_ticks_delta")
SIGNALS = (
    "http_5xx",
    "server_latency",
    "db_connections",
    "worker_timeouts",
    "restarts_or_oom",
    "runtime_resources",
    "domain_outcomes",
)
OBSERVATIONS = ("observed_normal", "observed_pressure", "not_observed")
STATEMENT = (
    "Thresholds and baselines are documented assumptions for regression "
    "evidence; they are not production SLOs or capacity claims."
)
THRESHOLDS_SUFFIX = ".thresholds.json"
BASELINE_SUFFIX = ".baseline.json"


class EvaluationFailed(Exception):
    """Refused evaluation or output; carries no input details."""


def _text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and value.isprintable()


def _image(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and hex_digest(value[7:], 64)
    )


def _platform(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-z0-9_]+(/[a-z0-9_.]+){1,2}", value) is not None
    )


def _reading(path: Path, limit: int) -> tuple[bytes, Any]:
    """Read at most `limit` bytes once, rejecting duplicate keys and constants."""
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit)
    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=no_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(ReportFailed()),
    )
    return data, value


def _key(value: object) -> dict[str, Any]:
    key = closed_object(
        value,
        {
            "scenario_id",
            "scenario_version",
            "descriptor_digest",
            "plan_digest",
            "environment",
            "execution_context",
        },
    )
    require(_text(key["scenario_id"], 64) and count(key["scenario_version"], 1000))
    require(hex_digest(key["descriptor_digest"], 64))
    require(hex_digest(key["plan_digest"], 64))
    require(key["environment"] in ("staging", "local"))
    require(_text(key["execution_context"], 64))
    return key


def _limit(value: object) -> float:
    entry = closed_object(value, {"value", "assumption"})
    require(number(entry["value"]) and _text(entry["assumption"], 500))
    return cast(float, entry["value"])


def parse_thresholds(value: object) -> dict[str, Any]:
    """Validate a threshold file's content; raises `ReportFailed`."""
    thresholds = closed_object(
        value,
        {
            "schema_version",
            "kind",
            "key",
            "minimum_samples",
            "operations",
            "regression",
            "saturation",
        },
    )
    require(thresholds["schema_version"] == 1 and thresholds["kind"] == "thresholds")
    require(type(thresholds["schema_version"]) is int)
    _key(thresholds["key"])
    for name in closed_object(thresholds["minimum_samples"], {"p95", "p99"}).values():
        _limit(name)
    operations = thresholds["operations"]
    require(isinstance(operations, dict))
    for name, limits in cast(dict[str, Any], operations).items():
        require(name in NAMES and isinstance(limits, dict))
        require(set(cast(dict[str, Any], limits)) <= set(LIMITS))
        for entry in cast(dict[str, Any], limits).values():
            _limit(entry)
    for entry in closed_object(
        thresholds["regression"], {"p95_percent", "p99_percent", "minimum_delta_ms"}
    ).values():
        _limit(entry)
    for entry in closed_object(thresholds["saturation"], set(SATURATION)).values():
        _limit(entry)
    return thresholds


def parse_baseline(value: object) -> dict[str, Any]:
    """Validate a baseline record's content (the U3 record shape); raises `ReportFailed`."""
    baseline = closed_object(
        value,
        {
            "schema_version",
            "kind",
            "key",
            "report",
            "metrics",
            "rationale",
            "supersedes",
        },
    )
    require(baseline["schema_version"] == 1 and baseline["kind"] == "baseline")
    require(type(baseline["schema_version"]) is int)
    _key(baseline["key"])
    report = closed_object(
        baseline["report"],
        {
            "run_id",
            "sha256",
            "started_at",
            "simulator_sha",
            "dependency_lock_sha256",
            "backend",
            "execution",
        },
    )
    require(uuid_text(report["run_id"]) and hex_digest(report["sha256"], 64))
    require(timestamp(report["started_at"]))
    require(hex_digest(report["simulator_sha"], 40))
    require(hex_digest(report["dependency_lock_sha256"], 64))
    backend = closed_object(
        report["backend"], {"deployment_id", "source_sha", "environment"}
    )
    require(uuid_text(backend["deployment_id"]))
    require(
        hex_digest(backend["source_sha"], 40) and backend["environment"] == "staging"
    )
    if report["execution"] is not None:
        execution = closed_object(report["execution"], {"image_id", "platform"})
        require(_image(execution["image_id"]) and _platform(execution["platform"]))
    metrics = baseline["metrics"]
    require(isinstance(metrics, dict) and len(cast(dict[str, Any], metrics)) > 0)
    for name, row in cast(dict[str, Any], metrics).items():
        require(name in NAMES)
        fields = closed_object(
            row,
            {
                "samples",
                "p50",
                "p95",
                "p99",
                "max",
                "error_rate",
                "timeout_rate",
                "throughput",
            },
        )
        require(count(fields["samples"]))
        require(
            all(v is None or number(v) for k, v in fields.items() if k != "samples")
        )
        require(
            all(
                fields[rate] is None or fields[rate] <= 1
                for rate in ("error_rate", "timeout_rate")
            )
        )
    require(_text(baseline["rationale"], 1000))
    require(baseline["supersedes"] is None or hex_digest(baseline["supersedes"], 64))
    return baseline


def _context(value: object, run_id: str) -> dict[str, str]:
    context = closed_object(value, {"schema_version", "run_id", "signals"})
    require(type(context["schema_version"]) is int and context["schema_version"] == 1)
    require(context["run_id"] == run_id)
    signals = closed_object(context["signals"], set(SIGNALS))
    require(all(v in OBSERVATIONS for v in signals.values()))
    return {name: signals[name] for name in SIGNALS}


def _companion(value: object, run_id: str) -> dict[str, Any]:
    companion = closed_object(
        value, {"schema_version", "run_id", "completed_at", "evidence"}
    )
    require(type(companion["schema_version"]) is int)
    require(companion["schema_version"] == 1 and companion["run_id"] == run_id)
    require(number(companion["completed_at"]))
    evidence = closed_object(
        companion["evidence"],
        {
            "schema_version",
            "run_id",
            "image_id",
            "platform",
            "container_id",
            "stop_reason",
            "hard_stop",
            "container_exit_code",
            "recovery",
            "samples",
            "report_attribution",
        },
    )
    require(type(evidence["schema_version"]) is int and evidence["schema_version"] == 1)
    require(evidence["run_id"] == run_id)
    require(_image(evidence["image_id"]) and _platform(evidence["platform"]))
    require(hex_digest(evidence["container_id"], 64))
    require(evidence["stop_reason"] is None or _text(evidence["stop_reason"], 64))
    require(type(evidence["hard_stop"]) is bool)
    code = evidence["container_exit_code"]
    require(type(code) is int and -255 <= code <= 255)
    require(_text(evidence["recovery"], 64))
    require(evidence["report_attribution"] in ("matched", "mismatched", "unavailable"))
    samples = evidence["samples"]
    require(isinstance(samples, list) and len(cast(list[Any], samples)) <= 301)
    for each in cast(list[Any], samples):
        row = closed_object(each, {"cpu_percent", "memory_percent", "cpu_steal_ticks"})
        require(row["cpu_percent"] is None or number(row["cpu_percent"]))
        require(row["memory_percent"] is None or number(row["memory_percent"]))
        require(
            row["cpu_steal_ticks"] is None or count(row["cpu_steal_ticks"], 2**63 - 1)
        )
    return evidence


def _peak(samples: list[dict[str, Any]], field: str) -> float | None:
    values = [s[field] for s in samples if s[field] is not None]
    return max(values) if values else None


def _generator(
    evidence: dict[str, Any] | None, traffic: Mapping[str, Any] | None
) -> dict[str, Any]:
    generator: dict[str, Any] = {
        "status": "not_observed",
        "samples": None,
        "peak_cpu_percent": None,
        "peak_memory_percent": None,
        "steal_ticks_delta": None,
        "lag_seconds": None if traffic is None else traffic["lag_seconds"],
        "image_id": None,
        "platform": None,
    }
    if evidence is not None:
        samples = cast(list[dict[str, Any]], evidence["samples"])
        steal = [
            s["cpu_steal_ticks"] for s in samples if s["cpu_steal_ticks"] is not None
        ]
        generator.update(
            status="observed",
            samples=len(samples),
            peak_cpu_percent=_peak(samples, "cpu_percent"),
            peak_memory_percent=_peak(samples, "memory_percent"),
            steal_ticks_delta=steal[-1] - steal[0] if len(steal) > 1 else None,
            image_id=evidence["image_id"],
            platform=evidence["platform"],
        )
    return generator


def _rate(counts: Mapping[str, int], classes: tuple[str, ...]) -> float | None:
    denominator = sum(counts.values()) - counts["injected"]
    return sum(counts[c] for c in classes) / denominator if denominator else None


def _observed_rows(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Per operation: samples, percentiles and rates from a schema-5 report."""
    performance = report["performance"]
    attempts = performance["attempts"]["value"]
    latency = performance["latency_percentiles"]["value"]
    return {
        name: {
            "samples": latency[name]["samples"],
            "p95_ms": latency[name]["p95"]["value"],
            "p99_ms": latency[name]["p99"]["value"],
            "error_rate": _rate(attempts[name], ERRORS),
            "timeout_rate": _rate(attempts[name], ("timeout",)),
        }
        for name in NAMES
    }


def _check(
    kind: str,
    operation: str | None,
    metric: str,
    observed: float | None,
    limit: float,
    baseline: float | None,
    result: str,
) -> dict[str, Any]:
    return {
        "check": kind,
        "operation": operation,
        "metric": metric,
        "observed": observed,
        "limit": limit,
        "baseline": baseline,
        "result": result,
    }


def _absolute(
    rows: Mapping[str, Mapping[str, Any]], thresholds: Mapping[str, Any]
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    minimum = {
        "p95_ms": thresholds["minimum_samples"]["p95"]["value"],
        "p99_ms": thresholds["minimum_samples"]["p99"]["value"],
    }
    for name in NAMES:
        for metric in LIMITS:
            entry = thresholds["operations"].get(name, {}).get(metric)
            if entry is None:
                continue
            row, limit = rows[name], entry["value"]
            observed = row[metric]
            if observed is None or (
                metric in minimum and row["samples"] < minimum[metric]
            ):
                result = "inconclusive"
            else:
                result = "breached" if observed > limit else "passed"
            checks.append(
                _check("absolute", name, metric, observed, limit, None, result)
            )
    return checks


def _regression(
    rows: Mapping[str, Mapping[str, Any]],
    baseline: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    settings = thresholds["regression"]
    delta = settings["minimum_delta_ms"]["value"]
    for name in NAMES:
        reference = baseline["metrics"].get(name)
        if reference is None:
            continue
        for quantile in ("p95", "p99"):
            metric = f"{quantile}_ms"
            if metric not in thresholds["operations"].get(name, {}):
                continue
            observed, before = rows[name][metric], reference[quantile]
            if observed is None or before is None:
                continue
            limit = before * (1 + settings[f"{quantile}_percent"]["value"] / 100)
            minimum = thresholds["minimum_samples"][quantile]["value"]
            if min(rows[name]["samples"], reference["samples"]) < minimum:
                result = "inconclusive"
            elif observed > limit and observed - before >= delta:
                result = "regressed"
            else:
                result = "passed"
            checks.append(
                _check("regression", name, metric, observed, limit, before, result)
            )
    return checks


def _saturation(
    generator: Mapping[str, Any], thresholds: Mapping[str, Any]
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for metric in SATURATION:
        observed = generator[metric]
        if observed is None:
            continue
        limit = thresholds["saturation"][metric]["value"]
        result = "breached" if observed > limit else "passed"
        checks.append(_check("saturation", None, metric, observed, limit, None, result))
    return checks


def _discover(
    baselines_dir: Path, key: dict[str, Any]
) -> tuple[tuple[Path, bytes, dict[str, Any]] | None, ...]:
    """Find the one threshold and baseline file for `key`; every such file must validate."""
    found: list[list[tuple[Path, bytes, dict[str, Any]]]] = [[], []]
    if baselines_dir.is_dir():
        for path in sorted(baselines_dir.iterdir()):
            for matches, suffix, parse in (
                (found[0], THRESHOLDS_SUFFIX, parse_thresholds),
                (found[1], BASELINE_SUFFIX, parse_baseline),
            ):
                if not path.name.endswith(suffix):
                    continue
                require(path.is_file() and not path.is_symlink())
                data, value = _reading(path, RECORD_LIMIT)
                parsed = parse(value)
                if parsed["key"] == key:
                    matches.append((path, data, parsed))
    require(all(len(matches) <= 1 for matches in found))
    return tuple(matches[0] if matches else None for matches in found)


def _comparable_key(
    report: Mapping[str, Any],
    traffic: Mapping[str, Any] | None,
    mode: str | None,
    host: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if traffic is None:
        return None
    target = report["target"]
    identity = target["starting"]["value"]
    if target["name"] == "staging":
        environment = None if identity is None else identity["environment"]
    else:
        environment = "local"
    if environment is None:
        return None
    if host is not None and mode == "container":
        context = f"external_host:{host['platform']}"
    else:
        context = mode or "unknown"
    return {
        "scenario_id": report["scenario"]["id"],
        "scenario_version": report["scenario"]["version"],
        "descriptor_digest": report["scenario"]["descriptor_digest"],
        "plan_digest": traffic["plan_digest"],
        "environment": environment,
        "execution_context": context,
    }


def _caveats(
    report: Mapping[str, Any], baseline: Mapping[str, Any], image_id: str | None
) -> list[str]:
    recorded = baseline["report"]
    caveats: list[str] = []
    if report["source"]["simulator_sha"]["value"] != recorded["simulator_sha"]:
        caveats.append("simulator_sha_differs")
    runtime = report["source"]["runtime"]["dependency_lock_sha256"]["value"]
    if runtime != recorded["dependency_lock_sha256"]:
        caveats.append("dependency_lock_differs")
    execution = recorded["execution"]
    if (
        image_id is not None
        and execution is not None
        and execution["image_id"] != image_id
    ):
        caveats.append("image_differs")
    return sorted(caveats)


def _evaluate(
    report_path: Path,
    host_companion: Path | None,
    context: Path | None,
    baselines_dir: Path,
) -> dict[str, Any]:
    data, loaded = _reading(report_path, REPORT_LIMIT)
    report = cast(dict[str, Any], validate_report(loaded))
    require(report["schema_version"] in (4, 5))
    run_id = report["run_id"]
    evidence = (
        None
        if host_companion is None
        else _companion(_reading(host_companion, RECORD_LIMIT)[1], run_id)
    )
    signals = (
        None
        if context is None
        else _context(_reading(context, RECORD_LIMIT)[1], run_id)
    )
    measured = report["schema_version"] == 5
    performance = report["performance"]
    traffic = report["results"].get("traffic", {}).get("value")
    mode = performance["execution_mode"]["value"] if measured else None
    key = _comparable_key(report, traffic, mode, evidence)
    generator = _generator(evidence, traffic)
    window = performance["window_seconds"]["value"] if measured else None
    starting = report["target"]["starting"]["value"]

    reasons: set[str] = set()
    for condition, reason in (
        (report["outcome"] != "passed", "run_not_passed"),
        (report["correctness"] != "passed", "correctness_not_passed"),
        (not measured, "performance_not_measured"),
        (
            evidence is not None
            and (
                evidence["stop_reason"] is not None
                or evidence["hard_stop"]
                or evidence["container_exit_code"] != 0
                or evidence["report_attribution"] != "matched"
            ),
            "host_run_not_passed",
        ),
    ):
        if condition:
            reasons.add(reason)
    evaluated = not reasons
    thresholds = baseline = None
    checks: list[dict[str, Any]] = []
    caveats: list[str] = []
    if evaluated:
        if traffic is not None and traffic["stop_reason"] is not None:
            reasons.add("traffic_stopped")
        if key is None:
            reasons.add("not_comparable")
        else:
            thresholds, baseline = _discover(baselines_dir, key)
            reasons.update(
                reason
                for found, reason in (
                    (thresholds, "no_thresholds"),
                    (baseline, "no_baseline"),
                )
                if found is None
            )
        if thresholds is not None:
            rows = _observed_rows(report)
            limits = thresholds[2]
            checks += _absolute(rows, limits)
            if baseline is not None:
                checks += _regression(rows, baseline[2], limits)
            checks += _saturation(generator, limits)
        if baseline is not None:
            caveats = _caveats(report, baseline[2], generator["image_id"])
        results = {(c["check"], c["result"]) for c in checks}
        if ("saturation", "breached") in results:
            reasons.add("generator_saturated")
        if any(c["result"] == "inconclusive" for c in checks):
            reasons.add("insufficient_samples")
    if not evaluated:
        verdict = "not_evaluated"
    elif reasons:
        verdict = "inconclusive"
    elif any(c["check"] == "absolute" and c["result"] == "breached" for c in checks):
        verdict = "breached"
    elif any(c["result"] == "regressed" for c in checks):
        verdict = "regressed"
    else:
        verdict = "acceptable"
    return {
        "schema_version": 1,
        "kind": "evaluation",
        "evaluated_at": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "report": {
            "run_id": run_id,
            "sha256": hashlib.sha256(data).hexdigest(),
            "schema_version": report["schema_version"],
            "scenario_id": report["scenario"]["id"],
            "scenario_version": report["scenario"]["version"],
            "outcome": report["outcome"],
            "correctness": report["correctness"],
            "simulator_sha": report["source"]["simulator_sha"]["value"],
            "dependency_lock_sha256": report["source"]["runtime"][
                "dependency_lock_sha256"
            ]["value"],
        },
        "key": key,
        "observation": {
            "started_at": report["timing"]["started_at"],
            "ended_at": report["timing"]["ended_at"]["value"],
            "window_seconds": window,
            "backend": starting,
        },
        "thresholds": None
        if thresholds is None
        else {
            "path": thresholds[0].name,
            "sha256": hashlib.sha256(thresholds[1]).hexdigest(),
        },
        "baseline": None
        if baseline is None
        else {
            "path": baseline[0].name,
            "report_sha256": baseline[2]["report"]["sha256"],
        },
        "generator": generator,
        "backend_context": signals,
        "checks": checks,
        "caveats": caveats,
        "verdict": verdict,
        "reasons": sorted(reasons)
        if verdict in ("not_evaluated", "inconclusive")
        else [],
        "statement": STATEMENT,
    }


def evaluate(
    report_path: Path,
    *,
    host_companion: Path | None = None,
    context: Path | None = None,
    baselines_dir: Path,
) -> dict[str, Any]:
    """Evaluate one report against committed thresholds and baselines; read-only."""
    try:
        return _evaluate(report_path, host_companion, context, baselines_dir)
    except (
        ReportFailed,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        OverflowError,
    ):
        raise EvaluationFailed from None


def default_output(report_path: Path, artifact: Mapping[str, Any]) -> Path:
    stamp = str(artifact["evaluated_at"]).replace("-", "").replace(":", "")
    return (
        report_path.parent / f"{artifact['report']['run_id']}.evaluation-{stamp}.json"
    )


def write_evaluation(artifact: Mapping[str, Any], out: Path) -> None:
    """Create `out` privately and exclusively; an existing file is never replaced."""
    created = False
    try:
        text = json.dumps(artifact, indent=1, allow_nan=False) + "\n"
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, TypeError):
        if created:
            out.unlink(missing_ok=True)
        raise EvaluationFailed from None


def summary(artifact: Mapping[str, Any]) -> list[str]:
    """Bounded fixed-format lines; every value is a closed token or a count."""
    tally = {
        result: sum(1 for c in artifact["checks"] if c["result"] == result)
        for result in ("passed", "breached", "regressed", "inconclusive")
    }
    listing: Callable[[list[str]], str] = lambda items: ",".join(items) or "-"
    return [
        f"reasons {listing(artifact['reasons'])}",
        f"caveats {listing(artifact['caveats'])}",
        "checks " + " ".join(f"{name}={count}" for name, count in tally.items()),
    ]
