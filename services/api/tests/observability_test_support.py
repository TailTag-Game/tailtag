"""Shared test-only helpers for the request-correlation and Sentry contracts."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from io import StringIO
from typing import Any, TextIO, cast

import sentry_sdk
from django.http import HttpRequest, HttpResponse
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
BREADCRUMB_EXTRA = "synthetic-breadcrumb-extra-must-be-dropped"

_LOGGER = logging.getLogger("tailtag.test_support")
_LOGGER.setLevel(logging.INFO)


def boom_view(request: HttpRequest, item_id: int) -> HttpResponse:
    """Log with a non-allow-listed extra, then fail the way an unhandled bug would."""
    _LOGGER.info(  # nosemgrep: tailtag.logging.sensitive-argument
        "before failure", extra={"token": BREADCRUMB_EXTRA, "stage": "boundary"}
    )
    raise RuntimeError(FAILURE_MESSAGE)


# Test-only URLconf: `@override_settings(ROOT_URLCONF="tests.observability_test_support")`.
urlpatterns: list[URLPattern] = [path("boom/<int:item_id>/", boom_view)]


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
def sentry_capturing(identity: Identity | None) -> Generator[CapturingTransport]:
    """Initialize Sentry via production code with a capturing transport; always reset.

    The fake DSN is unresolvable, and the real transport is replaced (and killed)
    before any event exists, so no network call can occur.
    """
    transport = CapturingTransport()
    try:
        assert init_sentry(FAKE_DSN, identity) is True
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
