"""Authenticated owner-scoped HTTP adapters for durable fursuits."""

from __future__ import annotations

from collections.abc import Iterable
from typing import NoReturn, cast

from django.core.exceptions import PermissionDenied
from django.http import Http404
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import serializers, status
from rest_framework.exceptions import (
    ErrorDetail,
    NotFound,
    ParseError,
    UnsupportedMediaType,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from config.catch_requests_gate import catch_requests_enabled
from fursuits import services, tags
from fursuits.models import Fursuit
from fursuits.normalization import FursuitNameError
from fursuits.parsers import ClosedMultiPartParser, MultipartContract
from fursuits.serializers import (
    FURSUIT_CREATE_REQUEST_SCHEMA,
    FURSUIT_PATCH_REQUEST_SCHEMA,
    FURSUIT_PHOTO_REQUEST_SCHEMA,
    FURSUIT_RESPONSE_SCHEMA,
    FURSUIT_TAG_CONFLICT_ERROR_SCHEMA,
    FURSUIT_TAG_ERROR_SCHEMA,
    FURSUIT_TAG_REPLACE_REQUEST_SCHEMA,
    FURSUIT_TAG_REPLACE_VALIDATION_ERROR_SCHEMA,
    FURSUIT_TAG_RESPONSE_SCHEMA,
    MEDIA_ERROR_MESSAGES,
    FursuitCreateSerializer,
    FursuitPatchSerializer,
    FursuitPhotoSerializer,
    fursuit_response_data,
)
from media.images import ImageValidationError

_AUTH_401 = OpenApiResponse(description="Authentication credentials were not provided.")
_FORBIDDEN_403 = OpenApiResponse(description="The player profile is not eligible.")
_NOT_FOUND_404 = OpenApiResponse(description="The fursuit was not found.")
_INVALID_400 = OpenApiResponse(description="The supplied fursuit data is invalid.")
_METHOD_405 = OpenApiResponse(description="Method not allowed.")
_SERVER_500 = OpenApiResponse(description="An unexpected server error occurred.")
_FURSUIT_LIST_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": FURSUIT_RESPONSE_SCHEMA,
}


class _FursuitAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    unsupported_media_error_field = "photo"

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, UnsupportedMediaType):
            return Response(
                {
                    self.unsupported_media_error_field: [
                        ErrorDetail("Upload a valid image.", code="invalid")
                    ]
                },
                status=400,
            )
        return super().handle_exception(exc)


class FursuitListCreateView(_FursuitAPIView):
    """List owned records or create one required-photo record."""

    parser_classes = (ClosedMultiPartParser,)
    multipart_contract = MultipartContract(
        value_fields=frozenset({"name"}), file_fields=frozenset({"photo"})
    )

    @extend_schema(
        operation_id="fursuits_list",
        responses={
            200: OpenApiResponse(response=_FURSUIT_LIST_SCHEMA),
            401: _AUTH_401,
            405: _METHOD_405,
            500: _SERVER_500,
        },
    )
    def get(self, request: Request) -> Response:
        fursuits = Fursuit.objects.filter(owner=_user(request)).order_by("id")
        return _fursuit_list_response(fursuits)

    @extend_schema(
        operation_id="fursuits_create",
        request={"multipart/form-data": FURSUIT_CREATE_REQUEST_SCHEMA},
        responses={
            201: OpenApiResponse(response=FURSUIT_RESPONSE_SCHEMA),
            400: _INVALID_400,
            401: _AUTH_401,
            403: _FORBIDDEN_403,
            405: _METHOD_405,
            500: _SERVER_500,
        },
    )
    def post(self, request: Request) -> Response:
        _require_eligible(_user(request))
        serializer = FursuitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fursuit = services.create_fursuit(
                _user(request),
                name=cast(str, serializer.validated_data["name"]),
                photo=serializer.validated_data["photo"],  # type: ignore[arg-type]
            )
        except ImageValidationError as error:
            _raise_image_error(error)
        except FursuitNameError as error:
            _raise_name_error(error)
        except services.FursuitWriteIneligibleError:
            raise PermissionDenied from None
        return _fursuit_response(fursuit, status_code=status.HTTP_201_CREATED)


class FursuitDetailView(_FursuitAPIView):
    """Retrieve a private player record, or change its name or approval mode."""

    parser_classes = (JSONParser,)
    unsupported_media_error_field = "name"

    @extend_schema(
        operation_id="fursuits_retrieve",
        responses={
            200: OpenApiResponse(response=FURSUIT_RESPONSE_SCHEMA),
            401: _AUTH_401,
            404: _NOT_FOUND_404,
            405: _METHOD_405,
            500: _SERVER_500,
        },
    )
    def get(self, request: Request, id: int) -> Response:
        return _fursuit_response(_owned_or_404(_user(request), id))

    @extend_schema(
        operation_id="fursuits_update",
        request={"application/json": FURSUIT_PATCH_REQUEST_SCHEMA},
        responses={
            200: OpenApiResponse(response=FURSUIT_RESPONSE_SCHEMA),
            400: _INVALID_400,
            401: _AUTH_401,
            403: _FORBIDDEN_403,
            404: _NOT_FOUND_404,
            405: _METHOD_405,
            500: _SERVER_500,
        },
    )
    def patch(self, request: Request, id: int) -> Response:
        _owned_or_404(_user(request), id)
        _require_eligible(_user(request))
        serializer = FursuitPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fursuit = services.update_fursuit(
                _user(request),
                fursuit_id=id,
                name=serializer.validated_data.get("name"),
                catch_approval_mode=serializer.validated_data.get(
                    "catch_approval_mode"
                ),
            )
        except FursuitNameError as error:
            _raise_name_error(error)
        except Fursuit.DoesNotExist:
            raise Http404 from None
        except services.FursuitWriteIneligibleError:
            raise PermissionDenied from None
        return _fursuit_response(fursuit)


class FursuitPhotoView(_FursuitAPIView):
    """Replace the required photo of a private player record."""

    parser_classes = (ClosedMultiPartParser,)
    multipart_contract = MultipartContract(
        value_fields=frozenset(), file_fields=frozenset({"photo"})
    )

    @extend_schema(
        operation_id="fursuits_replace_photo",
        request={"multipart/form-data": FURSUIT_PHOTO_REQUEST_SCHEMA},
        responses={
            200: OpenApiResponse(response=FURSUIT_RESPONSE_SCHEMA),
            400: _INVALID_400,
            401: _AUTH_401,
            403: _FORBIDDEN_403,
            404: _NOT_FOUND_404,
            405: _METHOD_405,
            500: _SERVER_500,
        },
    )
    def put(self, request: Request, id: int) -> Response:
        _owned_or_404(_user(request), id)
        _require_eligible(_user(request))
        serializer = FursuitPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fursuit = services.replace_fursuit_photo(
                _user(request),
                fursuit_id=id,
                photo=serializer.validated_data["photo"],  # type: ignore[arg-type]
            )
        except ImageValidationError as error:
            _raise_image_error(error)
        except Fursuit.DoesNotExist:
            raise Http404 from None
        except services.FursuitWriteIneligibleError:
            raise PermissionDenied from None
        return _fursuit_response(fursuit)


_TAG_RESPONSES: dict[int, OpenApiResponse] = {
    200: OpenApiResponse(response=FURSUIT_TAG_RESPONSE_SCHEMA),
    401: _AUTH_401,
    403: _FORBIDDEN_403,
    404: OpenApiResponse(
        response=FURSUIT_TAG_ERROR_SCHEMA,
        description=(
            "fursuit_not_found when the caller does not own the suit. While the "
            "catch request gate is off, every call returns the generic not-found shape."
        ),
    ),
    405: _METHOD_405,
    409: OpenApiResponse(
        response=FURSUIT_TAG_CONFLICT_ERROR_SCHEMA,
        description="fursuit_disabled, or tag_version_conflict for a replacement.",
    ),
    500: _SERVER_500,
}
_INVALID_EXPECTED_VERSION = {
    "expected_version": [
        ErrorDetail("A non-negative integer is required.", code="invalid")
    ]
}


class _FursuitTagAPIView(APIView):
    """Owner tag routes. The catch request gate hides them while it is off."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        if not catch_requests_enabled():
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (ParseError, UnsupportedMediaType)):
            return Response(_INVALID_EXPECTED_VERSION, status=400)
        return super().handle_exception(exc)


class FursuitTagView(_FursuitTagAPIView):
    """Return the owner's reusable tag. The first read creates the first tag."""

    @extend_schema(
        operation_id="fursuit_tag_retrieve",
        tags=["fursuits"],
        description=(
            "Return the current reusable tag for an owned suit. The first read "
            "creates the first tag. After an operator revocation, the read returns "
            "state revoked and no payload, and never creates a replacement."
        ),
        responses=_TAG_RESPONSES,
    )
    def get(self, request: Request, id: int) -> Response:
        try:
            view = tags.get_or_create_owner_tag(_user(request), fursuit_id=id)
        except Fursuit.DoesNotExist:
            return _fursuit_not_found()
        except tags.TagOwnerIneligibleError:
            raise PermissionDenied from None
        except tags.TagFursuitDisabledError:
            return _fursuit_disabled()
        return _tag_response(view)


class FursuitTagReplaceView(_FursuitTagAPIView):
    """Replace the owner's reusable tag when the sent version is current."""

    @extend_schema(
        operation_id="fursuit_tag_replace",
        tags=["fursuits"],
        description=(
            "Replace the tag when expected_version matches the current tag_version. "
            "Old copies stop working. A stale version returns tag_version_conflict "
            "and changes nothing. After a lost response, read the tag again and "
            "never replace again automatically."
        ),
        request={"application/json": FURSUIT_TAG_REPLACE_REQUEST_SCHEMA},
        responses={
            **_TAG_RESPONSES,
            400: OpenApiResponse(
                response=FURSUIT_TAG_REPLACE_VALIDATION_ERROR_SCHEMA,
                description="expected_version is missing or not a non-negative integer.",
            ),
        },
    )
    def post(self, request: Request, id: int) -> Response:
        if not Fursuit.objects.filter(pk=id, owner=_user(request)).exists():
            return _fursuit_not_found()
        expected_version = _expected_version(request.data)
        if expected_version is None:
            return Response(_INVALID_EXPECTED_VERSION, status=400)
        try:
            view = tags.replace_owner_tag(
                _user(request), fursuit_id=id, expected_version=expected_version
            )
        except Fursuit.DoesNotExist:
            return _fursuit_not_found()
        except tags.TagOwnerIneligibleError:
            raise PermissionDenied from None
        except tags.TagFursuitDisabledError:
            return _fursuit_disabled()
        except tags.TagVersionConflictError as error:
            return _tag_conflict(error.current)
        return _tag_response(view)


def _expected_version(data: object) -> int | None:
    if not isinstance(data, dict) or set(cast(dict[str, object], data)) != {
        "expected_version"
    }:
        return None
    value = cast(dict[str, object], data)["expected_version"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _tag_response(view: tags.TagView) -> Response:
    """Return an owner-only tag without permitting intermediary storage."""
    response = Response(
        {
            "fursuit_id": view.fursuit_id,
            "state": str(view.state),
            "tag_version": view.tag_version,
            "payload": view.payload,
        }
    )
    response["Cache-Control"] = "no-store"
    return response


def _tag_conflict(current: tags.TagView) -> Response:
    response = Response(
        {
            "code": "tag_version_conflict",
            "detail": "The tag changed. Read the current tag.",
            "current": {
                "fursuit_id": current.fursuit_id,
                "state": str(current.state),
                "tag_version": current.tag_version,
            },
        },
        status=status.HTTP_409_CONFLICT,
    )
    response["Cache-Control"] = "no-store"
    return response


def _fursuit_not_found() -> Response:
    return Response(
        {"code": "fursuit_not_found", "detail": "The fursuit was not found."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _fursuit_disabled() -> Response:
    return Response(
        {"code": "fursuit_disabled", "detail": "The fursuit is disabled."},
        status=status.HTTP_409_CONFLICT,
    )


def _user(request: Request) -> User:
    return cast(User, request.user)


def _owned_or_404(user: User, fursuit_id: int) -> Fursuit:
    try:
        return services.get_owned_fursuit(user, fursuit_id)
    except Fursuit.DoesNotExist:
        raise Http404 from None


def _require_eligible(user: User) -> None:
    try:
        services.require_fursuit_write_eligible(user)
    except services.FursuitWriteIneligibleError:
        raise PermissionDenied from None


def _raise_image_error(error: ImageValidationError) -> NoReturn:
    raise serializers.ValidationError(
        {
            "photo": [
                ErrorDetail(MEDIA_ERROR_MESSAGES[error.code], code=error.code.value)
            ]
        }
    ) from None


def _raise_name_error(error: FursuitNameError) -> NoReturn:
    raise serializers.ValidationError(
        {"name": [ErrorDetail(error.safe_message, code=error.code)]}
    ) from None


def _fursuit_response(
    fursuit: Fursuit, *, status_code: int = status.HTTP_200_OK
) -> Response:
    """Return a complete projection while preserving committed state on URL failure."""
    return Response(fursuit_response_data(fursuit), status=status_code)


def _fursuit_list_response(fursuits: Iterable[Fursuit]) -> Response:
    return Response([fursuit_response_data(fursuit) for fursuit in fursuits])
