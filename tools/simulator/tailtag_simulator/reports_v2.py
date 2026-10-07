"""Closed population evidence for convention scenarios; shared lifecycle stays in reports."""

from typing import Any, cast

PERSONAS = ("casual", "active", "heavy", "retry_prone", "normal_owner", "popular_owner")
COUNTERS = {
    "actors",
    "actions",
    "completed",
    "created",
    "already_caught",
    "expected_rejections",
    "retries",
    "history_reads",
    "exhausted",
    "unused_budget",
    "cycles",
}


def population(config: dict[str, Any]) -> dict[str, object]:
    roles = {
        p: config[
            {"normal_owner": "normal_owners", "popular_owner": "popular_owners"}.get(
                p, p
            )
        ]
        for p in PERSONAS
    }
    owners = roles["normal_owner"] + roles["popular_owner"]
    attendees = sum(roles[p] for p in PERSONAS[:4])
    return {
        "roles": roles,
        "identities": owners + attendees,
        "fixtures": {
            "owners": owners,
            "attendees": attendees,
            "fursuits_per_owner": config["fursuits"],
            "fursuits": owners * config["fursuits"],
        },
    }


def results(value: object, config: dict[str, Any], *, successful: bool) -> None:
    # Local import avoids moving or duplicating the established privacy primitives.
    from tailtag_simulator.reports import (
        CHECKS,
        CLEANUP,
        _count,  # pyright: ignore[reportPrivateUsage]
        _measurement,  # pyright: ignore[reportPrivateUsage]
        _object,  # pyright: ignore[reportPrivateUsage]
        _require,  # pyright: ignore[reportPrivateUsage]
    )

    result = _object(value, {"behavior", "checks", "cleanup"})
    behavior = _object(result["behavior"], {"items", "failure", "reason"})
    _require(
        behavior["failure"]
        in (None, "FAIL_SIMULATION", "FAIL_LEASE", "FAIL_INTERRUPTED")
    )
    _require(behavior["reason"] in (None, "not_observed"))
    if behavior["reason"] is not None:
        _require(
            behavior["items"] == {} and behavior["failure"] is None and not successful
        )
    else:
        items = _object(behavior["items"], set(PERSONAS))
        roles = cast(dict[str, int], population(config)["roles"])
        for persona, raw in items.items():
            item = _object(raw, COUNTERS)
            _require(all(_count(v) for v in item.values()))
            actors = roles[persona]
            _require(item["actors"] == actors)
            if actors == 0:
                _require(all(value == 0 for value in item.values()))
            if successful:
                cycles = config["cycles"]
                _require(
                    item["cycles"] == actors * cycles
                    and item["expected_rejections"] == 0
                )
                if persona in PERSONAS[4:]:
                    _require(item["completed"] == actors * config["fursuits"] * cycles)
                    _require(
                        all(
                            item[k] == 0
                            for k in (
                                "created",
                                "already_caught",
                                "retries",
                                "history_reads",
                                "exhausted",
                                "unused_budget",
                            )
                        )
                    )
                else:
                    prefix = "retry" if persona == "retry_prone" else persona
                    budget = config[prefix + "_budget"]
                    targets = (
                        1
                        if config["family"] == "hotspot"
                        else (config["normal_owners"] + config["popular_owners"])
                        * config["fursuits"]
                    )
                    visits = min(budget, targets)
                    repeats = config[prefix + "_repeats"]
                    cadence = config[prefix + "_history"]
                    _require(item["completed"] == actors * visits * cycles)
                    _require(item["created"] == actors * visits)
                    _require(item["retries"] == actors * visits * repeats * cycles)
                    _require(
                        item["already_caught"]
                        == actors * visits * (cycles - 1) + item["retries"]
                    )
                    _require(item["exhausted"] == (actors if budget > targets else 0))
                    _require(item["unused_budget"] == actors * max(0, budget - targets))
                    reads = (
                        1
                        if cadence == 0
                        else visits // cadence + int(visits % cadence != 0)
                    )
                    _require(item["history_reads"] == actors * cycles * reads)
                _require(item["actions"] >= item["completed"] + item["retries"])
        if successful:
            _require(behavior["failure"] is None)
    checks = _object(result["checks"], {"items", "count", "reason"})
    _require(
        isinstance(checks["items"], list)
        and len(cast(list[object], checks["items"])) <= 10000
        and _count(checks["count"], len(CHECKS))
    )
    allowed = {
        f"owner{n}" for n in range(config["normal_owners"] + config["popular_owners"])
    } | {f"attendee{n}" for n in range(sum(config[p] for p in PERSONAS[:4]))}
    names: set[str] = set()
    for raw in cast(list[object], checks["items"]):
        item = _object(raw, {"check", "actor", "expected", "observed"})
        _require(
            item["check"] in CHECKS
            and (item["actor"] is None or item["actor"] in allowed)
            and _count(item["expected"])
            and _count(item["observed"])
        )
        names.add(item["check"])
    _require(
        checks["count"] >= len(names) and checks["reason"] in (None, "not_observed")
    )
    if checks["reason"] is not None:
        _require(checks["items"] == [] and checks["count"] == 0)
    if successful:
        _require(checks == {"items": [], "count": len(CHECKS), "reason": None})
    _measurement(
        result["cleanup"],
        lambda v: all(_count(n) for n in _object(v, set(CLEANUP)).values()),
    )
