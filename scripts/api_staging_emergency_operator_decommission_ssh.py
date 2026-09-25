"""Decommission the exact synthetic #243 emergency actor on verified Staging."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid

from scripts import api_staging_emergency_operator_ssh as _create

_github_identity = _create._github_identity  # pyright: ignore[reportPrivateUsage]
_railway_identity = _create._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _create._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _create._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _create._active_instance  # pyright: ignore[reportPrivateUsage]
_target_ids = _create._target_ids  # pyright: ignore[reportPrivateUsage]
_registry_reconcile = _create._registry_reconcile  # pyright: ignore[reportPrivateUsage]
_inspector = _create._inspector  # pyright: ignore[reportPrivateUsage]
_public_identity = _create._public_identity  # pyright: ignore[reportPrivateUsage]
_registry_pass = _create._registry_pass  # pyright: ignore[reportPrivateUsage]
_inspector_pass = _create._inspector_pass  # pyright: ignore[reportPrivateUsage]
_binding_request = _create._binding_request  # pyright: ignore[reportPrivateUsage]
_run = _create._run  # pyright: ignore[reportPrivateUsage]
_result = _create._result  # pyright: ignore[reportPrivateUsage]

_DECOMMISSION_BOOTSTRAP = (
    _create._GUARD  # pyright: ignore[reportPrivateUsage]
    + r"""
try:
    if len(sys.argv)!=2: raise ValueError
    request=guard(sys.argv[1])
    from django.db import connection, transaction
    from accounts.management.commands.decommission_staging_emergency_operator import Command
    with transaction.atomic():
        with connection.cursor() as cursor: physical=check_database(request,connection,cursor)
        same_connection(connection,physical)
        Command().execute(force_color=False,no_color=True,skip_checks=True)
        same_connection(connection,physical)
except BaseException:
    print('FAIL_EMERGENCY_DECOMMISSION_COMMAND',file=sys.stderr)
    raise SystemExit(1)
print('TAILTAG_EMERGENCY_DECOMMISSION_COMMAND_COMPLETED')
"""
)


def _emergency_precondition(identity: dict[str, str], instance: str) -> str:
    return _create._state(identity, instance)  # pyright: ignore[reportPrivateUsage]


def _emergency_postcondition(identity: dict[str, str], instance: str) -> str:
    return _create._state(identity, instance)  # pyright: ignore[reportPrivateUsage]


def run() -> dict[str, object]:
    started = _create._now()  # pyright: ignore[reportPrivateUsage]
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
        observed = _public_identity(_preflight())
        if observed is None:
            raise ValueError
        phase = "approved_receipt"
        _approved_receipt(observed)
        identity = observed
        phase = "running_instance"
        project_id, environment_id, service_id, _ = _target_ids()
        instance = _active_instance(identity)
        if str(uuid.UUID(instance)) != instance:
            raise ValueError
        phase = "registry_reconciliation"
        if not _registry_pass(_registry_reconcile.run(_create._CONFIG_PATH)):  # pyright: ignore[reportPrivateUsage]
            raise ValueError
        phase = "exact_instance_inspector"
        if not _inspector_pass(_inspector.run(), identity):
            raise ValueError
        phase = "emergency_precondition"
        if _emergency_precondition(identity, instance) != "READY":
            raise ValueError
        phase = "repeat_preflight"
        if _public_identity(_preflight()) != identity:
            raise ValueError
        phase = "railway_identity"
        _railway_identity()
        phase = "database_binding"
        request = _binding_request(identity)
        phase = "repeat_preflight"
        if _public_identity(_preflight()) != identity:
            raise ValueError
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
                _DECOMMISSION_BOOTSTRAP,
                json.dumps(request, separators=(",", ":")),
            ]
        )
        if execution.returncode != 0 or not _inspector._allowed_ssh_stderr(  # pyright: ignore[reportPrivateUsage]
            execution.stderr or ""
        ):
            return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
        phase = "postcondition_target"
        _railway_identity()
        if (
            _public_identity(_preflight()) != identity
            or _active_instance(identity) != instance
        ):
            return _result("FAIL_POSTCONDITION_TARGET", phase, identity, started)
        phase = "emergency_postcondition"
        if _emergency_postcondition(identity, instance) != "DECOMMISSIONED":
            return _result("FAIL_POSTCONDITION_UNCERTAIN", phase, identity, started)
        phase = "postcondition_roles"
        if not _inspector_pass(_inspector.run(), identity):
            return _result("FAIL_POSTCONDITION_ROLES", phase, identity, started)
        return _result(
            "PASS_EMERGENCY_OPERATOR_DECOMMISSIONED", phase, identity, started
        )
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
    except Exception:  # noqa: BLE001
        return _result("FAIL_" + phase.upper(), phase, identity, started)


def main() -> int:
    if len(sys.argv) != 1:
        print("FAIL_INVALID_ARGUMENTS")
        return 1
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS_EMERGENCY_OPERATOR_DECOMMISSIONED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
