"""Custom user model behavior."""

from __future__ import annotations

from uuid import UUID

import pytest
from django.db import IntegrityError

from accounts.models import User


@pytest.mark.django_db
def test_user_manager_stores_a_canonical_email_and_hashed_password() -> None:
    """A user has a UUID identity and never stores the plaintext password."""
    password = "a secure password 123"

    user = User.objects.create_user(
        email="  Alice@Example.Test ",
        password=password,
        display_name="Alice",
    )

    assert isinstance(user.id, UUID)
    assert user.email == "alice@example.test"
    assert user.check_password(password)
    assert user.password != password


@pytest.mark.django_db
def test_user_manager_enforces_canonical_email_uniqueness() -> None:
    """Email casing and surrounding whitespace cannot create another account."""
    User.objects.create_user(
        email="alice@example.test",
        password="a secure password 123",
        display_name="Alice",
    )

    with pytest.raises(IntegrityError):
        User.objects.create_user(
            email=" Alice@Example.Test ",
            password="another secure password 123",
            display_name="Another Alice",
        )
