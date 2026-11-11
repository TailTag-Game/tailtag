"""Catch confirmation, preview, request, review, and history routes."""

from __future__ import annotations

from django.urls import path

from .request_review_views import (
    OwnerRequestApproveView,
    OwnerRequestBlockView,
    OwnerRequestDeclineView,
    OwnerRequestListView,
    OwnerRequestRestoreView,
    OwnerRequestSummaryView,
    OwnerRequestUndoDeclineView,
    PlayerRequestWithdrawView,
)
from .views import (
    CatchConfirmationView,
    CatchHistoryView,
    CatchPreviewView,
    CatchRequestView,
)

urlpatterns = [
    path("", CatchHistoryView.as_view(), name="catch-history"),
    path("confirm/", CatchConfirmationView.as_view(), name="catch-confirm"),
    path("preview/", CatchPreviewView.as_view(), name="catch-preview"),
    path("requests/", CatchRequestView.as_view(), name="catch-requests"),
    path(
        "requests/<int:id>/withdraw/",
        PlayerRequestWithdrawView.as_view(),
        name="catch-request-withdraw",
    ),
    path(
        "incoming-requests/",
        OwnerRequestListView.as_view(),
        name="catch-incoming-requests",
    ),
    path(
        "incoming-requests/summary/",
        OwnerRequestSummaryView.as_view(),
        name="catch-incoming-requests-summary",
    ),
    path(
        "incoming-requests/<int:id>/approve/",
        OwnerRequestApproveView.as_view(),
        name="catch-incoming-request-approve",
    ),
    path(
        "incoming-requests/<int:id>/decline/",
        OwnerRequestDeclineView.as_view(),
        name="catch-incoming-request-decline",
    ),
    path(
        "incoming-requests/<int:id>/undo-decline/",
        OwnerRequestUndoDeclineView.as_view(),
        name="catch-incoming-request-undo-decline",
    ),
    path(
        "incoming-requests/<int:id>/restore/",
        OwnerRequestRestoreView.as_view(),
        name="catch-incoming-request-restore",
    ),
    path(
        "incoming-requests/<int:id>/block/",
        OwnerRequestBlockView.as_view(),
        name="catch-incoming-request-block",
    ),
]
