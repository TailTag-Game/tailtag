"""URL routing for convention and enrollment endpoints."""

from __future__ import annotations

from django.urls import path

from .views import (
    ActiveConventionView,
    ConventionDetailView,
    ConventionEnrollmentListCreateView,
    ConventionListView,
)

urlpatterns = [
    path("", ConventionListView.as_view(), name="convention-list"),
    path("<int:pk>/", ConventionDetailView.as_view(), name="convention-detail"),
    path(
        "enrollments/",
        ConventionEnrollmentListCreateView.as_view(),
        name="convention-enrollment-list-create",
    ),
    path("active/", ActiveConventionView.as_view(), name="convention-active"),
]
