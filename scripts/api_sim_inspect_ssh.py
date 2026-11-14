"""Relay one read-only simulation inspection to the pinned Staging API instance."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Final, TextIO, cast

from scripts import api_sim_render_relay as _render_relay
from scripts import api_staging_preflight as _staging_preflight

_json_loads = _render_relay._json_loads  # pyright: ignore[reportPrivateUsage]

_MAX_REQUEST_BYTES: Final = 64 * 1024
_SSH_TIMEOUT_SECONDS: Final = 30
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
# inspect-population-v2 adds the run's catch requests, capped at 120 (#508).
_V2_OPERATION: Final = "inspect-population-v2"
_V2_MAX_REQUESTS: Final = 120
_REQUEST_ENTRY_KEYS: Final = frozenset(
    {"id", "player", "fursuit", "run_convention", "state", "requested_at"}
)
_REQUEST_STATES: Final = frozenset(
    {"pending", "approved", "declined", "withdrawn", "invalidated"}
)
_CAUGHT_AT: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z"
)
_FAILURE: Final[dict[str, object]] = {"result": "FAIL_LAUNCHER", "data": {}}

# The remote program binds to the deployed code and prints one fixed JSON
# object. Imported-code output is captured so nothing else reaches stdout.
_BOOTSTRAP: Final = r"""
import contextlib, io, json, os, sys
def _emit(result, data, instance=None):
    reply = {"result": result, "data": data}
    if instance is not None:
        reply["instance"] = instance
    sys.stdout.write(json.dumps(reply, sort_keys=True) + "\n")
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
    _emit(response["result"], response["data"], response.get("instance"))
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
    if frozenset(request) - {"expected_identity", "expected_instance"} != _REQUEST_KEYS:
        raise ValueError
    if "expected_identity" in request:
        _staging_preflight._validate_identity(  # pyright: ignore[reportPrivateUsage]
            request["expected_identity"]
        )
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


def _request_is_valid(entry: Mapping[str, object]) -> bool:
    requested_at = entry["requested_at"]
    return (
        _integer(entry["id"])
        and _integer(entry["fursuit"])
        and (entry["player"] is None or _integer(entry["player"]))
        and type(entry["run_convention"]) is bool
        and entry["state"] in _REQUEST_STATES
        and isinstance(requested_at, str)
        and _CAUGHT_AT.fullmatch(requested_at) is not None
    )


def _requests_are_valid(value: object) -> bool:
    entries = _objects(value)
    return (
        entries is not None
        and len(entries) <= _V2_MAX_REQUESTS
        and all(
            frozenset(entry) == _REQUEST_ENTRY_KEYS and _request_is_valid(entry)
            for entry in entries
        )
    )


def _validated_output(raw: str, *, requests: bool = False) -> dict[str, object]:
    """Accept one fixed shape: the v1 data keys, plus ``requests`` for v2 only."""
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
        and frozenset(typed_data)
        == (_DATA_KEYS | {"requests"} if requests else _DATA_KEYS)
        and _data_is_valid(typed_data)
        and (not requests or _requests_are_valid(typed_data["requests"]))
    )
    if not valid:
        raise ValueError
    return output


def _execute(request: dict[str, object]) -> dict[str, object]:
    requests = request["operation"] == _V2_OPERATION
    return _render_relay.execute(
        request,
        _BOOTSTRAP,
        lambda raw: _validated_output(raw, requests=requests),
        timeout=_SSH_TIMEOUT_SECONDS,
    )


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
