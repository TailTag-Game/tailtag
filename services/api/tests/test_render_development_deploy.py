"""CI-gated Render Development deploy (#408, G3 option B)."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import render_development_deploy as deploy

WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"

SHA = "a" * 40
NEWER_SHA = "b" * 40
HOOK = "https://api.render.com/deploy/srv-d0development00000000?key=SyntheticHookKey"
TOKEN = "synthetic-github-token"


def workflow(
    name: str, status: str = "completed", conclusion: str | None = "success"
) -> dict[str, object]:
    return {"name": name, "status": status, "conclusion": conclusion}


CI_PASSED: list[object] = [
    workflow("TailTag API"),
    workflow("Mobile App Build Test"),
    workflow("Windows parity"),
]
EVERY_PUSH = frozenset({"TailTag API", "Mobile App Build Test", "Windows parity"})
BACKEND_CHANGE = ["services/api/config/replacement_migrate.py"]


class FakeGitHub(deploy.GitHub):
    """In-memory GitHub reads for one commit; the network boundary is replaced."""

    def __init__(self, runs: Sequence[list[object] | None], latest: str = SHA) -> None:
        super().__init__("https://api.github.com", "TailTag-Game/tailtag", TOKEN)
        self._runs = runs
        self._latest = latest
        self.calls = 0

    def changed_files(self, sha: str) -> list[str]:
        assert sha == SHA
        return BACKEND_CHANGE

    def workflow_runs(self, sha: str) -> list[object]:
        """Return each poll's runs in order; None stands for a failed poll."""
        assert sha == SHA
        runs = self._runs[min(self.calls, len(self._runs) - 1)]
        self.calls += 1
        if runs is None:
            raise deploy.DeployFailure
        return runs

    def latest_backend_sha(self) -> str:
        return self._latest


@pytest.fixture
def requests(monkeypatch: MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def record(url: str, *, token: str | None = None, method: str = "GET") -> object:
        assert token is None
        calls.append((method, url))
        return {"deploy": {"id": "dep-synthetic"}}

    def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(deploy, "_request", record)
    monkeypatch.setattr(
        deploy, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=no_wait)
    )
    return calls


@pytest.mark.parametrize(
    ("runs", "state"),
    (
        ([workflow("Windows parity")], "pending"),
        ([CI_PASSED[0], CI_PASSED[2]], "pending"),
        ([*CI_PASSED[:2], workflow("Windows parity", "in_progress", None)], "pending"),
        (CI_PASSED, "passed"),
        ([*CI_PASSED[:2], workflow("Windows parity", conclusion="skipped")], "passed"),
        ([*CI_PASSED[:2], workflow("Windows parity", conclusion="failure")], "failed"),
        (
            [*CI_PASSED[:2], workflow("Windows parity", conclusion="cancelled")],
            "failed",
        ),
        (
            [
                *CI_PASSED,
                workflow("TailTag post-deploy smoke", conclusion="failure"),
                workflow("Render Development deploy", "in_progress", None),
            ],
            "passed",
        ),
        ([*CI_PASSED, "not-a-run"], "failed"),
    ),
    ids=(
        "api-not-started",
        "mobile-not-started",
        "one-running",
        "all-passed",
        "skipped-passes",
        "failure-blocks",
        "cancel-blocks",
        "excluded-workflows-ignored",
        "malformed-run",
    ),
)
def test_ci_state_requires_every_other_workflow_to_pass(
    runs: list[object], state: str
) -> None:
    """D1/D2: only CI workflows gate the deploy, and every one must pass."""
    assert deploy.ci_state(runs, EVERY_PUSH) == state


@pytest.mark.parametrize(
    ("changed", "extra"),
    (
        (BACKEND_CHANGE, set[str]()),
        (["services/api/uv.lock"], {"TailTag Simulator"}),
        (["services/api/simulation_fixtures/images/a/b.png"], {"TailTag Simulator"}),
        ([".semgrep/rules/no-secrets.yml"], {"TailTag Simulator"}),
        (["services/api/simulation_fixtures/__init__.py"], set[str]()),
    ),
    ids=("backend", "exact-path", "nested-glob", "dot-directory", "near-miss"),
)
def test_expected_workflows_follow_each_path_filter(
    changed: list[str], extra: set[str]
) -> None:
    """D2: a path-filtered workflow is expected only when the commit triggers it."""
    assert deploy.expected_workflows(changed) == EVERY_PUSH | extra


def test_expected_workflow_that_never_appears_keeps_ci_pending() -> None:
    """D2: a triggered path-filtered workflow must exist before CI can pass."""
    expected = deploy.expected_workflows(["Taskfile.yml"])
    assert deploy.ci_state(CI_PASSED, expected) == "pending"
    assert (
        deploy.ci_state([*CI_PASSED, workflow("TailTag Simulator")], expected)
        == "passed"
    )


def test_a_few_failed_polls_count_as_waiting(
    requests: list[tuple[str, str]],
) -> None:
    """D1: transient GitHub errors do not end the deploy; a streak does."""
    environment = {
        "TAILTAG_DEPLOY_SHA": SHA,
        "RENDER_DEVELOPMENT_DEPLOY_HOOK_URL": HOOK,
    }
    flaky = FakeGitHub([None, None, None, CI_PASSED])
    assert deploy.run(environment, flaky) is True

    broken = FakeGitHub([None, None, None, None])
    with pytest.raises(deploy.DeployFailure):
        deploy.run(environment, broken)
    assert requests == [("POST", f"{HOOK}&ref={SHA}")]


def test_passed_ci_deploys_exactly_the_commit_through_the_hook(
    requests: list[tuple[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    """D3: the hook deploys the gated SHA and its URL never reaches output."""
    github = FakeGitHub([[workflow("TailTag API", "in_progress", None)], CI_PASSED])
    environment = {
        "TAILTAG_DEPLOY_SHA": SHA,
        "RENDER_DEVELOPMENT_DEPLOY_HOOK_URL": HOOK,
    }

    assert deploy.run(environment, github) is True

    assert requests == [("POST", f"{HOOK}&ref={SHA}")]
    captured = capsys.readouterr()
    assert "SyntheticHookKey" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("runs", "latest"),
    (
        ([[*CI_PASSED[:2], workflow("Windows parity", conclusion="failure")]], SHA),
        ([CI_PASSED], NEWER_SHA),
    ),
    ids=("ci-failed", "superseded"),
)
def test_failed_or_superseded_commit_is_not_deployed(
    requests: list[tuple[str, str]], runs: list[list[object]], latest: str
) -> None:
    """D5: a CI failure or a newer backend commit never calls the hook."""
    environment = {
        "TAILTAG_DEPLOY_SHA": SHA,
        "RENDER_DEVELOPMENT_DEPLOY_HOOK_URL": HOOK,
    }

    assert deploy.run(environment, FakeGitHub(runs, latest)) is False
    assert requests == []


def test_ci_that_never_finishes_fails_the_run_without_deploying(
    requests: list[tuple[str, str]], monkeypatch: MonkeyPatch
) -> None:
    """D1: a CI wait that times out turns red, because CI may still pass later."""
    now = [0.0]

    def sleep(seconds: float) -> None:
        assert 0 < seconds <= deploy._CI_RETRY_SECONDS  # pyright: ignore[reportPrivateUsage]
        now[0] += seconds

    monkeypatch.setattr(
        deploy, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep)
    )
    environment = {
        "TAILTAG_DEPLOY_SHA": SHA,
        "RENDER_DEVELOPMENT_DEPLOY_HOOK_URL": HOOK,
    }

    with pytest.raises(deploy.DeployFailure):
        deploy.run(
            environment, FakeGitHub([[workflow("TailTag API", "in_progress", None)]])
        )

    assert now[0] >= deploy._CI_DEADLINE_SECONDS  # pyright: ignore[reportPrivateUsage]
    assert requests == []


def test_manual_run_of_an_older_commit_fails_before_waiting(
    requests: list[tuple[str, str]],
) -> None:
    """D5: a dispatch cancels the running deploy, so an older SHA must turn red."""
    github = FakeGitHub([CI_PASSED], latest=NEWER_SHA)
    environment = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "TAILTAG_DEPLOY_SHA": SHA,
        "RENDER_DEVELOPMENT_DEPLOY_HOOK_URL": HOOK,
    }

    with pytest.raises(deploy.DeployFailure):
        deploy.run(environment, github)

    assert github.calls == 0
    assert requests == []


@pytest.mark.parametrize(
    "hook",
    (
        "",
        "http://api.render.com/deploy/srv-d0development00000000?key=SyntheticHookKey",
        "https://api.render.com.example/deploy/srv-d0development00000000?key=SyntheticHookKey",
        "https://api.render.com/deploy/srv-d0development00000000?key=SyntheticHookKey&ref=main",
    ),
    ids=("missing", "http", "other-host", "extra-query"),
)
def test_unexpected_hook_url_fails_closed_without_echoing_it(
    requests: list[tuple[str, str]], hook: str
) -> None:
    """D3: only a Render service deploy hook is ever called."""
    with pytest.raises(deploy.DeployFailure) as caught:
        deploy.trigger_deploy(hook, SHA)
    assert requests == []
    assert "SyntheticHookKey" not in str(caught.value)


def test_main_writes_only_the_decision_and_hides_failure_details(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D3/D5: the step output is a fixed decision; failures name no secret."""
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "TailTag-Game/tailtag")
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("TAILTAG_DEPLOY_SHA", SHA)
    monkeypatch.setenv("RENDER_DEVELOPMENT_DEPLOY_HOOK_URL", HOOK)

    def unreachable(*_: object, **__: object) -> object:
        raise deploy.DeployFailure

    def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(
        deploy, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=no_wait)
    )
    monkeypatch.setattr(deploy, "_request", unreachable)
    assert deploy.main() == 1
    captured = capsys.readouterr()
    assert captured.err == "FAIL Render Development deploy unavailable\n"
    assert TOKEN not in captured.out + captured.err
    assert not output.exists()

    def passed_runs(_self: deploy.GitHub, _sha: str) -> list[object]:
        return CI_PASSED

    def latest(_self: deploy.GitHub) -> str:
        return SHA

    def changed(_self: deploy.GitHub, _sha: str) -> list[str]:
        return BACKEND_CHANGE

    def accepted(*_: object, **__: object) -> object:
        return {}

    monkeypatch.setattr(deploy.GitHub, "workflow_runs", passed_runs)
    monkeypatch.setattr(deploy.GitHub, "latest_backend_sha", latest)
    monkeypatch.setattr(deploy.GitHub, "changed_files", changed)
    monkeypatch.setattr(deploy, "_request", accepted)
    assert deploy.main() == 0
    assert output.read_text() == "deployed=true\n"


def _workflow(name: str) -> dict[Any, Any]:
    return cast(dict[Any, Any], yaml.safe_load((WORKFLOWS / name).read_text()))


def test_deploy_workflow_keeps_the_secret_and_inputs_inside_the_gate() -> None:
    """D1/D3/D5: main only, least privilege, and no input inside a run script."""
    text = (WORKFLOWS / "render-development-deploy.yml").read_text()
    workflow = _workflow("render-development-deploy.yml")
    triggers = workflow[True]  # YAML 1.1 reads the "on" key as True.
    job = workflow["jobs"]["deploy"]

    assert triggers["push"] == {"branches": ["main"], "paths": ["services/api/**"]}
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["environment"] == "render-development"
    secret_steps = [step for step in job["steps"] if "secrets." in str(step)]
    assert [step["name"] for step in secret_steps] == [
        "Wait for CI and request the deploy"
    ]
    assert all("inputs." not in step.get("run", "") for step in job["steps"])
    assert {match.split("@", 1)[0] for match in re.findall(r"uses: (\S+)", text)} == {
        "actions/checkout",
        "actions/setup-python",
        "astral-sh/setup-uv",
        "./.github/actions/install-go-task",
    }


def test_gate_tables_match_the_real_workflows() -> None:
    """D2: a new, renamed, or refiltered workflow cannot escape the gate."""
    excluded = deploy._EXCLUDED_WORKFLOWS  # pyright: ignore[reportPrivateUsage]
    push_workflows: dict[str, tuple[str, ...] | None] = {}
    names: set[str] = set()
    for path in WORKFLOWS.glob("*.yml"):
        workflow = _workflow(path.name)
        names.add(workflow["name"])
        push = workflow[True].get("push")  # YAML 1.1 reads "on" as True.
        if workflow["name"] in excluded or push is None:
            continue
        assert push["branches"] == ["main"]
        assert "paths-ignore" not in push
        paths = push.get("paths")
        push_workflows[workflow["name"]] = None if paths is None else tuple(paths)

    assert excluded <= names
    assert _workflow("render-development-deploy.yml")["name"] in excluded
    assert push_workflows == dict(
        deploy._PUSH_WORKFLOWS  # pyright: ignore[reportPrivateUsage]
    )
