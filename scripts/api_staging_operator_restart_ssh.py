"""Attempt one guarded three-role #243 restart on the exact Railway instance."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import uuid
from pathlib import Path

from scripts import api_staging_emergency_operator_ssh as _emergency
from scripts import api_staging_operator_inspect_ssh as _inspector
from scripts import api_staging_registry_reconcile as _registry_reconcile

_github_identity = _emergency._github_identity  # pyright: ignore[reportPrivateUsage]
_railway_identity = _emergency._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _emergency._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _emergency._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _emergency._active_instance  # pyright: ignore[reportPrivateUsage]
_target_ids = _emergency._target_ids  # pyright: ignore[reportPrivateUsage]
_CONFIG_PATH: Path = _emergency._CONFIG_PATH  # pyright: ignore[reportPrivateUsage]

_BOOTSTRAP = (
    _emergency._GUARD  # pyright: ignore[reportPrivateUsage]
    + r"""
try:
    if len(sys.argv)!=2: raise ValueError
    request=guard(sys.argv[1])
    from django.db import connection, transaction
    from rehearsal.models import StagingResetIdentity
    from rehearsal.reset import validate_baseline
    from accounts.management.commands.bootstrap_staging_emergency_operator import inspect_emergency_state
    from accounts.management.commands.restart_staging_validation_operators import Command
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            physical=check_database(request,connection,cursor)
        validate_baseline(StagingResetIdentity.objects.get(pk=1))
        if inspect_emergency_state()!='READY': raise ValueError
        same_connection(connection,physical)
    Command().execute(expected_identity=request['identity'],force_color=False,no_color=True,skip_checks=True)
except BaseException:
    print('FAIL_OPERATOR_RESTART_UNCERTAIN',file=sys.stderr)
    raise SystemExit(1)
print('TAILTAG_OPERATOR_RESTART_COMMAND_COMPLETED')
"""
)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        shell=False,
        stdin=None,
        stdout=None,
        stderr=subprocess.PIPE,
        timeout=1800,
    )


def _result(
    result: str, phase: str, identity: dict[str, str] | None, started: str
) -> dict[str, object]:
    return {
        "result": result,
        "phase": phase,
        "identity": identity,
        "window_utc": [started, _now()],
    }


def run() -> dict[str, object]:
    """Only the remote command may emit POSTCONDITION_PASS; never infer it here."""
    started = _now()
    identity: dict[str, str] | None = None
    phase = "terminal"
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _result("FAIL_INTERACTIVE_INPUT", phase, None, started)
    try:
        phase = "github_identity"
        _github_identity()
        phase = "railway_identity"
        _railway_identity()
        phase = "public_preflight"
        identity = _inspector._identity(_preflight())  # pyright: ignore[reportPrivateUsage]
        if identity is None:
            raise ValueError
        phase = "approved_receipt"
        _approved_receipt(identity)
        phase = "running_instance"
        project_id, environment_id, service_id, _ = _target_ids()
        instance = _active_instance(identity)
        if str(uuid.UUID(instance)) != instance:
            raise ValueError
        phase = "exact_instance_inspector"
        if not _emergency._inspector_pass(_inspector.run(), identity):  # pyright: ignore[reportPrivateUsage]
            raise ValueError
        phase = "registry_reconciliation"
        if not _emergency._registry_pass(_registry_reconcile.run(_CONFIG_PATH)):  # pyright: ignore[reportPrivateUsage]
            raise ValueError
        phase = "repeat_preflight"
        if _inspector._identity(_preflight()) != identity:  # pyright: ignore[reportPrivateUsage]
            raise ValueError
        phase = "database_binding"
        request = _emergency._binding_request(identity)  # pyright: ignore[reportPrivateUsage]
        phase = "railway_identity"
        _railway_identity()
        phase = "interactive_ssh"
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
                json.dumps(request, separators=(",", ":")),
            ]
        )
        if execution.returncode != 0 or not _inspector._allowed_ssh_stderr(  # pyright: ignore[reportPrivateUsage]
            execution.stderr or ""
        ):
            return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
        # stdout is inherited by the real hidden TTY and cannot be trusted as a
        # machine-readable completion receipt by this launcher.
        return _result("TRANSPORT_EXITED_ZERO_UNVERIFIED", phase, identity, started)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
    except Exception:  # noqa: BLE001
        if phase == "interactive_ssh":
            return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
        return _result("FAIL_" + phase.upper(), phase, identity, started)


def main() -> int:
    if len(sys.argv) != 1:
        print("FAIL_INVALID_ARGUMENTS")
        return 1
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
