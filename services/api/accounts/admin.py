"""Secret-safe administration for TailTag application identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from .models import User

if TYPE_CHECKING:
    UserAdminBase = admin.ModelAdmin[User]
else:
    UserAdminBase = admin.ModelAdmin


@admin.register(User)
class UserAdmin(UserAdminBase):
    """Inspect identity links without exposing local credential material."""

    fields = (
        "id",
        "clerk_user_id",
        "is_staff",
        "is_superuser",
        "groups",
        "user_permissions",
        "last_login",
    )
    filter_horizontal = ("groups", "user_permissions")
    list_display = ("id", "clerk_user_id", "is_staff", "is_superuser")
    list_filter = ("is_staff", "is_superuser")
    ordering = ("id",)
    readonly_fields = fields
    search_fields = ("id__exact", "clerk_user_id__exact")

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Allow identity inspection while rejecting all change submissions."""
        if request.method == "POST":
            raise PermissionDenied
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Keep application-user provisioning outside Django admin."""
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: User | None = None,
    ) -> bool:
        """Keep account deletion outside this identity contract."""
        return False
