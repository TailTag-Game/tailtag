"""Operator administration and correction for Catch records."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse

from conventions.catch_credential_protocol import CATCH_CREDENTIAL_TOKEN_PATTERN

from .models import Catch
from .services import remove_catch_as_operator

_SENSITIVE_CREDENTIAL_SEARCH_PATTERN = re.compile(
    CATCH_CREDENTIAL_TOKEN_PATTERN, re.ASCII
)
REDACTED_CREDENTIAL_SEARCH_QUERY = "__tailtag_admin_credential_query_redacted__"
_REDACTED_CREDENTIAL_SEARCH_QUERY = REDACTED_CREDENTIAL_SEARCH_QUERY

if TYPE_CHECKING:
    CatchAdminBase = admin.ModelAdmin[Catch]
else:
    CatchAdminBase = admin.ModelAdmin


@admin.register(Catch)
class CatchAdmin(CatchAdminBase):
    """Admin interface for operator inspection and safe removal of catches."""

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
        return self.has_delete_permission(request, obj)

    def delete_model(self, request: HttpRequest, obj: Catch) -> None:
        del request
        remove_catch_as_operator(catch_id=obj.pk)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Catch]) -> None:
        del request, queryset
        raise PermissionDenied("Bulk catch deletion is not permitted.")

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
