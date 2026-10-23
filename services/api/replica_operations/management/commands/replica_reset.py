"""Run the guarded replica baseline reset or provision inside its pinned job."""

from __future__ import annotations

from typing import Final, cast

from django.core.management import BaseCommand

from config.build_identity import Identity
from rehearsal import procedure, replica_preflight, reset, safety
from replica_operations import runner

JOB_NAME = "tailtag-replica-reset"
_CONFIRMATIONS: Final = {
    "reset": "reset-tailtag-replica",
    "provision": "provision-tailtag-replica-reset",
}
_REQUEST_KEYS: Final = frozenset({"operation", "confirm", "configuration"})
_FAILURES: Final = {
    "preflight": "FAIL_PREFLIGHT",
    "configuration": "FAIL_CONFIGURATION",
    "provision": "FAIL_PROVISION",
    "maintenance unknown": "FAIL_MAINTENANCE_UNKNOWN",
    "maintenance retained": "FAIL_MAINTENANCE_RETAINED",
    "committed maintenance retained": "FAIL_COMMITTED_MAINTENANCE_RETAINED",
}

__all__ = ["Command"]


def _configuration(request: dict[str, object]) -> safety.ResetConfiguration:
    values = request.get("configuration")
    if not isinstance(values, dict) or not all(
        isinstance(value, str) for value in cast(dict[str, object], values).values()
    ):
        raise safety.ResetSafetyError
    return safety.load_replica_configuration(cast(dict[str, str], values))


def _reset(
    request: dict[str, object], identity: Identity
) -> tuple[str, dict[str, object]]:
    del identity
    operation = request.get("operation")
    if (
        not isinstance(operation, str)
        or operation not in _CONFIRMATIONS
        or not set(request) <= _REQUEST_KEYS
    ):
        return "FAIL_REQUEST", {}
    if request.get("confirm") != _CONFIRMATIONS[operation]:
        return "FAIL_CONFIRMATION", {}
    outcome = procedure.run(
        provision=operation == "provision",
        preflight=replica_preflight.validate_target,
        load_configuration=lambda: _configuration(request),
        maintenance=lambda configuration: safety.DatabaseMaintenance(configuration),
        reset_baseline=lambda configuration: reset.reset_baseline(configuration),
        provision_identity=lambda configuration: reset.provision_identity(
            configuration
        ),
    )
    if outcome.failure is not None:
        return _FAILURES[outcome.failure], {}
    if operation == "provision":
        return "PASS", {"provisioned": 1}
    return "PASS", {
        "baseline_version": outcome.baseline_version,
        "counts": outcome.counts,
    }


class Command(BaseCommand):
    """Run the replica reset job request and exit with its status."""

    help = "Provision or reset the replica rehearsal baseline inside its pinned job."
    requires_system_checks = ()

    def handle(self, *args: object, **options: object) -> None:
        """Print one JSON result line and exit 0 only for PASS."""
        raise SystemExit(runner.run(JOB_NAME, _reset, uses_media=True))
