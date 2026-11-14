"""Closed client-side performance evidence, layered over schema 4 semantics (#229).

Schema 6 (#508) is schema 5 for scenario version 3: the same rules with the
catch request operation names. Schema 5 stays bound to scenario version 2.
"""

import copy
import math
from collections.abc import Mapping
from typing import Any, cast

from tailtag_simulator.traffic_metrics import (
    CLASSES,
    OPERATIONS,
    PERCENTILES,
    RESPONSES,
    V6_OPERATIONS,
)

KEYS = {
    "duration_seconds",
    "window_seconds",
    "execution_mode",
    "attempts",
    "throughput",
    "latency_percentiles",
    "resource_context",
}
MODES = ("container", "checkout")
NAMES = {*OPERATIONS, "total"}
SCHEMA_OPERATIONS = {5: OPERATIONS, 6: V6_OPERATIONS}
SCHEMA_SCENARIO_VERSION = {5: 2, 6: 3}


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9)


def _observed(
    value: object, *, named: bool = True, operations: tuple[str, ...] = OPERATIONS
) -> Any:
    """Unwrap an observed measurement; `named` demands one entry per operation."""
    from tailtag_simulator.reports import (
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
    )

    result = _object(value, {"value", "reason"})
    inner: Any = result["value"]
    _require(inner is not None and result["reason"] is None)
    if named:
        _require(isinstance(result["value"], dict))
        _require(set(result["value"]) == {*operations, "total"})
    return inner


def _performance(
    performance: dict[str, Any],
    traffic: Mapping[str, Any] | None,
    operations: tuple[str, ...] = OPERATIONS,
) -> None:
    from tailtag_simulator.reports import (
        _count,  # pyright: ignore[reportPrivateUsage]
        _measurement,  # pyright: ignore[reportPrivateUsage]
        _number,  # pyright: ignore[reportPrivateUsage]
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
        unavailable,
    )

    _measurement(performance["duration_seconds"], _number)
    _measurement(performance["execution_mode"], lambda v: v in MODES)
    _require(performance["resource_context"] == unavailable())
    gaps = ("window_seconds", "attempts", "throughput", "latency_percentiles")
    if traffic is None:
        _require(all(performance[key] == unavailable() for key in gaps))
        return
    window = _observed(performance["window_seconds"], named=False)
    _require(
        _number(window)
        and _close(window, traffic["generation_seconds"] + traffic["drain_seconds"])
    )
    attempts = cast(
        dict[str, dict[str, int]],
        _observed(performance["attempts"], operations=operations),
    )
    for counts in attempts.values():
        _require(all(_count(n) for n in _object(counts, set(CLASSES)).values()))
    for outcome in CLASSES:
        _require(
            attempts["total"][outcome]
            == sum(attempts[name][outcome] for name in operations)
        )
    total = attempts["total"]
    _require(total["injected"] == traffic["injected"])
    _require(total["expected_rejection"] == traffic["expected_rejections"])
    _require(sum(total.values()) <= traffic["attempts"])
    _require(sum(total.values()) - total["injected"] <= traffic["sent"])
    responses = {
        name: sum(counts[outcome] for outcome in RESPONSES)
        for name, counts in attempts.items()
    }
    if window == 0:
        _require(performance["throughput"] == unavailable())
    else:
        throughput = cast(
            dict[str, float],
            _observed(performance["throughput"], operations=operations),
        )
        _require(
            all(
                _number(throughput[name]) and _close(throughput[name], n / window)
                for name, n in responses.items()
            )
        )
    latency = cast(
        dict[str, dict[str, Any]],
        _observed(performance["latency_percentiles"], operations=operations),
    )
    for name, row in latency.items():
        _object(row, {"samples", *(key for key, _ in PERCENTILES)})
        _require(_count(row["samples"]) and row["samples"] == responses[name])
        values: list[float] = []
        for key, _ in PERCENTILES:
            if row["samples"] == 0:
                _require(row[key] == unavailable())
                continue
            point = _object(row[key], {"value", "reason"})
            _require(point["reason"] is None and _number(point["value"]))
            values.append(point["value"])
        _require(values == sorted(values))


def validate(
    value: dict[str, Any], admitted_scenario: Mapping[str, Any] | None
) -> dict[str, object]:
    from tailtag_simulator.reports import (
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
        _validate_report,  # pyright: ignore[reportPrivateUsage]
        unavailable,
    )

    schema = value["schema_version"]
    scenario = value.get("scenario")
    _require(
        isinstance(scenario, dict)
        and cast(dict[str, Any], scenario).get("version")
        == SCHEMA_SCENARIO_VERSION[schema]
    )
    performance = _object(value["performance"], KEYS)
    # Schema 4 supplies every other rule; only the performance block differs.
    _validate_report(
        {
            **value,
            "schema_version": 4,
            "performance": {
                "duration_seconds": performance["duration_seconds"],
                "throughput": unavailable("not_implemented"),
                "latency_percentiles": unavailable("not_implemented"),
                "resource_context": unavailable(),
            },
        },
        admitted_scenario,
    )
    traffic = cast(dict[str, Any], value["results"]["traffic"])
    _performance(performance, traffic["value"], SCHEMA_OPERATIONS[schema])
    return copy.deepcopy(value)
