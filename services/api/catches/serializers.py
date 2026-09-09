"""Closed request and response serialization for catch confirmation."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC
from typing import TypedDict

from drf_spectacular.extensions import OpenApiSerializerExtension
from rest_framework import serializers
from rest_framework.request import Request

from conventions.serializers import (
    FURSUIT_CATCH_CREDENTIAL_RESOLUTION_REQUEST_SCHEMA,
    FURSUIT_CATCH_CREDENTIAL_RESOLUTION_VALIDATION_ERROR_SCHEMA,
    FursuitCatchCredentialResolutionRequestSerializer,  # noqa: F401  # pyright: ignore[reportUnusedImport] - re-exported request contract.
)
from media import service as media_service

from .services import CatchConfirmationResult

CATCH_CONFIRMATION_REQUEST_SCHEMA = FURSUIT_CATCH_CREDENTIAL_RESOLUTION_REQUEST_SCHEMA
CATCH_CONFIRMATION_VALIDATION_ERROR_SCHEMA = (
    FURSUIT_CATCH_CREDENTIAL_RESOLUTION_VALIDATION_ERROR_SCHEMA
)

AUTHENTICATION_ERROR_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"detail": {"type": "string"}},
    "required": ["detail"],
}

CATCH_CONFIRMATION_DOMAIN_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "code": {"type": "string"},
        "detail": {"type": "string"},
    },
    "required": ["code", "detail"],
}

CATCH_CONFIRMATION_FORBIDDEN_ERROR_SCHEMA: dict[str, object] = {
    **CATCH_CONFIRMATION_DOMAIN_ERROR_SCHEMA,
    "properties": {
        "code": {"type": "string", "enum": ["catcher_ineligible"]},
        "detail": {"type": "string"},
    },
}
CATCH_CONFIRMATION_NOT_FOUND_ERROR_SCHEMA: dict[str, object] = {
    **CATCH_CONFIRMATION_DOMAIN_ERROR_SCHEMA,
    "properties": {
        "code": {"type": "string", "enum": ["catch_target_unavailable"]},
        "detail": {"type": "string"},
    },
}
CATCH_CONFIRMATION_CONFLICT_ERROR_SCHEMA: dict[str, object] = {
    **CATCH_CONFIRMATION_DOMAIN_ERROR_SCHEMA,
    "properties": {
        "code": {
            "type": "string",
            "enum": ["active_convention_mismatch", "self_catch_not_allowed"],
        },
        "detail": {"type": "string"},
    },
}
CATCH_CONFIRMATION_SERVER_ERROR_SCHEMA: dict[str, object] = {
    **CATCH_CONFIRMATION_DOMAIN_ERROR_SCHEMA,
    "properties": {
        "code": {"type": "string", "enum": ["server_error"]},
        "detail": {"type": "string"},
    },
}

CATCH_CONFIRMATION_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["created", "already_caught"],
            "readOnly": True,
        },
        "catch": {
            "type": "object",
            "additionalProperties": False,
            "readOnly": True,
            "properties": {
                "id": {"type": "integer", "readOnly": True},
                "caught_at": {
                    "type": "string",
                    "format": "date-time",
                    "readOnly": True,
                },
                "convention_id": {"type": "integer", "readOnly": True},
                "fursuit": {
                    "type": "object",
                    "additionalProperties": False,
                    "readOnly": True,
                    "properties": {
                        "tailtag_id": {
                            "type": "string",
                            "format": "uuid",
                            "readOnly": True,
                        },
                        "name": {"type": "string", "readOnly": True},
                        "photo_url": {
                            "type": "string",
                            "format": "uri",
                            "readOnly": True,
                        },
                    },
                    "required": ["tailtag_id", "name", "photo_url"],
                },
            },
            "required": ["id", "caught_at", "convention_id", "fursuit"],
        },
    },
    "required": ["outcome", "catch"],
}


class CatchConfirmationFursuitResponseData(TypedDict):
    tailtag_id: str
    name: str
    photo_url: str


class CatchConfirmationCatchResponseData(TypedDict):
    id: int
    caught_at: str
    convention_id: int
    fursuit: CatchConfirmationFursuitResponseData


class CatchConfirmationResponseData(TypedDict):
    outcome: str
    catch: CatchConfirmationCatchResponseData


class CatchConfirmationRequestSchemaSerializer(serializers.Serializer[dict[str, str]]):
    """OpenAPI carrier for the reused request contract."""


class CatchConfirmationResponseSchemaSerializer(
    serializers.Serializer[dict[str, object]]
):
    """OpenAPI carrier for the closed success projection."""


class _CatchConfirmationRequestSchemaExtension(  # pyright: ignore[reportUnusedClass] - auto-discovered by drf-spectacular.
    OpenApiSerializerExtension
):
    target_class = "catches.serializers.CatchConfirmationRequestSchemaSerializer"

    def map_serializer(self, auto_schema: object, direction: str) -> dict[str, object]:
        del auto_schema, direction
        return deepcopy(CATCH_CONFIRMATION_REQUEST_SCHEMA)


class _CatchConfirmationResponseSchemaExtension(  # pyright: ignore[reportUnusedClass] - auto-discovered by drf-spectacular.
    OpenApiSerializerExtension
):
    target_class = "catches.serializers.CatchConfirmationResponseSchemaSerializer"

    def map_serializer(self, auto_schema: object, direction: str) -> dict[str, object]:
        del auto_schema, direction
        return deepcopy(CATCH_CONFIRMATION_RESPONSE_SCHEMA)


def catch_confirmation_response_data(
    result: CatchConfirmationResult, *, request: Request
) -> CatchConfirmationResponseData:
    """Project only the canonical, player-safe catch confirmation data."""
    catch = result.catch
    return {
        "outcome": result.status.value,
        "catch": {
            "id": catch.pk,
            "caught_at": catch.caught_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "convention_id": catch.convention_id,
            "fursuit": {
                "tailtag_id": str(catch.fursuit.tailtag_id),
                "name": catch.fursuit.name,
                "photo_url": request.build_absolute_uri(
                    media_service.read_image_url(catch.fursuit.photo_key)
                ),
            },
        },
    }
