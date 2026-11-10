"""Authenticated HTTP boundaries for catch confirmation and player catch history."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Literal, cast

from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    ErrorDetail,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.mediatypes import (
    _MediaType,  # pyright: ignore[reportPrivateUsage]
    media_type_matches,
    order_by_precedence,
)
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from accounts.models import User
from config.catch_requests_gate import catch_requests_enabled
from conventions.models import Convention
from media import service as media_service
from observability.outcomes import Outcome, Reason, Signal, record_outcome

from .models import Catch
from .pagination import CatchHistoryPagination
from .serializers import (
    AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
    CATCH_CONFIRMATION_CONFLICT_ERROR_SCHEMA,
    CATCH_CONFIRMATION_FORBIDDEN_ERROR_SCHEMA,
    CATCH_CONFIRMATION_NOT_FOUND_ERROR_SCHEMA,
    CATCH_CONFIRMATION_SERVER_ERROR_SCHEMA,
    CATCH_CONFIRMATION_VALIDATION_ERROR_SCHEMA,
    CATCH_HISTORY_AUTHENTICATION_ERROR_SCHEMA,
    CATCH_HISTORY_INVALID_QUERY_ERROR_SCHEMA,
    CATCH_HISTORY_NOT_FOUND_ERROR_SCHEMA,
    CATCH_HISTORY_SERVER_ERROR_SCHEMA,
    CatchConfirmationRequestSchemaSerializer,
    CatchConfirmationResponseSchemaSerializer,
    CatchHistoryQueryError,
    CatchHistoryResponseSchemaSerializer,
    FursuitCatchCredentialResolutionRequestSerializer,
    catch_confirmation_response_data,
    catch_history_entry_data,
    parse_catch_history_query,
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
from .tag_preview import (
    TagPreview,
    TagPreviewCatcherIneligibleError,
    TagPreviewSelfCatchError,
    TagPreviewTargetUnavailableError,
    TagPreviewUnavailableError,
    preview_tag,
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

_CATCH_HISTORY_OPENAPI_RESPONSES: dict[int, OpenApiResponse] = {
    200: OpenApiResponse(
        response=CatchHistoryResponseSchemaSerializer,
        description=(
            "Returns the current player's matching Catch rows. An existing Convention "
            "with no catches returns 200 with empty results."
        ),
    ),
    400: OpenApiResponse(
        response=CATCH_HISTORY_INVALID_QUERY_ERROR_SCHEMA,
        description="The catch-history query is invalid.",
    ),
    401: OpenApiResponse(
        response=CATCH_HISTORY_AUTHENTICATION_ERROR_SCHEMA,
        description="Authentication is required.",
    ),
    404: OpenApiResponse(
        response=CATCH_HISTORY_NOT_FOUND_ERROR_SCHEMA,
        description=(
            "A missing Convention returns 404; an out-of-range page also returns 404."
        ),
    ),
    500: OpenApiResponse(
        response=CATCH_HISTORY_SERVER_ERROR_SCHEMA,
        description=(
            "A photo signing failure returns a sanitized 500 for the whole request."
        ),
    ),
}


class _CatchHistoryContentNegotiation(DefaultContentNegotiation):
    """Keep DRF's normal negotiation while reserving every query key for history."""

    def select_renderer(
        self,
        request: Request,
        renderers: Iterable[BaseRenderer],
        format_suffix: str | None = None,
    ) -> tuple[BaseRenderer, str]:
        """Do not let DRF's ``format`` query override bypass closed validation."""
        available_renderers = list(renderers)
        if format_suffix:
            available_renderers = self.filter_renderers(
                available_renderers, format_suffix
            )

        accepts = self.get_accept_list(request)
        for media_type_set in order_by_precedence(accepts):
            for renderer in available_renderers:
                for media_type in media_type_set:
                    if media_type_matches(renderer.media_type, media_type):
                        media_type_wrapper = _MediaType(media_type)
                        if (
                            _MediaType(renderer.media_type).precedence
                            > media_type_wrapper.precedence
                        ):
                            full_media_type = ";".join(
                                (renderer.media_type,)
                                + tuple(
                                    f"{key}={value}"
                                    for key, value in media_type_wrapper.params.items()
                                )
                            )
                            return renderer, full_media_type
                        return renderer, media_type

        raise NotAcceptable(available_renderers=available_renderers)


class CatchConfirmationView(APIView):
    """Delegate one opaque credential to the sole catch-write authority."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (RecursionError, ParseError, UnsupportedMediaType)):
            _record_confirmation_rejected(Reason.PAYLOAD_INVALID)
            return Response(_INVALID_PAYLOAD, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, ValidationError):
            _record_confirmation_rejected(Reason.PAYLOAD_INVALID)
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        return _unexpected_error(stage="boundary")

    @extend_schema(
        operation_id="catch_confirm",
        tags=["catches"],
        request={"application/json": CatchConfirmationRequestSchemaSerializer},
        responses=_OPENAPI_RESPONSES,
        deprecated=True,
    )
    def post(self, request: Request) -> Response:
        if catch_requests_enabled():
            # The catch request gate retires v1 player codes with no compatibility period.
            return _catch_target_unavailable()
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
            _record_confirmation_rejected(Reason.CATCHER_INELIGIBLE)
            return _domain_error(
                "catcher_ineligible",
                "You are not eligible to catch this target.",
                status.HTTP_403_FORBIDDEN,
            )
        except CatchActiveConventionMismatchError:
            _record_confirmation_rejected(Reason.CONVENTION_MISMATCH)
            return _domain_error(
                "active_convention_mismatch",
                "Your active convention does not match the catch target.",
                status.HTTP_409_CONFLICT,
            )
        except CatchSelfCatchError:
            _record_confirmation_rejected(Reason.SELF_CATCH)
            return _domain_error(
                "self_catch_not_allowed",
                "You cannot catch your own fursuit.",
                status.HTTP_409_CONFLICT,
            )
        except CatchTargetInvalidError as error:
            _record_confirmation_rejected(error.reason)
            return _catch_target_unavailable()
        except Exception:  # noqa: BLE001 - all untyped service failures are sanitized.
            return _unexpected_error(stage="service")

        created = result.status is CatchConfirmationStatus.CREATED
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        try:
            response = Response(
                catch_confirmation_response_data(result, request=request),
                status=response_status,
            )
        except Exception:  # noqa: BLE001 - projection failures are sanitized.
            return _unexpected_error(stage="projection")
        record_outcome(
            Signal.CATCH_CONFIRMATION,
            Outcome.CREATED if created else Outcome.ALREADY_CAUGHT,
        )
        return response


_PREVIEW_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"code": {"type": "string"}, "detail": {"type": "string"}},
    "required": ["code", "detail"],
}
_PREVIEW_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fursuit": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": "integer"},
                "tailtag_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "photo_url": {"type": "string", "format": "uri"},
            },
            "required": ["id", "tailtag_id", "name", "photo_url"],
        },
        "convention_id": {"type": "integer"},
    },
    "required": ["fursuit", "convention_id"],
}
_PREVIEW_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "payload": {
            "type": "string",
            "description": "The full scanned tag payload, https://tailtag.app/t#<token>.",
        }
    },
    "required": ["payload"],
}
_INVALID_PREVIEW_BODY = {
    "payload": [ErrorDetail("Provide the scanned tag payload.", code="invalid")]
}


class CatchPreviewView(APIView):
    """Preview a scanned reusable tag at the catcher's selected convention."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        if not catch_requests_enabled():
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (RecursionError, ParseError, UnsupportedMediaType)):
            _record_preview_rejected(Reason.PAYLOAD_INVALID)
            return Response(_INVALID_PREVIEW_BODY, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        _LOGGER.error("Unexpected tag preview failure.")
        return _domain_error(
            "server_error",
            "An unexpected error occurred.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @extend_schema(
        operation_id="catch_preview",
        tags=["catches"],
        description=(
            "Resolve a scanned tag against the caller's selected convention. Preview "
            "creates nothing. Unknown, revoked, and unavailable targets share one "
            "neutral 404."
        ),
        request={"application/json": _PREVIEW_REQUEST_SCHEMA},
        responses={
            200: OpenApiResponse(response=_PREVIEW_RESPONSE_SCHEMA),
            400: OpenApiResponse(
                response=CATCH_CONFIRMATION_VALIDATION_ERROR_SCHEMA,
                description="The body is not a JSON object with one string payload.",
            ),
            401: _AUTHENTICATION_401,
            403: OpenApiResponse(
                response=_PREVIEW_ERROR_SCHEMA, description="catcher_ineligible"
            ),
            404: OpenApiResponse(
                response=_PREVIEW_ERROR_SCHEMA,
                description=(
                    "catch_target_unavailable. While the catch request gate is off, "
                    "every call returns the generic not-found shape."
                ),
            ),
            409: OpenApiResponse(
                response=_PREVIEW_ERROR_SCHEMA,
                description="catch_requests_unavailable or self_catch_not_allowed",
            ),
            500: OpenApiResponse(
                response=CATCH_CONFIRMATION_SERVER_ERROR_SCHEMA,
                description="An unexpected error occurred.",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        data = request.data
        if (
            not isinstance(data, dict)
            or set(cast(dict[str, object], data)) != {"payload"}
            or not isinstance(cast(dict[str, object], data)["payload"], str)
        ):
            _record_preview_rejected(Reason.PAYLOAD_INVALID)
            return Response(_INVALID_PREVIEW_BODY, status=status.HTTP_400_BAD_REQUEST)
        payload = cast(str, cast(dict[str, object], data)["payload"])
        try:
            preview = preview_tag(_user(request), payload=payload)
        except TagPreviewCatcherIneligibleError as error:
            _record_preview_rejected(error.reason)
            return _domain_error(
                "catcher_ineligible",
                "You are not eligible to catch this target.",
                status.HTTP_403_FORBIDDEN,
            )
        except TagPreviewUnavailableError as error:
            _record_preview_rejected(error.reason)
            return _domain_error(
                "catch_requests_unavailable",
                "Catch requests are unavailable for this convention.",
                status.HTTP_409_CONFLICT,
            )
        except TagPreviewTargetUnavailableError as error:
            _record_preview_rejected(error.reason)
            return _catch_target_unavailable()
        except TagPreviewSelfCatchError as error:
            _record_preview_rejected(error.reason)
            return _domain_error(
                "self_catch_not_allowed",
                "You cannot catch your own fursuit.",
                status.HTTP_409_CONFLICT,
            )
        response = Response(_preview_response_data(preview, request=request))
        record_outcome(Signal.CREDENTIAL_RESOLUTION, Outcome.RESOLVED)
        return response


def _preview_response_data(
    preview: TagPreview, *, request: Request
) -> dict[str, object]:
    fursuit = preview.fursuit
    return {
        "fursuit": {
            "id": fursuit.pk,
            "tailtag_id": str(fursuit.tailtag_id),
            "name": fursuit.name,
            "photo_url": request.build_absolute_uri(
                media_service.read_image_url(fursuit.photo_key)
            ),
        },
        "convention_id": preview.convention.pk,
    }


def _record_preview_rejected(reason: Reason) -> None:
    record_outcome(Signal.CREDENTIAL_RESOLUTION, Outcome.REJECTED, reason)


def _catch_target_unavailable() -> Response:
    return _domain_error(
        "catch_target_unavailable",
        "The catch target is unavailable.",
        status.HTTP_404_NOT_FOUND,
    )


class CatchHistoryView(APIView):
    """Return the authenticated player's closed, paginated Catch history."""

    permission_classes = (IsAuthenticated,)
    http_method_names = ("get",)
    content_negotiation_class = _CatchHistoryContentNegotiation

    @extend_schema(
        operation_id="catch_history_list",
        tags=["catches"],
        request=None,
        parameters=[
            OpenApiParameter(
                name="convention_id",
                type={"type": "integer", "minimum": 1},
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional positive ASCII decimal Convention identifier.",
                style="form",
                explode=True,
            ),
            OpenApiParameter(
                name="page",
                type={"type": "integer", "minimum": 1},
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional positive ASCII decimal page number; defaults to 1.",
                default=1,
                style="form",
                explode=True,
            ),
            OpenApiParameter(
                name="page_size",
                type={"type": "integer", "minimum": 1, "maximum": 100},
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Optional positive ASCII decimal page size from 1 through 100; "
                    "defaults to 20."
                ),
                default=20,
                style="form",
                explode=True,
            ),
        ],
        responses=_CATCH_HISTORY_OPENAPI_RESPONSES,
        description=(
            "Returns only the authenticated player's Catch history ordered by "
            "-caught_at then -id. catch_count is the total number of matching Catch "
            "rows before pagination. Each supported query parameter may appear at "
            "most once; unknown query parameters are rejected."
        ),
    )
    def get(self, request: Request) -> Response:
        try:
            query = parse_catch_history_query(request)
        except CatchHistoryQueryError:
            return _domain_error(
                "invalid_query",
                "The catch-history query is invalid.",
                status.HTTP_400_BAD_REQUEST,
            )
        except Exception:  # noqa: BLE001 - parsing failures are sanitized.
            return _unexpected_history_error()

        if query.convention_id_is_out_of_range:
            return _domain_error(
                "convention_not_found",
                "The convention was not found.",
                status.HTTP_404_NOT_FOUND,
            )
        try:
            catches = (
                Catch.objects.filter(catcher_user=_user(request))
                .select_related("fursuit", "convention")
                .order_by("-caught_at", "-id")
            )
            if query.convention_id is not None:
                if not Convention.objects.filter(pk=query.convention_id).exists():
                    return _domain_error(
                        "convention_not_found",
                        "The convention was not found.",
                        status.HTTP_404_NOT_FOUND,
                    )
                catches = catches.filter(convention_id=query.convention_id)
        except Exception:  # noqa: BLE001 - database failures are sanitized.
            return _unexpected_history_error()

        if query.page_is_out_of_range:
            return _domain_error(
                "invalid_page",
                "The requested page does not exist.",
                status.HTTP_404_NOT_FOUND,
            )

        try:
            paginator = CatchHistoryPagination(
                page_number=query.page, page_size=query.page_size
            )
            page = paginator.paginate_queryset(catches, request, view=self)
            if page is None:
                return _unexpected_history_error()
        except NotFound:
            return _domain_error(
                "invalid_page",
                "The requested page does not exist.",
                status.HTTP_404_NOT_FOUND,
            )
        except Exception:  # noqa: BLE001 - pagination failures are sanitized.
            return _unexpected_history_error()

        try:
            data = [catch_history_entry_data(catch, request=request) for catch in page]
            response = paginator.get_paginated_response(data)
            if query.page == 2 and response.data["previous"] is not None:
                response.data["previous"] = replace_query_param(
                    response.data["previous"], paginator.page_query_param, 1
                )
            response["Cache-Control"] = "no-store"
            return response
        except Exception:  # noqa: BLE001 - projection failures are sanitized.
            return _unexpected_history_error()


_catch_history_get_kwargs = cast(
    dict[str, object],
    CatchHistoryView.get.kwargs,  # pyright: ignore[reportFunctionMemberAccess]
)
_CatchHistorySchema = cast(type[Any], _catch_history_get_kwargs["schema"])


class _CatchHistorySchemaWithExplicitOptionalParameters(_CatchHistorySchema):
    """Emit explicit optionality required by the frozen API contract."""

    def _process_override_parameters(
        self, direction: str = "request"
    ) -> dict[tuple[str, str], dict[str, object]]:
        parameters = cast(
            dict[tuple[str, str], dict[str, object]],
            super()._process_override_parameters(direction),  # pyright: ignore[reportUnknownMemberType]
        )
        for name in ("convention_id", "page", "page_size"):
            parameters[name, OpenApiParameter.QUERY]["required"] = False
        return parameters


_catch_history_get_kwargs["schema"] = _CatchHistorySchemaWithExplicitOptionalParameters


def _user(request: Request) -> User:
    return cast(User, request.user)


def _record_confirmation_rejected(reason: Reason) -> None:
    record_outcome(Signal.CATCH_CONFIRMATION, Outcome.REJECTED, reason)


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


def _unexpected_history_error() -> Response:
    _LOGGER.error("Unexpected catch history failure.")
    return _domain_error(
        "server_error",
        "An unexpected error occurred.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
