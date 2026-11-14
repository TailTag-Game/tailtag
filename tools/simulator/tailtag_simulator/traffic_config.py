"""Closed convention traffic assumptions, validated before external work."""

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from tailtag_simulator.behavior_config import (
    DEFAULTS,
    PERSONAS,
    resolve_behavior_config,
)

BUCKET_TOLERANCE = 1e-9


def _invalid() -> ValueError:
    return ValueError("invalid traffic configuration")


def traffic_bucket_count(duration: float, width: float) -> int:
    """Keep decimal boundary noise from adding an empty terminal bucket."""
    ratio = duration / width
    if not math.isfinite(ratio):
        raise _invalid()
    return max(1, math.ceil(ratio - BUCKET_TOLERANCE))


def _number(value: object, low: float, high: float, *, integer: bool = False) -> float:
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise _invalid()
    try:
        number = float(cast(int | float, value))
    except OverflowError:
        raise _invalid() from None
    if not math.isfinite(number) or not low <= number <= high:
        raise _invalid()
    return number


def _section(value: object, defaults: dict[str, object]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid()
    supplied = cast(dict[str, object], value)
    if set(supplied) - set(defaults):
        raise _invalid()
    return deepcopy({**defaults, **supplied})


# v2 names stay frozen: archived schema 5 reports re-resolve through them.
V2_FAILURE_OPERATIONS = ("read", "resolve", "confirm")
V2_DOMAIN_CASES = ("none", "stale", "stopped", "expired")
# The catch request flow (#508): scenario version 3.
V3_FAILURE_OPERATIONS = ("read", "preview", "submit")
V3_DOMAIN_CASES = ("none", "replaced", "stopped", "expired")
# inspect-population-v2 caps catches and requests at 120 per run.
V3_MAXIMUM_REQUESTS = 120
# The contract's per-player limit: 30 created requests in a rolling 10 minutes.
# The load model plans no 429, so no attendee may plan more than that.
V3_PER_PLAYER_REQUESTS = 30
REVIEW_DEFAULTS: dict[str, object] = {
    "automatic_share": 0.25,
    "delay_min_seconds": 5,
    "delay_max_seconds": 30,
    "approve_rate": 0.85,
    "poll_seconds": 2,
}


def resolve_traffic_config(config: Mapping[str, object]) -> dict[str, object]:
    """Resolve a scenario version 2 configuration (the retired v1 catch path)."""
    return _resolve(config, V2_FAILURE_OPERATIONS, V2_DOMAIN_CASES)


def resolve_request_traffic_config(config: Mapping[str, object]) -> dict[str, object]:
    """Resolve a scenario version 3 configuration (the catch request flow)."""
    if not isinstance(config.get("review", {}), dict):
        raise _invalid()
    review = _section(config.get("review", {}), REVIEW_DEFAULTS)
    result = _resolve(
        {k: v for k, v in config.items() if k != "review"},
        V3_FAILURE_OPERATIONS,
        V3_DOMAIN_CASES,
    )
    for key in ("automatic_share", "approve_rate"):
        _number(review[key], 0, 1)
    low = _number(review["delay_min_seconds"], 0, 3600)
    high = _number(review["delay_max_seconds"], 0, 3600)
    if low > high or _number(review["poll_seconds"], 0, 60) == 0:
        raise _invalid()
    if (
        _planned_requests(result) > V3_MAXIMUM_REQUESTS
        or _most_per_attendee(result) > V3_PER_PLAYER_REQUESTS
    ):
        raise _invalid()
    result["review"] = review
    return result


def _targets(config: Mapping[str, object]) -> int:
    owners = cast(int, config["normal_owners"]) + cast(int, config["popular_owners"])
    return (
        1 if config["family"] == "hotspot" else owners * cast(int, config["fursuits"])
    )


def _most_per_attendee(config: Mapping[str, object]) -> int:
    """The most distinct suits any one attendee plans to request."""
    targets = _targets(config)
    return max(
        (
            min(cast(int, config[f"{prefix}_budget"]), targets)
            for persona, prefix in zip(
                PERSONAS[:4], ("casual", "active", "heavy", "retry"), strict=True
            )
            if cast(int, config[persona]) > 0
        ),
        default=0,
    )


def _planned_requests(config: Mapping[str, object]) -> int:
    owners = cast(int, config["normal_owners"]) + cast(int, config["popular_owners"])
    targets = (
        1 if config["family"] == "hotspot" else owners * cast(int, config["fursuits"])
    )
    return sum(
        cast(int, config[persona]) * min(cast(int, config[f"{prefix}_budget"]), targets)
        for persona, prefix in zip(
            PERSONAS[:4], ("casual", "active", "heavy", "retry"), strict=True
        )
    )


def _resolve(
    config: Mapping[str, object],
    failure_operations: tuple[str, ...],
    domain_cases: tuple[str, ...],
) -> dict[str, object]:
    nested = {"traffic", "failure", "retry", "limits"}
    result = resolve_behavior_config(
        {k: v for k, v in config.items() if k not in nested}
    )
    attendees = sum(cast(int, result[k]) for k in PERSONAS[:4])
    family = result["family"]
    compatibility = {
        key: DEFAULTS[key]
        for key in (
            "activation_break",
            "casual_history",
            "active_history",
            "heavy_history",
            "retry_history",
        )
    }
    compatibility["cycles"] = 3 if family == "soak" else 1
    if any(result[key] != value for key, value in compatibility.items()):
        raise _invalid()
    limits = _section(
        config.get("limits", {}),
        {
            "attempts": 5000,
            "active": 10,
            "in_flight": 10,
            "generation_seconds": 300,
            "drain_seconds": 15,
        },
    )
    for key, upper in (("attempts", 1000000), ("active", 250), ("in_flight", 250)):
        _number(limits[key], 1, upper, integer=True)
    for key, upper in (("generation_seconds", 86400), ("drain_seconds", 300)):
        if _number(limits[key], 0, upper) == 0:
            raise _invalid()
    generation = cast(float, limits["generation_seconds"])
    burst = family in ("post-event", "hotspot")
    soak = family == "soak"
    rate = min(attendees, 10) if soak else (0 if burst else attendees / 2)
    traffic = _section(
        config.get("traffic", {}),
        {
            "mode": "active" if soak else "arrivals",
            "segments": [
                {"duration_seconds": 30 if soak else 2, "start": rate, "end": rate}
            ],
            "bursts": [
                {"at_seconds": 0.1 if family == "hotspot" else 0.25, "count": attendees}
            ]
            if burst
            else [],
            "think_seconds": 1 if soak else 0.05,
            "jitter_seconds": 0,
            "max_entries": 10000,
            "bucket_seconds": 1,
        },
    )
    if traffic["mode"] not in ("arrivals", "active"):
        raise _invalid()
    _number(traffic["max_entries"], 1, 10000, integer=True)
    for key in ("think_seconds", "jitter_seconds"):
        _number(traffic[key], 0, math.inf)
    width = _number(traffic["bucket_seconds"], 0, math.inf)
    if width == 0:
        raise _invalid()
    segments = traffic["segments"]
    if (
        not isinstance(segments, list)
        or not 1 <= len(cast(list[object], segments)) <= 100
    ):
        raise _invalid()
    duration = 0.0
    for raw in cast(list[object], segments):
        segment = _section(raw, {"duration_seconds": 0, "start": 0, "end": 0})
        if set(cast(dict[str, object], raw)) != set(segment):
            raise _invalid()
        seconds = _number(segment["duration_seconds"], 0, generation)
        if seconds == 0:
            raise _invalid()
        duration += seconds
        for key in ("start", "end"):
            _number(
                segment[key],
                0,
                min(attendees, cast(int, limits["active"]))
                if traffic["mode"] == "active"
                else 1000000,
                integer=traffic["mode"] == "active",
            )
    if duration > generation or traffic_bucket_count(duration, width) > 1000:
        raise _invalid()
    bursts = traffic["bursts"]
    if not isinstance(bursts, list) or len(cast(list[object], bursts)) > 100:
        raise _invalid()
    for raw in cast(list[object], bursts):
        item = _section(raw, {"at_seconds": 0, "count": 0})
        if set(cast(dict[str, object], raw)) != set(item):
            raise _invalid()
        _number(item["at_seconds"], 0, duration)
        _number(item["count"], 1, 10000, integer=True)
    failure = _section(
        config.get("failure", {}),
        {
            "operations": list(failure_operations),
            "pre_send_delay_seconds": 0,
            "pre_send_failure_rate": 0.1 if family == "retry" else 0,
            "response_delay_seconds": 0,
            "lost_response_rate": 0.1 if family == "retry" else 0,
            "timeout_rate": 0,
            "duplicate_overlap": family == "hotspot",
            "domain_case": "none",
            "recover_existing": False,
            "confirmation_delay_seconds": 0,
        },
    )
    operations = failure["operations"]
    if not isinstance(operations, list):
        raise _invalid()
    ops = cast(list[object], operations)
    if any(type(op) is not str or op not in failure_operations for op in ops) or len(
        set(cast(list[str], ops))
    ) != len(ops):
        raise _invalid()
    for key in ("pre_send_failure_rate", "lost_response_rate", "timeout_rate"):
        _number(failure[key], 0, 1)
    if (
        cast(float, failure["lost_response_rate"])
        + cast(float, failure["timeout_rate"])
        > 1
    ):
        raise _invalid()
    for key in (
        "pre_send_delay_seconds",
        "response_delay_seconds",
        "confirmation_delay_seconds",
    ):
        _number(failure[key], 0, generation)
    for key in ("duplicate_overlap", "recover_existing"):
        if type(failure[key]) is not bool:
            raise _invalid()
    if failure["domain_case"] not in domain_cases:
        raise _invalid()
    if failure["domain_case"] == "expired" and (
        duration <= 43200 or generation <= 43200
    ):
        raise _invalid()
    retry = _section(
        config.get("retry", {}),
        {"attempts": 3, "base_seconds": 0.25, "cap_seconds": 2, "jitter_seconds": 0},
    )
    _number(retry["attempts"], 1, 10, integer=True)
    for key in ("base_seconds", "cap_seconds", "jitter_seconds"):
        _number(retry[key], 0, math.inf)
    if cast(float, retry["base_seconds"]) > cast(float, retry["cap_seconds"]):
        raise _invalid()
    result.update(traffic=traffic, failure=failure, retry=retry, limits=limits)
    return result
