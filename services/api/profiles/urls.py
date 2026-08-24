"""Private player-profile routes."""

from __future__ import annotations

from django.urls import URLPattern, path

from profiles.views import ProfileView

urlpatterns: list[URLPattern] = [
    path("profile/", ProfileView.as_view(), name="profile-detail"),
]
