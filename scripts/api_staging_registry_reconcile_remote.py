"""Value-free, read-only #204 private/registry/database comparison."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import Mapping
from typing import Final, Protocol, cast

_SHA: Final = re.compile(r"[0-9a-f]{40}\Z")
_HASH: Final = re.compile(r"[0-9a-f]{64}\Z")
_CLUSTER: Final = re.compile(r"[1-9][0-9]*\Z")
_DATABASE: Final = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_PRIVATE_KEYS: Final = frozenset(
    {
        "TAILTAG_STAGING_RESET_ENABLED",
        "TAILTAG_STAGING_RESET_ID",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
        "TAILTAG_STAGING_DATABASE_HOST",
        "TAILTAG_STAGING_DATABASE_PORT",
        "TAILTAG_STAGING_DATABASE_NAME",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
        "TAILTAG_STAGING_RESET_MEDIA_KEY",
    }
)
_EQUALITY_KEYS: Final = (
    "reset_environment_id",
    "database_name_private_registry",
    "cluster_identifier_private_registry",
    "database_name_actual_private",
    "database_name_actual_registry",
    "cluster_identifier_actual_private",
    "cluster_identifier_actual_registry",
    "owner_binding_private_registry",
    "catcher_binding_private_registry",
    "media_binding_private_registry",
    "database_host_runtime_private",
    "database_port_runtime_private",
)
_STRUCTURAL_KEYS: Final = (
    "registry_singleton",
    "registry_structure",
    "root_completeness",
)


class _UserBinding(Protocol):
    clerk_user_id: str


class _Registry(Protocol):
    pk: int
    environment_id: uuid.UUID
    cluster_identifier: str
    database_name: str
    owner: _UserBinding
    catcher: _UserBinding
    media_key: str
    convention_id: int | None
    first_fursuit_id: int | None
    second_fursuit_id: int | None


class _Private(Protocol):
    @property
    def environment_id(self) -> uuid.UUID: ...

    @property
    def cluster_identifier(self) -> str: ...

    @property
    def database_host(self) -> str: ...

    @property
    def database_port(self) -> str: ...

    @property
    def database_name(self) -> str: ...

    @property
    def owner_clerk_id(self) -> str: ...

    @property
    def catcher_clerk_id(self) -> str: ...

    @property
    def media_key(self) -> str: ...


class _AmbiguousRegistry(Exception):
    """The singleton lookup returned multiple rows."""


def _equal(left: object, right: object) -> str:
    return "MATCH" if left == right else "MISMATCH"


def compare_authorities(
    private: _Private,
    registry: _Registry | None,
    actual_database_name: str,
    actual_cluster_identifier: str,
    runtime_host: str,
    runtime_port: str,
) -> dict[str, str]:
    """Return only fixed statuses; never render either side of a comparison."""
    if registry is None:
        return {
            "registry_singleton": "MISSING",
            **{
                key: "INDETERMINATE" for key in (*_STRUCTURAL_KEYS[1:], *_EQUALITY_KEYS)
            },
        }
    if registry.pk != 1:
        return {
            "registry_singleton": "AMBIGUOUS",
            **{
                key: "INDETERMINATE" for key in (*_STRUCTURAL_KEYS[1:], *_EQUALITY_KEYS)
            },
        }
    roots = (
        registry.convention_id,
        registry.first_fursuit_id,
        registry.second_fursuit_id,
    )
    complete_roots = (
        all(root is None for root in roots) or all(root is not None for root in roots)
    ) and (roots[1] is None or roots[1] != roots[2])
    valid_registry = (
        registry.environment_id.version == 4
        and _CLUSTER.fullmatch(registry.cluster_identifier) is not None
        and _DATABASE.fullmatch(registry.database_name) is not None
        and registry.database_name != "postgres"
    )
    return {
        "registry_singleton": "PASS",
        "registry_structure": "PASS" if valid_registry else "MISMATCH",
        "root_completeness": "PASS" if complete_roots else "MISMATCH",
        "reset_environment_id": _equal(private.environment_id, registry.environment_id),
        "database_name_private_registry": _equal(
            private.database_name, registry.database_name
        ),
        "cluster_identifier_private_registry": _equal(
            private.cluster_identifier, registry.cluster_identifier
        ),
        "database_name_actual_private": _equal(
            actual_database_name, private.database_name
        ),
        "database_name_actual_registry": _equal(
            actual_database_name, registry.database_name
        ),
        "cluster_identifier_actual_private": _equal(
            actual_cluster_identifier, private.cluster_identifier
        ),
        "cluster_identifier_actual_registry": _equal(
            actual_cluster_identifier, registry.cluster_identifier
        ),
        "owner_binding_private_registry": _equal(
            private.owner_clerk_id, registry.owner.clerk_user_id
        ),
        "catcher_binding_private_registry": _equal(
            private.catcher_clerk_id, registry.catcher.clerk_user_id
        ),
        "media_binding_private_registry": _equal(private.media_key, registry.media_key),
        "database_host_runtime_private": _equal(runtime_host, private.database_host),
        "database_port_runtime_private": _equal(runtime_port, private.database_port),
    }


def target_matches(request: Mapping[str, object]) -> bool:
    """Bind the SSH worker to the approved image, runtime and DB URL."""
    from config.build_identity import get_identity

    if frozenset(request) != frozenset(
        {"identity", "database_url_fingerprint", "configuration"}
    ):
        return False
    identity = request.get("identity")
    fingerprint = request.get("database_url_fingerprint")
    if not isinstance(identity, dict) or not isinstance(fingerprint, str):
        return False
    values = cast(dict[str, object], identity)
    if frozenset(values) != frozenset({"source_sha", "deployment_id", "environment"}):
        return False
    source_sha, deployment_id, environment = (
        values["source_sha"],
        values["deployment_id"],
        values["environment"],
    )
    if not isinstance(source_sha, str) or _SHA.fullmatch(source_sha) is None:
        return False
    if not isinstance(deployment_id, str):
        return False
    try:
        if str(uuid.UUID(deployment_id)) != deployment_id:
            return False
    except ValueError:
        return False
    if environment != "staging" or get_identity() != values:
        return False
    if _HASH.fullmatch(fingerprint) is None:
        return False
    from config.replacement_target_binding import (
        TargetBindingError,
        validate_runtime_target,
    )

    if os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging":
        return False
    try:
        validate_runtime_target(os.environ)
    except TargetBindingError:
        return False
    return (
        hashlib.sha256(os.environ.get("DATABASE_URL", "").encode()).hexdigest()
        == fingerprint
    )


def load_configuration(environment: Mapping[str, str]) -> _Private:
    from rehearsal.safety import load_configuration as checked_load

    return checked_load(environment)


def read_registry() -> _Registry | None:
    from rehearsal.models import StagingResetIdentity

    rows = list(StagingResetIdentity.objects.select_related("owner", "catcher")[:2])
    if len(rows) > 1:
        raise _AmbiguousRegistry
    return cast(_Registry | None, rows[0] if rows else None)


def read_actual_database_facts() -> tuple[str, str, str, str]:
    from django.conf import settings

    from rehearsal.safety import _database_facts  # pyright: ignore[reportPrivateUsage]

    database_name, cluster_identifier = _database_facts()
    database = settings.DATABASES["default"]
    return (
        database_name,
        cluster_identifier,
        str(database.get("HOST", "")),
        str(database.get("PORT", "")),
    )


def run_request(request: Mapping[str, object]) -> dict[str, object]:
    """Fail closed and return only allowlisted status words."""
    try:
        if not target_matches(request):
            return {"result": "FAIL_INVALID_INPUT", "checks": {}}
    except Exception:  # noqa: BLE001
        return {"result": "FAIL_EXECUTION", "checks": {}}
    raw_configuration = request.get("configuration")
    if not isinstance(raw_configuration, dict):
        return {"result": "FAIL_CONFIGURATION", "checks": {}}
    values = cast(dict[object, object], raw_configuration)
    if frozenset(values) != _PRIVATE_KEYS or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in values.items()
    ):
        return {"result": "FAIL_CONFIGURATION", "checks": {}}
    try:
        private = load_configuration({**os.environ, **cast(dict[str, str], values)})
    except Exception:  # noqa: BLE001
        return {"result": "FAIL_CONFIGURATION", "checks": {}}
    try:
        registry = read_registry()
        actual_name, actual_cluster, runtime_host, runtime_port = (
            read_actual_database_facts()
        )
        checks = compare_authorities(
            private,
            registry,
            actual_name,
            actual_cluster,
            runtime_host,
            runtime_port,
        )
    except _AmbiguousRegistry:
        checks = {
            "registry_singleton": "AMBIGUOUS",
            **{
                key: "INDETERMINATE" for key in (*_STRUCTURAL_KEYS[1:], *_EQUALITY_KEYS)
            },
        }
    except Exception:  # noqa: BLE001
        return {"result": "FAIL_QUERY", "checks": {}}
    result = (
        "PASS"
        if checks["registry_singleton"] == "PASS"
        and checks["registry_structure"] == "PASS"
        and checks["root_completeness"] == "PASS"
        and all(checks[key] == "MATCH" for key in _EQUALITY_KEYS)
        else "MISMATCH"
    )
    return {"result": result, "checks": checks}
