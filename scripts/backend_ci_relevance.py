"""Classify changed files for TailTag's backend pull-request validation."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

BACKEND_RELEVANT_PREFIXES = ("services/api/", ".semgrep/")
BACKEND_RELEVANT_FILES = {
    "Makefile",
    "scripts/api_smoke.py",
    "scripts/api_auth_smoke.py",
    "scripts/api_replacement_auth_smoke.py",
    "scripts/api_staging_auth_smoke.py",
    "scripts/api_environment_fingerprint.py",
    "scripts/api_deployment_identity.py",
    "scripts/api_development_delivery_event.py",
    "scripts/api_staging_emergency_operator_ssh.py",
    "scripts/api_staging_emergency_operator_decommission_ssh.py",
    "scripts/api_staging_promote.py",
    "scripts/api_staging_preflight.py",
    "scripts/api_staging_fixture_diagnose.py",
    "scripts/api_staging_managed_auth_diagnose.py",
    "scripts/api_staging_managed_auth_diagnose_ssh.py",
    "scripts/api_staging_managed_operator_replace_ssh.py",
    "scripts/api_staging_managed_password_rotate_ssh.py",
    "scripts/api_staging_operator_inspect.py",
    "scripts/api_staging_operator_inspect_ssh.py",
    "scripts/api_staging_operator_lifecycle_ssh.py",
    "scripts/api_staging_operator_matrix.py",
    "scripts/api_staging_operator_matrix_ssh.py",
    "scripts/api_staging_registry_reconcile.py",
    "scripts/api_staging_registry_reconcile_remote.py",
    "scripts/api_staging_reset.py",
    "scripts/api_staging_reset_ssh.py",
    "scripts/api_staging_restore_drill.py",
    "scripts/api_media_storage_smoke.py",
    "scripts/clerk_development_session.py",
    "scripts/backend_ci_relevance.py",
    "scripts/validate_semgrep_contract.py",
    ".github/workflows/api.yml",
    ".github/workflows/post-deploy-smoke.yml",
    ".semgrepignore",
}


def backend_validation_required(paths: Iterable[str]) -> bool:
    """Return whether any changed path affects the backend validation contract."""
    return any(
        path in BACKEND_RELEVANT_FILES or path.startswith(BACKEND_RELEVANT_PREFIXES)
        for path in paths
    )


def changed_paths(path: Path) -> list[str]:
    """Read NUL-delimited Git paths without losing unusual filenames."""
    return [
        item.decode(errors="surrogateescape")
        for item in path.read_bytes().split(b"\0")
        if item
    ]


def parse_arguments() -> argparse.Namespace:
    """Parse the workflow-facing classifier arguments."""
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--changed-files", type=Path)
    source.add_argument("--force-run", action="store_true")
    parser.add_argument("--github-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Classify changed paths and write a GitHub Actions step output."""
    arguments = parse_arguments()
    required = arguments.force_run or backend_validation_required(
        changed_paths(arguments.changed_files)
    )
    result = "true" if required else "false"
    arguments.github_output.write_text(f"backend_relevant={result}\n")
    message = (
        "Backend-relevant changes detected; backend validation required."
        if required
        else "No backend-relevant changes detected; backend validation skipped."
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
