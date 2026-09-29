"""Single-line JSON log formatting, request context, and the LOGGING config."""

from __future__ import annotations

import copy
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final, TextIO

import sentry_sdk

from config.build_identity import Identity, get_identity

from .context import railway_request_id_var, request_id_var
from .privacy import redact_text

# The only `extra` attributes written to stdout or kept on Sentry breadcrumbs.
# Anything else, including Django's attached `request`, is dropped.
ALLOWED_EXTRA_FIELDS: Final = (
    "event",
    "stage",
    "http.request.method",
    "http.route",
    "http.response.status_code",
    "duration_ms",
    "error.type",
)

_QUIET_THIRD_PARTY_LOGGERS: Final = (
    "botocore",
    "boto3",
    "s3transfer",
    "urllib3",
    "django.db.backends",
)
_CONTEXT_ATTRIBUTE: Final = "_tailtag_context"
_LEVEL_NAMES: Final = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class ContextFilter(logging.Filter):
    """Attach request, trace, and build identity context to every record."""

    def __init__(self, identity: Identity | None = None) -> None:
        super().__init__()
        if identity is None:
            try:
                identity = get_identity()
            except (ValueError, OSError):
                identity = None
        self._identity_fields: dict[str, str | None] = (
            {}
            if identity is None
            else {
                "environment": identity["environment"],
                "release": identity["source_sha"],
                "deployment_id": identity["deployment_id"],
            }
        )

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        # Return a copy so other handlers (and caplog) see the record unchanged.
        record = copy.copy(record)
        fields: dict[str, str | None] = {
            "request_id": request_id_var.get(),
            "railway_request_id": railway_request_id_var.get(),
        }
        if sentry_sdk.get_client().is_active():
            trace_context = sentry_sdk.get_current_scope().get_trace_context()
            fields["trace_id"] = trace_context.get("trace_id")
            fields["span_id"] = trace_context.get("span_id")
        fields.update(self._identity_fields)
        setattr(record, _CONTEXT_ATTRIBUTE, fields)
        return record


class JsonFormatter(logging.Formatter):
    """Write one JSON object per record using only contract-approved keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": _LEVEL_NAMES.get(record.levelno, "error"),
            "message": redact_text(record.getMessage()),
            "logger": record.name,
        }
        payload.update(getattr(record, _CONTEXT_ATTRIBUTE, {}))
        for key in ALLOWED_EXTRA_FIELDS:
            payload[key] = getattr(record, key, None)
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["error.type"] = record.exc_info[0].__name__
        return json.dumps(
            {key: value for key, value in payload.items() if value is not None},
            default=str,
        )


class StdoutHandler(logging.StreamHandler[TextIO]):
    """Write to whatever `sys.stdout` is at emit time, not at configuration time.

    Settings are configured once per process, but Django may be set up again
    in-process (management commands, test runners) while `sys.stdout` is swapped.
    """

    def __init__(self) -> None:
        super().__init__(sys.stdout)
        self._stream_override: TextIO | None = None

    @property
    def stream(self) -> TextIO:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self._stream_override or sys.stdout

    @stream.setter
    def stream(self, value: TextIO) -> None:  # pyright: ignore[reportIncompatibleVariableOverride]
        self._stream_override = None if value is sys.stdout else value


def build_logging_config() -> dict[str, Any]:
    """Return the LOGGING setting: JSON records on stdout for every logger."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": "observability.logging.ContextFilter"}},
        "formatters": {"json": {"()": "observability.logging.JsonFormatter"}},
        "handlers": {
            "stdout": {
                "class": "observability.logging.StdoutHandler",
                "formatter": "json",
                "filters": ["context"],
            },
        },
        "root": {"handlers": ["stdout"], "level": "INFO"},
        # Their INFO output carries URLs and request detail that must not reach stdout.
        "loggers": {name: {"level": "WARNING"} for name in _QUIET_THIRD_PARTY_LOGGERS},
    }
