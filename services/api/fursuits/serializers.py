"""Strict request and response serialization for fursuit APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict, cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    extend_schema_field,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from fursuits.models import Fursuit
from media import service as media_service
from media.images import ImageRejectionCode

MEDIA_ERROR_MESSAGES = {
    ImageRejectionCode.FILE_TOO_LARGE: "The photo file is too large.",
    ImageRejectionCode.INVALID_IMAGE: "Upload a valid image.",
    ImageRejectionCode.UNSUPPORTED_FORMAT: "Upload a JPEG, PNG, or static WebP image.",
    ImageRejectionCode.ANIMATED_IMAGE: "Animated photos are not supported.",
    ImageRejectionCode.TOO_MANY_PIXELS: "The photo dimensions are too large.",
}

FURSUIT_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "integer", "readOnly": True},
        "tailtag_id": {"type": "string", "format": "uuid", "readOnly": True},
        "name": {"type": "string"},
        "photo_url": {"type": "string", "format": "uri", "readOnly": True},
        "is_enabled": {"type": "boolean", "readOnly": True},
    },
    "required": ["id", "tailtag_id", "name", "photo_url", "is_enabled"],
}

FURSUIT_CREATE_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "photo": {"type": "string", "format": "binary"},
    },
    "required": ["name", "photo"],
}

FURSUIT_NAME_PATCH_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}

FURSUIT_PHOTO_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"photo": {"type": "string", "format": "binary"}},
    "required": ["photo"],
}


@extend_schema_field(OpenApiTypes.BINARY)
class PhotoUploadField(serializers.FileField):
    """Runtime upload field with its multipart binary schema representation."""


class FursuitCreateSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(
        allow_blank=False, allow_null=False, trim_whitespace=False
    )
    photo = PhotoUploadField(allow_empty_file=False)


class FursuitNamePatchSerializer(serializers.Serializer[dict[str, str]]):
    name = serializers.CharField(
        allow_blank=False, allow_null=False, trim_whitespace=False
    )

    def to_internal_value(self, data: Any) -> dict[str, str]:
        if not isinstance(data, Mapping) or set(cast(Mapping[str, object], data)) != {
            "name"
        }:
            raise serializers.ValidationError(
                {
                    "name": [
                        ErrorDetail("Provide exactly the name field.", code="invalid")
                    ]
                }
            )
        return cast(dict[str, str], super().to_internal_value(data))


class FursuitPhotoSerializer(serializers.Serializer[dict[str, object]]):
    photo = PhotoUploadField(allow_empty_file=False)


class FursuitResponseData(TypedDict):
    id: int
    tailtag_id: str
    name: str
    photo_url: str
    is_enabled: bool


def fursuit_response_data(fursuit: Fursuit) -> FursuitResponseData:
    """Project durable state to the exact player-visible representation."""
    return {
        "id": fursuit.pk,
        "tailtag_id": str(fursuit.tailtag_id),
        "name": fursuit.name,
        "photo_url": media_service.read_image_url(fursuit.photo_key),
        "is_enabled": fursuit.is_enabled,
    }


_ERROR_CODE_SCHEMA: dict[str, object] = {"type": "string"}

FURSUIT_TAG_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fursuit_id": {"type": "integer"},
        "state": {"type": "string", "enum": ["current", "revoked"]},
        "tag_version": {"type": "integer", "minimum": 0},
        "payload": {
            "type": "string",
            "nullable": True,
            "description": "The printed tag payload. Null when state is revoked.",
        },
    },
    "required": ["fursuit_id", "state", "tag_version", "payload"],
}

FURSUIT_TAG_REPLACE_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"expected_version": {"type": "integer", "minimum": 0}},
    "required": ["expected_version"],
}

FURSUIT_TAG_REPLACE_VALIDATION_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "expected_version": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["expected_version"],
}

FURSUIT_TAG_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"code": _ERROR_CODE_SCHEMA, "detail": {"type": "string"}},
    "required": ["code", "detail"],
}

FURSUIT_TAG_CONFLICT_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "code": {
            "type": "string",
            "enum": ["fursuit_disabled", "tag_version_conflict"],
        },
        "detail": {"type": "string"},
        "current": {
            "type": "object",
            "additionalProperties": False,
            "description": (
                "Present only for tag_version_conflict. It never carries a payload. "
                "State none means the suit never had a tag."
            ),
            "properties": {
                "fursuit_id": {"type": "integer"},
                "state": {"type": "string", "enum": ["current", "revoked", "none"]},
                "tag_version": {"type": "integer", "minimum": 0},
            },
            "required": ["fursuit_id", "state", "tag_version"],
        },
    },
    "required": ["code", "detail"],
}
