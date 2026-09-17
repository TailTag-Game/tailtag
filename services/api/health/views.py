"""Unauthenticated service health endpoints."""

from __future__ import annotations

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


def ready(_: HttpRequest) -> JsonResponse:
    """Report whether safe effective configuration and PostgreSQL are usable."""
    try:
        validate_configuration()
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except (DatabaseError, ImproperlyConfigured, OSError):
        return health_response("unavailable", status_code=503)
    return health_response("ok")


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
