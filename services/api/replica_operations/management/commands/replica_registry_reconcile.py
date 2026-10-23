"""Compare the private reset facts with the registry inside the replica job."""

from __future__ import annotations

from typing import cast

from django.core.management import BaseCommand

from config.build_identity import Identity
from rehearsal import registry_reconciliation
from replica_operations import runner

JOB_NAME = "tailtag-replica-registry-reconcile"

__all__ = ["Command"]


def _reconcile(
    request: dict[str, object], identity: Identity
) -> tuple[str, dict[str, object]]:
    response = registry_reconciliation.run_request(
        {**request, "identity": dict(identity)}
    )
    return cast(str, response["result"]), {"checks": response["checks"]}


class Command(BaseCommand):
    """Run the registry reconciliation job request and exit with its status."""

    help = "Compare the private reset facts with the registry in the replica job."
    requires_system_checks = ()

    def handle(self, *args: object, **options: object) -> None:
        """Print one JSON result line and exit 0 only for PASS."""
        raise SystemExit(runner.run(JOB_NAME, _reconcile, uses_media=False))
