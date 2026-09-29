"""Sentry initialization and hooks that keep events free of request content."""

from __future__ import annotations

import logging
from typing import Any, cast

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
    scrub_url_data,
    strip_query_and_fragment,
)

_REMOVED_REQUEST_FIELDS = ("query_string", "data", "cookies", "headers")


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


def init_sentry(dsn: str | None, identity: Identity | None) -> bool:
    """Initialize Sentry when a DSN is configured; report whether it was."""
    if not dsn:
        return False
    source_sha = identity["source_sha"] if identity is not None else None
    environment = identity["environment"] if identity is not None else None

    def before_send(event: Event, hint: Hint) -> Event:
        return _scrub_event(event, source_sha)

    def before_send_transaction(event: Event, hint: Hint) -> Event:
        scrubbed = _scrub_event(event, source_sha)
        scrub_transaction(cast("dict[str, Any]", scrubbed))
        return scrubbed

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
    )
    if source_sha is None:
        # The SDK guesses a release from SENTRY_RELEASE, git, or CI variables
        # when none is given; build identity is the only allowed source.
        sentry_sdk.get_client().options["release"] = None
    return True
