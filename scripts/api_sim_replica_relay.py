"""Relay one simulator pool, fixture or inspection request to a hybrid replica job.

The replica counterpart of the `api_sim_*_ssh` relays (#359). It takes the same
stdin request as the relay of its channel, plus a required `expected_identity`,
and prints the same one-line `{"result", "data"}` response. Instead of Railway
SSH, it runs the pinned Cloud Run job for the channel as `tt-simrelay`.

Private inputs come only from two owner-only files: `TAILTAG_REPLICA_SESSION_FILE`
holds `{"project", "host"}`, and `TAILTAG_REPLICA_TOKEN_FILE` holds one access
token that the owner minted for this session. Nothing private reaches the
output, and every launcher fault prints one fixed line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Final, NoReturn, TextIO, cast

from scripts import api_replica_job as _job
from scripts import api_sim_fixture_ssh as _fixture
from scripts import api_sim_inspect_ssh as _inspect
from scripts import api_sim_pool_ssh as _pool
from scripts import api_staging_preflight as _preflight

from config import owner_only, replica_binding

_SESSION_ENVIRONMENT: Final = "TAILTAG_REPLICA_SESSION_FILE"
_TOKEN_ENVIRONMENT: Final = "TAILTAG_REPLICA_TOKEN_FILE"
_SESSION_KEYS: Final = frozenset({"project", "host"})
_MAX_SESSION_BYTES: Final = 4096
_MAX_TOKEN_BYTES: Final = 8192
_MAX_REQUEST_BYTES: Final = 64 * 1024
# The simulator kills a relay after 180 seconds (#359 AC16). The job work ends
# by 135 seconds, and a cancel takes at most 10 more, so a cancelled job is
# reported by about 150 seconds. The rest covers `task` and `uv run` startup.
_DEADLINE_SECONDS: Final = 135
_LOG_VIEW: Final = "simrelay-job-results"
_IDENTITY_FIELDS: Final = frozenset({"source_sha", "deployment_id", "environment"})
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_REVISION: Final = re.compile(
    rf"{re.escape(replica_binding.SERVICE_NAME)}-[a-z0-9](?:[a-z0-9-]{{0,40}}[a-z0-9])?"
)
_FAILURE: Final[dict[str, object]] = {"result": "FAIL_LAUNCHER", "data": {}}


class _Answer(Exception):
    """A fixed relay result that ends the call without starting a job."""

    def __init__(self, result: str) -> None:
        super().__init__(result)
        self.result = result


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError


_CHANNELS: Final[dict[str, tuple[ModuleType, str]]] = {
    "pool": (_pool, "pool"),
    "fixture": (_fixture, "fixture"),
    "inspect": (_inspect, "inspect"),
}


def _request(channel: ModuleType, stdin: TextIO) -> dict[str, object]:
    """Read the caller request: the channel's keys plus `expected_identity`."""
    text = stdin.read(_MAX_REQUEST_BYTES + 1)
    if len(text.encode()) > _MAX_REQUEST_BYTES:
        raise ValueError
    value: object = _pool._json_loads(text)  # pyright: ignore[reportPrivateUsage]
    if not isinstance(value, dict):
        raise TypeError
    request = cast(dict[str, object], value)
    keys = cast(frozenset[str], channel._REQUEST_KEYS)  # pyright: ignore[reportPrivateUsage]
    if frozenset(request) != keys | {"expected_identity"}:
        raise ValueError
    _identity(request["expected_identity"])
    return request


def _identity(value: object) -> dict[str, str]:
    """Return a replica service identity, or raise for any other shape."""
    if not isinstance(value, dict) or frozenset(value) != _IDENTITY_FIELDS:
        raise ValueError
    identity = cast(dict[str, object], value)
    source_sha = identity["source_sha"]
    deployment_id = identity["deployment_id"]
    if (
        not isinstance(source_sha, str)
        or _SOURCE_SHA.fullmatch(source_sha) is None
        or not isinstance(deployment_id, str)
        or _REVISION.fullmatch(deployment_id) is None
        or identity["environment"] != "replica"
    ):
        raise ValueError
    return cast(dict[str, str], identity)


def _private(variable: str, max_bytes: int) -> str:
    path = os.environ.get(variable)
    if not path:
        raise ValueError
    with owner_only.open_owner_only_file(Path(path), max_bytes=max_bytes) as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError
    return raw.decode("utf-8")


def _session() -> tuple[str, str]:
    """Return the private project and the pinned host from the session file."""
    raw = _private(_SESSION_ENVIRONMENT, _MAX_SESSION_BYTES)
    value: object = _pool._json_loads(raw)  # pyright: ignore[reportPrivateUsage]
    if not isinstance(value, dict) or frozenset(value) != _SESSION_KEYS:
        raise ValueError
    session = cast(dict[str, object], value)
    project, host = session["project"], session["host"]
    if not isinstance(project, str) or not isinstance(host, str):
        raise TypeError
    _job.valid_project(project)
    return project, replica_binding.validate_run_app_host([host])


def _token() -> str:
    # One trailing line end is allowed, in POSIX or Windows form.
    token = _private(_TOKEN_ENVIRONMENT, _MAX_TOKEN_BYTES)
    token = token.removesuffix("\n").removesuffix("\r")
    if _job._TOKEN.fullmatch(token) is None:  # pyright: ignore[reportPrivateUsage]
        raise ValueError
    return token


def _public_identity(
    host: str, fetch: Callable[[str], object] | None = None
) -> dict[str, str]:
    """Read identity, readiness and identity again from the public service host."""
    read = fetch or _preflight._fetch_json  # pyright: ignore[reportPrivateUsage]
    origin = f"https://{host}"
    first = _identity(read(f"{origin}/health/identity"))
    if read(f"{origin}/health/ready") != {"status": "ok"}:
        raise ValueError
    if _identity(read(f"{origin}/health/identity")) != first:
        raise _Answer("FAIL_TARGET")
    return first


def _execute(channel_name: str, stdin: TextIO) -> dict[str, object]:
    deadline = time.monotonic() + _DEADLINE_SECONDS
    channel, family = _CHANNELS[channel_name]
    try:
        request = _request(channel, stdin)
    except (TypeError, ValueError):
        return {"result": "FAIL_REQUEST", "data": {}}
    project, host = _session()
    token = _token()
    expected = cast(dict[str, str], request.pop("expected_identity"))
    try:
        observed = _public_identity(host)
    except _preflight.TargetSafetyError:
        raise ValueError from None
    if observed != expected:
        return {"result": "FAIL_TARGET", "data": {}}
    value = _job.job_request_value(expected["source_sha"], request)
    if not _job.fits_override(value):
        return {"result": "FAIL_REQUEST", "data": {}}
    job = cast(str, _job._JOBS[family])  # pyright: ignore[reportPrivateUsage]
    resource = f"projects/{project}/locations/global/buckets/_Default/views/{_LOG_VIEW}"
    succeeded, payload = _job.run_once(
        project, job, value, token=token, resource=resource, deadline=deadline
    )
    claimed = payload.get("identity")
    if (
        not isinstance(claimed, dict)
        or cast(dict[str, object], claimed).get("source_sha") != expected["source_sha"]
        or cast(dict[str, object], claimed).get("environment") != "replica"
        # A job prints PASS before it exits, so a failed execution voids it.
        or (payload["result"] == "PASS" and not succeeded)
    ):
        raise ValueError
    validate = cast(
        Callable[[str], dict[str, object]],
        channel._validated_output,  # pyright: ignore[reportPrivateUsage]
    )
    return validate(json.dumps({"result": payload["result"], "data": payload["data"]}))


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Read one request from stdin and print one fixed-shape JSON response."""
    output = stdout or sys.stdout
    response: Mapping[str, object]
    try:
        parser = _Parser(add_help=False)
        parser.add_argument("--channel", required=True, choices=sorted(_CHANNELS))
        arguments = parser.parse_args(list(argv or ()))
        response = _execute(arguments.channel, stdin or sys.stdin)
    except _Answer as answer:
        response = {"result": answer.result, "data": {}}
    except Exception:  # noqa: BLE001
        response = dict(_FAILURE)
    output.write(json.dumps(response, sort_keys=True) + "\n")
    return 0 if response["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
