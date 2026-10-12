"""AC8/14/15/17: closed traffic inputs preserve finite inspectable workloads."""

from copy import deepcopy
from typing import cast

import pytest

from tailtag_simulator.traffic_config import resolve_traffic_config


def nested(config: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], config[key])


@pytest.mark.parametrize(
    ("family", "mode", "duration", "rate", "burst", "think"),
    [
        ("baseline", "arrivals", 2, 2, [], 0.05),
        ("post-event", "arrivals", 2, 0, [{"at_seconds": 0.25, "count": 4}], 0.05),
        ("hotspot", "arrivals", 2, 0, [{"at_seconds": 0.1, "count": 4}], 0.05),
        ("retry", "arrivals", 2, 2, [], 0.05),
        ("soak", "active", 30, 4, [], 1),
    ],
)
def test_recipes_resolve_distinct_synthetic_workloads(
    family: str,
    mode: str,
    duration: int,
    rate: int,
    burst: list[dict[str, object]],
    think: float,
) -> None:
    config = resolve_traffic_config({"pool": "alpha", "family": family})
    traffic = nested(config, "traffic")
    assert traffic["mode"] == mode
    assert traffic["segments"] == [
        {"duration_seconds": duration, "start": rate, "end": rate}
    ]
    assert traffic["bursts"] == burst
    assert traffic["think_seconds"] == think
    failure = nested(config, "failure")
    assert failure["duplicate_overlap"] is (family == "hotspot")
    assert failure["pre_send_failure_rate"] == (0.1 if family == "retry" else 0)
    assert failure["lost_response_rate"] == (0.1 if family == "retry" else 0)


INVALID: dict[str, dict[str, object]] = {
    "unknown-top-level": {"SENTINEL-private": 1},
    "unknown-traffic-key": {"traffic": {"SENTINEL-private": 1}},
    "unknown-failure-key": {"failure": {"SENTINEL-private": 1}},
    "unknown-retry-key": {"retry": {"SENTINEL-private": 1}},
    "unknown-limit-key": {"limits": {"SENTINEL-private": 1}},
    "non-object": {"failure": []},
    "unknown-mode": {"traffic": {"mode": "SENTINEL-private"}},
    "empty-segments": {"traffic": {"segments": []}},
    "unbounded-segments": {
        "traffic": {"segments": [{"duration_seconds": 1, "start": 0, "end": 0}] * 101}
    },
    "unknown-segment-field": {
        "traffic": {"segments": [{"duration_seconds": 1, "start": 0, "end": 0, "x": 0}]}
    },
    "zero-duration": {
        "traffic": {"segments": [{"duration_seconds": 0, "start": 0, "end": 0}]}
    },
    "negative-rate": {
        "traffic": {"segments": [{"duration_seconds": 1, "start": -1, "end": 0}]}
    },
    "fractional-active-target": {
        "traffic": {
            "mode": "active",
            "segments": [{"duration_seconds": 1, "start": 1.5, "end": 1}],
        }
    },
    "active-target-over-population": {
        "traffic": {
            "mode": "active",
            "segments": [{"duration_seconds": 1, "start": 5, "end": 5}],
        }
    },
    "active-target-over-cap": {
        "traffic": {
            "mode": "active",
            "segments": [{"duration_seconds": 1, "start": 2, "end": 2}],
        },
        "limits": {"active": 1},
    },
    "burst-outside-profile": {"traffic": {"bursts": [{"at_seconds": 2.1, "count": 1}]}},
    "negative-burst-time": {"traffic": {"bursts": [{"at_seconds": -0.1, "count": 1}]}},
    "boolean-burst-count": {
        "traffic": {"bursts": [{"at_seconds": 0.1, "count": True}]}
    },
    "burst-over-entry-bound": {
        "traffic": {"bursts": [{"at_seconds": 0.1, "count": 10001}]}
    },
    "entry-limit-over-hard-bound": {"traffic": {"max_entries": 10001}},
    "boolean-entry-limit": {"traffic": {"max_entries": True}},
    "bucket-over-hard-bound": {"traffic": {"bucket_seconds": 0.001}},
    "bucket-division-overflow": {"traffic": {"bucket_seconds": 5e-324}},
    "zero-bucket-width": {"traffic": {"bucket_seconds": 0}},
    "unknown-effect-operation": {"failure": {"operations": ["SENTINEL-private"]}},
    "duplicate-effect-operation": {"failure": {"operations": ["confirm", "confirm"]}},
    "invalid-effect-probability": {"failure": {"pre_send_failure_rate": 1.1}},
    "conflicting-loss-probabilities": {
        "failure": {"lost_response_rate": 0.6, "timeout_rate": 0.5}
    },
    "negative-effect-delay": {"failure": {"response_delay_seconds": -1}},
    "effect-delay-outside-ceiling": {"failure": {"pre_send_delay_seconds": 301}},
    "wrong-boolean": {"failure": {"recover_existing": 1}},
    "unknown-domain-case": {"failure": {"domain_case": "SENTINEL-private"}},
    "expiration-with-short-defaults": {"failure": {"domain_case": "expired"}},
    "retry-unbounded": {"retry": {"attempts": 11}},
    "retry-disabled": {"retry": {"attempts": 0}},
    "retry-negative-delay": {"retry": {"jitter_seconds": -1}},
    "integer-float-overflow": {"retry": {"base_seconds": 10**400}},
    "retry-base-over-cap": {"retry": {"base_seconds": 3, "cap_seconds": 2}},
    "zero-attempt-limit": {"limits": {"attempts": 0}},
    "attempt-limit-over-hard-bound": {"limits": {"attempts": 1000001}},
    "active-limit-over-hard-bound": {"limits": {"active": 251}},
    "boolean-inflight-limit": {"limits": {"in_flight": True}},
    "zero-drain": {"limits": {"drain_seconds": 0}},
    "drain-over-hard-bound": {"limits": {"drain_seconds": 301}},
    "generation-over-hard-bound": {"limits": {"generation_seconds": 86401}},
    "profile-outside-generation": {"limits": {"generation_seconds": 1}},
    "compat-cycles": {"cycles": 2},
    "compat-soak-cycles": {"family": "soak", "cycles": 1},
    "compat-activation-break": {"activation_break": True},
    "compat-casual-history": {"casual_history": 1},
    "compat-active-history": {"active_history": 0},
    "compat-heavy-history": {"heavy_history": 0},
    "compat-retry-history": {"retry_history": 0},
    "distinct-pairs-over-cap": {
        "casual": 41,
        "active": 0,
        "heavy": 0,
        "retry_prone": 0,
        "normal_owners": 1,
        "popular_owners": 0,
        "fursuits": 5,
        "casual_budget": 5,
    },
}


@pytest.mark.parametrize("case", INVALID)
def test_rejects_unsafe_nested_config_without_private_details(case: str) -> None:
    with pytest.raises(ValueError) as caught:
        resolve_traffic_config({"pool": "alpha", **INVALID[case]})
    assert "SENTINEL" not in repr(caught.value)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), True, "1"]
)
@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("traffic", "think_seconds"),
        ("failure", "lost_response_rate"),
        ("retry", "base_seconds"),
        ("limits", "generation_seconds"),
    ],
)
def test_nonfinite_and_coerced_numbers_cannot_enter_runtime(
    section: str,
    key: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        resolve_traffic_config({"pool": "alpha", section: {key: value}})


def test_nested_overrides_replace_segments_merge_defaults_and_do_not_alias_inputs() -> (
    None
):
    supplied: dict[str, object] = {
        "pool": "alpha",
        "family": "soak",
        "traffic": {"segments": [{"duration_seconds": 1, "start": 0, "end": 1}]},
        "retry": {"attempts": 1},
    }
    original = deepcopy(supplied)
    resolved = resolve_traffic_config(supplied)
    assert nested(resolved, "traffic")["segments"] == [
        {"duration_seconds": 1, "start": 0, "end": 1}
    ]
    assert nested(resolved, "retry") == {
        "attempts": 1,
        "base_seconds": 0.25,
        "cap_seconds": 2,
        "jitter_seconds": 0,
    }
    nested(resolved, "traffic")["think_seconds"] = 99
    assert supplied == original
    assert nested(resolve_traffic_config(supplied), "traffic")["think_seconds"] == 1


def test_inspection_capacity_allows_revisiting_exactly_200_distinct_pairs() -> None:
    config = resolve_traffic_config(
        {
            "pool": "alpha",
            "family": "soak",
            "casual": 40,
            "active": 0,
            "heavy": 0,
            "retry_prone": 0,
            "normal_owners": 1,
            "popular_owners": 0,
            "fursuits": 5,
            "casual_budget": 5,
            "cycles": 3,
        }
    )
    assert config["cycles"] == 3
    assert config["casual"] == 40


def test_natural_expiration_requires_and_accepts_explicit_long_finite_profile() -> None:
    config = resolve_traffic_config(
        {
            "pool": "alpha",
            "traffic": {
                "segments": [{"duration_seconds": 43201, "start": 0, "end": 0}],
                "bucket_seconds": 60,
            },
            "failure": {"domain_case": "expired", "confirmation_delay_seconds": 43200},
            "limits": {"generation_seconds": 43201},
        }
    )
    assert nested(config, "failure")["domain_case"] == "expired"
    assert nested(config, "limits")["generation_seconds"] == 43201
