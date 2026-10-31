"""Bind replacement Railway and Render runtimes to reviewed, code-owned pins."""

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
_UUID: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_ROLES: Final = frozenset(
    {"development-api", "development-postgres", "staging-api", "staging-postgres"}
)
_SELECTOR_KEYS: Final = (
    "rebuild_railway_project_id",
    "rebuild_development_environment_id",
    "rebuild_staging_environment_id",
    "rebuild_api_service_id",
    "rebuild_postgres_service_id",
)
_MANIFEST_PATH: Final = (
    Path.home() / ".config/tailtag/staging-clean-rebuild-targets.json"
)
_CANDIDATE_HOST_KEY: Final = "rebuild_staging_candidate_api_domain"
_DEVELOPMENT_HOST_KEY: Final = "rebuild_development_api_domain"
_RENDER_STAGING_SERVICE_KEY: Final = "render_staging_api_service_id"
_CANDIDATE_HOST: Final = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)
_EXPECTED_CANDIDATE_HOST_DIGEST: Final = (
    "42686896aeb40d236f5097c0c42b77ce1ad0ac982c653883cfb2b62e8df60de9"
)
_EXPECTED_DEVELOPMENT_CANDIDATE_HOST_DIGEST: Final = (
    "30064b0e3e823ac59c6108da1dd7a950154e9545f83d2da3d3585776a1ad5fb6"
)
_EXPECTED_DEVELOPMENT_CLERK_PORTAL_ORIGIN_DIGEST: Final = (
    "3cde8d9faf99b1089cc040f1db5342845a83120fea890634a3ad0ec85c9c4179"
)
_EXPECTED_DIGESTS: Final = {
    "development-api": "d67c0114b9b522306942115eb0735b9c8dca3291ab2d1cec52986c404bf9fc9a",
    "development-postgres": "6e0af05b3f6b4b0d561fe6edf9af3de960223ecfcae8d1d169bea74a0f5f6ad8",
    "staging-api": "19655575835ea83b432a7499634eb83c167acb50ba333144e2bf6b27ca96bfd6",
    "staging-postgres": "b75516fd066d0895ee63fd2f1b5f246a35ca0923150d0dfec66e2a00c1bb7a9c",
}


_RENDER_ENVIRONMENTS: Final = ("development", "staging")
_RENDER_SERVICE_ID: Final = re.compile(r"srv-[a-z0-9]{1,60}")
_EXPECTED_RENDER_DIGESTS: Final[dict[str, str]] = {
    "development": "64d011b1894192693c980dd0f18d90965df3f56b45b2c604a2a79e2ca2617010",
    "staging": "19b4021269c4003848c9aa8b9373037bd0d2c5fd00a2f7e17d13b6060d13d405",
}
_EXPECTED_RENDER_HOST_DIGESTS: Final[dict[str, str]] = {
    "development": "55770374ef59dccf72a2aa1c98a9a1eaccbd140c2924a1a60376ff0161ae72c0",
    "staging": "e4625e95b760af49f9bfa9cdbc968fe98606c371426099c82d40d9a5e3fc4d37",
}
# The owner computes this digest from their private Render reset file with
# scripts/api_staging_reset_render_digest.py. Empty admits no Render reset
# configuration. Pinned for the fresh Render Staging baseline (#410 AC5).
_EXPECTED_RENDER_RESET_DIGEST: Final[str] = (
    "f8ff2ea4e1cba6b6230c3d361a05914f4fc8e45edc912c4be17488233b32c0a6"
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
_RAILWAY_RUNTIME_MARKERS: Final = (
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_DEPLOYMENT_ID",
    "RAILWAY_SERVICE_NAME",
)
_RENDER_RUNTIME_MARKERS: Final = ("RENDER", "RENDER_SERVICE_ID")


class TargetBindingError(ValueError):
    """A fixed, sanitized target-binding failure."""

    def __init__(self) -> None:
        super().__init__(_ERROR)


def _uuid(value: object) -> str:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise TargetBindingError
    return value


def fingerprint_tuple(role: str, project: str, environment: str, service: str) -> str:
    """Hash one logical role and three canonical Railway UUIDs."""
    if role not in _ROLES:
        raise TargetBindingError
    fields = (
        "tailtag-rebuild-v1",
        role,
        *(_uuid(v) for v in (project, environment, service)),
    )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def _pinned(role: str, project: object, environment: object, service: object) -> None:
    if (
        fingerprint_tuple(role, _uuid(project), _uuid(environment), _uuid(service))
        != _EXPECTED_DIGESTS[role]
    ):
        raise TargetBindingError


def validate_selectors(selectors: Mapping[str, object]) -> None:
    """Reject a local manifest unless every replacement service matches its pin."""
    try:
        project = selectors[_SELECTOR_KEYS[0]]
        api = selectors[_SELECTOR_KEYS[3]]
        postgres = selectors[_SELECTOR_KEYS[4]]
        for name in ("development", "staging"):
            environment = selectors[f"rebuild_{name}_environment_id"]
            _pinned(f"{name}-api", project, environment, api)
            _pinned(f"{name}-postgres", project, environment, postgres)
    except (KeyError, TypeError):
        raise TargetBindingError from None


def runtime_host(actual: Mapping[str, str]) -> str | None:
    """Name the one hosting platform whose runtime variables are present."""
    railway = any(name in actual for name in _RAILWAY_RUNTIME_MARKERS)
    render = any(name in actual for name in _RENDER_RUNTIME_MARKERS)
    if railway and render:
        raise TargetBindingError
    if railway:
        return "railway"
    return "render" if render else None


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


def _render_environment(actual: Mapping[str, str]) -> str:
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


def validate_runtime_target(actual: Mapping[str, str]) -> str:
    """Join the actual in-image API identity to its pin and return its environment."""
    if runtime_host(actual) == "render":
        return _render_environment(actual)
    try:
        environment_name = actual["RAILWAY_ENVIRONMENT_NAME"]
        if environment_name not in {"development", "staging"}:
            raise TargetBindingError
        if actual["RAILWAY_SERVICE_NAME"] != "api":
            raise TargetBindingError
        _pinned(
            f"{environment_name}-api",
            actual["RAILWAY_PROJECT_ID"],
            actual["RAILWAY_ENVIRONMENT_ID"],
            actual["RAILWAY_SERVICE_ID"],
        )
    except (KeyError, TypeError):
        raise TargetBindingError from None
    return environment_name


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


def load_local_manifest(path: Path) -> dict[str, str]:
    """Read only selector fields from an owner-only, non-symlink local file."""
    fields = _read_local_manifest(path)
    try:
        return {key: _uuid(fields[key]) for key in _SELECTOR_KEYS}
    except (KeyError, TypeError):
        raise TargetBindingError from None


def fingerprint_candidate_hostname(hostname: object) -> str:
    """Commit to one exact lowercase Railway candidate hostname."""
    if not isinstance(hostname, str) or _CANDIDATE_HOST.fullmatch(hostname) is None:
        raise TargetBindingError
    return hashlib.sha256(f"tailtag-candidate-api-v1\0{hostname}".encode()).hexdigest()


def pinned_candidate_origin(hostname: str) -> str:
    """Check an exact candidate hostname against the code-owned commitment."""
    if fingerprint_candidate_hostname(hostname) != _EXPECTED_CANDIDATE_HOST_DIGEST:
        raise TargetBindingError
    return f"https://{hostname}"


def load_candidate_origin() -> str:
    """Return the sole approved HTTPS candidate origin after all local pins pass."""
    fields = _read_local_manifest(_MANIFEST_PATH)
    selectors = {key: _uuid(fields.get(key)) for key in _SELECTOR_KEYS}
    validate_selectors(selectors)
    hostname = fields.get(_CANDIDATE_HOST_KEY)
    if not isinstance(hostname, str):
        raise TargetBindingError
    return pinned_candidate_origin(hostname)


def fingerprint_development_candidate_hostname(hostname: object) -> str:
    """Commit to the exact lowercase Development API hostname."""
    if not isinstance(hostname, str) or _CANDIDATE_HOST.fullmatch(hostname) is None:
        raise TargetBindingError
    return hashlib.sha256(
        f"tailtag-development-api-v1\0{hostname}".encode()
    ).hexdigest()


def pinned_development_candidate_origin(hostname: str) -> str:
    """Return only the reviewed Development HTTPS origin."""
    if (
        fingerprint_development_candidate_hostname(hostname)
        != _EXPECTED_DEVELOPMENT_CANDIDATE_HOST_DIGEST
    ):
        raise TargetBindingError
    return f"https://{hostname}"


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


def load_development_candidate_origin() -> str:
    """Read the owner-only selector and validate every replacement tuple."""
    fields = _read_local_manifest(_MANIFEST_PATH)
    selectors = {key: _uuid(fields.get(key)) for key in _SELECTOR_KEYS}
    validate_selectors(selectors)
    hostname = fields.get(_DEVELOPMENT_HOST_KEY)
    if not isinstance(hostname, str):
        raise TargetBindingError
    return pinned_development_candidate_origin(hostname)


def load_render_staging_service_id() -> str:
    """Return the Render Staging service ID only from the pinned owner-only manifest."""
    service_id = _read_local_manifest(_MANIFEST_PATH).get(_RENDER_STAGING_SERVICE_KEY)
    if (
        fingerprint_render_service("staging", service_id)
        != _EXPECTED_RENDER_DIGESTS["staging"]
    ):
        raise TargetBindingError
    return cast(str, service_id)
