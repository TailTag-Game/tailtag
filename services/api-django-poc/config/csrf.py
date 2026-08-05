"""API-safe CSRF failure behavior."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse


def csrf_failure(_: HttpRequest, reason: str = "") -> JsonResponse:
    """Return a stable JSON error without exposing CSRF internals."""
    del reason
    return JsonResponse({"detail": "CSRF validation failed."}, status=403)
