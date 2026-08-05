"""Safe Django administration for custom account identities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User

if TYPE_CHECKING:
    UserAdminBase = DjangoUserAdmin[User]
else:
    UserAdminBase = DjangoUserAdmin


@admin.register(User)
class UserAdmin(UserAdminBase):
    """Expose user administration while retaining Django's password workflow."""

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name",)}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Audit", {"fields": ("id", "created_at", "updated_at")}),
    )
    list_display = ("email", "display_name", "is_active", "is_staff", "created_at")
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("email",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("email", "display_name")
