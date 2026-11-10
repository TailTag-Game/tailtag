"""Setup and secrecy assertions for reusable tag acceptance tests."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit, FursuitTag
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session

GENERIC_NOT_FOUND = {"detail": "Not found."}
TARGET_UNAVAILABLE = {
    "code": "catch_target_unavailable",
    "detail": "The catch target is unavailable.",
}


def tag_path(fursuit_id: int) -> str:
    return f"/api/fursuits/{fursuit_id}/tag/"


def replace_path(fursuit_id: int) -> str:
    return f"{tag_path(fursuit_id)}replace/"


PREVIEW_PATH = "/api/catches/preview/"


def create_player(label: str, *, enabled: bool = True) -> tuple[User, PlayerProfile]:
    user = create_test_user(clerk_user_id=f"tag_{label}")
    profile = PlayerProfile.objects.create(
        user=user,
        handle=f"tag_{user.pk}",
        display_name=f"Tag {label}",
        onboarding_completed_at=timezone.now(),
        is_enabled=enabled,
    )
    return user, profile


def create_convention(
    label: str,
    *,
    window_open: bool | None = True,
    status: str = ConventionStatus.ACTIVE,
) -> Convention:
    """Create a convention. ``window_open=None`` leaves the time zone unknown."""
    now = timezone.now()
    deadline: datetime.datetime | None
    if window_open is None:
        deadline = None
    else:
        deadline = now + datetime.timedelta(days=2 if window_open else -1)
    return Convention.objects.create(
        name=f"Tag Convention {label}",
        status=status,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
        time_zone=None if deadline is None else "America/New_York",
        review_deadline_at=deadline,
    )


def create_suit(owner: User, *, enabled: bool = True) -> Fursuit:
    return Fursuit.objects.create(
        owner=owner,
        name=f"Tag Suit {owner.pk}",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
        is_enabled=enabled,
    )


@dataclass(frozen=True)
class PreviewScenario:
    owner: User
    owner_profile: PlayerProfile
    owner_enrollment: ConventionEnrollment
    catcher: User
    catcher_profile: PlayerProfile
    catcher_enrollment: ConventionEnrollment
    convention: Convention
    fursuit: Fursuit
    activation: FursuitActivation
    session: Any
    payload: str

    def catcher_client(self) -> Client:
        return force_authenticated_client(user=User.objects.get(pk=self.catcher.pk))


def owner_client(user: User) -> Client:
    return force_authenticated_client(user=User.objects.get(pk=user.pk))


def read_payload(user: User, fursuit: Fursuit) -> str:
    """Read the owner tag through the public API and return its payload."""
    response = owner_client(user).get(tag_path(fursuit.pk))
    assert response.status_code == 200, response.content
    payload = response.json()["payload"]
    assert isinstance(payload, str)
    return payload


def create_preview_scenario(label: str = "preview") -> PreviewScenario:
    """Create one currently catchable suit and a catcher at the same convention."""
    owner, owner_profile = create_player(f"{label}_owner")
    convention = create_convention(label)
    owner_enrollment = ConventionEnrollment.objects.create(
        user=owner, convention=convention, is_active=False
    )
    fursuit = create_suit(owner)
    activation = create_activation_row(
        fursuit=fursuit, convention=convention, active=True
    )
    session = create_catch_session(activation=activation)
    catcher, catcher_profile = create_player(f"{label}_catcher")
    catcher_enrollment = ConventionEnrollment.objects.create(
        user=catcher, convention=convention, is_active=True
    )
    return PreviewScenario(
        owner=owner,
        owner_profile=owner_profile,
        owner_enrollment=owner_enrollment,
        catcher=catcher,
        catcher_profile=catcher_profile,
        catcher_enrollment=catcher_enrollment,
        convention=convention,
        fursuit=fursuit,
        activation=activation,
        session=session,
        payload=read_payload(owner, fursuit),
    )


def tokens_in_database() -> list[str]:
    return list(FursuitTag.objects.values_list("token", flat=True))


def assert_no_token_leak(text: str) -> None:
    """Fail if any stored token appears in *text*."""
    tokens = tokens_in_database()
    assert tokens, "secrecy check needs at least one stored token"
    for token in tokens:
        assert token not in text


def assert_logs_hold_no_token(caplog: pytest.LogCaptureFixture) -> None:
    assert_no_token_leak(
        "\n".join(
            f"{record.getMessage()} {record.__dict__}" for record in caplog.records
        )
    )
