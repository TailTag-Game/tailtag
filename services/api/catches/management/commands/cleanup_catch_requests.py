"""Delete catch request history after each convention's review deadline (#507).

A Render cron job runs this command once a day at 10:00 UTC. Operators run it
again after a database restore, before the restored database serves traffic.
See docs/operations/catch-request-cleanup.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from django.core.management.base import BaseCommand, CommandError
from sentry_sdk.crons import monitor

from catches.request_cleanup import run_cleanup

if TYPE_CHECKING:
    from sentry_sdk.types import MonitorConfig

MONITOR_SLUG: Final = "catch-request-cleanup"
# Sentry creates or updates the monitor from this configuration on each run.
# A run that does not start within the margin is a missed check-in (#507 G2).
MONITOR_CONFIG: Final[MonitorConfig] = {
    "schedule": {"type": "crontab", "value": "0 10 * * *"},
    "timezone": "UTC",
    "checkin_margin": 60,
    "max_runtime": 30,
    "failure_issue_threshold": 1,
    "recovery_threshold": 1,
}


class Command(BaseCommand):
    help = "Delete catch requests and blocks after each review deadline."

    def handle(self, *args: Any, **options: Any) -> None:
        with monitor(monitor_slug=MONITOR_SLUG, monitor_config=MONITOR_CONFIG):
            result = run_cleanup()
            if not result.succeeded:
                raise CommandError(
                    "Catch request cleanup failed for "
                    f"{result.failed_conventions} convention(s). The next run retries."
                )
        self.stdout.write(
            f"Deleted {sum(result.deleted_requests.values())} catch requests and "
            f"{result.deleted_blocks} blocks."
        )
