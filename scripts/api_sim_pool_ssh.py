"""Relay one synthetic identity pool request to the pinned Staging API instance."""

from __future__ import annotations

import json
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
_REQUEST_KEYS: Final = frozenset({"operation", "pool", "arguments"})
_RESULTS: Final = frozenset(
    {
        "PASS",
        "FAIL_REQUEST",
        "FAIL_TARGET",
        "FAIL_INSUFFICIENT",
        "FAIL_SLOT",
        "FAIL_BOOTSTRAP",
    }
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
        from simulation_pool import remote
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


def _integers(value: object) -> bool:
    if isinstance(value, list):
        return all(type(item) is int for item in cast(list[object], value))
    return type(value) is int


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
        or not all(
            isinstance(key, str) and _integers(item)
            for key, item in cast(Mapping[object, object], data).items()
        )
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
