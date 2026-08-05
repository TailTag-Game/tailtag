"""Django admin registration behavior."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User
from fursuits.models import Fursuit


def test_user_and_fursuit_admin_are_registered_safely() -> None:
    """Admin uses Django's password-safe user base and useful fursuit tools."""
    user_admin = admin.site._registry[User]
    fursuit_admin = admin.site._registry[Fursuit]

    assert isinstance(user_admin, DjangoUserAdmin)
    assert "email" in user_admin.search_fields
    assert {"id", "created_at", "updated_at"}.issubset(user_admin.readonly_fields)
    assert {"name", "species", "owner__email"}.issubset(fursuit_admin.search_fields)
    assert {"id", "created_at", "updated_at"}.issubset(fursuit_admin.readonly_fields)
