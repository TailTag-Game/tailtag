"""HTTP boundaries for owner review, player withdrawal, and unblock (#506).

The reusable TailTag contract is the source of truth: section "Operations".
The catch request gate hides every operation while it is off.
"""

from __future__ import annotations

import datetime
import logging
from typing import cast

from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ParseError,
    PermissionDenied,
    UnsupportedMediaType,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from config.catch_requests_gate import catch_requests_enabled
from conventions.review_deadline import database_now
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile

from . import request_actions
from .catch_request_serializers import (
    ACTION_ERROR_SCHEMA,
    ACTION_NOT_FOUND_SCHEMA,
    CATCH_REQUEST_ERROR_SCHEMA,
    DECLINE_REQUEST_SCHEMA,
    DETAIL_ERROR_SCHEMA,
    OWNER_APPROVAL_SCHEMA,
    OWNER_REQUEST_LIST_SCHEMA,
    OWNER_REQUEST_SCHEMA,
    OWNER_REQUEST_SUMMARY_SCHEMA,
    PLAYER_REQUEST_SCHEMA,
    owner_approval_data,
    owner_request_data,
    player_request_data,
)
from .models import CatchRequest
from .owner_requests import (
    open_owner_request_rows,
    owner_request_rows,
    pending_summary,
)

_LOGGER = logging.getLogger(__name__)
_NO_STORE = "no-store"
_ERROR_DETAILS = {
    "request_not_found": "The catch request was not found.",
    "request_state_changed": "The catch request changed before this action.",
    "review_window_closed": "The review window for this convention is closed.",
    "approval_paused": "Approval is paused for this catch request.",
    "request_superseded": "A newer request or a catch replaced this request.",
    "undo_expired": "The decline can no longer be undone.",
}

_401 = OpenApiResponse(
    response=DETAIL_ERROR_SCHEMA,
    description="Authentication credentials were not provided.",
)
_403_OWNER = OpenApiResponse(
    response=DETAIL_ERROR_SCHEMA,
    description="The caller has no enabled, completed profile.",
)
_404 = OpenApiResponse(
    response=ACTION_NOT_FOUND_SCHEMA,
    description=(
        "request_not_found. While the catch request gate is off, every call "
        "returns the generic not-found shape."
    ),
)
_500 = OpenApiResponse(response=CATCH_REQUEST_ERROR_SCHEMA, description="server_error")


def _conflicts(extra: str = "") -> OpenApiResponse:
    codes = "request_state_changed, review_window_closed" + extra
    return OpenApiResponse(response=ACTION_ERROR_SCHEMA, description=codes)


class _RequestReviewView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        if not catch_requests_enabled():
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = _NO_STORE
        return response

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (RecursionError, ParseError, UnsupportedMediaType)):
            return _error(
                "invalid_request",
                "The request body is invalid.",
                status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(exc, request_actions.RequestActionError):
            return _action_error(exc)
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        _LOGGER.error("Unexpected catch request review failure.")
        return _error(
            "server_error",
            "An unexpected error occurred.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class _OwnerView(_RequestReviewView):
    def owner(self, request: Request) -> User:
        user = cast(User, request.user)
        if not is_participation_eligible(user):
            raise PermissionDenied
        return user


def _id_parameter(name: str, description: str) -> OpenApiParameter:
    return OpenApiParameter(
        name=name,
        type=int,
        location=OpenApiParameter.QUERY,
        required=False,
        description=description,
    )


_INVALID_QUERY = OpenApiResponse(
    response=CATCH_REQUEST_ERROR_SCHEMA,
    description="invalid_query: a filter is not a positive integer.",
)


class OwnerRequestListView(_OwnerView):
    """List requests on the caller's suits in open review windows."""

    @extend_schema(
        operation_id="catch_incoming_requests_list",
        tags=["catches"],
        description=(
            "List requests on the caller's suits, newest first, for conventions "
            "whose review window is open."
        ),
        parameters=[
            _id_parameter("convention_id", "Limit the list to one convention."),
            _id_parameter("fursuit_id", "Limit the list to one suit."),
        ],
        responses={
            200: OpenApiResponse(response=OWNER_REQUEST_LIST_SCHEMA),
            400: _INVALID_QUERY,
            401: _401,
            403: _403_OWNER,
            404: OpenApiResponse(
                response=DETAIL_ERROR_SCHEMA,
                description="The catch request gate is off.",
            ),
            500: _500,
        },
    )
    def get(self, request: Request) -> Response:
        owner = self.owner(request)
        filters = _id_filters(request, ("convention_id", "fursuit_id"))
        if filters is None:
            return _invalid_query()
        now = database_now()
        rows = open_owner_request_rows(owner, now=now, **filters)
        owner_profile = _profile(owner)
        return Response(
            {
                "results": [
                    owner_request_data(
                        row, request=request, now=now, owner_profile=owner_profile
                    )
                    for row in rows
                ]
            }
        )


class OwnerRequestSummaryView(_OwnerView):
    """Count pending requests per suit in open review windows."""

    @extend_schema(
        operation_id="catch_incoming_requests_summary",
        tags=["catches"],
        description="Count pending requests on the caller's suits in open windows.",
        parameters=[
            _id_parameter("convention_id", "Limit the counts to one convention.")
        ],
        responses={
            200: OpenApiResponse(response=OWNER_REQUEST_SUMMARY_SCHEMA),
            400: _INVALID_QUERY,
            401: _401,
            403: _403_OWNER,
            404: OpenApiResponse(
                response=DETAIL_ERROR_SCHEMA,
                description="The catch request gate is off.",
            ),
            500: _500,
        },
    )
    def get(self, request: Request) -> Response:
        owner = self.owner(request)
        filters = _id_filters(request, ("convention_id",))
        if filters is None:
            return _invalid_query()
        return Response(pending_summary(owner, now=database_now(), **filters))


class OwnerRequestApproveView(_OwnerView):
    @extend_schema(
        operation_id="catch_incoming_requests_approve",
        tags=["catches"],
        description=(
            "Approve a pending request. The catch time is the request time. A "
            "repeat returns the same catch."
        ),
        request=None,
        responses={
            200: OpenApiResponse(response=OWNER_APPROVAL_SCHEMA),
            401: _401,
            403: _403_OWNER,
            404: _404,
            409: _conflicts(", approval_paused, request_superseded"),
            500: _500,
        },
    )
    def post(self, request: Request, id: int) -> Response:
        owner = self.owner(request)
        result = request_actions.approve(owner, id)
        if result.catch is None:  # pragma: no cover - approve always has a catch.
            raise request_actions.RequestStateChangedError("approved")
        return Response(
            owner_approval_data(
                _owner_row(owner, id),
                result.catch,
                request=request,
                now=result.now,
                owner_profile=_profile(owner),
            )
        )


class OwnerRequestDeclineView(_OwnerView):
    @extend_schema(
        operation_id="catch_incoming_requests_decline",
        tags=["catches"],
        description=(
            "Decline a pending request. No reason is needed. With block true, the "
            "player is also blocked for this suit at this convention."
        ),
        request={"application/json": DECLINE_REQUEST_SCHEMA},
        responses={
            200: OpenApiResponse(response=OWNER_REQUEST_SCHEMA),
            400: OpenApiResponse(
                response=CATCH_REQUEST_ERROR_SCHEMA,
                description="invalid_request: the body needs one boolean block.",
            ),
            401: _401,
            403: _403_OWNER,
            404: _404,
            409: _conflicts(),
            500: _500,
        },
    )
    def post(self, request: Request, id: int) -> Response:
        owner = self.owner(request)
        data = request.data
        if (
            not isinstance(data, dict)
            or set(cast(dict[str, object], data)) != {"block"}
            or not isinstance(cast(dict[str, object], data)["block"], bool)
        ):
            return _error(
                "invalid_request",
                "Provide block as true or false.",
                status.HTTP_400_BAD_REQUEST,
            )
        block = cast(bool, cast(dict[str, object], data)["block"])
        result = request_actions.decline(owner, id, block=block)
        return _owner_response(owner, id, request=request, now=result.now)


class OwnerRequestUndoDeclineView(_OwnerView):
    @extend_schema(
        operation_id="catch_incoming_requests_undo_decline",
        tags=["catches"],
        description=(
            "Undo an ordinary decline within 10 seconds. The request returns to "
            "pending, and the decline no longer counts."
        ),
        request=None,
        responses={
            200: OpenApiResponse(response=OWNER_REQUEST_SCHEMA),
            401: _401,
            403: _403_OWNER,
            404: _404,
            409: _conflicts(", undo_expired, request_superseded"),
            500: _500,
        },
    )
    def post(self, request: Request, id: int) -> Response:
        owner = self.owner(request)
        result = request_actions.undo_decline(owner, id)
        return _owner_response(owner, id, request=request, now=result.now)


class OwnerRequestRestoreView(_OwnerView):
    @extend_schema(
        operation_id="catch_incoming_requests_restore",
        tags=["catches"],
        description=(
            "Restore a declined request to pending before the review deadline. An "
            "active block stays."
        ),
        request=None,
        responses={
            200: OpenApiResponse(response=OWNER_REQUEST_SCHEMA),
            401: _401,
            403: _403_OWNER,
            404: _404,
            409: _conflicts(", request_superseded"),
            500: _500,
        },
    )
    def post(self, request: Request, id: int) -> Response:
        owner = self.owner(request)
        result = request_actions.restore(owner, id)
        return _owner_response(owner, id, request=request, now=result.now)


class OwnerRequestBlockView(_OwnerView):
    @extend_schema(
        operation_id="catch_incoming_requests_unblock",
        tags=["catches"],
        description=(
            "Remove the block for this request's player, suit, and convention. "
            "The cooldown stays. No block in place also returns 204."
        ),
        request=None,
        responses={
            204: OpenApiResponse(description="The block is gone."),
            401: _401,
            403: _403_OWNER,
            404: _404,
            409: OpenApiResponse(
                response=ACTION_ERROR_SCHEMA, description="review_window_closed"
            ),
            500: _500,
        },
    )
    def delete(self, request: Request, id: int) -> Response:
        request_actions.unblock(self.owner(request), id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlayerRequestWithdrawView(_RequestReviewView):
    @extend_schema(
        operation_id="catch_requests_withdraw",
        tags=["catches"],
        description=(
            "Withdraw the caller's pending request. A withdrawal does not count as "
            "a decline and does not reset a cooldown."
        ),
        request=None,
        responses={
            200: OpenApiResponse(response=PLAYER_REQUEST_SCHEMA),
            401: _401,
            403: OpenApiResponse(
                response=CATCH_REQUEST_ERROR_SCHEMA, description="catcher_ineligible"
            ),
            404: _404,
            409: _conflicts(),
            500: _500,
        },
    )
    def post(self, request: Request, id: int) -> Response:
        user = cast(User, request.user)
        if not is_participation_eligible(user):
            return _error(
                "catcher_ineligible",
                "You are not eligible to catch this target.",
                status.HTTP_403_FORBIDDEN,
            )
        result = request_actions.withdraw(user, id)
        return Response(player_request_data(result.request, request=request))


def _owner_row(owner: User, request_id: int) -> CatchRequest:
    row = owner_request_rows(owner).filter(pk=request_id).first()
    if row is None:  # pragma: no cover - the action just locked this row.
        raise request_actions.RequestNotFoundError
    return row


def _owner_response(
    owner: User, request_id: int, *, request: Request, now: datetime.datetime
) -> Response:
    return Response(
        owner_request_data(
            _owner_row(owner, request_id),
            request=request,
            now=now,
            owner_profile=_profile(owner),
        )
    )


def _profile(user: User) -> PlayerProfile | None:
    return PlayerProfile.objects.filter(user=user).first()


def _id_filters(request: Request, names: tuple[str, ...]) -> dict[str, int] | None:
    """Parse optional positive integer filters. ``None`` means one is invalid."""
    filters: dict[str, int] = {}
    for name in names:
        raw = request.query_params.get(name)
        if raw is None:
            continue
        # isascii() rejects digits such as "²" that int() cannot parse.
        if not (raw.isascii() and raw.isdigit()) or int(raw) < 1:
            return None
        filters[name] = int(raw)
    return filters


def _invalid_query() -> Response:
    return _error("invalid_query", "A filter is invalid.", status.HTTP_400_BAD_REQUEST)


def _action_error(error: request_actions.RequestActionError) -> Response:
    body: dict[str, object] = {"code": error.code, "detail": _ERROR_DETAILS[error.code]}
    if isinstance(error, request_actions.RequestStateChangedError):
        body["state"] = error.state
    return Response(body, status=error.status)


def _error(code: str, detail: str, response_status: int) -> Response:
    return Response({"code": code, "detail": detail}, status=response_status)
