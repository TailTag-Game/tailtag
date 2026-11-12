"""Staging-only entry point for one validated simulation fixture request."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final, cast

from simulation_fixtures import cleanup, services
from simulation_pool import target

_IDENTITY_KEYS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_REQUEST_KEYS: Final = frozenset({"operation", "identity", "arguments"})

_Data = dict[str, object]
_Operation = Callable[[Mapping[str, object]], tuple[str, _Data]]


def _provision(arguments: Mapping[str, object]) -> tuple[str, _Data]:
    outcome = services.provision(
        cast(str, arguments["pool"]),
        cast(str, arguments["run_id"]),
        cast(list[int], arguments["owners"]),
        cast(list[int], arguments["catchers"]),
        cast(int, arguments["fursuits_per_owner"]),
        cast(list[int], arguments["extras"]),
        cast(int | None, arguments.get("review_deadline_offset_seconds")),
    )
    return outcome.result, dict(outcome.counts)


def _status(arguments: Mapping[str, object]) -> tuple[str, _Data]:
    report = services.status(cast(str, arguments["run_id"]))
    if report is None:
        return "FAIL_RUN_UNKNOWN", {}
    return "PASS", {"status": report.status, "counts": dict(report.counts)}


def _cleanup(arguments: Mapping[str, object]) -> tuple[str, _Data]:
    outcome = cleanup.cleanup(
        cast(str, arguments["pool"]), cast(str, arguments["run_id"])
    )
    return outcome.result, dict(outcome.data)


def _retain(arguments: Mapping[str, object]) -> tuple[str, _Data]:
    outcome = cleanup.retain(
        cast(str, arguments["pool"]),
        cast(str, arguments["run_id"]),
        cast(str, arguments["reason"]),
    )
    return outcome.result, dict(outcome.data)


def _retained(_arguments: Mapping[str, object]) -> tuple[str, _Data]:
    outcome = cleanup.retained()
    return outcome.result, dict(outcome.data)


def _retained_counts(_arguments: Mapping[str, object]) -> tuple[str, _Data]:
    outcome = cleanup.retained_counts()
    return outcome.result, dict(outcome.data)


_OPERATIONS: Final[dict[str, tuple[frozenset[str], _Operation]]] = {
    "provision": (
        frozenset(
            {"pool", "run_id", "owners", "catchers", "fursuits_per_owner", "extras"}
        ),
        _provision,
    ),
    "status": (frozenset({"run_id"}), _status),
    "cleanup": (frozenset({"pool", "run_id"}), _cleanup),
    "retain": (frozenset({"pool", "run_id", "reason"}), _retain),
    "retained": (frozenset[str](), _retained),
    "retained_counts": (frozenset[str](), _retained_counts),
}


# Older simulator releases omit these, so they stay optional (#508).
_OPTIONAL_ARGUMENTS: Final[dict[str, frozenset[str]]] = {
    "provision": frozenset({"review_deadline_offset_seconds"}),
}


def _response(
    result: str, data: _Data | None = None, instance: str | None = None
) -> dict[str, object]:
    response: dict[str, object] = {"result": result, "data": data or {}}
    if instance is not None:
        response["instance"] = instance
    return response


def execute(
    request: object,
    *,
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
) -> dict[str, object]:
    """Run one fixture operation after proving this is the named Staging API.

    The request identity is checked against the runtime before anything else is
    validated or any database access happens. Outputs carry fixed result codes
    and counts only.
    """
    if not isinstance(request, Mapping):
        return _response("FAIL_REQUEST")
    fields = cast(Mapping[str, object], request)
    identity = fields.get("identity")
    if not isinstance(identity, Mapping):
        return _response("FAIL_REQUEST")
    typed_identity = cast(Mapping[str, object], identity)
    if frozenset(typed_identity) != _IDENTITY_KEYS:
        return _response("FAIL_REQUEST")
    try:
        instance = target.check(
            typed_identity, runtime_identity, environ, fields.get("expected_instance")
        )
    except target.TargetRefused:
        return _response("FAIL_TARGET")
    operation = fields.get("operation")
    arguments = fields.get("arguments")
    if (
        frozenset(fields) - {"expected_instance"} != _REQUEST_KEYS
        or not isinstance(operation, str)
        or operation not in _OPERATIONS
        or not isinstance(arguments, Mapping)
    ):
        return _response("FAIL_REQUEST", instance=instance)
    names, run = _OPERATIONS[operation]
    typed_arguments = cast(Mapping[str, object], arguments)
    if (
        frozenset(typed_arguments) - _OPTIONAL_ARGUMENTS.get(operation, frozenset())
        != names
    ):
        return _response("FAIL_REQUEST", instance=instance)
    try:
        result, data = run(typed_arguments)
    except ValueError:
        return _response("FAIL_REQUEST", instance=instance)
    return _response(result, data, instance)
