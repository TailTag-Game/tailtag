"""Classify changed files for TailTag's backend pull-request validation."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

BACKEND_RELEVANT_PREFIXES = ("services/api/", ".semgrep/")
BACKEND_RELEVANT_FILES = {
    "Taskfile.yml",
    "scripts/api_smoke.py",
    "scripts/api_auth_smoke.py",
    "scripts/api_staging_auth_smoke.py",
    "scripts/render_development_deploy.py",
    "scripts/api_sim_fixture_ssh.py",
    "scripts/api_sim_inspect_ssh.py",
    "scripts/api_sim_render_relay.py",
    "scripts/api_sim_pool_ssh.py",
    "scripts/api_staging_render_promote.py",
    "scripts/api_staging_render_job.py",
    "scripts/api_staging_render_ssh.py",
    "scripts/api_staging_reset_render_digest.py",
    "scripts/api_staging_preflight.py",
    "scripts/api_media_storage_smoke.py",
    "scripts/clerk_development_session.py",
    "scripts/backend_ci_relevance.py",
    "scripts/doctor.py",
    "scripts/doctor.sh",
    "scripts/fvm_sdk.py",
    "scripts/mobile_run.py",
    "scripts/mobile_openapi.py",
    "scripts/validate_semgrep_contract.py",
    ".github/workflows/api.yml",
    ".github/workflows/render-development-deploy.yml",
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
