"""Reusable, test-only support for TailTag authentication scenarios."""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest
from pytest import MonkeyPatch
from rest_framework.test import APIClient

from accounts.models import User
from authentication.clerk import (
    ClerkSessionVerifier,
    ClerkVerificationConfiguration,
    VerifiedClerkIdentity,
)

TEST_CLERK_CONFIGURATION = ClerkVerificationConfiguration(
    jwt_key="test-only-not-used-by-patched-verifier",
    authorized_parties=("http://testserver",),
)


def create_test_user(*, clerk_user_id: str | None = None) -> User:
    """Persist a TailTag user with an opaque Clerk identity for a test."""
    subject = clerk_user_id or f"user_test_{uuid4().hex}"
    return User.objects.create_user(clerk_user_id=subject)


def force_authenticated_client(*, user: User) -> APIClient:
    """Return a DRF client authenticated as a real TailTag user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def fake_clerk_session_verification(
    monkeypatch: MonkeyPatch,
    *,
    subject: str,
) -> list[HttpRequest]:
    """Fake only Clerk verification while retaining the real auth composition."""
    requests: list[HttpRequest] = []
    monkeypatch.setattr(
        settings,
        "CLERK_AUTHENTICATION",
        TEST_CLERK_CONFIGURATION,
    )

    def verify(
        _verifier: ClerkSessionVerifier,
        request: HttpRequest,
    ) -> VerifiedClerkIdentity:
        requests.append(request)
        return VerifiedClerkIdentity(subject=subject)

    monkeypatch.setattr(ClerkSessionVerifier, "verify", verify)
    return requests
