"""Closed, synthetic population assumptions and finite workload bounds."""

import re
from collections.abc import Mapping
from typing import cast

FAMILIES = ("baseline", "post-event", "hotspot", "retry", "soak")
PERSONAS = ("casual", "active", "heavy", "retry_prone", "normal_owner", "popular_owner")
DEFAULTS: dict[str, object] = {
    "target": "staging",
    "base_url": None,
    "pool": None,
    "family": "baseline",
    "casual": 1,
    "active": 1,
    "heavy": 1,
    "retry_prone": 1,
    "normal_owners": 1,
    "popular_owners": 1,
    "fursuits": 4,
    "casual_budget": 1,
    "active_budget": 3,
    "heavy_budget": 8,
    "retry_budget": 3,
    "casual_repeats": 0,
    "active_repeats": 0,
    "heavy_repeats": 0,
    "retry_repeats": 2,
    "casual_history": 0,
    "active_history": 3,
    "heavy_history": 1,
    "retry_history": 1,
    "normal_weight": 1,
    "popular_weight": 4,
    "cycles": 1,
    "activation_break": False,
}


def resolve_behavior_config(config: Mapping[str, object]) -> dict[str, object]:
    """Reject unsupported or over-cap workloads before external work."""
    if set(config) - set(DEFAULTS):
        raise ValueError("invalid behavior configuration")
    family = config.get("family", "baseline")
    if not isinstance(family, str) or family not in FAMILIES:
        raise ValueError("invalid behavior configuration")
    effective = {**DEFAULTS, "cycles": 3 if family == "soak" else 1, **config}
    pool = effective["pool"]
    if (
        effective["target"] != "staging"
        or effective["base_url"] is not None
        or not isinstance(pool, str)
        or re.fullmatch(r"[a-z0-9]{1,12}", pool) is None
        or type(effective["activation_break"]) is not bool
    ):
        raise ValueError("invalid behavior configuration")
    for key, value in effective.items():
        if key in {"target", "base_url", "pool", "family", "activation_break"}:
            continue
        lower, upper = 0, 200
        if key == "fursuits":
            lower, upper = 1, 5
        elif key.endswith("_budget"):
            lower, upper = 1, 200
        elif key.endswith("_repeats"):
            upper = 10
        elif key.endswith("_weight") or key == "cycles":
            lower, upper = 1, 100
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError("invalid behavior configuration")
    owners = cast(int, effective["normal_owners"]) + cast(
        int, effective["popular_owners"]
    )
    attendees = sum(cast(int, effective[key]) for key in PERSONAS[:4])
    targets = 1 if family == "hotspot" else owners * cast(int, effective["fursuits"])
    maximum = sum(
        cast(int, effective[persona])
        * min(cast(int, effective[f"{prefix}_budget"]), targets)
        for persona, prefix in zip(
            PERSONAS[:4], ("casual", "active", "heavy", "retry"), strict=True
        )
    )
    if (
        not 1 <= owners <= 50
        or not 1 <= attendees <= 200
        or maximum > 200
        or (family == "hotspot" and effective["popular_owners"] == 0)
        or (family == "retry" and effective["retry_prone"] == 0)
    ):
        raise ValueError("invalid behavior configuration")
    return effective
