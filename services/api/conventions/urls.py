"""URL routing for convention endpoints."""

from __future__ import annotations

from django.urls import path

from .views import ConventionDetailView, ConventionListView

urlpatterns = [
    path("", ConventionListView.as_view(), name="convention-list"),
    path("<int:pk>/", ConventionDetailView.as_view(), name="convention-detail"),
]
