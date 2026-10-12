"""Reviewed baseline promotion and read-only trend over archived runs (#229).

Promotion is the only writer under the baselines directory and is reached only
from the CLI entry point. It never trusts a supplied evaluation: it evaluates the
report itself, refuses unless the run is a clean Staging reference, and writes
nothing on refusal. Trend only reads. Neither echoes input content on failure.
"""

# pyright: reportPrivateUsage=false
import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from tailtag_simulator.evaluation import (
    BASELINE_SUFFIX,
    ERRORS,
    NAMES,
    RECORD_LIMIT,
    REPORT_LIMIT,
    THRESHOLDS_SUFFIX,
    EvaluationFailed,
    _companion,
    _comparable_key,
    _rate,
    _reading,
    _text,
    evaluate,
    parse_baseline,
    parse_thresholds,
)
from tailtag_simulator.reports import ReportFailed, validate_report

VERDICTS = ("acceptable", "breached", "regressed", "inconclusive", "not_evaluated")
PROMOTABLE_REASONS = {"no_baseline", "no_thresholds"}
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
TREND_FILES = 2000
TREND_DEPTH = 4
TREND_LIMIT = 1024 * 1024
RECORD_FIELDS = ("p50", "p95", "p99", "max")
COMPANION_FIELDS = {"schema_version", "run_id", "completed_at", "evidence"}


class PromotionFailed(Exception):
    """Refused promotion; carries no input details."""


def baseline_slug(key: Mapping[str, Any]) -> str:
    """The file stem shared by a key's baseline and thresholds records."""
    context = str(key["execution_context"]).replace("/", "-").replace(":", "-")
    slug = (
        f"{key['scenario_id']}-v{key['scenario_version']}-"
        f"{str(key['plan_digest'])[:12]}-{context}"
    )
    if SLUG.fullmatch(slug) is None:
        raise PromotionFailed
    return slug


def _metrics(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    performance = report["performance"]
    attempts = performance["attempts"]["value"]
    latency = performance["latency_percentiles"]["value"]
    throughput = performance["throughput"]["value"]
    return {
        name: {
            "samples": latency[name]["samples"],
            **{field: latency[name][field]["value"] for field in RECORD_FIELDS},
            "error_rate": _rate(attempts[name], ERRORS),
            "timeout_rate": _rate(attempts[name], ("timeout",)),
            "throughput": throughput[name],
        }
        for name in NAMES
    }


def _proposed(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    def entry(value: float, assumption: str) -> dict[str, Any]:
        return {"value": value, "assumption": assumption}

    def rate(observed: float | None) -> dict[str, Any]:
        return entry(
            max(2 * (observed or 0), 0.01),
            "Proposed: the greater of 2x the baseline rate and 0.01; maintainer to review.",
        )

    operations: dict[str, Any] = {}
    for name, row in metrics.items():
        samples = row["samples"]  # latency samples, as evaluation compares them
        limits: dict[str, Any] = {}
        for quantile, minimum in (("p95", 200), ("p99", 1000)):
            if samples >= minimum and row[quantile] is not None:
                limits[f"{quantile}_ms"] = entry(
                    math.ceil(2 * row[quantile]),
                    f"Proposed: 2x the baseline {quantile}, rounded up to 1 ms; "
                    "maintainer to review.",
                )
        if samples >= 200:
            limits["error_rate"] = rate(row["error_rate"])
            limits["timeout_rate"] = rate(row["timeout_rate"])
        if limits:
            operations[name] = limits
    return {
        "minimum_samples": {
            "p95": entry(200, "Proposed: minimum samples for a meaningful p95."),
            "p99": entry(1000, "Proposed: minimum samples for a meaningful p99."),
        },
        "operations": operations,
        "regression": {
            "p95_percent": entry(25, "Proposed: p95 may rise 25% over the baseline."),
            "p99_percent": entry(50, "Proposed: p99 may rise 50% over the baseline."),
            "minimum_delta_ms": entry(
                20, "Proposed: ignore regressions smaller than 20 ms."
            ),
        },
        "saturation": {
            "peak_cpu_percent": entry(
                160, "Proposed: 80% of 2 vCPUs in Docker CPUPerc units."
            ),
            "lag_seconds": entry(
                1.0, "Proposed: generator lag above 1 s is saturation."
            ),
            "steal_ticks_delta": entry(
                1500, "Proposed: CPU steal above 1500 USER_HZ ticks is saturation."
            ),
        },
    }


def _encode(value: Mapping[str, Any]) -> bytes:
    data = (
        json.dumps(value, indent=1, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    if len(data) > RECORD_LIMIT:
        raise PromotionFailed
    return data


def _stage(directory: Path, data: bytes) -> Path:
    """Write `data` to a private temp file beside its destination, mode 0644."""
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _promote(
    report_path: Path,
    rationale: str,
    baselines_dir: Path,
    host_companion: Path | None,
    context: Path | None,
    initial_thresholds: bool,
) -> Path:
    if not _text(rationale, 1000):
        raise PromotionFailed
    artifact = evaluate(
        report_path,
        host_companion=host_companion,
        context=context,
        baselines_dir=baselines_dir,
    )
    key = artifact["key"]
    subject = artifact["report"]
    reasons = set(artifact["reasons"])
    if (
        key is None
        or key["environment"] != "staging"
        or subject["schema_version"] != 5
        or subject["outcome"] != "passed"
        or subject["correctness"] != "passed"
        or not (
            artifact["verdict"] == "acceptable"
            or (artifact["verdict"] == "inconclusive" and reasons <= PROMOTABLE_REASONS)
        )
        or any(
            c["check"] in ("absolute", "regression")
            and c["result"] in ("breached", "regressed")
            for c in artifact["checks"]
        )
    ):
        raise PromotionFailed
    data, loaded = _reading(report_path, REPORT_LIMIT)
    if hashlib.sha256(data).hexdigest() != subject["sha256"]:
        raise PromotionFailed
    report = cast(dict[str, Any], validate_report(loaded))
    slug = baseline_slug(key)
    prior = artifact["baseline"]
    destination = baselines_dir / (slug + BASELINE_SUFFIX)
    if (prior is not None and prior["path"] != destination.name) or (
        prior is None and os.path.lexists(destination)
    ):
        raise PromotionFailed  # one record per key, under its canonical name
    thresholds_path = baselines_dir / (slug + THRESHOLDS_SUFFIX)
    if initial_thresholds and (
        artifact["thresholds"] is not None or os.path.lexists(thresholds_path)
    ):
        raise PromotionFailed
    metrics = _metrics(report)
    generator = artifact["generator"]
    backend = artifact["observation"]["backend"]
    record = {
        "schema_version": 1,
        "kind": "baseline",
        "key": key,
        "report": {
            "run_id": subject["run_id"],
            "sha256": subject["sha256"],
            "started_at": artifact["observation"]["started_at"],
            "simulator_sha": subject["simulator_sha"],
            "dependency_lock_sha256": subject["dependency_lock_sha256"],
            "backend": {
                name: backend[name]
                for name in ("deployment_id", "source_sha", "environment")
            },
            "execution": None
            if generator["status"] != "observed"
            else {
                "image_id": generator["image_id"],
                "platform": generator["platform"],
            },
        },
        "metrics": metrics,
        "rationale": rationale,
        "supersedes": None if prior is None else prior["report_sha256"],
    }
    parse_baseline(record)
    baseline_bytes = _encode(record)
    thresholds_bytes = None
    if initial_thresholds:
        proposed = {
            "schema_version": 1,
            "kind": "thresholds",
            "key": key,
            **_proposed(metrics),
        }
        if not proposed["operations"]:
            raise PromotionFailed  # nothing to bound: the proposal would be inert
        parse_thresholds(proposed)
        thresholds_bytes = _encode(proposed)

    baselines_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    linked: Path | None = None
    try:
        baseline_temp = _stage(baselines_dir, baseline_bytes)
        staged.append(baseline_temp)
        if thresholds_bytes is not None:
            thresholds_temp = _stage(baselines_dir, thresholds_bytes)
            staged.append(thresholds_temp)
            os.link(thresholds_temp, thresholds_path)  # exclusive: never replaces
            linked = thresholds_path
        os.replace(baseline_temp, destination)
        linked = None
    except BaseException:
        if linked is not None:
            linked.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
    return destination


def promote(
    report_path: Path,
    *,
    rationale: str,
    baselines_dir: Path,
    host_companion: Path | None = None,
    context: Path | None = None,
    initial_thresholds: bool = False,
) -> Path:
    """Write the reviewed baseline for a report's key; returns its path."""
    try:
        return _promote(
            report_path,
            rationale,
            baselines_dir,
            host_companion,
            context,
            initial_thresholds,
        )
    except (
        PromotionFailed,
        EvaluationFailed,
        ReportFailed,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        OverflowError,
    ):
        raise PromotionFailed from None


def _files(directory: Path) -> tuple[list[Path], int]:
    """JSON files within the bounds, in stable order, and the count beyond them."""
    if not directory.is_dir():
        raise NotADirectoryError
    inside: list[Path] = []
    beyond = 0
    for root, folders, names in os.walk(directory):
        folders.sort()
        depth = len(Path(root).relative_to(directory).parts)
        for name in sorted(names):
            path = Path(root) / name
            if not name.endswith(".json"):
                continue
            if (
                depth > TREND_DEPTH
                or len(inside) >= TREND_FILES
                or path.is_symlink()
                or not path.is_file()
            ):
                beyond += 1
            else:
                inside.append(path)
    return inside, beyond


def _evaluation(artifact: dict[str, Any]) -> dict[str, Any]:
    """The few fields trend relies on; other content is not interpreted."""
    report = artifact["report"]
    if (
        artifact["schema_version"] != 1
        or artifact["verdict"] not in VERDICTS
        or not isinstance(artifact["evaluated_at"], str)
        or not isinstance(report["sha256"], str)
        or not isinstance(report["run_id"], str)
    ):
        raise ReportFailed
    return artifact


def _active_baselines(baselines_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if baselines_dir.is_dir():
        for path in sorted(baselines_dir.glob("*" + BASELINE_SUFFIX)):
            try:
                records.append(parse_baseline(_reading(path, RECORD_LIMIT)[1]))
            except (ReportFailed, OSError, ValueError):
                continue
    return records


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _row(report: Mapping[str, Any], verdict: str | None, mark: str) -> str:
    starting = report["target"]["starting"]["value"]
    sha = None if starting is None else starting.get("source_sha")
    source = sha[:12] if isinstance(sha, str) and sha else "-"
    metrics = "-"
    rates = "-"
    if report["schema_version"] == 5:
        performance = report["performance"]
        latency = performance["latency_percentiles"]["value"]
        attempts = performance["attempts"]["value"]
        metrics = " ".join(
            f"{name}:{_ms(latency[name]['p95']['value'])}/{_ms(latency[name]['p99']['value'])}"
            for name in NAMES
            if latency[name]["samples"] > 0
        )
        error, timeout = (
            _rate(attempts["total"], ERRORS),
            _rate(attempts["total"], ("timeout",)),
        )
        rates = " ".join(
            f"{label}={'-' if rate is None else f'{rate:.4f}'}"
            for label, rate in (("err", error), ("timeout", timeout))
        )
    return (
        f"{mark} {report['timing']['started_at']} {report['run_id']} {source} "
        f"{report['correctness']} {verdict or '-'} "
        f"p95/p99_ms {metrics or '-'} {rates}"
    )


def trend(directory: Path, *, baselines_dir: Path) -> list[str]:
    """Time-ordered tables per comparable key, ending with `skipped <n>`; never writes."""
    files, skipped = _files(directory)
    reports: dict[str, dict[str, Any]] = {}
    evaluations: list[dict[str, Any]] = []
    companions: dict[str, list[Any]] = {}
    for path in files:
        try:
            data, value = _reading(path, TREND_LIMIT)
            document = cast(dict[str, Any], value) if isinstance(value, dict) else {}
            if document.get("kind") == "evaluation":
                evaluations.append(_evaluation(document))
            elif set(document) == COMPANION_FIELDS:
                companions.setdefault(str(document["run_id"]), []).append(document)
            else:
                report = cast(dict[str, Any], validate_report(cast(object, value)))
                if report["schema_version"] not in (4, 5):
                    raise ReportFailed
                reports.setdefault(hashlib.sha256(data).hexdigest(), report)
        except (
            ReportFailed,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RecursionError,
            OverflowError,
        ):
            skipped += 1

    baselines = _active_baselines(baselines_dir)
    groups: dict[str, list[tuple[Mapping[str, Any], str | None, str]]] = {}
    headers: dict[str, str] = {}
    for digest, report in reports.items():
        run_id = report["run_id"]
        host = None
        for candidate in companions.get(run_id, []):
            try:
                host = _companion(candidate, run_id)
                break
            except (ReportFailed, KeyError, TypeError):
                continue
        traffic = report["results"].get("traffic", {}).get("value")
        measured = report["schema_version"] == 5
        mode = report["performance"]["execution_mode"]["value"] if measured else None
        key = _comparable_key(report, traffic, mode, host)
        if key is None:
            skipped += 1
            continue
        matching = [
            e
            for e in evaluations
            if e["report"]["run_id"] == run_id and e["report"]["sha256"] == digest
        ]
        verdict = (
            max(matching, key=lambda e: e["evaluated_at"])["verdict"]
            if matching
            else None
        )
        active = any(
            b["key"] == key and b["report"]["sha256"] == digest for b in baselines
        )
        label = json.dumps(key, sort_keys=True)
        headers[label] = (
            f"key {key['scenario_id']} v{key['scenario_version']} "
            f"plan {key['plan_digest'][:12]} {key['environment']} "
            f"{key['execution_context']}"
        )
        groups.setdefault(label, []).append((report, verdict, "*" if active else " "))

    lines: list[str] = []
    for label in sorted(groups):
        lines.append(headers[label])
        lines.append("  started_at run_id source correctness verdict metrics rates")
        for report, verdict, mark in sorted(
            groups[label], key=lambda r: (r[0]["timing"]["started_at"], r[0]["run_id"])
        ):
            lines.append(_row(report, verdict, mark))
    lines.append(f"skipped {skipped}")
    return lines
