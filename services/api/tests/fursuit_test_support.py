"""Shared black-box fixtures for the V0 fursuit acceptance contract."""

from __future__ import annotations

from typing import Protocol, cast

from django.http import HttpResponse
from django.test import Client
from django.utils import timezone

from accounts.models import User
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user


class _JsonResponse(Protocol):
    def json(self) -> dict[str, object]: ...


class _BytesGenericClient(Protocol):
    def generic(
        self, method: str, path: str, data: bytes, content_type: str
    ) -> HttpResponse: ...


def assert_fursuit_data(data: dict[str, object]) -> dict[str, object]:
    assert set(data) == {"id", "name", "photo_url", "is_enabled"}
    assert isinstance(data["id"], int)
    assert isinstance(data["name"], str)
    assert isinstance(data["photo_url"], str)
    assert data["photo_url"]
    assert isinstance(data["is_enabled"], bool)
    return data


def assert_fursuit_response(response: _JsonResponse) -> dict[str, object]:
    return assert_fursuit_data(response.json())


def raw_client_request(
    client: Client, *, method: str, path: str, data: bytes, content_type: str
) -> HttpResponse:
    """Exercise Django's supported bytes path despite its narrower client stub."""
    return cast(_BytesGenericClient, client).generic(
        method, path, data=data, content_type=content_type
    )


def create_eligible_user(*, clerk_user_id: str | None = None) -> User:
    user = create_test_user(clerk_user_id=clerk_user_id)
    PlayerProfile.objects.create(
        user=user,
        handle=f"eligible_{user.pk}",
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
) -> Fursuit:
    return Fursuit.objects.create(owner=owner, name=name, photo_key=photo_key)
