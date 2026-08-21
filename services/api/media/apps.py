"""Django application configuration for the media boundary."""

from django.apps import AppConfig


class MediaConfig(AppConfig):
    """Register TailTag's reusable media infrastructure."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "media"
