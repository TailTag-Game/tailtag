"""Launch one exact-instance interactive #243 managed-login replacement."""

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

_railway_identity = _inspector._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _inspector._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _inspector._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _inspector._active_instance  # pyright: ignore[reportPrivateUsage]
_identity = _inspector._identity  # pyright: ignore[reportPrivateUsage]
_allowed_ssh_stderr = _inspector._allowed_ssh_stderr  # pyright: ignore[reportPrivateUsage]
_target_ids = _inspector._target_ids  # pyright: ignore[reportPrivateUsage]
_ROOT: Final = Path(__file__).resolve().parents[1]
_SOURCES: Final = {
    "inspector": _ROOT / "scripts" / "api_staging_operator_inspect.py",
    "recovery_command": _ROOT
    / "services"
    / "api"
    / "accounts"
    / "management"
    / "commands"
    / "replace_staging_managed_operator.py",
}
_TIMEOUT_SECONDS: Final = 1800
_SHA: Final = re.compile(r"[0-9a-f]{40}\Z")

_BOOTSTRAP: Final = r"""
import contextlib, hashlib, io, json, re, sys, types, uuid
_SHA = re.compile(r"[0-9a-f]{40}\Z")
def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError
        result[key] = value
    return result
def _valid(request):
    if not isinstance(request, dict) or set(request) != {"identity", "sources"}: return False
    identity, sources = request["identity"], request["sources"]
    if not isinstance(identity, dict) or set(identity) != {"environment", "source_sha", "deployment_id"}: return False
    if identity["environment"] != "staging" or not isinstance(identity["source_sha"], str) or not _SHA.fullmatch(identity["source_sha"]) or not isinstance(identity["deployment_id"], str): return False
    try:
        if str(uuid.UUID(identity["deployment_id"])) != identity["deployment_id"]: return False
    except ValueError: return False
    if not isinstance(sources, dict) or set(sources) != {"inspector", "recovery_command"}: return False
    for item in sources.values():
        if not isinstance(item, dict) or set(item) != {"source", "sha256"}: return False
        source, digest = item["source"], item["sha256"]
        if not isinstance(source, str) or not isinstance(digest, str) or len(source) > 131072 or hashlib.sha256(source.encode()).hexdigest() != digest: return False
    return True
def _fail():
    print("FAIL_MANAGED_REPLACEMENT_UNCERTAIN", file=sys.stderr)
    raise SystemExit(1)
try:
    if len(sys.argv) != 2 or len(sys.argv[1]) > 262144: raise ValueError
    request = json.loads(sys.argv[1], object_pairs_hook=_unique)
    if not _valid(request): raise ValueError
    identity, sources = request["identity"], request["sources"]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        sys.path.insert(0, "/app")
        package = types.ModuleType("scripts")
        package.__path__ = ["/app"]
        sys.modules["scripts"] = package
        inspector = types.ModuleType("scripts.api_staging_operator_inspect")
        inspector.__file__ = "/app/api_staging_operator_inspect.py"
        sys.modules[inspector.__name__] = inspector
        exec(compile(sources["inspector"]["source"], inspector.__file__, "exec"), inspector.__dict__)
        if not inspector._valid_expected_identity(identity["source_sha"], identity["deployment_id"]): raise ValueError
        if not inspector._target_identity_matches(identity["source_sha"], identity["deployment_id"]): raise ValueError
        inspector._bootstrap()
        from django.db import connection, transaction
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            status = inspector._inspect_orm_preconditions()
        if status != "PASS": raise ValueError
        command_module = types.ModuleType("accounts.management.commands.replace_staging_managed_operator")
        command_module.__file__ = "/app/replace_staging_managed_operator.py"
        command_module.__package__ = "accounts.management.commands"
        sys.modules[command_module.__name__] = command_module
        exec(compile(sources["recovery_command"]["source"], command_module.__file__, "exec"), command_module.__dict__)
    if captured.getvalue(): raise ValueError
except BaseException:
    _fail()
try:
    command_module.Command().execute(expected_identity=identity, force_color=False, no_color=False, skip_checks=True)
except BaseException:
    _fail()
print("TAILTAG_MANAGED_REPLACEMENT_COMMAND_COMPLETED")
"""


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


def _reviewed_source() -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for name, path in _SOURCES.items():
        status = path.lstat()
        if not path.is_file() or path.is_symlink() or status.st_size > 128 * 1024:
            raise ValueError
        source = path.read_text(encoding="utf-8")
        sources[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    return sources


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


def run() -> dict[str, object]:
    """Guard one mutation attempt; transport success still needs postcondition proof."""
    started = _now()
    identity: dict[str, str] | None = None
    phase = "inspector"
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _result("FAIL_INTERACTIVE_INPUT", "terminal", None, started)
    try:
        observed = _inspector.run()
        if (
            set(observed)
            != {"result", "phase", "identity", "target_verified", "window_utc"}
            or observed["result"] != "PASS"
            or observed["phase"] != "exact_instance_inspector"
            or observed["target_verified"] is not True
            or not isinstance(observed["window_utc"], list)
            or len(cast(list[object], observed["window_utc"])) != 2
        ):
            return _result("FAIL_INSPECTOR", phase, None, started)
        identity = _identity(observed["identity"])
        if identity is None:
            return _result("FAIL_INSPECTOR", phase, None, started)
        phase = "railway_identity"
        _railway_identity()
        phase = "registry_reconciliation"
        reconciliation = _registry_reconcile.run(
            _reset_ssh.REPLACEMENT_RESET_CONFIG_PATH
        )
        try:
            validated_registry = _registry_reconcile._valid_output(  # pyright: ignore[reportPrivateUsage]
                json.dumps(reconciliation)
            )
        except (TypeError, ValueError):
            return _result("FAIL_REGISTRY_RECONCILIATION", phase, identity, started)
        if validated_registry["result"] != "PASS":
            return _result("FAIL_REGISTRY_RECONCILIATION", phase, identity, started)
        phase = "public_preflight"
        if _identity(_preflight()) != identity:
            return _result("FAIL_TARGET_CHANGED", phase, identity, started)
        phase = "approved_receipt"
        _approved_receipt(identity)
        phase = "running_instance"
        project_id, environment_id, service_id, _ = _target_ids()
        instance = _active_instance(identity)
        if str(uuid.UUID(instance)) != instance:
            return _result("FAIL_INSTANCE", phase, identity, started)
        phase = "repeat_preflight"
        if _identity(_preflight()) != identity:
            return _result("FAIL_TARGET_CHANGED", phase, identity, started)
        phase = "railway_identity"
        _railway_identity()
        phase = "reviewed_source"
        request = json.dumps(
            {"identity": identity, "sources": _reviewed_source()},
            separators=(",", ":"),
        )
        phase = "interactive_ssh"
        completed = _run(
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
        if completed.returncode != 0 or not _allowed_ssh_stderr(completed.stderr):
            return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
        return _result("TRANSPORT_EXITED_ZERO_UNVERIFIED", phase, identity, started)
    except BaseException:  # noqa: BLE001
        return _result(
            "FAIL_TRANSPORT_UNCERTAIN" if phase == "interactive_ssh" else "FAIL_GUARD",
            phase,
            identity,
            started,
        )


def main() -> int:
    if len(sys.argv) != 1:
        print("FAIL_INVALID_ARGUMENTS", file=sys.stderr)
        return 2
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
