"""Admit and run one replica job command, printing one fixed-shape JSON line."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Final, cast

from django.conf import settings

from config import build_identity, replica_binding

_REQUEST_ENVIRONMENT: Final = "TAILTAG_JOB_REQUEST"
_MAX_REQUEST_BYTES: Final = 65_536
_REQUEST_IDENTITY_KEYS: Final = frozenset({"source_sha", "environment"})

Handler = Callable[
    [dict[str, object], build_identity.Identity], tuple[str, dict[str, object]]
]
RemoteExecute = Callable[..., dict[str, object]]


class _RefusedRequest(Exception):
    """The request text is not one acceptable JSON object."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise _RefusedRequest
    return dict(pairs)


def _refuse_constant(_: str) -> object:
    raise _RefusedRequest


def _read_request() -> dict[str, object]:
    text = os.environ.get(_REQUEST_ENVIRONMENT)
    if text is None:
        raise _RefusedRequest
    try:
        if len(text.encode("utf-8")) > _MAX_REQUEST_BYTES:
            raise _RefusedRequest
        value: object = json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_refuse_constant
        )
    except (UnicodeError, ValueError, RecursionError):
        raise _RefusedRequest from None
    if not isinstance(value, dict):
        raise _RefusedRequest
    return cast(dict[str, object], value)


def remote_handler(execute: RemoteExecute) -> Handler:
    """Adapt a remote module's `execute` to the runner handler shape."""

    def handle(
        request: dict[str, object], identity: build_identity.Identity
    ) -> tuple[str, dict[str, object]]:
        response = execute(
            {**request, "identity": dict(identity)},
            runtime_identity=identity,
            environ=os.environ,
        )
        return cast(str, response["result"]), cast(dict[str, object], response["data"])

    return handle


def _admit(job_name: str) -> tuple[build_identity.Identity | None, str | None]:
    """Return the runtime identity (when it loaded) and a failure result, if any."""
    try:
        target = replica_binding.read_cloud_run_target(os.environ)
        if target is None or target.kind != "job" or target.name != job_name:
            return None, "FAIL_TARGET"
        identity = build_identity.get_identity()
    except ValueError:
        return None, "FAIL_TARGET"
    if (
        identity["environment"] != "replica"
        or identity["source_sha"] is None
        or identity["deployment_id"] != target.deployment_id
    ):
        return identity, "FAIL_TARGET"
    return identity, None


def _validate_data_targets(uses_media: bool) -> bool:
    database = cast(Mapping[str, object], settings.DATABASES["default"])
    try:
        if uses_media:
            replica_binding.validate_data_targets(
                database, settings.MEDIA_STORAGE_CONFIGURATION
            )
        else:
            replica_binding.validate_database_target(database)
    except (replica_binding.ReplicaBindingError, AttributeError, KeyError, TypeError):
        return False
    return True


def _execute(
    job_name: str, handler: Handler, uses_media: bool
) -> tuple[str, dict[str, object], build_identity.Identity | None]:
    identity, failure = _admit(job_name)
    if failure is not None or identity is None:
        return failure or "FAIL_TARGET", {}, identity
    try:
        request = _read_request()
    except _RefusedRequest:
        return "FAIL_REQUEST", {}, identity
    claimed = request.pop("identity", None)
    if not isinstance(claimed, dict) or (
        frozenset(cast(dict[str, object], claimed)) != _REQUEST_IDENTITY_KEYS
    ):
        return "FAIL_REQUEST", {}, identity
    claims = cast(dict[str, object], claimed)
    if (
        claims["source_sha"] != identity["source_sha"]
        or claims["environment"] != identity["environment"]
        or not _validate_data_targets(uses_media)
    ):
        return "FAIL_TARGET", {}, identity
    try:
        result, data = handler(request, identity)
        if not isinstance(result, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError
        json.dumps(data)
    except Exception:  # noqa: BLE001
        return "FAIL_EXECUTION", {}, identity
    return result, data, identity


def run(job_name: str, handler: Handler, *, uses_media: bool) -> int:
    """Admit the pinned job, run its handler and print the one result line."""
    result, data = "FAIL_EXECUTION", {}
    runtime_identity: build_identity.Identity | None = None
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            result, data, runtime_identity = _execute(job_name, handler, uses_media)
    except Exception:  # noqa: BLE001, S110
        pass
    sys.stdout.write(
        json.dumps(
            {"result": result, "data": data, "identity": runtime_identity},
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if result == "PASS" else 1
