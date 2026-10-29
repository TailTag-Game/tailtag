"""Closed, bounded host launch manifests and newline JSON frames."""

import json
import re
import uuid
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from tailtag_simulator.pool import validate_pool_name
from tailtag_simulator.safety import resolve_safety_policy
from tailtag_simulator.traffic_config import resolve_traffic_config

MAX_FRAME_BYTES = 65536


def _invalid() -> ValueError:
    return ValueError("invalid host protocol")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _constant(_: str) -> object:
    raise _invalid()


def decode_document(raw: bytes) -> dict[str, object]:
    """Decode one bounded local JSON object, allowing document whitespace."""
    try:
        if len(raw) > MAX_FRAME_BYTES:
            raise _invalid()
        value: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
        if not isinstance(value, dict):
            raise _invalid()
        # Also reject numeric overflow to infinity at any nested depth.
        json.dumps(value, allow_nan=False)
        return cast(dict[str, object], value)
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None


def decode_frame(raw: bytes) -> dict[str, object]:
    if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise _invalid()
    return decode_document(raw)


def encode_frame(value: dict[str, object]) -> bytes:
    try:
        raw = (json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        decode_frame(raw)
        return raw
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid()
    return cast(dict[str, object], value)


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None
    )


def _within(safety: dict[str, object], ceilings: Mapping[str, float]) -> bool:
    return all(cast(float, safety[k]) <= maximum for k, maximum in ceilings.items())


_STANDARD_SAFETY = {
    "seconds": 900,
    "final_seconds": 600,
    "population": 50,
    "in_flight": 10,
}
_EXPIRATION_SAFETY = {
    "seconds": 46800,
    "final_seconds": 600,
    "population": 2,
    "in_flight": 2,
    "requests": 10000,
}


def _journeys_shape(
    launch: dict[str, object], config: dict[str, object], safety: dict[str, object]
) -> None:
    """Journeys smoke: fixed seven identities, no randomness, pool-only configuration."""
    if (
        launch["scenario_version"] != 1
        or launch["seed"] != 0
        or set(config) != {"pool"}
        or not isinstance(config["pool"], str)
        or validate_pool_name(config["pool"]) != config["pool"]
        or cast(int, safety["population"]) < 7
        or not _within(safety, _STANDARD_SAFETY)
    ):
        raise _invalid()


def _convention_shape(
    launch: dict[str, object], config: dict[str, object], safety: dict[str, object]
) -> None:
    """Standard tier, or the expiration tier selected only by the closed shape."""
    if (
        launch["scenario_version"] != 2
        or resolve_traffic_config(config) != config
        or launch["scenario_id"] != "convention-" + cast(str, config["family"])
    ):
        raise _invalid()
    population = sum(
        cast(int, config[k])
        for k in (
            "normal_owners",
            "popular_owners",
            "casual",
            "active",
            "heavy",
            "retry_prone",
        )
    )
    limits = _mapping(config["limits"])
    if _mapping(config["failure"])["domain_case"] != "expired":
        if (
            population > 50
            or not _within(safety, _STANDARD_SAFETY)
            or any(cast(int, limits[k]) > 10 for k in ("active", "in_flight"))
        ):
            raise _invalid()
    elif (
        launch["scenario_id"] != "convention-baseline"
        or population > 2
        or cast(int, limits["active"]) > 1
        or cast(int, limits["in_flight"]) > 2
        or cast(float, limits["generation_seconds"]) > 45000
        or not _within(safety, _EXPIRATION_SAFETY)
    ):
        raise _invalid()


def validate_manifest(value: object) -> dict[str, object]:
    try:
        launch = _mapping(value)
        if set(launch) != {
            "schema_version",
            "run_id",
            "scenario_id",
            "scenario_version",
            "seed",
            "configuration",
            "safety",
            "backend_identity",
            "release",
        }:
            raise _invalid()
        if (
            type(launch["schema_version"]) is not int
            or launch["schema_version"] != 1
            or type(launch["scenario_version"]) is not int
            or type(launch["seed"]) is not int
            or not _uuid(launch["run_id"])
        ):
            raise _invalid()
        config = _mapping(launch["configuration"])
        safety = _mapping(launch["safety"])
        if resolve_safety_policy(safety) != safety:
            raise _invalid()
        if launch["scenario_id"] == "journeys":
            _journeys_shape(launch, config, safety)
        else:
            _convention_shape(launch, config, safety)
        identity = _mapping(launch["backend_identity"])
        if (
            set(identity) != {"source_sha", "deployment_id", "environment"}
            or not _hex(identity["source_sha"], 40)
            or not _uuid(identity["deployment_id"])
            or identity["environment"] != "staging"
        ):
            raise _invalid()
        release = _mapping(launch["release"])
        if (
            set(release)
            != {"simulator_sha", "dependency_lock_sha256", "image_id", "platform"}
            or not _hex(release["simulator_sha"], 40)
            or not _hex(release["dependency_lock_sha256"], 64)
            or not isinstance(release["image_id"], str)
            or not release["image_id"].startswith("sha256:")
            or not _hex(release["image_id"][7:], 64)
            or release["platform"] != "linux/amd64"
        ):
            raise _invalid()
        encode_frame(launch)
        return deepcopy(launch)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise _invalid() from None
