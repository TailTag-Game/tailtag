"""Relay one read-only simulation inspection to the pinned Staging API instance."""

from __future__ import annotations

import json
import re
import sys
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
_FAILURES: Final = frozenset(
    {
        "FAIL_REQUEST",
        "FAIL_TARGET",
        "FAIL_LEASE",
        "FAIL_RUN_UNKNOWN",
        "FAIL_LIMIT",
        "FAIL_BOOTSTRAP",
    }
)
_DATA_KEYS: Final = frozenset(
    {"catches", "fursuits", "fixture_photos_unchanged", "avatars"}
)
_CATCH_INTEGERS: Final = frozenset({"id", "fursuit"})
_CATCH_OPTIONAL_INTEGERS: Final = frozenset({"catcher", "fursuit_owner"})
_CATCH_BOOLEANS: Final = frozenset({"run_convention", "provenance", "in_window"})
_CATCH_KEYS: Final = (
    _CATCH_INTEGERS | _CATCH_OPTIONAL_INTEGERS | _CATCH_BOOLEANS | {"caught_at"}
)
_FURSUIT_KEYS: Final = frozenset({"id", "owner"})
_CAUGHT_AT: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z"
)
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
        from simulation_fixtures import inspection_remote
        response = inspection_remote.execute(request, runtime_identity=get_identity(), environ=os.environ)
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


def _integer(value: object) -> bool:
    return type(value) is int


def _objects(value: object) -> list[Mapping[str, object]] | None:
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if not all(isinstance(item, dict) for item in items):
        return None
    return cast(list[Mapping[str, object]], items)


def _catch_is_valid(catch: Mapping[str, object]) -> bool:
    caught_at = catch["caught_at"]
    return (
        all(_integer(catch[key]) for key in _CATCH_INTEGERS)
        and all(
            catch[key] is None or _integer(catch[key])
            for key in _CATCH_OPTIONAL_INTEGERS
        )
        and all(type(catch[key]) is bool for key in _CATCH_BOOLEANS)
        and isinstance(caught_at, str)
        and _CAUGHT_AT.fullmatch(caught_at) is not None
    )


def _data_is_valid(data: Mapping[str, object]) -> bool:
    catches = _objects(data["catches"])
    fursuits = _objects(data["fursuits"])
    avatars = data["avatars"]
    return (
        catches is not None
        and fursuits is not None
        and all(
            frozenset(catch) == _CATCH_KEYS and _catch_is_valid(catch)
            for catch in catches
        )
        and all(
            frozenset(fursuit) == _FURSUIT_KEYS
            and _integer(fursuit["id"])
            and _integer(fursuit["owner"])
            for fursuit in fursuits
        )
        and type(data["fixture_photos_unchanged"]) is bool
        and isinstance(avatars, list)
        and all(_integer(index) for index in cast(list[object], avatars))
    )


def _validated_output(raw: str) -> dict[str, object]:
    value = _json_loads(raw)
    if not isinstance(value, dict):
        raise TypeError
    output = cast(dict[str, object], value)
    data = output.get("data")
    if frozenset(output) != frozenset({"result", "data"}) or not isinstance(data, dict):
        raise ValueError
    typed_data = cast(dict[str, object], data)
    result = output["result"]
    valid = (
        not typed_data
        if result in _FAILURES
        else result == "PASS"
        and frozenset(typed_data) == _DATA_KEYS
        and _data_is_valid(typed_data)
    )
    if not valid:
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
