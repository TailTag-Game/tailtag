"""Fursuit persistence behavior."""

from __future__ import annotations

from uuid import UUID

import pytest

from accounts.models import User
from fursuits.models import Fursuit


@pytest.mark.django_db
def test_fursuit_has_uuid_owner_empty_description_and_timestamps() -> None:
    """A fursuit is owned by one user and records its lifecycle timestamps."""
    user = User.objects.create_user(
        email="owner@example.test",
        password="a secure password 123",
        display_name="Owner",
    )

    fursuit = Fursuit.objects.create(owner=user, name="Nova", species="Fox")

    assert isinstance(fursuit.id, UUID)
    assert fursuit.owner_id == user.id
    assert fursuit.description == ""
    assert fursuit.created_at <= fursuit.updated_at


@pytest.mark.django_db
def test_deleting_a_user_cascades_to_owned_fursuits() -> None:
    """The POC's temporary retention rule follows the user lifecycle."""
    user = User.objects.create_user(
        email="owner@example.test",
        password="a secure password 123",
        display_name="Owner",
    )
    fursuit = Fursuit.objects.create(owner=user, name="Nova", species="Fox")

    user.delete()

    assert not Fursuit.objects.filter(pk=fursuit.pk).exists()
