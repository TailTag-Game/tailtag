"""Owner-scoped fursuit routes."""

from __future__ import annotations

from django.urls import URLPattern, path

from fursuits.views import FursuitDetailView, FursuitListCreateView, FursuitPhotoView

fursuit_list_view = FursuitListCreateView.as_view()
fursuit_list_view.should_append_slash = False  # pyright: ignore[reportAttributeAccessIssue]

urlpatterns: list[URLPattern] = [
    path("", fursuit_list_view, name="fursuit-list"),
    path("<int:id>/", FursuitDetailView.as_view(), name="fursuit-detail"),
    path("<int:id>/photo/", FursuitPhotoView.as_view(), name="fursuit-photo"),
]
