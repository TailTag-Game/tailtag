"""Fail-closed, credential-free readiness preflight for the exact Staging origin."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.client import HTTPException
from pathlib import Path
from typing import Final, TypedDict, cast

_STAGING_URL: Final = "https://staging.tailtag.app"
_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_MAX_RESPONSE_BYTES: Final = 4096
# A Render deploy that CI starts must build and run the pre-deploy migration
# before the new SHA serves traffic.
_RENDER_DEPLOY_DEADLINE_SECONDS: Final = 20 * 60
_RENDER_DEPLOY_RETRY_SECONDS: Final = 15
# The public Render Staging origin follows the phase. staging.tailtag.app
# serves Virginia Staging since the #452 cutover.
_RENDER_STAGING_PHASE: str = "canonical"
_RENDER_STAGING_HOST: Final = "tailtag-api-stg.onrender.com"
_RENDER_STAGING_FLAG: Final = "--render-staging"
_DEVELOPMENT_FLAGS: Final = frozenset(
    {
        "--render-development-current",
        "--render-development-candidate",
    }
)


class RenderBackendIdentity(TypedDict):
    """Render sets no runtime deploy ID, so its identity reports null."""

    source_sha: str
    deployment_id: None
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
) -> RenderBackendIdentity:
    if not isinstance(value, dict):
        raise TargetSafetyError
    identity = cast(dict[str, object], value)
    if frozenset(identity) != _IDENTITY_FIELDS:
        raise TargetSafetyError
    source_sha = identity["source_sha"]
    if (
        not isinstance(source_sha, str)
        or _SOURCE_SHA.fullmatch(source_sha) is None
        or identity["deployment_id"] is not None
        or identity["environment"] != expected_environment
    ):
        raise TargetSafetyError
    return cast(RenderBackendIdentity, identity)


def render_staging_origin() -> str:
    """Return the public Render Staging origin for the current phase."""
    if _RENDER_STAGING_PHASE == "canonical":
        return _STAGING_URL
    api_directory = Path(__file__).resolve().parents[1] / "services/api"
    if str(api_directory) not in sys.path:
        sys.path.insert(0, str(api_directory))
    from config import replacement_target_binding

    try:
        return replacement_target_binding.pinned_render_origin(
            "staging", _RENDER_STAGING_HOST
        )
    except replacement_target_binding.TargetBindingError:
        raise TargetSafetyError from None


def validate_render_staging_target(
    expected_sha: str | None = None,
) -> RenderBackendIdentity:
    """Make one stable-identity readiness observation of Render Staging."""
    origin = render_staging_origin()
    if expected_sha is not None and _SOURCE_SHA.fullmatch(expected_sha) is None:
        raise TargetSafetyError
    first = _validate_identity(_fetch_json(f"{origin}/health/identity"))
    if expected_sha is not None and first["source_sha"] != expected_sha:
        raise TargetSafetyError
    if _fetch_json(f"{origin}/health/ready") != {"status": "ok"}:
        raise TargetSafetyError
    second = _validate_identity(_fetch_json(f"{origin}/health/identity"))
    if second != first:
        raise TargetSafetyError
    return first


def validate_development_candidate_target(
    expected_sha: str | None,
) -> RenderBackendIdentity:
    """Verify the pinned public Development target and optional event source."""
    api_directory = Path(__file__).resolve().parents[1] / "services/api"
    if str(api_directory) not in sys.path:
        sys.path.insert(0, str(api_directory))
    from config import replacement_target_binding

    configured_url = os.environ.get("TAILTAG_DEVELOPMENT_API_BASE_URL")
    if not isinstance(configured_url, str) or not configured_url.startswith("https://"):
        raise TargetSafetyError
    hostname = configured_url.removeprefix("https://")
    try:
        origin = replacement_target_binding.pinned_render_origin(
            "development", hostname
        )
    except replacement_target_binding.TargetBindingError:
        raise TargetSafetyError from None
    if configured_url != origin:
        raise TargetSafetyError
    if expected_sha is not None and _SOURCE_SHA.fullmatch(expected_sha) is None:
        raise TargetSafetyError
    if expected_sha is None:
        return _attempt_development_candidate(origin, None)
    deadline = time.monotonic() + _RENDER_DEPLOY_DEADLINE_SECONDS
    while True:
        try:
            return _attempt_development_candidate(origin, expected_sha)
        except TargetSafetyError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(_RENDER_DEPLOY_RETRY_SECONDS, remaining))


def _attempt_development_candidate(
    origin: str, expected_sha: str | None
) -> RenderBackendIdentity:
    """Make one stable-identity readiness observation of the Development target."""
    first = _validate_identity(
        _fetch_json(f"{origin}/health/identity"),
        expected_environment="development",
    )
    if expected_sha is not None and first["source_sha"] != expected_sha:
        raise TargetSafetyError
    if _fetch_json(f"{origin}/health/ready") != {"status": "ok"}:
        raise TargetSafetyError
    second = _validate_identity(
        _fetch_json(f"{origin}/health/identity"),
        expected_environment="development",
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
        if sys.argv[1] in _DEVELOPMENT_FLAGS:
            expected_sha = None
            if sys.argv[1].endswith("-candidate"):
                expected_sha = os.environ.get("TAILTAG_EXPECTED_SOURCE_SHA")
                if expected_sha is None:
                    raise TargetSafetyError
            result = validate_development_candidate_target(expected_sha)
        elif sys.argv[1] == _RENDER_STAGING_FLAG:
            result = validate_render_staging_target()
        else:
            raise TargetSafetyError
        print(json.dumps(result))
    except TargetSafetyError:
        label = "development" if sys.argv[1] in _DEVELOPMENT_FLAGS else "staging"
        print(f"FAIL {label} preflight unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
