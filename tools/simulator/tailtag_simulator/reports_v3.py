"""Closed observed traffic evidence; lifecycle validation stays in reports."""

from typing import Any, cast

from tailtag_simulator import reports_v2

COUNTERS = {
    "offered",
    "admitted",
    "skipped",
    "completed",
    "active_peak",
    "in_flight_peak",
    "attempts",
    "sent",
    "injected",
    "transient",
    "retries",
    "expected_rejections",
    "exhausted",
    "unresolved",
}
TIMES = {"generation_seconds", "drain_seconds", "lag_seconds"}
BUCKET_COUNTS = {"offered", "admitted", "skipped", "completed"}


def profile(descriptor: dict[str, Any], config: dict[str, Any]) -> dict[str, object]:
    return {
        "operations": descriptor["operations"],
        **{k: config[k] for k in ("traffic", "failure", "retry")},
    }


def limits(existing: dict[str, object], config: dict[str, Any]) -> dict[str, object]:
    definitions = {
        "request_ceiling": ("attempts", "attempts", "simulation"),
        "duration_ceiling": ("generation_seconds", "seconds", "generation"),
        "concurrency_ceiling": ("in_flight", "requests", "simulation"),
        "active_ceiling": ("active", "actors", "simulation"),
        "drain_ceiling": ("drain_seconds", "seconds", "drain"),
    }
    return {
        **existing,
        **{
            key: {
                "value": config["limits"][name],
                "reason": None,
                "unit": unit,
                "scope": scope,
            }
            for key, (name, unit, scope) in definitions.items()
        },
    }


def results(
    value: object, config: dict[str, Any], *, successful: bool, correct: bool
) -> None:
    from tailtag_simulator.reports import (
        CHECKS,
        _count,  # pyright: ignore[reportPrivateUsage]
        _hex,  # pyright: ignore[reportPrivateUsage]
        _number,  # pyright: ignore[reportPrivateUsage]
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
    )

    result = _object(value, {"behavior", "checks", "cleanup", "traffic"})
    reports_v2.results(
        {k: result[k] for k in ("behavior", "checks", "cleanup")},
        config,
        successful=False,
    )
    if correct:
        _require(
            result["checks"] == {"items": [], "count": len(CHECKS), "reason": None}
        )
    measurement = _object(result["traffic"], {"value", "reason"})
    if measurement["value"] is None:
        _require(measurement["reason"] == "not_observed" and not successful)
        return
    _require(measurement["reason"] is None)
    snapshot = _object(
        measurement["value"],
        COUNTERS | TIMES | {"plan_digest", "stop_reason", "buckets"},
    )
    _require(
        _hex(snapshot["plan_digest"], 64)
        and all(_count(snapshot[k]) for k in COUNTERS)
        and all(_number(snapshot[k]) for k in TIMES)
    )
    _require(
        snapshot["stop_reason"]
        in (
            None,
            "attempts",
            "generation",
            "drain",
            "external",
            "correctness",
            "entries",
        )
    )
    _require(
        snapshot["offered"] == snapshot["admitted"] + snapshot["skipped"]
        and snapshot["completed"] <= snapshot["admitted"]
        and snapshot["sent"] <= snapshot["attempts"]
    )
    for key, ceiling in (
        ("active_peak", "active"),
        ("in_flight_peak", "in_flight"),
        ("attempts", "attempts"),
    ):
        _require(snapshot[key] <= config["limits"][ceiling])
    raw_buckets = snapshot["buckets"]
    _require(
        isinstance(raw_buckets, list) and len(cast(list[object], raw_buckets)) <= 1000
    )
    totals = dict.fromkeys(BUCKET_COUNTS, 0)
    previous = -1.0
    width = config["traffic"]["bucket_seconds"]
    duration = sum(
        segment["duration_seconds"] for segment in config["traffic"]["segments"]
    )
    for raw in cast(list[object], raw_buckets):
        bucket = _object(raw, BUCKET_COUNTS | {"at_seconds"})
        at = bucket["at_seconds"]
        _require(
            _number(at)
            and previous < at < duration
            and abs(at / width - round(at / width)) < 1e-9
        )
        previous = at
        _require(all(_count(bucket[k]) for k in BUCKET_COUNTS))
        _require(
            bucket["offered"] == bucket["admitted"] + bucket["skipped"]
            and bucket["completed"] <= bucket["admitted"]
        )
        for key in totals:
            totals[key] += bucket[key]
    _require(all(totals[k] == snapshot[k] for k in totals))
    if successful:
        _require(
            snapshot["stop_reason"] is None
            and snapshot["unresolved"] == snapshot["exhausted"] == 0
            and snapshot["completed"] == snapshot["admitted"]
        )
        _require(
            result["behavior"]["reason"] is None
            and result["behavior"]["failure"] is None
        )
