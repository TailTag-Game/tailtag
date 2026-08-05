"""Django administration for fursuit profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest

from .models import Fursuit

if TYPE_CHECKING:
    FursuitAdminBase = admin.ModelAdmin[Fursuit]
else:
    FursuitAdminBase = admin.ModelAdmin


@admin.register(Fursuit)
class FursuitAdmin(FursuitAdminBase):
    """Provide searchable, owner-aware support administration."""

    list_display = ("name", "species", "owner", "created_at", "updated_at")
    list_filter = ("species", "created_at")
    list_select_related = ("owner",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("name", "species", "owner__email")

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Fursuit | None = None,
    ) -> tuple[str, ...]:
        """Prevent accidental reassignment after a profile has been created."""
        del request
        if obj is None:
            return self.readonly_fields
        return (*self.readonly_fields, "owner")
