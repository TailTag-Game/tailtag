"""Per-request correlation identifiers shared by the middleware and log filter."""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
railway_request_id_var: ContextVar[str | None] = ContextVar(
    "railway_request_id", default=None
)
