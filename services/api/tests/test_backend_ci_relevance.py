"""Contracts for backend pull-request validation relevance."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLASSIFIER = REPOSITORY_ROOT / "scripts" / "backend_ci_relevance.py"


def classify_paths(tmp_path: Path, paths: list[str]) -> bool:
    """Run the workflow-facing classifier and return its GitHub output."""
    changed_files = tmp_path / "changed-files"
    changed_files.write_bytes(b"\0".join(os.fsencode(path) for path in paths) + b"\0")
    github_output = tmp_path / "github-output"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLASSIFIER),
            "--changed-files",
            str(changed_files),
            "--github-output",
            str(github_output),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    return github_output.read_text() == "backend_relevant=true\n"


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["services/api/config/settings/base.py"], True),
        (["services/api/tests/test_health.py"], True),
        (["services/api/uv.lock"], True),
        (["services/api/compose.yaml"], True),
        (["Makefile"], True),
        (["scripts/api_smoke.py"], True),
        (["scripts/api_auth_smoke.py"], True),
        (["scripts/clerk_development_session.py"], True),
        (["scripts/backend_ci_relevance.py"], True),
        (["scripts/validate_semgrep_contract.py"], True),
        ([".github/workflows/api.yml"], True),
        ([".semgrepignore"], True),
        ([".semgrep/pyproject.toml"], True),
        ([".semgrep/uv.lock"], True),
        ([".semgrep/.gitignore"], True),
        ([".semgrep/rules/tailtag-security.yml"], True),
        ([".semgrep/tests/tailtag-security.py"], True),
        ([".semgrep/notes/future-policy.md"], True),
        (["docs/development/getting-started.md"], False),
        (["README.md"], False),
        (["CONTRIBUTING.md"], False),
        (["scripts/doctor.sh"], False),
        ([".devcontainer/devcontainer.json"], False),
        ([".github/workflows/repository-checks.yml"], False),
        (["apps/mobile/src/App.tsx"], False),
    ],
)
def test_classification_matches_the_backend_path_contract(
    tmp_path: Path, paths: list[str], expected: bool
) -> None:
    """Only paths that influence API validation require the full backend suite."""
    assert classify_paths(tmp_path, paths) is expected


def test_classification_runs_for_mixed_changes_when_any_path_is_relevant(
    tmp_path: Path,
) -> None:
    """One backend path makes a mixed pull request require validation."""
    assert classify_paths(
        tmp_path,
        ["docs/development/getting-started.md", "services/api/health/views.py"],
    )


def test_classification_skips_multiple_unrelated_changes(tmp_path: Path) -> None:
    """Several irrelevant paths do not collectively require backend validation."""
    assert not classify_paths(
        tmp_path,
        [
            "README.md",
            "docs/development/getting-started.md",
            ".github/ISSUE_TEMPLATE/03-work-item.yml",
        ],
    )


def test_manual_dispatch_requires_backend_validation(tmp_path: Path) -> None:
    """Manual workflow dispatches run the canonical backend suite."""
    github_output = tmp_path / "github-output"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLASSIFIER),
            "--force-run",
            "--github-output",
            str(github_output),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert github_output.read_text() == "backend_relevant=true\n"
