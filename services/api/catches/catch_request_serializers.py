"""Closed response shapes for catch request submission and the player list (#505).

The shapes follow the reusable TailTag contract, section "Shared objects".
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import TypedDict

from rest_framework.request import Request

from catches.catch_requests import SubmissionResult
from catches.models import Catch, CatchRequest, CatchRequestState
from config.openapi_components import component_ref
from fursuits.models import Fursuit
from media import service as media_service

# The operations reference named components, so the generated client has one
# class per shape. The shapes live in config.openapi_components.
SUBMISSION_REQUEST_SCHEMA = component_ref("CatchRequestPayload")
SUBMISSION_RESPONSE_SCHEMA = component_ref("CatchRequestSubmission")
PLAYER_REQUEST_LIST_SCHEMA = component_ref("PlayerRequestList")
CATCH_REQUEST_ERROR_SCHEMA = component_ref("CatchRequestError")
CATCH_REQUEST_NOT_FOUND_SCHEMA = component_ref("CatchRequestNotFound")
DETAIL_ERROR_SCHEMA = component_ref("DetailError")


class FursuitSummaryData(TypedDict):
    id: int
    tailtag_id: str
    name: str
    photo_url: str


class PlayerRequestData(TypedDict):
    id: int
    fursuit: FursuitSummaryData
    convention_id: int
    state: str
    requested_at: str
    review_deadline_at: str


class RequestCatchFursuitData(TypedDict):
    tailtag_id: str
    name: str
    photo_url: str


class RequestCatchData(TypedDict):
    id: int
    caught_at: str
    approved_at: str
    convention_id: int
    fursuit: RequestCatchFursuitData


class SubmissionResponseData(TypedDict):
    outcome: str
    request: PlayerRequestData | None
    catch: RequestCatchData | None


def player_request_data(
    request_row: CatchRequest, *, request: Request
) -> PlayerRequestData:
    """Project one request for its player. Players never see ``invalidated``."""
    deadline = request_row.convention.review_deadline_at
    if deadline is None:  # pragma: no cover - rows exist only for zoned conventions.
        message = "A catch request convention has no review deadline."
        raise ValueError(message)
    state = request_row.state
    if state == CatchRequestState.INVALIDATED.value:
        state = "unavailable"
    return {
        "id": request_row.pk,
        "fursuit": _fursuit_summary(request_row.fursuit, request=request),
        "convention_id": request_row.convention_id,
        "state": str(state),
        "requested_at": _utc(request_row.requested_at),
        "review_deadline_at": _utc(deadline),
    }


def submission_response_data(
    result: SubmissionResult, *, request: Request
) -> SubmissionResponseData:
    return {
        "outcome": result.outcome.value,
        "request": None
        if result.request is None
        else player_request_data(result.request, request=request),
        "catch": None
        if result.catch is None
        else _request_catch_data(result.catch, request=request),
    }


def _request_catch_data(catch: Catch, *, request: Request) -> RequestCatchData:
    return {
        "id": catch.pk,
        "caught_at": _utc(catch.caught_at),
        "approved_at": _utc(catch.approved_at),
        "convention_id": catch.convention_id,
        "fursuit": {
            "tailtag_id": str(catch.fursuit.tailtag_id),
            "name": catch.fursuit.name,
            "photo_url": _photo_url(catch.fursuit, request=request),
        },
    }


def _fursuit_summary(fursuit: Fursuit, *, request: Request) -> FursuitSummaryData:
    return {
        "id": fursuit.pk,
        "tailtag_id": str(fursuit.tailtag_id),
        "name": fursuit.name,
        "photo_url": _photo_url(fursuit, request=request),
    }


def _photo_url(fursuit: Fursuit, *, request: Request) -> str:
    return request.build_absolute_uri(media_service.read_image_url(fursuit.photo_key))


def _utc(value: datetime.datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
