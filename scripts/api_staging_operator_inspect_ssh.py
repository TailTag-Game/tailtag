"""Run the read-only #243 operator inspector on one verified Railway instance."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

from scripts import api_staging_registry_reconcile as _registry_reconcile
from scripts import api_staging_reset_ssh as _reset_ssh

_approved_receipt = _registry_reconcile._approved_receipt  # pyright: ignore[reportPrivateUsage]
_github_identity = _registry_reconcile._github_identity  # pyright: ignore[reportPrivateUsage]
_ENVIRONMENT_ID = _reset_ssh._ENVIRONMENT_ID  # pyright: ignore[reportPrivateUsage]
_PROJECT_ID = _reset_ssh._PROJECT_ID  # pyright: ignore[reportPrivateUsage]
_SERVICE_ID = _reset_ssh._SERVICE_ID  # pyright: ignore[reportPrivateUsage]
_active_instance = _reset_ssh._active_instance  # pyright: ignore[reportPrivateUsage]
_preflight = _reset_ssh._preflight  # pyright: ignore[reportPrivateUsage]
_railway_identity = _reset_ssh._railway_identity  # pyright: ignore[reportPrivateUsage]

_ROOT: Final = Path(__file__).resolve().parents[1]
_INSPECTOR: Final = _ROOT / "scripts" / "api_staging_operator_inspect.py"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SSH_KEY_NOTICE = re.compile(
    r"\AUsing SSH key from (?:file [^\x00-\x1f\x7f]+: [^\x00-\x1f\x7f]+|agent: [^\x00-\x1f\x7f]+)\n\Z"
)
_TIMEOUT_SECONDS: Final = 120

PASS: Final = "PASS"
FAIL_IDENTITY: Final = "FAIL_IDENTITY"
FAIL_PREFLIGHT: Final = "FAIL_PREFLIGHT"
FAIL_APPROVED_RECEIPT: Final = "FAIL_APPROVED_RECEIPT"
FAIL_INSTANCE: Final = "FAIL_INSTANCE"
FAIL_TARGET_CHANGED: Final = "FAIL_TARGET_CHANGED"
FAIL_TIMEOUT: Final = "FAIL_TIMEOUT"
FAIL_TRANSPORT: Final = "FAIL_TRANSPORT"
FAIL_OUTPUT_CONTRACT: Final = "FAIL_OUTPUT_CONTRACT"
FAIL_BOOTSTRAP: Final = "FAIL_BOOTSTRAP"
FAIL_TARGET_IDENTITY: Final = "FAIL_TARGET_IDENTITY"

_RUNNER_FAILURES: Final = frozenset(
    {
        FAIL_IDENTITY,
        FAIL_PREFLIGHT,
        FAIL_APPROVED_RECEIPT,
        FAIL_INSTANCE,
        FAIL_TARGET_CHANGED,
        FAIL_TIMEOUT,
        FAIL_TRANSPORT,
        FAIL_OUTPUT_CONTRACT,
        FAIL_BOOTSTRAP,
        FAIL_TARGET_IDENTITY,
    }
)
_PHASES: Final = frozenset(
    {
        "github_identity",
        "railway_identity",
        "public_preflight",
        "approved_receipt",
        "running_instance",
        "repeat_preflight",
        "exact_instance_inspector",
    }
)

# The remote program receives reviewed source as data instead of executing it
# directly from SSH stdin. It prints one fixed JSON shape after imported-code
# output is captured.
_BOOTSTRAP: Final = r"""
import contextlib, hashlib, io, json, re, sys, uuid
_SHA = re.compile(r"[0-9a-f]{40}\Z")
def _invalid_request(request):
    if not isinstance(request, dict) or set(request) != {"source", "source_sha256", "identity"}:
        return True
    source, digest, identity = request["source"], request["source_sha256"], request["identity"]
    if not isinstance(source, str) or not isinstance(digest, str) or hashlib.sha256(source.encode()).hexdigest() != digest:
        return True
    if not isinstance(identity, dict) or set(identity) != {"source_sha", "deployment_id", "environment"}:
        return True
    source_sha, deployment_id, environment = identity["source_sha"], identity["deployment_id"], identity["environment"]
    if not isinstance(source_sha, str) or _SHA.fullmatch(source_sha) is None or not isinstance(deployment_id, str) or environment != "staging":
        return True
    try:
        return str(uuid.UUID(deployment_id)) != deployment_id
    except ValueError:
        return True
def _emit(result, target_verified):
    sys.stdout.write(json.dumps({"result": result, "target_verified": target_verified}, sort_keys=True) + "\n")
try:
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144:
        raise ValueError
    request = json.loads(raw)
    if _invalid_request(request):
        raise ValueError
    source = request["source"]
    identity = request["identity"]
    captured_stdout, captured_stderr = io.StringIO(), io.StringIO()
    verified = False
    with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
        sys.path.insert(0, "/app")
        namespace = {"__name__": "tailtag_operator_inspector", "__file__": "/app/api_staging_operator_inspect.py"}
        exec(compile(source, "/app/api_staging_operator_inspect.py", "exec"), namespace)
        if not namespace["_valid_expected_identity"](identity["source_sha"], identity["deployment_id"]) or not namespace["_target_identity_matches"](identity["source_sha"], identity["deployment_id"]):
            result, verified = "FAIL_TARGET_IDENTITY", False
        else:
            verified = True
            try:
                namespace["_bootstrap"]()
                from django.db import connection, transaction
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION READ ONLY")
                    result = namespace["_inspect_orm_preconditions"]()
                if result not in namespace["STATUS_CODES"]:
                    raise ValueError
            except BaseException:
                result = "FAIL_BOOTSTRAP"
    _emit(result, verified)
except BaseException:
    _emit("FAIL_BOOTSTRAP", False)
"""


def _run(
    arguments: list[str], *, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one local provider command with no shell or inherited output."""
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=_TIMEOUT_SECONDS,
        input=input,
    )


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _identity(value: object) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    identity = cast(Mapping[str, object], value)
    if frozenset(identity) != frozenset({"source_sha", "deployment_id", "environment"}):
        return None
    source_sha = identity.get("source_sha")
    deployment_id = identity.get("deployment_id")
    environment = identity.get("environment")
    if (
        not isinstance(source_sha, str)
        or _SHA.fullmatch(source_sha) is None
        or not isinstance(deployment_id, str)
        or environment != "staging"
    ):
        return None
    try:
        if str(uuid.UUID(deployment_id)) != deployment_id:
            return None
    except ValueError:
        return None
    return {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": "staging",
    }


def _result(
    result: str,
    phase: str,
    identity: dict[str, str] | None,
    target_verified: bool,
    started: str,
) -> dict[str, object]:
    if result not in _RUNNER_FAILURES and result != PASS:
        from scripts.api_staging_operator_inspect import STATUS_CODES

        if result not in STATUS_CODES:
            result = FAIL_OUTPUT_CONTRACT
    if phase not in _PHASES:
        result, phase = FAIL_OUTPUT_CONTRACT, "exact_instance_inspector"
    return {
        "result": result,
        "phase": phase,
        "identity": identity,
        "target_verified": target_verified,
        "window_utc": [started, _now()],
    }


def _reviewed_source() -> tuple[str, str]:
    status = _INSPECTOR.lstat()
    if (
        not _INSPECTOR.is_file()
        or _INSPECTOR.is_symlink()
        or status.st_size > 128 * 1024
    ):
        raise ValueError
    source = _INSPECTOR.read_text(encoding="utf-8")
    return source, hashlib.sha256(source.encode()).hexdigest()


def _bootstrap_output(raw: str, returncode: int) -> tuple[str, bool] | None:
    if not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    output = cast(dict[str, object], value)
    if frozenset(output) != frozenset({"result", "target_verified"}):
        return None
    result = output.get("result")
    verified = output.get("target_verified")
    if not isinstance(result, str) or type(verified) is not bool:
        return None
    from scripts.api_staging_operator_inspect import STATUS_CODES

    if result not in STATUS_CODES | {FAIL_BOOTSTRAP, FAIL_TARGET_IDENTITY}:
        return None
    if returncode != 0:
        return None
    if result == PASS and not verified:
        return None
    if result in STATUS_CODES and result != PASS and not verified:
        return None
    if result == FAIL_TARGET_IDENTITY and verified:
        return None
    return result, verified


def _allowed_ssh_stderr(stderr: str) -> bool:
    """Accept only Railway CLI's documented one-line key-selection notice."""
    return not stderr or _SSH_KEY_NOTICE.fullmatch(stderr) is not None


def run() -> dict[str, object]:
    """Run one preflighted read-only inspection and retain only public evidence."""
    started = _now()
    identity: dict[str, str] | None = None
    try:
        _github_identity()
    except Exception:  # noqa: BLE001
        return _result(FAIL_IDENTITY, "github_identity", None, False, started)
    try:
        _railway_identity()
    except Exception:  # noqa: BLE001
        return _result(FAIL_IDENTITY, "railway_identity", None, False, started)
    try:
        identity = _identity(_preflight())
        if identity is None:
            raise ValueError
    except Exception:  # noqa: BLE001
        return _result(FAIL_PREFLIGHT, "public_preflight", None, False, started)
    try:
        _approved_receipt(identity)
    except Exception:  # noqa: BLE001
        return _result(
            FAIL_APPROVED_RECEIPT, "approved_receipt", identity, False, started
        )
    try:
        _railway_identity()
    except Exception:  # noqa: BLE001
        return _result(FAIL_IDENTITY, "railway_identity", identity, False, started)
    try:
        instance = _active_instance(identity)
    except Exception:  # noqa: BLE001
        return _result(FAIL_INSTANCE, "running_instance", identity, False, started)
    try:
        repeated = _identity(_preflight())
        if repeated != identity:
            return _result(
                FAIL_TARGET_CHANGED, "repeat_preflight", identity, False, started
            )
        if repeated is None:
            raise ValueError
    except Exception:  # noqa: BLE001
        return _result(FAIL_PREFLIGHT, "repeat_preflight", identity, False, started)
    try:
        _railway_identity()
    except Exception:  # noqa: BLE001
        return _result(FAIL_IDENTITY, "railway_identity", identity, False, started)
    try:
        source, source_sha256 = _reviewed_source()
        request = json.dumps(
            {"source": source, "source_sha256": source_sha256, "identity": identity},
            separators=(",", ":"),
        )
        execution = _run(
            [
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
            ],
            input=request,
        )
    except subprocess.TimeoutExpired:
        return _result(
            FAIL_TIMEOUT, "exact_instance_inspector", identity, False, started
        )
    except (OSError, ValueError):
        return _result(
            FAIL_TRANSPORT, "exact_instance_inspector", identity, False, started
        )
    if execution.returncode != 0:
        return _result(
            FAIL_TRANSPORT, "exact_instance_inspector", identity, False, started
        )
    if not _allowed_ssh_stderr(execution.stderr):
        return _result(
            FAIL_OUTPUT_CONTRACT,
            "exact_instance_inspector",
            identity,
            False,
            started,
        )
    output = _bootstrap_output(execution.stdout, execution.returncode)
    if output is None:
        return _result(
            FAIL_OUTPUT_CONTRACT, "exact_instance_inspector", identity, False, started
        )
    result, target_verified = output
    return _result(
        result, "exact_instance_inspector", identity, target_verified, started
    )


def main() -> int:
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
