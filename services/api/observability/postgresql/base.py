"""Django's PostgreSQL backend, recording each new connection attempt.

Only `get_new_connection` is overridden; the original exception still propagates
unchanged. See `docs/architecture/backend/observability.md`.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from django.db.backends.postgresql.base import (
    DatabaseWrapper as PostgreSQLDatabaseWrapper,
)

from ..dependencies import (
    classify_database_connection_error,
    record_database_connection,
)


class DatabaseWrapper(PostgreSQLDatabaseWrapper):
    def get_new_connection(self, conn_params: dict[str, Any]) -> Any:
        started = perf_counter()
        try:
            connection = super().get_new_connection(conn_params)
        except Exception as error:
            record_database_connection(
                (perf_counter() - started) * 1000,
                classify_database_connection_error(error),
            )
            raise
        record_database_connection((perf_counter() - started) * 1000)
        return connection
