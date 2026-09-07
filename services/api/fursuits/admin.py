"""Restricted Django administration for participating characters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.html import format_html

from media.service import read_image_url

from .models import Fursuit
from .services import set_fursuit_enabled

if TYPE_CHECKING:
    FursuitAdminBase = admin.ModelAdmin[Fursuit]
else:
    FursuitAdminBase = admin.ModelAdmin


@admin.register(Fursuit)
class FursuitAdmin(FursuitAdminBase):
    """Inspect fursuits and permit only per-object enablement changes."""

    fields = (
        "id",
        "application_owner_id",
        "name",
        "is_enabled",
        "photo_present",
        "photo_link",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "id",
        "application_owner_id",
        "name",
        "photo_present",
        "photo_link",
        "created_at",
        "updated_at",
    )
    list_display = (
        "id",
        "application_owner_id",
        "name",
        "is_enabled",
        "photo_present",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_enabled",)
    search_fields = ("id__exact", "owner__id__exact", "name__exact")
    ordering = ("id",)
    actions = None

    @admin.display(description="Application owner ID", ordering="owner_id")
    def application_owner_id(self, fursuit: Fursuit) -> int:
        """Show TailTag's internal owner identity without provider data."""
        return fursuit.owner_id

    @admin.display(boolean=True, description="Photo present")
    def photo_present(self, fursuit: Fursuit) -> bool:
        """Show photo presence without disclosing the opaque media key."""
        return fursuit.photo_present

    @admin.display(description="Photo link")
    def photo_link(self, fursuit: Fursuit) -> str:
        """Generate a short-lived inspection link only when detail renders."""
        photo_url = read_image_url(fursuit.photo_key)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">View photo</a>', photo_url
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Fursuits are created only through the player API."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Fursuit | None = None
    ) -> bool:
        """Fursuit records are durable and have no administrative delete path."""
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: Fursuit,
        form: ModelForm[Fursuit],
        change: bool,
    ) -> None:
        """Persist the only permitted operator mutation without broad saves."""
        del request
        if not change or set(form.changed_data) - {"is_enabled"}:
            raise PermissionDenied
        if "is_enabled" not in form.changed_data:
            return

        updated = set_fursuit_enabled(fursuit_id=obj.pk, is_enabled=obj.is_enabled)
        obj.is_enabled = updated.is_enabled
        obj.updated_at = updated.updated_at
