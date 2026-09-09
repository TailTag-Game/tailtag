"""Django application configuration for catches."""

from __future__ import annotations

from django.apps import AppConfig


class CatchesConfig(AppConfig):
    """Configure the catches application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catches"
