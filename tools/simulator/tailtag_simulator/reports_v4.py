"""Closed bounded safety evidence, layered over historical scenario semantics."""

import copy
from collections.abc import Mapping
from typing import Any

from tailtag_simulator.safety import resolve_safety_policy

REASONS = {
    "identity_mismatch",
    "readiness",
    "catastrophic_errors",
    "request_ceiling",
    "duration_ceiling",
    "population_ceiling",
    "correctness",
    "resource_saturation",
    "report_failure",
}
OBSERVATIONS = {"unverified", "passed", "unavailable", "invalid", "mismatch"}
OPERATIONS = {"reconciliation", "retention", "release", "clerk_closure"}
COUNTERS = {
    "requests",
    "ordinary_active",
    "ordinary_peak",
    "control_active",
    "control_peak",
}
ERRORS = {
    "closed_windows",
    "qualifying_windows",
    "consecutive_windows",
    "current_completed",
    "current_catastrophic",
    "last_completed",
    "last_catastrophic",
}


def safety(value: object) -> dict[str, Any]:
    from tailtag_simulator.reports import (
        ReportFailed,
        _count,  # pyright: ignore[reportPrivateUsage]
        _identity,  # pyright: ignore[reportPrivateUsage]
        _number,  # pyright: ignore[reportPrivateUsage]
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
    )

    try:
        result = _object(
            value,
            {
                "policy",
                "target",
                "preflight",
                "probes",
                "execution",
                "finalization",
                "errors",
                "abort",
                "resources",
                "concurrency",
            },
        )
        policy = result["policy"]
        _require(isinstance(policy, dict))
        _require(resolve_safety_policy(policy) == policy)
        target = _object(result["target"], {"identity", "evidence"})
        _require(target["evidence"] in ("unverified", "staging", "local"))
        if target["identity"] is None:
            _require(target["evidence"] == "unverified")
        else:
            _require(target["evidence"] != "unverified")
            _require(_identity(target["identity"], target["evidence"]))
        for name in ("preflight", "probes"):
            keys = {"checks", "passed", "failed", "last"}
            if name == "probes":
                keys |= {"consecutive_failures", "paused"}
            observation = _object(result[name], keys)
            _require(
                all(
                    _count(observation[k], 2**63 - 1) for k in keys - {"last", "paused"}
                )
            )
            _require(
                observation["checks"]
                == min(2**63 - 1, observation["passed"] + observation["failed"])
            )
            _require(observation["last"] in OBSERVATIONS)
            if name == "probes":
                _require(type(observation["paused"]) is bool)
                _require(observation["consecutive_failures"] <= observation["failed"])
        for name in ("execution", "finalization"):
            keys = COUNTERS | {"elapsed_seconds", "exhausted"}
            if name == "finalization":
                keys |= OPERATIONS | {"started", "allowed"}
            budget = _object(result[name], keys)
            limit = policy["requests" if name == "execution" else "final_requests"]
            _require(_count(budget["requests"], limit))
            _require(all(_count(budget[k], 250) for k in COUNTERS - {"requests"}))
            _require(_number(budget["elapsed_seconds"]))
            _require(
                budget["exhausted"]
                in (
                    None,
                    "requests",
                    "seconds",
                    *(("population",) if name == "execution" else ()),
                )
            )
            for kind, cap in (("ordinary", policy["in_flight"]), ("control", 1)):
                _require(budget[kind + "_active"] <= budget[kind + "_peak"] <= cap)
            if name == "finalization":
                _require(
                    type(budget["started"]) is bool and type(budget["allowed"]) is bool
                )
                _require(not budget["allowed"] or budget["started"])
                _require(
                    all(
                        budget[k]
                        in ("not_attempted", "passed", "failed", "skipped", "uncertain")
                        for k in OPERATIONS
                    )
                )
        errors = _object(result["errors"], ERRORS)
        _require(all(_count(n, 2**63 - 1) for n in errors.values()))
        _require(
            errors["consecutive_windows"]
            <= errors["qualifying_windows"]
            <= errors["closed_windows"]
        )
        for prefix in ("current", "last"):
            _require(errors[prefix + "_catastrophic"] <= errors[prefix + "_completed"])
        if result["abort"] is not None:
            abort = _object(result["abort"], {"reason", "elapsed_seconds"})
            _require(abort["reason"] in REASONS and _number(abort["elapsed_seconds"]))
        _require(
            _object(result["resources"], {"monitoring"})
            == {"monitoring": "unavailable"}
        )
        _require(
            all(
                _count(n, 251)
                for n in _object(
                    result["concurrency"],
                    {"ordinary_limit", "control_limit", "combined_limit"},
                ).values()
            )
        )
        _require(
            _object(
                result["concurrency"],
                {"ordinary_limit", "control_limit", "combined_limit"},
            )
            == {
                "ordinary_limit": policy["in_flight"],
                "control_limit": 1,
                "combined_limit": policy["in_flight"] + 1,
            }
        )
        return copy.deepcopy(result)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ReportFailed from None


def validate(
    value: dict[str, Any], admitted_scenario: Mapping[str, Any] | None
) -> dict[str, object]:
    from tailtag_simulator.reports import (
        _require,  # pyright: ignore[reportPrivateUsage]
        _validate_report,  # pyright: ignore[reportPrivateUsage]
    )

    evidence = safety(value["safety"])
    _require(evidence["abort"] is None or value["outcome"] in ("running", "aborted"))
    if value["outcome"] == "passed":
        pin = evidence["target"]
        target = value["target"]
        _require(pin["identity"] is not None and pin["evidence"] == target["name"])
        for name in ("starting", "final"):
            observed = target[name]["value"]
            _require(observed is None or observed == pin["identity"])
        preflight, probes = evidence["preflight"], evidence["probes"]
        _require(preflight["last"] == "passed" and preflight["passed"] > 0)
        _require(not probes["paused"] and probes["consecutive_failures"] == 0)
        _require(probes["last"] == ("passed" if probes["checks"] else "unverified"))
        _require(not probes["checks"] or probes["passed"] > 0)
    _require(value["outcome"] != "aborted" or evidence["abort"] is not None)
    projection = {k: v for k, v in value.items() if k != "safety"}
    scenario = projection["scenario"]
    convention = isinstance(scenario["id"], str) and scenario["id"].startswith(
        "convention-"
    )
    projection["schema_version"] = (
        3 if convention and scenario["version"] == 2 else 2 if convention else 1
    )
    if projection["outcome"] == "aborted":
        projection["outcome"] = "failed"
    _validate_report(projection, admitted_scenario)
    return copy.deepcopy(value)
