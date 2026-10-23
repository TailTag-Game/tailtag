"""Run one validated inspection inside the replica inspect job."""

from __future__ import annotations

from django.core.management import BaseCommand

from replica_operations import runner
from simulation_fixtures.inspection_remote import execute

JOB_NAME = "tailtag-replica-inspect"

__all__ = ["Command"]


class Command(BaseCommand):
    """Run the inspection job request and exit with its pass or fail status."""

    help = "Run one validated inspection inside the replica inspect job."
    requires_system_checks = ()

    def handle(self, *args: object, **options: object) -> None:
        """Print one JSON result line and exit 0 only for PASS."""
        raise SystemExit(
            runner.run(JOB_NAME, runner.remote_handler(execute), uses_media=False)
        )
