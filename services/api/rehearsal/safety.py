"""Fail-closed Staging target checks and PostgreSQL maintenance gate."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import IO, Any, Protocol, Self, cast

import psycopg
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import connection
from psycopg import sql

from config.replacement_target_binding import (
    TargetBindingError,
    validate_runtime_target,
)
from media.keys import validate_image_key

from .models import StagingResetIdentity

_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
_DNS = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
_PORT = re.compile(
    r"(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])\Z"
)


class ResetSafetyError(Exception):
    """Raised for every unsafe or uncertain reset condition."""


class _UserPrivileges(Protocol):
    is_superuser: bool


class _ReadableStorage(Protocol):
    def exists(self, name: str) -> bool: ...
    def open(self, name: str, mode: str = "rb") -> IO[bytes]: ...


@dataclass(frozen=True)
class ResetConfiguration:
    environment_id: uuid.UUID
    cluster_identifier: str
    database_host: str
    database_port: str
    database_name: str
    owner_clerk_id: str
    catcher_clerk_id: str
    media_key: str


def load_configuration(environment: Mapping[str, str]) -> ResetConfiguration:
    """Parse only the independently configured, canonical Staging facts."""
    required = (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_SERVICE_ID",
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
    try:
        values = {name: environment[name] for name in required}
    except KeyError:
        raise ResetSafetyError from None
    if (
        values["RAILWAY_ENVIRONMENT_NAME"] != "staging"
        or values["TAILTAG_STAGING_RESET_ENABLED"] != "true"
    ):
        raise ResetSafetyError
    try:
        validate_runtime_target(
            {**values, "RAILWAY_SERVICE_NAME": environment["RAILWAY_SERVICE_NAME"]}
        )
    except (KeyError, TargetBindingError):
        raise ResetSafetyError
    try:
        environment_id = uuid.UUID(values["TAILTAG_STAGING_RESET_ID"])
    except ValueError:
        raise ResetSafetyError from None
    if (
        str(environment_id) != values["TAILTAG_STAGING_RESET_ID"]
        or environment_id.version != 4
    ):
        raise ResetSafetyError
    owner, catcher = (
        values["TAILTAG_STAGING_RESET_OWNER_CLERK_ID"],
        values["TAILTAG_STAGING_RESET_CATCHER_CLERK_ID"],
    )
    cluster = values["TAILTAG_STAGING_DATABASE_SYSTEM_ID"]
    host, port, name = (
        values["TAILTAG_STAGING_DATABASE_HOST"],
        values["TAILTAG_STAGING_DATABASE_PORT"],
        values["TAILTAG_STAGING_DATABASE_NAME"],
    )
    if (
        _DECIMAL.fullmatch(cluster) is None
        or _DNS.fullmatch(host) is None
        or _PORT.fullmatch(port) is None
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name)
        or name == "postgres"
        or owner.strip() != owner
        or catcher.strip() != catcher
    ):
        raise ResetSafetyError
    if not owner or not catcher or owner == catcher:
        raise ResetSafetyError
    try:
        media_key = validate_image_key(values["TAILTAG_STAGING_RESET_MEDIA_KEY"])
    except ValueError:
        raise ResetSafetyError from None
    return ResetConfiguration(
        environment_id, cluster, host, port, name, owner, catcher, media_key
    )


def _database_facts() -> tuple[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        row = cursor.fetchone()
    return str(row[0]), str(row[1])


def validate_database(configuration: ResetConfiguration) -> None:
    """Require the actual Django target to equal its independently pinned binding."""
    database = settings.DATABASES["default"]
    try:
        name, cluster = _database_facts()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_prepared_xacts WHERE database = current_database()"
            )
            prepared = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_subscription")
            subscriptions = cursor.fetchone()[0]
            cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            executor_superuser = cursor.fetchone()[0]
    except Exception:  # noqa: BLE001
        raise ResetSafetyError from None
    if (
        str(database.get("HOST", "")),
        str(database.get("PORT", "")),
        name,
        cluster,
    ) != (
        configuration.database_host,
        configuration.database_port,
        configuration.database_name,
        configuration.cluster_identifier,
    ):
        raise ResetSafetyError
    if prepared or subscriptions or not executor_superuser:
        raise ResetSafetyError


def validate_asset(media_key: str) -> None:
    from media.storage import S3MediaStorage

    if not isinstance(default_storage, S3MediaStorage):
        raise ResetSafetyError
    try:
        storage = cast(_ReadableStorage, default_storage)
        if not storage.exists(media_key):
            raise ResetSafetyError
        source = storage.open(media_key, "rb")
        with source:
            if not source.read(1):
                raise ResetSafetyError
    except ResetSafetyError:
        raise
    except Exception:  # noqa: BLE001
        raise ResetSafetyError from None


def validate_identity(configuration: ResetConfiguration) -> StagingResetIdentity:
    """Validate the provisioned sentinel, preserved bindings, and registered asset."""
    try:
        identity = StagingResetIdentity.objects.select_related("owner", "catcher").get(
            pk=1
        )
    except StagingResetIdentity.DoesNotExist:
        raise ResetSafetyError from None
    if (
        identity.environment_id,
        identity.cluster_identifier,
        identity.database_name,
        identity.owner.clerk_user_id,
        identity.catcher.clerk_user_id,
        identity.media_key,
    ) != (
        configuration.environment_id,
        configuration.cluster_identifier,
        configuration.database_name,
        configuration.owner_clerk_id,
        configuration.catcher_clerk_id,
        configuration.media_key,
    ):
        raise ResetSafetyError
    if (
        identity.owner_id == identity.catcher_id
        or identity.owner.is_staff
        or cast(_UserPrivileges, identity.owner).is_superuser
        or identity.catcher.is_staff
        or cast(_UserPrivileges, identity.catcher).is_superuser
    ):
        raise ResetSafetyError
    validate_asset(identity.media_key)
    return identity


class DatabaseMaintenance:
    """Keep the target executor while a trusted control connection gates writers."""

    def __init__(self, configuration: ResetConfiguration) -> None:
        self.configuration = configuration
        self._control: psycopg.Connection[Any] | None = None
        self._original_allow: bool | None = None

    def __enter__(self) -> Self:
        validate_database(self.configuration)
        validate_identity(self.configuration)
        database = settings.DATABASES["default"]
        if connection.in_atomic_block or self.configuration.database_name == "postgres":
            raise ResetSafetyError
        try:
            self._control = psycopg.connect(
                host=str(database["HOST"]),
                port=str(database["PORT"]),
                user=str(database.get("USER", "")),
                password=str(database.get("PASSWORD", "")),
                dbname="postgres",
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=5000 -c lock_timeout=5000",
            )
            row = self._control.execute(
                "SELECT current_database(), (pg_control_system()).system_identifier, rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if row is None or (str(row[0]), str(row[1]), bool(row[2])) != (
                "postgres",
                self.configuration.cluster_identifier,
                True,
            ):
                raise ResetSafetyError
            locked = self._control.execute(
                "SELECT pg_try_advisory_lock(204)"
            ).fetchone()
            if locked is None or not bool(locked[0]):
                raise ResetSafetyError
            row = self._control.execute(
                "SELECT datallowconn FROM pg_database WHERE datname = %s",
                (self.configuration.database_name,),
            ).fetchone()
            if row is None or not bool(row[0]):
                raise ResetSafetyError
            self._original_allow = True
        except ResetSafetyError:
            self.__exit__(None, None, None)
            raise
        except Exception:  # noqa: BLE001
            self.__exit__(None, None, None)
            raise ResetSafetyError from None
        return self

    def __exit__(self, *_: object) -> None:
        connection.close()
        if self._control is not None:
            self._control.close()
            self._control = None

    def quiesce(self) -> None:
        if self._control is None:
            raise ResetSafetyError
        try:
            statement = sql.SQL(
                "ALTER DATABASE {} WITH ALLOW_CONNECTIONS false"
            ).format(sql.Identifier(self.configuration.database_name))
            self._control.execute(statement)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT datallowconn FROM pg_database WHERE datname = current_database()"
                )
                if bool(cursor.fetchone()[0]):
                    raise ResetSafetyError
            observed = self._control.execute(
                "SELECT datallowconn FROM pg_database WHERE datname = %s",
                (self.configuration.database_name,),
            ).fetchone()
            if observed is None or bool(observed[0]):
                raise ResetSafetyError
            try:
                denied = psycopg.connect(
                    host=self.configuration.database_host,
                    port=self.configuration.database_port,
                    user=str(settings.DATABASES["default"].get("USER", "")),
                    password=str(settings.DATABASES["default"].get("PASSWORD", "")),
                    dbname=self.configuration.database_name,
                    connect_timeout=2,
                )
            except psycopg.OperationalError:
                denied = None
            if denied is not None:
                denied.close()
                raise ResetSafetyError
            connection.ensure_connection()
            executor_pid = connection.connection.info.backend_pid
            self._control.execute(
                "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity WHERE datname = %s AND pid <> %s",
                (self.configuration.database_name, executor_pid),
            )
            assert_quiescent(self.configuration)
        except Exception:  # noqa: BLE001
            raise ResetSafetyError from None

    def resume(self) -> None:
        if self._control is None or not self._original_allow:
            raise ResetSafetyError
        try:
            validate_database(self.configuration)
            validate_identity(self.configuration)
            assert_quiescent(self.configuration)
            row = self._control.execute(
                "SELECT current_database(), (pg_control_system()).system_identifier, rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if row is None or (str(row[0]), str(row[1]), bool(row[2])) != (
                "postgres",
                self.configuration.cluster_identifier,
                True,
            ):
                raise ResetSafetyError
            statement = sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS true").format(
                sql.Identifier(self.configuration.database_name)
            )
            self._control.execute(statement)
        except Exception:  # noqa: BLE001
            raise ResetSafetyError from None


def assert_quiescent(configuration: ResetConfiguration) -> None:
    """Require the retained executor to be the sole live target connection."""
    validate_database(configuration)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_stat_clear_snapshot()")
            cursor.execute(
                "SELECT datallowconn FROM pg_database WHERE datname = current_database()"
            )
            allowed = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )
            count = cursor.fetchone()[0]
    except Exception:  # noqa: BLE001
        raise ResetSafetyError from None
    if allowed or count != 1:
        raise ResetSafetyError
