from django.apps import AppConfig


class ReplicaOperationsConfig(AppConfig):
    """Register the replica job commands."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "replica_operations"
