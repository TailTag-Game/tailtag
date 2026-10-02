from django.apps import AppConfig


class SimulationPoolConfig(AppConfig):
    """Register the Staging synthetic identity pool lease store."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "simulation_pool"
