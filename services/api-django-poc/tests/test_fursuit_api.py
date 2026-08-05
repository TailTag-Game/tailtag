"""Owner-scoped fursuit API behavior."""

from __future__ import annotations

import json
from typing import cast

import pytest
from django.test import Client

from accounts.models import User
from fursuits.models import Fursuit
from tests.test_auth_api import JsonResponse, csrf_token


def json_request(
    client: Client,
    method: str,
    path: str,
    data: dict[str, str] | None,
    token: str | None,
) -> JsonResponse:
    """Make a JSON request with an optional CSRF header."""
    headers = {"X-CSRFToken": token} if token is not None else None
    response = getattr(client, method)(
        path,
        data=json.dumps(data) if data is not None else None,
        content_type="application/json",
        headers=headers,
    )
    return cast(JsonResponse, response)


@pytest.fixture
def owner() -> User:
    """Create the authenticated owner for a fursuit test."""
    return User.objects.create_user(
        email="owner@example.test",
        password="a secure password 123",
        display_name="Owner",
    )


@pytest.fixture
def other_user() -> User:
    """Create a user who must not see the owner's profiles."""
    return User.objects.create_user(
        email="other@example.test",
        password="a secure password 123",
        display_name="Other",
    )


@pytest.fixture
def csrf_client(owner: User) -> Client:
    """Return a CSRF-enforcing, authenticated browser client."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_create_list_update_and_delete_owned_fursuit(
    csrf_client: Client, owner: User
) -> None:
    """The owner can complete the full fursuit lifecycle."""
    token = csrf_token(csrf_client)
    create = json_request(
        csrf_client,
        "post",
        "/api/fursuits",
        {"name": "Nova", "species": "Fox", "description": "Friendly"},
        token,
    )

    assert create.status_code == 201
    fursuit_id = str(create.json()["id"])
    assert create.json()["owner_id"] == str(owner.id)

    listed = csrf_client.get("/api/fursuits")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [fursuit_id]

    updated = json_request(
        csrf_client,
        "patch",
        f"/api/fursuits/{fursuit_id}",
        {"description": "Updated"},
        csrf_token(csrf_client),
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated"

    deleted = json_request(
        csrf_client,
        "delete",
        f"/api/fursuits/{fursuit_id}",
        None,
        csrf_token(csrf_client),
    )
    assert deleted.status_code == 204
    assert not Fursuit.objects.filter(pk=fursuit_id).exists()


@pytest.mark.django_db
def test_other_users_fursuit_is_not_disclosed(
    csrf_client: Client, other_user: User
) -> None:
    """A cross-owner identifier is indistinguishable from a missing profile."""
    fursuit = Fursuit.objects.create(owner=other_user, name="Secret", species="Wolf")
    detail = f"/api/fursuits/{fursuit.id}"

    assert csrf_client.get(detail).status_code == 404
    assert (
        json_request(
            csrf_client, "patch", detail, {"name": "Changed"}, csrf_token(csrf_client)
        ).status_code
        == 404
    )
    assert (
        json_request(
            csrf_client, "delete", detail, None, csrf_token(csrf_client)
        ).status_code
        == 404
    )


def test_fursuits_reject_unauthenticated_and_missing_csrf_requests() -> None:
    """Protected writes require both a session and a CSRF token."""
    client = Client(enforce_csrf_checks=True)

    assert client.get("/api/fursuits").status_code == 403
    assert (
        json_request(
            client,
            "post",
            "/api/fursuits",
            {"name": "Nova", "species": "Fox"},
            None,
        ).status_code
        == 403
    )
