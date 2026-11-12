"""Staging-only entry point for one validated read-only simulation inspection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final, cast

from simulation_fixtures import inspection
from simulation_pool import target

_IDENTITY_KEYS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_REQUEST_KEYS: Final = frozenset({"operation", "identity", "arguments"})
_ARGUMENT_KEYS: Final = frozenset({"pool", "run_id", "identities"})
# v1 stays for simulator releases from before #508.
_OPERATIONS: Final[
    Mapping[str, Callable[[str, str, Mapping[str, int]], inspection.InspectionOutcome]]
] = {
    "inspect": inspection.inspect,
    "inspect-population-v1": inspection.inspect_population,
    "inspect-population-v2": inspection.inspect_population_v2,
}


def _response(
    result: str, data: dict[str, object] | None = None, instance: str | None = None
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
    """Run one inspection after proving this is the named Staging API.

    The request identity is checked against the runtime before anything else is
    validated or any database access happens. Every supported operation shares the same target guard.
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
    arguments = fields.get("arguments")
    if (
        frozenset(fields) - {"expected_instance"} != _REQUEST_KEYS
        or not isinstance(fields["operation"], str)
        or fields["operation"] not in _OPERATIONS
        or not isinstance(arguments, Mapping)
        or frozenset(cast(Mapping[str, object], arguments)) != _ARGUMENT_KEYS
    ):
        return _response("FAIL_REQUEST", instance=instance)
    typed_arguments = cast(Mapping[str, object], arguments)
    outcome = _OPERATIONS[fields["operation"]](
        cast(str, typed_arguments["pool"]),
        cast(str, typed_arguments["run_id"]),
        cast(Mapping[str, int], typed_arguments["identities"]),
    )
    return _response(outcome.result, outcome.data, instance)
