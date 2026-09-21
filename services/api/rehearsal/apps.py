from django.apps import AppConfig


class RehearsalConfig(AppConfig):
    """Register the guarded rehearsal reset schema."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "rehearsal"
