"""Fail-closed, credential-free readiness preflight for the exact Staging origin."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from http.client import HTTPException
from pathlib import Path
from typing import Final, TypedDict, cast

_STAGING_URL: Final = "https://staging.tailtag.app"
_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_MAX_RESPONSE_BYTES: Final = 4096


class BackendIdentity(TypedDict):
    source_sha: str
    deployment_id: str
    environment: str


class TargetSafetyError(Exception):
    """A fixed safe denial for uncertain or unsafe preflight observations."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _fetch_json(url: str) -> object:
    """Fetch one bounded JSON object without proxy or redirect behavior."""
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            if response.getcode() != 200 or response.geturl() != url:
                raise TargetSafetyError
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except (
        HTTPException,
        OSError,
        RecursionError,
        TimeoutError,
        urllib.error.URLError,
    ):
        raise TargetSafetyError from None
    if len(body) > _MAX_RESPONSE_BYTES:
        raise TargetSafetyError
    try:
        parsed = json.loads(body, object_pairs_hook=_reject_duplicate_keys)
    except (RecursionError, UnicodeError, json.JSONDecodeError, ValueError):
        raise TargetSafetyError from None
    if not isinstance(parsed, dict):
        raise TargetSafetyError
    return cast(dict[str, object], parsed)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _validate_identity(
    value: object, *, expected_environment: str = "staging"
) -> BackendIdentity:
    if not isinstance(value, dict):
        raise TargetSafetyError
    identity = cast(dict[str, object], value)
    if frozenset(identity) != _IDENTITY_FIELDS:
        raise TargetSafetyError
    source_sha = identity["source_sha"]
    deployment_id = identity["deployment_id"]
    environment = identity["environment"]
    if (
        not isinstance(source_sha, str)
        or _SOURCE_SHA.fullmatch(source_sha) is None
        or not _canonical_uuid(deployment_id)
        or environment != expected_environment
    ):
        raise TargetSafetyError
    return cast(BackendIdentity, identity)


def _canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def validate_target(base_url: str) -> BackendIdentity:
    """Return observed safe identity only for the exact, healthy Staging target."""
    if base_url != _STAGING_URL:
        raise TargetSafetyError
    first = _validate_identity(_fetch_json(f"{base_url}/health/identity"))
    if _fetch_json(f"{base_url}/health/ready") != {"status": "ok"}:
        raise TargetSafetyError
    second = _validate_identity(_fetch_json(f"{base_url}/health/identity"))
    if second != first:
        raise TargetSafetyError
    return first


def validate_candidate_target() -> dict[str, object]:
    """Return candidate-only evidence for the one code-pinned replacement origin."""
    api_directory = Path(__file__).resolve().parents[1] / "services/api"
    if str(api_directory) not in sys.path:
        sys.path.insert(0, str(api_directory))
    from config import replacement_target_binding

    try:
        origin = replacement_target_binding.load_candidate_origin()
    except replacement_target_binding.TargetBindingError:
        raise TargetSafetyError from None
    first = _validate_identity(_fetch_json(f"{origin}/health/identity"))
    if _fetch_json(f"{origin}/health/ready") != {"status": "ok"}:
        raise TargetSafetyError
    second = _validate_identity(_fetch_json(f"{origin}/health/identity"))
    if second != first:
        raise TargetSafetyError
    return {"phase": "candidate", "identity": first}


def validate_development_candidate_target(expected_sha: str | None) -> BackendIdentity:
    """Verify the pinned public Development target and optional event source."""
    api_directory = Path(__file__).resolve().parents[1] / "services/api"
    if str(api_directory) not in sys.path:
        sys.path.insert(0, str(api_directory))
    from config import replacement_target_binding

    configured_url = os.environ.get("TAILTAG_DEVELOPMENT_API_BASE_URL")
    if not isinstance(configured_url, str) or not configured_url.startswith("https://"):
        raise TargetSafetyError
    try:
        origin = replacement_target_binding.pinned_development_candidate_origin(
            configured_url.removeprefix("https://")
        )
    except replacement_target_binding.TargetBindingError:
        raise TargetSafetyError from None
    if configured_url != origin:
        raise TargetSafetyError
    if expected_sha is not None and _SOURCE_SHA.fullmatch(expected_sha) is None:
        raise TargetSafetyError
    first = _validate_identity(
        _fetch_json(f"{origin}/health/identity"), expected_environment="development"
    )
    if expected_sha is not None and first["source_sha"] != expected_sha:
        raise TargetSafetyError
    if _fetch_json(f"{origin}/health/ready") != {"status": "ok"}:
        raise TargetSafetyError
    second = _validate_identity(
        _fetch_json(f"{origin}/health/identity"), expected_environment="development"
    )
    if second != first:
        raise TargetSafetyError
    return first


def main() -> int:
    """Validate one explicit target and emit only the captured safe tuple."""
    if len(sys.argv) != 2:
        print("FAIL staging preflight unavailable", file=sys.stderr)
        return 1
    try:
        if sys.argv[1] == "--development-current":
            result = validate_development_candidate_target(None)
        elif sys.argv[1] == "--development-candidate":
            expected_sha = os.environ.get("TAILTAG_EXPECTED_SOURCE_SHA")
            if expected_sha is None:
                raise TargetSafetyError
            result = validate_development_candidate_target(expected_sha)
        elif sys.argv[1] == "--candidate":
            result = validate_candidate_target()
        else:
            result = validate_target(sys.argv[1])
        print(json.dumps(result))
    except TargetSafetyError:
        label = "development" if sys.argv[1].startswith("--development-") else "staging"
        print(f"FAIL {label} preflight unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
