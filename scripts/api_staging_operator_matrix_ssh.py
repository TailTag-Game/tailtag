"""Run the reviewed #243 matrix once on an exact Staging instance."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Final, cast

from scripts import api_staging_operator_inspect_ssh as _inspector
from scripts import api_staging_registry_reconcile as _registry
from scripts import api_staging_reset_ssh as _reset_ssh

_github_identity = _registry._github_identity  # pyright: ignore[reportPrivateUsage]
_railway_identity = _reset_ssh._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _reset_ssh._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _registry._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _reset_ssh._active_instance  # pyright: ignore[reportPrivateUsage]
_target_ids = _reset_ssh._target_ids  # pyright: ignore[reportPrivateUsage]

_ROOT: Final = Path(__file__).resolve().parents[1]
_SOURCES: Final = {
    "inspector": _ROOT / "scripts/api_staging_operator_inspect.py",
    "matrix": _ROOT / "scripts/api_staging_operator_matrix.py",
}
_CONTROLS: Final = (
    "accounts/admin.py",
    "catches/admin.py",
    "conventions/admin.py",
    "fursuits/admin.py",
    "profiles/admin.py",
)
_TIMEOUT_SECONDS: Final = 1800

# This request contains reviewed source and public identifiers only. Matrix
# credentials and reset acknowledgements stay on the inherited real terminal.
_BOOTSTRAP: Final = r"""
import contextlib, datetime, hashlib, io, json, re, sys, types, uuid
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_CONTROLS = {'accounts/admin.py', 'catches/admin.py', 'conventions/admin.py', 'fursuits/admin.py', 'profiles/admin.py'}
_CASE9 = {'catch_add', 'catch_change', 'catch_bulk_edit', 'credential_add', 'credential_replacement', 'credential_raw_edit', 'session_add', 'session_delete', 'session_bulk_edit', 'session_history_edit', 'activation_add', 'activation_delete', 'activation_reactivation', 'enrollment_add', 'enrollment_selection_change', 'convention_create', 'convention_delete'}
_LIMITATIONS = {'catch_change', 'credential_replacement', 'credential_raw_edit', 'activation_reactivation'}
_AUDIT_EVENTS = [
    {'action': 'set_fursuit_enabled', 'actor_class': 'unauthorized_actor', 'target_type': 'fursuits.fursuit', 'outcome': 'denied', 'count': 1},
    {'action': 'set_profile_enabled', 'actor_class': 'operator', 'target_type': 'profiles.playerprofile', 'outcome': 'succeeded', 'count': 1},
    {'action': 'set_fursuit_enabled', 'actor_class': 'emergency_superuser', 'target_type': 'fursuits.fursuit', 'outcome': 'succeeded', 'count': 1},
]
def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError
        result[key] = value
    return result
def _valid(request):
    if not isinstance(request, dict) or set(request) != {'identity', 'sources', 'control_hashes'}: return False
    identity = request['identity']
    if not isinstance(identity, dict) or set(identity) != {'source_sha', 'deployment_id', 'environment'}: return False
    sha, deployment = identity['source_sha'], identity['deployment_id']
    if not isinstance(sha, str) or not _SHA.fullmatch(sha) or not isinstance(deployment, str) or identity['environment'] != 'staging': return False
    try:
        if str(uuid.UUID(deployment)) != deployment: return False
    except ValueError: return False
    sources = request['sources']
    if not isinstance(sources, dict) or set(sources) != {'inspector', 'matrix'}: return False
    for item in sources.values():
        if not isinstance(item, dict) or set(item) != {'source', 'sha256'}: return False
        source, digest = item['source'], item['sha256']
        if not isinstance(source, str) or not isinstance(digest, str) or not _HEX.fullmatch(digest) or len(source) > 524288 or hashlib.sha256(source.encode()).hexdigest() != digest: return False
    controls = request['control_hashes']
    if not isinstance(controls, dict) or set(controls) != _CONTROLS: return False
    return all(isinstance(value, str) and _HEX.fullmatch(value) for value in controls.values())
def _fail():
    print('FAIL_MATRIX_UNCERTAIN', file=sys.stderr)
    raise SystemExit(1)
def _completed(result, identity):
    if not isinstance(result, dict) or set(result) != {'classification', 'identity', 'window_utc', 'cases', 'case9', 'deployed_control_hash_match', 'case9_control_review', 'case9_deterministic_evidence', 'case9_limitations', 'mutation_may_have_begun', 'reset', 'emergency_decommission', 'decommission', 'audit_events', 'session_cascade', 'credential_cascade'}: return False
    if result['classification'] != 'LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE' or result['identity'] != identity: return False
    window = result['window_utc']
    if not isinstance(window, list) or len(window) != 2: return False
    try:
        if any(not isinstance(item, str) or not item.endswith('Z') or datetime.datetime.fromisoformat(item.replace('Z', '+00:00')).tzinfo != datetime.timezone.utc for item in window): return False
    except ValueError: return False
    if result['cases'] != {**{str(i): 'PASS' for i in range(1, 9)}, '9': 'NOT_EXERCISED'}: return False
    if result['case9'] != {name: 'NOT_EXERCISED' if name in _LIMITATIONS else 'PASS' for name in _CASE9}: return False
    if result['case9_limitations'] != sorted(_LIMITATIONS): return False
    if result['deployed_control_hash_match'] != 'PASS' or result['case9_control_review'] != 'NOT_EXERCISED' or result['case9_deterministic_evidence'] != 'NOT_EXERCISED': return False
    if result['mutation_may_have_begun'] is not True or result['reset'] != 'PASS' or result['decommission'] != 'PASS': return False
    if result['emergency_decommission'] not in {'PASS', 'NOT_EXERCISED'}: return False
    if result['session_cascade'] != 'PASS' or result['credential_cascade'] != 'NOT_EXERCISED': return False
    events = result['audit_events']
    return isinstance(events, list) and all(isinstance(event, dict) and type(event.get('count')) is int for event in events) and events == _AUDIT_EVENTS
try:
    if len(sys.argv) != 2 or len(sys.argv[1]) > 1200000: raise ValueError
    request = json.loads(sys.argv[1], object_pairs_hook=_unique)
    if not _valid(request): raise ValueError
    identity, sources = request['identity'], request['sources']
    startup_stdout, startup_stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(startup_stdout), contextlib.redirect_stderr(startup_stderr):
        sys.path.insert(0, '/app')
        package = types.ModuleType('scripts')
        package.__path__ = []
        sys.modules['scripts'] = package
        inspector = types.ModuleType('scripts.api_staging_operator_inspect')
        inspector.__file__ = '/app/api_staging_operator_inspect.py'
        exec(compile(sources['inspector']['source'], inspector.__file__, 'exec'), inspector.__dict__)
        sys.modules[inspector.__name__] = inspector
        package.api_staging_operator_inspect = inspector
        if not inspector._valid_expected_identity(identity['source_sha'], identity['deployment_id']): raise ValueError
        if not inspector._target_identity_matches(identity['source_sha'], identity['deployment_id']): raise ValueError
        inspector._bootstrap()
        from django.db import connection, transaction
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION READ ONLY')
            if inspector._inspect_orm_preconditions() != 'PASS': raise ValueError
        if startup_stdout.getvalue() or startup_stderr.getvalue(): raise ValueError
        matrix = types.ModuleType('scripts.api_staging_operator_matrix')
        matrix.__file__ = '/app/api_staging_operator_matrix.py'
        matrix._CONTROL_HASHES = request['control_hashes']
        sys.modules[matrix.__name__] = matrix
        package.api_staging_operator_matrix = matrix
        exec(compile(sources['matrix']['source'], matrix.__file__, 'exec'), matrix.__dict__)
    if startup_stdout.getvalue() or startup_stderr.getvalue(): raise ValueError
    result = matrix.run(identity)
    if not _completed(result, identity): raise ValueError
except BaseException:
    _fail()
print('TAILTAG_MATRIX_LIVE_SEQUENCE_COMPLETED_PENDING_CASE9_EVIDENCE')
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


def _reviewed_source() -> dict[str, object]:
    sources: dict[str, dict[str, str]] = {}
    for name, path in _SOURCES.items():
        status = path.lstat()
        if not path.is_file() or path.is_symlink() or status.st_size > 512 * 1024:
            raise ValueError
        source = path.read_text(encoding="utf-8")
        sources[name] = {
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    controls = {
        name: hashlib.sha256((_ROOT / "services/api" / name).read_bytes()).hexdigest()
        for name in _CONTROLS
    }
    return {"sources": sources, "control_hashes": controls}


def _reconcile() -> dict[str, object]:
    return _registry.run(_reset_ssh.REPLACEMENT_RESET_CONFIG_PATH)


def _registry_pass(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        observed = _registry._valid_output(json.dumps(value))  # pyright: ignore[reportPrivateUsage]
    except (TypeError, ValueError):
        return False
    return observed["result"] == "PASS"


def _inspector_pass(value: object, identity: dict[str, str]) -> bool:
    if not isinstance(value, dict):
        return False
    observed = cast(dict[str, object], value)
    if set(observed) != {
        "result",
        "phase",
        "identity",
        "target_verified",
        "window_utc",
    }:
        return False
    window = observed["window_utc"]
    return (
        observed["result"] == "PASS"
        and observed["phase"] == "exact_instance_inspector"
        and observed["target_verified"] is True
        and _inspector._identity(observed["identity"]) == identity  # pyright: ignore[reportPrivateUsage]
        and isinstance(window, list)
        and len(cast(list[object], window)) == 2
        and all(
            isinstance(item, str) and item.endswith("Z")
            for item in cast(list[object], window)
        )
    )


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
    """Preflight every authority and attempt one interactive matrix transport."""
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
        phase = "registry_reconciliation"
        if not _registry_pass(_reconcile()):
            raise ValueError
        phase = "exact_instance_inspector"
        if not _inspector_pass(_inspector.run(), identity):
            raise ValueError
        phase = "repeat_preflight"
        if _inspector._identity(_preflight()) != identity:  # pyright: ignore[reportPrivateUsage]
            raise ValueError
        phase = "railway_identity"
        _railway_identity()
        phase = "reviewed_source"
        request = json.dumps(
            {"identity": identity, **_reviewed_source()}, separators=(",", ":")
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
        if execution.returncode != 0 or not _inspector._allowed_ssh_stderr(  # pyright: ignore[reportPrivateUsage]
            execution.stderr or ""
        ):
            return _result("FAIL_TRANSPORT_UNCERTAIN", phase, identity, started)
        return _result("TRANSPORT_EXITED_ZERO_UNVERIFIED", phase, identity, started)
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
    return 0 if result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
