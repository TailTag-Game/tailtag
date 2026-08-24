"""HTTP serialization for the player text-profile surface."""

from __future__ import annotations

from typing import TypedDict

from rest_framework import serializers

from media import service as media_service
from profiles.models import PlayerProfile


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
