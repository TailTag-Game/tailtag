"""Shared test support for TailTag's canonical Semgrep command contract."""

from __future__ import annotations

import re

FROZEN_ROOT_HELPERS = frozenset(
    {
        "scripts/api_smoke.py",
        "scripts/api_auth_smoke.py",
        "scripts/api_media_storage_smoke.py",
        "scripts/clerk_development_session.py",
        "scripts/backend_ci_relevance.py",
        "scripts/validate_semgrep_contract.py",
    }
)
MAKE_DIRECTORY_DIAGNOSTIC = re.compile(
    r"^make(?:\[\d+\])?: (?:Entering|Leaving) directory "
)


def dry_run_commands(dry_run: str) -> list[str]:
    """Collapse Make continuations and omit recursive-Make diagnostics."""
    commands: list[str] = []
    fragments: list[str] = []
    for raw_line in dry_run.splitlines():
        line = raw_line.strip()
        if not line or MAKE_DIRECTORY_DIAGNOSTIC.match(line):
            continue
        if line.endswith("\\"):
            fragments.append(line[:-1].rstrip())
            continue
        if fragments:
            fragments.append(line)
            commands.append(" ".join(fragments))
            fragments = []
        else:
            commands.append(line)

    assert not fragments, "Make dry run must not end with a shell continuation"
    return commands
