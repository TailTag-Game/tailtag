"""Unauthenticated service health endpoints."""

from __future__ import annotations

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse


def health_response(status: str, status_code: int = 200) -> JsonResponse:
    """Return a non-cacheable health response."""
    response = JsonResponse({"status": status}, status=status_code)
    response["Cache-Control"] = "no-store"
    return response


def live(_: HttpRequest) -> JsonResponse:
    """Report whether the process can accept requests without querying PostgreSQL."""
    return health_response("ok")


def ready(_: HttpRequest) -> JsonResponse:
    """Report whether the process can connect to PostgreSQL."""
    try:
        connection.ensure_connection()
    except DatabaseError:
        return health_response("unavailable", status_code=503)
    return health_response("ok")
