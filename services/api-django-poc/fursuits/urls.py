"""URL routes owned by the fursuits application."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("fursuits", views.FursuitListView.as_view(), name="fursuit-list"),
    path(
        "fursuits/<uuid:fursuit_id>",
        views.FursuitDetailView.as_view(),
        name="fursuit-detail",
    ),
]
