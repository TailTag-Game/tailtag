"""Acceptance tests for telemetry privacy and metric-cardinality enforcement (#211).

Only the Sentry network boundary is substituted (`CapturingTransport`); Sentry is
initialized through production `init_sentry`, and logs go through the configured
JSON stdout handler. Every secret below is synthetic.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest
import sentry_sdk
from django.urls import resolve

from tests.observability_test_support import (
    CapturingTransport,
    capture_json_stdout,
    identity,
    sentry_capturing,
)

SDK_ATTRIBUTES = {
    "sentry.environment",
    "sentry.release",
    "sentry.sdk.name",
    "sentry.sdk.version",
}
FORGED_CREDENTIAL = "synthetic-metric-credential-must-not-leak"
FORGED_SCOPE_VALUE = "synthetic-scope-attribute-must-not-leak"

_LOGGER = logging.getLogger("tailtag.test_telemetry_privacy")


def _emit_metric(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Emit through the real SDK API, then flush the batcher into the transport."""
    sentry_sdk.metrics.count(  # nosemgrep: tailtag.observability.direct-sentry-metrics
        name, 1, attributes=attributes
    )
    sentry_sdk.flush()


def _sent_attributes(transport: CapturingTransport) -> dict[str, Any]:
    [metric] = transport.metrics()
    return {key: entry["value"] for key, entry in metric["attributes"].items()}


# --- AC-1: metric attributes are allow-listed by key and bounded by value ---


@pytest.mark.parametrize("environment", ["development", "production"])
def test_metric_attributes_are_reduced_to_sdk_attributes_when_all_dimensions_are_unbounded(
    environment: str,
) -> None:
    """AC-1, AC-9: an allow-list (not a deny-list) applies in every environment.

    Each rejected attribute is a realistic unbounded label: an entity id, a raw
    path, an out-of-set value under an allow-listed key, a credential, an SDK
    `server.address`/`user.*`, and a scope-level attribute.
    """
    with sentry_capturing(identity(environment=environment)) as transport:
        sentry_sdk.set_attribute("scope_only", FORGED_SCOPE_VALUE)
        _emit_metric(
            "tailtag.test.hostile",
            {
                "user_id": 42,
                "fursuit_id": 7,
                "convention_id": 3,
                "request_id": "synthetic-request-id",
                "credential": FORGED_CREDENTIAL,
                "server.address": "synthetic-host",
                "user.id": "synthetic-clerk-subject",
                "user.email": "synthetic@example.invalid",
                "user.name": "synthetic-username",
                "http.route": "api/fursuits/42/",
                "http.request.method": "FROBNICATE",
                "http.response.status_class": "200",
                "tailtag.outcome": "any-value-is-rejected-until-213",
                "tailtag.reason": "any-value-is-rejected-until-213",
            },
        )

    [metric] = transport.metrics()
    assert (metric["name"], metric["type"], metric["value"]) == (
        "tailtag.test.hostile",
        "counter",
        1.0,
    )
    attributes = _sent_attributes(transport)
    assert set(attributes) == SDK_ATTRIBUTES
    assert attributes["sentry.environment"] == environment
    assert attributes["sentry.release"] == identity()["source_sha"]
    for leaked in (FORGED_CREDENTIAL, FORGED_SCOPE_VALUE, "synthetic-host"):
        assert leaked not in transport.serialized()


def test_sdk_attached_user_attributes_are_stripped_from_metrics() -> None:
    """AC-1, D6: the filter itself defends against SDK `user.*` attribution.

    `send_default_pii=False` keeps the SDK from attaching these today, so the
    option is flipped on the live client to prove the filter, not the option, is
    what keeps user identity off metrics.
    """
    with sentry_capturing(identity()) as transport:
        sentry_sdk.get_client().options["send_default_pii"] = True
        sentry_sdk.set_user(
            {
                "id": "synthetic-clerk-subject",
                "email": "synthetic@example.invalid",
                "username": "synthetic-username",
                "ip_address": "203.0.113.9",
            }
        )
        _emit_metric("tailtag.test.user")

    assert set(_sent_attributes(transport)) == SDK_ATTRIBUTES
    assert "synthetic-clerk-subject" not in transport.serialized()
    assert "203.0.113.9" not in transport.serialized()


def test_bounded_dimension_values_survive_on_metrics() -> None:
    """AC-1: the allow-list is not so narrow that legitimate dimensions vanish.

    Routes are real templates from the project URLconf, as Django reports them on
    `request.resolver_match.route`.
    """
    routes = [
        resolve(path).route
        for path in ("/api/me/", "/api/fursuits/42/", "/api/catches/confirm/")
    ]
    assert "api/fursuits/<int:id>/" in routes
    accepted = [
        *[("http.request.method", method) for method in ("GET", "POST", "DELETE")],
        *[("http.response.status_class", f"{code}xx") for code in range(1, 6)],
        *[("http.route", route) for route in routes],
    ]
    with sentry_capturing(identity()) as transport:
        for key, value in accepted:
            _emit_metric("tailtag.test.bounded", {key: value})

    sent = [
        {key: entry["value"] for key, entry in metric["attributes"].items()}
        for metric in transport.metrics()
    ]
    assert len(sent) == len(accepted)
    for (key, value), attributes in zip(accepted, sent, strict=True):
        assert attributes[key] == value
        assert SDK_ATTRIBUTES <= attributes.keys()


# --- AC-2: rejection is reported once per key, without the value ---


def test_rejected_attribute_warns_once_per_key_without_the_value() -> None:
    """AC-2: a hot-path rejection cannot flood logs or leak the rejected value.

    The same rejected key on several metrics still warns once per process, and
    attributes the SDK attaches itself are stripped silently.
    """
    key = f"unbounded_{uuid.uuid4().hex[:8]}"
    metric_names = [f"tailtag.test.warn.{uuid.uuid4().hex[:8]}" for _ in range(2)]
    with sentry_capturing(identity()), capture_json_stdout() as capture:
        for index in range(3):
            for metric_name in metric_names:
                _emit_metric(metric_name, {key: f"synthetic-rejected-value-{index}"})

    warnings = [line for line in capture.lines() if line["level"] == "warn"]
    named = [line for line in warnings if key in line["message"]]
    assert len(named) == 1
    assert any(name in named[0]["message"] for name in metric_names)
    assert "synthetic-rejected-value" not in capture.text
    sdk_keys = ("server.address", "process.runtime", "user.")
    assert [
        line["message"]
        for line in warnings
        if any(sdk_key in line["message"] for sdk_key in sdk_keys)
    ] == []


# --- AC-3 / AC-4: sensitive shapes are redacted from logs and Sentry events ---

_BEARER = "synthetic-bearer-must-not-leak"
_JWT_SEGMENTS = (
    "eyJhbGciOiJIUzI1NiJ9",
    "eyJzdWIiOiJzeW50aGV0aWMifQ",
    "c3ludGhldGljLXNpZ25hdHVyZQ",
)
_CATCH_TOKEN = "SyntheticCatchTokenMustNotLeak" + "0123456789abc"
_QUERY_SECRET = "synthetic-signature-must-not-leak"
# (id, text as it appears in a message, fragments that must not survive)
_SHAPE_CASES: list[tuple[str, str, tuple[str, ...]]] = [
    ("bearer", f"Bearer {_BEARER}", (_BEARER,)),
    ("bearer-any-case", f"bEaReR {_BEARER}", (_BEARER,)),
    ("jwt", ".".join(_JWT_SEGMENTS), _JWT_SEGMENTS),
    ("catch-credential", f"tailtag:catch:v1:{_CATCH_TOKEN}", (_CATCH_TOKEN,)),
    (
        "absolute-url-query",
        f"https://media.example.invalid/fursuits/1.jpg?X-Amz-Signature={_QUERY_SECRET}&X-Amz-Expires=600",
        (_QUERY_SECRET,),
    ),
    (
        "relative-url-query",
        f"/api/fursuits/1/photo/?X-Amz-Signature={_QUERY_SECRET}",
        (_QUERY_SECRET,),
    ),
]
_SHAPES = [pytest.param(shape, vanish, id=id_) for id_, shape, vanish in _SHAPE_CASES]
_BEFORE = "upstream refused"
_AFTER = "during cleanup"


@pytest.mark.parametrize(("shape", "vanish"), _SHAPES)
def test_log_records_are_redacted_but_keep_surrounding_text(
    shape: str, vanish: tuple[str, ...]
) -> None:
    """AC-3, AC-4: stdout lines, breadcrumbs, and error events redact, not drop.

    The shape arrives both interpolated into the message and as a lazy `%s`
    argument, because stdout, breadcrumbs, and event log entries each read a
    different form of the record.
    """
    with sentry_capturing(identity()) as transport, capture_json_stdout() as capture:
        for message, arguments in (
            (
                f"{_BEFORE} {shape} {_AFTER}",
                (),
            ),
            (f"{_BEFORE} %s {_AFTER}", (shape,)),
        ):
            _LOGGER.info(message, *arguments)
            _LOGGER.error(message, *arguments)

    lines = [line for line in capture.lines() if line["logger"] == _LOGGER.name]
    assert [line["level"] for line in lines] == ["info", "error"] * 2
    for line in lines:
        assert line["message"].startswith(_BEFORE)
        assert line["message"].endswith(_AFTER)
    events = transport.events()
    assert len(events) == 2
    for event in events:
        assert _BEFORE in str(event["logentry"])
    breadcrumbs = events[-1]["breadcrumbs"]["values"]
    assert any(_BEFORE in crumb.get("message", "") for crumb in breadcrumbs)
    for text in (capture.text, transport.serialized()):
        for fragment in (shape, *vanish):
            assert fragment not in text


def test_exception_values_are_redacted_but_keep_surrounding_text() -> None:
    """AC-4: an exception message carrying every sensitive shape does not reach Sentry."""
    shapes = [shape for _, shape, _ in _SHAPE_CASES]
    message = f"{_BEFORE} " + " and ".join(shapes) + f" {_AFTER}"
    with sentry_capturing(identity()) as transport:
        sentry_sdk.capture_exception(RuntimeError(message))

    [event] = transport.events()
    [exception] = event["exception"]["values"]
    assert exception["value"].startswith(_BEFORE)
    assert exception["value"].endswith(_AFTER)
    assert exception["value"].count(" and ") == len(shapes) - 1
    for _, shape, vanish in _SHAPE_CASES:
        for fragment in (shape, *vanish):
            assert fragment not in transport.serialized()


# --- AC-5: outgoing-HTTP breadcrumbs ---


def test_http_breadcrumbs_lose_query_and_fragment_but_keep_other_data() -> None:
    """AC-5: presigned-URL signatures in outgoing-HTTP breadcrumbs never leave."""
    with sentry_capturing(identity()) as transport:
        sentry_sdk.add_breadcrumb(
            category="httplib",
            type="http",
            data={
                "url": f"https://media.example.invalid/a.jpg?X-Amz-Signature={_QUERY_SECRET}#frag-secret",
                "http.query": f"X-Amz-Signature={_QUERY_SECRET}",
                "http.fragment": "frag-secret",
                "http.request.method": "GET",
                "http.response.status_code": 200,
            },
        )
        sentry_sdk.add_breadcrumb(category="tailtag.test", data={"stage": "kept"})
        sentry_sdk.capture_message("marker")

    [event] = transport.events()
    http_crumb, other_crumb = event["breadcrumbs"]["values"]
    assert http_crumb["data"] == {
        "url": "https://media.example.invalid/a.jpg",
        "http.request.method": "GET",
        "http.response.status_code": 200,
    }
    assert other_crumb["data"] == {"stage": "kept"}
    for secret in (_QUERY_SECRET, "frag-secret"):
        assert secret not in transport.serialized()


# --- AC-6: transaction and span scrubbing ---


def test_transaction_spans_and_trace_context_are_scrubbed() -> None:
    """AC-6: the production `before_send_transaction` hook strips URL and SQL params.

    Tracing is not enabled by `init_sentry`, so the registered hook is applied to a
    synthetic transaction; parameterized SQL text and other span data survive.
    """
    signed = f"https://media.example.invalid/a.jpg?X-Amz-Signature={_QUERY_SECRET}#frag-secret"
    url_data = {
        "url": signed,
        "http.url": signed,
        "http.query": f"X-Amz-Signature={_QUERY_SECRET}",
        "http.fragment": "frag-secret",
        "http.request.method": "GET",
    }
    sql = "SELECT id FROM fursuits WHERE owner_id = %s AND name = %s"
    event: dict[str, Any] = {
        "type": "transaction",
        "contexts": {
            "trace": {
                "op": "http.server",
                "description": f"GET {signed}",
                "data": dict(url_data),
            }
        },
        "spans": [
            {
                "op": "http.client",
                "description": f"GET {signed}",
                "data": dict(url_data),
            },
            {
                "op": "db",
                "description": sql,
                "data": {"db.system": "postgresql", "db.params": [42, _QUERY_SECRET]},
            },
        ],
    }
    with sentry_capturing(identity()):
        scrubbed = sentry_sdk.get_client().options["before_send_transaction"](event, {})

    assert scrubbed is not None
    serialized = str(scrubbed)
    for secret in (_QUERY_SECRET, "frag-secret"):
        assert secret not in serialized
    trace = scrubbed["contexts"]["trace"]
    http_span, db_span = scrubbed["spans"]
    for carrier in (trace, http_span):
        assert carrier["description"] == "GET https://media.example.invalid/a.jpg"
        assert carrier["data"] == {
            "url": "https://media.example.invalid/a.jpg",
            "http.url": "https://media.example.invalid/a.jpg",
            "http.request.method": "GET",
        }
    assert db_span["description"] == sql
    assert db_span["data"] == {"db.system": "postgresql"}


# --- AC-7: noisy third-party loggers are pinned at WARNING ---


@pytest.mark.parametrize(
    "logger_name",
    [
        "botocore",
        "boto3",
        "s3transfer",
        "urllib3",
        "django.db.backends",
    ],
)
def test_third_party_loggers_only_emit_warnings_and_above(logger_name: str) -> None:
    """AC-7: their INFO output (URLs, request detail) never reaches stdout."""
    third_party = logging.getLogger(logger_name)
    with capture_json_stdout() as capture:
        third_party.info("synthetic-info-must-not-reach-stdout")
        third_party.warning("synthetic-warning-must-reach-stdout")
        _LOGGER.info("synthetic-application-info-still-emitted")

    messages = [line["message"] for line in capture.lines()]
    assert "synthetic-info-must-not-reach-stdout" not in messages
    assert "synthetic-warning-must-reach-stdout" in messages
    assert "synthetic-application-info-still-emitted" in messages
