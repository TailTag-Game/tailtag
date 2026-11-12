"""Bind replacement Render runtimes to reviewed, code-owned pins."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

from config.owner_only import open_owner_only_file

_ERROR: Final = "Replacement target binding unavailable"
# Railway is retired (#412). Any process variable with this prefix fails closed.
_RETIRED_HOST_MARKER_PREFIX: Final = "RAILWAY_"
_MANIFEST_FILE: Final = Path(".config/tailtag/staging-clean-rebuild-targets.json")
_RENDER_STAGING_SERVICE_KEY: Final = "render_staging_api_service_id"
_CANDIDATE_HOST: Final = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)
_EXPECTED_DEVELOPMENT_CLERK_PORTAL_ORIGIN_DIGEST: Final = (
    "3cde8d9faf99b1089cc040f1db5342845a83120fea890634a3ad0ec85c9c4179"
)

_RENDER_ENVIRONMENTS: Final = ("development", "staging")
_RENDER_SERVICE_ID: Final = re.compile(r"srv-[a-z0-9]{1,60}")
_RENDER_CRON_JOB_ID: Final = re.compile(r"crn-[a-z0-9]{1,60}")
_EXPECTED_RENDER_DIGESTS: Final[dict[str, str]] = {
    "development": "64d011b1894192693c980dd0f18d90965df3f56b45b2c604a2a79e2ca2617010",
    # Virginia Staging (ADR 0012, #452).
    "staging": "38c9d94cbcb405005988ca158bc4c81e23a066b13b538e8d8aa7148963a94470",
}
# The catch request cleanup cron jobs (#507 G15). A cron job is its own Render
# service, with a `crn-` ID. Only build identity reads these pins. Guarded
# operator paths keep `validate_runtime_target`, which accepts only the `srv-`
# web services above.
_EXPECTED_RENDER_CLEANUP_DIGESTS: Final[dict[str, str]] = {
    # tailtag-cleanup-dev (Oregon).
    "development": "a4d1f810b9c9c1427f436a75a8c615a949a072d669408ed2ff26de29ef4d4d7d",
    # tailtag-cleanup-stg (Virginia).
    "staging": "91e6977c0ed9509722716919d443347c763dbdd6a46fa14e8d4abaa2f2988632",
}
_EXPECTED_RENDER_HOST_DIGESTS: Final[dict[str, str]] = {
    "development": "55770374ef59dccf72a2aa1c98a9a1eaccbd140c2924a1a60376ff0161ae72c0",
    "staging": "ba833a5e9735b26c26c656e7a62d3b484ffc6de047366439bc903907599a78f4",
}
# The owner computes this digest from their private Render reset file with
# scripts/api_staging_reset_render_digest.py. Empty admits no Render reset
# configuration. Pinned for the Virginia Staging baseline (ADR 0012, #452).
_EXPECTED_RENDER_RESET_DIGEST: Final[str] = (
    "3c974ba3ad7785c34f45395bffa625f327f263b2da642d7641b3af450b9c022f"
)
RENDER_RESET_NAMES: Final = (
    "TAILTAG_STAGING_RESET_ENABLED",
    "TAILTAG_STAGING_RESET_ID",
    "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
    "TAILTAG_STAGING_DATABASE_HOST",
    "TAILTAG_STAGING_DATABASE_PORT",
    "TAILTAG_STAGING_DATABASE_NAME",
    "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
    "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
    "TAILTAG_STAGING_RESET_MEDIA_KEY",
)
_RENDER_RUNTIME_MARKERS: Final = ("RENDER", "RENDER_SERVICE_ID")


class TargetBindingError(ValueError):
    """A fixed, sanitized target-binding failure."""

    def __init__(self) -> None:
        super().__init__(_ERROR)


def runtime_host(actual: Mapping[str, str]) -> str | None:
    """Name the one hosting platform whose runtime variables are present."""
    if any(name.startswith(_RETIRED_HOST_MARKER_PREFIX) for name in actual):
        raise TargetBindingError
    return "render" if any(name in actual for name in _RENDER_RUNTIME_MARKERS) else None


def fingerprint_render_service(environment: str, service_id: object) -> str:
    """Hash one environment and one canonical Render service ID."""
    if (
        environment not in _RENDER_ENVIRONMENTS
        or not isinstance(service_id, str)
        or _RENDER_SERVICE_ID.fullmatch(service_id) is None
    ):
        raise TargetBindingError
    return hashlib.sha256(
        f"tailtag-render-api-v1\0{environment}\0{service_id}".encode()
    ).hexdigest()


def validate_runtime_target(actual: Mapping[str, str]) -> str:
    """Join the actual in-image API identity to its pin and return its environment."""
    if runtime_host(actual) != "render" or actual.get("RENDER") != "true":
        raise TargetBindingError
    service_id = actual.get("RENDER_SERVICE_ID")
    matches = [
        environment
        for environment in _RENDER_ENVIRONMENTS
        if _EXPECTED_RENDER_DIGESTS.get(environment)
        == fingerprint_render_service(environment, service_id)
    ]
    if len(matches) != 1:
        raise TargetBindingError
    return matches[0]


def runtime_environment(actual: Mapping[str, str]) -> str:
    """Name the environment of a pinned web or cleanup cron service.

    This widens only build identity, for logs and Sentry. Every guarded operator
    path calls `validate_runtime_target`, which a cron service cannot pass.
    """
    try:
        return validate_runtime_target(actual)
    except TargetBindingError:
        pass
    job_id = actual.get("RENDER_SERVICE_ID")
    matches = [
        environment
        for environment in _RENDER_ENVIRONMENTS
        if _EXPECTED_RENDER_CLEANUP_DIGESTS.get(environment)
        == fingerprint_render_cron_job(environment, job_id)
    ]
    if len(matches) != 1:
        raise TargetBindingError
    return matches[0]


def fingerprint_render_cron_job(environment: str, job_id: object) -> str:
    """Hash one environment and one canonical Render cron job ID (#507 G15)."""
    if (
        environment not in _RENDER_ENVIRONMENTS
        or not isinstance(job_id, str)
        or _RENDER_CRON_JOB_ID.fullmatch(job_id) is None
    ):
        raise TargetBindingError
    return hashlib.sha256(
        f"tailtag-render-cleanup-v1\0{environment}\0{job_id}".encode()
    ).hexdigest()


def fingerprint_render_reset_configuration(values: Mapping[str, str]) -> str:
    """Hash exactly the nine private Render Staging reset values."""
    if frozenset(values) != frozenset(RENDER_RESET_NAMES):
        raise TargetBindingError
    fields = (
        "tailtag-render-staging-reset-v1",
        *(f"{name}={values[name]}" for name in RENDER_RESET_NAMES),
    )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def validate_render_reset_configuration(values: Mapping[str, str]) -> None:
    """Require the Render reset values to equal the owner's pinned private file."""
    if not _EXPECTED_RENDER_RESET_DIGEST or (
        fingerprint_render_reset_configuration(values) != _EXPECTED_RENDER_RESET_DIGEST
    ):
        raise TargetBindingError


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TargetBindingError
        result[key] = value
    return result


def _manifest_path() -> Path:
    # Resolved on use, so importing this module needs no operator home directory.
    return Path.home() / _MANIFEST_FILE


def _read_local_manifest(path: Path) -> dict[str, object]:
    """Read one owner-only, non-symlink manifest without exposing its values."""
    try:
        with io.TextIOWrapper(
            open_owner_only_file(path, max_bytes=65536), encoding="utf-8"
        ) as stream:
            document: object = json.load(stream, object_pairs_hook=_unique_object)
        if not isinstance(document, dict):
            raise TargetBindingError
        return cast(dict[str, object], document)
    except (OSError, RecursionError, UnicodeError, ValueError, KeyError, TypeError):
        raise TargetBindingError from None


def fingerprint_development_clerk_portal_origin(origin: object) -> str:
    """Commit to the exact HTTPS Development Clerk portal origin."""
    if (
        not isinstance(origin, str)
        or not origin.startswith("https://")
        or _CANDIDATE_HOST.fullmatch(origin.removeprefix("https://")) is None
    ):
        raise TargetBindingError
    return hashlib.sha256(
        f"tailtag-development-clerk-portal-v1\0{origin}".encode()
    ).hexdigest()


def pinned_development_clerk_portal_origin(origin: str) -> str:
    """Return only the reviewed Development Clerk portal origin."""
    if (
        fingerprint_development_clerk_portal_origin(origin)
        != _EXPECTED_DEVELOPMENT_CLERK_PORTAL_ORIGIN_DIGEST
    ):
        raise TargetBindingError
    return origin


def fingerprint_render_hostname(environment: str, hostname: object) -> str:
    """Commit to one exact lowercase Render API hostname for one environment."""
    if (
        environment not in _RENDER_ENVIRONMENTS
        or not isinstance(hostname, str)
        or _CANDIDATE_HOST.fullmatch(hostname) is None
    ):
        raise TargetBindingError
    return hashlib.sha256(
        f"tailtag-render-api-host-v1\0{environment}\0{hostname}".encode()
    ).hexdigest()


def pinned_render_origin(environment: str, hostname: str) -> str:
    """Return only the reviewed HTTPS origin of one Render environment."""
    expected = _EXPECTED_RENDER_HOST_DIGESTS.get(environment)
    if (
        expected is None
        or fingerprint_render_hostname(environment, hostname) != expected
    ):
        raise TargetBindingError
    return f"https://{hostname}"


def load_render_staging_service_id() -> str:
    """Return the Render Staging service ID only from the pinned owner-only manifest."""
    service_id = _read_local_manifest(_manifest_path()).get(_RENDER_STAGING_SERVICE_KEY)
    if (
        fingerprint_render_service("staging", service_id)
        != _EXPECTED_RENDER_DIGESTS["staging"]
    ):
        raise TargetBindingError
    return cast(str, service_id)
