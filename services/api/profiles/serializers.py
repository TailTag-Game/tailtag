"""HTTP serialization for the player text-profile surface."""

from __future__ import annotations

from typing import TypedDict

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    extend_schema_field,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import serializers

from media import service as media_service
from media.images import ImageRejectionCode
from profiles.models import PlayerProfile

MEDIA_ERROR_MESSAGES = {
    ImageRejectionCode.FILE_TOO_LARGE: "The avatar file is too large.",
    ImageRejectionCode.INVALID_IMAGE: "Upload a valid image.",
    ImageRejectionCode.UNSUPPORTED_FORMAT: "Upload a JPEG, PNG, or static WebP image.",
    ImageRejectionCode.ANIMATED_IMAGE: "Animated avatars are not supported.",
    ImageRejectionCode.TOO_MANY_PIXELS: "The avatar dimensions are too large.",
}

PROFILE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "handle": {"type": "string", "nullable": True, "readOnly": True},
        "display_name": {"type": "string", "nullable": True, "readOnly": True},
        "avatar_url": {
            "type": "string",
            "format": "uri",
            "nullable": True,
            "readOnly": True,
        },
        "onboarding_complete": {"type": "boolean", "readOnly": True},
        "is_enabled": {"type": "boolean", "readOnly": True},
    },
    "required": [
        "handle",
        "display_name",
        "avatar_url",
        "onboarding_complete",
        "is_enabled",
    ],
}


class ProfilePutSerializer(serializers.Serializer[dict[str, str]]):
    handle = serializers.CharField(allow_blank=False, allow_null=False)
    display_name = serializers.CharField(
        allow_blank=False, allow_null=False, trim_whitespace=False
    )


class ProfilePatchSerializer(serializers.Serializer[dict[str, str]]):
    handle = serializers.CharField(required=False, allow_blank=False, allow_null=False)
    display_name = serializers.CharField(
        required=False, allow_blank=False, allow_null=False, trim_whitespace=False
    )


@extend_schema_field(OpenApiTypes.BINARY)
class AvatarUploadField(serializers.FileField):
    """Runtime upload field with its multipart binary schema representation."""


class AvatarPutSerializer(serializers.Serializer[dict[str, object]]):
    avatar = AvatarUploadField(allow_empty_file=False)


class ProfileResponseData(TypedDict):
    handle: str | None
    display_name: str | None
    avatar_url: str | None
    onboarding_complete: bool
    is_enabled: bool


class ProfileResponseSerializer(serializers.Serializer[ProfileResponseData]):
    handle = serializers.CharField(allow_null=True, read_only=True)
    display_name = serializers.CharField(allow_null=True, read_only=True)
    avatar_url = serializers.URLField(allow_null=True, read_only=True)
    onboarding_complete = serializers.BooleanField(read_only=True)
    is_enabled = serializers.BooleanField(read_only=True)


def profile_response_data(profile: PlayerProfile) -> ProfileResponseData:
    """Project durable state to the exact player-visible representation."""
    avatar_url = (
        None
        if profile.avatar_key is None
        else media_service.read_image_url(profile.avatar_key)
    )
    return {
        "handle": profile.handle,
        "display_name": profile.display_name,
        "avatar_url": avatar_url,
        "onboarding_complete": profile.onboarding_complete,
        "is_enabled": profile.is_enabled,
    }
