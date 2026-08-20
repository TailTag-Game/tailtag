"""Operator administration for TailTag conventions."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib import admin

from .models import Convention

if TYPE_CHECKING:
    ConventionAdminBase = admin.ModelAdmin[Convention]
else:
    ConventionAdminBase = admin.ModelAdmin


@admin.register(Convention)
class ConventionAdmin(ConventionAdminBase):
    """Admin interface for operator creation, editing, and lifecycle management."""

    list_display: ClassVar[tuple[str, ...]] = (
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter: ClassVar[tuple[str, ...]] = (
        "status",
        "start_date",
        "end_date",
    )
    search_fields: ClassVar[tuple[str, ...]] = ("name",)
    readonly_fields: ClassVar[tuple[str, ...]] = (
        "created_at",
        "updated_at",
    )
    fieldsets: ClassVar[tuple[tuple[str | None, dict[str, object]], ...]] = (
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
