"""Django REST Framework integration for verified Clerk identities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException

from accounts.models import User
from accounts.resolution import (
    ApplicationUserResolutionUnavailable,
    resolve_application_user,
)
from authentication.clerk import ClerkSessionVerifier

if TYPE_CHECKING:
    from rest_framework.request import Request


class _ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable."
    default_code = "service_unavailable"


class TailTagAuthentication(BaseAuthentication):
    """Expose a resolved TailTag user through DRF's authentication contract."""

    def authenticate(self, request: Request) -> tuple[User, None] | None:
        configuration = settings.CLERK_AUTHENTICATION
        if configuration is None:
            return None

        identity = ClerkSessionVerifier(configuration).verify(request._request)
        if identity is None:
            return None

        try:
            user = resolve_application_user(identity.subject)
        except ApplicationUserResolutionUnavailable:
            raise _ServiceUnavailable() from None
        return user, None

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"
