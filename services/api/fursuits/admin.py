"""Restricted Django administration for participating characters."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.forms import ModelForm
from django.http import Http404, HttpRequest, HttpResponse
from django.utils.html import format_html

from accounts.models import User
from media.service import read_image_url
from operator_audit.admin_actions import (
    execute_bound_operator_transition,
    parse_admin_object_id,
    run_sensitive_admin_attempt,
)
from operator_audit.models import OperatorAction, OperatorTargetType

from .models import Fursuit
from .services import set_fursuit_enabled

if TYPE_CHECKING:
    FursuitAdminBase = admin.ModelAdmin[Fursuit]
else:
    FursuitAdminBase = admin.ModelAdmin


def _has_permission(request: HttpRequest, permission: str) -> bool:
    user = cast(User, request.user)
    return user.is_staff and user.has_perm(permission)


@admin.register(Fursuit)
class FursuitAdmin(FursuitAdminBase):
    """Inspect fursuits and permit only per-object enablement changes."""

    fields = (
        "id",
        "tailtag_id",
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
        "tailtag_id",
        "application_owner_id",
        "name",
        "photo_present",
        "photo_link",
        "created_at",
        "updated_at",
    )
    list_display = (
        "id",
        "tailtag_id",
        "application_owner_id",
        "name",
        "is_enabled",
        "photo_present",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_enabled",)
    search_fields = (
        "id__exact",
        "tailtag_id__exact",
        "owner__id__exact",
        "name__exact",
    )
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

    def has_change_permission(
        self, request: HttpRequest, obj: Fursuit | None = None
    ) -> bool:
        return _has_permission(request, "fursuits.set_fursuit_enabled")

    def has_view_permission(
        self, request: HttpRequest, obj: Fursuit | None = None
    ) -> bool:
        return self.has_change_permission(request, obj) or super().has_view_permission(
            request, obj
        )

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        if request.method != "POST" or object_id is None:
            return super().changeform_view(request, object_id, form_url, extra_context)
        target_id = parse_admin_object_id(object_id)
        if target_id is None:
            super().changeform_view(request, object_id, form_url, extra_context)
            raise Http404
        return run_sensitive_admin_attempt(
            request,
            permission="fursuits.set_fursuit_enabled",
            action=OperatorAction.SET_FURSUIT_ENABLED,
            target_type=OperatorTargetType.FURSUIT,
            target_id=target_id,
            handler=lambda: super(FursuitAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: Fursuit,
        form: ModelForm[Fursuit],
        change: bool,
    ) -> None:
        """Persist the only permitted operator mutation without broad saves."""
        if not change or set(form.changed_data) - {"is_enabled"}:
            raise PermissionDenied
        if "is_enabled" not in form.changed_data:
            return

        transition = set_fursuit_enabled(fursuit_id=obj.pk, is_enabled=obj.is_enabled)
        updated = (
            execute_bound_operator_transition(request, lambda: transition)
            if hasattr(request, "_operator_audit_attempt")
            else transition.value
        )
        obj.is_enabled = updated.is_enabled
        obj.updated_at = updated.updated_at
