"""Shared black-box fixtures for the V0 fursuit acceptance contract."""

from __future__ import annotations

from typing import Protocol

from django.http import JsonResponse
from django.utils import timezone

from accounts.models import User
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user


class _JsonResponse(Protocol):
    def json(self) -> dict[str, object]: ...


def assert_fursuit_response(
    response: JsonResponse | _JsonResponse,
) -> dict[str, object]:
    data = response.json()
    assert set(data) == {"id", "name", "photo_url", "is_enabled"}
    assert isinstance(data["id"], int)
    assert isinstance(data["name"], str)
    assert isinstance(data["photo_url"], str)
    assert data["photo_url"]
    assert isinstance(data["is_enabled"], bool)
    return data


def create_eligible_user(*, clerk_user_id: str | None = None) -> User:
    user = create_test_user(clerk_user_id=clerk_user_id)
    PlayerProfile.objects.create(
        user=user,
        handle="eligible_1",
        display_name="Eligible Player",
        onboarding_completed_at=timezone.now(),
        is_enabled=True,
    )
    return user


def create_fursuit_record(
    *,
    owner: User,
    name: str = "Example Character",
    photo_key: str = "images/0123456789abcdef0123456789abcdef.png",
) -> object:
    from fursuits.models import Fursuit

    return Fursuit.objects.create(owner=owner, name=name, photo_key=photo_key)
