"""Operator administration for TailTag conventions and enrollments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Convention, ConventionEnrollment

if TYPE_CHECKING:
    ConventionAdminBase = admin.ModelAdmin[Convention]
    ConventionEnrollmentAdminBase = admin.ModelAdmin[ConventionEnrollment]
else:
    ConventionAdminBase = admin.ModelAdmin
    ConventionEnrollmentAdminBase = admin.ModelAdmin


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
