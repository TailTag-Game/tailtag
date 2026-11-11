"""Read the immutable build identity artifact and explicit host runtime fields."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypedDict, cast

_METADATA_PATH: Final = Path("/opt/tailtag/build-identity.json")
_SOURCE_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")


class Identity(TypedDict):
    """The only fields safe to pass to the deployment join command."""

    source_sha: str | None
    deployment_id: str | None
    environment: str | None


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

    # Import here, not at module load: the binding module resolves the operator
    # home directory at import, and every settings import loads this module.
    from config import replacement_target_binding

    # A retired-host marker raises here, whether or not Render variables exist.
    if replacement_target_binding.runtime_host(environment) == "render":
        # Render sets no runtime deploy ID. Only the matched pin names the
        # environment, so a service display name cannot select one.
        render_environment = replacement_target_binding.validate_runtime_target(
            environment
        )
        if render_environment == "staging" and source_sha is None:
            raise ValueError("staging identity incomplete")
        return {
            "source_sha": source_sha,
            "deployment_id": None,
            "environment": render_environment,
        }

    return {"source_sha": source_sha, "deployment_id": None, "environment": None}


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
