"""Django application configuration for conventions."""

from __future__ import annotations

from django.apps import AppConfig


class ConventionsConfig(AppConfig):
    """Configure the conventions application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "conventions"
