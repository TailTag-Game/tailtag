"""Read-only #243 three-way registry reconciliation on exact Staging."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Final, NoReturn, cast

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.api_staging_reset_ssh import (
    REPLACEMENT_RESET_CONFIG_PATH,
    _active_instance,  # pyright: ignore[reportPrivateUsage]
    _preflight,  # pyright: ignore[reportPrivateUsage]
    _railway_identity,  # pyright: ignore[reportPrivateUsage]
    _read_configuration,
    _runtime_database_fingerprint,  # pyright: ignore[reportPrivateUsage]
    _target_ids,  # pyright: ignore[reportPrivateUsage]
)
from scripts.api_staging_reset_ssh import (
    _approved_receipt as _reset_approved_receipt,  # pyright: ignore[reportPrivateUsage]
)

_REMOTE_SOURCE: Final = _ROOT / "scripts/api_staging_registry_reconcile_remote.py"
_SHA: Final = re.compile(r"[0-9a-f]{40}\Z")
_CHECKS: Final = frozenset(
    {
        "registry_singleton",
        "registry_structure",
        "root_completeness",
        "reset_environment_id",
        "database_name_private_registry",
        "cluster_identifier_private_registry",
        "database_name_actual_private",
        "database_name_actual_registry",
        "cluster_identifier_actual_private",
        "cluster_identifier_actual_registry",
        "owner_binding_private_registry",
        "catcher_binding_private_registry",
        "media_binding_private_registry",
        "database_host_runtime_private",
        "database_port_runtime_private",
    }
)
_BOOTSTRAP: Final = """
import hashlib, json, sys
try:
    raw = sys.stdin.read(131073)
    if len(raw) > 131072:
        raise ValueError
    request = json.loads(raw)
    source = request.pop('source')
    digest = request.pop('source_sha256')
    if not isinstance(source, str) or not isinstance(digest, str) or hashlib.sha256(source.encode()).hexdigest() != digest:
        raise ValueError
    sys.path.insert(0, '/app')
    import django
    django.setup()
    namespace = {'__name__': 'tailtag_registry_reconcile_remote'}
    exec(compile(source, '<reviewed-registry-reconciler>', 'exec'), namespace)
    result = namespace['run_request'](request)
    print(json.dumps(result, sort_keys=True))
except BaseException:
    print('{"result":"FAIL_EXECUTION","checks":{}}')
"""


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


def _run(
    arguments: list[str], *, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        input=input,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=120,
    )


def _github_identity() -> None:
    observed = _run(["gh", "api", "user", "--jq", ".login"])
    if observed.returncode != 0 or observed.stdout.strip() != "FinnThePanther":
        raise ValueError


def _source_commit(source_sha: str) -> None:
    _github_identity()
    observed = _run(
        [
            "gh",
            "api",
            f"repos/TailTag-Game/tailtag/commits/{source_sha}",
            "--jq",
            ".sha",
        ]
    )
    if observed.returncode != 0 or observed.stdout.strip() != source_sha:
        raise ValueError


def _approved_receipt(identity: dict[str, str]) -> None:
    _reset_approved_receipt(identity, _ROOT)


def _reviewed_source() -> tuple[str, str]:
    status = _REMOTE_SOURCE.lstat()
    if not stat.S_ISREG(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise ValueError
    if status.st_size <= 0 or status.st_size > 64 * 1024:
        raise ValueError
    source = _REMOTE_SOURCE.read_text(encoding="utf-8")
    return source, hashlib.sha256(source.encode()).hexdigest()


def _valid_output(raw: str) -> dict[str, object]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError
    output = cast(dict[str, object], value)
    if frozenset(output) != frozenset({"result", "checks"}):
        raise ValueError
    result = output["result"]
    checks = output["checks"]
    if result not in {
        "PASS",
        "MISMATCH",
        "FAIL_INVALID_INPUT",
        "FAIL_CONFIGURATION",
        "FAIL_QUERY",
        "FAIL_EXECUTION",
    } or not isinstance(checks, dict):
        raise ValueError
    typed_checks = cast(dict[object, object], checks)
    if result in {"PASS", "MISMATCH"}:
        if frozenset(typed_checks) != _CHECKS:
            raise ValueError
        if typed_checks["registry_singleton"] not in {"PASS", "MISSING", "AMBIGUOUS"}:
            raise ValueError
        if any(
            typed_checks[key] not in {"PASS", "MISMATCH", "INDETERMINATE"}
            for key in ("registry_structure", "root_completeness")
        ):
            raise ValueError
        if any(
            typed_checks[key] not in {"MATCH", "MISMATCH", "INDETERMINATE"}
            for key in _CHECKS
            - {"registry_singleton", "registry_structure", "root_completeness"}
        ):
            raise ValueError
        expected_result = (
            "PASS"
            if all(
                typed_checks[key] == "PASS"
                for key in (
                    "registry_singleton",
                    "registry_structure",
                    "root_completeness",
                )
            )
            and all(
                typed_checks[key] == "MATCH"
                for key in _CHECKS
                - {"registry_singleton", "registry_structure", "root_completeness"}
            )
            else "MISMATCH"
        )
        if result != expected_result:
            raise ValueError
    elif typed_checks:
        raise ValueError
    return output


def run(config_path: Path) -> dict[str, object]:
    """Perform one guarded read-only request; never expose private observations."""
    project_id, environment_id, service_id, _ = _target_ids()
    configuration = _read_configuration(config_path)
    _github_identity()
    _railway_identity()
    identity = _preflight()
    if _SHA.fullmatch(identity["source_sha"]) is None:
        raise ValueError
    _approved_receipt(identity)
    _source_commit(identity["source_sha"])
    _railway_identity()
    instance = _active_instance(identity)
    _railway_identity()
    fingerprint = _runtime_database_fingerprint()
    source, source_hash = _reviewed_source()
    request: dict[str, object] = {
        "identity": identity,
        "database_url_fingerprint": fingerprint,
        "configuration": configuration,
        "source": source,
        "source_sha256": source_hash,
    }
    _railway_identity()
    executed = _run(
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
        ],
        input=json.dumps(request, separators=(",", ":")),
    )
    if executed.returncode != 0:
        raise ValueError
    return _valid_output(executed.stdout)


def main() -> int:
    parser = _SafeParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--config", type=Path, default=REPLACEMENT_RESET_CONFIG_PATH)
    try:
        arguments = parser.parse_args()
        result = run(arguments.config)
    except Exception:  # noqa: BLE001
        print('{"result":"FAIL_EXECUTION","checks":{}}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] in {"PASS", "MISMATCH"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
