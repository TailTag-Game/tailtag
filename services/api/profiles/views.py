"""Authenticated HTTP adapter for player text-profile operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, cast

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail, UnsupportedMediaType
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from media.images import ImageValidationError
from profiles.models import PlayerProfile
from profiles.serializers import (
    MEDIA_ERROR_MESSAGES,
    AvatarPutSerializer,
    ProfilePatchSerializer,
    ProfilePutSerializer,
    ProfileResponseSerializer,
    profile_response_data,
)
from profiles.services import (
    DuplicateHandleError,
    ProfileDisabledError,
    ProfileIncompleteError,
    ProfileValueError,
    get_or_create_profile,
    patch_text_profile,
    put_text_profile,
    remove_profile_avatar,
    replace_profile_avatar,
)

if TYPE_CHECKING:
    from django.core.files import File


class ProfileView(APIView):
    """Read or mutate the authenticated user's private player profile."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: ProfileResponseSerializer})
    def get(self, request: Request) -> Response:
        return _profile_response(get_or_create_profile(_user(request)))

    @extend_schema(
        request=ProfilePutSerializer,
        responses={200: ProfileResponseSerializer},
        description="Replace both text fields while preserving the independently managed avatar.",
    )
    def put(self, request: Request) -> Response:
        serializer = ProfilePutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = put_text_profile(_user(request), **serializer.validated_data)
        except (
            DuplicateHandleError,
            ProfileValueError,
            ProfileIncompleteError,
            ProfileDisabledError,
        ) as error:
            _raise_domain_error(error)
        return _profile_response(profile)

    @extend_schema(
        request=ProfilePatchSerializer, responses={200: ProfileResponseSerializer}
    )
    def patch(self, request: Request) -> Response:
        serializer = ProfilePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        ErrorDetail("Provide a profile field.", code="required")
                    ]
                }
            )
        try:
            profile = patch_text_profile(_user(request), **serializer.validated_data)
        except (
            DuplicateHandleError,
            ProfileValueError,
            ProfileIncompleteError,
            ProfileDisabledError,
        ) as error:
            _raise_domain_error(error)
        return _profile_response(profile)


class ProfileAvatarView(APIView):
    """Mutate the authenticated user's independently managed avatar."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, UnsupportedMediaType):
            return Response(
                {"avatar": [ErrorDetail("Upload a valid image.", code="invalid")]},
                status=400,
            )
        return super().handle_exception(exc)

    def put(self, request: Request) -> Response:
        _require_avatar_mutation_enabled(_user(request))
        serializer = AvatarPutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = replace_profile_avatar(
                _user(request),
                upload=cast("File[bytes]", serializer.validated_data["avatar"]),
            )
        except ImageValidationError as error:
            raise serializers.ValidationError(
                {
                    "avatar": [
                        ErrorDetail(
                            MEDIA_ERROR_MESSAGES[error.code], code=error.code.value
                        )
                    ]
                }
            ) from None
        except ProfileDisabledError as error:
            _raise_domain_error(error)
        return _profile_response(profile)

    def delete(self, request: Request) -> Response:
        try:
            remove_profile_avatar(_user(request))
        except ProfileDisabledError as error:
            _raise_domain_error(error)
        return Response(status=204)


def _user(request: Request) -> User:
    return cast(User, request.user)


def _profile_response(profile: PlayerProfile) -> Response:
    return Response(profile_response_data(profile))


def _require_avatar_mutation_enabled(user: User) -> None:
    """Reject disabled avatar writes before multipart parsing or media work."""
    if not get_or_create_profile(user).is_enabled:
        raise PermissionDenied()


def _raise_domain_error(
    error: DuplicateHandleError
    | ProfileValueError
    | ProfileIncompleteError
    | ProfileDisabledError,
) -> NoReturn:
    if isinstance(error, DuplicateHandleError):
        raise serializers.ValidationError(
            {"handle": [ErrorDetail("This handle is already in use.", code="unique")]}
        ) from None
    if isinstance(error, ProfileValueError):
        raise serializers.ValidationError(
            {error.field: [ErrorDetail(error.safe_message, code=error.code)]}
        ) from None
    if isinstance(error, ProfileIncompleteError):
        raise serializers.ValidationError(
            {
                "non_field_errors": [
                    ErrorDetail(
                        "Complete onboarding with PUT before using PATCH.",
                        code="incomplete",
                    )
                ]
            }
        ) from None
    raise PermissionDenied() from None
