"""CSRF-protected session account endpoints."""

from __future__ import annotations

from typing import cast

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import LoginSerializer, PublicUserSerializer, SignupSerializer


@require_GET
@ensure_csrf_cookie
def csrf(_: HttpRequest) -> HttpResponse:
    """Ensure that a same-origin browser has a CSRF cookie."""
    return HttpResponse(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=extend_schema(
        auth=[],
        request=SignupSerializer,
        responses={201: PublicUserSerializer},
    )
)
class SignupView(APIView):
    """Create an account and establish its authenticated session."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        """Validate, create, and log in a public signup request."""
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request._request, user)
        return Response(PublicUserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=extend_schema(
        auth=[],
        request=LoginSerializer,
        responses={200: PublicUserSerializer},
    )
)
class LoginView(APIView):
    """Authenticate valid credentials into a new session."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        """Return one non-disclosing response for any credential failure."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request._request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request._request, user)
        return Response(PublicUserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(post=extend_schema(request=None, responses={204: None}))
class LogoutView(APIView):
    """Invalidate the caller's active authenticated session."""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        """End the session without returning account details."""
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(get=extend_schema(responses={200: PublicUserSerializer}))
class CurrentUserView(APIView):
    """Return the authenticated user's public representation."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        """Serialize the caller without exposing account privileges."""
        return Response(PublicUserSerializer(cast(User, request.user)).data)
