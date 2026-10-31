"""Shared test support for TailTag's canonical Semgrep command contract."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

FROZEN_ROOT_HELPERS = frozenset(
    {
        "scripts/api_smoke.py",
        "scripts/api_auth_smoke.py",
        "scripts/api_replacement_auth_smoke.py",
        "scripts/api_staging_auth_smoke.py",
        "scripts/api_staging_preflight.py",
        "scripts/api_staging_operator_inspect.py",
        "scripts/api_staging_fixture_diagnose.py",
        "scripts/api_staging_managed_auth_diagnose.py",
        "scripts/api_staging_managed_auth_diagnose_ssh.py",
        "scripts/api_staging_managed_operator_replace_ssh.py",
        "scripts/api_staging_managed_password_rotate_ssh.py",
        "scripts/api_staging_operator_inspect_ssh.py",
        "scripts/api_staging_operator_lifecycle_ssh.py",
        "scripts/api_staging_operator_restart_ssh.py",
        "scripts/api_staging_registry_reconcile.py",
        "scripts/api_staging_registry_reconcile_remote.py",
        "scripts/api_staging_operator_matrix.py",
        "scripts/api_staging_operator_matrix_ssh.py",
        "scripts/api_staging_emergency_operator_ssh.py",
        "scripts/api_staging_emergency_operator_decommission_ssh.py",
        "scripts/api_development_delivery_event.py",
        "scripts/render_development_deploy.py",
        "scripts/api_media_storage_smoke.py",
        "scripts/api_environment_fingerprint.py",
        "scripts/clerk_development_session.py",
        "scripts/api_deployment_identity.py",
        "scripts/api_staging_promote.py",
        "scripts/api_staging_render_promote.py",
        "scripts/backend_ci_relevance.py",
        "scripts/doctor.py",
        "scripts/fvm_sdk.py",
        "scripts/mobile_run.py",
        "scripts/mobile_openapi.py",
        "scripts/api_sim_fixture_ssh.py",
        "scripts/api_sim_inspect_ssh.py",
        "scripts/api_sim_pool_ssh.py",
        "scripts/api_staging_reset.py",
        "scripts/api_staging_reset_ssh.py",
        "scripts/api_staging_reset_render_digest.py",
        "scripts/api_staging_render_job.py",
        "scripts/api_staging_restore_drill.py",
        "scripts/staging_restore_integrity.py",
        "scripts/validate_semgrep_contract.py",
    }
)
TASK_COMMAND_PREFIX = re.compile(r"^task: \[[^\]]+\] ")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def task_environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return a hermetic environment for running go-task from a test.

    GitHub Actions makes go-task emit ANSI colors and `::error` annotations, so
    the parent's GITHUB_ACTIONS is dropped and colors are disabled explicitly.
    An inherited UV (set by some CI images) is dropped too, because the
    Taskfile honors it; tests that exercise UV pass it as an override.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"GITHUB_ACTIONS", "UV"}
    }
    return {**environment, "NO_COLOR": "1", **(overrides or {})}


def run_task(
    *arguments: str,
    environment: dict[str, str] | None = None,
    cwd: Path = REPOSITORY_ROOT,
) -> subprocess.CompletedProcess[str]:
    """Run go-task from the repository root with optional environment overrides."""
    return subprocess.run(
        ["task", *arguments],
        cwd=cwd,
        env=task_environment(environment),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def task_dry_run(
    *targets: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Compile targets without executing; verbose mode also lists silent tasks."""
    completed = run_task("--dry", "--verbose", *targets, environment=environment)
    assert completed.returncode == 0, completed.stderr
    # go-task writes the dry-run echo to stderr; expose it as the output stream.
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        stdout=completed.stdout + completed.stderr,
        stderr="",
    )


PLATFORM_IGNORED = " not for current platform - ignored"


def dry_run_commands(dry_run: str) -> list[str]:
    """Return each command a go-task dry run would execute, continuations joined."""
    commands: list[list[str]] = []
    open_command = False
    for raw_line in dry_run.splitlines():
        line = raw_line.strip()
        prefix = TASK_COMMAND_PREFIX.match(line)
        if prefix:
            commands.append([line[prefix.end() :]])
            open_command = True
        elif not line or line.startswith("task: "):
            open_command = False
        elif open_command:
            commands[-1].append(line)

    joined = [
        " ".join(part.removesuffix("\\").rstrip() for part in parts)
        for parts in commands
    ]
    # go-task still lists commands whose `platforms:` exclude this OS; they never run.
    return [command for command in joined if not command.endswith(PLATFORM_IGNORED)]
