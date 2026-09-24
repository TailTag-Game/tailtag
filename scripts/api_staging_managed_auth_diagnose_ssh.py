"""Launch one guarded, exact-instance managed-operator credential diagnosis."""

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

_railway_identity = _inspector._railway_identity  # pyright: ignore[reportPrivateUsage]
_preflight = _inspector._preflight  # pyright: ignore[reportPrivateUsage]
_approved_receipt = _inspector._approved_receipt  # pyright: ignore[reportPrivateUsage]
_active_instance = _inspector._active_instance  # pyright: ignore[reportPrivateUsage]
_parse_identity = _inspector._identity  # pyright: ignore[reportPrivateUsage]
_PROJECT_ID = _inspector._PROJECT_ID  # pyright: ignore[reportPrivateUsage]
_SERVICE_ID = _inspector._SERVICE_ID  # pyright: ignore[reportPrivateUsage]
_ENVIRONMENT_ID = _inspector._ENVIRONMENT_ID  # pyright: ignore[reportPrivateUsage]
_ROOT: Final = Path(__file__).resolve().parents[1]
_REMOTE: Final = _ROOT / "scripts" / "api_staging_managed_auth_diagnose.py"
_INSPECTOR_REMOTE: Final = _ROOT / "scripts" / "api_staging_operator_inspect.py"
_TIMEOUT_SECONDS: Final = 1800
_SSH_KEY_NOTICE = re.compile(
    r"\AUsing SSH key from (?:file [^\x00-\x1f\x7f]+: [^\x00-\x1f\x7f]+|agent: [^\x00-\x1f\x7f]+)\n\Z"
)

_BOOTSTRAP: Final = r"""
import contextlib, datetime, hashlib, io, json, re, sys, types, uuid
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CODES = {"CREDENTIAL_ACCEPTED", "CREDENTIAL_REJECTED", "IDENTITY_MISMATCH", "IDENTITY_AMBIGUOUS", "PASSWORD_UNUSABLE", "TARGET_OR_ROLE_FAILURE", "AUTH_PROTOCOL_FAILURE", "EXECUTION_FAILURE"}
def _valid(request):
    if not isinstance(request, dict) or set(request) != {"source", "source_sha256", "inspector_source", "inspector_sha256", "identity"}:
        return False
    for source_key, digest_key in (("source", "source_sha256"), ("inspector_source", "inspector_sha256")):
        source, digest = request[source_key], request[digest_key]
        if not isinstance(source, str) or not isinstance(digest, str) or len(source) > 131072 or hashlib.sha256(source.encode()).hexdigest() != digest:
            return False
    identity = request["identity"]
    if not isinstance(identity, dict) or set(identity) != {"source_sha", "deployment_id", "environment"} or identity["environment"] != "staging":
        return False
    if not isinstance(identity["source_sha"], str) or not _SHA.fullmatch(identity["source_sha"]) or not isinstance(identity["deployment_id"], str):
        return False
    try:
        return str(uuid.UUID(identity["deployment_id"])) == identity["deployment_id"]
    except ValueError:
        return False
def _emit(classification, identity=None, window=None):
    if classification not in _CODES:
        classification = "EXECUTION_FAILURE"
    if not isinstance(window, list) or len(window) != 2:
        window = ["", ""]
    sys.stdout.write(json.dumps({"classification": classification, "identity": identity, "window_utc": window}, sort_keys=True) + "\n")
    if classification == "CREDENTIAL_ACCEPTED":
        sys.stdout.write("TAILTAG_MANAGED_AUTH_DIAGNOSIS_COMPLETED\n")
def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value
try:
    if len(sys.argv) != 2 or len(sys.argv[1]) > 262144:
        raise ValueError
    request = json.loads(sys.argv[1], object_pairs_hook=_unique)
    if not _valid(request):
        raise ValueError
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        sys.path.insert(0, "/app")
        package = types.ModuleType("scripts")
        package.__path__ = ["/app"]
        sys.modules["scripts"] = package
        inspector = types.ModuleType("scripts.api_staging_operator_inspect")
        inspector.__file__ = "/app/api_staging_operator_inspect.py"
        sys.modules[inspector.__name__] = inspector
        exec(compile(request["inspector_source"], inspector.__file__, "exec"), inspector.__dict__)
        remote = types.ModuleType("scripts.api_staging_managed_auth_diagnose")
        remote.__file__ = "/app/api_staging_managed_auth_diagnose.py"
        sys.modules[remote.__name__] = remote
        exec(compile(request["source"], remote.__file__, "exec"), remote.__dict__)
        inspector._bootstrap()
    if captured.getvalue():
        raise ValueError
    result = remote.run(request["identity"])
    if not isinstance(result, dict) or set(result) != {"classification", "identity", "window_utc"} or result["classification"] not in _CODES:
        raise ValueError
    if result["identity"] != request["identity"] and not (result["identity"] is None and result["classification"] in {"TARGET_OR_ROLE_FAILURE", "EXECUTION_FAILURE"}):
        raise ValueError
    window = result["window_utc"]
    if not isinstance(window, list) or len(window) != 2 or not all(isinstance(value, str) and value.endswith("Z") for value in window):
        raise ValueError
    for value in window:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    _emit(result["classification"], result["identity"], result["window_utc"])
except BaseException:
    _emit("EXECUTION_FAILURE")
    sys.exit(1)
if result["classification"] != "CREDENTIAL_ACCEPTED":
    sys.exit(1)
"""


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _result(
    code: str, phase: str, identity: dict[str, str] | None, started: str
) -> dict[str, object]:
    return {
        "result": code,
        "phase": phase,
        "identity": identity,
        "target_verified": False,
        "window_utc": [started, _now()],
    }


def _source(path: Path) -> tuple[str, str]:
    status = path.lstat()
    if not path.is_file() or path.is_symlink() or status.st_size > 128 * 1024:
        raise ValueError
    source = path.read_text(encoding="utf-8")
    return source, hashlib.sha256(source.encode()).hexdigest()


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        stdout=None,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=_TIMEOUT_SECONDS,
    )


def run() -> dict[str, object]:
    """Check public guards, then make exactly one interactive SSH attempt."""
    started = _now()
    phase = "exact_instance_auth_diagnosis"
    identity: dict[str, str] | None = None
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _result("FAIL_INTERACTIVE_INPUT", phase, None, started)
    try:
        inspection = _inspector.run()
        if inspection.get("result") == "FAIL_IDENTITY":
            return _result("FAIL_IDENTITY", phase, None, started)
        if (
            inspection.get("phase") != "exact_instance_inspector"
            or inspection.get("target_verified") is not True
            or _parse_identity(inspection.get("identity")) is None
            or _parse_identity(inspection.get("identity")) != inspection.get("identity")
        ):
            return _result("FAIL_INSPECTOR", phase, None, started)
        if inspection.get("result") == "FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE":
            return _result("PASSWORD_UNUSABLE", phase, None, started)
        if inspection.get("result") != "PASS":
            return _result("FAIL_INSPECTOR", phase, None, started)
        inspected_identity = cast(dict[str, str], inspection["identity"])
    except BaseException:  # noqa: BLE001
        return _result("FAIL_INSPECTOR", phase, None, started)
    try:
        _railway_identity()
    except BaseException:  # noqa: BLE001
        return _result("FAIL_IDENTITY", phase, None, started)
    try:
        identity = _parse_identity(_preflight())
        if identity != inspected_identity:
            return _result("FAIL_TARGET_CHANGED", phase, identity, started)
        if identity is None:
            raise ValueError
        _approved_receipt(identity)
        instance = _active_instance(identity)
        if str(uuid.UUID(instance)) != instance:
            raise ValueError
        if _parse_identity(_preflight()) != identity:
            return _result("FAIL_TARGET_CHANGED", phase, identity, started)
    except BaseException:  # noqa: BLE001
        return _result("FAIL_GUARD", phase, identity, started)
    try:
        _railway_identity()
    except BaseException:  # noqa: BLE001
        return _result("FAIL_IDENTITY", phase, identity, started)
    try:
        source, digest = _source(_REMOTE)
        inspector_source, inspector_digest = _source(_INSPECTOR_REMOTE)
        request = json.dumps(
            {
                "source": source,
                "source_sha256": digest,
                "inspector_source": inspector_source,
                "inspector_sha256": inspector_digest,
                "identity": identity,
            },
            separators=(",", ":"),
        )
    except BaseException:  # noqa: BLE001
        return _result("FAIL_GUARD", phase, identity, started)
    arguments = [
        "railway",
        "ssh",
        "--project",
        _PROJECT_ID,
        "--service",
        _SERVICE_ID,
        "--environment",
        _ENVIRONMENT_ID,
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
    try:
        completed = _run(arguments)
    except subprocess.TimeoutExpired:
        return _result("FAIL_TRANSPORT_TIMEOUT", phase, identity, started)
    except BaseException:  # noqa: BLE001
        return _result("FAIL_TRANSPORT_EXECUTION", phase, identity, started)
    if completed.returncode != 0:
        return _result("FAIL_TRANSPORT_EXIT_STATUS", phase, identity, started)
    if completed.stderr and _SSH_KEY_NOTICE.fullmatch(completed.stderr) is None:
        return _result("FAIL_TRANSPORT_STDERR", phase, identity, started)
    return _result("TRANSPORT_EXITED_ZERO_UNVERIFIED", phase, identity, started)


def main() -> int:
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "TRANSPORT_EXITED_ZERO_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
