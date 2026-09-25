"""Promote one eligible immutable TailTag commit to the canonical Staging API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final, NoReturn, TypedDict, cast

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from scripts.api_staging_reset_ssh import (
    _target_ids,  # pyright: ignore[reportPrivateUsage]
)

_TargetIds = tuple[str, str, str, str]
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
_REPOSITORY: Final = "TailTag-Game/tailtag"
_TIMEOUT_SECONDS: Final = 30
_REQUIRED_EVENTS: Final = frozenset(
    {"PRE_DEPLOY_COMMAND", "CREATE_CONTAINER", "HEALTHCHECK"}
)
_EVIDENCE_FIELDS: Final = frozenset(
    {
        "source_sha",
        "deployment_id",
        "environment",
        "deployment_timestamp",
        "accepted_main_sha",
        "validation_run_id",
        "validation_run_attempt",
        "deployment_outcome",
        "migration_outcome",
        "startup_outcome",
        "readiness_outcome",
        "identity_outcome",
        "smoke_outcome",
        "final_active_state",
        "overall_outcome",
    }
)

_CONFIG_QUERY: Final = """query PromotionConfiguration($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId environmentId source { repo image } preDeployCommand healthcheckPath
  }
}"""
_TRIGGERS_QUERY: Final = """query PromotionTriggers($projectId: String!, $serviceId: String!, $environmentId: String!) {
  deploymentTriggers(projectId: $projectId, serviceId: $serviceId, environmentId: $environmentId) {
    edges { node { id } } pageInfo { hasNextPage endCursor }
  }
}"""
_MUTATION: Final = """mutation PromoteStaging($serviceId: String!, $environmentId: String!, $commitSha: String!) {
  serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId, commitSha: $commitSha)
}"""
_OBSERVATION_QUERY: Final = """query PromotionObservation($id: String!, $after: String) {
  deployment(id: $id) { id projectId serviceId environmentId createdAt status deploymentStopped environment { name } instances { id status } }
  deploymentEvents(id: $id, first: 100, after: $after) { edges { node { id step completedAt payload { skipped error } } } pageInfo { hasNextPage endCursor } }
}"""
_ACTIVE_QUERY: Final = """query PromotionActive($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId environmentId activeDeployments { id projectId serviceId environmentId status instances { id status } }
  }
}"""


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


def _railway(query: str, variables: Mapping[str, object]) -> Mapping[str, object]:
    return _json_command(
        ["railway", "api", query, "--variables", json.dumps(variables)]
    )


def _data(response: Mapping[str, object], key: str) -> Mapping[str, object]:
    data = _mapping(response.get("data"))
    if data is None:
        raise TypeError("response invalid")
    value = data.get(key)
    result = _mapping(value)
    if result is None:
        raise TypeError("response invalid")
    return result


def _uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return value if str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


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


def _preflight(target: _TargetIds) -> None:
    project_id, environment_id, service_id, _ = target
    selectors = {"serviceId": service_id, "environmentId": environment_id}
    config = _data(_railway(_CONFIG_QUERY, selectors), "serviceInstance")
    source = _mapping(config.get("source"))
    command = config.get("preDeployCommand")
    if not (
        config.get("serviceId") == service_id
        and config.get("environmentId") == environment_id
        and source is not None
        and source.get("repo") == _REPOSITORY
        and "image" in source
        and source.get("image") is None
        and command
        == ["python manage.py migrate --settings=config.settings.production --noinput"]
        and config.get("healthcheckPath") == "/health/ready"
    ):
        raise ValueError("staging configuration invalid")
    triggers = _data(
        _railway(_TRIGGERS_QUERY, {"projectId": project_id, **selectors}),
        "deploymentTriggers",
    )
    page_info = _mapping(triggers.get("pageInfo"))
    if (
        not isinstance(triggers.get("edges"), list)
        or triggers["edges"]
        or page_info is None
        or type(page_info.get("hasNextPage")) is not bool
        or page_info["hasNextPage"]
    ):
        raise ValueError("staging autodeploy enabled")


def _deployment_valid(
    deployment: Mapping[str, object], deployment_id: str, target: _TargetIds
) -> bool:
    project_id, environment_id, service_id, _ = target
    environment = _mapping(deployment.get("environment"))
    return (
        deployment.get("id") == deployment_id
        and deployment.get("projectId") == project_id
        and deployment.get("serviceId") == service_id
        and deployment.get("environmentId") == environment_id
        and environment is not None
        and environment.get("name") == "staging"
    )


def _event_outcome(events: list[Mapping[str, object]], step: str) -> str:
    matching = [event for event in events if event.get("step") == step]
    if len(matching) != 1:
        return "INDETERMINATE"
    event = matching[0]
    if _timestamp(event.get("completedAt")) is None or "payload" not in event:
        return "INDETERMINATE"
    raw_payload = event["payload"]
    if raw_payload is None:
        return "SUCCEEDED"
    payload = _mapping(raw_payload)
    if payload is None:
        return "INDETERMINATE"
    if set(payload) != {"skipped", "error"}:
        return "INDETERMINATE"
    skipped = payload.get("skipped")
    error = payload.get("error")
    if (skipped is not None and type(skipped) is not bool) or (
        error is not None and not isinstance(error, str)
    ):
        return "INDETERMINATE"
    if payload.get("skipped") is True or payload.get("error") is not None:
        return "FAILED"
    return "SUCCEEDED"


def _lifecycle(record: Evidence, target: _TargetIds) -> Mapping[str, object] | None:
    after: str | None = None
    cursors: set[str] = set()
    events: list[Mapping[str, object]] = []
    deadline = time.monotonic() + 20 * 60
    while True:
        if time.monotonic() >= deadline:
            record["overall_outcome"] = "INDETERMINATE"
            _persist(record)
            return None
        response = _railway(
            _OBSERVATION_QUERY, {"id": record["deployment_id"], "after": after}
        )
        data = _mapping(response.get("data"))
        if data is None:
            raise TypeError("observation invalid")
        deployment = _mapping(data.get("deployment"))
        connection = _mapping(data.get("deploymentEvents"))
        if (
            deployment is None
            or connection is None
            or not _deployment_valid(deployment, record["deployment_id"], target)
        ):
            raise ValueError("observation invalid")
        raw_edges = connection.get("edges")
        info = _mapping(connection.get("pageInfo"))
        if not isinstance(raw_edges, list) or info is None:
            raise TypeError("observation invalid")
        edges = cast(list[object], raw_edges)
        for edge in edges:
            edge_data = _mapping(edge)
            node = _mapping(edge_data.get("node")) if edge_data else None
            if node is None:
                raise TypeError("observation invalid")
            events.append(node)
        has_next_page = info.get("hasNextPage")
        if type(has_next_page) is not bool:
            raise ValueError("observation invalid")
        if has_next_page:
            cursor = info.get("endCursor")
            if not isinstance(cursor, str) or cursor in cursors:
                raise ValueError("observation invalid")
            cursors.add(cursor)
            after = cursor
            continue
        status = deployment.get("status")
        record["deployment_timestamp"] = _timestamp(deployment.get("createdAt"))
        if record["deployment_timestamp"] is None:
            raise ValueError("deployment timestamp invalid")
        record["migration_outcome"] = _event_outcome(events, "PRE_DEPLOY_COMMAND")
        record["startup_outcome"] = _event_outcome(events, "CREATE_CONTAINER")
        record["readiness_outcome"] = _event_outcome(events, "HEALTHCHECK")
        if status != "SUCCESS":
            if (
                status in {"INITIALIZING", "QUEUED", "WAITING", "BUILDING", "DEPLOYING"}
                and time.monotonic() < deadline
            ):
                events.clear()
                cursors.clear()
                after = None
                time.sleep(5)
                continue
            record["deployment_outcome"] = (
                "FAILED"
                if status
                in {
                    "CRASHED",
                    "FAILED",
                    "SKIPPED",
                    "REMOVED",
                    "REMOVING",
                    "NEEDS_APPROVAL",
                    "SLEEPING",
                }
                else "INDETERMINATE"
            )
            record["overall_outcome"] = (
                "FAILED"
                if record["deployment_outcome"] == "FAILED"
                else "INDETERMINATE"
            )
            if record["migration_outcome"] in {"FAILED", "INDETERMINATE"}:
                record["overall_outcome"] = "OR7_HANDOFF"
            _persist(record)
            return None
        record["deployment_outcome"] = "SUCCEEDED"
        if any(
            record[key] != "SUCCEEDED"
            for key in ("migration_outcome", "startup_outcome", "readiness_outcome")
        ):
            record["overall_outcome"] = (
                "OR7_HANDOFF"
                if record["migration_outcome"] in {"FAILED", "INDETERMINATE"}
                else (
                    "FAILED"
                    if "FAILED"
                    in {record["startup_outcome"], record["readiness_outcome"]}
                    else "INDETERMINATE"
                )
            )
            _persist(record)
            return None
        _persist(record)
        raw_instances = deployment.get("instances")
        if not isinstance(raw_instances, list):
            raise TypeError("instance invalid")
        instances = cast(list[object], raw_instances)
        for instance in instances:
            instance_data = _mapping(instance)
            if (
                instance_data
                and instance_data.get("status") == "RUNNING"
                and isinstance(instance_data.get("id"), str)
            ):
                selected = dict(deployment)
                selected["running_instance_id"] = instance_data["id"]
                return selected
        record["identity_outcome"] = "INDETERMINATE"
        record["overall_outcome"] = "INDETERMINATE"
        _persist(record)
        return None


def _identity(record: Evidence, instance_id: str, target: _TargetIds) -> bool:
    project_id, environment_id, service_id, _ = target
    ssh = _run(
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
            instance_id,
            "--",
            "uv",
            "run",
            "--locked",
            "--no-sync",
            "python",
            "-m",
            "config.build_identity",
        ]
    )
    if ssh.returncode != 0:
        return False
    try:
        raw_identity: object = json.loads(ssh.stdout)
    except (UnicodeError, json.JSONDecodeError):
        return False
    identity = _mapping(raw_identity)
    if identity != {
        "source_sha": record["source_sha"],
        "deployment_id": record["deployment_id"],
        "environment": "staging",
    }:
        return False
    joined = _json_command(
        [
            sys.executable,
            str(_REPOSITORY_ROOT / "scripts" / "api_deployment_identity.py"),
        ],
        input=ssh.stdout,
    )
    return joined == {
        "source_sha": record["source_sha"],
        "deployment_id": record["deployment_id"],
        "environment": "staging",
        "deployment_timestamp": record["deployment_timestamp"],
    }


def _final_active(record: Evidence, target: _TargetIds) -> None:
    project_id, environment_id, service_id, _ = target
    response = _railway(
        _ACTIVE_QUERY, {"serviceId": service_id, "environmentId": environment_id}
    )
    service_instance = _data(response, "serviceInstance")
    if (
        service_instance.get("serviceId") != service_id
        or service_instance.get("environmentId") != environment_id
    ):
        raise ValueError("active deployment invalid")
    raw_active = service_instance.get("activeDeployments")
    if not isinstance(raw_active, list):
        raise TypeError("active deployment invalid")
    active = cast(list[object], raw_active)
    target_deployment: dict[str, object] | None = None
    for item in active:
        candidate = _mapping(item)
        instances = candidate.get("instances") if candidate else None
        valid_instances = isinstance(instances, list) and all(
            (instance_data := _mapping(instance)) is not None
            and isinstance(instance_data.get("id"), str)
            and isinstance(instance_data.get("status"), str)
            for instance in cast(list[object], instances)
        )
        if not (
            candidate is not None
            and _uuid(candidate.get("id")) is not None
            and candidate.get("projectId") == project_id
            and candidate.get("serviceId") == service_id
            and candidate.get("environmentId") == environment_id
            and isinstance(candidate.get("status"), str)
            and valid_instances
        ):
            record["final_active_state"] = "INDETERMINATE"
            record["overall_outcome"] = "INDETERMINATE"
            return
        if candidate and candidate.get("id") == record["deployment_id"]:
            target_deployment = candidate
            break
    if target_deployment is None:
        record["final_active_state"] = "SUPERSEDED" if active else "INACTIVE"
        record["overall_outcome"] = "SUPERSEDED" if active else "FAILED"
        return
    raw_instances = target_deployment.get("instances")
    instances = (
        cast(list[object], raw_instances) if isinstance(raw_instances, list) else []
    )
    running = any(
        (_mapping(item) or {}).get("status") == "RUNNING" for item in instances
    )
    if (
        target_deployment.get("id") == record["deployment_id"]
        and target_deployment.get("projectId") == project_id
        and target_deployment.get("serviceId") == service_id
        and target_deployment.get("environmentId") == environment_id
        and target_deployment.get("status") == "SUCCESS"
        and running
    ):
        record["final_active_state"] = "ACTIVE"
        record["overall_outcome"] = "SUCCEEDED"
    else:
        record["final_active_state"] = "INDETERMINATE"
        record["overall_outcome"] = "FAILED"


def _railway_identity() -> None:
    response = _json_command(["railway", "whoami", "--json"])
    if (
        response.get("name") != "Finn the Panther"
        or response.get("email") != "finn@finnthepanther.com"
    ):
        raise ValueError("railway identity unavailable")


def parse_arguments() -> argparse.Namespace:
    parser = _SafeArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def _result(record: Evidence) -> int:
    print(
        f"promotion {record['source_sha']} {record['deployment_id']} "
        f"{record['overall_outcome']} "
        f"docs/development/staging-deployments/{record['deployment_id']}.json"
    )
    return 0 if record["overall_outcome"] == "SUCCEEDED" else 1


def main() -> int:
    record: Evidence | None = None
    try:
        arguments = parse_arguments()
        source_sha = arguments.source_sha
        if (
            not isinstance(source_sha, str)
            or _SOURCE_SHA.fullmatch(source_sha) is None
            or arguments.confirm != "promote-tailtag-staging"
        ):
            raise ValueError("arguments invalid")
        target = _target_ids()
        evidence_directory = (
            _REPOSITORY_ROOT / "docs" / "development" / "staging-deployments"
        )
        evidence_directory.mkdir(parents=True, exist_ok=True)
        if not evidence_directory.is_dir():
            raise ValueError("evidence unavailable")
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
        _railway_identity()
        _preflight(target)
        _railway_identity()
        mutation = _railway(
            _MUTATION,
            {
                "serviceId": target[2],
                "environmentId": target[1],
                "commitSha": source_sha,
            },
        )
        data = _mapping(mutation.get("data"))
        deployment_id = data.get("serviceInstanceDeployV2") if data else None
        if _uuid(deployment_id) is None:
            raise ValueError("deployment submission indeterminate")
        record = _new_evidence(
            source_sha, main_sha, validation, cast(str, deployment_id)
        )
        _persist(record)
        lifecycle = _lifecycle(record, target)
        if lifecycle is None:
            return _result(record)
        instance_id = lifecycle.get("running_instance_id")
        if not isinstance(instance_id, str) or not _identity(
            record, instance_id, target
        ):
            record["identity_outcome"] = "FAILED"
            record["overall_outcome"] = "FAILED"
            _persist(record)
            return _result(record)
        record["identity_outcome"] = "SUCCEEDED"
        _persist(record)
        smoke_environment = dict(os.environ)
        smoke_environment["API_BASE_URL"] = "https://staging.tailtag.app"
        smoke = _run(["make", "api-smoke"], env=smoke_environment, cwd=_REPOSITORY_ROOT)
        if smoke.returncode != 0:
            record["smoke_outcome"] = "FAILED"
            record["overall_outcome"] = "FAILED"
            _persist(record)
            return _result(record)
        record["smoke_outcome"] = "SUCCEEDED"
        _persist(record)
        _final_active(record, target)
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
        print("FAIL promotion interrupted", file=sys.stderr)
        return 1
    except (OSError, TypeError, UnicodeError, ValueError, subprocess.SubprocessError):
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
        print("FAIL promotion unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
