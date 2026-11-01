"""Start one guarded #204 Staging operation as a Render Staging job (#410).

The operations are the reset and the sentinel provision, which need their
exact confirmation, and the read-only registry reconcile, operator inspect,
emergency operator state, and row counts.

The launcher makes every target check before and after the job, starts exactly
one job, and prints the one result line that the job writes to the Render Logs
API. It exits 0 only for a consistent PASS. It never retries or cancels a job,
because a reset can stop between its gate and its resume.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NoReturn, cast

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts import api_staging_preflight
from scripts import api_staging_render_promote as promote
from scripts.api_staging_operator_inspect import STATUS_CODES
from scripts.api_staging_promote import (
    _SOURCE_SHA,  # pyright: ignore[reportPrivateUsage]
    _mapping,  # pyright: ignore[reportPrivateUsage]
)
from scripts.api_staging_registry_reconcile import (
    _valid_output,  # pyright: ignore[reportPrivateUsage]
)
from scripts.api_staging_reset_ssh import (
    _EXPECTED_COUNTS,  # pyright: ignore[reportPrivateUsage]
)

from rehearsal import row_counts

_RECEIPTS: Path = _REPOSITORY_ROOT / "docs/development/staging-deployments"
_RESULT_PREFIX: Final = "TAILTAG-RENDER-JOB "
_CONFIRMATIONS: Final = {
    "reset": "reset-tailtag-staging",
    "provision": "provision-tailtag-staging-reset",
}
_READ_ONLY: Final = ("reconcile", "inspect", "emergency-state", "row-counts")
_EMERGENCY_STATES: Final = frozenset(
    {"ABSENT", "READY", "DECOMMISSIONED", "MISMATCH", "INDETERMINATE", "FAIL_BINDING"}
)
_VALID_EMERGENCY_STATES: Final = frozenset({"ABSENT", "READY", "DECOMMISSIONED"})
_DEPLOY_ID: Final = re.compile(r"dep-[a-z0-9]{1,60}")
_JOB_ID: Final = re.compile(r"job-[0-9a-z]{20}")
_OWNER_ID: Final = re.compile(r"tea-[a-z0-9]{1,60}")
_CAPTURED_AT: Final = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z")
_PENDING: Final = frozenset({"pending", "running"})
# The reset gate holds the database closed, so a job normally ends in minutes.
_JOB_DEADLINE_SECONDS: Final = 20 * 60
_JOB_POLL_SECONDS: Final = 5
# The Logs API can show a line some seconds after the job has ended.
_LOG_DEADLINE_SECONDS: Final = 2 * 60
_LOG_POLL_SECONDS: Final = 5
_LOG_PAGES: Final = 50
# Render keeps an old instance serving for up to 300 seconds after a restart.
_SETTLE_DEADLINE_SECONDS: Final = 5 * 60
_SETTLE_POLL_SECONDS: Final = 10
_FAIL_PHASES: Final = frozenset(
    {
        "target",
        "configuration",
        "provision",
        "maintenance unknown",
        "maintenance retained",
        "committed maintenance retained",
    }
)

_Target = tuple[str, str, str]


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("arguments invalid")


class _Indeterminate(Exception):
    """The job may have run, but its result cannot be proved."""


class JobFailure(Exception):
    """A job's result is unknown. The phase names the job when Render made one."""

    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("render observation invalid")
    return cast(list[object], value)


def _target(key: str, service_id: str) -> _Target:
    """Return the workspace, live deploy, and source SHA that Staging serves."""
    service = _mapping(promote._get(key, f"/services/{service_id}"))  # pyright: ignore[reportPrivateUsage]
    owner_id = service.get("ownerId") if service else None
    if not isinstance(owner_id, str) or _OWNER_ID.fullmatch(owner_id) is None:
        raise ValueError("render workspace invalid")
    live = _list(
        promote._get(key, f"/services/{service_id}/deploys?status=live&limit=20")  # pyright: ignore[reportPrivateUsage]
    )
    entry = _mapping(live[0]) if len(live) == 1 else None
    deploy = _mapping(entry.get("deploy")) if entry else None
    commit = _mapping(deploy.get("commit")) if deploy else None
    deploy_id = deploy.get("id") if deploy else None
    source_sha = commit.get("id") if commit else None
    if (
        deploy is None
        or deploy.get("status") != "live"
        or not isinstance(deploy_id, str)
        or _DEPLOY_ID.fullmatch(deploy_id) is None
        or not isinstance(source_sha, str)
        or _SOURCE_SHA.fullmatch(source_sha) is None
    ):
        raise ValueError("live deploy invalid")
    receipt = _mapping(json.loads((_RECEIPTS / f"{deploy_id}.json").read_text()))
    if receipt is None or not (
        receipt.get("deployment_id") == deploy_id
        and receipt.get("source_sha") == source_sha
        and receipt.get("environment") == "staging"
        and receipt.get("overall_outcome") == "SUCCEEDED"
        and receipt.get("final_active_state") == "ACTIVE"
    ):
        raise ValueError("deploy receipt invalid")
    api_staging_preflight.validate_render_staging_target(source_sha)
    instances = _list(promote._get(key, f"/services/{service_id}/instances"))  # pyright: ignore[reportPrivateUsage]
    instance = _mapping(instances[0]) if len(instances) == 1 else None
    if instance is None or not isinstance(instance.get("id"), str):
        raise ValueError("instance invalid")
    return owner_id, deploy_id, source_sha


def _start(key: str, service_id: str, command: str) -> tuple[str, str]:
    status, payload = promote._render(  # pyright: ignore[reportPrivateUsage]
        key, "POST", f"/services/{service_id}/jobs", {"startCommand": command}
    )
    job = _mapping(payload)
    job_id = job.get("id") if job else None
    created_at = job.get("createdAt") if job else None
    if (
        status != 201
        or job is None
        or not isinstance(job_id, str)
        or _JOB_ID.fullmatch(job_id) is None
        or job.get("serviceId") != service_id
        or job.get("startCommand") != command
        or not isinstance(created_at, str)
    ):
        raise ValueError("job submission indeterminate")
    return job_id, created_at


def _wait(key: str, service_id: str, job_id: str) -> str:
    deadline = time.monotonic() + _JOB_DEADLINE_SECONDS
    while True:
        job = _mapping(promote._get(key, f"/services/{service_id}/jobs/{job_id}"))  # pyright: ignore[reportPrivateUsage]
        if job is None or job.get("id") != job_id:
            raise _Indeterminate
        status = job.get("status")
        if status in {"succeeded", "failed", "canceled"}:
            return cast(str, status)
        if status not in _PENDING or time.monotonic() >= deadline:
            raise _Indeterminate
        time.sleep(_JOB_POLL_SECONDS)


def _result_lines(key: str, owner_id: str, job_id: str, created_at: str) -> list[str]:
    """Read every log line of the job and keep the lines with the result prefix."""
    window = {
        "startTime": created_at,
        "endTime": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    lines: list[str] = []
    for _ in range(_LOG_PAGES):
        query = urllib.parse.urlencode(
            {
                "ownerId": owner_id,
                "resource": job_id,
                **window,
                "direction": "forward",
                "limit": 100,
            }
        )
        page = _mapping(promote._get(key, f"/logs?{query}"))  # pyright: ignore[reportPrivateUsage]
        if page is None:
            raise _Indeterminate
        for item in _list(page.get("logs")):
            entry = _mapping(item)
            message = entry.get("message") if entry else None
            if not isinstance(message, str):
                raise _Indeterminate
            if message.startswith(_RESULT_PREFIX):
                lines.append(message)
        if page.get("hasMore") is not True:
            return lines
        start, end = page.get("nextStartTime"), page.get("nextEndTime")
        if not isinstance(start, str) or not isinstance(end, str):
            raise _Indeterminate
        window = {"startTime": start, "endTime": end}
    raise _Indeterminate


def _result_line(key: str, owner_id: str, job_id: str, created_at: str) -> str:
    deadline = time.monotonic() + _LOG_DEADLINE_SECONDS
    while True:
        lines = _result_lines(key, owner_id, job_id, created_at)
        if len(lines) == 1:
            return lines[0]
        if lines or time.monotonic() >= deadline:
            raise _Indeterminate
        time.sleep(_LOG_POLL_SECONDS)


def _outcome(line: str, operation: str, source_sha: str) -> str:
    """Return PASS or FAIL for a well-formed result line of this exact job."""
    result = _mapping(json.loads(line.removeprefix(_RESULT_PREFIX)))
    if result is None or result.get("operation") != operation:
        raise _Indeterminate
    if result.get("outcome") == "FAIL" and "phase" in result:
        if set(result) != {"operation", "outcome", "phase"} or (
            result.get("phase") not in _FAIL_PHASES
        ):
            raise _Indeterminate
        return "FAIL"
    if result.get("source_sha") != source_sha:
        raise _Indeterminate
    common = {"operation", "outcome", "source_sha"}
    if operation in _READ_ONLY:
        return _read_only_outcome(result, operation)
    if operation == "reset":
        valid = (
            set(result) == common | {"baseline_version", "counts"}
            and type(result.get("baseline_version")) is int
            and result.get("baseline_version") == 1
            and result.get("counts") == _EXPECTED_COUNTS
        )
    else:
        valid = (
            set(result) == common | {"provision_postcondition"}
            and result.get("provision_postcondition") == "PASS"
        )
    if not valid or result.get("outcome") != "PASS":
        raise _Indeterminate
    return "PASS"


def _read_only_outcome(result: dict[str, object], operation: str) -> str:
    """Accept only the fixed Railway result schema, and PASS only for PASS."""
    code = result.get("result")
    common = {"operation", "outcome", "source_sha", "result"}
    if operation == "reconcile":
        if set(result) != common | {"checks"}:
            raise _Indeterminate
        try:
            _valid_output(json.dumps({"result": code, "checks": result["checks"]}))
        except (TypeError, ValueError):
            raise _Indeterminate from None
        passed = code == "PASS"
    elif operation == "emergency-state":
        if set(result) != common or code not in _EMERGENCY_STATES:
            raise _Indeterminate
        passed = code in _VALID_EMERGENCY_STATES
    elif operation == "row-counts":
        passed = code == "PASS"
        if not (
            _valid_row_counts(result)
            if passed
            else set(result) == common and code == "FAIL_QUERY"
        ):
            raise _Indeterminate
    else:
        if set(result) != common or code not in STATUS_CODES:
            raise _Indeterminate
        passed = code == "PASS"
    outcome = "PASS" if passed else "FAIL"
    if result.get("outcome") != outcome:
        raise _Indeterminate
    return outcome


def _valid_row_counts(result: dict[str, object]) -> bool:
    """A count PASS needs whole counts, their total, digest, and time T (AC13)."""
    counts = _mapping(result.get("counts"))
    captured_at = result.get("captured_at")
    return (
        set(result)
        == {
            "operation",
            "outcome",
            "source_sha",
            "result",
            "tables",
            "counts",
            "counts_sha256",
            "captured_at",
        }
        and counts is not None
        # AC13 names the migration table, and an empty schema proves nothing.
        and "django_migrations" in counts
        and all(type(count) is int and count >= 0 for count in counts.values())
        and type(result.get("tables")) is int
        and result.get("tables") == len(counts)
        and result.get("counts_sha256")
        == row_counts.digest(cast(dict[str, int], counts))
        and isinstance(captured_at, str)
        and _CAPTURED_AT.fullmatch(captured_at) is not None
    )


def _settled(key: str, service_id: str, target: _Target) -> bool:
    """Wait until Staging again serves the same deploy as before the job.

    The web instance can restart during the reset gate, and an old instance can
    serve for a short time after a restart. So one failed read is not final.
    """
    deadline = time.monotonic() + _SETTLE_DEADLINE_SECONDS
    while True:
        try:
            promote._preflight(key, service_id)  # pyright: ignore[reportPrivateUsage]
            if _target(key, service_id) == target:
                return True
        except (
            OSError,
            TypeError,
            UnicodeError,
            ValueError,
            api_staging_preflight.TargetSafetyError,
        ):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(_SETTLE_POLL_SECONDS)


def progress(message: str) -> None:
    """Show the operator what the launcher waits for, only on a terminal."""
    if sys.stderr.isatty():
        print(f"... {message}", file=sys.stderr, flush=True)


def run_job(
    key: str, service_id: str, owner_id: str, operation: str, source_sha: str
) -> tuple[str, str, str]:
    """Start one job of S, wait for it, and return its outcome, line, and job ID.

    It never retries or cancels the job. Any unproved result raises JobFailure.
    """
    command = (
        f"python -m rehearsal.render_job --operation {operation} "
        f"--source-sha {source_sha}"
    )
    if operation in _CONFIRMATIONS:
        command += f" --confirm {_CONFIRMATIONS[operation]}"
    progress(f"starting the {operation} job")
    try:
        job_id, created_at = _start(key, service_id, command)
    except (KeyboardInterrupt, TypeError, ValueError):
        raise JobFailure("submission indeterminate") from None
    progress(f"job {job_id} started, waiting for its result")
    try:
        status = _wait(key, service_id, job_id)
        line = _result_line(key, owner_id, job_id, created_at)
        outcome = _outcome(line, operation, source_sha)
        if (status == "succeeded") != (outcome == "PASS") or status == "canceled":
            raise _Indeterminate
    except (_Indeterminate, KeyboardInterrupt, TypeError, ValueError):
        raise JobFailure(f"indeterminate {job_id}") from None
    return outcome, line, job_id


def result_code(line: str) -> object:
    """Return the "result" field of a validated read-only result line."""
    return cast(dict[str, object], json.loads(line.removeprefix(_RESULT_PREFIX))).get(
        "result"
    )


def _fail(phase: str) -> int:
    print(f"FAIL render job {phase}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument("operation", choices=(*_CONFIRMATIONS, *_READ_ONLY))
        parser.add_argument("--confirm")
        arguments = parser.parse_args(argv)
        operation = cast(str, arguments.operation)
        # Only a mutation takes a confirmation, and it must be its exact one.
        if arguments.confirm != _CONFIRMATIONS.get(operation):
            raise ValueError("arguments invalid")
    except (SystemExit, ValueError):
        return _fail("confirmation")
    try:
        service_id = promote._service_id()  # pyright: ignore[reportPrivateUsage]
        key = promote._prompt_key()  # pyright: ignore[reportPrivateUsage]
        progress("checking the Render Staging target")
        promote._preflight(key, service_id)  # pyright: ignore[reportPrivateUsage]
        target = _target(key, service_id)
    except (
        KeyboardInterrupt,
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        api_staging_preflight.TargetSafetyError,
    ):
        return _fail("target")
    owner_id, _, source_sha = target
    try:
        outcome, line, job_id = run_job(
            key, service_id, owner_id, operation, source_sha
        )
    except JobFailure as failure:
        return _fail(failure.phase)
    if outcome == "FAIL":
        print(line)
        return 1
    progress("waiting until Staging serves the same deploy again")
    try:
        settled = _settled(key, service_id, target)
    except KeyboardInterrupt:
        settled = False
    if not settled:
        return _fail(f"target changed {job_id}")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
