"""Relay one simulation fixture request to the pinned Staging API instance."""

from __future__ import annotations

import json
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from typing import Final, TextIO, cast

from scripts import api_staging_reset_ssh as _reset_ssh

_target_ids = _reset_ssh._target_ids  # pyright: ignore[reportPrivateUsage]
_active_instance = _reset_ssh._active_instance  # pyright: ignore[reportPrivateUsage]
_preflight = _reset_ssh._preflight  # pyright: ignore[reportPrivateUsage]
_railway_identity = _reset_ssh._railway_identity  # pyright: ignore[reportPrivateUsage]
_run = _reset_ssh._run  # pyright: ignore[reportPrivateUsage]
_json_loads = _reset_ssh._json_loads  # pyright: ignore[reportPrivateUsage]

_MAX_REQUEST_BYTES: Final = 64 * 1024
_REQUEST_KEYS: Final = frozenset({"operation", "arguments"})
_RESULTS: Final = frozenset(
    {
        "PASS",
        "FAIL_REQUEST",
        "FAIL_TARGET",
        "FAIL_RUN_EXISTS",
        "FAIL_LEASE",
        "FAIL_DIRTY",
        "FAIL_INVARIANT",
        "FAIL_ERROR",
        "FAIL_RUN_UNKNOWN",
        "FAIL_BOOTSTRAP",
        "FAIL_ATTRIBUTION",
        "FAIL_STORAGE",
        "FAIL_VERIFY",
        "FAIL_LIMIT",
    }
)
_COUNT_KEYS: Final = frozenset(
    {
        "convention",
        "enrollment",
        "fursuit",
        "activation",
        "quarantined",
        "catch",
        "session",
        "credential",
        "image",
        "readmitted",
        "retained",
        "unfinished",
    }
)
_RUN_STATUSES: Final = frozenset({"provisioned", "failed", "retained", "cleaned"})
_LISTED_REASONS: Final = frozenset(
    {"journeys", "reconciliation", "cleanup", "interrupted", "unfinished"}
)
_LISTED_RUN_KEYS: Final = frozenset({"run_id", "pool", "reason", "age_days"})
_POOL: Final = re.compile(r"[a-z0-9]{1,12}")
# A provision near the configuration bounds stores up to 250 images remotely, so the
# SSH call needs more than the shared 30-second default. It stays below the
# simulator's 180-second launcher limit, leaving room for the preflight calls.
_SSH_TIMEOUT_SECONDS: Final = 150
_FAILURE: Final[dict[str, object]] = {"result": "FAIL_LAUNCHER", "data": {}}

# The remote program binds to the deployed code and prints one fixed JSON
# object. Imported-code output is captured so nothing else reaches stdout.
_BOOTSTRAP: Final = r"""
import contextlib, io, json, os, sys
def _emit(result, data):
    sys.stdout.write(json.dumps({"result": result, "data": data}, sort_keys=True) + "\n")
try:
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError
    request = json.loads(raw)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
        sys.path.insert(0, "/app")
        import django
        django.setup()
        from config.build_identity import get_identity
        from simulation_fixtures import remote
        response = remote.execute(request, runtime_identity=get_identity(), environ=os.environ)
    _emit(response["result"], response["data"])
except BaseException:
    _emit("FAIL_BOOTSTRAP", {})
"""


def _caller_request(stdin: TextIO) -> dict[str, object]:
    text = stdin.read(_MAX_REQUEST_BYTES + 1)
    if len(text.encode()) > _MAX_REQUEST_BYTES:
        raise ValueError
    value = _json_loads(text)
    if not isinstance(value, dict):
        raise TypeError
    request = cast(dict[str, object], value)
    if frozenset(request) != _REQUEST_KEYS:
        raise ValueError
    return request


def _counts(value: object) -> bool:
    return isinstance(value, dict) and all(
        key in _COUNT_KEYS and type(count) is int
        for key, count in cast(Mapping[object, object], value).items()
    )


def _is_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _listed_run(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    run = cast(Mapping[object, object], value)
    pool, reason, age = run.get("pool"), run.get("reason"), run.get("age_days")
    return (
        frozenset(run) == _LISTED_RUN_KEYS
        and _is_uuid(run["run_id"])
        and isinstance(pool, str)
        and _POOL.fullmatch(pool) is not None
        and isinstance(reason, str)
        and reason in _LISTED_REASONS
        and type(age) is int
        and age >= 0
    )


def _runs(value: object) -> bool:
    return isinstance(value, list) and all(
        _listed_run(run) for run in cast(list[object], value)
    )


def _data_is_valid(data: Mapping[object, object]) -> bool:
    for key, value in data.items():
        if key == "status":
            valid = isinstance(value, str) and value in _RUN_STATUSES
        elif key == "counts":
            valid = _counts(value)
        elif key == "runs":
            valid = _runs(value)
        else:
            valid = key in _COUNT_KEYS and type(value) is int
        if not valid:
            return False
    return True


def _validated_output(raw: str) -> dict[str, object]:
    value = _json_loads(raw)
    if not isinstance(value, dict):
        raise TypeError
    output = cast(dict[str, object], value)
    data = output.get("data")
    if (
        frozenset(output) != frozenset({"result", "data"})
        or output["result"] not in _RESULTS
        or not isinstance(data, dict)
        or not _data_is_valid(cast(Mapping[object, object], data))
    ):
        raise ValueError
    return output


def _execute(request: dict[str, object]) -> dict[str, object]:
    _railway_identity()
    identity = _preflight()
    project_id, environment_id, service_id, _ = _target_ids()
    instance = _active_instance(identity)
    execution = _run(
        [
            "railway",
            "ssh",
            "--project",
            project_id,
            "--service",
            service_id,
            "--environment",
            environment_id,
            "--deployment-instance",
            instance,
            "--",
            "/app/.venv/bin/python",
            "-I",
            "-c",
            _BOOTSTRAP,
        ],
        input=json.dumps({**request, "identity": identity}, separators=(",", ":")),
        timeout=_SSH_TIMEOUT_SECONDS,
    )
    if execution.returncode != 0:
        raise ValueError
    return _validated_output(execution.stdout)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Read one request from stdin and print one fixed-shape JSON response."""
    output = stdout or sys.stdout
    response: dict[str, object]
    try:
        if argv:
            raise ValueError
        response = _execute(_caller_request(stdin or sys.stdin))
    except Exception:  # noqa: BLE001
        response = dict(_FAILURE)
    output.write(json.dumps(response, sort_keys=True) + "\n")
    return 0 if response["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
