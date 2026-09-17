"""Join a backend build identity to one exact Railway Staging deployment."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Final, TypedDict, cast

_PROJECT_ID: Final = "85324de4-be6a-49c3-a3f9-6cac13877849"
_SERVICE_ID: Final = "2247da27-97df-4d5d-b1dc-d21eeb7901d9"
_SOURCE_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_QUERY: Final = """query DeploymentIdentity($id: String!) {
  deployment(id: $id) {
    id
    createdAt
    meta
    projectId
    environment { name }
    serviceId
  }
}"""
_LOOKUP_TIMEOUT_SECONDS: Final = 30


class BackendIdentity(TypedDict):
    source_sha: str
    deployment_id: str
    environment: str


class DeploymentIdentity(BackendIdentity):
    deployment_timestamp: str


def _valid_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value)) if str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


def _validate_identity(value: object) -> BackendIdentity:
    if not isinstance(value, dict):
        raise TypeError("identity invalid")
    identity = cast(dict[str, object], value)
    if set(identity) != set(_IDENTITY_FIELDS):
        raise ValueError("identity invalid")
    source_sha = identity.get("source_sha")
    deployment_id = identity.get("deployment_id")
    environment = identity.get("environment")
    if (
        not isinstance(source_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(source_sha) is None
        or _valid_uuid(deployment_id) is None
        or environment != "staging"
    ):
        raise ValueError("identity invalid")
    return {
        "source_sha": source_sha,
        "deployment_id": cast(str, deployment_id),
        "environment": cast(str, environment),
    }


def _valid_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return value


def join_deployment(
    identity: Mapping[str, object], record: Mapping[str, object]
) -> DeploymentIdentity:
    """Validate that an exact Railway record proves the supplied Staging identity."""
    validated = _validate_identity(identity)
    metadata = record.get("meta")
    record_environment = record.get("environment")
    timestamp = _valid_timestamp(record.get("createdAt"))
    if (
        record.get("id") != validated["deployment_id"]
        or not isinstance(metadata, Mapping)
        or not isinstance(record_environment, Mapping)
        or record.get("projectId") != _PROJECT_ID
        or record.get("serviceId") != _SERVICE_ID
        or timestamp is None
    ):
        raise ValueError("deployment record invalid")
    if (
        cast(Mapping[str, object], metadata).get("commitHash")
        != validated["source_sha"]
        or cast(Mapping[str, object], record_environment).get("name") != "staging"
    ):
        raise ValueError("deployment record invalid")
    return {
        **validated,
        "deployment_timestamp": timestamp,
    }


def _read_identity() -> BackendIdentity:
    try:
        raw_identity: object = json.load(sys.stdin)
        return _validate_identity(raw_identity)
    except (TypeError, UnicodeError, json.JSONDecodeError, OSError, ValueError):
        raise ValueError("identity input invalid") from None


def _query_deployment(deployment_id: str) -> Mapping[str, object]:
    completed = subprocess.run(
        [
            "railway",
            "api",
            _QUERY,
            "--variables",
            json.dumps({"id": deployment_id}),
        ],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=_LOOKUP_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise ValueError("deployment lookup failed")
    try:
        raw_response: object = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("deployment lookup failed") from None
    if not isinstance(raw_response, dict):
        raise TypeError("deployment lookup failed")
    response = cast(dict[str, object], raw_response)
    if response.get("errors"):
        raise ValueError("deployment lookup failed")
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise TypeError("deployment lookup failed")
    deployment = cast(Mapping[str, object], data).get("deployment")
    if not isinstance(deployment, Mapping):
        raise TypeError("deployment lookup failed")
    return cast(Mapping[str, object], deployment)


def main() -> int:
    """Read one safe tuple, make one exact-ID lookup, and render safe evidence."""
    try:
        identity = _read_identity()
        result = join_deployment(identity, _query_deployment(identity["deployment_id"]))
    except (OSError, TypeError, UnicodeError, ValueError, subprocess.SubprocessError):
        print("FAIL deployment identity unavailable", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
