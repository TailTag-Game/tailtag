"""Health application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class HealthConfig(AppConfig):
    """Register the health-check application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "health"
