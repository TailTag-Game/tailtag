"""Acceptance contract for reusable, offline TailTag authentication test support."""

from __future__ import annotations

import pytest
from django.http import HttpRequest
from django.test import Client
from pytest import MonkeyPatch

from accounts.models import User
from authentication.clerk import VerifiedClerkIdentity
from tests.authentication_support import (
    create_test_user,
    fake_clerk_session_verification,
    force_authenticated_client,
)


@pytest.mark.django_db
def test_user_factory_persists_unique_opaque_clerk_identities() -> None:
    """Defaults establish only a persisted application identity."""
    first = create_test_user()
    second = create_test_user()

    assert first.pk is not None
    assert second.pk is not None
    assert first.clerk_user_id.startswith("user_test_")
    assert second.clerk_user_id.startswith("user_test_")
    assert first.clerk_user_id != second.clerk_user_id
    assert User.objects.filter(pk__in=(first.pk, second.pk)).count() == 2
    assert not first.is_staff
    assert not second.is_staff


@pytest.mark.django_db
def test_user_factory_preserves_an_explicit_opaque_identity_override() -> None:
    subject = "user_test_deliberate_override"

    user = create_test_user(clerk_user_id=subject)

    assert user.pk is not None
    assert user.clerk_user_id == subject
    assert User.objects.get(pk=user.pk).clerk_user_id == subject


@pytest.mark.django_db
def test_endpoint_isolation_client_exposes_a_real_tailtag_user() -> None:
    """Endpoint tests must use the owned user, not provider identity objects."""
    user = create_test_user()

    response = force_authenticated_client(user=user).get("/api/me/")

    assert response.status_code == 200
    assert response.json() == {"id": user.pk}
    assert type(response.json()["id"]) is int


@pytest.mark.django_db
def test_composed_fake_retains_authenticator_and_resolver(
    monkeypatch: MonkeyPatch,
) -> None:
    """Only verification is faked; bearer parsing and user resolution remain real."""
    requests = fake_clerk_session_verification(
        monkeypatch,
        subject="user_test_composed_acceptance",
    )

    response = Client().get("/api/me/", HTTP_AUTHORIZATION="Bearer synthetic")
    user = User.objects.get(clerk_user_id="user_test_composed_acceptance")

    assert response.status_code == 200
    assert response.json() == {"id": user.pk}
    assert len(requests) == 1
    assert isinstance(requests[0], HttpRequest)
    assert requests[0].headers["Authorization"] == "Bearer synthetic"
    assert not isinstance(user, VerifiedClerkIdentity)
