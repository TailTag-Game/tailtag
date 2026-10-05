"""Immutable, bounded descriptions of the supported simulator workloads."""

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from tailtag_simulator.targets import LOCAL_ORIGINS


class ScenarioRejected(Exception):
    """Invalid or unverifiable scenario; never includes input details."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


CATALOG = Path(__file__).with_name("scenarios")
RELATIVE = "tools/simulator/tailtag_simulator/scenarios"
IDS = ("smoke", "pool-smoke", "fixture-smoke", "journeys")
JOURNEYS = (
    "unauthenticated",
    "catch",
    "retry",
    "stopped_session",
    "stale_credential",
    "deactivated",
    "self_catch",
    "convention_mismatch",
    "ineligible_catcher",
    "not_owner",
    "avatar",
    "fursuit_photo",
    "image_rejections",
)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ScenarioRejected
        value[key] = item
    return value


def _entry(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.parent.is_symlink():
        raise ScenarioRejected
    data = path.read_bytes()
    if len(data) > 65536:
        raise ScenarioRejected
    raw_value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    if not isinstance(raw_value, dict):
        raise ScenarioRejected
    value = cast(dict[str, Any], raw_value)
    expected = {
        "id",
        "version",
        "api_contract",
        "consumes_randomness",
        "roles",
        "operations",
        "assumptions",
        "waits_seconds",
        "configuration",
        "descriptor_digest",
    }
    if (
        set(value) != expected
        or value["id"] not in IDS
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ScenarioRejected
    descriptor = {k: v for k, v in value.items() if k != "descriptor_digest"}
    if value["descriptor_digest"] != hashlib.sha256(canonical(descriptor)).hexdigest():
        raise ScenarioRejected
    # Current supported descriptors are closed contracts, including nested labels.
    if (
        value["api_contract"] != "tailtag-public-v0"
        or value["consumes_randomness"] is not False
    ):
        raise ScenarioRejected
    if path.name != f"{value['id']}-v{value['version']}.json":
        raise ScenarioRejected
    raw_config = value["configuration"]
    if not isinstance(raw_config, dict) or set(cast(dict[str, object], raw_config)) != {
        "defaults",
        "parameters",
    }:
        raise ScenarioRejected
    config = cast(dict[str, Any], raw_config)
    defaults, parameters = config["defaults"], config["parameters"]
    base = {"target": "staging", "base_url": None}
    extras = {
        "smoke": {},
        "pool-smoke": {"pool": None, "count": None},
        "fixture-smoke": {"pool": None, "owners": 2, "fursuits": 1, "catchers": 2},
        "journeys": {"pool": None},
    }[value["id"]]
    expected_defaults = {**base, **extras}
    expected_parameters = {
        "target": "target",
        "base_url": "local_origin",
        **{k: k for k in extras},
    }
    if (
        canonical(defaults) != canonical(expected_defaults)
        or parameters != expected_parameters
    ):
        raise ScenarioRejected
    profiles: dict[str, tuple[list[str], list[str], list[str], list[float]]] = {
        "smoke": (
            ["player"],
            [
                "identity_preflight",
                "token_setup",
                "me_first",
                "me_second",
                "identity_final",
            ],
            ["same_authenticated_identity"],
            [],
        ),
        "pool-smoke": (
            ["player"],
            [
                "identity_preflight",
                "lease",
                "token_setup",
                "me_first",
                "heartbeat",
                "token_refresh_wait",
                "me_second",
                "identity_final",
                "release",
            ],
            ["distinct_authenticated_identities", "token_refresh"],
            [61.0],
        ),
        "fixture-smoke": (
            ["owner", "catcher"],
            [
                "identity_preflight",
                "retention_preflight",
                "lease",
                "token_setup",
                "provision",
                "fixture_reads",
                "reconciliation",
                "identity_final",
                "cleanup",
                "retain_on_failure",
                "release",
            ],
            ["isolated_convention", "photo_bearing_active_fursuits"],
            [],
        ),
        "journeys": (
            ["owner", "catcher", "outsider"],
            [
                "identity_preflight",
                "retention_preflight",
                "lease",
                "token_setup",
                "provision",
                *JOURNEYS,
                "reconciliation",
                "identity_final",
                "cleanup",
                "retain_on_failure",
                "release",
            ],
            ["isolated_convention", "fixed_seven_identities", "public_api_journeys"],
            [],
        ),
    }
    for key, expected_value in zip(
        ("roles", "operations", "assumptions", "waits_seconds"),
        profiles[value["id"]],
        strict=True,
    ):
        if canonical(value[key]) != canonical(expected_value):
            raise ScenarioRejected
    return value


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def validate_catalog(root: Path | None = None) -> None:
    """Verify digests and every committed descriptor version in full Git history."""
    directory = root / RELATIVE if root is not None else CATALOG
    if root is None:
        root = next(
            (parent for parent in CATALOG.parents if (parent / ".git").exists()), None
        )
    try:
        current = {p.name: _entry(p) for p in directory.glob("*.json")}
        if not current:
            raise ScenarioRejected
        if root is not None and (root / ".git").exists():
            if _git(root, "rev-parse", "--is-shallow-repository") != "false":
                raise ScenarioRejected
            historical: dict[str, object] = {}
            for sha in _git(root, "rev-list", "HEAD", "--", RELATIVE).splitlines():
                for name in _git(
                    root, "ls-tree", "-r", "--name-only", sha, "--", RELATIVE
                ).splitlines():
                    path = Path(name)
                    if not name.endswith(".json") or path.parent != Path(RELATIVE):
                        continue
                    value = json.loads(
                        _git(root, "show", f"{sha}:{name}"), object_pairs_hook=_pairs
                    )
                    filename = path.name
                    if filename in historical and historical[filename] != value:
                        raise ScenarioRejected
                    historical[filename] = value
            for filename, value in historical.items():
                if current.get(filename) != value:
                    raise ScenarioRejected
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, RecursionError):
        raise ScenarioRejected from None


def resolve_scenario(
    command: str, version: int, config: Mapping[str, object]
) -> dict[str, object]:
    try:
        if command not in IDS or type(version) is not int or version != 1:
            raise ScenarioRejected
        entry = _entry(CATALOG / f"{command}-v{version}.json")
        descriptor = {k: v for k, v in entry.items() if k != "descriptor_digest"}
        defaults = descriptor["configuration"]["defaults"]
        if set(config) - set(defaults):
            raise ScenarioRejected
        required: set[str] = {"pool"} if command != "smoke" else set()
        if command == "pool-smoke":
            required.add("count")
        if not required <= set(config):
            raise ScenarioRejected
        effective = {**defaults, **config}
        if effective["target"] not in ("staging", "local"):
            raise ScenarioRejected
        if command != "smoke" and effective["target"] != "staging":
            raise ScenarioRejected
        if effective["base_url"] is not None and not isinstance(
            effective["base_url"], str
        ):
            raise ScenarioRejected
        if effective["target"] == "local":
            effective["base_url"] = effective["base_url"] or LOCAL_ORIGINS[0]
            if effective["base_url"] not in LOCAL_ORIGINS:
                raise ScenarioRejected
        elif effective["base_url"] is not None:
            raise ScenarioRejected
        if "pool" in effective and (
            not isinstance(effective["pool"], str)
            or re.fullmatch(r"[a-z0-9]{1,12}", effective["pool"]) is None
        ):
            raise ScenarioRejected
        for key, maximum in (
            ("count", 1000),
            ("owners", 50),
            ("fursuits", 5),
            ("catchers", 200),
        ):
            if key in effective and (
                type(effective[key]) is not int
                or not 1 <= cast(int, effective[key]) <= maximum
            ):
                raise ScenarioRejected
        return {
            "id": command,
            "version": version,
            "descriptor": descriptor,
            "descriptor_digest": entry["descriptor_digest"],
            "configuration": effective,
        }
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ScenarioRejected from None
