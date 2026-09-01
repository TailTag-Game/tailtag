"""Operator administration for TailTag conventions and enrollments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils import timezone

from .models import Convention, ConventionEnrollment, FursuitActivation

if TYPE_CHECKING:
    ConventionAdminBase = admin.ModelAdmin[Convention]
    ConventionEnrollmentAdminBase = admin.ModelAdmin[ConventionEnrollment]
    FursuitActivationAdminBase = admin.ModelAdmin[FursuitActivation]
else:
    ConventionAdminBase = admin.ModelAdmin
    ConventionEnrollmentAdminBase = admin.ModelAdmin
    FursuitActivationAdminBase = admin.ModelAdmin


@admin.register(Convention)
class ConventionAdmin(ConventionAdminBase):
    """Admin interface for operator creation, editing, and lifecycle management."""

    list_display = (
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter = (
        "status",
        "start_date",
        "end_date",
    )
    search_fields = ("name",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "status",
                    "start_date",
                    "end_date",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(ConventionEnrollment)
class ConventionEnrollmentAdmin(ConventionEnrollmentAdminBase):
    """Admin interface for operator inspection of player enrollments."""

    list_display = (
        "id",
        "user",
        "convention",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "convention__status",
        "convention",
        "created_at",
    )
    search_fields = (
        "user__clerk_user_id",
        "convention__name",
    )
    raw_id_fields = (
        "user",
        "convention",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(FursuitActivation)
class FursuitActivationAdmin(FursuitActivationAdminBase):
    """Inspect fursuit participation and permit only deactivation."""

    fields = (
        "id",
        "fursuit",
        "convention",
        "is_active",
        "activated_at",
        "deactivated_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "id",
        "fursuit",
        "convention",
        "activated_at",
        "deactivated_at",
        "created_at",
        "updated_at",
    )
    list_display = (
        "id",
        "fursuit",
        "convention",
        "is_active",
        "activated_at",
        "deactivated_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("fursuit", "convention", "is_active")
    search_fields = (
        "id__exact",
        "fursuit__id__exact",
        "fursuit__name__exact",
        "fursuit__owner__id__exact",
        "convention__id__exact",
        "convention__name__exact",
    )
    ordering = ("fursuit_id", "id")
    actions = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Fursuit participation is selected only through the owner API."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: FursuitActivation | None = None
    ) -> bool:
        """Activation records are durable and have no operator delete path."""
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: FursuitActivation,
        form: ModelForm[FursuitActivation],
        change: bool,
    ) -> None:
        """Persist only an active-to-inactive transition without broad saves."""
        del request
        if not change or set(form.changed_data) - {"is_active"}:
            raise PermissionDenied
        if "is_active" not in form.changed_data:
            return
        if obj.is_active:
            raise PermissionDenied

        now = timezone.now()
        updated = FursuitActivation.objects.filter(pk=obj.pk, is_active=True).update(
            is_active=False,
            deactivated_at=now,
            updated_at=now,
        )
        if not updated:
            obj.refresh_from_db()
            return
        obj.deactivated_at = now
        obj.updated_at = now
