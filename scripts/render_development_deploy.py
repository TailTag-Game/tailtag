"""Deploy one main commit to Render Development after every CI workflow passes."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final, Literal, cast

_SHA: Final = re.compile(r"[0-9a-f]{40}")
_REPOSITORY: Final = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_HOOK: Final = re.compile(
    r"https://api\.render\.com/deploy/srv-[a-z0-9]{1,60}\?key=[A-Za-z0-9_-]{1,200}"
)
# This workflow and the Railway post-deploy smoke are not CI for the commit.
_EXCLUDED_WORKFLOWS: Final = frozenset(
    {"Render Development deploy", "TailTag post-deploy smoke"}
)
# The app workflows share one ordered path filter. GitHub applies it in order:
# a "!" pattern excludes a path, and a later positive pattern includes it again.
# Documentation-only changes match no pattern. A test keeps this list equal to
# the workflow files.
_APP_PATHS: Final = (
    "**",
    "!docs/**",
    "!**/*.md",
    "services/api/**",
    ".semgrep/**",
    "docs/operations/simulation-host.md",
    "docs/development/staging.md",
    "docs/development/backend-delivery-operations.md",
    "docs/operations/operator-authorization-audit.md",
    "docs/operations/catch-administration.md",
    "docs/specs/README.md",
    "docs/specs/2026-09-22-v0-migration-application-rollback.md",
    "docs/specs/2026-09-22-v0-migration-application-rollback-implementation-plan.md",
    "docs/development/staging-recovery/2026-09-22-issue-206-no-go.json",
)
# Each workflow that runs on a push to main, with its path filter. A test keeps
# this table equal to the files in .github/workflows, so a new or changed
# workflow cannot escape the gate.
_PUSH_WORKFLOWS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "TailTag API": _APP_PATHS,
        "Mobile App Build Test": _APP_PATHS,
        "Windows parity": _APP_PATHS,
        "TailTag Simulator": (
            "tools/simulator/**",
            "docs/operations/simulation-host.md",
            "scripts/api_sim_pool_ssh.py",
            "scripts/api_sim_fixture_ssh.py",
            "scripts/api_sim_inspect_ssh.py",
            "scripts/api_staging_reset_ssh.py",
            "scripts/api_staging_preflight.py",
            "services/api/pyproject.toml",
            "services/api/uv.lock",
            "services/api/simulation_fixtures/images/**",
            ".semgrep/**",
            "Taskfile.yml",
            "scripts/validate_semgrep_contract.py",
            ".github/workflows/simulator.yml",
        ),
    }
)
_PASSING: Final = frozenset({"success", "skipped", "neutral"})
_BACKEND_PATH: Final = "services/api"
_CI_DEADLINE_SECONDS: Final = 75 * 60
_CI_RETRY_SECONDS: Final = 30
# A few failed GitHub polls in a row count as "still waiting".
_MAX_POLL_FAILURES: Final = 3
_MAX_RESPONSE_BYTES: Final = 1_048_576

CiState = Literal["pending", "passed", "failed"]


class DeployFailure(Exception):
    """A fixed, sanitized failure that never carries the hook or a response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _starts_workflow(path: PurePosixPath, patterns: tuple[str, ...]) -> bool:
    """Apply GitHub's path filter to one changed file: the last matching pattern wins."""
    starts = False
    for pattern in patterns:
        if pattern.startswith("!"):
            if path.full_match(pattern[1:]):
                starts = False
        elif path.full_match(pattern):
            starts = True
    return starts


def expected_workflows(changed_files: Iterable[str]) -> frozenset[str]:
    """Name every workflow that a push of these changed files starts on main."""
    paths = [PurePosixPath(name) for name in changed_files]
    return frozenset(
        name
        for name, patterns in _PUSH_WORKFLOWS.items()
        if any(_starts_workflow(path, patterns) for path in paths)
    )


def ci_state(runs: list[object], expected: frozenset[str]) -> CiState:
    """Classify the commit's CI from its GitHub Actions workflow runs."""
    relevant: list[dict[str, object]] = []
    for run in runs:
        if not isinstance(run, dict):
            return "failed"
        run = cast(dict[str, object], run)
        if run.get("name") not in _EXCLUDED_WORKFLOWS:
            relevant.append(run)
    if not expected <= {run.get("name") for run in relevant}:
        return "pending"
    if any(run.get("status") != "completed" for run in relevant):
        return "pending"
    if all(run.get("conclusion") in _PASSING for run in relevant):
        return "passed"
    return "failed"


def _request(url: str, *, token: str | None = None, method: str = "GET") -> object:
    headers = {"Accept": "application/json", "User-Agent": "tailtag-render-deploy"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            if response.status not in {200, 201, 202}:
                raise DeployFailure
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except (OSError, HTTPException, urllib.error.URLError):
        raise DeployFailure from None
    if len(body) > _MAX_RESPONSE_BYTES:
        raise DeployFailure
    try:
        return json.loads(body) if body else {}
    except ValueError:
        raise DeployFailure from None


class GitHub:
    """The few read-only GitHub REST calls the gate needs."""

    def __init__(self, api_url: str, repository: str, token: str) -> None:
        if not api_url.startswith("https://") or not _REPOSITORY.fullmatch(repository):
            raise DeployFailure
        self._base = f"{api_url.rstrip('/')}/repos/{repository}"
        self._token = token

    def workflow_runs(self, sha: str) -> list[object]:
        runs: list[object] = []
        page = 1
        while True:
            document = _request(
                f"{self._base}/actions/runs?head_sha={sha}&per_page=100&page={page}",
                token=self._token,
            )
            if not isinstance(document, dict):
                raise DeployFailure
            batch = cast(dict[str, object], document).get("workflow_runs")
            if not isinstance(batch, list):
                raise DeployFailure
            runs.extend(cast(list[object], batch))
            if len(cast(list[object], batch)) < 100:
                return runs
            page += 1

    def changed_files(self, sha: str) -> list[str]:
        files: list[str] = []
        page = 1
        while True:
            document = _request(
                f"{self._base}/commits/{sha}?per_page=100&page={page}",
                token=self._token,
            )
            if not isinstance(document, dict):
                raise DeployFailure
            batch = cast(dict[str, object], document).get("files")
            if not isinstance(batch, list):
                raise DeployFailure
            for entry in cast(list[object], batch):
                name = (
                    cast(dict[str, object], entry).get("filename")
                    if isinstance(entry, dict)
                    else None
                )
                if not isinstance(name, str) or not name:
                    raise DeployFailure
                files.append(name)
            if len(cast(list[object], batch)) < 100:
                return files
            page += 1

    def latest_backend_sha(self) -> str:
        document = _request(
            f"{self._base}/commits?sha=main&path={_BACKEND_PATH}&per_page=1",
            token=self._token,
        )
        if not isinstance(document, list) or not document:
            raise DeployFailure
        first = cast(list[object], document)[0]
        sha = (
            cast(dict[str, object], first).get("sha")
            if isinstance(first, dict)
            else None
        )
        if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
            raise DeployFailure
        return sha


def trigger_deploy(hook_url: str, sha: str) -> None:
    """Ask Render to deploy exactly this commit. Never reveal the hook URL."""
    if _HOOK.fullmatch(hook_url) is None or _SHA.fullmatch(sha) is None:
        raise DeployFailure
    _request(f"{hook_url}&ref={sha}", method="POST")


def wait_for_ci(
    github: GitHub,
    sha: str,
    *,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> CiState:
    """Wait until every other workflow on the commit finishes, or the deadline."""
    monotonic = monotonic or time.monotonic
    sleep = sleep or time.sleep
    deadline = monotonic() + _CI_DEADLINE_SECONDS
    expected: frozenset[str] | None = None
    failures = 0
    while True:
        state: CiState = "pending"
        try:
            if expected is None:
                expected = expected_workflows(github.changed_files(sha))
            state = ci_state(github.workflow_runs(sha), expected)
            failures = 0
        except DeployFailure:
            failures += 1
            if failures > _MAX_POLL_FAILURES:
                raise
        remaining = deadline - monotonic()
        if state != "pending" or remaining <= 0:
            return state
        sleep(min(_CI_RETRY_SECONDS, remaining))


def run(environment: Mapping[str, str], github: GitHub) -> bool:
    """Deploy the commit when CI passed and no newer backend commit exists."""
    sha = environment.get("TAILTAG_DEPLOY_SHA", "")
    if _SHA.fullmatch(sha) is None:
        raise DeployFailure
    # A manual run cancels any running deploy run, so an older SHA is an error.
    if (
        environment.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and github.latest_backend_sha() != sha
    ):
        raise DeployFailure
    state = wait_for_ci(github, sha)
    if state == "pending":
        # CI may still pass later, so a timeout must not look like a decision.
        raise DeployFailure
    if state == "failed":
        print("::notice::CI did not pass for this commit; not deploying.")
        return False
    if github.latest_backend_sha() != sha:
        print("::notice::A newer backend commit exists on main; not deploying.")
        return False
    trigger_deploy(environment.get("RENDER_DEVELOPMENT_DEPLOY_HOOK_URL", ""), sha)
    print("Render Development deploy requested.")
    return True


def main() -> int:
    """Run the gate and write only a fixed deploy decision to the step outputs."""
    try:
        github = GitHub(
            os.environ.get("GITHUB_API_URL", ""),
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ["GITHUB_TOKEN"],
        )
        deployed = run(os.environ, github)
    except (DeployFailure, KeyError):
        print("FAIL Render Development deploy unavailable", file=sys.stderr)
        return 1
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write(f"deployed={'true' if deployed else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
