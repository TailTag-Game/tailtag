"""Apply migrations inside the pinned replica migrate job."""

from __future__ import annotations

from django.core.management import BaseCommand, call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from config.build_identity import Identity
from health.configuration import (
    _settings_module,  # pyright: ignore[reportPrivateUsage]
)
from replica_operations import runner

JOB_NAME = "tailtag-replica-migrate"
_MIGRATE_SETTINGS = "config.settings.migrate"

__all__ = ["Command"]


def _migrate(
    request: dict[str, object], identity: Identity
) -> tuple[str, dict[str, object]]:
    if request:
        return "FAIL_REQUEST", {}
    if _settings_module() != _MIGRATE_SETTINGS:
        return "FAIL_TARGET", {}
    try:
        call_command("migrate", interactive=False, verbosity=0)
        executor = MigrationExecutor(connection)
        unapplied = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    except Exception:  # noqa: BLE001
        return "FAIL_MIGRATION", {}
    if unapplied:
        return "FAIL_MIGRATION", {"unapplied": unapplied}
    return "PASS", {"unapplied": 0}


class Command(BaseCommand):
    """Run the migration job request and exit with its pass or fail status."""

    help = "Apply migrations inside the replica migrate Cloud Run job."
    requires_system_checks = ()

    def handle(self, *args: object, **options: object) -> None:
        """Print one JSON result line and exit 0 only for PASS."""
        raise SystemExit(runner.run(JOB_NAME, _migrate, uses_media=False))
