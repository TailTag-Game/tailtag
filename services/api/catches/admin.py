"""Operator administration and correction for Catch records."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    QueryDict,
)

from accounts.models import User
from conventions.catch_credential_protocol import CATCH_CREDENTIAL_TOKEN_PATTERN
from operator_audit.admin_actions import (
    execute_bound_operator_transition,
    parse_admin_object_id,
    run_sensitive_admin_attempt,
)
from operator_audit.models import OperatorAction, OperatorTargetType

from .models import Catch, CatchBlock, CatchRequest
from .request_invalidation import invalidate_request_as_operator
from .services import remove_catch_as_operator

_SENSITIVE_CREDENTIAL_SEARCH_PATTERN = re.compile(
    CATCH_CREDENTIAL_TOKEN_PATTERN, re.ASCII
)
REDACTED_CREDENTIAL_SEARCH_QUERY = "__tailtag_admin_credential_query_redacted__"
_REDACTED_CREDENTIAL_SEARCH_QUERY = REDACTED_CREDENTIAL_SEARCH_QUERY


def _has_permission(request: HttpRequest, permission: str) -> bool:
    user = cast(User, request.user)
    return user.is_staff and user.has_perm(permission)


def _is_sensitive_credential_query(value: str) -> bool:
    return value != _REDACTED_CREDENTIAL_SEARCH_QUERY and bool(
        _SENSITIVE_CREDENTIAL_SEARCH_PATTERN.search(value)
    )


def _has_sensitive_credential_in_query(request: HttpRequest) -> bool:
    for key, values in request.GET.lists():
        if _is_sensitive_credential_query(key):
            return True
        if any(_is_sensitive_credential_query(val) for val in values):
            return True
    return False


def _build_sanitized_changelist_query(request: HttpRequest) -> QueryDict:
    sanitized = request.GET.copy()
    for key in list(sanitized.keys()):
        if _is_sensitive_credential_query(key):
            sanitized.pop(key, None)
            continue
        values = sanitized.getlist(key)
        if any(_is_sensitive_credential_query(val) for val in values):
            if key == "q":
                sanitized.setlist(key, [_REDACTED_CREDENTIAL_SEARCH_QUERY])
            else:
                sanitized.pop(key, None)
    if any(_is_sensitive_credential_query(val) for val in request.GET.getlist("q")):
        sanitized.setlist("q", [_REDACTED_CREDENTIAL_SEARCH_QUERY])
    return sanitized


if TYPE_CHECKING:
    CatchAdminBase = admin.ModelAdmin[Catch]
    CatchRequestAdminBase = admin.ModelAdmin[CatchRequest]
    CatchBlockAdminBase = admin.ModelAdmin[CatchBlock]
    CatchRequestAdminFormBase = forms.ModelForm[CatchRequest]
else:
    CatchAdminBase = admin.ModelAdmin
    CatchRequestAdminBase = admin.ModelAdmin
    CatchBlockAdminBase = admin.ModelAdmin
    CatchRequestAdminFormBase = forms.ModelForm


@admin.register(Catch)
class CatchAdmin(CatchAdminBase):
    """Admin interface for operator inspection and safe removal of catches."""

    change_list_template = "admin/catches/catch/change_list.html"
    fields = (
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
        "caught_at",
    )
    readonly_fields = fields
    list_display = (
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "caught_at",
        "activation",
        "catch_session",
    )
    list_select_related = (
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
    )
    list_filter = ("convention", "caught_at")
    search_fields = (
        "id__exact",
        "catcher_user__id__exact",
        "catcher_user__clerk_user_id",
        "fursuit__name",
        "fursuit__tailtag_id__exact",
        "convention__name",
    )
    ordering = ("-caught_at", "-id")
    actions = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: Catch | None = None
    ) -> bool:
        del request, obj
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Catch | None = None
    ) -> bool:
        user = request.user
        is_staff = bool(getattr(user, "is_staff", False))
        if not (user and user.is_authenticated and is_staff):
            return False
        return super().has_delete_permission(request, obj)

    def has_view_permission(
        self, request: HttpRequest, obj: Catch | None = None
    ) -> bool:
        return self.has_delete_permission(request, obj) or _has_permission(
            request, "catches.view_catch"
        )

    def delete_model(self, request: HttpRequest, obj: Catch) -> None:
        execute_bound_operator_transition(
            request, lambda: remove_catch_as_operator(catch_id=obj.pk)
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
            permission="catches.delete_catch",
            action=OperatorAction.REMOVE_CATCH,
            target_type=OperatorTargetType.CATCH,
            target_id=target_id,
            handler=lambda: super(CatchAdmin, self).delete_view(
                request, object_id, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Catch]) -> None:
        del request, queryset
        raise PermissionDenied("Bulk catch deletion is not permitted.")

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, object] | None = None,
    ) -> HttpResponse:
        """Sanitize credential-shaped queries via redirect before rendering."""
        if request.method == "POST":
            raise PermissionDenied("Bulk catch deletion is not permitted.")
        if _has_sensitive_credential_in_query(request):
            sanitized_query = _build_sanitized_changelist_query(request)
            redirect_url = (
                f"{request.path}?{sanitized_query.urlencode()}"
                if sanitized_query
                else request.path
            )
            return HttpResponseRedirect(redirect_url)
        return super().changelist_view(request, extra_context=extra_context)


class CatchRequestAdminForm(CatchRequestAdminFormBase):
    """Expose only the explicit invalidation control. No request field is editable."""

    invalidate = forms.BooleanField(
        required=False, label="Invalidate this pending or declined request"
    )

    class Meta:
        model = CatchRequest
        fields: tuple[()] = ()


_REQUEST_FIELDS = (
    "id",
    "player",
    "fursuit",
    "convention",
    "activation",
    "catch_session",
    "state",
    "requested_at",
    "approved_at",
    "declined_at",
    "withdrawn_at",
    "invalidated_at",
    "decline_blocked",
)


@admin.register(CatchRequest)
class CatchRequestAdmin(CatchRequestAdminBase):
    """Find and inspect catch requests, and invalidate one (#507).

    Operators see the stored state, including ``invalidated``. No admin path can
    approve, decline, undo, restore, add, edit, or delete a request. Cleanup
    deletes the rows after the review deadline.
    """

    form = CatchRequestAdminForm
    fields = (*_REQUEST_FIELDS, "invalidate")
    readonly_fields = _REQUEST_FIELDS
    list_display = (
        "id",
        "player",
        "fursuit",
        "convention",
        "state",
        "requested_at",
        "decline_blocked",
    )
    list_select_related = ("player", "fursuit", "convention")
    list_filter = ("state", "convention")
    search_fields = (
        "id__exact",
        "player__id__exact",
        "fursuit__tailtag_id__exact",
        "convention__name",
    )
    ordering = ("-requested_at", "-id")
    actions = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Requests come only from player submissions."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: CatchRequest | None = None
    ) -> bool:
        """Only cleanup deletes request history."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: CatchRequest | None = None
    ) -> bool:
        return _has_permission(request, "catches.invalidate_catch_request")

    def has_view_permission(
        self, request: HttpRequest, obj: CatchRequest | None = None
    ) -> bool:
        return self.has_change_permission(request, obj) or _has_permission(
            request, "catches.view_catchrequest"
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
            permission="catches.invalidate_catch_request",
            action=OperatorAction.INVALIDATE_CATCH_REQUEST,
            target_type=OperatorTargetType.CATCH_REQUEST,
            target_id=target_id,
            handler=lambda: super(CatchRequestAdmin, self).changeform_view(
                request, object_id, form_url, extra_context
            ),
            rejected_exceptions=(PermissionDenied,),
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: CatchRequest,
        form: CatchRequestAdminForm,
        change: bool,
    ) -> None:
        """Delegate the sole permitted mutation to its lock-aware service."""
        if not change or set(form.changed_data) - {"invalidate"}:
            raise PermissionDenied
        if not form.cleaned_data["invalidate"]:
            return
        transition = invalidate_request_as_operator(request_id=obj.pk)
        updated = (
            execute_bound_operator_transition(request, lambda: transition)
            if hasattr(request, "_operator_audit_attempt")
            else transition.value
        )
        obj.state = updated.state
        obj.invalidated_at = updated.invalidated_at


@admin.register(CatchBlock)
class CatchBlockAdmin(CatchBlockAdminBase):
    """Inspect owner blocks (#507). Only the owner can remove a block."""

    fields = ("id", "player", "fursuit", "convention", "created_at")
    readonly_fields = fields
    list_display = fields
    list_select_related = ("player", "fursuit", "convention")
    list_filter = ("convention",)
    search_fields = (
        "id__exact",
        "player__id__exact",
        "fursuit__tailtag_id__exact",
        "convention__name",
    )
    ordering = ("-created_at", "-id")
    actions = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: CatchBlock | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: CatchBlock | None = None
    ) -> bool:
        return False

    def has_view_permission(
        self, request: HttpRequest, obj: CatchBlock | None = None
    ) -> bool:
        return _has_permission(request, "catches.view_catchblock")
