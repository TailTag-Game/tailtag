"""Catch confirmation route."""

from __future__ import annotations

from django.urls import path

from .views import CatchConfirmationView, CatchHistoryView

urlpatterns = [
    path("", CatchHistoryView.as_view(), name="catch-history"),
    path("confirm/", CatchConfirmationView.as_view(), name="catch-confirm"),
]
