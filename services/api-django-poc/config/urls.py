"""Project URL configuration; application routes are registered by their apps."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from health import views as health_views

urlpatterns: list[URLPattern | URLResolver] = [
    path("health/live", health_views.live),
    path("health/ready", health_views.ready),
]
