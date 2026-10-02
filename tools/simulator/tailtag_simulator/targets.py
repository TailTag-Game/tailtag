"""Closed target set and fail-closed backend identity verification (A-6, A-7)."""

import re
import uuid
from dataclasses import dataclass
from typing import Final, cast

from tailtag_simulator.client import ApiClient

STAGING_ORIGIN: Final = "https://staging.tailtag.app"
LOCAL_ORIGINS: Final = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://host.docker.internal:8000",
)
IDENTITY_PATH: Final = "/health/identity"

_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")


class TargetRejected(Exception):
    """The target name, origin, or reported identity is not an allowed target."""


@dataclass(frozen=True)
class Target:
    """A permitted target name and its exact origin. Not yet identity-verified."""

    name: str
    origin: str


@dataclass(frozen=True)
class VerifiedTarget:
    """A target whose two `/health/identity` reads agreed with its expectations."""

    target: Target
    source_sha: str | None


def resolve_target(name: str, base_url: str | None) -> Target:
    """Resolve a target name; there is no way to name Production or Development."""
    if name == "staging" and base_url is None:
        return Target("staging", STAGING_ORIGIN)
    if name == "local" and (base_url is None or base_url in LOCAL_ORIGINS):
        return Target("local", base_url or LOCAL_ORIGINS[0])
    raise TargetRejected


def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _is_source_sha(value: object) -> bool:
    return isinstance(value, str) and _SOURCE_SHA.fullmatch(value) is not None


async def _read_identity(client: ApiClient, target: Target) -> dict[str, object]:
    reply = await client.get(IDENTITY_PATH)
    body = reply.body
    if reply.status != 200 or not isinstance(body, dict):
        raise TargetRejected
    identity = cast(dict[str, object], body)
    if frozenset(identity) != _IDENTITY_FIELDS:
        raise TargetRejected
    source_sha = identity["source_sha"]
    deployment_id = identity["deployment_id"]
    environment = identity["environment"]
    if target.name == "staging":
        valid = (
            environment == "staging"
            and _is_source_sha(source_sha)
            and _is_canonical_uuid(deployment_id)
        )
    else:
        valid = (
            environment is None
            and deployment_id is None
            and (source_sha is None or _is_source_sha(source_sha))
        )
    if not valid:
        raise TargetRejected
    return identity


async def verify_target(client: ApiClient, target: Target) -> VerifiedTarget:
    """Require two agreeing, expected identity reads before any token is involved."""
    first = await _read_identity(client, target)
    second = await _read_identity(client, target)
    if first != second:
        raise TargetRejected
    source_sha = first["source_sha"]
    return VerifiedTarget(target, source_sha if isinstance(source_sha, str) else None)
