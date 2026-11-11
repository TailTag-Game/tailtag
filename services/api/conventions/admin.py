"""Operator administration for TailTag conventions and enrollments."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.forms import ModelForm
from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone

from accounts.models import User
from operator_audit.admin_actions import (
    execute_bound_operator_transition,
    parse_admin_object_id,
    run_sensitive_admin_attempt,
)
from operator_audit.models import OperatorAction, OperatorTargetType

from .catch_credential_protocol import CATCH_CREDENTIAL_TOKEN_PATTERN
from .catch_credentials import revoke_catch_credential_as_operator
from .catch_sessions import terminate_session_as_operator
from .models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from .review_deadline import (
    apply_review_schedule,
    review_deadline_local_date,
    review_window_open,
    time_zone_names,
)
from .services import (
    ConventionPlayabilityBoundaryError,
    ConventionTimeZoneRequiredError,
    deactivate_fursuit_activation_as_operator,
    remove_convention_enrollment,
    set_convention_admin_state,
)

_SENSITIVE_CREDENTIAL_SEARCH_PATTERN = re.compile(
    CATCH_CREDENTIAL_TOKEN_PATTERN, re.ASCII
)
_REDACTED_CREDENTIAL_SEARCH_QUERY = "__tailtag_admin_credential_query_redacted__"
_CREDENTIAL_FILTER_LOOKUPS = ("revocation_reason", "activation__convention")

if TYPE_CHECKING:
    ConventionAdminBase = admin.ModelAdmin[Convention]
    ConventionEnrollmentAdminBase = admin.ModelAdmin[ConventionEnrollment]
    FursuitActivationAdminBase = admin.ModelAdmin[FursuitActivation]
    FursuitCatchCredentialAdminBase = admin.ModelAdmin[FursuitCatchCredential]
    FursuitCatchSessionAdminBase = admin.ModelAdmin[FursuitCatchSession]
else:
    ConventionAdminBase = admin.ModelAdmin
    ConventionEnrollmentAdminBase = admin.ModelAdmin
    FursuitActivationAdminBase = admin.ModelAdmin
    FursuitCatchCredentialAdminBase = admin.ModelAdmin
    FursuitCatchSessionAdminBase = admin.ModelAdmin


def _has_permission(request: HttpRequest, permission: str) -> bool:
    user = cast(User, request.user)
    return user.is_staff and user.has_perm(permission)


def _time_zone_choices() -> list[tuple[str, str]]:
    """Build the zone list at form time, so a tzdata update needs no migration."""
    return [("", "---------"), *((name, name) for name in sorted(time_zone_names()))]


class ConventionAdminForm(forms.ModelForm):  # pyright: ignore[reportMissingTypeArgument]
    time_zone = forms.ChoiceField(
        choices=_time_zone_choices,
        required=False,
        help_text=(
            "IANA time zone of the convention. Catch requests stay unavailable "
            "until it is set. A set zone cannot be removed."
        ),
    )

    class Meta:
        model = Convention
        fields = "__all__"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # pyright: ignore[reportArgumentType, reportUnknownMemberType]
        field = self.fields.get("time_zone")
        if isinstance(field, forms.ChoiceField) and self.instance.time_zone:  # pyright: ignore[reportUnknownMemberType]
            field.choices = [choice for choice in _time_zone_choices() if choice[0]]

    def clean_time_zone(self) -> str | None:
        time_zone = self.cleaned_data["time_zone"] or None
        if time_zone is None and self.instance.time_zone:  # pyright: ignore[reportUnknownMemberType]
            raise forms.ValidationError("A set time zone cannot be removed.")
        return time_zone

    def clean_status(self) -> str:
        status = self.cleaned_data["status"]
        if self.instance.pk is None and status == ConventionStatus.ACTIVE.value:  # pyright: ignore[reportUnknownMemberType]
            raise forms.ValidationError("Conventions cannot be created playable.")
        return status


@admin.register(Convention)
class ConventionAdmin(ConventionAdminBase):
    """Admin interface for operator creation, editing, and lifecycle management."""

    form = ConventionAdminForm

    list_display = (
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
        "time_zone",
        "review_deadline_at",
        "created_at",
    )
    list_filter = (
        "status",
        "start_date",
        "end_date",
        ("time_zone", admin.EmptyFieldListFilter),
    )
    search_fields = ("name",)
    readonly_fields = (
        "review_deadline_utc",
        "review_deadline_local_day",
        "review_window",
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
                    "time_zone",
                ),
            },
        ),
        (
            "Catch request review",
            {
                "fields": (
                    "review_deadline_utc",
                    "review_deadline_local_day",
                    "review_window",
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

    def get_readonly_fields(
        self, request: HttpRequest, obj: Convention | None = None
    ) -> tuple[str, ...]:
        if (
            obj is not None
            and _has_permission(request, "conventions.set_convention_playability")
            and not _has_permission(request, "conventions.change_convention")
        ):
            return (
                *self.readonly_fields,
                "name",
                "start_date",
                "end_date",
                "time_zone",
            )
        return tuple(self.readonly_fields)

    @admin.display(description="Review deadline (UTC)")
    def review_deadline_utc(self, obj: Convention) -> str:
        deadline = obj.review_deadline_at
        return "-" if deadline is None else deadline.isoformat()

    @admin.display(description="Review deadline local date")
    def review_deadline_local_day(self, obj: Convention) -> str:
        local_date = review_deadline_local_date(obj)
        return "-" if local_date is None else local_date.isoformat()

    @admin.display(description="Review window")
    def review_window(self, obj: Convention) -> str:
        if obj.review_deadline_at is None:
            return "Unavailable until a time zone is set"
        return "Open" if review_window_open(obj, timezone.now()) else "Closed"

    def has_change_permission(
        self, request: HttpRequest, obj: Convention | None = None
    ) -> bool:
        return _has_permission(
            request, "conventions.change_convention"
        ) or _has_permission(request, "conventions.set_convention_playability")

    def has_view_permission(
        self, request: HttpRequest, obj: Convention | None = None
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
            raise Http404
        convention = Convention.objects.filter(pk=target_id).first()
        submitted_status = request.POST.get("status")
        if convention is None:
            if submitted_status == ConventionStatus.ACTIVE.value:
                return run_sensitive_admin_attempt(
                    request,
                    permission="conventions.set_convention_playability",
                    action=OperatorAction.SET_CONVENTION_PLAYABILITY,
                    target_type=OperatorTargetType.CONVENTION,
                    target_id=target_id,
                    handler=lambda: super(ConventionAdmin, self).changeform_view(
                        request, object_id, form_url, extra_context
                    ),
                )
            return super().changeform_view(request, object_id, form_url, extra_context)
        if submitted_status not in ConventionStatus.values:
            return super().changeform_view(request, object_id, form_url, extra_context)
        # A move into cancellation ends catch requests, so it needs the
        # playability authority and its audit, like a playability change (#507 G4).
        crosses = convention.is_playable != (
            submitted_status == ConventionStatus.ACTIVE.value
        ) or (
            submitted_status == ConventionStatus.CANCELLED.value
            and convention.status != ConventionStatus.CANCELLED.value
        )
        generic = _has_permission(request, "conventions.change_convention")
        control = _has_permission(request, "conventions.set_convention_playability")
        if not generic and control and not crosses:
            raise PermissionDenied

        def render() -> HttpResponse:
            if (
                control
                and not generic
                and any(
                    field in request.POST
                    and request.POST[field] != str(getattr(convention, field) or "")
                    for field in ("name", "start_date", "end_date", "time_zone")
                )
            ):
                raise PermissionDenied
            request.__dict__["_convention_expected_is_playable"] = (
                convention.is_playable
            )
            request.__dict__["_convention_allow_playability_transition"] = crosses
            try:
                return super(ConventionAdmin, self).changeform_view(
                    request, object_id, form_url, extra_context
                )
            finally:
                delattr(request, "_convention_expected_is_playable")
                delattr(request, "_convention_allow_playability_transition")

        if crosses:
            return run_sensitive_admin_attempt(
                request,
                permission="conventions.set_convention_playability",
                action=OperatorAction.SET_CONVENTION_PLAYABILITY,
                target_type=OperatorTargetType.CONVENTION,
                target_id=target_id,
                handler=render,
                rejected_exceptions=(
                    PermissionDenied,
                    ConventionPlayabilityBoundaryError,
                ),
            )
        return render()

    def save_model(
        self,
        request: HttpRequest,
        obj: Convention,
        form: ModelForm[Convention],
        change: bool,
    ) -> None:
        """Route edits through the lock-aware Convention lifecycle seam."""
        if not change:
            apply_review_schedule(obj, end_date=obj.end_date, time_zone=obj.time_zone)
            super().save_model(request, obj, form, change)
            return
        if (
            _has_permission(request, "conventions.set_convention_playability")
            and not _has_permission(request, "conventions.change_convention")
            and set(form.changed_data) - {"status"}
        ):
            raise PermissionDenied
        operation = lambda: set_convention_admin_state(
            convention_id=obj.pk,
            name=obj.name,
            status=obj.status,
            start_date=obj.start_date,
            end_date=obj.end_date,
            time_zone=obj.time_zone,
            expected_is_playable=cast(
                bool, request.__dict__["_convention_expected_is_playable"]
            ),
            allow_playability_transition=cast(
                bool, request.__dict__["_convention_allow_playability_transition"]
            ),
        )
        try:
            if hasattr(request, "_operator_audit_attempt"):
                updated = execute_bound_operator_transition(request, operation)
            else:
                updated = operation().value
        except (
            ConventionPlayabilityBoundaryError,
            ConventionTimeZoneRequiredError,
        ) as error:
            raise PermissionDenied from error
        obj.updated_at = updated.updated_at
        obj.review_deadline_at = updated.review_deadline_at

    def delete_model(self, request: HttpRequest, obj: Convention) -> None:
        with transaction.atomic():
            locked = Convention.objects.select_for_update().get(pk=obj.pk)
            if locked.is_playable:
                raise PermissionDenied
            super().delete_model(request, locked)

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[Convention]
    ) -> None:
        del request, queryset
        raise PermissionDenied("Bulk Convention deletion is not permitted.")


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

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: ConventionEnrollment | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: ConventionEnrollment | None = None
    ) -> bool:
        return _has_permission(request, "conventions.remove_convention_enrollment")

    def has_view_permission(
        self, request: HttpRequest, obj: ConventionEnrollment | None = None
    ) -> bool:
        return self.has_delete_permission(request, obj) or super().has_view_permission(
            request, obj
        )

    def get_readonly_fields(
        self, request: HttpRequest, obj: ConventionEnrollment | None = None
    ) -> tuple[str, ...]:
        """Enrollment identity is immutable after creation."""
        if obj is None:
            return tuple(self.readonly_fields)
        return (*tuple(self.readonly_fields), "user", "convention", "is_active")

    def delete_model(self, request: HttpRequest, obj: ConventionEnrollment) -> None:
        """Route per-object removal through its transactional termination seam."""
        execute_bound_operator_transition(
            request, lambda: remove_convention_enrollment(enrollment_id=obj.pk)
        )

    def delete_view(
        self,
        request: HttpRequest,
        object_id: str,
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        if request.method != "POST":
            return super().delete_view(request, object_id, extra_context)
        target_id = parse_admin_object_id(object_id)
        if target_id is None:
            raise Http404
        return run_sensitive_admin_attempt(
            request,
            permission="conventions.remove_convention_enrollment",
            action=OperatorAction.REMOVE_CONVENTION_ENROLLMENT,
            target_type=OperatorTargetType.CONVENTION_ENROLLMENT,
            target_id=target_id,
            handler=lambda: super(ConventionEnrollmentAdmin, self).delete_view(
                request, object_id, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
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

    def has_change_permission(
        self, request: HttpRequest, obj: FursuitActivation | None = None
    ) -> bool:
        return _has_permission(request, "conventions.deactivate_fursuit_activation")

    def has_view_permission(
        self, request: HttpRequest, obj: FursuitActivation | None = None
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
            raise Http404
        return run_sensitive_admin_attempt(
            request,
            permission="conventions.deactivate_fursuit_activation",
            action=OperatorAction.DEACTIVATE_FURSUIT_ACTIVATION,
            target_type=OperatorTargetType.FURSUIT_ACTIVATION,
            target_id=target_id,
            handler=lambda: super(FursuitActivationAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

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
        if not change or set(form.changed_data) - {"is_active"}:
            raise PermissionDenied
        if "is_active" not in form.changed_data:
            return
        if obj.is_active:
            raise PermissionDenied

        transition = deactivate_fursuit_activation_as_operator(activation_id=obj.pk)
        updated = (
            execute_bound_operator_transition(request, lambda: transition)
            if hasattr(request, "_operator_audit_attempt")
            else transition.value
        )
        obj.is_active = updated.is_active
        obj.deactivated_at = updated.deactivated_at
        obj.updated_at = updated.updated_at


if TYPE_CHECKING:
    CatchCredentialAdminFormBase = forms.ModelForm[FursuitCatchCredential]
else:
    CatchCredentialAdminFormBase = forms.ModelForm


class CatchCredentialAdminForm(CatchCredentialAdminFormBase):
    """Expose only the explicit terminal operator control."""

    revoke = forms.BooleanField(required=False, label="Revoke current credential")

    class Meta:
        model = FursuitCatchCredential
        fields: tuple[()] = ()


@admin.register(FursuitCatchCredential)
class FursuitCatchCredentialAdmin(FursuitCatchCredentialAdminBase):
    """Inspect credential history and permit only current-row revocation."""

    form = CatchCredentialAdminForm
    fields = (
        "id",
        "activation",
        "revoked_at",
        "revocation_reason",
        "created_at",
        "updated_at",
        "revoke",
    )
    readonly_fields = (
        "id",
        "activation",
        "revoked_at",
        "revocation_reason",
        "created_at",
        "updated_at",
    )
    list_display = (
        "id",
        "activation",
        "is_current",
        "revoked_at",
        "revocation_reason",
        "created_at",
        "updated_at",
    )
    list_filter = ("revocation_reason", "activation__convention")
    search_fields = (
        "id__exact",
        "activation__id__exact",
        "activation__fursuit__id__exact",
        "activation__fursuit__tailtag_id__exact",
        "activation__fursuit__owner__id__exact",
        "activation__convention__id__exact",
        "activation__fursuit__name",
        "activation__convention__name",
    )
    ordering = ("-created_at", "-id")
    actions = None

    def has_change_permission(
        self, request: HttpRequest, obj: FursuitCatchCredential | None = None
    ) -> bool:
        return _has_permission(request, "conventions.revoke_catch_credential")

    def has_view_permission(
        self, request: HttpRequest, obj: FursuitCatchCredential | None = None
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
            raise Http404
        return run_sensitive_admin_attempt(
            request,
            permission="conventions.revoke_catch_credential",
            action=OperatorAction.REVOKE_CATCH_CREDENTIAL,
            target_type=OperatorTargetType.FURSUIT_CATCH_CREDENTIAL,
            target_id=target_id,
            handler=lambda: super(FursuitCatchCredentialAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        """Redact credential-shaped queries before Django renders preserved filters."""
        if any(
            _SENSITIVE_CREDENTIAL_SEARCH_PATTERN.search(value)
            for value in request.GET.getlist("q")
        ):
            query = request.GET.copy()
            query.setlist("q", [_REDACTED_CREDENTIAL_SEARCH_QUERY])
            object.__setattr__(request, "GET", query)
            request.META["QUERY_STRING"] = query.urlencode()
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(boolean=True, description="Current")
    def is_current(self, credential: FursuitCatchCredential) -> bool:
        """Derive current state solely from the terminal timestamp."""
        return credential.revoked_at is None

    def lookup_allowed(self, lookup: str, value: str, request: HttpRequest) -> bool:
        """Allow URL filters only behind the list filters.

        Django otherwise accepts a lookup on any local field, so a URL such as
        ``?token__startswith=`` would let an operator recover a token.
        """
        return any(
            lookup == prefix or lookup.startswith(f"{prefix}__")
            for prefix in _CREDENTIAL_FILTER_LOOKUPS
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Credentials originate only from the owner lifecycle."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: FursuitCatchCredential | None = None
    ) -> bool:
        """Credential history is append-only and cannot be deleted."""
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: FursuitCatchCredential,
        form: CatchCredentialAdminForm,
        change: bool,
    ) -> None:
        """Delegate the sole permitted mutation to its lock-aware service."""
        if not change or set(form.changed_data) - {"revoke"}:
            raise PermissionDenied
        if not form.cleaned_data["revoke"]:
            return
        transition = revoke_catch_credential_as_operator(obj.pk)
        updated = (
            execute_bound_operator_transition(request, lambda: transition)
            if hasattr(request, "_operator_audit_attempt")
            else transition.value
        )
        obj.revoked_at = updated.revoked_at
        obj.revocation_reason = updated.revocation_reason
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

    def has_change_permission(
        self, request: HttpRequest, obj: FursuitCatchSession | None = None
    ) -> bool:
        return _has_permission(request, "conventions.terminate_catch_session")

    def has_view_permission(
        self, request: HttpRequest, obj: FursuitCatchSession | None = None
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
            raise Http404
        return run_sensitive_admin_attempt(
            request,
            permission="conventions.terminate_catch_session",
            action=OperatorAction.TERMINATE_CATCH_SESSION,
            target_type=OperatorTargetType.FURSUIT_CATCH_SESSION,
            target_id=target_id,
            handler=lambda: super(FursuitCatchSessionAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[FursuitCatchSession]:
        effective_session = _effectively_active_sessions(
            FursuitCatchSession.objects.filter(pk=OuterRef("pk"))
        )
        return (
            super()
            .get_queryset(request)
            .annotate(_is_effectively_active=Exists(effective_session))
        )

    @admin.display(boolean=True, description="Effectively active")
    def is_effectively_active(self, session: FursuitCatchSession) -> bool:
        """Show state computed from time and current operational participation."""
        return bool(getattr(session, "_is_effectively_active", False))

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
        if not change:
            raise PermissionDenied
        if not form.cleaned_data["terminate"]:
            return
        transition = terminate_session_as_operator(obj.pk)
        updated = (
            execute_bound_operator_transition(request, lambda: transition)
            if hasattr(request, "_operator_audit_attempt")
            else transition.value
        )
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
    return (
        queryset.filter(
            ended_at__isnull=True,
            expires_at__gt=timezone.now(),
            activation__is_active=True,
            activation__fursuit__is_enabled=True,
            activation__convention__status=ConventionStatus.ACTIVE,
            activation__fursuit__owner__player_profile__is_enabled=True,
            activation__fursuit__owner__player_profile__onboarding_completed_at__isnull=False,
            activation__fursuit__owner__player_profile__handle__isnull=False,
            activation__fursuit__owner__player_profile__display_name__isnull=False,
        )
        .filter(Exists(enrollment_exists))
        .exclude(activation__fursuit__owner__player_profile__display_name="")
    )
