"""Request correlation: server-generated request ID, timing, completion log."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Final

import sentry_sdk
from django.core.signals import request_finished
from django.http import HttpRequest
from django.http.response import HttpResponseBase

from .context import railway_request_id_var, request_id_var
from .privacy import UNMATCHED_ROUTE, normalize_method

REQUEST_METRIC: Final = "tailtag.http.server.requests"

_RAILWAY_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
_logger = logging.getLogger("tailtag.request")


def _clear_context(**_: object) -> None:
    """Clear the IDs once the response is closed.

    Django logs 4xx responses after the middleware chain returns, so clearing
    here keeps those lines correlated. Test client and WSGI servers both close
    the response, which sends this signal.
    """
    request_id_var.set(None)
    railway_request_id_var.set(None)


request_finished.connect(  # pyright: ignore[reportUnknownMemberType]
    _clear_context, dispatch_uid="tailtag.request_correlation"
)


def _valid_railway_request_id(value: str | None) -> str | None:
    if value is not None and _RAILWAY_REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return None


class RequestCorrelationMiddleware:
    """Give every request its own ID and log one completion line for it.

    Client-supplied correlation headers are ignored. Railway's edge ID is recorded
    only when it is well formed.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        request_id = uuid.uuid4().hex
        railway_request_id = _valid_railway_request_id(
            request.META.get("HTTP_X_RAILWAY_REQUEST_ID")
        )
        request_id_var.set(request_id)
        railway_request_id_var.set(railway_request_id)
        started = time.perf_counter()
        # A forked scope keeps the tags from outliving this request.
        with sentry_sdk.isolation_scope() as scope:
            scope.set_tag("request_id", request_id)
            if railway_request_id is not None:
                scope.set_tag("railway_request_id", railway_request_id)
            response = self.get_response(request)
            self._log_completion(request, response, started)
            self._count_request(request, response)
            return response

    @staticmethod
    def _log_completion(
        request: HttpRequest, response: HttpResponseBase, started: float
    ) -> None:
        extra: dict[str, object] = {
            "event": "tailtag.http.request",
            "http_request_method": request.method,
            "http_response_status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        if request.resolver_match is not None:
            extra["http_route"] = request.resolver_match.route
        _logger.info("HTTP request completed", extra=extra)

    @staticmethod
    def _count_request(request: HttpRequest, response: HttpResponseBase) -> None:
        route = request.resolver_match.route if request.resolver_match else None
        sentry_sdk.metrics.count(
            REQUEST_METRIC,
            1,
            attributes={
                "http.route": route or UNMATCHED_ROUTE,
                "http.request.method": normalize_method(request.method),
                "http.response.status_class": f"{response.status_code // 100}xx",
            },
        )
