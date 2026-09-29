"""Acceptance tests for structured stdout logging and request correlation (#210)."""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client
from pytest_django.fixtures import SettingsWrapper

from config.build_identity import Identity
from observability.logging import ContextFilter, JsonFormatter
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.observability_test_support import (
    DEPLOYMENT_ID,
    FAILURE_MESSAGE,
    SOURCE_SHA,
    JsonLogCapture,
    capture_json_stdout,
    identity,
)

BOOM_URLCONF = "tests.observability_test_support"
CLIENT_REQUEST_ID = "client-supplied-request-id"
RAILWAY_ID = "NnpHMrRbT-6rmzcsHn5Ytg"
REQUEST_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
BASE_KEYS = {"timestamp", "level", "message", "logger"}
CONTEXT_KEYS = {
    "request_id",
    "railway_request_id",
    "trace_id",
    "span_id",
    "environment",
    "release",
    "deployment_id",
}
UNKNOWN_IDENTITY = identity(source_sha=None, environment=None, deployment_id=None)
ALLOWED_EXTRAS: dict[str, object] = {
    "event": "tailtag.test",
    "stage": "service",
    "http.request.method": "GET",
    "http.route": "api/things/<int:pk>/",
    "http.response.status_code": 204,
    "duration_ms": 1.5,
    "error.type": "ValueError",
}


def _completion(lines: list[dict[str, Any]]) -> dict[str, Any]:
    completions = [line for line in lines if line["logger"] == "tailtag.request"]
    assert len(completions) == 1
    return completions[0]


def _log_outside_any_request() -> None:
    logging.getLogger("tailtag.test_outside").error("outside any request")


def _outside(lines: list[dict[str, Any]]) -> dict[str, Any]:
    return next(line for line in lines if line["message"] == "outside any request")


@contextmanager
def _isolated_logger(
    context_filter: ContextFilter,
) -> Generator[tuple[logging.Logger, JsonLogCapture]]:
    """A private logger writing through the real formatter and filter to a buffer."""
    buffer = StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(context_filter)
    logger = logging.getLogger("tailtag.test_formatter")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield logger, JsonLogCapture(buffer)
    finally:
        logger.removeHandler(handler)
        logger.propagate = True


def test_correlation_middleware_runs_before_every_other_middleware(
    settings: SettingsWrapper,
) -> None:
    """AC-1: the ID must exist before any other middleware can log or fail."""
    assert (
        settings.MIDDLEWARE[0]
        == "observability.middleware.RequestCorrelationMiddleware"
    )


@pytest.mark.parametrize(
    ("path", "route"),
    [
        ("/health/live", "health/live"),
        ("/api/conventions/424242/", "api/conventions/<int:pk>/"),
        ("/no/such/route/424242/", None),
    ],
)
def test_each_request_emits_one_completion_line_with_a_server_generated_id(
    path: str, route: str | None
) -> None:
    """AC-1, AC-5: one completion line, route template (never raw path), own ID."""
    with capture_json_stdout() as capture:
        response = Client().get(path, HTTP_X_REQUEST_ID=CLIENT_REQUEST_ID)

    lines = capture.lines()
    completion = _completion(lines)
    assert completion["event"] == "tailtag.http.request"
    assert completion["level"] == "info"
    assert completion["http.request.method"] == "GET"
    assert completion["http.response.status_code"] == response.status_code
    duration = completion["duration_ms"]
    assert isinstance(duration, (int, float)) and not isinstance(duration, bool)
    assert duration >= 0
    if route is None:
        assert "http.route" not in completion
    else:
        assert completion["http.route"].lstrip("/") == route
    request_id = completion["request_id"]
    assert REQUEST_ID_PATTERN.fullmatch(request_id)
    assert request_id != CLIENT_REQUEST_ID
    assert [line.get("request_id") for line in lines] == [request_id] * len(lines)


def test_ids_are_unique_and_context_never_outlives_its_request() -> None:
    """AC-1, AC-2: no ID sharing, no Railway ID carry-over, cleared afterwards."""
    client = Client()
    with capture_json_stdout() as capture:
        client.get("/health/live", HTTP_X_RAILWAY_REQUEST_ID=RAILWAY_ID)
        client.get("/health/live")
        _log_outside_any_request()

    lines = capture.lines()
    first, second = [line for line in lines if line["logger"] == "tailtag.request"]
    assert first["request_id"] != second["request_id"]
    assert first["railway_request_id"] == RAILWAY_ID
    assert "railway_request_id" not in second
    assert not {"request_id", "railway_request_id"} & _outside(lines).keys()


@pytest.mark.parametrize(
    "value",
    [
        RAILWAY_ID,
        "a" * 64,
        None,
        "",
        "a" * 65,
        "has space",
        "has/slash",
        'has"quote',
        "line\nbreak",
    ],
)
def test_railway_request_id_is_recorded_only_when_valid(value: str | None) -> None:
    """AC-2: valid values reach every line; anything else is omitted, never echoed."""
    extra: dict[str, Any] = (
        {} if value is None else {"HTTP_X_RAILWAY_REQUEST_ID": value}
    )
    valid = value is not None and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)
    with capture_json_stdout() as capture:
        Client().get("/no/such/route/", **extra)

    lines = capture.lines()
    assert len(lines) >= 2  # Django's own "Not Found" warning plus the completion line
    for line in lines:
        if valid:
            assert line["railway_request_id"] == value
        else:
            assert "railway_request_id" not in line


@pytest.mark.django_db
def test_application_logs_share_the_request_id_and_allow_listed_extras() -> None:
    """AC-1, AC-4, AC-5: a real view's ERROR log correlates with its completion."""
    client = force_authenticated_client(user=create_test_user())
    with (
        capture_json_stdout() as capture,
        patch(
            "catches.views.FursuitCatchCredentialResolutionRequestSerializer.is_valid",
            side_effect=RuntimeError("synthetic boundary failure"),
        ),
    ):
        response = client.post(
            "/api/catches/confirm/",
            {"payload": "tailtag:catch:v1:" + "A" * 43},
            format="json",
            HTTP_X_RAILWAY_REQUEST_ID=RAILWAY_ID,
        )

    assert response.status_code == 500
    lines = capture.lines()
    completion = _completion(lines)
    [application] = [line for line in lines if line["logger"] == "catches.views"]
    assert application["level"] == "error"
    assert application["stage"] == "boundary"
    assert "error.type" not in application
    assert completion["http.response.status_code"] == 500
    for line in (application, completion):
        assert line["request_id"] == completion["request_id"]
        assert line["railway_request_id"] == RAILWAY_ID


def test_unhandled_view_exception_still_completes_and_stays_out_of_stdout(
    settings: SettingsWrapper,
) -> None:
    """AC-1, AC-3, AC-4, AC-5, AC-7: 500 path completes, clears, and leaks nothing."""
    settings.ROOT_URLCONF = BOOM_URLCONF
    with capture_json_stdout() as capture:
        response = Client(raise_request_exception=False).get("/boom/424242/")
        _log_outside_any_request()

    assert response.status_code == 500
    lines = capture.lines()
    outside = _outside(lines)
    request_lines = [line for line in lines if line is not outside]
    completion = _completion(request_lines)
    assert completion["http.response.status_code"] == 500
    assert completion["http.route"].lstrip("/") == "boom/<int:item_id>/"
    assert {line.get("request_id") for line in request_lines} == {
        completion["request_id"]
    }
    assert "request_id" not in outside
    # Django attaches `request`/`status_code`/exc_info to its own error record.
    for line in lines:
        assert set(line) <= BASE_KEYS | CONTEXT_KEYS | set(ALLOWED_EXTRAS)
    assert any(
        line["logger"] == "django.request" and line.get("error.type") == "RuntimeError"
        for line in request_lines
    )
    assert FAILURE_MESSAGE not in capture.text
    assert "Traceback" not in capture.text


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (logging.DEBUG, "debug"),
        (logging.INFO, "info"),
        (logging.WARNING, "warn"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "error"),
    ],
)
def test_every_record_is_one_json_line_with_the_required_shape(
    level: int, expected: str
) -> None:
    """AC-3: single line even for multi-line messages; level names; ISO UTC; no nulls."""
    with _isolated_logger(ContextFilter(identity=UNKNOWN_IDENTITY)) as (logger, out):
        logger.log(level, "first line\nsecond line")

    assert out.text.count("\n") == 1
    [line] = out.lines()
    assert line["level"] == expected
    assert line["message"] == "first line\nsecond line"
    assert line["logger"] == "tailtag.test_formatter"
    assert datetime.fromisoformat(line["timestamp"]).utcoffset() == timedelta(0)
    assert None not in line.values()
    assert not CONTEXT_KEYS & line.keys()


def test_only_allow_listed_extras_are_written() -> None:
    """AC-3, AC-4: allow-listed extras pass; anything else, including `request`, drops."""

    class HostileRequest:
        def __repr__(self) -> str:
            return "synthetic-request-repr-must-not-appear"

    with _isolated_logger(ContextFilter(identity=UNKNOWN_IDENTITY)) as (logger, out):
        logger.info(
            "allowed",
            extra={
                **ALLOWED_EXTRAS,
                "token": "synthetic-token-must-not-appear",
                "user_id": 42,
                "request": HostileRequest(),
            },
        )
        logger.info("unknown value", extra={"stage": None})

    allowed, unknown = out.lines()
    assert set(allowed) == BASE_KEYS | set(ALLOWED_EXTRAS)
    assert {key: allowed[key] for key in ALLOWED_EXTRAS} == ALLOWED_EXTRAS
    for forbidden in (
        "synthetic-token-must-not-appear",
        "synthetic-request-repr-must-not-appear",
    ):
        assert forbidden not in out.text
    assert "stage" not in unknown


def test_exception_records_write_the_class_name_but_no_message_or_traceback() -> None:
    """AC-7: chained causes and stack info stay out of stdout."""
    with _isolated_logger(ContextFilter(identity=UNKNOWN_IDENTITY)) as (logger, out):
        try:
            try:
                raise KeyError("synthetic-inner-secret")
            except KeyError as inner:
                raise ValueError("synthetic-outer-secret") from inner
        except ValueError:
            logger.exception("failed", stack_info=True)

    [line] = out.lines()
    assert line["error.type"] == "ValueError"
    for forbidden in (
        "synthetic-inner-secret",
        "synthetic-outer-secret",
        "Traceback",
        "test_request_correlation_logging",
    ):
        assert forbidden not in out.text


@pytest.mark.parametrize(
    ("explicit", "runtime", "expected"),
    [
        (
            identity(),
            {},
            {
                "environment": "development",
                "release": SOURCE_SHA,
                "deployment_id": DEPLOYMENT_ID,
            },
        ),
        (UNKNOWN_IDENTITY, {}, {}),
        (
            None,
            {
                "RAILWAY_ENVIRONMENT_NAME": "development",
                "RAILWAY_DEPLOYMENT_ID": DEPLOYMENT_ID,
            },
            {"environment": "development", "deployment_id": DEPLOYMENT_ID},
        ),
        (None, {"RAILWAY_ENVIRONMENT_NAME": "Not A Valid Name!"}, {}),
    ],
    ids=["explicit", "explicit-unknown", "runtime-valid", "runtime-invalid"],
)
def test_build_identity_fields_come_from_identity_and_fail_soft(
    monkeypatch: pytest.MonkeyPatch,
    explicit: Identity | None,
    runtime: dict[str, str],
    expected: dict[str, str],
) -> None:
    """AC-6: identity written when known, omitted when not, read once, never fatal."""
    for name in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_DEPLOYMENT_ID"):
        monkeypatch.delenv(name, raising=False)
    for name, value in runtime.items():
        monkeypatch.setenv(name, value)
    context_filter = ContextFilter(identity=explicit)
    # A later environment change must not alter (or repair) what was read at startup.
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "changed-after-startup")

    with _isolated_logger(context_filter) as (logger, out):
        logger.info("still logging")

    [line] = out.lines()
    assert line["message"] == "still logging"
    identity_fields = {"environment", "release", "deployment_id"}
    assert {k: v for k, v in line.items() if k in identity_fields} == expected
