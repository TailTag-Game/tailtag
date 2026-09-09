"""Catch confirmation route."""

from __future__ import annotations

from django.urls import path

from .views import CatchConfirmationView

urlpatterns = [
    path("confirm/", CatchConfirmationView.as_view(), name="catch-confirm"),
]
