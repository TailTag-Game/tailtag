"""Dependency health telemetry: the bounded taxonomy, classifiers, and recorders.

Database connection attempts and storage operations are each one Sentry metric
(and, on failure only, one WARNING log line) carrying only the bounded values
below. Classification happens inside the process; exception text, hosts, bucket
names, keys, and URLs never leave it. Values are add-only: dashboards and alerts
depend on them. See `docs/architecture/backend/observability.md`.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum

import sentry_sdk
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ReadTimeoutError,
)
from botocore.exceptions import (
    ConnectionError as BotocoreConnectionError,
)
from psycopg.errors import ConnectionTimeout

_logger = logging.getLogger(__name__)


class DependencySignal(StrEnum):
    DB_CONNECTION_ATTEMPTS = "tailtag.db.connection.attempts"
    DB_CONNECTION_DURATION = "tailtag.db.connection.duration"
    MEDIA_STORAGE_OPERATIONS = "tailtag.media.storage.operations"


class DependencyOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DatabaseConnectionReason(StrEnum):
    TIMEOUT = "timeout"
    TOO_MANY_CONNECTIONS = "too_many_connections"
    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    OTHER = "other"


class StorageReason(StrEnum):
    UNAVAILABLE = "unavailable"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    THROTTLED = "throttled"
    SERVER_ERROR = "server_error"
    OTHER = "other"


class RpcMethod(StrEnum):
    """The `rpc.method` values: the four S3 calls that cross the network."""

    PUT_OBJECT = "PutObject"
    GET_OBJECT = "GetObject"
    HEAD_OBJECT = "HeadObject"
    DELETE_OBJECT = "DeleteObject"


# psycopg exposes no SQLSTATE for connect failures, so these are matched against
# the lowercased server and libpq messages. A wording change degrades to `other`.
_TOO_MANY_CONNECTIONS_MARKERS = (
    "too many clients",
    "remaining connection slots are reserved",
)
_UNREACHABLE_MARKERS = (
    "could not translate host name",
    "name or service not known",
    "temporary failure in name resolution",
    "connection refused",
    "no route to host",
    "network is unreachable",
)
_REJECTED_MARKERS = (
    "password authentication failed",
    "authentication failed",
    "no password supplied",
    "no pg_hba.conf entry",
)
# Only the server's missing-role and missing-database phrases: libpq also says
# "does not exist" about local files such as a missing root certificate.
_REJECTED_PATTERNS = (
    re.compile(r'\brole "[^\n]*" does not exist'),
    re.compile(r'\bdatabase "[^\n]*" does not exist'),
)

_ACCESS_DENIED_CODES = frozenset(
    {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}
)
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey"})
_THROTTLED_CODES = frozenset({"SlowDown", "Throttling", "RequestLimitExceeded"})
_UNAVAILABLE_ERRORS = (BotocoreConnectionError, ReadTimeoutError, ConnectionClosedError)


def classify_database_connection_error(
    error: BaseException,
) -> DatabaseConnectionReason:
    if isinstance(error, ConnectionTimeout):
        return DatabaseConnectionReason.TIMEOUT
    message = str(error).lower()
    if any(marker in message for marker in _TOO_MANY_CONNECTIONS_MARKERS):
        return DatabaseConnectionReason.TOO_MANY_CONNECTIONS
    if any(marker in message for marker in _REJECTED_MARKERS) or any(
        pattern.search(message) for pattern in _REJECTED_PATTERNS
    ):
        return DatabaseConnectionReason.REJECTED
    if any(marker in message for marker in _UNREACHABLE_MARKERS):
        return DatabaseConnectionReason.UNREACHABLE
    return DatabaseConnectionReason.OTHER


def classify_storage_error(error: BaseException) -> StorageReason:
    if isinstance(error, _UNAVAILABLE_ERRORS):
        return StorageReason.UNAVAILABLE
    if not isinstance(error, ClientError):
        return StorageReason.OTHER
    code = error.response.get("Error", {}).get("Code")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if code in _ACCESS_DENIED_CODES or status in (401, 403):
        return StorageReason.ACCESS_DENIED
    if code in _NOT_FOUND_CODES or status == 404:
        return StorageReason.NOT_FOUND
    if code in _THROTTLED_CODES or status in (429, 503):
        return StorageReason.THROTTLED
    if isinstance(status, int) and 500 <= status <= 599:
        return StorageReason.SERVER_ERROR
    return StorageReason.OTHER


def record_database_connection(
    duration_ms: float, reason: DatabaseConnectionReason | None = None
) -> None:
    """Count one connection attempt and record its duration; log failures only."""
    outcome = (
        DependencyOutcome.SUCCEEDED if reason is None else DependencyOutcome.FAILED
    )
    attributes = {"tailtag.outcome": str(outcome)}
    if reason is not None:
        _logger.warning(
            "Database connection attempt failed",
            extra={
                "event": str(DependencySignal.DB_CONNECTION_ATTEMPTS),
                "tailtag_outcome": str(outcome),
                "tailtag_reason": str(reason),
                "duration_ms": round(duration_ms, 3),
            },
        )
    sentry_sdk.metrics.count(
        str(DependencySignal.DB_CONNECTION_ATTEMPTS),
        1,
        attributes=(
            attributes
            if reason is None
            else {**attributes, "tailtag.reason": str(reason)}
        ),
    )
    sentry_sdk.metrics.distribution(
        str(DependencySignal.DB_CONNECTION_DURATION),
        duration_ms,
        unit="millisecond",
        attributes=attributes,
    )


def record_storage_operation(
    method: RpcMethod, reason: StorageReason | None = None
) -> None:
    """Count one storage call; log failures only."""
    outcome = (
        DependencyOutcome.SUCCEEDED if reason is None else DependencyOutcome.FAILED
    )
    attributes = {"rpc.method": str(method), "tailtag.outcome": str(outcome)}
    if reason is not None:
        attributes["tailtag.reason"] = str(reason)
        _logger.warning(
            "Storage operation failed",
            extra={
                "event": str(DependencySignal.MEDIA_STORAGE_OPERATIONS),
                "tailtag_outcome": str(outcome),
                "tailtag_reason": str(reason),
                "rpc_method": str(method),
            },
        )
    sentry_sdk.metrics.count(
        str(DependencySignal.MEDIA_STORAGE_OPERATIONS), 1, attributes=attributes
    )
