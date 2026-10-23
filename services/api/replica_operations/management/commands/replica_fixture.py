"""Run one validated fixture request inside the replica fixture job."""

from __future__ import annotations

from django.core.management import BaseCommand

from replica_operations import runner
from simulation_fixtures.remote import execute

JOB_NAME = "tailtag-replica-fixture"

__all__ = ["Command"]


class Command(BaseCommand):
    """Run the fixture job request and exit with its pass or fail status."""

    help = "Run one validated fixture request inside the replica fixture job."
    requires_system_checks = ()

    def handle(self, *args: object, **options: object) -> None:
        """Print one JSON result line and exit 0 only for PASS."""
        raise SystemExit(
            runner.run(JOB_NAME, runner.remote_handler(execute), uses_media=True)
        )
