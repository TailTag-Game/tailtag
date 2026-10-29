"""Read the immutable build identity artifact and explicit Railway runtime fields."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypedDict, cast

_METADATA_PATH: Final = Path("/opt/tailtag/build-identity.json")
_SOURCE_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_ENVIRONMENT_PATTERN: Final = re.compile(r"[a-z][a-z0-9-]{0,62}")


class Identity(TypedDict):
    """The only fields safe to pass to the deployment join command."""

    source_sha: str | None
    deployment_id: str | None
    environment: str | None


def _valid_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value)) if str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


def _load_identity(metadata_path: Path, environment: Mapping[str, str]) -> Identity:
    """Load the fixed build artifact without consulting runtime source metadata."""
    source_sha: str | None = None
    if metadata_path.exists():
        try:
            raw_metadata: object = json.loads(metadata_path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("identity metadata invalid") from None
        if not isinstance(raw_metadata, dict):
            raise ValueError("identity metadata invalid")
        metadata = cast(dict[str, object], raw_metadata)
        if set(metadata) != {"source_sha"}:
            raise ValueError("identity metadata invalid")
        stored_source_sha = metadata["source_sha"]
        if stored_source_sha is not None:
            if not isinstance(
                stored_source_sha, str
            ) or not _SOURCE_SHA_PATTERN.fullmatch(stored_source_sha):
                raise ValueError("identity metadata invalid")
            source_sha = stored_source_sha

    environment_name = environment.get("RAILWAY_ENVIRONMENT_NAME")
    if environment_name is not None and not _ENVIRONMENT_PATTERN.fullmatch(
        environment_name
    ):
        raise ValueError("runtime identity invalid")

    deployment_id = environment.get("RAILWAY_DEPLOYMENT_ID")
    if deployment_id is not None and _valid_uuid(deployment_id) is None:
        raise ValueError("runtime identity invalid")

    if environment_name == "staging" and (source_sha is None or deployment_id is None):
        raise ValueError("staging identity incomplete")
    if deployment_id is not None and environment_name is None:
        raise ValueError("runtime identity incomplete")

    return {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": environment_name,
    }


def get_identity() -> Identity:
    """Read the production artifact and actual process environment."""
    return _load_identity(_METADATA_PATH, os.environ)


def main() -> int:
    """Render a safe identity tuple for a selected deployment instance."""
    try:
        print(json.dumps(get_identity()))
    except ValueError:
        print("FAIL build identity unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
