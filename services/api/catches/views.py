"""Authenticated HTTP boundary for the authoritative catch confirmation service."""

from __future__ import annotations

import logging
from typing import Literal, cast

from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    ErrorDetail,
    NotAuthenticated,
    ParseError,
    UnsupportedMediaType,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .serializers import (
    AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
    CATCH_CONFIRMATION_CONFLICT_ERROR_SCHEMA,
    CATCH_CONFIRMATION_FORBIDDEN_ERROR_SCHEMA,
    CATCH_CONFIRMATION_NOT_FOUND_ERROR_SCHEMA,
    CATCH_CONFIRMATION_SERVER_ERROR_SCHEMA,
    CATCH_CONFIRMATION_VALIDATION_ERROR_SCHEMA,
    CatchConfirmationRequestSchemaSerializer,
    CatchConfirmationResponseSchemaSerializer,
    FursuitCatchCredentialResolutionRequestSerializer,
    catch_confirmation_response_data,
)
from .services import (
    CatchActiveConventionMismatchError,
    CatchAuthenticationError,
    CatchConfirmationStatus,
    CatchParticipationIneligibleError,
    CatchSelfCatchError,
    CatchTargetInvalidError,
    confirm_catch,
)

_LOGGER = logging.getLogger(__name__)
_INVALID_PAYLOAD = {
    "payload": [ErrorDetail("Invalid catch credential payload.", code="invalid")]
}
_AUTHENTICATION_401 = OpenApiResponse(
    response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
    description="Authentication credentials were not provided.",
)
_CONFIRMATION_RESPONSE = OpenApiResponse(
    response=CatchConfirmationResponseSchemaSerializer
)
_OPENAPI_RESPONSES: dict[int, OpenApiResponse] = {
    200: _CONFIRMATION_RESPONSE,
    201: _CONFIRMATION_RESPONSE,
    400: OpenApiResponse(
        response=CATCH_CONFIRMATION_VALIDATION_ERROR_SCHEMA,
        description="The supplied catch credential payload is invalid.",
    ),
    401: _AUTHENTICATION_401,
    403: OpenApiResponse(
        response=CATCH_CONFIRMATION_FORBIDDEN_ERROR_SCHEMA,
        description="Request not permitted.",
    ),
    404: OpenApiResponse(
        response=CATCH_CONFIRMATION_NOT_FOUND_ERROR_SCHEMA,
        description="The target is unavailable; privacy-collapsed outcomes are indistinguishable.",
    ),
    409: OpenApiResponse(
        response=CATCH_CONFIRMATION_CONFLICT_ERROR_SCHEMA,
        description="The catch cannot be confirmed in the active convention.",
    ),
    500: OpenApiResponse(
        response=CATCH_CONFIRMATION_SERVER_ERROR_SCHEMA,
        description="An unexpected error occurred.",
    ),
}


class CatchConfirmationView(APIView):
    """Delegate one opaque credential to the sole catch-write authority."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (RecursionError, ParseError, UnsupportedMediaType)):
            return Response(_INVALID_PAYLOAD, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        return _unexpected_error(stage="boundary")

    @extend_schema(
        operation_id="catch_confirm",
        tags=["catches"],
        request={"application/json": CatchConfirmationRequestSchemaSerializer},
        responses=_OPENAPI_RESPONSES,
    )
    def post(self, request: Request) -> Response:
        serializer = FursuitCatchCredentialResolutionRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        try:
            result = confirm_catch(
                _user(request), payload=serializer.validated_data["payload"]
            )
        except CatchAuthenticationError:
            raise NotAuthenticated() from None
        except CatchParticipationIneligibleError:
            return _domain_error(
                "catcher_ineligible",
                "You are not eligible to catch this target.",
                status.HTTP_403_FORBIDDEN,
            )
        except CatchActiveConventionMismatchError:
            return _domain_error(
                "active_convention_mismatch",
                "Your active convention does not match the catch target.",
                status.HTTP_409_CONFLICT,
            )
        except CatchSelfCatchError:
            return _domain_error(
                "self_catch_not_allowed",
                "You cannot catch your own fursuit.",
                status.HTTP_409_CONFLICT,
            )
        except CatchTargetInvalidError:
            return _domain_error(
                "catch_target_unavailable",
                "The catch target is unavailable.",
                status.HTTP_404_NOT_FOUND,
            )
        except Exception:  # noqa: BLE001 - all untyped service failures are sanitized.
            return _unexpected_error(stage="service")

        response_status = (
            status.HTTP_201_CREATED
            if result.status is CatchConfirmationStatus.CREATED
            else status.HTTP_200_OK
        )
        try:
            return Response(
                catch_confirmation_response_data(result, request=request),
                status=response_status,
            )
        except Exception:  # noqa: BLE001 - projection failures are sanitized.
            return _unexpected_error(stage="projection")


def _user(request: Request) -> User:
    return cast(User, request.user)


def _domain_error(code: str, detail: str, response_status: int) -> Response:
    return Response({"code": code, "detail": detail}, status=response_status)


def _unexpected_error(
    *, stage: Literal["boundary", "service", "projection"]
) -> Response:
    _LOGGER.error("Unexpected catch confirmation failure.", extra={"stage": stage})
    return _domain_error(
        "server_error",
        "An unexpected error occurred.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
