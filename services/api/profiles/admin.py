"""Restricted Django administration for TailTag player profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.forms import ModelForm
from django.http import Http404, HttpRequest, HttpResponse

from accounts.models import User
from operator_audit.admin_actions import (
    execute_bound_operator_transition,
    parse_admin_object_id,
    run_sensitive_admin_attempt,
)
from operator_audit.models import OperatorAction, OperatorTargetType
from profiles.models import PlayerProfile
from profiles.services import set_profile_enabled

if TYPE_CHECKING:
    PlayerProfileAdminBase = admin.ModelAdmin[PlayerProfile]
else:
    PlayerProfileAdminBase = admin.ModelAdmin


def _has_permission(request: HttpRequest, permission: str) -> bool:
    user = cast(User, request.user)
    return user.is_staff and user.has_perm(permission)


@admin.register(PlayerProfile)
class PlayerProfileAdmin(PlayerProfileAdminBase):
    """Inspect player state and permit only per-object eligibility changes."""

    fields = (
        "application_user_id",
        "handle",
        "display_name",
        "onboarding_complete",
        "is_enabled",
        "avatar_present",
    )
    readonly_fields = (
        "application_user_id",
        "handle",
        "display_name",
        "onboarding_complete",
        "avatar_present",
    )
    list_display = (
        "application_user_id",
        "handle",
        "display_name",
        "onboarding_complete",
        "is_enabled",
        "avatar_present",
    )
    list_filter = ("is_enabled",)
    search_fields = ("user__id__exact", "handle__exact", "display_name__exact")
    ordering = ("user_id",)
    actions = None

    @admin.display(description="Application user ID", ordering="user_id")
    def application_user_id(self, profile: PlayerProfile) -> int:
        """Show the TailTag-owned user ID without dereferencing provider identity."""
        return profile.user_id

    @admin.display(boolean=True, description="Onboarding complete")
    def onboarding_complete(self, profile: PlayerProfile) -> bool:
        """Show derived onboarding state without exposing lifecycle timestamps."""
        return profile.onboarding_complete

    @admin.display(boolean=True, description="Avatar present")
    def avatar_present(self, profile: PlayerProfile) -> bool:
        """Show avatar existence without exposing opaque media references."""
        return profile.avatar_present

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Profiles are materialized only through the player profile service."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: PlayerProfile | None = None
    ) -> bool:
        """Profile deletion is outside the V0 administrative contract."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: PlayerProfile | None = None
    ) -> bool:
        return _has_permission(request, "profiles.set_profile_enabled")

    def has_view_permission(
        self, request: HttpRequest, obj: PlayerProfile | None = None
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
            permission="profiles.set_profile_enabled",
            action=OperatorAction.SET_PROFILE_ENABLED,
            target_type=OperatorTargetType.PLAYER_PROFILE,
            target_id=target_id,
            handler=lambda: super(PlayerProfileAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: PlayerProfile,
        form: ModelForm[PlayerProfile],
        change: bool,
    ) -> None:
        """Route the sole editable field through its transactional lifecycle seam."""
        if not change or set(form.changed_data) - {"is_enabled"}:
            raise PermissionDenied
        if "is_enabled" not in form.changed_data:
            return
        updated = execute_bound_operator_transition(
            request,
            lambda: set_profile_enabled(profile_id=obj.pk, is_enabled=obj.is_enabled),
        )
        obj.is_enabled = updated.is_enabled
