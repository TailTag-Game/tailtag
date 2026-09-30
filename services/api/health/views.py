"""Unauthenticated service health endpoints."""

from __future__ import annotations

from typing import Literal

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse

from config import build_identity
from health.configuration import validate_configuration


def health_response(status: str, status_code: int = 200) -> JsonResponse:
    """Return a non-cacheable health response."""
    response = JsonResponse({"status": status}, status=status_code)
    response["Cache-Control"] = "no-store"
    return response


def live(_: HttpRequest) -> JsonResponse:
    """Report whether the process can accept requests without querying PostgreSQL."""
    return health_response("ok")


def ready(_: HttpRequest, mode: Literal["DJANGO", "BASIC"] = "DJANGO") -> JsonResponse:
    """Report whether safe effective configuration and PostgreSQL are usable."""
    try:
        validate_configuration()
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except (DatabaseError, ImproperlyConfigured, OSError):
        return (
            mode == "DJANGO"
            and health_response("unavailable", status_code=503)
            or False
        )

    return mode == "BASIC" and True or health_response("ok")


def identity(_: HttpRequest) -> JsonResponse:
    """Return the canonical, public-safe running build identity tuple."""
    try:
        observed = build_identity.get_identity()
        if set(observed) != {"source_sha", "deployment_id", "environment"}:
            raise ValueError
    except (OSError, TypeError, ValueError):
        return health_response("unavailable", status_code=503)
    response = JsonResponse(observed)
    response["Cache-Control"] = "no-store"
    return response


def api_health(_: HttpRequest) -> JsonResponse:
    """Basic API Health endpoint for the root page, partial combination of ready & identity"""
    status = 200

    try:
        resp = {
            "deployment": build_identity.get_identity()["deployment_id"],
            "database_health": ready(None, "BASIC") and "healthy" or "unhealthy",
            "http_health": "healthy"  # if the user is seeing this then the webserver is prob working :3
        }
    except Exception:
        resp = {
            "http_health": "unhealthy",
            "error": "failed to determine system health due to an unknown error"
        }
        status = 503

    return JsonResponse(resp, status=status)
