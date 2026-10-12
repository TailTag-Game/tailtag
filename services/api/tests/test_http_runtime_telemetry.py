"""Acceptance tests for HTTP and backend runtime telemetry (#212).

Only the Sentry network boundary is substituted (`CapturingTransport`). Sentry is
initialized through production `init_sentry`; logs go through the configured JSON
stdout handler; Gunicorn logging uses Gunicorn's real `Config`, `Logger`, and the
real `gunicorn.conf.py`. Contract values (`<unmatched>`, `_OTHER`, the metric
name) are written literally so a renamed constant cannot silently pass.

Transactions are started by the Sentry WSGI wrapper inside Django's
`WSGIHandler`, which Django's test client bypasses, so tracing tests use
`wsgi_request`; the request metric is emitted by middleware, so its tests use the
test client.
"""

from __future__ import annotations

import logging
import logging.config
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn

import pytest
import sentry_sdk
from django.test import Client
from gunicorn import glogging  # pyright: ignore[reportMissingTypeStubs]
from gunicorn.app.base import Application  # pyright: ignore[reportMissingTypeStubs]
from pytest_django.fixtures import SettingsWrapper

from observability import sentry as observability_sentry
from tests.observability_test_support import (
    DEPLOYMENT_ID,
    SOURCE_SHA,
    SQL_PARAMETER,
    CapturingTransport,
    capture_json_stdout,
    identity,
    sentry_capturing,
    wsgi_request,
)

TEST_URLCONF = "tests.observability_test_support"
GUNICORN_CONFIG = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
REQUEST_METRIC = "tailtag.http.server.requests"
SDK_ATTRIBUTES = {
    "sentry.environment",
    "sentry.release",
    "sentry.sdk.name",
    "sentry.sdk.version",
}
RAW_PATH_SENTINEL = "sentinel-raw-path-12345"
UNMATCHED_PATH = f"/no-such-route/{RAW_PATH_SENTINEL}/"
CONVENTION_PATH = "/api/conventions/424242/"
SAMPLED_PARENT = f"{'a' * 32}-{'b' * 16}-1"
UNSAMPLED_PARENT = f"{'a' * 32}-{'b' * 16}-0"
CLIENT_TRACE_ID = "c0ffee00" * 4
CLIENT_SPAN_ID = "d00dfeed" * 2
CLIENT_BAGGAGE_VALUES = [
    CLIENT_TRACE_ID,
    "0.314159",  # sentry-sample_rand
    "client-environment-sentinel",
    "client-release-sentinel",
    "client-public-key-sentinel",
]
CLIENT_BAGGAGE = ",".join(
    f"sentry-{key}={value}"
    for key, value in zip(
        ["trace_id", "sample_rand", "environment", "release", "public_key"],
        CLIENT_BAGGAGE_VALUES,
        strict=True,
    )
)


def _request_metric_attributes(transport: CapturingTransport) -> dict[str, Any]:
    sentry_sdk.flush()
    [metric] = transport.metrics()
    assert (metric["name"], metric["type"], metric["value"]) == (
        REQUEST_METRIC,
        "counter",
        1.0,
    )
    return {key: entry["value"] for key, entry in metric["attributes"].items()}


# --- AC-1: tracing configuration ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("0", 0.0), ("0.25", 0.25), ("1", 1.0), ("1.0", 1.0)],
)
def test_traces_sample_rate_is_optional_and_accepts_the_closed_unit_interval(
    value: str | None, expected: float | None
) -> None:
    """AC-1: unset or empty means tracing off; both bounds are valid rates."""
    assert observability_sentry.parse_traces_sample_rate(value) == expected


@pytest.mark.parametrize("value", ["synthetic-rate-sentinel", "-0.1", "1.5", "nan"])
def test_invalid_traces_sample_rate_stops_startup_without_echoing_the_value(
    value: str,
) -> None:
    """AC-1: a typo fails loudly (RuntimeError) and never leaks into a log."""
    with pytest.raises(RuntimeError) as raised:
        observability_sentry.parse_traces_sample_rate(value)

    assert value not in str(raised.value)


# --- AC-2, AC-5: sampling, and the request metric whether or not traced ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path", "rate", "parent", "traced"),
    [
        ("GET", "/health/live", 1.0, None, False),
        ("GET", "/health/ready", 1.0, SAMPLED_PARENT, False),
        ("GET", CONVENTION_PATH, None, None, False),
        ("GET", CONVENTION_PATH, 1.0, None, True),
        ("GET", CONVENTION_PATH, 1.0, UNSAMPLED_PARENT, True),
        ("GET", CONVENTION_PATH, 0.0, SAMPLED_PARENT, False),
        ("HEAD", CONVENTION_PATH, 1.0, None, False),
    ],
    ids=[
        "health-live-never-traced",
        "health-ready-client-header-has-no-effect",
        "tracing-off-without-a-rate",
        "traced-at-rate-one",
        "client-unsampled-header-has-no-effect",
        "client-sampled-header-has-no-effect",
        "head-counted-not-traced",
    ],
)
def test_health_is_never_traced_other_routes_follow_the_rate_and_every_request_is_counted(
    method: str, path: str, rate: float | None, parent: str | None, traced: bool
) -> None:
    """AC-1, AC-2, AC-5: a client's sampling decision never affects tracing.

    Cases with a `sentry-trace` header prove this end to end; #260 AC-1 covers
    the header being dropped at the entry point, so the sampler never sees it.

    HEAD and OPTIONS are never traced, as the SDK's Django integration default.
    The request metric is unsampled: exactly one per request for health, traced,
    and untraced requests alike.
    """
    headers = None if parent is None else {"sentry-trace": parent}
    with sentry_capturing(identity(), traces_sample_rate=rate) as transport:
        wsgi_request(path, method=method, headers=headers)
        sentry_sdk.flush()

    assert len(transport.transactions()) == (1 if traced else 0)
    assert len(transport.metrics()) == 1


# --- AC-3, AC-9: transaction names ---


@pytest.mark.parametrize(
    ("path", "name"),
    [
        (CONVENTION_PATH, "/api/conventions/{pk}/"),
        (UNMATCHED_PATH, "<unmatched>"),
    ],
    ids=["matched-route-template", "unmatched-fixed-name"],
)
def test_transactions_are_named_by_route_template_or_the_fixed_unmatched_name(
    path: str, name: str
) -> None:
    """AC-3, AC-9: never the raw path or a `url` source; identity from build only.

    An unmatched path is client-chosen free text, so it appears nowhere in the
    envelope, including the request URL.
    """
    with sentry_capturing(identity(), traces_sample_rate=1.0) as transport:
        wsgi_request(path)
        sentry_sdk.flush()

    [transaction] = transport.transactions()
    assert transaction["transaction"] == name
    assert transaction["transaction_info"]["source"] == "route"
    assert "424242" not in transaction["transaction"]
    assert RAW_PATH_SENTINEL not in transport.serialized()
    assert transaction["environment"] == "development"
    assert transaction["release"] == SOURCE_SHA


@pytest.mark.parametrize(
    ("event_name", "source", "expected_name"),
    [
        (f"/raw/{RAW_PATH_SENTINEL}/", "url", "<unmatched>"),
        ("/api/conventions/{pk}/", "route", "/api/conventions/{pk}/"),
    ],
    ids=["url-source-is-replaced", "route-source-is-kept"],
)
def test_transaction_hook_backstops_url_sourced_names(
    event_name: str, source: str, expected_name: str
) -> None:
    """AC-3: the transaction hook is what renames a raw-path (`url`) name.

    The production hook is applied to a synthetic event, as the existing scrubber
    tests do, to prove the rename and that route-sourced names are kept.
    """
    event: dict[str, Any] = {
        "type": "transaction",
        "transaction": event_name,
        "transaction_info": {"source": source},
    }
    with sentry_capturing(identity()):
        scrubbed = sentry_sdk.get_client().options["before_send_transaction"](event, {})

    assert scrubbed is not None
    assert scrubbed["transaction"] == expected_name
    assert scrubbed["transaction_info"]["source"] == "route"


# --- AC-4: SQL spans ---


@pytest.mark.django_db
def test_sql_spans_keep_parameterized_text_and_never_carry_parameter_values(
    settings: SettingsWrapper,
) -> None:
    """AC-4: database timing is visible without SQL parameters leaving the process."""
    settings.ROOT_URLCONF = TEST_URLCONF
    with sentry_capturing(identity(), traces_sample_rate=1.0) as transport:
        assert wsgi_request("/query/") == 200
        sentry_sdk.flush()

    [transaction] = transport.transactions()
    descriptions = [
        span["description"] for span in transaction["spans"] if span["op"] == "db"
    ]
    assert any("SELECT %s" in description for description in descriptions)
    assert SQL_PARAMETER not in transport.serialized()


# --- AC-5, AC-6: request metric attributes and server-error classification ---


@pytest.mark.parametrize(
    ("method", "path", "urlconf", "expected", "error_events"),
    [
        ("GET", "/health/live", None, ("health/live", "GET", "2xx"), 0),
        (
            "GET",
            CONVENTION_PATH,
            None,
            ("api/conventions/<int:pk>/", "GET", "4xx"),
            0,
        ),
        ("GET", UNMATCHED_PATH, None, ("<unmatched>", "GET", "4xx"), 0),
        ("FROBNICATE", "/no-such-route/", None, ("<unmatched>", "_OTHER", "4xx"), 0),
        (
            "GET",
            "/boom/424242/",
            TEST_URLCONF,
            ("boom/<int:item_id>/", "GET", "5xx"),
            1,
        ),
    ],
    ids=[
        "health-2xx",
        "matched-template-401",
        "unmatched-404",
        "unknown-method",
        "unhandled-exception-5xx",
    ],
)
def test_each_request_is_counted_once_with_bounded_attributes_and_only_5xx_is_an_error(
    settings: SettingsWrapper,
    method: str,
    path: str,
    urlconf: str | None,
    expected: tuple[str, str, str],
    error_events: int,
) -> None:
    """AC-5, AC-6: tracing is off here, so the count cannot depend on a transaction.

    Attributes are exactly the SDK's plus the three bounded HTTP dimensions: no
    ID, raw path, or query. A 404 and a rejected authentication are client
    outcomes; only the unhandled exception creates one error event.
    """
    if urlconf is not None:
        settings.ROOT_URLCONF = urlconf
    with sentry_capturing(identity()) as transport:
        Client(raise_request_exception=False).generic(method, path)
        attributes = _request_metric_attributes(transport)

    route, sent_method, status_class = expected
    assert attributes.pop("http.route") == route
    assert attributes.pop("http.request.method") == sent_method
    assert attributes.pop("http.response.status_class") == status_class
    assert set(attributes) == SDK_ATTRIBUTES
    assert len(transport.events()) == error_events
    assert RAW_PATH_SENTINEL not in transport.serialized()


# --- AC-8: Gunicorn logs ---


class _GunicornConfigOnly(Application):  # pyright: ignore[reportUntypedBaseClass]
    """Load the real `gunicorn.conf.py` exactly as Gunicorn's own loader does."""

    def init(self, parser: object, opts: object, args: object) -> None:
        return None

    def load(self) -> NoReturn:
        raise NotImplementedError("configuration only")

    def load_config(self) -> None:
        self.load_config_from_file(str(GUNICORN_CONFIG))  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture
def restored_process_logging(settings: SettingsWrapper) -> Iterator[None]:
    """Gunicorn reconfigures process-wide logging; put Django's back afterwards."""
    yield
    for name in ("gunicorn.error", "gunicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
    logging.config.dictConfig(settings.LOGGING)


@pytest.mark.usefixtures("restored_process_logging")
def test_gunicorn_error_records_are_json_lines_with_build_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: a worker timeout, otherwise plain stderr text, is searchable in Railway."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "development")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", DEPLOYMENT_ID)
    config = _GunicornConfigOnly().cfg  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    gunicorn_logger = glogging.Logger(config)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    with capture_json_stdout() as capture:
        gunicorn_logger.critical("WORKER TIMEOUT (pid:%s)", 4242)  # pyright: ignore[reportUnknownMemberType]

    [line] = capture.lines()
    assert line["logger"] == "gunicorn.error"
    assert line["level"] == "error"
    assert line["message"] == "WORKER TIMEOUT (pid:4242)"
    assert line["environment"] == "development"
    assert line["deployment_id"] == DEPLOYMENT_ID


@pytest.mark.usefixtures("restored_process_logging")
def test_gunicorn_access_records_reach_neither_stdout_nor_sentry_breadcrumbs() -> None:
    """AC-8, AC-12: `logconfig_dict` turns Gunicorn access logging on.

    Access lines carry the client IP, raw path, and user agent, and are written
    outside the request's Sentry scope, so a breadcrumb would reach other
    requests' error events.
    """
    config = _GunicornConfigOnly().cfg  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    glogging.Logger(config)  # pyright: ignore[reportUnknownMemberType]
    access_line = f'203.0.113.9 - - "GET /{RAW_PATH_SENTINEL}/ HTTP/1.1" 404 0'

    with sentry_capturing(identity()) as transport, capture_json_stdout() as capture:
        logging.getLogger("gunicorn.access").info(access_line)
        sentry_sdk.capture_message("probe")
        sentry_sdk.flush()

    assert capture.lines() == []
    assert RAW_PATH_SENTINEL not in transport.serialized()


# --- #260: client trace headers are ignored ---


@pytest.mark.django_db
@pytest.mark.parametrize("rate", [None, 1.0], ids=["tracing-off", "tracing-on"])
def test_client_trace_headers_never_reach_logs_or_sentry_and_the_request_still_succeeds(
    settings: SettingsWrapper, rate: float | None
) -> None:
    """#260 AC-1, AC-2, AC-4: `sentry-trace` and `baggage` from a client are inert.

    The SDK adopts them even with tracing off, so a client could pick the
    `trace_id` on every log line and Sentry item and inject the dynamic sampling
    context. The request fails (`/boom/`) so a log line, an error event, and, when
    tracing is on, a transaction all carry trace context.
    """
    settings.ROOT_URLCONF = TEST_URLCONF
    headers = {
        "sentry-trace": f"{CLIENT_TRACE_ID}-{CLIENT_SPAN_ID}-1",
        "baggage": CLIENT_BAGGAGE,
    }
    baseline_status = wsgi_request("/boom/424242/")

    with (
        sentry_capturing(identity(), traces_sample_rate=rate) as transport,
        capture_json_stdout() as capture,
    ):
        status = wsgi_request("/boom/424242/", headers=headers)
        sentry_sdk.flush()

    assert status == baseline_status == 500
    trace_ids = {line["trace_id"] for line in capture.lines()}
    sent = [*transport.events(), *transport.transactions()]
    sent_trace_ids = {item["contexts"]["trace"]["trace_id"] for item in sent}
    assert len(trace_ids) == 1
    assert len(transport.events()) == 1
    assert len(transport.transactions()) == (0 if rate is None else 1)
    assert sent_trace_ids == trace_ids
    everything_observable = capture.text + transport.serialized()
    leaked = [
        value
        for value in [*CLIENT_BAGGAGE_VALUES, CLIENT_SPAN_ID]
        if value in everything_observable
    ]
    assert leaked == []
