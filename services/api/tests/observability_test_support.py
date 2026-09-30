"""Shared test-only helpers for the request-correlation and Sentry contracts."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from io import StringIO
from typing import Any, TextIO, cast

import sentry_sdk
from django.core.signals import request_finished, request_started
from django.core.wsgi import get_wsgi_application
from django.db import close_old_connections, connection
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory
from django.urls import URLPattern, path
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from config.build_identity import Identity
from observability.logging import JsonFormatter
from observability.sentry import init_sentry

FAKE_DSN = "https://public@example.invalid/1"
SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
FAILURE_MESSAGE = "synthetic-failure-message-must-stay-out-of-stdout"
SQL_PARAMETER = "synthetic-sql-parameter-must-not-leak"
BREADCRUMB_EXTRA = "synthetic-breadcrumb-extra-must-be-dropped"

_LOGGER = logging.getLogger("tailtag.test_support")
_LOGGER.setLevel(logging.INFO)


def boom_view(request: HttpRequest, item_id: int) -> HttpResponse:
    """Log with a non-allow-listed extra, then fail the way an unhandled bug would."""
    _LOGGER.info(  # nosemgrep: tailtag.logging.sensitive-argument
        "before failure", extra={"token": BREADCRUMB_EXTRA, "stage": "boundary"}
    )
    raise RuntimeError(FAILURE_MESSAGE)


def query_view(request: HttpRequest) -> HttpResponse:
    """Run a real parameterized query whose parameter is a sentinel."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT %s", [SQL_PARAMETER])
        cursor.fetchone()
    return HttpResponse("queried")


# Test-only URLconf: `@override_settings(ROOT_URLCONF="tests.observability_test_support")`.
urlpatterns: list[URLPattern] = [
    path("boom/<int:item_id>/", boom_view),
    path("query/", query_view),
]


class JsonLogCapture:
    """Real formatted output of the configured stdout JSON handler(s)."""

    def __init__(self, buffer: StringIO) -> None:
        self._buffer = buffer

    @property
    def text(self) -> str:
        return self._buffer.getvalue()

    def lines(self) -> list[dict[str, Any]]:
        """Parse every emitted line; each must be exactly one valid JSON object."""
        raw = self.text
        assert raw == "" or raw.endswith("\n")
        parsed: list[dict[str, Any]] = []
        for line in raw.split("\n")[:-1]:
            value: object = json.loads(line)
            assert isinstance(value, dict)
            parsed.append(cast(dict[str, Any], value))
        return parsed


def _configured_json_handlers() -> list[logging.StreamHandler[TextIO]]:
    loggers: list[logging.Logger] = [logging.getLogger()]
    loggers.extend(
        candidate
        for candidate in logging.Logger.manager.loggerDict.values()
        if isinstance(candidate, logging.Logger)
    )
    handlers: list[logging.StreamHandler[TextIO]] = []
    for logger in loggers:
        for handler in logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and isinstance(handler.formatter, JsonFormatter)
                and handler not in handlers
            ):
                handlers.append(cast("logging.StreamHandler[TextIO]", handler))
    return handlers


@contextmanager
def capture_json_stdout() -> Generator[JsonLogCapture]:
    """Redirect the handler(s) that settings.LOGGING points at stdout into a buffer.

    Only the destination stream is swapped, so the real formatter, filters, levels,
    and logger routing from settings are what produce the captured lines.
    """
    handlers = _configured_json_handlers()
    assert handlers, "settings.LOGGING must configure a JsonFormatter handler"
    buffer = StringIO()
    originals = [handler.setStream(buffer) for handler in handlers]
    try:
        yield JsonLogCapture(buffer)
    finally:
        for handler, original in zip(handlers, originals, strict=True):
            if original is not None:
                handler.setStream(original)


class CapturingTransport(Transport):
    """The only substitute: the Sentry network boundary."""

    def __init__(self) -> None:
        super().__init__(None)
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    def events(self) -> list[dict[str, Any]]:
        return [
            cast(dict[str, Any], event)
            for envelope in self.envelopes
            if (event := envelope.get_event()) is not None
        ]

    def transactions(self) -> list[dict[str, Any]]:
        """Transaction events as sent; `events()` returns error events only."""
        return [
            cast(dict[str, Any], event)
            for envelope in self.envelopes
            if (event := envelope.get_transaction_event()) is not None
        ]

    def metrics(self) -> list[dict[str, Any]]:
        """Metrics as sent: `trace_metric` envelope items carry `{"version": 2, "items": [...]}`.

        Each metric's `attributes` map key to `{"value": ..., "type": ...}`.
        """
        sent: list[dict[str, Any]] = []
        for envelope in self.envelopes:
            for item in envelope.items:
                if item.type == "trace_metric":
                    payload = cast(dict[str, Any], item.payload.json)
                    sent.extend(payload["items"])
        return sent

    def serialized(self) -> str:
        return "".join(
            envelope.serialize().decode("utf-8", "replace")
            for envelope in self.envelopes
        )


@contextmanager
def sentry_capturing(
    identity: Identity | None, *, traces_sample_rate: float | None = None
) -> Generator[CapturingTransport]:
    """Initialize Sentry via production code with a capturing transport; always reset.

    The fake DSN is unresolvable, and the real transport is replaced (and killed)
    before any event exists, so no network call can occur. Tracing stays off
    unless a rate is given, as in production.
    """
    transport = CapturingTransport()
    try:
        assert (
            init_sentry(FAKE_DSN, identity, traces_sample_rate=traces_sample_rate)
            is True
        )
        client = sentry_sdk.get_client()
        original = client.transport
        client.transport = transport
        if original is not None:
            original.kill()
        yield transport
    finally:
        reset_sentry()


def reset_sentry() -> None:
    """Leave the process with no active SDK client, tags, or breadcrumbs."""
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()


def identity(
    *,
    source_sha: str | None = SOURCE_SHA,
    environment: str | None = "development",
    deployment_id: str | None = DEPLOYMENT_ID,
) -> Identity:
    return {
        "source_sha": source_sha,
        "environment": environment,
        "deployment_id": deployment_id,
    }


def wsgi_request(
    path: str, *, method: str = "GET", headers: dict[str, str] | None = None
) -> int:
    """Serve one request through Django's real WSGI handler; return its status code.

    Django's test client bypasses `WSGIHandler`, which is where the Sentry SDK
    starts transactions, so tracing can only be observed through this entry
    point. Like the test client, it keeps `close_old_connections` from closing
    the test's connection.
    """
    environ = RequestFactory().generic(method, path, headers=headers).environ
    status: list[str] = []

    def start_response(response_status: str, *_: object) -> None:
        status.append(response_status)

    handler = get_wsgi_application()
    request_started.disconnect(close_old_connections)  # pyright: ignore[reportUnknownMemberType]
    request_finished.disconnect(close_old_connections)  # pyright: ignore[reportUnknownMemberType]
    try:
        body = handler(environ, start_response)  # pyright: ignore[reportArgumentType]
        try:
            b"".join(body)
        finally:
            body.close()  # Sentry finishes the transaction when the body closes.
    finally:
        request_started.connect(close_old_connections)  # pyright: ignore[reportUnknownMemberType]
        request_finished.connect(close_old_connections)  # pyright: ignore[reportUnknownMemberType]
    return int(status[0].split(" ", 1)[0])


OUTCOME_METRIC_ATTRIBUTE = "tailtag.outcome"
REASON_METRIC_ATTRIBUTE = "tailtag.reason"

RecordedOutcome = tuple[str, str, str | None]


def recorded_outcomes(
    logs: JsonLogCapture, transport: CapturingTransport
) -> list[RecordedOutcome]:
    """Every domain outcome as `(signal, outcome, reason)`, in emission order.

    Reads both real channels (the stdout JSON lines and the Sentry metrics as
    sent, after the privacy filter) and asserts they describe the same events, so
    a dropped attribute, a missing signal, or a log/metric mismatch fails here.
    """
    sentry_sdk.flush()
    from_logs: list[RecordedOutcome] = [
        (line["event"], line["tailtag_outcome"], line.get("tailtag_reason"))
        for line in logs.lines()
        if "tailtag_outcome" in line
    ]
    from_metrics: list[RecordedOutcome] = []
    for metric in transport.metrics():
        attributes = {
            key: entry["value"] for key, entry in metric["attributes"].items()
        }
        if OUTCOME_METRIC_ATTRIBUTE not in attributes:
            continue
        assert (metric["type"], metric["value"]) == ("counter", 1.0)
        from_metrics.append(
            (
                metric["name"],
                attributes[OUTCOME_METRIC_ATTRIBUTE],
                attributes.get(REASON_METRIC_ATTRIBUTE),
            )
        )
    assert sorted(from_logs, key=repr) == sorted(from_metrics, key=repr)
    return from_logs
