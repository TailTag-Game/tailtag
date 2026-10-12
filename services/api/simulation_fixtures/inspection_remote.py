"""Staging-only entry point for one validated read-only simulation inspection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from simulation_fixtures import inspection
from simulation_fixtures.remote import target_matches

_IDENTITY_KEYS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_REQUEST_KEYS: Final = frozenset({"operation", "identity", "arguments"})
_ARGUMENT_KEYS: Final = frozenset({"pool", "run_id", "identities"})


def _response(result: str, data: dict[str, object] | None = None) -> dict[str, object]:
    return {"result": result, "data": data or {}}


def execute(
    request: object,
    *,
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
) -> dict[str, object]:
    """Run one inspection after proving this is the named Staging API.

    The request identity is checked against the runtime before anything else is
    validated or any database access happens. Both supported operations share the same target guard.
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
    arguments = fields.get("arguments")
    if (
        frozenset(fields) != _REQUEST_KEYS
        or fields["operation"] not in ("inspect", "inspect-population-v1")
        or not isinstance(arguments, Mapping)
        or frozenset(cast(Mapping[str, object], arguments)) != _ARGUMENT_KEYS
    ):
        return _response("FAIL_REQUEST")
    typed_arguments = cast(Mapping[str, object], arguments)
    operation = (
        inspection.inspect_population
        if fields["operation"] == "inspect-population-v1"
        else inspection.inspect
    )
    outcome = operation(
        cast(str, typed_arguments["pool"]),
        cast(str, typed_arguments["run_id"]),
        cast(Mapping[str, int], typed_arguments["identities"]),
    )
    return _response(outcome.result, outcome.data)
