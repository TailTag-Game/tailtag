"""Django application configuration for player profiles."""

from __future__ import annotations

from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    """Configure the player profiles application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "profiles"
