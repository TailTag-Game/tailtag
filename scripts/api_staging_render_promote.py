"""Promote one eligible immutable TailTag commit to Render Staging (#409)."""

from __future__ import annotations

import argparse
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
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from typing import Final, NoReturn, TypedDict, cast

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts import api_staging_preflight

from config import replacement_target_binding

_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
_REPOSITORY: Final = "TailTag-Game/tailtag"
_API: Final = "https://api.render.com/v1"
_CONFIRMATION: Final = "promote-tailtag-render-staging"
_DEPLOY_ID: Final = re.compile(r"dep-[a-z0-9]{1,60}")
_MAX_RESPONSE_BYTES: Final = 1_048_576
_TIMEOUT_SECONDS: Final = 30
# A Render deploy builds the image, runs the pre-deploy migration, and waits up
# to 15 minutes for health checks before it goes live.
_DEPLOY_DEADLINE_SECONDS: Final = 30 * 60
_POLL_SECONDS: Final = 10
# After a deploy goes live, Render keeps the old instance serving while it
# drains, for up to 300 seconds. The public identity can show the old SHA then.
_IDENTITY_DEADLINE_SECONDS: Final = 5 * 60
_IDENTITY_POLL_SECONDS: Final = 5
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


class Evidence(TypedDict):
    source_sha: str
    deployment_id: str
    environment: str
    deployment_timestamp: str | None
    accepted_main_sha: str
    validation_run_id: int
    validation_run_attempt: int
    deployment_outcome: str
    migration_outcome: str
    startup_outcome: str
    readiness_outcome: str
    identity_outcome: str
    smoke_outcome: str
    final_active_state: str
    overall_outcome: str


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("arguments invalid")


def _run(
    arguments: list[str],
    *,
    input: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        timeout=_TIMEOUT_SECONDS,
        input=input,
        env=env,
        cwd=cwd,
    )


def _json_command(
    arguments: list[str], *, input: str | None = None
) -> Mapping[str, object]:
    completed = _run(arguments, input=input)
    if completed.returncode != 0:
        raise ValueError("external operation failed")
    try:
        value: object = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("external operation failed") from error
    if not isinstance(value, dict):
        raise TypeError("external operation failed")
    response = cast(dict[str, object], value)
    if response.get("errors"):
        raise ValueError("external operation failed")
    return response


def _mapping(value: object) -> dict[str, object] | None:
    return (
        dict(cast(Mapping[str, object], value)) if isinstance(value, Mapping) else None
    )


def _gh(endpoint: str) -> Mapping[str, object]:
    identity = _run(["gh", "api", "user", "--jq", ".login"])
    if identity.returncode != 0 or identity.stdout.strip() != "FinnThePanther":
        raise ValueError("github identity unavailable")
    return _json_command(["gh", "api", endpoint])


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        value if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    )


def _evidence_path(deployment_id: str) -> Path:
    return (
        _REPOSITORY_ROOT
        / "docs"
        / "development"
        / "staging-deployments"
        / f"{deployment_id}.json"
    )


def _persist(record: Evidence) -> None:
    path = _evidence_path(record["deployment_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, sort_keys=True) + "\n")
    temporary.replace(path)


def _new_evidence(
    source_sha: str, main_sha: str, run: Mapping[str, object], deployment_id: str
) -> Evidence:
    run_id = run.get("id")
    attempt = run.get("run_attempt")
    if (
        type(run_id) is not int
        or run_id <= 0
        or type(attempt) is not int
        or attempt <= 0
    ):
        raise ValueError("validation record invalid")
    return {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": "staging",
        "deployment_timestamp": None,
        "accepted_main_sha": main_sha,
        "validation_run_id": run_id,
        "validation_run_attempt": attempt,
        "deployment_outcome": "PENDING",
        "migration_outcome": "PENDING",
        "startup_outcome": "PENDING",
        "readiness_outcome": "PENDING",
        "identity_outcome": "PENDING",
        "smoke_outcome": "PENDING",
        "final_active_state": "NOT_CHECKED",
        "overall_outcome": "PENDING",
    }


def _eligible(source_sha: str) -> tuple[str, Mapping[str, object]]:
    commit = _gh(f"/repos/{_REPOSITORY}/commits/{source_sha}")
    if commit.get("sha") != source_sha:
        raise ValueError("candidate invalid")
    main = _gh(f"/repos/{_REPOSITORY}/commits/main")
    main_sha = main.get("sha")
    if not isinstance(main_sha, str) or _SOURCE_SHA.fullmatch(main_sha) is None:
        raise ValueError("main invalid")
    comparison = _gh(
        f"/repos/{_REPOSITORY}/compare/{source_sha}...{main_sha}?per_page=1"
    )
    base = _mapping(comparison.get("base_commit"))
    merge_base = _mapping(comparison.get("merge_base_commit"))
    if not (
        base is not None
        and merge_base is not None
        and base.get("sha") == source_sha
        and merge_base.get("sha") == source_sha
        and comparison.get("behind_by") == 0
        and comparison.get("status") in {"ahead", "identical"}
    ):
        raise ValueError("candidate ineligible")
    page = 1
    selected: dict[str, object] | None = None
    while True:
        runs = _gh(
            f"/repos/{_REPOSITORY}/actions/workflows/api.yml/runs?head_sha={source_sha}&event=push&status=success&per_page=100&page={page}"
        )
        raw_rows = runs.get("workflow_runs")
        if not isinstance(raw_rows, list):
            raise TypeError("validation unavailable")
        rows = cast(list[object], raw_rows)
        for row in rows:
            candidate = _mapping(row)
            repository = _mapping(candidate.get("repository")) if candidate else None
            if (
                candidate is not None
                and type(candidate.get("id")) is int
                and repository is not None
                and repository.get("full_name") == _REPOSITORY
                and candidate.get("path") == ".github/workflows/api.yml"
                and candidate.get("head_sha") == source_sha
                and candidate.get("event") == "push"
                and candidate.get("status") == "completed"
                and candidate.get("conclusion") == "success"
            ):
                selected = candidate
                break
        if selected is not None or len(rows) < 100:
            break
        page += 1
    if selected is None or type(selected.get("id")) is not int:
        raise ValueError("validation unavailable")
    verified = _gh(f"/repos/{_REPOSITORY}/actions/runs/{selected['id']}")
    repository = _mapping(verified.get("repository"))
    if not (
        repository is not None
        and repository.get("full_name") == _REPOSITORY
        and verified.get("id") == selected.get("id")
        and verified.get("path") == ".github/workflows/api.yml"
        and verified.get("head_sha") == source_sha
        and verified.get("event") == "push"
        and verified.get("status") == "completed"
        and verified.get("conclusion") == "success"
    ):
        raise ValueError("validation unavailable")
    return main_sha, verified


def _result(record: Evidence) -> int:
    print(
        f"promotion {record['source_sha']} {record['deployment_id']} "
        f"{record['overall_outcome']} "
        f"docs/development/staging-deployments/{record['deployment_id']}.json"
    )
    return 0 if record["overall_outcome"] == "SUCCEEDED" else 1


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
        and service.get("name") == "tailtag-api-stg"
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
    # A classic key reaches every workspace of the account. So the key must see
    # the one team workspace that owns the pinned service, among any others.
    owners = _get(key, "/owners?limit=100")
    if not isinstance(owners, list):
        raise TypeError("render workspace invalid")
    matches: list[dict[str, object]] = []
    for item in cast(list[object], owners):
        wrapper = _mapping(item)
        owner = _mapping(wrapper.get("owner")) if wrapper else None
        if owner is None:
            raise ValueError("render workspace invalid")
        if owner.get("id") == service.get("ownerId"):
            matches.append(owner)
    if len(matches) != 1 or matches[0].get("type") != "team":
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


def _public_identity_converges(source_sha: str) -> bool:
    """Read the public identity until it stably shows S, within a bounded wait."""
    deadline = time.monotonic() + _IDENTITY_DEADLINE_SECONDS
    while True:
        try:
            api_staging_preflight.validate_render_staging_target(source_sha)
        except api_staging_preflight.TargetSafetyError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(_IDENTITY_POLL_SECONDS)
        else:
            return True


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
        if not _public_identity_converges(source_sha):
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
