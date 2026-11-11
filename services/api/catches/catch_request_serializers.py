"""Closed response shapes for catch requests (#505, #506).

The shapes follow the reusable TailTag contract, section "Shared objects".
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import TypedDict, cast

from rest_framework.request import Request

from catches.catch_requests import SubmissionResult
from catches.models import Catch, CatchRequest, CatchRequestState
from catches.request_actions import UNDO_WINDOW, is_approval_paused, public_state
from config.openapi_components import component_ref
from fursuits.models import Fursuit
from media import service as media_service
from profiles.models import PlayerProfile

# The operations reference named components, so the generated client has one
# class per shape. The shapes live in config.openapi_components.
SUBMISSION_REQUEST_SCHEMA = component_ref("CatchRequestPayload")
SUBMISSION_RESPONSE_SCHEMA = component_ref("CatchRequestSubmission")
PLAYER_REQUEST_LIST_SCHEMA = component_ref("PlayerRequestList")
CATCH_REQUEST_ERROR_SCHEMA = component_ref("CatchRequestError")
CATCH_REQUEST_NOT_FOUND_SCHEMA = component_ref("CatchRequestNotFound")
DETAIL_ERROR_SCHEMA = component_ref("DetailError")
REFUSAL_SCHEMA = component_ref("CatchRequestRefusal")
ACTION_ERROR_SCHEMA = component_ref("CatchRequestActionError")
OWNER_REQUEST_SCHEMA = component_ref("OwnerRequest")
OWNER_REQUEST_LIST_SCHEMA = component_ref("OwnerRequestList")
OWNER_REQUEST_SUMMARY_SCHEMA = component_ref("OwnerRequestSummary")
OWNER_APPROVAL_SCHEMA = component_ref("OwnerApproval")
DECLINE_REQUEST_SCHEMA = component_ref("CatchRequestDecline")
PLAYER_REQUEST_SCHEMA = component_ref("PlayerRequest")


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


class OwnerRequestPlayerData(TypedDict):
    display_name: str
    handle: str


class OwnerRequestData(TypedDict):
    id: int
    fursuit: FursuitSummaryData
    convention_id: int
    player: OwnerRequestPlayerData
    state: str
    requested_at: str
    undo_available_until: str | None
    prior_decline_count: int
    player_blocked: bool
    approval_paused: bool
    review_deadline_at: str


class OwnerApprovalData(TypedDict):
    request: OwnerRequestData
    catch: RequestCatchData


def player_request_data(
    request_row: CatchRequest, *, request: Request
) -> PlayerRequestData:
    """Project one request for its player. Players never see ``invalidated``."""
    deadline = request_row.convention.review_deadline_at
    if deadline is None:  # pragma: no cover - rows exist only for zoned conventions.
        message = "A catch request convention has no review deadline."
        raise ValueError(message)
    return {
        "id": request_row.pk,
        "fursuit": _fursuit_summary(request_row.fursuit, request=request),
        "convention_id": request_row.convention_id,
        "state": public_state(request_row.state),
        "requested_at": _utc(request_row.requested_at),
        "review_deadline_at": _utc(deadline),
    }


def owner_request_data(
    row: CatchRequest,
    *,
    request: Request,
    now: datetime.datetime,
    owner_profile: PlayerProfile | None,
) -> OwnerRequestData:
    """Project one annotated row from ``owner_request_rows`` for its owner."""
    deadline = row.convention.review_deadline_at
    if deadline is None:  # pragma: no cover - rows exist only for zoned conventions.
        message = "A catch request convention has no review deadline."
        raise ValueError(message)
    # A missing reverse one-to-one raises an AttributeError subclass.
    player_profile = cast(
        "PlayerProfile | None", getattr(row.player, "player_profile", None)
    )
    return {
        "id": row.pk,
        "fursuit": _fursuit_summary(row.fursuit, request=request),
        "convention_id": row.convention_id,
        "player": {
            "display_name": ""
            if player_profile is None
            else str(player_profile.display_name or ""),
            "handle": ""
            if player_profile is None
            else str(player_profile.handle or ""),
        },
        "state": public_state(row.state),
        "requested_at": _utc(row.requested_at),
        "undo_available_until": _undo_available_until(row, now),
        "prior_decline_count": int(getattr(row, "prior_decline_count", 0)),
        "player_blocked": bool(getattr(row, "player_blocked", False)),
        "approval_paused": is_approval_paused(
            player_profile=player_profile,
            owner_profile=owner_profile,
            fursuit=row.fursuit,
            convention=row.convention,
        ),
        "review_deadline_at": _utc(deadline),
    }


def owner_approval_data(
    row: CatchRequest,
    catch: Catch,
    *,
    request: Request,
    now: datetime.datetime,
    owner_profile: PlayerProfile | None,
) -> OwnerApprovalData:
    return {
        "request": owner_request_data(
            row, request=request, now=now, owner_profile=owner_profile
        ),
        "catch": _request_catch_data(catch, request=request),
    }


def _undo_available_until(row: CatchRequest, now: datetime.datetime) -> str | None:
    """Only an ordinary decline whose undo window is still open (#506 G11b)."""
    if (
        row.state != CatchRequestState.DECLINED.value
        or row.decline_blocked
        or row.declined_at is None
    ):
        return None
    until = row.declined_at + UNDO_WINDOW
    return _utc(until) if now < until else None


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
