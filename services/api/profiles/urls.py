"""Private player-profile routes."""

from __future__ import annotations

from django.urls import URLPattern, path

from profiles.views import ProfileAvatarView, ProfileView

urlpatterns: list[URLPattern] = [
    path("profile/", ProfileView.as_view(), name="profile-detail"),
    path("profile/avatar/", ProfileAvatarView.as_view(), name="profile-avatar"),
]
