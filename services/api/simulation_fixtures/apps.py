from django.apps import AppConfig


class SimulationFixturesConfig(AppConfig):
    """Register the Staging simulation fixture run ledger."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "simulation_fixtures"
