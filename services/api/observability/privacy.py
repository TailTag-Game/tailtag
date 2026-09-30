"""Canonical telemetry privacy policy: allow-lists, redaction, and Sentry scrubbers.

Everything that decides what may leave the process lives here so the log
formatter and the Sentry hooks cannot drift apart. The policy is identical in
every environment. See `docs/architecture/backend/observability.md` §6.
"""

from __future__ import annotations

import logging
import re
import threading
from functools import cache
from typing import Any, Final, cast

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver
from sentry_sdk.types import Metric

_LOGGER = logging.getLogger(__name__)

_REDACTED: Final = "[redacted]"

# Unmistakable sensitive shapes only; a bare catch token in free text is not
# pattern-detectable, so Semgrep (not this backstop) is the control for that.
_TEXT_REDACTIONS: Final = (
    (re.compile(r"(?i)\bBearer\s+[^\s,;\"']+"), f"Bearer {_REDACTED}"),
    (re.compile(r"\beyJ[\w-]*\.[\w-]+\.[\w-]*"), _REDACTED),
    (re.compile(r"tailtag:catch:v1:[\w-]+"), _REDACTED),
    (re.compile(r"\?[\w.~%-]+=[^\s\"'<>]*"), f"?{_REDACTED}"),
)
_URL_TAIL: Final = re.compile(r"[?#]\S*")

_URL_DATA_KEYS: Final = ("url", "http.url", "url.full")
_REMOVED_URL_PART_KEYS: Final = ("http.query", "http.fragment")
_SQL_PARAMETER_PREFIXES: Final = ("db.params", "db.query.parameter.")

# Metric attributes the SDK attaches itself; anything else must be allow-listed.
SDK_METRIC_ATTRIBUTES: Final = frozenset(
    {"sentry.environment", "sentry.release", "sentry.sdk.name", "sentry.sdk.version"}
)
_HTTP_METHODS: Final = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}
)
# Fixed values for a request that matched no route or used an unknown method, so
# the request metric never carries a raw path or a client-chosen method.
UNMATCHED_ROUTE: Final = "<unmatched>"
OTHER_METHOD: Final = "_OTHER"
_STATUS_CLASSES: Final = frozenset(f"{digit}xx" for digit in range(1, 6))
# #213 populates the outcome and reason enumerations; until then nothing passes.
_OUTCOMES: Final[frozenset[str]] = frozenset()
_REASONS: Final[frozenset[str]] = frozenset()

# Attributes the SDK attaches on its own and this policy strips by design; they are
# dropped silently so they do not warn on every process.
_SILENT_STRIP_KEYS: Final = frozenset({"server.address"})
_SILENT_STRIP_PREFIXES: Final = ("process.runtime.", "user.")

_warned_rejections: set[str] = set()
_warned_lock = threading.Lock()


def normalize_method(method: str | None) -> str:
    """Return a known HTTP method, or the fixed `_OTHER` value."""
    return method if method in _HTTP_METHODS else OTHER_METHOD


def redact_text(text: str) -> str:
    """Redact unmistakable sensitive shapes while keeping the surrounding text."""
    for pattern, replacement in _TEXT_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def strip_query_and_fragment(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in cast("list[Any]", value)]
    if isinstance(value, dict):
        return {
            key: _redact_value(item)
            for key, item in cast("dict[Any, Any]", value).items()
        }
    return value


def _mapping(value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def scrub_event_text(event: dict[str, Any]) -> None:
    """Redact log-entry messages/params and exception values on an error event."""
    if isinstance(event.get("message"), str):
        event["message"] = redact_text(event["message"])
    logentry = _mapping(event.get("logentry"))
    if logentry is not None:
        for field in ("message", "formatted", "params"):
            if field in logentry:
                logentry[field] = _redact_value(logentry[field])
    exception = _mapping(event.get("exception"))
    for entry in cast("list[Any]", (exception or {}).get("values") or []):
        entry = _mapping(entry)
        if entry is not None and isinstance(entry.get("value"), str):
            entry["value"] = redact_text(entry["value"])


def scrub_url_data(data: dict[str, Any]) -> None:
    """Remove query strings, fragments, and SQL parameters from span/breadcrumb data."""
    for key in _URL_DATA_KEYS:
        if isinstance(data.get(key), str):
            data[key] = strip_query_and_fragment(data[key])
    # Breadcrumb data is caller-supplied, so a key may not be a string.
    for key in [
        key
        for key in cast("dict[Any, Any]", data)
        if isinstance(key, str)
        and (key in _REMOVED_URL_PART_KEYS or key.startswith(_SQL_PARAMETER_PREFIXES))
    ]:
        del data[key]


def _scrub_span(span: dict[str, Any]) -> None:
    description = span.get("description")
    if isinstance(description, str):
        if str(span.get("op", "")).startswith("http"):
            description = _URL_TAIL.sub("", description)
        span["description"] = redact_text(description)
    data = _mapping(span.get("data"))
    if data is not None:
        scrub_url_data(data)


def scrub_transaction(event: dict[str, Any]) -> None:
    """Scrub the root trace context and every span of a transaction event."""
    trace = _mapping((_mapping(event.get("contexts")) or {}).get("trace"))
    if trace is not None:
        _scrub_span(trace)
    for span in cast("list[Any]", event.get("spans") or []):
        span = _mapping(span)
        if span is not None:
            _scrub_span(span)


def scrub_transaction_name(event: dict[str, Any]) -> None:
    """Rename a raw-path (`url` source) transaction and drop its client-chosen URL."""
    info = _mapping(event.get("transaction_info"))
    if info is not None and info.get("source") == "url":
        event["transaction"] = UNMATCHED_ROUTE
        info["source"] = "route"
        request = _mapping(event.get("request"))
        if request is not None:
            request.pop("url", None)


@cache
def _route_templates(urlconf: str) -> frozenset[str]:
    """Every route template in the URLconf, as `request.resolver_match.route` yields."""

    def walk(patterns: list[URLPattern | URLResolver], prefix: str) -> set[str]:
        routes: set[str] = set()
        for pattern in patterns:
            route = str(pattern.pattern).removeprefix("^")
            if isinstance(pattern, URLResolver):
                routes |= walk(pattern.url_patterns, prefix + route)
            else:
                routes.add(prefix + route)
        return routes

    return frozenset(walk(get_resolver(urlconf).url_patterns, ""))


def _is_bounded(key: str, value: object) -> bool:
    if not isinstance(value, str):
        return False
    if key == "http.request.method":
        return value in _HTTP_METHODS or value == OTHER_METHOD
    if key == "http.route":
        return value == UNMATCHED_ROUTE or value in _route_templates(
            settings.ROOT_URLCONF
        )
    if key == "http.response.status_class":
        return value in _STATUS_CLASSES
    if key == "tailtag.outcome":
        return value in _OUTCOMES
    if key == "tailtag.reason":
        return value in _REASONS
    return False


def _warn_rejected(metric_name: str, key: str) -> None:
    if key in _SILENT_STRIP_KEYS or key.startswith(_SILENT_STRIP_PREFIXES):
        return
    with _warned_lock:
        if key in _warned_rejections:
            return
        _warned_rejections.add(key)
    _LOGGER.warning(
        "Metric attribute rejected by the privacy policy (metric=%s, key=%s).",
        metric_name,
        key,
    )


def scrub_metric(metric: Metric, hint: Any) -> Metric:
    """Keep SDK attributes and allow-listed, bounded dimensions; send the metric anyway."""
    attributes = metric.get("attributes") or {}
    kept: dict[str, Any] = {}
    for key, value in attributes.items():
        if key in SDK_METRIC_ATTRIBUTES or _is_bounded(key, value):
            kept[key] = value
        else:
            _warn_rejected(metric["name"], key)
    metric["attributes"] = kept
    return metric
