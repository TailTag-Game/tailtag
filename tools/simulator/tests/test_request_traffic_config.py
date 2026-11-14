"""#508 AC14: scenario version 3 resolves the catch request flow and keeps v2 frozen."""

from typing import cast

import pytest

from tailtag_simulator.traffic_config import (
    resolve_request_traffic_config,
    resolve_traffic_config,
)


def test_v3_adds_the_review_mix_and_request_operation_names() -> None:
    config = resolve_request_traffic_config({"pool": "alpha"})

    assert config["review"] == {
        "automatic_share": 0.25,
        "delay_min_seconds": 5,
        "delay_max_seconds": 30,
        "approve_rate": 0.85,
        "poll_seconds": 2,
    }
    failure = cast(dict[str, object], config["failure"])
    assert failure["operations"] == ["read", "preview", "submit"]
    # v2 keeps its frozen names and has no review section.
    v2 = resolve_traffic_config({"pool": "alpha"})
    assert cast(dict[str, object], v2["failure"])["operations"] == [
        "read",
        "resolve",
        "confirm",
    ]
    assert "review" not in v2


@pytest.mark.parametrize(
    "change",
    [
        {"failure": {"operations": ["resolve"]}},
        {"review": {"unknown": 1}},
        # 121 planned requests: 11 heavy players with 11 suits each.
        {
            "casual": 0,
            "active": 0,
            "retry_prone": 0,
            "heavy": 11,
            "heavy_budget": 11,
            "normal_owners": 11,
            "popular_owners": 0,
            "fursuits": 1,
        },
        # One player planning 31 suits would meet the per-player limit.
        {
            "casual": 0,
            "active": 0,
            "retry_prone": 0,
            "heavy": 1,
            "heavy_budget": 31,
            "normal_owners": 31,
            "popular_owners": 0,
            "fursuits": 1,
        },
    ],
    ids=("v2-operation", "unknown-review-key", "over-request-cap", "over-player-limit"),
)
def test_v3_rejects_v2_names_bad_review_values_and_oversized_runs(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="invalid"):
        resolve_request_traffic_config({"pool": "alpha", **change})


def test_v3_accepts_the_request_domain_cases_and_the_request_cap() -> None:
    for case in ("none", "replaced", "stopped"):
        failure = resolve_request_traffic_config(
            {"pool": "alpha", "failure": {"domain_case": case}}
        )["failure"]
        assert cast(dict[str, object], failure)["domain_case"] == case
    at_cap = resolve_request_traffic_config(
        {
            "pool": "alpha",
            "casual": 0,
            "active": 0,
            "retry_prone": 0,
            "heavy": 10,
            "heavy_budget": 12,
            "normal_owners": 12,
            "popular_owners": 0,
            "fursuits": 1,
        }
    )
    assert at_cap["heavy"] == 10
