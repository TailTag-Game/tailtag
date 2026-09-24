"""Bind replacement Railway selectors to the reviewed, code-owned generation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

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
_CANDIDATE_HOST: Final = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)
_EXPECTED_CANDIDATE_HOST_DIGEST: Final = (
    "42686896aeb40d236f5097c0c42b77ce1ad0ac982c653883cfb2b62e8df60de9"
)
_EXPECTED_DEVELOPMENT_CANDIDATE_HOST_DIGEST: Final = (
    "6d194fe9f0785a5e90d9feaa62967fde2bc98dadf5fd5a126003e4f885f7ee41"
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


def validate_runtime_target(actual: Mapping[str, str]) -> None:
    """Join actual in-image Railway API identity to the replacement pin."""
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
        parent = path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise TargetBindingError
        flags = os.O_RDONLY | os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 65536
            ):
                raise TargetBindingError
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                document: object = json.load(stream, object_pairs_hook=_unique_object)
        finally:
            if descriptor != -1:
                os.close(descriptor)
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


def load_development_candidate_origin() -> str:
    """Read the owner-only selector and validate every replacement tuple."""
    fields = _read_local_manifest(_MANIFEST_PATH)
    selectors = {key: _uuid(fields.get(key)) for key in _SELECTOR_KEYS}
    validate_selectors(selectors)
    hostname = fields.get(_DEVELOPMENT_HOST_KEY)
    if not isinstance(hostname, str):
        raise TargetBindingError
    return pinned_development_candidate_origin(hostname)
