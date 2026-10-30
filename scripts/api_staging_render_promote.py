"""Promote one eligible immutable TailTag commit to Render Staging (#409)."""

from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import warnings
from collections.abc import Mapping
from http.client import HTTPException
from pathlib import Path
from typing import Final, cast

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts import api_staging_preflight
from scripts.api_staging_promote import (
    _SOURCE_SHA,  # pyright: ignore[reportPrivateUsage]
    Evidence,
    _eligible,  # pyright: ignore[reportPrivateUsage]
    _mapping,  # pyright: ignore[reportPrivateUsage]
    _new_evidence,  # pyright: ignore[reportPrivateUsage]
    _persist,  # pyright: ignore[reportPrivateUsage]
    _result,  # pyright: ignore[reportPrivateUsage]
    _run,  # pyright: ignore[reportPrivateUsage]
    _SafeArgumentParser,  # pyright: ignore[reportPrivateUsage]
    _timestamp,  # pyright: ignore[reportPrivateUsage]
)

from config import replacement_target_binding

_API: Final = "https://api.render.com/v1"
_CONFIRMATION: Final = "promote-tailtag-render-staging"
_DEPLOY_ID: Final = re.compile(r"dep-[a-z0-9]{1,60}")
_MAX_RESPONSE_BYTES: Final = 1_048_576
_TIMEOUT_SECONDS: Final = 30
# A Render deploy builds the image, runs the pre-deploy migration, and waits up
# to 15 minutes for health checks before it goes live.
_DEPLOY_DEADLINE_SECONDS: Final = 30 * 60
_POLL_SECONDS: Final = 10
_IN_PROGRESS: Final = frozenset(
    {
        "created",
        "queued",
        "build_in_progress",
        "pre_deploy_in_progress",
        "update_in_progress",
    }
)
_PRE_DEPLOY_COMMAND: Final = "python -m config.replacement_migrate"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _render(
    key: str, method: str, path: str, body: Mapping[str, object] | None = None
) -> tuple[int, object]:
    """Make one bounded Render API call. Errors never carry the key or a body."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{_API}{path}", data=data, headers=headers, method=method
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            status = response.status
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (OSError, HTTPException, urllib.error.URLError):
        raise ValueError("render request failed") from None
    if status not in {200, 201, 202} or len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("render request failed")
    try:
        return status, json.loads(raw) if raw else None
    except (RecursionError, UnicodeError, ValueError):
        raise ValueError("render request failed") from None


def _get(key: str, path: str) -> object:
    return _render(key, "GET", path)[1]


def _service_id() -> str:
    try:
        return replacement_target_binding.load_render_staging_service_id()
    except replacement_target_binding.TargetBindingError:
        raise ValueError("render staging target unavailable") from None


def _prompt_key() -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("hidden prompt unavailable")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = getpass.getpass("Render API key: ", stream=sys.stderr)
        except getpass.GetPassWarning:
            raise ValueError("hidden prompt unavailable") from None
    # Render rejects a wrong key. This check only keeps the header intact.
    if not key or any(c.isspace() or not c.isprintable() for c in key):
        raise ValueError("render api key invalid")
    return key


def _preflight(key: str, service_id: str) -> None:
    """Require the exact Staging service settings, workspace, and an idle service."""
    service = _mapping(_get(key, f"/services/{service_id}"))
    details = _mapping(service.get("serviceDetails")) if service else None
    docker = _mapping(details.get("envSpecificDetails")) if details else None
    if service is None or details is None or docker is None:
        raise ValueError("staging configuration invalid")
    if not (
        service.get("id") == service_id
        and service.get("name") == "tailtag-api-staging"
        and service.get("type") == "web_service"
        and service.get("repo") == "https://github.com/TailTag-Game/tailtag"
        and service.get("branch") == "main"
        and service.get("autoDeployTrigger") == "off"
        and service.get("suspended") == "not_suspended"
        and details.get("runtime") == "docker"
        and details.get("healthCheckPath") == "/health/ready"
        and docker.get("preDeployCommand") == _PRE_DEPLOY_COMMAND
    ):
        raise ValueError("staging configuration invalid")
    owners = _get(key, "/owners?limit=100")
    if not isinstance(owners, list) or len(cast(list[object], owners)) != 1:
        raise ValueError("render workspace invalid")
    wrapper = _mapping(cast(list[object], owners)[0])
    owner = _mapping(wrapper.get("owner")) if wrapper else None
    if not (
        owner is not None
        and owner.get("type") == "team"
        and owner.get("id") == service.get("ownerId")
    ):
        raise ValueError("render workspace invalid")
    deploys = _get(key, f"/services/{service_id}/deploys?limit=20")
    if not isinstance(deploys, list):
        raise TypeError("deploys invalid")
    for item in cast(list[object], deploys):
        entry = _mapping(item)
        deploy = _mapping(entry.get("deploy")) if entry else None
        if deploy is None or not isinstance(deploy.get("status"), str):
            raise ValueError("deploys invalid")
        if deploy["status"] in _IN_PROGRESS:
            raise ValueError("staging deploy in progress")


def _submit(key: str, service_id: str, source_sha: str) -> str:
    status, payload = _render(
        key,
        "POST",
        f"/services/{service_id}/deploys",
        {"commitId": source_sha, "clearCache": "do_not_clear"},
    )
    deploy = _mapping(payload)
    deploy_id = deploy.get("id") if deploy else None
    if (
        status != 201
        or not isinstance(deploy_id, str)
        or _DEPLOY_ID.fullmatch(deploy_id) is None
    ):
        raise ValueError("deployment submission indeterminate")
    return deploy_id


def _deploy(key: str, service_id: str, record: Evidence) -> dict[str, object]:
    deploy = _mapping(
        _get(key, f"/services/{service_id}/deploys/{record['deployment_id']}")
    )
    if deploy is None or deploy.get("id") != record["deployment_id"]:
        raise ValueError("observation invalid")
    commit = _mapping(deploy.get("commit"))
    commit_id = commit.get("id") if commit else None
    if commit_id is not None and commit_id != record["source_sha"]:
        raise ValueError("observation invalid")
    return deploy


def _lifecycle(key: str, service_id: str, record: Evidence) -> bool:
    """Wait for D to finish and map its Render status to the #202 outcomes."""
    deadline = time.monotonic() + _DEPLOY_DEADLINE_SECONDS
    while True:
        deploy = _deploy(key, service_id, record)
        record["deployment_timestamp"] = _timestamp(deploy.get("createdAt"))
        if record["deployment_timestamp"] is None:
            raise ValueError("deployment timestamp invalid")
        status = deploy.get("status")
        if status in _IN_PROGRESS:
            if time.monotonic() >= deadline:
                record["overall_outcome"] = "INDETERMINATE"
                _persist(record)
                return False
            time.sleep(_POLL_SECONDS)
            continue
        break
    commit = _mapping(deploy.get("commit"))
    if (
        status == "live"
        and commit is not None
        and commit.get("id") == record["source_sha"]
    ):
        # Render goes live only after the pre-deploy step and health checks pass.
        record["deployment_outcome"] = "SUCCEEDED"
        record["migration_outcome"] = "SUCCEEDED"
        record["startup_outcome"] = "SUCCEEDED"
        record["readiness_outcome"] = "SUCCEEDED"
        _persist(record)
        return True
    record["deployment_outcome"] = "FAILED"
    record["overall_outcome"] = "FAILED"
    if status == "pre_deploy_failed":
        record["migration_outcome"] = "FAILED"
        record["overall_outcome"] = "OR7_HANDOFF"
    elif status == "update_failed":
        record["migration_outcome"] = "SUCCEEDED"
        record["startup_outcome"] = "INDETERMINATE"
        record["readiness_outcome"] = "FAILED"
    elif status not in {"build_failed", "canceled", "deactivated"}:
        record["deployment_outcome"] = "INDETERMINATE"
        record["overall_outcome"] = "INDETERMINATE"
    _persist(record)
    return False


def _final_active(key: str, service_id: str, record: Evidence) -> None:
    deploy = _deploy(key, service_id, record)
    status = deploy.get("status")
    if status == "live":
        record["final_active_state"] = "ACTIVE"
        record["overall_outcome"] = "SUCCEEDED"
        return
    if status != "deactivated":
        record["final_active_state"] = "INDETERMINATE"
        record["overall_outcome"] = "FAILED"
        return
    live = _get(key, f"/services/{service_id}/deploys?status=live&limit=20")
    if not isinstance(live, list):
        raise TypeError("active deployment invalid")
    others: list[object] = []
    for item in cast(list[object], live):
        entry = _mapping(item)
        other = _mapping(entry.get("deploy")) if entry else None
        if (
            other is None
            or other.get("status") != "live"
            or other.get("id") == record["deployment_id"]
        ):
            record["final_active_state"] = "INDETERMINATE"
            record["overall_outcome"] = "FAILED"
            return
        others.append(other)
    record["final_active_state"] = "SUPERSEDED" if others else "INACTIVE"
    record["overall_outcome"] = "SUPERSEDED" if others else "FAILED"


def main() -> int:
    record: Evidence | None = None
    source_sha: object = None
    submitted = False
    try:
        parser = _SafeArgumentParser()
        parser.add_argument("--source-sha", required=True)
        parser.add_argument("--confirm", required=True)
        arguments = parser.parse_args()
        source_sha = arguments.source_sha
        if (
            not isinstance(source_sha, str)
            or _SOURCE_SHA.fullmatch(source_sha) is None
            or arguments.confirm != _CONFIRMATION
        ):
            raise ValueError("arguments invalid")
        service_id = _service_id()
        evidence_directory = (
            _REPOSITORY_ROOT / "docs" / "development" / "staging-deployments"
        )
        evidence_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=evidence_directory):
            pass
        main_sha, validation = _eligible(source_sha)
        validation_id = validation.get("id")
        validation_attempt = validation.get("run_attempt")
        if (
            type(validation_id) is not int
            or validation_id <= 0
            or type(validation_attempt) is not int
            or validation_attempt <= 0
        ):
            raise ValueError("validation record invalid")
        key = _prompt_key()
        _preflight(key, service_id)
        submitted = True
        deployment_id = _submit(key, service_id, source_sha)
        record = _new_evidence(source_sha, main_sha, validation, deployment_id)
        _persist(record)
        if not _lifecycle(key, service_id, record):
            return _result(record)
        try:
            api_staging_preflight.validate_render_staging_target(source_sha)
        except api_staging_preflight.TargetSafetyError:
            record["identity_outcome"] = "FAILED"
            record["overall_outcome"] = "FAILED"
            _persist(record)
            return _result(record)
        record["identity_outcome"] = "SUCCEEDED"
        _persist(record)
        smoke_environment = dict(os.environ)
        smoke_environment["API_BASE_URL"] = (
            api_staging_preflight.render_staging_origin()
        )
        smoke = _run(["task", "api-smoke"], env=smoke_environment, cwd=_REPOSITORY_ROOT)
        if smoke.returncode != 0:
            record["smoke_outcome"] = "FAILED"
            record["overall_outcome"] = "FAILED"
            _persist(record)
            return _result(record)
        record["smoke_outcome"] = "SUCCEEDED"
        _persist(record)
        _final_active(key, service_id, record)
        _persist(record)
        return _result(record)
    except KeyboardInterrupt:
        if record is not None:
            record["overall_outcome"] = "INDETERMINATE"
            try:
                _persist(record)
                return _result(record)
            except (OSError, ValueError):
                pass
        if submitted and record is None:
            print(
                f"FAIL promotion submission indeterminate {source_sha}",
                file=sys.stderr,
            )
            return 1
        print("FAIL promotion interrupted", file=sys.stderr)
        return 1
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
        api_staging_preflight.TargetSafetyError,
    ):
        if record is not None:
            record["overall_outcome"] = "INDETERMINATE"
            try:
                _persist(record)
                return _result(record)
            except (OSError, ValueError):
                print(
                    f"FAIL promotion evidence unavailable for {record['source_sha']} "
                    f"{record['deployment_id']} "
                    f"docs/development/staging-deployments/{record['deployment_id']}.json",
                    file=sys.stderr,
                )
                return 1
        if submitted:
            # Render may have accepted the deploy although no D came back.
            print(
                f"FAIL promotion submission indeterminate {source_sha}",
                file=sys.stderr,
            )
            return 1
        print("FAIL promotion unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
