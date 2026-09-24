"""Fail-closed first migration for the replacement Railway API instances."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final

_BUILD_METADATA_PATH: Path = Path("/opt/tailtag/build-identity.json")
_EXPECTED_BINDING_DIGESTS: Final = {
    "development": "4f9d3738265641df9a2d1f94c9748884e35270524713295786b2bb30bd9c8daa",
    "staging": "083e5cec1d20a62b89b3989b1745d57e24489634cdec712cc17eb6ce997c6ac3",
}


class _GuardFailure(Exception):
    """A rejected target or database before migration begins."""


def _runtime_environment() -> str:
    from config import build_identity, replacement_target_binding

    if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.production":
        raise _GuardFailure
    replacement_target_binding.validate_runtime_target(os.environ)
    environment = os.environ["RAILWAY_ENVIRONMENT_NAME"]
    identity = build_identity._load_identity(  # pyright: ignore[reportPrivateUsage]
        _BUILD_METADATA_PATH, os.environ
    )
    if identity["source_sha"] is None or identity["deployment_id"] is None:
        raise _GuardFailure
    if environment == "staging" and os.environ.get(
        "TAILTAG_STAGING_TARGET_PHASE"
    ) not in {"candidate", "canonical"}:
        raise _GuardFailure
    replacement_target_binding._pinned(  # pyright: ignore[reportPrivateUsage]
        f"{environment}-postgres",
        os.environ["RAILWAY_PROJECT_ID"],
        os.environ["RAILWAY_ENVIRONMENT_ID"],
        os.environ["TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID"],
    )
    return environment


def _database_digest(environment: str, name: str, cluster: str) -> str:
    fields = (
        "tailtag-postgres-first-boot-v1",
        environment,
        os.environ["RAILWAY_PROJECT_ID"],
        os.environ["RAILWAY_ENVIRONMENT_ID"],
        os.environ["TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID"],
        name,
        cluster,
    )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def _migrate(environment: str) -> None:
    import django
    from django.conf import settings
    from django.core import management
    from django.db import connections

    configured = settings.DATABASES["default"]
    if configured.get("ENGINE") != "django.db.backends.postgresql":
        raise _GuardFailure
    name, host, port = (configured.get(key) for key in ("NAME", "HOST", "PORT"))
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(host, str)
        or not host
        or not isinstance(port, str)
        or not port.isdecimal()
        or not 1 <= int(port) <= 65535
    ):
        raise _GuardFailure
    connection = connections["default"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        row = cursor.fetchone()
    if (
        row is None
        or len(row) != 2
        or not isinstance(row[0], str)
        or row[0] != name
        or isinstance(row[1], bool)
        or not isinstance(row[1], int)
        or row[1] <= 0
    ):
        raise _GuardFailure
    physical = connection.connection
    expected = _EXPECTED_BINDING_DIGESTS.get(environment)
    if (
        physical is None
        or expected is None
        or _database_digest(environment, row[0], str(row[1])) != expected
    ):
        raise _GuardFailure

    def refuse_reconnect() -> None:
        raise _GuardFailure

    def refuse_any_connect(self: object) -> None:
        raise _GuardFailure

    def require_verified_handle() -> None:
        if connection.connection is not physical or physical.closed:
            raise _GuardFailure

    # A migration can obtain another DatabaseWrapper for the same alias, even
    # in this process. Seal the configured PostgreSQL backend class as well as
    # the verified instance so no wrapper may open another physical session.
    type(connection).connect = refuse_any_connect
    connection.connect = refuse_reconnect  # type: ignore[method-assign]
    # Reject a handle replaced without following Django's connect path.
    connection.ensure_connection = require_verified_handle  # type: ignore[method-assign]
    require_verified_handle()
    django.setup()
    require_verified_handle()
    try:
        management.call_command(
            "migrate", database="default", interactive=False, skip_checks=False
        )
        if connection.connection is not physical or physical.closed:
            raise RuntimeError
    except BaseException:  # noqa: BLE001 - never leak a migration traceback
        raise _MigrationFailure from None


class _MigrationFailure(Exception):
    """Migration may have committed some work or lost acknowledgement."""


def main() -> int:
    """Suppress process output and emit one fixed completion classification."""
    saved_stdout = os.dup(1)
    try:
        with open(os.devnull, "wb", buffering=0) as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
        try:
            environment = _runtime_environment()
            _migrate(environment)
            classification = "PASS"
        except _MigrationFailure:
            classification = "FAIL_MIGRATION"
        except BaseException:  # noqa: BLE001 - never leak setup/guard failures
            classification = "FAIL_GUARD"
        os.write(saved_stdout, f"{classification}\n".encode("ascii"))
        return 0 if classification == "PASS" else 1
    finally:
        os.close(saved_stdout)


if __name__ == "__main__":
    raise SystemExit(main())
