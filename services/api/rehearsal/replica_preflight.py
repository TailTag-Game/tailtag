"""Read the public identity of the replica API for the guarded reset procedure."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.client import HTTPException
from typing import Final, cast

from django.conf import settings

from config import build_identity, replica_binding

_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_MAX_RESPONSE_BYTES: Final = 4096


class ReplicaPreflightError(Exception):
    """A fixed safe denial for uncertain or unsafe preflight observations."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _fetch_json(url: str) -> dict[str, object]:
    """Fetch one bounded JSON object without proxy or redirect behavior."""
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            if response.getcode() != 200 or response.geturl() != url:
                raise ReplicaPreflightError
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except (
        HTTPException,
        OSError,
        RecursionError,
        TimeoutError,
        urllib.error.URLError,
    ):
        raise ReplicaPreflightError from None
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ReplicaPreflightError
    try:
        parsed = json.loads(body, object_pairs_hook=_reject_duplicate_keys)
    except (RecursionError, UnicodeError, ValueError):
        raise ReplicaPreflightError from None
    if not isinstance(parsed, dict):
        raise ReplicaPreflightError
    return cast(dict[str, object], parsed)


def validate_target() -> dict[str, str]:
    """Return the public identity only if it is this job's own replica build."""
    try:
        host = replica_binding.validate_run_app_host(settings.ALLOWED_HOSTS)
    except replica_binding.ReplicaBindingError:
        raise ReplicaPreflightError from None
    identity = _fetch_json(f"https://{host}/health/identity")
    deployment_id = identity.get("deployment_id")
    if (
        frozenset(identity) != _IDENTITY_FIELDS
        or identity["environment"] != "replica"
        or identity["source_sha"] != build_identity.get_identity()["source_sha"]
        or not isinstance(deployment_id, str)
        or not deployment_id.startswith("tailtag-api-replica-")
    ):
        raise ReplicaPreflightError
    return cast(dict[str, str], identity)
