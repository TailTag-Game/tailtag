"""Run one #243 Staging operator command over `render ssh` (#410 AC9).

The launcher checks the Render CLI account, the workspace, the one live deploy
and its receipt, the public identity, and the one running instance. Read-only
one-off jobs then prove the state that the command needs. The launcher opens
one interactive session on that exact instance, where
`accounts.render_operator` runs the command. Afterwards it waits for the same
live deploy, and read-only jobs check the state again. It passes only when the
session exits 0 and every check matches. It never retries a session or a job.

The `restore-count` operation runs the AC13 PITR restore counter instead. It
reads no Staging state, so no job runs, but every target check still does. The
counter itself compares the new database with the digest that the owner passes.

For the create, provision, decommission, and emergency operations, the jobs
after the session show the new state. No read-only job can see a new password
or a replaced login. So for the two password rotations and the managed
replace, the jobs show only that the roles stay valid, and PASS rests on the
session's exit status.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, NoReturn, cast

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts import api_staging_preflight
from scripts import api_staging_render_job as job
from scripts import api_staging_render_promote as promote
from scripts.api_staging_promote import (
    _mapping,  # pyright: ignore[reportPrivateUsage]
)

_Checks = tuple[tuple[str, str], ...]
# Each operation: the read-only job results it needs before the session, and
# the results that prove its new state after it. The inspector checks the
# #204 fixture, then the managed operator, then the limited operator.
_PLANS: Final[dict[str, tuple[_Checks, _Checks]]] = {
    "managed-create": (
        (("reconcile", "PASS"), ("inspect", "FAIL_MANAGED_OPERATOR_MISSING")),
        (("inspect", "FAIL_LIMITED_OPERATOR_MISSING"),),
    ),
    "lifecycle-provision": (
        (("reconcile", "PASS"), ("inspect", "FAIL_LIMITED_OPERATOR_MISSING")),
        (("inspect", "PASS"),),
    ),
    "lifecycle-rotate-password": ((("inspect", "PASS"),), (("inspect", "PASS"),)),
    # A decommissioned limited operator keeps its User and group, so the
    # inspector reports its inactive state.
    "lifecycle-decommission": (
        (("inspect", "PASS"),),
        (("inspect", "FAIL_LIMITED_OPERATOR_STATE"),),
    ),
    "managed-password-rotate": (
        (("reconcile", "PASS"), ("inspect", "PASS")),
        (("inspect", "PASS"),),
    ),
    "managed-operator-replace": (
        (("reconcile", "PASS"), ("inspect", "PASS")),
        (("inspect", "PASS"),),
    ),
    "emergency-create": (
        (("reconcile", "PASS"), ("inspect", "PASS"), ("emergency-state", "ABSENT")),
        (("emergency-state", "READY"), ("inspect", "PASS")),
    ),
    "emergency-decommission": (
        (("reconcile", "PASS"), ("inspect", "PASS"), ("emergency-state", "READY")),
        (("emergency-state", "DECOMMISSIONED"), ("inspect", "PASS")),
    ),
}
_RESTORE_COUNT: Final = "restore-count"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
_CLI_IDENTITY: Final = {"name": "Finn the Panther", "email": "finn@finnthepanther.com"}
_CLI_TIMEOUT_SECONDS: Final = 30
_TARGET_ERRORS: Final = (
    KeyboardInterrupt,
    OSError,
    TypeError,
    UnicodeError,
    ValueError,
    api_staging_preflight.TargetSafetyError,
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("arguments invalid")


class _Failure(Exception):
    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _cli_identity() -> None:
    """Require the Render CLI to act as the approved Finn account (AC11)."""
    try:
        result = subprocess.run(
            ["render", "whoami", "-o", "json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
        identity = (
            _mapping(json.loads(result.stdout)) if result.returncode == 0 else None
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        identity = None
    if identity is None or any(
        identity.get(name) != value for name, value in _CLI_IDENTITY.items()
    ):
        raise _Failure("identity")


def _instance(key: str, service_id: str) -> str:
    """Return the one running instance, which `render ssh` must reach exactly."""
    instances = job._list(  # pyright: ignore[reportPrivateUsage]
        promote._get(key, f"/services/{service_id}/instances")  # pyright: ignore[reportPrivateUsage]
    )
    instance = _mapping(instances[0]) if len(instances) == 1 else None
    instance_id = instance.get("id") if instance else None
    # Render names an instance by its service ID and a 5-character slug.
    if not isinstance(instance_id, str) or (
        re.fullmatch(re.escape(service_id) + r"-[a-z0-9]{5}", instance_id) is None
    ):
        raise ValueError("instance invalid")
    return instance_id


def _checks(
    key: str,
    service_id: str,
    target: job._Target,  # pyright: ignore[reportPrivateUsage]
    checks: _Checks,
    phase: str,
) -> None:
    owner_id, _, source_sha = target
    for operation, expected in checks:
        try:
            _, line, _ = job.run_job(key, service_id, owner_id, operation, source_sha)
        except job.JobFailure as failure:
            raise _Failure(failure.phase) from None
        if job.result_code(line) != expected:
            raise _Failure(f"{phase} {operation}")


def _remote(operation: str, source_sha: str, expected_counts: str | None) -> str:
    """Return the fixed in-image command. Each value in it was validated first."""
    if operation == _RESTORE_COUNT:
        return (
            "cd /app && exec /app/.venv/bin/python -m rehearsal.render_restore_count "
            f"--source-sha {source_sha} --expected-counts {expected_counts}"
        )
    return (
        "cd /app && exec /app/.venv/bin/python -m accounts.render_operator "
        f"--operation {operation} --source-sha {source_sha}"
    )


def _session(instance_id: str, remote: str) -> int:
    """Open one session on the exact instance, on the operator's own terminal."""
    try:
        return subprocess.run(
            [
                "render",
                "ssh",
                instance_id,
                "-o",
                "text",
                "--",
                # The ssh options follow the host, where OpenSSH still reads
                # them. A terminal is needed for the hidden prompts.
                "-o",
                "UpdateHostKeys=no",
                "-t",
                remote,
            ],
            check=False,
        ).returncode
    except (KeyboardInterrupt, OSError, subprocess.SubprocessError):
        return 1


def _run(operation: str, expected_counts: str | None) -> None:
    if not _interactive():
        raise _Failure("terminal")
    _cli_identity()
    try:
        service_id = promote._service_id()  # pyright: ignore[reportPrivateUsage]
        key = promote._prompt_key()  # pyright: ignore[reportPrivateUsage]
        job.progress("checking the Render Staging target")
        promote._preflight(key, service_id)  # pyright: ignore[reportPrivateUsage]
        target = job._target(key, service_id)  # pyright: ignore[reportPrivateUsage]
        instance_id = _instance(key, service_id)
    except _TARGET_ERRORS:
        raise _Failure("target") from None
    before, after = _PLANS.get(operation, ((), ()))
    _checks(key, service_id, target, before, "precondition")
    try:
        promote._preflight(key, service_id)  # pyright: ignore[reportPrivateUsage]
        if (
            job._target(key, service_id) != target  # pyright: ignore[reportPrivateUsage]
            or _instance(key, service_id) != instance_id
        ):
            raise ValueError("target changed")
    except _TARGET_ERRORS:
        raise _Failure("target") from None
    _cli_identity()
    job.progress("opening the render ssh session")
    if _session(instance_id, _remote(operation, target[2], expected_counts)) != 0:
        # The command may have committed before the session failed, so the
        # state is unknown. Run the read-only inspect job before any retry.
        raise _Failure("session uncertain")
    job.progress("waiting until Staging serves the same deploy again")
    try:
        settled = job._settled(key, service_id, target)  # pyright: ignore[reportPrivateUsage]
    except KeyboardInterrupt:
        settled = False
    if not settled:
        raise _Failure("target changed")
    _checks(key, service_id, target, after, "postcondition")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument("operation", choices=(*_PLANS, _RESTORE_COUNT))
        parser.add_argument("--expected-counts")
        arguments = parser.parse_args(argv)
        operation = cast(str, arguments.operation)
        expected_counts = cast(str | None, arguments.expected_counts)
        # Only the restore counter takes a digest, and it must be exact hex.
        if (operation == _RESTORE_COUNT) != (expected_counts is not None) or (
            expected_counts is not None and _DIGEST.fullmatch(expected_counts) is None
        ):
            raise ValueError("arguments invalid")
    except (SystemExit, ValueError):
        print("FAIL render ssh arguments", file=sys.stderr)
        return 1
    try:
        _run(operation, expected_counts)
    except _Failure as failure:
        print(f"FAIL render ssh {operation} {failure.phase}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"FAIL render ssh {operation} interrupted", file=sys.stderr)
        return 1
    print(f"PASS render ssh {operation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
