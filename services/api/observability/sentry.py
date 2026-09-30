"""Sentry initialization and hooks that keep events free of request content."""

from __future__ import annotations

import logging
import math
from typing import Any, Final, cast

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Breadcrumb, BreadcrumbHint, Event, Hint

from config.build_identity import Identity

from .logging import ALLOWED_EXTRA_FIELDS
from .privacy import (
    redact_text,
    scrub_event_text,
    scrub_metric,
    scrub_transaction,
    scrub_transaction_name,
    scrub_url_data,
    strip_query_and_fragment,
)

_REMOVED_REQUEST_FIELDS = ("query_string", "data", "cookies", "headers")
_UNTRACED_PATHS: Final = frozenset({"/health/live", "/health/ready"})
_TRACES_SAMPLE_RATE_VARIABLE: Final = "SENTRY_TRACES_SAMPLE_RATE"


def parse_traces_sample_rate(value: str | None) -> float | None:
    """Parse `SENTRY_TRACES_SAMPLE_RATE`: unset or empty means tracing off.

    A rejected value is never echoed in the error.
    """
    if not value:
        return None
    message = f"{_TRACES_SAMPLE_RATE_VARIABLE} must be a number from 0 to 1, or unset."
    try:
        rate = float(value)
    except ValueError:
        raise RuntimeError(message) from None
    if not math.isfinite(rate) or not 0 <= rate <= 1:
        raise RuntimeError(message)
    return rate


def _allow_listed(values: object) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    items = cast("dict[str, Any]", values)
    return {key: value for key, value in items.items() if key in ALLOWED_EXTRA_FIELDS}


def _scrub_event(event: Event, source_sha: str | None) -> Event:
    scrubbed = cast("dict[str, Any]", event)
    request: object = scrubbed.get("request")
    if isinstance(request, dict):
        request_fields = cast("dict[str, Any]", request)
        for field in _REMOVED_REQUEST_FIELDS:
            request_fields.pop(field, None)
        url = request_fields.get("url")
        if isinstance(url, str):
            request_fields["url"] = strip_query_and_fragment(url)
    if "extra" in scrubbed:
        scrubbed["extra"] = _allow_listed(scrubbed["extra"])
    scrub_event_text(scrubbed)
    if source_sha is None:
        scrubbed.pop("release", None)
    else:
        scrubbed["release"] = source_sha
    return event


def before_breadcrumb(crumb: Breadcrumb, hint: BreadcrumbHint) -> Breadcrumb:
    """Allow-list log `extra` fields, redact messages, and strip URL queries."""
    if "log_record" in hint and "data" in crumb:
        crumb["data"] = _allow_listed(crumb["data"])
    message = crumb.get("message")
    if isinstance(message, str):
        crumb["message"] = redact_text(message)
    data: object = crumb.get("data")
    if isinstance(data, dict):
        scrub_url_data(cast("dict[str, Any]", data))
    return crumb


def init_sentry(
    dsn: str | None,
    identity: Identity | None,
    *,
    traces_sample_rate: float | None = None,
) -> bool:
    """Initialize Sentry when a DSN is configured; report whether it was.

    Tracing is on only when a rate is given; health checks are never traced.
    """
    if not dsn:
        return False
    source_sha = identity["source_sha"] if identity is not None else None
    environment = identity["environment"] if identity is not None else None

    def before_send(event: Event, hint: Hint) -> Event:
        return _scrub_event(event, source_sha)

    def before_send_transaction(event: Event, hint: Hint) -> Event:
        scrubbed = _scrub_event(event, source_sha)
        scrub_transaction(cast("dict[str, Any]", scrubbed))
        scrub_transaction_name(cast("dict[str, Any]", scrubbed))
        return scrubbed

    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        # Only the configured rate applies: an incoming `parent_sampled` is ignored
        # so a client cannot force tracing on.
        environ: object = sampling_context.get("wsgi_environ")
        if isinstance(environ, dict):
            path = cast("dict[str, Any]", environ).get("PATH_INFO")
            if path in _UNTRACED_PATHS:
                return 0
        return traces_sample_rate or 0.0

    tracing: dict[str, Any] = (
        {} if traces_sample_rate is None else {"traces_sampler": traces_sampler}
    )

    sentry_sdk.init(
        dsn=dsn,
        environment=environment or "unknown",
        release=source_sha,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        before_send=before_send,
        before_send_transaction=before_send_transaction,
        before_send_metric=scrub_metric,
        before_breadcrumb=before_breadcrumb,
        **tracing,
    )
    if source_sha is None:
        # The SDK guesses a release from SENTRY_RELEASE, git, or CI variables
        # when none is given; build identity is the only allowed source.
        sentry_sdk.get_client().options["release"] = None
    return True
