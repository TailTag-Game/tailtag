"""Project URL configuration; application routes are registered by their apps."""

from __future__ import annotations

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from accounts.views import CurrentUserView
from health import views as health_views

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("api/me/", CurrentUserView.as_view(), name="current-user"),
    path("api/conventions/", include("conventions.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema", permission_classes=[AllowAny]
        ),
        name="docs",
    ),
    path("health/live", health_views.live),
    path("health/ready", health_views.ready),
]
