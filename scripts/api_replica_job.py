"""Run one hybrid replica Cloud Run job from the maintainer's machine (#355).

The caller picks a family (migrate, pool, fixture or inspect) and sends the
request body on stdin. The runner adds the build identity, runs the pinned job
through the Cloud Run Admin API, waits for the execution, and reads the job's
one result line from Cloud Logging. It prints that line and exits 0 only for a
`PASS` result of a succeeded execution. Every launcher failure prints one fixed
line and nothing else, so no token, project id, URL or response body escapes.

Run it with `task replica-job -- --project <gcp-project-id> --family <family>
--source-sha <40 hex>`. It needs `gcloud` signed in as a project owner.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import BinaryIO, Final, NoReturn, cast

from scripts.replica_neon_roles import (
    _PROJECT_ID,  # pyright: ignore[reportPrivateUsage]
)

REGION: Final = "us-east4"
FAILURE: Final = '{"result": "FAIL_LAUNCHER"}'
_JOBS: Final = {
    "migrate": "tailtag-replica-migrate",
    "pool": "tailtag-replica-pool",
    "fixture": "tailtag-replica-fixture",
    "inspect": "tailtag-replica-inspect",
}
_REQUEST_ENVIRONMENT: Final = "TAILTAG_JOB_REQUEST"
_MAX_REQUEST_BYTES: Final = 65_536
# Cloud Run refuses an env override value longer than this (live check, #355 AC16).
_MAX_OVERRIDE_BYTES: Final = 32_768
_MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024
_HTTP_TIMEOUT_SECONDS: Final = 30
# A cancel is a last, short attempt inside the caller's own time budget.
_CANCEL_TIMEOUT_SECONDS: Final = 10
_TOKEN_TIMEOUT_SECONDS: Final = 60
_EXECUTION_DEADLINE_SECONDS: Final = 1_200
_LOG_DEADLINE_SECONDS: Final = 120
_POLL_SECONDS: Final = 5
_TRANSIENT_RETRIES: Final = 3
_MAX_LOG_PAGES: Final = 10
_LOG_SKEW: Final = timedelta(minutes=5)
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_EXECUTION_ID: Final = re.compile(r"[a-z][a-z0-9-]{0,62}")
_TOKEN: Final = re.compile(r"[A-Za-z0-9._~+/=-]+")
_RESULT_KEYS: Final = frozenset({"result", "data", "identity"})


class Parser(argparse.ArgumentParser):
    """An argument parser that never prints: a bad command line is a launcher failure."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def valid_project(project: str) -> None:
    """Raise unless the project id has the exact expected shape."""
    if _PROJECT_ID.fullmatch(project) is None:
        raise ValueError


def valid_target(project: str, source_sha: str) -> None:
    """Raise unless the project id and source sha have the exact expected shape."""
    valid_project(project)
    if _SOURCE_SHA.fullmatch(source_sha) is None:
        raise ValueError


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError
    return dict(pairs)


def _refuse_constant(_: str) -> object:
    raise ValueError


def _object(text: str) -> dict[str, object]:
    value: object = json.loads(
        text, object_pairs_hook=_unique_pairs, parse_constant=_refuse_constant
    )
    if not isinstance(value, dict):
        raise TypeError
    return cast(dict[str, object], value)


def _body(family: str, stdin: BinaryIO) -> dict[str, object]:
    raw = stdin.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES:
        raise ValueError
    text = raw.decode("utf-8")
    if family == "migrate" and not text.strip():
        return {}
    body = _object(text)
    if family == "migrate" and body:
        raise ValueError
    if "identity" in body:
        raise ValueError
    return body


def _token() -> str:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise ValueError
    done = subprocess.run(
        [gcloud, "auth", "print-access-token"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=_TOKEN_TIMEOUT_SECONDS,
        check=False,
    )
    token = done.stdout.strip()
    if done.returncode != 0 or _TOKEN.fullmatch(token) is None:
        raise ValueError
    return token


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect())


def _call(
    token: str,
    url: str,
    body: Mapping[str, object] | None,
    timeout: float = _HTTP_TIMEOUT_SECONDS,
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **({} if body is None else {"Content-Type": "application/json"}),
        },
    )
    with _opener().open(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError
    return _object(raw.decode("utf-8"))


class _Session:
    """The bearer token and the retry rules for one runner invocation.

    A caller can pass a fixed token, as the simulator relay does (#359). A fixed
    token is never refreshed, and `gcloud` is never called for it.
    """

    def __init__(self, token: str | None = None) -> None:
        if token is not None and _TOKEN.fullmatch(token) is None:
            raise ValueError
        self._fixed = token is not None
        self._token = token if token is not None else _token()

    def call(
        self,
        url: str,
        body: Mapping[str, object] | None,
        *,
        transient: int = 0,
        deadline: float | None = None,
        timeout: float = _HTTP_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Call one URL. A 401 refreshes the token once and retries the request.

        Up to `transient` answers of 429, 5xx or a network error are retried
        while the deadline allows. Callers pass `transient=0` for `jobs:run`,
        so a failed launch is never repeated. With a deadline, no call and no
        retry wait runs past it, because each call's timeout is cut to fit.
        """
        refreshed = False
        failures = 0
        while True:
            limit = timeout
            if deadline is not None:
                limit = min(timeout, deadline - time.monotonic())
                if limit <= 0:
                    raise ValueError
            try:
                return _call(self._token, url, body, limit)
            except urllib.error.HTTPError as error:
                if error.code == 401 and not refreshed and not self._fixed:
                    refreshed = True
                    self._token = _token()
                    continue
                retryable = error.code == 429 or error.code >= 500
            except (OSError, http.client.HTTPException):
                # URLError, read timeouts, dropped connections and short reads
                # are network errors. HTTPError is handled above.
                retryable = True
            if (
                not retryable
                or failures >= transient
                or (
                    deadline is not None
                    and time.monotonic() + _POLL_SECONDS >= deadline
                )
            ):
                raise ValueError
            failures += 1
            time.sleep(_POLL_SECONDS)


def _start(
    session: _Session,
    project: str,
    job: str,
    request_value: str,
    args: Sequence[str] | None = None,
) -> str:
    """Run the pinned job and return the execution id the response names.

    `args` replaces the container arguments; only the #356 migrate drill uses it.
    """
    prefix = f"projects/{project}/locations/{REGION}/jobs/{job}"
    container: dict[str, object] = {
        "env": [{"name": _REQUEST_ENVIRONMENT, "value": request_value}]
    }
    if args is not None:
        container["args"] = list(args)
    override = {"overrides": {"containerOverrides": [container]}}
    operation = session.call(f"https://run.googleapis.com/v2/{prefix}:run", override)
    metadata = operation.get("metadata")
    name = (
        cast(dict[str, object], metadata).get("name")
        if isinstance(metadata, dict)
        else None
    )
    marker = f"{prefix}/executions/"
    if not isinstance(name, str) or not name.startswith(marker):
        raise ValueError
    execution = name[len(marker) :]
    if _EXECUTION_ID.fullmatch(execution) is None:
        raise ValueError
    return execution


def _execution_url(project: str, job: str, execution: str) -> str:
    return (
        f"https://run.googleapis.com/v2/projects/{project}/locations/{REGION}"
        f"/jobs/{job}/executions/{execution}"
    )


def _wait(
    session: _Session,
    project: str,
    job: str,
    execution: str,
    deadline: float | None = None,
) -> bool:
    """Poll until the execution completes and return whether it succeeded."""
    url = _execution_url(project, job, execution)
    if deadline is None:
        deadline = time.monotonic() + _EXECUTION_DEADLINE_SECONDS
    while True:
        state = session.call(url, None, transient=_TRANSIENT_RETRIES, deadline=deadline)
        if state.get("completionTime"):
            succeeded = state.get("succeededCount")
            return (
                type(succeeded) is int
                and succeeded == 1
                and not state.get("failedCount")
            )
        if time.monotonic() + _POLL_SECONDS >= deadline:
            raise TimeoutError
        time.sleep(_POLL_SECONDS)


def _page_payloads(listing: Mapping[str, object], execution: str) -> list[object]:
    """Return the `jsonPayload` of each entry that belongs to the execution."""
    entries = listing.get("entries", [])
    payloads: list[object] = []
    if isinstance(entries, list):
        for entry in cast(list[object], entries):
            if not isinstance(entry, dict):
                continue
            fields = cast(dict[str, object], entry)
            labels = fields.get("labels")
            if (
                isinstance(labels, dict)
                and cast(dict[str, object], labels).get(
                    "run.googleapis.com/execution_name"
                )
                == execution
                and "jsonPayload" in fields
            ):
                payloads.append(fields["jsonPayload"])
    return payloads


def _result(
    session: _Session,
    project: str,
    job: str,
    execution: str,
    since: datetime,
    *,
    resource: str | None = None,
    deadline: float | None = None,
) -> dict[str, object]:
    """Return the one result entry the execution wrote to stdout.

    `resource` names a log view to read through instead of the project.
    """
    log_filter = (
        f'resource.type="cloud_run_job" AND resource.labels.job_name="{job}"'
        f' AND labels."run.googleapis.com/execution_name"="{execution}"'
        f' AND logName="projects/{project}/logs/run.googleapis.com%2Fstdout"'
        f' AND timestamp>="{since.strftime("%Y-%m-%dT%H:%M:%SZ")}"'
    )
    query: dict[str, object] = {
        "resourceNames": [resource or f"projects/{project}"],
        "filter": log_filter,
        "orderBy": "timestamp asc",
        "pageSize": 100,
    }
    if deadline is None:
        deadline = time.monotonic() + _LOG_DEADLINE_SECONDS
    while True:
        payloads: list[object] = []
        page_token: object = None
        for _ in range(_MAX_LOG_PAGES):
            listing = session.call(
                "https://logging.googleapis.com/v2/entries:list",
                {**query, **({} if page_token is None else {"pageToken": page_token})},
                transient=_TRANSIENT_RETRIES,
                deadline=deadline,
            )
            payloads += _page_payloads(listing, execution)
            page_token = listing.get("nextPageToken") or None
            if page_token is None:
                break
            if not isinstance(page_token, str):
                raise TypeError
        else:
            raise ValueError
        if payloads:
            if len(payloads) != 1:
                raise ValueError
            payload = payloads[0]
            if (
                not isinstance(payload, dict)
                or frozenset(cast(dict[str, object], payload)) != _RESULT_KEYS
            ):
                raise ValueError
            return cast(dict[str, object], payload)
        if time.monotonic() + _POLL_SECONDS >= deadline:
            raise TimeoutError
        time.sleep(_POLL_SECONDS)


def _cancel(session: _Session, project: str, job: str, execution: str) -> None:
    """Ask Cloud Run once to cancel the execution. Errors are the caller's to treat."""
    session.call(
        f"{_execution_url(project, job, execution)}:cancel",
        {},
        timeout=_CANCEL_TIMEOUT_SECONDS,
    )


def job_request_value(source_sha: str, body: Mapping[str, object]) -> str:
    """Return the exact override value: `body` plus the build identity."""
    request = {**body, "identity": {"source_sha": source_sha, "environment": "replica"}}
    return json.dumps(request, separators=(",", ":"))


def fits_override(value: str) -> bool:
    """True when Cloud Run accepts `value` as one environment override."""
    return len(value.encode("utf-8")) <= _MAX_OVERRIDE_BYTES


def run_once(
    project: str,
    job: str,
    value: str,
    *,
    token: str,
    resource: str,
    deadline: float,
) -> tuple[bool, dict[str, object]]:
    """Run the job once with a fixed token and return (succeeded, result entry).

    Every call ends by `deadline` (a `time.monotonic` value). If the execution
    started and anything fails, including the deadline, it is cancelled once
    with a short timeout of its own, and the error is raised. A run is never
    repeated.
    """
    if not fits_override(value):
        raise ValueError
    session = _Session(token)
    since = datetime.now(UTC) - _LOG_SKEW
    execution = _start(session, project, job, value)
    try:
        succeeded = _wait(session, project, job, execution, deadline)
        payload = _result(
            session,
            project,
            job,
            execution,
            since,
            resource=resource,
            deadline=deadline,
        )
    except Exception:
        with contextlib.suppress(Exception):
            _cancel(session, project, job, execution)
        raise
    return succeeded, payload


def submit(project: str, source_sha: str, job: str, body: Mapping[str, object]) -> int:
    """Run one pinned job with `body` plus the build identity and print one JSON line."""
    try:
        # The job measures this exact string, so the cap applies to what is sent.
        value = job_request_value(source_sha, body)
        if not fits_override(value):
            raise ValueError
        session = _Session()
        since = datetime.now(UTC) - _LOG_SKEW
        execution = _start(session, project, job, value)
        succeeded = _wait(session, project, job, execution)
        payload = _result(session, project, job, execution, since)
        line = json.dumps(payload, sort_keys=True)
    except Exception:  # noqa: BLE001
        print(FAILURE)
        return 1
    print(line)
    return 0 if succeeded and payload["result"] == "PASS" else 1


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None) -> int:
    """Read a request body from stdin, run the family's job, and report its result."""
    try:
        parser = Parser(add_help=False)
        parser.add_argument("--project", required=True)
        parser.add_argument("--family", required=True, choices=sorted(_JOBS))
        parser.add_argument("--source-sha", required=True)
        arguments = parser.parse_args(argv)
        valid_target(arguments.project, arguments.source_sha)
        body = _body(arguments.family, stdin or sys.stdin.buffer)
    except Exception:  # noqa: BLE001
        print(FAILURE)
        return 1
    return submit(
        arguments.project, arguments.source_sha, _JOBS[arguments.family], body
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
