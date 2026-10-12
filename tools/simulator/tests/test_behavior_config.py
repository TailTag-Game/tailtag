"""AC2/6/8/15: closed synthetic configuration before any external work."""

import pytest

from tailtag_simulator.behavior_config import resolve_behavior_config
from tailtag_simulator.scenarios import ScenarioRejected, resolve_scenario

DEFAULTS: dict[str, object] = {
    "target": "staging",
    "base_url": None,
    "pool": "alpha",
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
FAMILIES = ("baseline", "post-event", "hotspot", "retry", "soak")


@pytest.mark.parametrize("family", FAMILIES)
def test_each_family_resolves_versioned_synthetic_defaults_and_catalog(
    family: str,
) -> None:
    config = resolve_behavior_config({"pool": "alpha", "family": family})
    want = {**DEFAULTS, "family": family, "cycles": 3 if family == "soak" else 1}
    assert config == want
    catalog = resolve_scenario(
        f"convention-{family}", 1, {"pool": "alpha", "family": family}
    )
    assert catalog["configuration"] == want
    assert catalog["version"] == 1
    descriptor = catalog["descriptor"]
    assert isinstance(descriptor, dict)
    assert descriptor["consumes_randomness"] is True
    assert descriptor["api_contract"] == "tailtag-public-v0"
    assert descriptor["roles"] == [
        "casual",
        "active",
        "heavy",
        "retry_prone",
        "normal_owner",
        "popular_owner",
    ]
    assert descriptor["waits_seconds"] == []
    assert descriptor["assumptions"] == [
        "synthetic_population",
        "isolated_convention",
        "run_owned_fursuits",
        "public_api_only",
        "separate_owner_attendee",
        "finite_cycles",
        f"family_{family.replace('-', '_')}",
    ]
    macro = {
        "baseline": "round_robin_collect",
        "post-event": "grouped_collect",
        "hotspot": "hotspot_collect",
        "retry": "retry_collect",
        "soak": "repeated_collect_cycles",
    }[family]
    assert descriptor["operations"] == [
        "identity_preflight",
        "retention_preflight",
        "lease",
        "token_setup",
        "provision",
        "context",
        "owner_cycle",
        macro,
        "owner_stop",
        "reconciliation",
        "identity_final",
        "cleanup",
        "retain_on_failure",
        "release",
    ]


INVALID: dict[str, dict[str, object]] = {
    "unknown-key": {"secret": "SENTINEL-private"},
    "boolean-count": {"casual": True},
    "boolean-budget": {"heavy_budget": True},
    "fractional-repeat": {"retry_repeats": 1.5},
    "string-history": {"active_history": "3"},
    "negative-count": {"active": -1},
    "no-attendees": {"casual": 0, "active": 0, "heavy": 0, "retry_prone": 0},
    "no-owners": {"normal_owners": 0, "popular_owners": 0},
    "over-owner-limit": {"normal_owners": 50, "popular_owners": 1},
    "over-attendee-limit": {"casual": 200},
    "no-fixtures": {"fursuits": 0},
    "over-fixture-limit": {"fursuits": 6},
    "zero-budget": {"active_budget": 0},
    "over-budget": {"active_budget": 201},
    "negative-repeat": {"casual_repeats": -1},
    "over-repeat": {"retry_repeats": 11},
    "negative-history": {"casual_history": -1},
    "over-history": {"heavy_history": 201},
    "zero-weight": {"popular_weight": 0},
    "over-weight": {"normal_weight": 101},
    "zero-cycles": {"cycles": 0},
    "over-cycles": {"cycles": 101},
    "wrong-break-type": {"activation_break": 1},
    "unknown-family": {"family": "SENTINEL-private"},
    "production": {"target": "production"},
    "arbitrary-url": {"base_url": "https://SENTINEL-private.example"},
    "invalid-pool": {"pool": "SENTINEL-private"},
    "hotspot-without-popular": {"family": "hotspot", "popular_owners": 0},
    "retry-without-retry-persona": {"family": "retry", "retry_prone": 0},
    "distinct-catch-overcap": {
        "casual": 26,
        "casual_budget": 8,
        "active": 0,
        "heavy": 0,
        "retry_prone": 0,
    },
}


@pytest.mark.parametrize("case", INVALID)
def test_unsafe_or_impossible_configuration_is_rejected_without_private_detail(
    case: str,
) -> None:
    with pytest.raises((ScenarioRejected, ValueError)) as caught:
        resolve_behavior_config(
            {"pool": "alpha", "family": "baseline", **INVALID[case]}
        )
    assert "SENTINEL" not in repr(caught.value)


def test_missing_pool_is_rejected() -> None:
    with pytest.raises((ScenarioRejected, ValueError)):
        resolve_behavior_config({"family": "baseline"})


@pytest.mark.parametrize(
    "parameters",
    [
        {
            "casual": 40,
            "casual_budget": 5,
            "fursuits": 5,
            "normal_owners": 1,
            "popular_owners": 0,
        },
        {"family": "hotspot", "casual": 200, "casual_budget": 200, "cycles": 100},
    ],
)
def test_capacity_counts_distinct_pairs_and_allows_zero_unneeded_personas(
    parameters: dict[str, object],
) -> None:
    config = resolve_behavior_config(
        {
            "pool": "alpha",
            "family": "baseline",
            "active": 0,
            "heavy": 0,
            "retry_prone": 0,
            **parameters,
        }
    )
    assert config["casual"] == parameters["casual"]
    assert config["active"] == config["heavy"] == config["retry_prone"] == 0
    assert config["cycles"] == parameters.get("cycles", 1)
