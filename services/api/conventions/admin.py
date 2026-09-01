"""Operator administration for TailTag conventions and enrollments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils import timezone

from .catch_sessions import terminate_session_as_operator
from .models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchSession,
)
from .services import (
    deactivate_fursuit_activation_as_operator,
    remove_convention_enrollment,
    set_convention_admin_state,
)

if TYPE_CHECKING:
    ConventionAdminBase = admin.ModelAdmin[Convention]
    ConventionEnrollmentAdminBase = admin.ModelAdmin[ConventionEnrollment]
    FursuitActivationAdminBase = admin.ModelAdmin[FursuitActivation]
    FursuitCatchSessionAdminBase = admin.ModelAdmin[FursuitCatchSession]
else:
    ConventionAdminBase = admin.ModelAdmin
    ConventionEnrollmentAdminBase = admin.ModelAdmin
    FursuitActivationAdminBase = admin.ModelAdmin
    FursuitCatchSessionAdminBase = admin.ModelAdmin


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

    def save_model(
        self,
        request: HttpRequest,
        obj: Convention,
        form: ModelForm[Convention],
        change: bool,
    ) -> None:
        """Route edits through the lock-aware Convention lifecycle seam."""
        if not change:
            super().save_model(request, obj, form, change)
            return
        updated = set_convention_admin_state(
            convention_id=obj.pk,
            name=obj.name,
            status=obj.status,
            start_date=obj.start_date,
            end_date=obj.end_date,
        )
        obj.updated_at = updated.updated_at


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
    actions = None

    def get_readonly_fields(
        self, request: HttpRequest, obj: ConventionEnrollment | None = None
    ) -> tuple[str, ...]:
        """Enrollment identity is immutable after creation."""
        if obj is None:
            return tuple(self.readonly_fields)
        return (*tuple(self.readonly_fields), "user", "convention")

    def delete_model(self, request: HttpRequest, obj: ConventionEnrollment) -> None:
        """Route per-object removal through its transactional termination seam."""
        del request
        remove_convention_enrollment(enrollment_id=obj.pk)


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

        updated = deactivate_fursuit_activation_as_operator(activation_id=obj.pk)
        obj.is_active = updated.is_active
        obj.deactivated_at = updated.deactivated_at
        obj.updated_at = updated.updated_at


class CatchSessionActiveFilter(admin.SimpleListFilter):
    """Filter using the same effective-active predicate shown in session admin."""

    title = "effectively active"
    parameter_name = "is_effectively_active"

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin[FursuitCatchSession],
    ) -> tuple[tuple[str, str], ...]:
        del request, model_admin
        return (("1", "Yes"), ("0", "No"))

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[FursuitCatchSession]
    ) -> QuerySet[FursuitCatchSession]:
        del request
        value = self.value()
        if value is None:
            return queryset
        active = _effectively_active_sessions(queryset)
        return active if value == "1" else queryset.exclude(pk__in=active.values("pk"))


if TYPE_CHECKING:
    CatchSessionAdminFormBase = forms.ModelForm[FursuitCatchSession]
else:
    CatchSessionAdminFormBase = forms.ModelForm


class CatchSessionAdminForm(CatchSessionAdminFormBase):
    """A single explicit operator action, never a history-edit form."""

    terminate = forms.BooleanField(required=False, label="Terminate active session")

    class Meta:
        model = FursuitCatchSession
        fields: tuple[()] = ()


@admin.register(FursuitCatchSession)
class FursuitCatchSessionAdmin(FursuitCatchSessionAdminBase):
    """Inspect catch-session history and permit only one per-object termination."""

    form = CatchSessionAdminForm
    fields = (
        "activation",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "created_at",
        "updated_at",
        "terminate",
    )
    readonly_fields = (
        "activation",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "created_at",
        "updated_at",
    )
    list_display = (
        "id",
        "activation",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "is_effectively_active",
    )
    list_filter = (CatchSessionActiveFilter, "end_reason", "activation__convention")
    search_fields = (
        "id__exact",
        "activation__fursuit__id__exact",
        "activation__fursuit__name",
        "activation__fursuit__owner__id__exact",
        "activation__convention__id__exact",
        "activation__convention__name__exact",
    )
    ordering = ("-started_at", "-id")
    actions = None

    @admin.display(boolean=True, description="Effectively active")
    def is_effectively_active(self, session: FursuitCatchSession) -> bool:
        """Show state computed from time and current operational participation."""
        return _effectively_active_sessions(
            FursuitCatchSession.objects.filter(pk=session.pk)
        ).exists()

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: FursuitCatchSession | None = None
    ) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: FursuitCatchSession,
        form: CatchSessionAdminForm,
        change: bool,
    ) -> None:
        """Use the session-domain operator transition rather than editing history."""
        del request
        if not change:
            raise PermissionDenied
        if not form.cleaned_data["terminate"]:
            return
        updated = terminate_session_as_operator(obj.pk)
        obj.ended_at = updated.ended_at
        obj.end_reason = updated.end_reason
        obj.updated_at = updated.updated_at


def _effectively_active_sessions(
    queryset: QuerySet[FursuitCatchSession],
) -> QuerySet[FursuitCatchSession]:
    """Return sessions that are live and presently operationally participating."""
    enrollment_exists = ConventionEnrollment.objects.filter(
        user_id=OuterRef("activation__fursuit__owner_id"),
        convention_id=OuterRef("activation__convention_id"),
    )
    return queryset.filter(
        ended_at__isnull=True,
        expires_at__gt=timezone.now(),
        activation__is_active=True,
        activation__fursuit__is_enabled=True,
        activation__convention__status="active",
        activation__fursuit__owner__player_profile__is_enabled=True,
        activation__fursuit__owner__player_profile__onboarding_completed_at__isnull=False,
        activation__fursuit__owner__player_profile__handle__isnull=False,
        activation__fursuit__owner__player_profile__display_name__isnull=False,
    ).filter(Exists(enrollment_exists)).exclude(
        activation__fursuit__owner__player_profile__display_name=""
    )
