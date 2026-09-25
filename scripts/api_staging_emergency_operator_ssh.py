"""Create the dedicated #243 emergency account on one verified Staging instance."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import uuid
from collections.abc import Mapping
from typing import Final, cast

from scripts import api_staging_operator_inspect_ssh as _inspector
from scripts import api_staging_registry_reconcile as _registry_reconcile
from scripts import api_staging_reset_ssh as _reset_ssh

_github_identity = _registry_reconcile._github_identity  # pyright: ignore[reportPrivateUsage]
_railway_identity = _reset_ssh._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _reset_ssh._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _registry_reconcile._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _reset_ssh._active_instance  # pyright: ignore[reportPrivateUsage]
_target_ids = _reset_ssh._target_ids  # pyright: ignore[reportPrivateUsage]
_read_configuration = _reset_ssh._read_configuration  # pyright: ignore[reportPrivateUsage]
_runtime_database_fingerprint = _reset_ssh._runtime_database_fingerprint  # pyright: ignore[reportPrivateUsage]

_CONFIG_PATH: Final = _reset_ssh.REPLACEMENT_RESET_CONFIG_PATH
_TIMEOUT_SECONDS: Final = 1800
_REGISTRY_STRUCTURAL: Final = frozenset(
    {"registry_singleton", "registry_structure", "root_completeness"}
)
_STATE_CODES: Final = frozenset(
    {"ABSENT", "READY", "DECOMMISSIONED", "MISMATCH", "INDETERMINATE"}
)

# Only public identity and opaque binding fingerprints cross the command line.
# The username, password, and confirmation use the inherited real TTY.
_GUARD: Final = r"""
import hashlib, json, os, re, sys, uuid
from pathlib import Path
def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError
        result[key]=value
    return result
def digest(host,port,name,cluster):
    normalized=["tailtag-staging-emergency-db-v1",host.lower(),str(int(port)),name,cluster]
    return hashlib.sha256(json.dumps(normalized,separators=(',',':')).encode()).hexdigest()
def guard(raw):
    request=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(request,dict) or set(request)!={'identity','database_url_fingerprint','database_facts_fingerprint'}: raise ValueError
    identity=request['identity']
    if not isinstance(identity,dict) or set(identity)!={'source_sha','deployment_id','environment'}: raise ValueError
    if any(not isinstance(request[key],str) or not re.fullmatch(r'[0-9a-f]{64}',request[key]) for key in ('database_url_fingerprint','database_facts_fingerprint')): raise ValueError
    if identity['environment']!='staging' or not isinstance(identity['source_sha'],str) or not re.fullmatch(r'[0-9a-f]{40}',identity['source_sha']): raise ValueError
    if not isinstance(identity['deployment_id'],str) or str(uuid.UUID(identity['deployment_id']))!=identity['deployment_id']: raise ValueError
    sys.path.insert(0,'/app')
    from config.replacement_target_binding import validate_runtime_target
    validate_runtime_target(os.environ)
    if os.environ.get('RAILWAY_DEPLOYMENT_ID')!=identity['deployment_id'] or os.environ.get('RAILWAY_ENVIRONMENT_NAME')!='staging': raise ValueError
    built=json.loads(Path('/opt/tailtag/build-identity.json').read_text())
    if built!={'source_sha':identity['source_sha']}: raise ValueError
    if hashlib.sha256(os.environ.get('DATABASE_URL','').encode()).hexdigest()!=request['database_url_fingerprint']: raise ValueError
    os.environ['DJANGO_SETTINGS_MODULE']='config.settings.production'
    import django
    django.setup()
    return request
def check_database(request,connection,cursor):
    cursor.execute('SELECT current_database(), (pg_control_system()).system_identifier')
    row=cursor.fetchone()
    if row is None or len(row)!=2: raise ValueError
    config=connection.settings_dict
    if str(config.get('NAME',''))!=str(row[0]): raise ValueError
    if digest(str(config.get('HOST','')),str(config.get('PORT','')),str(row[0]),str(row[1]))!=request['database_facts_fingerprint']: raise ValueError
    physical=connection.connection
    if physical is None or getattr(physical,'closed',True): raise ValueError
    return physical
def same_connection(connection,physical):
    if connection.connection is not physical or not connection.in_atomic_block or getattr(physical,'closed',True): raise ValueError
"""

_STATE_BOOTSTRAP: Final = (
    _GUARD
    + r"""
try:
    if len(sys.argv)!=2: raise ValueError
    request=guard(sys.argv[1])
    from django.db import connection, transaction
    from accounts.management.commands.bootstrap_staging_emergency_operator import inspect_emergency_state
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            physical=check_database(request,connection,cursor)
        status=inspect_emergency_state()
        same_connection(connection,physical)
    if status not in {'ABSENT','READY','DECOMMISSIONED','MISMATCH'}: raise ValueError
    print(status)
except BaseException:
    print('INDETERMINATE')
    raise SystemExit(1)
"""
)

_CREATE_BOOTSTRAP: Final = (
    _GUARD
    + r"""
try:
    if len(sys.argv)!=2: raise ValueError
    request=guard(sys.argv[1])
    from django.db import connection, transaction
    from accounts.management.commands.bootstrap_staging_emergency_operator import Command
    with transaction.atomic():
        with connection.cursor() as cursor: physical=check_database(request,connection,cursor)
        same_connection(connection,physical)
        Command().execute(force_color=False,no_color=True,skip_checks=True)
        same_connection(connection,physical)
except BaseException:
    print('FAIL_EMERGENCY_COMMAND',file=sys.stderr)
    raise SystemExit(1)
print('TAILTAG_EMERGENCY_COMMAND_COMPLETED')
"""
)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _result(
    result: str, phase: str, identity: dict[str, str] | None, started: str
) -> dict[str, object]:
    return {
        "result": result,
        "phase": phase,
        "identity": identity,
        "window_utc": [started, _now()],
    }


def _public_identity(value: object) -> dict[str, str] | None:
    return _inspector._identity(value)  # pyright: ignore[reportPrivateUsage]


def _registry_pass(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    record = cast(Mapping[str, object], value)
    if set(record) != {"result", "checks"}:
        return False
    checks_value = record.get("checks")
    if record.get("result") != "PASS" or not isinstance(checks_value, Mapping):
        return False
    checks = cast(Mapping[str, object], checks_value)
    return frozenset(checks) == _registry_reconcile._CHECKS and all(  # pyright: ignore[reportPrivateUsage]
        checks[name] == ("PASS" if name in _REGISTRY_STRUCTURAL else "MATCH")
        for name in checks
    )


def _inspector_pass(value: object, identity: dict[str, str]) -> bool:
    if not isinstance(value, Mapping):
        return False
    record = cast(Mapping[str, object], value)
    if set(record) != {
        "result",
        "phase",
        "identity",
        "target_verified",
        "window_utc",
    }:
        return False
    window = record.get("window_utc")
    if not isinstance(window, list):
        return False
    typed_window = cast(list[object], window)
    return (
        record.get("result") == "PASS"
        and record.get("phase") == "exact_instance_inspector"
        and record.get("target_verified") is True
        and _public_identity(record.get("identity")) == identity
        and len(typed_window) == 2
        and all(isinstance(item, str) and item.endswith("Z") for item in typed_window)
    )


def _binding_request(identity: dict[str, str]) -> dict[str, object]:
    """Commit to private expected database facts without rendering their values."""
    configuration = _read_configuration(_CONFIG_PATH)
    facts = [
        "tailtag-staging-emergency-db-v1",
        configuration["TAILTAG_STAGING_DATABASE_HOST"].lower(),
        str(int(configuration["TAILTAG_STAGING_DATABASE_PORT"])),
        configuration["TAILTAG_STAGING_DATABASE_NAME"],
        configuration["TAILTAG_STAGING_DATABASE_SYSTEM_ID"],
    ]
    return {
        "identity": identity,
        "database_url_fingerprint": _runtime_database_fingerprint(),
        "database_facts_fingerprint": hashlib.sha256(
            json.dumps(facts, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _state(identity: dict[str, str], instance: str) -> str:
    """Read one fixed superuser classification from the exact current image."""
    project_id, environment_id, service_id, _ = _target_ids()
    _railway_identity()
    request = _binding_request(identity)
    result = subprocess.run(
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
            _STATE_BOOTSTRAP,
            json.dumps(request, separators=(",", ":")),
        ],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=120,
    )
    status = result.stdout.strip()
    if (
        result.returncode != 0
        or status not in _STATE_CODES - {"INDETERMINATE"}
        or not _inspector._allowed_ssh_stderr(result.stderr or "")  # pyright: ignore[reportPrivateUsage]
    ):
        return "INDETERMINATE"
    return status


def _emergency_precondition(identity: dict[str, str], instance: str) -> str:
    return _state(identity, instance)


def _emergency_postcondition(identity: dict[str, str], instance: str) -> str:
    return _state(identity, instance)


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Leave stdin/stdout on the real terminal for hidden Django prompts."""
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        shell=False,
        stdin=None,
        stdout=None,
        stderr=subprocess.PIPE,
        timeout=_TIMEOUT_SECONDS,
    )


def run() -> dict[str, object]:
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
        if not _registry_pass(_registry_reconcile.run(_CONFIG_PATH)):
            raise ValueError
        phase = "exact_instance_inspector"
        if not _inspector_pass(_inspector.run(), identity):
            raise ValueError
        phase = "emergency_precondition"
        if _emergency_precondition(identity, instance) != "ABSENT":
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
                _CREATE_BOOTSTRAP,
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
        if _emergency_postcondition(identity, instance) != "READY":
            return _result("FAIL_POSTCONDITION_UNCERTAIN", phase, identity, started)
        phase = "postcondition_roles"
        if not _inspector_pass(_inspector.run(), identity):
            return _result("FAIL_POSTCONDITION_ROLES", phase, identity, started)
        return _result("PASS_EMERGENCY_OPERATOR_READY", phase, identity, started)
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
    return 0 if result["result"] == "PASS_EMERGENCY_OPERATOR_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
