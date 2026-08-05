"""Session-authenticated account API behavior."""

from __future__ import annotations

import json
from typing import Protocol, cast

import pytest
from django.test import Client
from rest_framework import serializers

from accounts.models import User
from accounts.serializers import SignupSerializer


class JsonResponse(Protocol):
    """The stable subset of Django test responses used by JSON API tests."""

    status_code: int

    def json(self) -> dict[str, object]:
        """Decode an object-shaped JSON response."""
        ...


def csrf_token(client: Client) -> str:
    """Bootstrap and return Django's CSRF token for an unsafe request."""
    response = client.get("/api/auth/csrf")

    assert response.status_code == 204
    return client.cookies["csrftoken"].value


def post_json(
    client: Client, path: str, data: dict[str, str], token: str | None = None
) -> JsonResponse:
    """Submit an optional-CSRF JSON request."""
    headers = {"X-CSRFToken": token} if token is not None else None
    return cast(
        JsonResponse,
        client.post(
            path,
            data=json.dumps(data),
            content_type="application/json",
            headers=headers,
        ),
    )


@pytest.fixture
def csrf_client() -> Client:
    """Return a client that enforces the same CSRF checks as a browser."""
    return Client(enforce_csrf_checks=True)


@pytest.mark.django_db
def test_signup_creates_a_hashed_user_and_authenticated_session(
    csrf_client: Client,
) -> None:
    """Signup returns only public fields and establishes a session."""
    token = csrf_token(csrf_client)

    response = post_json(
        csrf_client,
        "/api/auth/signup",
        {
            "email": "  Player@Example.Test ",
            "display_name": "Player",
            "password": "a secure password 123",
        },
        token,
    )

    assert response.status_code == 201
    assert response.json()["email"] == "player@example.test"
    assert set(response.json()) == {
        "id",
        "email",
        "display_name",
        "created_at",
        "updated_at",
    }
    user = User.objects.get(email="player@example.test")
    assert user.check_password("a secure password 123")
    assert "_auth_user_id" in csrf_client.session


@pytest.mark.django_db
def test_signup_rejects_a_duplicate_canonical_email(csrf_client: Client) -> None:
    """Canonical identity prevents case and whitespace variants from registering."""
    User.objects.create_user(
        email="player@example.test",
        password="a secure password 123",
        display_name="Player",
    )

    response = post_json(
        csrf_client,
        "/api/auth/signup",
        {
            "email": " Player@Example.Test ",
            "display_name": "Another Player",
            "password": "another secure password 123",
        },
        csrf_token(csrf_client),
    )

    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.django_db
def test_signup_translates_a_concurrent_duplicate_email_conflict() -> None:
    """A database uniqueness race remains a stable email validation error."""
    serializer = SignupSerializer(
        data={
            "email": "player@example.test",
            "display_name": "Player",
            "password": "a secure password 123",
        }
    )
    serializer.is_valid(raise_exception=True)

    User.objects.create_user(
        email="player@example.test",
        password="a secure password 123",
        display_name="Player",
    )

    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.save()

    assert "email" in exc_info.value.detail


@pytest.mark.django_db
def test_login_failure_does_not_identify_the_bad_credential(
    csrf_client: Client,
) -> None:
    """Login errors use one stable message for unknown users and wrong passwords."""
    User.objects.create_user(
        email="player@example.test",
        password="a secure password 123",
        display_name="Player",
    )

    unknown_response = post_json(
        csrf_client,
        "/api/auth/login",
        {"email": "unknown@example.test", "password": "a secure password 123"},
        csrf_token(csrf_client),
    )
    wrong_password_response = post_json(
        csrf_client,
        "/api/auth/login",
        {"email": "player@example.test", "password": "not the right password 123"},
        csrf_token(csrf_client),
    )

    assert unknown_response.status_code == 400
    assert wrong_password_response.status_code == 400
    assert unknown_response.json() == {"detail": "Invalid email or password."}
    assert wrong_password_response.json() == {"detail": "Invalid email or password."}


@pytest.mark.django_db
def test_login_me_and_logout_follow_the_session_contract(csrf_client: Client) -> None:
    """Login exposes the current user and logout invalidates that session."""
    User.objects.create_user(
        email="player@example.test",
        password="a secure password 123",
        display_name="Player",
    )

    login_response = post_json(
        csrf_client,
        "/api/auth/login",
        {"email": "player@example.test", "password": "a secure password 123"},
        csrf_token(csrf_client),
    )

    assert login_response.status_code == 200
    assert csrf_client.get("/api/auth/me").json()["email"] == "player@example.test"

    logout_response = post_json(
        csrf_client,
        "/api/auth/logout",
        {},
        csrf_token(csrf_client),
    )

    assert logout_response.status_code == 204
    assert csrf_client.get("/api/auth/me").status_code == 403


def test_unsafe_auth_request_requires_a_csrf_token(csrf_client: Client) -> None:
    """Anonymous login is protected even before a session exists."""
    response = post_json(
        csrf_client,
        "/api/auth/login",
        {"email": "player@example.test", "password": "a secure password 123"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed."}
