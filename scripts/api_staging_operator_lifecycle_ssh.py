"""Run one guarded interactive #243 operator lifecycle action on Staging."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Final, cast

from scripts import api_staging_operator_inspect_ssh as _inspector
from scripts import api_staging_registry_reconcile as _registry_reconcile
from scripts import api_staging_reset_ssh as _reset_ssh

_approved_receipt = _registry_reconcile._approved_receipt  # pyright: ignore[reportPrivateUsage]
_target_ids = _reset_ssh._target_ids  # pyright: ignore[reportPrivateUsage]
_active_instance = _reset_ssh._active_instance  # pyright: ignore[reportPrivateUsage]
_preflight = _reset_ssh._preflight  # pyright: ignore[reportPrivateUsage]
_railway_identity = _reset_ssh._railway_identity  # pyright: ignore[reportPrivateUsage]

_ROOT: Final = Path(__file__).resolve().parents[1]
_SOURCES: Final = {
    "inspector": _ROOT / "scripts" / "api_staging_operator_inspect.py",
    "lifecycle_command": _ROOT
    / "services"
    / "api"
    / "accounts"
    / "management"
    / "commands"
    / "staging_validation_operator.py",
}
_ACTIONS: Final = frozenset({"provision", "decommission", "rotate_password"})
_EXPECTED_STATUS: Final = {
    "provision": "FAIL_LIMITED_OPERATOR_MISSING",
    "decommission": "PASS",
    "rotate_password": "PASS",
}
_SHA: Final = re.compile(r"[0-9a-f]{40}\Z")
_TIMEOUT_SECONDS: Final = 1800

# The request is public data only. Startup output stays private. Once guards
# pass, stdin and stdout remain the real SSH terminal for Django's prompts.
_BOOTSTRAP: Final = r"""
import contextlib, hashlib, io, json, re, sys, uuid
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ACTIONS = {"provision": "FAIL_LIMITED_OPERATOR_MISSING", "decommission": "PASS", "rotate_password": "PASS"}
_COMMAND_FAILURES = {
    "Invalid command arguments.": "FAIL_LIFECYCLE_CONFIGURATION",
    "This command is unavailable for the current target.": "FAIL_LIFECYCLE_TARGET",
    "This command requires an interactive terminal.": "FAIL_LIFECYCLE_TTY",
    "Query debugging must be disabled.": "FAIL_LIFECYCLE_DEBUG_LOGGING",
    "Confirmation failed.": "FAIL_LIFECYCLE_CONFIRMATION",
    "Hidden terminal input is unavailable.": "FAIL_LIFECYCLE_HIDDEN_INPUT",
    "Operator identifier is invalid.": "FAIL_LIFECYCLE_IDENTIFIER_INPUT",
    "Passwords do not match.": "FAIL_LIFECYCLE_PASSWORD_CONFIRMATION",
    "Password does not meet operator requirements.": "FAIL_LIFECYCLE_PASSWORD_POLICY",
    "Required operator permissions are unavailable.": "FAIL_LIFECYCLE_PERMISSION_PREREQUISITE",
    "Existing group cannot be used as an operator.": "FAIL_LIFECYCLE_EXISTING_GROUP",
    "Existing account cannot be used as an operator.": "FAIL_LIFECYCLE_EXISTING_ACCOUNT",
    "Validation operator postcondition failed.": "FAIL_LIFECYCLE_POSTCONDITION",
}
def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError
        result[key] = value
    return result
def _valid(request):
    if not isinstance(request, dict) or set(request) != {"action", "identity", "sources"}: return False
    if request["action"] not in _ACTIONS: return False
    identity = request["identity"]
    if not isinstance(identity, dict) or set(identity) != {"source_sha", "deployment_id", "environment"}: return False
    sha, deployment = identity["source_sha"], identity["deployment_id"]
    if not isinstance(sha, str) or not _SHA.fullmatch(sha) or not isinstance(deployment, str) or identity["environment"] != "staging": return False
    try:
        if str(uuid.UUID(deployment)) != deployment: return False
    except ValueError: return False
    sources = request["sources"]
    if not isinstance(sources, dict) or set(sources) != {"inspector", "lifecycle_command"}: return False
    for item in sources.values():
        if not isinstance(item, dict) or set(item) != {"source", "sha256"}: return False
        source, digest = item["source"], item["sha256"]
        if not isinstance(source, str) or not isinstance(digest, str) or len(source) > 131072 or hashlib.sha256(source.encode()).hexdigest() != digest: return False
    return True
def _fail(classification="FAIL_LIFECYCLE_UNCERTAIN"):
    print(classification, file=sys.stderr)
    raise SystemExit(1)
try:
    if len(sys.argv) != 2 or len(sys.argv[1]) > 262144: raise ValueError
    request = json.loads(sys.argv[1], object_pairs_hook=_unique)
    if not _valid(request): raise ValueError
    identity, sources = request["identity"], request["sources"]
    startup_stdout, startup_stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(startup_stdout), contextlib.redirect_stderr(startup_stderr):
        sys.path.insert(0, "/app")
        namespace = {"__name__": "tailtag_operator_inspector", "__file__": "/app/api_staging_operator_inspect.py"}
        exec(compile(sources["inspector"]["source"], namespace["__file__"], "exec"), namespace)
        if not namespace["_valid_expected_identity"](identity["source_sha"], identity["deployment_id"]): raise ValueError
        if not namespace["_target_identity_matches"](identity["source_sha"], identity["deployment_id"]): raise ValueError
        namespace["_bootstrap"]()
        from django.db import connection, transaction
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            status = namespace["_inspect_orm_preconditions"]()
        if status != _ACTIONS[request["action"]]: raise ValueError
        command_namespace = {"__name__": "tailtag_validation_operator_command", "__file__": "/app/staging_validation_operator.py"}
        exec(compile(sources["lifecycle_command"]["source"], command_namespace["__file__"], "exec"), command_namespace)
    if startup_stdout.getvalue() or startup_stderr.getvalue(): raise ValueError
except BaseException:
    _fail()
try:
    command_namespace["Command"]().execute(action=request["action"], force_color=False, no_color=False, skip_checks=True)
except BaseException as error:
    try:
        from django.core.management.base import CommandError
    except BaseException:
        _fail()
    if type(error) is CommandError and len(error.args) == 1 and type(error.args[0]) is str:
        _fail(_COMMAND_FAILURES.get(error.args[0], "FAIL_LIFECYCLE_UNCERTAIN"))
    _fail()
print("TAILTAG_LIFECYCLE_COMMAND_COMPLETED")
"""


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _result(
    action: str, result: str, phase: str, identity: dict[str, str] | None, started: str
) -> dict[str, object]:
    return {
        "action": action,
        "result": result,
        "phase": phase,
        "identity": identity,
        "window_utc": [started, _now()],
    }


def _identity(value: object) -> dict[str, str] | None:
    return _inspector._identity(value)  # pyright: ignore[reportPrivateUsage]


def _window(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return len(items) == 2 and all(
        isinstance(item, str) and item.endswith("Z") for item in items
    )


def _reviewed_source() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for name, path in _SOURCES.items():
        status = path.lstat()
        if not path.is_file() or path.is_symlink() or status.st_size > 128 * 1024:
            raise ValueError
        source = path.read_text(encoding="utf-8")
        result[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    return result


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
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


def run(action: str) -> dict[str, object]:
    """Attempt exactly one interactive transport; exit zero requires inspection."""
    started = _now()
    identity: dict[str, str] | None = None
    phase = "inspector"
    if action not in _ACTIONS:
        return _result("INVALID", "FAIL_INVALID_ACTION", "action", None, started)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _result(action, "FAIL_INTERACTIVE_INPUT", "terminal", None, started)
    try:
        observed = _inspector.run()
        if (
            set(observed)
            != {"result", "phase", "identity", "target_verified", "window_utc"}
            or observed["result"] != _EXPECTED_STATUS[action]
            or observed["phase"] != "exact_instance_inspector"
            or observed["target_verified"] is not True
            or not _window(observed["window_utc"])
        ):
            return _result(action, "FAIL_INSPECTOR", "inspector", None, started)
        identity = _identity(observed["identity"])
        if identity is None:
            return _result(action, "FAIL_INSPECTOR", "inspector", None, started)
        phase = "railway_identity"
        _railway_identity()
        phase = "public_preflight"
        fresh = _identity(_preflight())
        if fresh is None or fresh != identity:
            return _result(
                action, "FAIL_TARGET_CHANGED", "public_preflight", None, started
            )
        phase = "approved_receipt"
        _approved_receipt(identity)
        phase = "running_instance"
        project_id, environment_id, service_id, _ = _target_ids()
        instance = _active_instance(identity)
        if str(uuid.UUID(instance)) != instance:
            return _result(
                action, "FAIL_INSTANCE", "running_instance", identity, started
            )
        phase = "repeat_preflight"
        repeated = _identity(_preflight())
        if repeated != identity:
            return _result(
                action, "FAIL_TARGET_CHANGED", "repeat_preflight", identity, started
            )
        phase = "railway_identity"
        _railway_identity()
        phase = "reviewed_source"
        request = json.dumps(
            {"action": action, "identity": identity, "sources": _reviewed_source()},
            separators=(",", ":"),
        )
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
                "env",
                "DJANGO_SETTINGS_MODULE=config.settings.production",
                "/app/.venv/bin/python",
                "-I",
                "-c",
                _BOOTSTRAP,
                request,
            ]
        )
        if execution.returncode != 0:
            return _result(
                action, "FAIL_TRANSPORT_UNCERTAIN", "interactive_ssh", identity, started
            )
        if not _inspector._allowed_ssh_stderr(execution.stderr):  # pyright: ignore[reportPrivateUsage]
            return _result(
                action, "FAIL_TRANSPORT_UNCERTAIN", "interactive_ssh", identity, started
            )
        return _result(
            action,
            "TRANSPORT_EXITED_ZERO_UNVERIFIED",
            "interactive_ssh",
            identity,
            started,
        )
    except BaseException:  # noqa: BLE001
        return _result(
            action,
            "FAIL_TRANSPORT_UNCERTAIN" if phase == "interactive_ssh" else "FAIL_GUARD",
            phase,
            identity,
            started,
        )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in _ACTIONS:
        print("FAIL_INVALID_ACTION", file=sys.stderr)
        return 2
    result = run(sys.argv[1])
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
