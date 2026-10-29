"""Staging-only entry point for one validated pool request."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Final, cast

from simulation_pool import services

_IDENTITY_KEYS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_REQUEST_KEYS: Final = frozenset({"operation", "pool", "identity", "arguments"})

_Data = dict[str, object]
_Operation = Callable[[str, Mapping[str, object]], _Data]

_OPERATIONS: Final[dict[str, tuple[frozenset[str], _Operation]]] = {
    "register": (
        frozenset({"size"}),
        lambda pool, a: {"created": services.register(pool, cast(int, a["size"]))},
    ),
    "allocate": (
        frozenset({"run_id", "count", "ttl_seconds"}),
        lambda pool, a: {
            "indexes": list(
                services.allocate(
                    pool,
                    cast(str, a["run_id"]),
                    cast(int, a["count"]),
                    cast(int, a["ttl_seconds"]),
                )
            )
        },
    ),
    "heartbeat": (
        frozenset({"run_id", "ttl_seconds"}),
        lambda pool, a: {
            "extended": services.heartbeat(
                pool, cast(str, a["run_id"]), cast(int, a["ttl_seconds"])
            )
        },
    ),
    "release": (
        frozenset({"run_id"}),
        lambda pool, a: {"released": services.release(pool, cast(str, a["run_id"]))},
    ),
    "quarantine": (
        frozenset({"index", "run_id"}),
        lambda pool, a: (
            services.quarantine(pool, cast(int, a["index"]), cast(str, a["run_id"]))
            or {}
        ),
    ),
    "readmit": (
        frozenset({"index"}),
        lambda pool, a: services.readmit(pool, cast(int, a["index"])) or {},
    ),
    "status": (
        frozenset(),
        lambda pool, a: dataclasses.asdict(services.status(pool)),
    ),
}


def _response(result: str, data: _Data | None = None) -> dict[str, object]:
    return {"result": result, "data": data or {}}


def _target_matches(
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
    """Run one pool operation after proving this is the named Staging API.

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
    if not _target_matches(typed_identity, runtime_identity, environ):
        return _response("FAIL_TARGET")
    operation = fields.get("operation")
    arguments = fields.get("arguments")
    pool = fields.get("pool")
    if (
        frozenset(fields) != _REQUEST_KEYS
        or not isinstance(operation, str)
        or operation not in _OPERATIONS
        or not isinstance(pool, str)
        or not isinstance(arguments, Mapping)
    ):
        return _response("FAIL_REQUEST")
    names, run = _OPERATIONS[operation]
    typed_arguments = cast(Mapping[str, object], arguments)
    if frozenset(typed_arguments) != names:
        return _response("FAIL_REQUEST")
    try:
        return _response("PASS", run(pool, typed_arguments))
    except ValueError:
        return _response("FAIL_REQUEST")
    except services.InsufficientPool as shortage:
        return _response("FAIL_INSUFFICIENT", {"available": shortage.available})
    except (services.SlotNotLeased, services.UnknownSlot):
        return _response("FAIL_SLOT")
