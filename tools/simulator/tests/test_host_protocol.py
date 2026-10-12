"""#228 U1: trusted launch bounds and detail-free JSON framing."""

import json
from copy import deepcopy
from typing import cast

import pytest

from tailtag_simulator.host_protocol import (
    decode_document,
    decode_frame,
    encode_frame,
    validate_manifest,
)
from tailtag_simulator.safety import resolve_safety_policy
from tailtag_simulator.traffic_config import resolve_traffic_config

RUN = "55555555-5555-4555-8555-555555555555"
IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
SENTINEL = "SENTINEL-private-secret"


def manifest() -> dict[str, object]:
    # Existing resolvers prepare inputs only; expected authority is hand-derived:
    # two owners, four attendees, four fursuits per owner, six leased identities.
    return {
        "schema_version": 1,
        "run_id": RUN,
        "scenario_id": "convention-baseline",
        "scenario_version": 2,
        "seed": -7,
        "configuration": resolve_traffic_config({"pool": "alpha"}),
        "safety": resolve_safety_policy({"population": 50}),
        "backend_identity": dict(IDENTITY),
        "release": {
            "simulator_sha": "b" * 40,
            "dependency_lock_sha256": "c" * 64,
            "image_id": "sha256:" + "d" * 64,
            "platform": "linux/amd64",
        },
    }


def section(value: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], value[key])


def test_normalized_manifest_is_detached_and_accepts_host_boundary_population() -> None:
    supplied = manifest()
    configuration = resolve_traffic_config(
        {
            "pool": "alpha",
            "normal_owners": 1,
            "popular_owners": 0,
            "casual": 49,
            "active": 0,
            "heavy": 0,
            "retry_prone": 0,
        }
    )
    supplied["configuration"] = configuration
    expected = deepcopy(supplied)
    accepted = validate_manifest(supplied)
    assert accepted == expected
    section(supplied, "backend_identity")["source_sha"] = "e" * 40
    section(section(supplied, "configuration"), "limits")["active"] = 1
    assert accepted == expected
    section(accepted, "release")["image_id"] = SENTINEL
    assert section(supplied, "release")["image_id"] == "sha256:" + "d" * 64


MANIFEST_INVALID: list[tuple[str, str, object]] = [
    ("", "schema_version", True),
    ("", "run_id", "not-a-uuid-" + SENTINEL),
    ("", "scenario_version", 1),
    ("", "seed", True),
    ("", "scenario_id", "convention-retry"),
    ("", SENTINEL, 1),
    ("backend_identity", "environment", "production"),
    ("backend_identity", "deployment_id", SENTINEL),
    ("release", "platform", "linux/arm64"),
    ("release", "simulator_sha", SENTINEL),
    ("release", "image_id", "latest"),
    ("release", "dependency_lock_sha256", SENTINEL),
    ("safety", "seconds", 901),
    ("safety", "final_seconds", 601),
    ("safety", "population", 51),
    ("safety", "in_flight", 11),
    ("configuration.limits", "active", 11),
    ("configuration.limits", "in_flight", 11),
    ("configuration", "casual", 47),  # 2 owners + 50 attendees exceeds 50.
    ("configuration", "retry", None),  # Missing normalization must not be filled.
]


@pytest.mark.parametrize(("path", "key", "value"), MANIFEST_INVALID)
def test_manifest_rejects_untrusted_or_over_host_bound_launch_state(
    path: str, key: str, value: object
) -> None:
    supplied = manifest()
    target = supplied
    for name in path.split(".") if path else []:
        target = section(target, name)
    if value is None:
        del target[key]
    else:
        target[key] = value
    with pytest.raises(ValueError) as caught:
        validate_manifest(supplied)
    assert SENTINEL not in repr(caught.value)


def test_frames_roundtrip_requests_replies_and_exact_byte_boundary() -> None:
    values: list[dict[str, object]] = [
        {"schema_version": 1, "channel": "health", "run_id": RUN},
        {"result": "PASS", "data": {"indexes": [17, 23]}},
    ]
    for value in values:
        encoded = encode_frame(value)
        assert encoded.endswith(b"\n") and encoded.count(b"\n") == 1
        assert json.loads(encoded) == value
        assert decode_frame(encoded) == value
    pretty = b'{\n  "nested": {"value": 1},\n  "name": "configured"\n}\n'
    assert decode_document(pretty) == {"nested": {"value": 1}, "name": "configured"}
    with pytest.raises(ValueError):
        decode_frame(pretty)
    # Literal 65536 bytes including the required final newline.
    boundary = b'{"x":"' + b"a" * 65527 + b'"}\n'
    assert len(boundary) == 65536
    assert decode_frame(boundary) == {"x": "a" * 65527}
    assert decode_document(boundary) == {"x": "a" * 65527}
    for decode in (decode_frame, decode_document):
        with pytest.raises(ValueError):
            decode(boundary[:-1] + b" \n")
    with pytest.raises(ValueError):
        encode_frame({"x": "a" * 65536})
    with pytest.raises(ValueError):
        encode_frame({"x": float("nan")})


@pytest.mark.parametrize(
    ("raw", "document_valid"),
    [
        (b'{"x":1,"x":2}\n', False),
        (b'{"x":{"nested":1,"nested":2}}\n', False),
        (b'{"x":NaN}\n', False),
        (b'{"x":Infinity}\n', False),
        (b'{"x":"\xff"}\n', False),
        (b"[]\n", False),
        (b"{}", True),
        (b"{}\n{}\n", False),
        (b'{"x":"SENTINEL-private-secret"', False),
    ],
)
def test_malformed_frames_fail_without_echoing_input(
    raw: bytes, document_valid: bool
) -> None:
    with pytest.raises(ValueError) as caught:
        decode_frame(raw)
    assert SENTINEL not in repr(caught.value)
    if document_valid:
        assert decode_document(raw) == {}
    else:
        with pytest.raises(ValueError) as document_error:
            decode_document(raw)
        assert SENTINEL not in repr(document_error.value)


# #230 U1: admission accepts exactly three closed shapes.
def merged(base: dict[str, object], changes: dict[str, object]) -> dict[str, object]:
    """One-level-deep override so a case names only the nested key it changes."""
    result = deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**cast(dict[str, object], result[key]), **value}
        else:
            result[key] = value
    return result


def journeys_manifest(**changes: object) -> dict[str, object]:
    launch = manifest()
    launch.update(
        scenario_id="journeys",
        scenario_version=1,
        seed=0,
        configuration={"pool": "alpha"},
        safety=resolve_safety_policy({"population": 7}),
    )
    launch.update(changes)
    return launch


EXPIRATION_CONFIG: dict[str, object] = {
    "pool": "alpha",
    "family": "baseline",
    "normal_owners": 1,
    "popular_owners": 0,
    "casual": 1,
    "active": 0,
    "heavy": 0,
    "retry_prone": 0,
    "fursuits": 1,
    "traffic": {
        "mode": "active",
        "segments": [{"duration_seconds": 44000, "start": 1, "end": 1}],
        "bursts": [],
        "think_seconds": 1,
        "jitter_seconds": 0,
        "bucket_seconds": 60,
    },
    "failure": {"domain_case": "expired"},
    "limits": {
        "active": 1,
        "in_flight": 2,
        "generation_seconds": 44500,
        "drain_seconds": 15,
    },
}
EXPIRATION_SAFETY: dict[str, object] = {
    "seconds": 46800,
    "final_seconds": 600,
    "population": 2,
    "in_flight": 2,
}


def expiration_manifest(
    config: dict[str, object] | None = None,
    safety: dict[str, object] | None = None,
    **top: object,
) -> dict[str, object]:
    launch = manifest()
    launch.update(
        configuration=resolve_traffic_config(merged(EXPIRATION_CONFIG, config or {})),
        safety=resolve_safety_policy({**EXPIRATION_SAFETY, **(safety or {})}),
    )
    launch.update(top)
    return launch


def test_journeys_and_expiration_tier_manifests_are_admitted_unchanged() -> None:
    for supplied in (journeys_manifest(), expiration_manifest()):
        expected = deepcopy(supplied)
        assert validate_manifest(supplied) == expected


ADMISSION_REFUSED: list[tuple[str, dict[str, object]]] = [
    ("journeys-extra-key", journeys_manifest(configuration={"pool": "a", "x": 1})),
    ("journeys-family", journeys_manifest(configuration={"pool": "a", "family": "b"})),
    ("journeys-bad-pool", journeys_manifest(configuration={"pool": "Bad_Pool"})),
    ("journeys-seed", journeys_manifest(seed=1)),
    ("journeys-version", journeys_manifest(scenario_version=2)),
    (
        "journeys-population",
        journeys_manifest(safety=resolve_safety_policy({"population": 6})),
    ),
    (
        "journeys-over-standard-ceiling",
        journeys_manifest(safety=resolve_safety_policy({"population": 51})),
    ),
    ("expiration-persona-sum", expiration_manifest({"casual": 2})),
    (
        "expiration-domain-case",
        expiration_manifest({"failure": {"domain_case": "none"}}),
    ),
    ("expiration-seconds", expiration_manifest(safety={"seconds": 46801})),
    ("expiration-final-seconds", expiration_manifest(safety={"final_seconds": 601})),
    ("expiration-population", expiration_manifest(safety={"population": 3})),
    ("expiration-safety-in-flight", expiration_manifest(safety={"in_flight": 3})),
    ("expiration-requests", expiration_manifest(safety={"requests": 10001})),
    (
        "expiration-family",
        expiration_manifest(
            {"family": "retry", "casual": 0, "retry_prone": 1},
            scenario_id="convention-retry",
        ),
    ),
    ("expiration-active", expiration_manifest({"limits": {"active": 2}})),
    ("expiration-in-flight", expiration_manifest({"limits": {"in_flight": 3}})),
    (
        "expiration-generation",
        expiration_manifest({"limits": {"generation_seconds": 45001}}),
    ),
    (
        # Large persona sum, standard ceilings: only the tier rule can refuse it.
        "standard-expired",
        expiration_manifest(
            {"casual": 9, "limits": {"active": 10, "in_flight": 10}},
            {"seconds": 900, "population": 50, "in_flight": 10},
        ),
    ),
]


@pytest.mark.parametrize(
    "supplied",
    [item for _, item in ADMISSION_REFUSED],
    ids=[n for n, _ in ADMISSION_REFUSED],
)
def test_manifest_refuses_everything_outside_the_three_closed_shapes(
    supplied: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        validate_manifest(supplied)
