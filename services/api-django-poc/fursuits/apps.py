"""Django application configuration for fursuits."""

from __future__ import annotations

from django.apps import AppConfig


class FursuitsConfig(AppConfig):
    """Configure the fursuit application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "fursuits"
