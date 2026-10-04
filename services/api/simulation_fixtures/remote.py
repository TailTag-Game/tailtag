"""Staging-only entry point for one validated simulation fixture request."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final, cast

from simulation_fixtures import cleanup, services

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
}


def _response(result: str, data: _Data | None = None) -> dict[str, object]:
    return {"result": result, "data": data or {}}


def target_matches(
    identity: Mapping[str, object],
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
) -> bool:
    return (
        environ.get("RAILWAY_ENVIRONMENT_NAME") == "staging"
        and environ.get("RAILWAY_SERVICE_NAME") == "api"
        and identity.get("environment") == "staging"
        and isinstance(identity.get("source_sha"), str)
        and isinstance(identity.get("deployment_id"), str)
        and dict(runtime_identity) == dict(identity)
    )


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
    if not target_matches(typed_identity, runtime_identity, environ):
        return _response("FAIL_TARGET")
    operation = fields.get("operation")
    arguments = fields.get("arguments")
    if (
        frozenset(fields) != _REQUEST_KEYS
        or not isinstance(operation, str)
        or operation not in _OPERATIONS
        or not isinstance(arguments, Mapping)
    ):
        return _response("FAIL_REQUEST")
    names, run = _OPERATIONS[operation]
    typed_arguments = cast(Mapping[str, object], arguments)
    if frozenset(typed_arguments) != names:
        return _response("FAIL_REQUEST")
    try:
        result, data = run(typed_arguments)
    except ValueError:
        return _response("FAIL_REQUEST")
    return _response(result, data)
