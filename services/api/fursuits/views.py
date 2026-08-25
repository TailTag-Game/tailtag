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
from rest_framework.exceptions import ErrorDetail, UnsupportedMediaType
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from fursuits import services
from fursuits.models import Fursuit
from fursuits.normalization import FursuitNameError
from fursuits.parsers import ClosedMultiPartParser, MultipartContract
from fursuits.serializers import (
    FURSUIT_CREATE_REQUEST_SCHEMA,
    FURSUIT_NAME_PATCH_REQUEST_SCHEMA,
    FURSUIT_PHOTO_REQUEST_SCHEMA,
    FURSUIT_RESPONSE_SCHEMA,
    MEDIA_ERROR_MESSAGES,
    FursuitCreateSerializer,
    FursuitNamePatchSerializer,
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
        }
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
    """Retrieve or rename a private player record."""

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
        }
    )
    def get(self, request: Request, id: int) -> Response:
        return _fursuit_response(_owned_or_404(_user(request), id))

    @extend_schema(
        operation_id="fursuits_update_name",
        request={"application/json": FURSUIT_NAME_PATCH_REQUEST_SCHEMA},
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
        serializer = FursuitNamePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fursuit = services.update_fursuit_name(
                _user(request), fursuit_id=id, name=serializer.validated_data["name"]
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
