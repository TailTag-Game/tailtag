"""Offline acceptance contract for the exact-SHA Staging promotion operator."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_promote.py"
SOURCE_SHA = "eb518d36baa21b7943acd9744f2499d80d527e61"
MAIN_SHA = "2586ade0c1115e090044c9385831b33538918dcf"
OTHER_SHA = "a" * 40
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
OTHER_DEPLOYMENT_ID = "1b6a4b35-4e94-4775-a4b9-304205c75786"
RUNNING_INSTANCE_ID = "46d09c1e-9c09-4f31-8b86-4ce9b667c70b"
STOPPED_INSTANCE_ID = "674ca47c-37ca-4658-a6d8-85048c7e8fca"
PROJECT_ID = "a1111111-1111-4111-8111-111111111111"
SERVICE_ID = "d4444444-4444-4444-8444-444444444444"
ENVIRONMENT_ID = "33333333-3333-4333-8333-333333333333"
POSTGRES_SERVICE_ID = "55555555-5555-4555-8555-555555555555"
RETIRED_PROJECT_ID = "85324de4-be6a-49c3-a3f9-6cac13877849"
CREATED_AT = "2026-09-17T00:16:10.526Z"
RUN_ID = 35179642379
SENSITIVE_SENTINEL = "promotion-untrusted-diagnostic-secret"
EVIDENCE_FIELDS = {
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
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def completed(
    payload: object, *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Build one captured subprocess result without exposing an external boundary."""
    return subprocess.CompletedProcess(
        args=("offline",),
        returncode=returncode,
        stdout=payload if isinstance(payload, str) else json.dumps(payload),
        stderr=stderr,
    )


def stage_event(
    step: str,
    *,
    completed_at: str | None = "2026-09-17T00:18:00.000Z",
    skipped: object = None,
    error: object = None,
) -> dict[str, object]:
    return {
        "id": f"event-{step}",
        "step": step,
        "completedAt": completed_at,
        "payload": {"skipped": skipped, "error": error},
    }


def deployment(
    *,
    deployment_id: str = DEPLOYMENT_ID,
    status: str = "SUCCESS",
    instances: list[dict[str, str]] | None = None,
    project_id: str = PROJECT_ID,
    service_id: str = SERVICE_ID,
    environment_id: str = ENVIRONMENT_ID,
    created_at: object = CREATED_AT,
) -> dict[str, object]:
    return {
        "id": deployment_id,
        "projectId": project_id,
        "serviceId": service_id,
        "environmentId": environment_id,
        "createdAt": created_at,
        "status": status,
        "deploymentStopped": False,
        "environment": {"name": "staging"},
        "instances": instances
        or [
            {"id": STOPPED_INSTANCE_ID, "status": "REMOVED"},
            {"id": RUNNING_INSTANCE_ID, "status": "RUNNING"},
        ],
    }


def active_deployment(
    *,
    deployment_id: str = DEPLOYMENT_ID,
    status: str = "SUCCESS",
    instances: list[dict[str, str]] | None = None,
    project_id: str = PROJECT_ID,
    service_id: str = SERVICE_ID,
    environment_id: str = ENVIRONMENT_ID,
) -> dict[str, object]:
    """Return exactly the frozen ACTIVE_QUERY projection, no lifecycle-only fields."""
    return {
        "id": deployment_id,
        "projectId": project_id,
        "serviceId": service_id,
        "environmentId": environment_id,
        "status": status,
        "instances": instances
        or [
            {"id": STOPPED_INSTANCE_ID, "status": "REMOVED"},
            {"id": RUNNING_INSTANCE_ID, "status": "RUNNING"},
        ],
    }


def canonical_config(**overrides: object) -> dict[str, object]:
    """Return only the allowlisted configuration facts needed by the contract."""
    return {
        "serviceId": SERVICE_ID,
        "environmentId": ENVIRONMENT_ID,
        "source": {"repo": "TailTag-Game/tailtag", "image": None},
        "preDeployCommand": ["python -m config.replacement_migrate"],
        "healthcheckPath": "/health/ready",
        **overrides,
    }


@pytest.fixture
def staging_promote(monkeypatch: MonkeyPatch) -> ModuleType:
    """Load the operator only after its production file exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_promote.py must exist"
    operator = importlib.import_module("scripts.api_staging_promote")
    monkeypatch.setattr(
        operator,
        "_target_ids",
        lambda: (PROJECT_ID, ENVIRONMENT_ID, SERVICE_ID, POSTGRES_SERVICE_ID),
        raising=False,
    )
    return operator


class PromotionSubprocess:
    """Strict deterministic stand-in for the approved gh/Railway/SSH boundaries."""

    def __init__(
        self,
        evidence_file: Path,
        *,
        comparison: Mapping[str, object] | None = None,
        resolved_source_sha: str = SOURCE_SHA,
        run_pages: tuple[list[dict[str, object]], ...] | None = None,
        validated_run: Mapping[str, object] | None = None,
        observation_events: tuple[list[dict[str, object]], ...] | None = None,
        page_infos: tuple[Mapping[str, object], ...] | None = None,
        observed_deployment: Mapping[str, object] | None = None,
        active_deployments: list[dict[str, object]] | None = None,
        active_service_id: str = SERVICE_ID,
        active_environment_id: str = ENVIRONMENT_ID,
        joined_identity: Mapping[str, object] | None = None,
        config: Mapping[str, object] | None = None,
        deployment_triggers: Mapping[str, object] | None = None,
        smoke_returncode: int = 0,
        expected_smoke_cwd: Path | None = None,
        identity: str = "FinnThePanther",
        fail_mutation: bool = False,
        mutation_result: object = DEPLOYMENT_ID,
        on_mutation: Callable[[], None] | None = None,
        interrupt_observation: bool = False,
        observation_error: BaseException | None = None,
        mutation_error: str = SENSITIVE_SENTINEL,
        ssh_stdout: str | None = None,
    ) -> None:
        self.evidence_file = evidence_file
        self.comparison = comparison or {
            "base_commit": {"sha": SOURCE_SHA},
            "merge_base_commit": {"sha": SOURCE_SHA},
            "behind_by": 0,
            "status": "ahead",
        }
        self.resolved_source_sha = resolved_source_sha
        self.run_pages = run_pages or ([self.workflow_run()],)
        self.validated_run = validated_run or self.workflow_run()
        self.observation_events = observation_events or (
            [stage_event("PRE_DEPLOY_COMMAND")],
            [stage_event("CREATE_CONTAINER"), stage_event("HEALTHCHECK")],
        )
        self.observed_deployment = observed_deployment or deployment()
        self.page_infos = page_infos
        self.active_deployments = (
            active_deployments
            if active_deployments is not None
            else [active_deployment()]
        )
        self.active_service_id = active_service_id
        self.active_environment_id = active_environment_id
        self.joined_identity = joined_identity or {
            "source_sha": SOURCE_SHA,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
            "deployment_timestamp": CREATED_AT,
        }
        self.config = config or canonical_config()
        self.deployment_triggers = deployment_triggers or {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
        self.smoke_returncode = smoke_returncode
        self.expected_smoke_cwd = expected_smoke_cwd
        self.identity = identity
        self.fail_mutation = fail_mutation
        self.mutation_result = mutation_result
        self.on_mutation = on_mutation
        self.interrupt_observation = interrupt_observation
        self.observation_error = observation_error
        self.mutation_error = mutation_error
        self.calls: list[tuple[str, ...]] = []
        self.options: list[Mapping[str, object]] = []
        self.mutation_count = 0
        self.observation_count = 0
        self.ssh_stdout = ssh_stdout or json.dumps(
            {
                "source_sha": SOURCE_SHA,
                "deployment_id": DEPLOYMENT_ID,
                "environment": "staging",
            }
        )

    @staticmethod
    def _variables(command: tuple[str, ...]) -> Mapping[str, object]:
        if "--variables" in command:
            return cast(
                Mapping[str, object],
                json.loads(command[command.index("--variables") + 1]),
            )
        raw_values = [argument for argument in command if argument.startswith("id=")]
        if raw_values:
            return {"id": raw_values[-1].removeprefix("id=")}
        return {}

    @staticmethod
    def workflow_run(*, run_id: int = RUN_ID, **overrides: object) -> dict[str, object]:
        return {
            "id": run_id,
            "run_attempt": 1,
            "path": ".github/workflows/api.yml",
            "repository": {"full_name": "TailTag-Game/tailtag"},
            "head_sha": SOURCE_SHA,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            **overrides,
        }

    def _graphql(self, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        query = command[2]
        variables = self._variables(command)
        if "serviceInstanceDeployV2" in query:
            assert self.calls[-2] == ("railway", "whoami", "--json")
            self.mutation_count += 1
            assert variables == {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
                "commitSha": SOURCE_SHA,
            }
            if self.fail_mutation:
                return completed({"errors": [{"message": self.mutation_error}]})
            if self.on_mutation is not None:
                self.on_mutation()
            return completed(
                {"data": {"serviceInstanceDeployV2": self.mutation_result}}
            )
        if "deploymentEvents" in query:
            assert variables.get("id") == DEPLOYMENT_ID
            assert self.evidence_file.is_file(), (
                "S/D must be checkpointed before lifecycle observation"
            )
            checkpoint = json.loads(self.evidence_file.read_text())
            assert checkpoint["source_sha"] == SOURCE_SHA
            assert checkpoint["deployment_id"] == DEPLOYMENT_ID
            if self.interrupt_observation:
                raise KeyboardInterrupt
            if self.observation_error is not None:
                raise self.observation_error
            expected_after = None if self.observation_count == 0 else "cursor-1"
            assert variables.get("after") == expected_after
            page = self.observation_events[self.observation_count]
            self.observation_count += 1
            return completed(
                {
                    "data": {
                        "deployment": self.observed_deployment,
                        "deploymentEvents": {
                            "edges": [{"node": event} for event in page],
                            "pageInfo": self.page_infos[self.observation_count - 1]
                            if self.page_infos is not None
                            else {
                                "hasNextPage": self.observation_count
                                < len(self.observation_events),
                                "endCursor": "cursor-1"
                                if self.observation_count == 1
                                else None,
                            },
                        },
                    }
                }
            )
        if "activeDeployments" in query:
            assert "createdAt" not in query
            assert "environment { name }" not in query
            assert variables == {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
            }
            return completed(
                {
                    "data": {
                        "serviceInstance": {
                            "serviceId": self.active_service_id,
                            "environmentId": self.active_environment_id,
                            "activeDeployments": self.active_deployments,
                        }
                    }
                }
            )
        if "deployment(id:" in query:
            assert variables == {"id": DEPLOYMENT_ID}
            return completed({"data": {"deployment": self.observed_deployment}})
        if "deploymentTriggers" in query:
            assert variables == {
                "projectId": PROJECT_ID,
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
            }
            return completed({"data": {"deploymentTriggers": self.deployment_triggers}})
        if "preDeployCommand" in query:
            assert variables == {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
            }
            return completed({"data": {"serviceInstance": self.config}})
        raise AssertionError(f"unapproved Railway GraphQL operation: {query}")

    def __call__(
        self, arguments: object, **options: object
    ) -> subprocess.CompletedProcess[str]:
        assert isinstance(arguments, (list, tuple))
        command_arguments = cast(list[object] | tuple[object, ...], arguments)
        command = tuple(str(argument) for argument in command_arguments)
        self.calls.append(command)
        self.options.append(options)
        assert options.get("shell") is False
        assert options.get("capture_output") is True
        assert options.get("text") is True
        assert options.get("timeout") == 30
        if command[:4] == ("gh", "api", "user", "--jq"):
            assert command[4:] == (".login",)
            return completed(self.identity)
        if command[:2] == ("gh", "api"):
            endpoint = command[2]
            assert self.calls[-2][:4] == ("gh", "api", "user", "--jq")
            if endpoint.endswith(f"/commits/{SOURCE_SHA}"):
                return completed({"sha": self.resolved_source_sha})
            if endpoint.endswith("/commits/main"):
                return completed({"sha": MAIN_SHA})
            if "/compare/" in endpoint:
                assert f"{SOURCE_SHA}...{MAIN_SHA}" in endpoint
                assert "per_page=1" in endpoint
                return completed(self.comparison)
            if "/actions/workflows/api.yml/runs" in endpoint:
                page = (
                    sum(
                        "/actions/workflows/api.yml/runs" in item[2]
                        for item in self.calls
                        if item[:2] == ("gh", "api")
                    )
                    - 1
                )
                assert page < len(self.run_pages)
                assert f"head_sha={SOURCE_SHA}" in endpoint
                assert (
                    "event=push" in endpoint
                    and "status=success" in endpoint
                    and "per_page=100" in endpoint
                )
                assert f"page={page + 1}" in endpoint
                return completed({"workflow_runs": self.run_pages[page]})
            if endpoint.endswith(f"/actions/runs/{RUN_ID}"):
                return completed(self.validated_run)
            raise AssertionError(f"unapproved GitHub endpoint: {endpoint}")
        if command == ("railway", "whoami", "--json"):
            return completed(
                {"name": "Finn the Panther", "email": "finn@finnthepanther.com"}
            )
        if command[:2] == ("railway", "api"):
            return self._graphql(command)
        if command[:2] == ("railway", "ssh"):
            assert ("--project", PROJECT_ID) in pairwise(command)
            assert ("--service", SERVICE_ID) in pairwise(command)
            assert ("--environment", ENVIRONMENT_ID) in pairwise(command)
            assert ("--deployment-instance", RUNNING_INSTANCE_ID) in pairwise(command)
            assert "--" in command
            assert command[command.index("--") + 1 :] == (
                "uv",
                "run",
                "--locked",
                "--no-sync",
                "python",
                "-m",
                "config.build_identity",
            )
            return completed(self.ssh_stdout)
        if command and command[-1].endswith("api_deployment_identity.py"):
            assert options.get("input") == self.ssh_stdout
            return completed(self.joined_identity)
        if command == ("make", "api-smoke"):
            environment = cast(Mapping[str, str], options.get("env", {}))
            assert environment.get("API_BASE_URL") == "https://staging.tailtag.app"
            if self.expected_smoke_cwd is not None:
                assert options.get("cwd") == self.expected_smoke_cwd
            return completed(
                "", returncode=self.smoke_returncode, stderr=SENSITIVE_SENTINEL
            )
        raise AssertionError(f"unapproved subprocess command: {command}")


def run_operator(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    runner: PromotionSubprocess,
    *,
    source_sha: str = SOURCE_SHA,
    confirmation: str = "promote-tailtag-staging",
) -> int:
    """Invoke the public CLI while redirecting only its repository filesystem seam."""
    monkeypatch.setattr(staging_promote, "_REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(staging_promote.subprocess, "run", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_promote.py",
            "--source-sha",
            source_sha,
            "--confirm",
            confirmation,
        ],
    )
    return staging_promote.main()


def workflow_run_without_attempt() -> dict[str, object]:
    """Return an otherwise qualified exact-run response with no attempt evidence."""
    run = PromotionSubprocess.workflow_run()
    del run["run_attempt"]
    return run


def evidence_file(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "docs"
        / "development"
        / "staging-deployments"
        / f"{DEPLOYMENT_ID}.json"
    )


def read_evidence(path: Path) -> Mapping[str, object]:
    assert path.is_file(), "a returned deployment ID must leave a durable record"
    raw_record: object = json.loads(path.read_text())
    assert isinstance(raw_record, dict)
    record = cast(dict[str, object], raw_record)
    assert set(record) == EVIDENCE_FIELDS
    return cast(Mapping[str, object], record)


def assert_sanitized(*values: object) -> None:
    rendered = "\n".join(str(value) for value in values)
    assert SENSITIVE_SENTINEL not in rendered


@pytest.mark.parametrize(
    ("source_sha", "confirmation"),
    (
        (SOURCE_SHA.upper(), "promote-tailtag-staging"),
        (SOURCE_SHA[:-1], "promote-tailtag-staging"),
        (SOURCE_SHA, SENSITIVE_SENTINEL),
    ),
)
def test_main_rejects_invalid_or_unconfirmed_submission_before_any_subprocess(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_sha: str,
    confirmation: str,
) -> None:
    """AC-1/4/10/11 SECURITY: untrusted CLI input neither deploys nor leaks."""
    runner = PromotionSubprocess(evidence_file(tmp_path))

    assert (
        run_operator(
            staging_promote,
            monkeypatch,
            tmp_path,
            runner,
            source_sha=source_sha,
            confirmation=confirmation,
        )
        != 0
    )

    captured = capsys.readouterr()
    assert runner.calls == []
    assert not evidence_file(tmp_path).exists()
    assert_sanitized(captured.out, captured.err)


@pytest.mark.parametrize("reason", ("unavailable", "fingerprint mismatch"))
def test_main_requires_pinned_replacement_selectors_before_external_work(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    reason: str,
) -> None:
    """Replacement AC-1/5: an unavailable or rejected pin cannot reach a provider."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path)

    def rejected_target() -> tuple[str, str, str, str]:
        raise ValueError(f"{reason}: {SENSITIVE_SENTINEL} {PROJECT_ID}")

    monkeypatch.setattr(staging_promote, "_target_ids", rejected_target)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    captured = capsys.readouterr()
    assert runner.calls == []
    assert runner.mutation_count == 0
    assert not path.exists()
    assert SENSITIVE_SENTINEL not in captured.out + captured.err
    assert PROJECT_ID not in captured.out + captured.err


def test_main_uses_one_loaded_replacement_tuple_through_the_full_attempt(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Replacement AC-1/2/4: every existing gate uses one replacement target."""
    loads = 0

    def replacement_target() -> tuple[str, str, str, str]:
        nonlocal loads
        loads += 1
        return PROJECT_ID, ENVIRONMENT_ID, SERVICE_ID, POSTGRES_SERVICE_ID

    monkeypatch.setattr(staging_promote, "_target_ids", replacement_target)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", RETIRED_PROJECT_ID)
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    assert loads == 1
    assert runner.mutation_count == 1
    assert read_evidence(path)["overall_outcome"] == "SUCCEEDED"


def test_main_accepts_a_valid_older_main_ancestor_and_completes_the_exact_d_flow(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-1..9/11: an eligible older S passes every exact-D gate and becomes active."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    record = read_evidence(path)
    assert record == {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
        "deployment_timestamp": CREATED_AT,
        "accepted_main_sha": MAIN_SHA,
        "validation_run_id": RUN_ID,
        "validation_run_attempt": 1,
        "deployment_outcome": "SUCCEEDED",
        "migration_outcome": "SUCCEEDED",
        "startup_outcome": "SUCCEEDED",
        "readiness_outcome": "SUCCEEDED",
        "identity_outcome": "SUCCEEDED",
        "smoke_outcome": "SUCCEEDED",
        "final_active_state": "ACTIVE",
        "overall_outcome": "SUCCEEDED",
    }
    assert runner.mutation_count == 1
    assert runner.observation_count == 2, "event pages must be consumed to completion"
    calls = runner.calls
    mutation_index = next(
        index
        for index, command in enumerate(calls)
        if len(command) > 2 and "serviceInstanceDeployV2" in command[2]
    )
    observation_index = next(
        index
        for index, command in enumerate(calls)
        if len(command) > 2 and "deploymentEvents" in command[2]
    )
    assert mutation_index < observation_index
    assert any(command[:2] == ("railway", "ssh") for command in calls)
    assert any(command == ("make", "api-smoke") for command in calls)
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


def test_main_accepts_an_identical_current_main_candidate(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-2/3: current main is eligible when GitHub compares the same immutable SHA."""
    monkeypatch.setattr(sys.modules[__name__], "MAIN_SHA", SOURCE_SHA)
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        comparison={
            "base_commit": {"sha": SOURCE_SHA},
            "merge_base_commit": {"sha": SOURCE_SHA},
            "behind_by": 0,
            "status": "identical",
        },
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    record = read_evidence(path)
    assert record["accepted_main_sha"] == SOURCE_SHA
    assert record["overall_outcome"] == "SUCCEEDED"


@pytest.mark.parametrize(
    "comparison",
    (
        {
            "base_commit": {"sha": SOURCE_SHA},
            "merge_base_commit": {"sha": MAIN_SHA},
            "behind_by": 0,
            "status": "ahead",
        },
        {
            "base_commit": {"sha": SOURCE_SHA},
            "merge_base_commit": {"sha": SOURCE_SHA},
            "behind_by": 1,
            "status": "ahead",
        },
        {
            "base_commit": {"sha": SOURCE_SHA},
            "merge_base_commit": {"sha": SOURCE_SHA},
            "behind_by": 0,
            "status": "diverged",
        },
    ),
)
def test_main_rejects_non_ancestor_comparisons_without_submission(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    comparison: Mapping[str, object],
) -> None:
    """AC-2/10: local/stale/diverged ancestry cannot qualify S."""
    runner = PromotionSubprocess(evidence_file(tmp_path), comparison=comparison)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


def test_main_rejects_a_candidate_that_does_not_resolve_to_its_exact_sha(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-1/10: an abbreviated, redirected, or other commit object cannot become S."""
    runner = PromotionSubprocess(evidence_file(tmp_path), resolved_source_sha=OTHER_SHA)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


@pytest.mark.parametrize(
    "run_pages",
    (
        ([PromotionSubprocess.workflow_run(event="pull_request")],),
        ([PromotionSubprocess.workflow_run(head_sha=OTHER_SHA)],),
        ([],),
    ),
)
def test_main_requires_a_qualified_paginated_push_validation_before_submission(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    run_pages: tuple[list[dict[str, object]], ...],
) -> None:
    """AC-3/10: PR, another SHA, or no exact successful push run is ineligible."""
    runner = PromotionSubprocess(evidence_file(tmp_path), run_pages=run_pages)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


def test_main_follows_workflow_run_pages_when_a_full_first_page_has_no_qualifier(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-3: a valid run on page two cannot be hidden behind 100 other run rows."""
    first_page = [
        PromotionSubprocess.workflow_run(run_id=RUN_ID + index, event="pull_request")
        for index in range(100)
    ]
    runner = PromotionSubprocess(
        evidence_file(tmp_path),
        run_pages=(first_page, [PromotionSubprocess.workflow_run()]),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    workflow_queries = [
        command
        for command in runner.calls
        if command[:2] == ("gh", "api")
        and "/actions/workflows/api.yml/runs" in command[2]
    ]
    assert len(workflow_queries) == 2


@pytest.mark.parametrize(
    "validated_run",
    (
        PromotionSubprocess.workflow_run(path=".github/workflows/other.yml"),
        PromotionSubprocess.workflow_run(repository={"full_name": "other/repository"}),
        PromotionSubprocess.workflow_run(status="in_progress"),
        PromotionSubprocess.workflow_run(conclusion="failure"),
        PromotionSubprocess.workflow_run(run_id=RUN_ID + 1),
        PromotionSubprocess.workflow_run(run_attempt=0),
        PromotionSubprocess.workflow_run(run_id=True),
        PromotionSubprocess.workflow_run(run_attempt=True),
        workflow_run_without_attempt(),
    ),
)
def test_main_revalidates_the_selected_run_before_submission(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    validated_run: Mapping[str, object],
) -> None:
    """AC-3/10: list filtering cannot substitute for the canonical exact-run record."""
    runner = PromotionSubprocess(evidence_file(tmp_path), validated_run=validated_run)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


@pytest.mark.parametrize(
    "config",
    (
        canonical_config(source={"repo": "other/repository", "image": None}),
        canonical_config(
            source={"repo": "TailTag-Game/tailtag", "image": "registry/image"}
        ),
        canonical_config(source={"repo": "TailTag-Game/tailtag"}),
        canonical_config(
            preDeployCommand=[
                "python manage.py migrate --settings=config.settings.production --noinput"
            ]
        ),
        canonical_config(preDeployCommand=["python manage.py migrate"]),
        canonical_config(preDeployCommand=[]),
        {
            key: value
            for key, value in canonical_config().items()
            if key != "preDeployCommand"
        },
        canonical_config(healthcheckPath="/health/live"),
    ),
)
def test_main_rejects_target_source_migration_or_readiness_preflight_mismatches(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    config: Mapping[str, object],
) -> None:
    """AC-4/6/10: only the reviewed Staging/API configuration may be submitted."""
    runner = PromotionSubprocess(evidence_file(tmp_path), config=config)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


def test_main_rejects_an_enabled_scoped_autodeploy_trigger_before_submission(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-4/10: promotion never repairs or races an enabled Staging autodeploy."""
    runner = PromotionSubprocess(
        evidence_file(tmp_path),
        deployment_triggers={
            "edges": [{"node": {"id": "existing-trigger"}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 0
    assert not evidence_file(tmp_path).exists()


@pytest.mark.parametrize(
    "events",
    (
        ([stage_event("PRE_DEPLOY_COMMAND", skipped=True)],),
        ([stage_event("PRE_DEPLOY_COMMAND", error=SENSITIVE_SENTINEL)],),
        ([stage_event("CREATE_CONTAINER"), stage_event("HEALTHCHECK")],),
    ),
)
def test_main_fails_closed_for_skipped_error_or_missing_migration_evidence(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    events: tuple[list[dict[str, object]], ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/10/11 SECURITY, RELIABILITY: lifecycle completion cannot replace migration proof."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, observation_events=events)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["migration_outcome"] != "SUCCEEDED"
    assert record["overall_outcome"] != "SUCCEEDED"
    assert runner.mutation_count == 1
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)
    assert not any(command == ("make", "api-smoke") for command in runner.calls)
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


@pytest.mark.parametrize(
    "events",
    (
        [
            stage_event("PRE_DEPLOY_COMMAND"),
            stage_event("PRE_DEPLOY_COMMAND"),
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
        [
            stage_event("PRE_DEPLOY_COMMAND"),
            stage_event("PRE_DEPLOY_COMMAND", error=SENSITIVE_SENTINEL),
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
    ),
)
def test_main_fails_closed_for_duplicate_or_conflicting_migration_stage_evidence(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    events: list[dict[str, object]],
) -> None:
    """AC-6/10: duplicate/conflicting required-stage records are indeterminate."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, observation_events=(events,))

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["migration_outcome"] != "SUCCEEDED"
    assert record["overall_outcome"] != "SUCCEEDED"
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)


def test_main_records_terminal_failed_predeploy_migration_as_failed(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/10/11: a terminal deployment with a pre-deploy error records migration failure."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        observed_deployment=deployment(status="FAILED"),
        observation_events=(
            [stage_event("PRE_DEPLOY_COMMAND", error=SENSITIVE_SENTINEL)],
        ),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["deployment_outcome"] == "FAILED"
    assert record["migration_outcome"] == "FAILED"
    assert record["overall_outcome"] == "OR7_HANDOFF"
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)
    assert not any(command == ("make", "api-smoke") for command in runner.calls)
    assert runner.mutation_count == 1
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


def test_main_requires_all_completed_startup_and_readiness_events(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-6/10: SUCCESS plus an incomplete healthcheck cannot pass readiness."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        observation_events=(
            [
                stage_event("PRE_DEPLOY_COMMAND"),
                stage_event("CREATE_CONTAINER"),
                stage_event("HEALTHCHECK", completed_at=None),
            ],
        ),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["readiness_outcome"] != "SUCCEEDED"
    assert record["overall_outcome"] != "SUCCEEDED"
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)


@pytest.mark.parametrize(
    "observed",
    (
        deployment(project_id=RETIRED_PROJECT_ID),
        deployment(project_id="3b8d2a03-38ec-4bf7-91f1-1e562b9f4793"),
        deployment(service_id="2d913bc3-0fa2-436e-bd21-6b55847cf65e"),
        deployment(environment_id="bea90e14-3b5d-4bc1-b6ab-3c12d4f665b8"),
        deployment(instances=[{"id": STOPPED_INSTANCE_ID, "status": "REMOVED"}]),
    ),
)
def test_main_requires_exact_target_and_a_running_instance_before_identity_readback(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    observed: Mapping[str, object],
) -> None:
    """AC-5..7/10: a different target or default/stopped instance is never read."""
    runner = PromotionSubprocess(evidence_file(tmp_path), observed_deployment=observed)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)


@pytest.mark.parametrize(
    "created_at",
    (SENSITIVE_SENTINEL, "2026-09-17T00:16:10.526", None),
)
def test_main_rejects_malformed_or_sensitive_deployment_timestamps_before_identity(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    created_at: object,
) -> None:
    """AC-5/11: D.createdAt must be a safe exact timestamp, never arbitrary metadata."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        observed_deployment=deployment(created_at=created_at),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["deployment_timestamp"] is None
    assert record["overall_outcome"] != "SUCCEEDED"
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)
    assert not any(command == ("make", "api-smoke") for command in runner.calls)
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


@pytest.mark.parametrize(
    ("events", "outcome"),
    (
        (
            [
                stage_event("PRE_DEPLOY_COMMAND"),
                stage_event("CREATE_CONTAINER", skipped=True),
                stage_event("HEALTHCHECK"),
            ],
            "startup_outcome",
        ),
        (
            [
                stage_event("PRE_DEPLOY_COMMAND"),
                stage_event("CREATE_CONTAINER", error=SENSITIVE_SENTINEL),
                stage_event("HEALTHCHECK"),
            ],
            "startup_outcome",
        ),
        (
            [
                stage_event("PRE_DEPLOY_COMMAND"),
                stage_event("CREATE_CONTAINER"),
                stage_event("HEALTHCHECK", skipped=True),
            ],
            "readiness_outcome",
        ),
        (
            [
                stage_event("PRE_DEPLOY_COMMAND"),
                stage_event("CREATE_CONTAINER"),
                stage_event("HEALTHCHECK", completed_at=None),
            ],
            "readiness_outcome",
        ),
    ),
)
def test_main_fails_closed_for_bad_startup_or_readiness_evidence(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    events: list[dict[str, object]],
    outcome: str,
) -> None:
    """AC-6/10: skipped, failed, or incomplete startup/readiness events cannot pass."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, observation_events=(events,))

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record[outcome] != "SUCCEEDED"
    assert record["overall_outcome"] != "SUCCEEDED"
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)


def test_main_rejects_a_joined_identity_for_the_wrong_image_source_before_smoke(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-7/10: only the unchanged exact-instance output joined to S can proceed."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        joined_identity={
            "source_sha": OTHER_SHA,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
            "deployment_timestamp": CREATED_AT,
        },
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["identity_outcome"] != "SUCCEEDED"
    assert not any(command == ("make", "api-smoke") for command in runner.calls)


def test_main_stops_after_failed_smoke_without_declaring_the_deployment_active(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-8/10/11 SECURITY: a shared-URL smoke failure cannot be ignored or leaked."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, smoke_returncode=1)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["smoke_outcome"] == "FAILED"
    assert record["final_active_state"] == "NOT_CHECKED"
    assert record["overall_outcome"] == "FAILED"
    assert not any(
        len(command) > 2 and "activeDeployments" in command[2]
        for command in runner.calls
    )
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


def test_main_runs_canonical_smoke_from_the_repository_root_when_started_in_api(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-8: documented uv --directory startup must not leave make in services/api."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, expected_smoke_cwd=tmp_path)
    monkeypatch.chdir(REPOSITORY_ROOT / "services" / "api")

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    assert read_evidence(path)["smoke_outcome"] == "SUCCEEDED"


@pytest.mark.parametrize(
    ("active_deployments", "state", "overall"),
    (
        (
            [active_deployment(deployment_id=OTHER_DEPLOYMENT_ID)],
            "SUPERSEDED",
            "SUPERSEDED",
        ),
        ([], "INACTIVE", "FAILED"),
    ),
)
def test_main_preserves_historical_gates_when_exact_d_is_not_active(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    active_deployments: list[dict[str, object]],
    state: str,
    overall: str,
) -> None:
    """AC-9/10: a first/latest active deployment cannot replace D at declaration."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, active_deployments=active_deployments)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["deployment_outcome"] == "SUCCEEDED"
    assert record["migration_outcome"] == "SUCCEEDED"
    assert record["startup_outcome"] == "SUCCEEDED"
    assert record["readiness_outcome"] == "SUCCEEDED"
    assert record["identity_outcome"] == "SUCCEEDED"
    assert record["smoke_outcome"] == "SUCCEEDED"
    assert record["final_active_state"] == state
    assert record["overall_outcome"] == overall


@pytest.mark.parametrize(
    "active_target",
    (
        active_deployment(status="FAILED"),
        active_deployment(instances=[{"id": STOPPED_INSTANCE_ID, "status": "STOPPED"}]),
    ),
)
def test_main_requires_the_active_exact_d_to_still_be_successful_and_running(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    active_target: dict[str, object],
) -> None:
    """AC-9/10: active-set membership alone cannot revive a failed or stopped D."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, active_deployments=[active_target])

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["final_active_state"] != "ACTIVE"
    assert record["overall_outcome"] != "SUCCEEDED"


def test_main_accepts_a_schema_valid_non_uuid_running_final_active_instance(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-9: final active instance IDs are Railway strings, not UUID-constrained IDs."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        active_deployments=[
            active_deployment(
                instances=[{"id": "railway-instance-string", "status": "RUNNING"}]
            )
        ],
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    record = read_evidence(path)
    assert record["final_active_state"] == "ACTIVE"
    assert record["overall_outcome"] == "SUCCEEDED"


def test_main_records_interruption_as_indeterminate_without_a_second_submission(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4/10/11 RELIABILITY: post-submission interruption keeps safe S/D evidence."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, interrupt_observation=True)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["source_sha"] == SOURCE_SHA
    assert record["deployment_id"] == DEPLOYMENT_ID
    assert record["overall_outcome"] == "INDETERMINATE"
    assert runner.mutation_count == 1
    captured = capsys.readouterr()
    assert_sanitized(captured.out, captured.err, path.read_bytes())


def test_main_stops_after_an_authenticated_lifecycle_transport_failure(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC-5/10 RELIABILITY: a failed exact-D read has no retry, redeploy, or fallback."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        observation_error=subprocess.TimeoutExpired(("railway", "api"), timeout=30),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["overall_outcome"] == "INDETERMINATE"
    assert runner.mutation_count == 1
    assert runner.observation_count == 0
    assert len(runner.calls) == next(
        index
        for index, command in enumerate(runner.calls, start=1)
        if len(command) > 2 and "deploymentEvents" in command[2]
    )


def test_main_stops_on_identity_or_mutation_failure_without_retry_or_sensitive_output(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4/10/11 SECURITY, RELIABILITY: auth/mutation failure has no fallback or replay."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, fail_mutation=True)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    captured = capsys.readouterr()
    assert runner.mutation_count == 1
    assert not path.exists(), (
        "a lost/invalid mutation response cannot invent D evidence"
    )
    assert_sanitized(captured.out, captured.err)

    other_path = evidence_file(tmp_path / "identity")
    rejected = PromotionSubprocess(other_path, identity="someone-else")
    assert (
        run_operator(staging_promote, monkeypatch, tmp_path / "identity", rejected) != 0
    )
    assert rejected.mutation_count == 0
    assert not other_path.exists()


@pytest.mark.parametrize("mutation_result", ("not-a-deployment-id", None))
def test_main_rejects_a_missing_or_malformed_mutation_deployment_id(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    mutation_result: object,
) -> None:
    """AC-4/10: a response without a valid returned D cannot trigger a lookup or retry."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, mutation_result=mutation_result)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert runner.mutation_count == 1
    assert not path.exists()
    assert runner.observation_count == 0


def test_main_stops_safely_when_exact_sd_checkpoint_persistence_fails(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4/10/11 RELIABILITY, SECURITY: D is never observed or retried without evidence."""
    path = evidence_file(tmp_path)

    def make_evidence_directory_unwritable() -> None:
        path.parent.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.exists():
            path.parent.rmdir()
        path.parent.write_text(SENSITIVE_SENTINEL)

    runner = PromotionSubprocess(path, on_mutation=make_evidence_directory_unwritable)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    assert SOURCE_SHA in rendered
    assert DEPLOYMENT_ID in rendered
    assert runner.mutation_count == 1
    assert runner.observation_count == 0
    mutation_index = next(
        index
        for index, command in enumerate(runner.calls)
        if len(command) > 2 and "serviceInstanceDeployV2" in command[2]
    )
    assert len(runner.calls) == mutation_index + 1
    assert path.parent.is_file()
    assert_sanitized(rendered)


def test_main_rejects_ssh_identity_for_another_deployment_before_exact_join(
    staging_promote: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """AC-7: SSH identity E cannot make the existing join query E instead of D."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        ssh_stdout=json.dumps(
            {
                "source_sha": SOURCE_SHA,
                "deployment_id": OTHER_DEPLOYMENT_ID,
                "environment": "staging",
            }
        ),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["deployment_id"] == DEPLOYMENT_ID
    assert record["identity_outcome"] != "SUCCEEDED"
    assert not any(
        command[-1].endswith("api_deployment_identity.py") for command in runner.calls
    )
    assert not any(command == ("make", "api-smoke") for command in runner.calls)


def test_main_accepts_completed_required_events_with_null_payloads(
    staging_promote: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """AC-6: nullable payload is not an error when every required event completes."""
    events = [
        stage_event(step)
        for step in ("PRE_DEPLOY_COMMAND", "CREATE_CONTAINER", "HEALTHCHECK")
    ]
    for event in events:
        event["payload"] = None
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, observation_events=(events,))

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) == 0

    assert read_evidence(path)["overall_outcome"] == "SUCCEEDED"


@pytest.mark.parametrize(
    "events",
    (
        [
            stage_event("PRE_DEPLOY_COMMAND", completed_at="not-a-timestamp"),
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
        [
            stage_event("PRE_DEPLOY_COMMAND", skipped="false"),
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
        [
            stage_event("PRE_DEPLOY_COMMAND", error=7),
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
        [
            {
                key: value
                for key, value in stage_event("PRE_DEPLOY_COMMAND").items()
                if key != "payload"
            },
            stage_event("CREATE_CONTAINER"),
            stage_event("HEALTHCHECK"),
        ],
    ),
)
def test_main_fails_closed_for_malformed_required_event_fields(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    events: list[dict[str, object]],
) -> None:
    """AC-6/10: malformed completedAt or payload types are not successful evidence."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, observation_events=(events,))

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["migration_outcome"] == "INDETERMINATE"
    assert record["overall_outcome"] == "OR7_HANDOFF"


@pytest.mark.parametrize(
    ("active_service_id", "active_environment_id"),
    (("wrong-service", ENVIRONMENT_ID), (SERVICE_ID, "wrong-environment")),
)
def test_main_fails_closed_when_final_service_instance_selectors_are_wrong(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    active_service_id: str,
    active_environment_id: str,
) -> None:
    """AC-9: the final active set must prove its canonical service/environment selectors."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        active_service_id=active_service_id,
        active_environment_id=active_environment_id,
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert read_evidence(path)["overall_outcome"] != "SUCCEEDED"


@pytest.mark.parametrize(
    "active",
    (
        [{"id": OTHER_DEPLOYMENT_ID}],
        [
            active_deployment(
                deployment_id=OTHER_DEPLOYMENT_ID, project_id="wrong-project"
            )
        ],
    ),
)
def test_main_marks_malformed_or_wrong_target_non_d_active_entries_indeterminate(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    active: list[dict[str, object]],
) -> None:
    """AC-9: malformed non-D entries are not proof that D was cleanly superseded."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, active_deployments=active)

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    record = read_evidence(path)
    assert record["final_active_state"] == "INDETERMINATE"
    assert record["overall_outcome"] == "INDETERMINATE"


@pytest.mark.parametrize("page_info", ({"hasNextPage": None}, {}))
def test_main_rejects_malformed_event_page_info(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    page_info: Mapping[str, object],
) -> None:
    """AC-5/10: a malformed pageInfo cannot silently truncate lifecycle evidence."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(path, page_infos=(page_info,))

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0
    assert read_evidence(path)["overall_outcome"] == "INDETERMINATE"
    assert runner.observation_count == 1


def test_main_stops_on_a_repeated_event_cursor_without_identity_or_smoke(
    staging_promote: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """AC-5/10: a cyclic cursor is bounded and cannot create an observation retry loop."""
    path = evidence_file(tmp_path)
    runner = PromotionSubprocess(
        path,
        observation_events=(
            [stage_event("PRE_DEPLOY_COMMAND")],
            [stage_event("CREATE_CONTAINER")],
        ),
        page_infos=(
            {"hasNextPage": True, "endCursor": "cursor-1"},
            {"hasNextPage": True, "endCursor": "cursor-1"},
        ),
    )

    assert run_operator(staging_promote, monkeypatch, tmp_path, runner) != 0

    assert read_evidence(path)["overall_outcome"] == "INDETERMINATE"
    assert runner.observation_count == 2
    assert not any(command[:2] == ("railway", "ssh") for command in runner.calls)
    assert not any(command == ("make", "api-smoke") for command in runner.calls)


def test_main_sanitizes_unknown_argument_before_any_subprocess(
    staging_promote: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-1/11 SECURITY: argparse usage must not echo an untrusted argument value."""
    runner = PromotionSubprocess(evidence_file(tmp_path))
    monkeypatch.setattr(staging_promote, "_REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(staging_promote.subprocess, "run", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_promote.py",
            "--source-sha",
            SOURCE_SHA,
            "--confirm",
            "promote-tailtag-staging",
            "--unexpected",
            SENSITIVE_SENTINEL,
        ],
    )

    assert staging_promote.main() != 0

    captured = capsys.readouterr()
    assert runner.calls == []
    assert_sanitized(captured.out, captured.err)
