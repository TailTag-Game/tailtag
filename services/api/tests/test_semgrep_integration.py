"""End-to-end contracts for TailTag's canonical Semgrep scan."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FROZEN_ROOT_HELPERS = frozenset(
    {
        "scripts/api_smoke.py",
        "scripts/api_auth_smoke.py",
        "scripts/clerk_development_session.py",
        "scripts/backend_ci_relevance.py",
        "scripts/validate_semgrep_contract.py",
    }
)


def tracked_semgrep_targets(repository: Path) -> set[Path]:
    """Derive the approved API portion from Git, not Makefile operands."""
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "services/api"],
        cwd=repository,
        capture_output=True,
        check=True,
    )
    api_sources = {
        repository / os.fsdecode(path)
        for path in completed.stdout.split(b"\0")
        if path and path.endswith(b".py")
    }
    return {path.resolve() for path in api_sources} | {
        (repository / helper).resolve() for helper in FROZEN_ROOT_HELPERS
    }


def canonical_main_scan_command(repository: Path) -> tuple[dict[str, str], list[str]]:
    """Take the main scan's actual command construction directly from Make."""
    dry_run = subprocess.run(
        ["make", "-n", "api-semgrep-check"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    commands: list[str] = []
    fragments: list[str] = []
    for raw_line in dry_run.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith("\\"):
            fragments.append(line[:-1].rstrip())
            continue
        if fragments:
            fragments.append(line)
            line = " ".join(fragments)
            fragments = []
        if "semgrep scan" in line and "--test" not in line:
            commands.append(line)
    assert not fragments, "Make dry run must not end with a shell continuation"
    assert len(commands) == 1

    tokens = shlex.split(commands[0])
    environment: dict[str, str] = {}
    while "=" in tokens[0] and not tokens[0].startswith("-"):
        name, value = tokens.pop(0).split("=", maxsplit=1)
        environment[name] = value
    return environment, tokens


def test_canonical_main_scan_reports_exact_frozen_tracked_scope() -> None:
    """The canonical configuration scans every tracked API Python file and no drift."""
    command_environment, command = canonical_main_scan_command(REPOSITORY_ROOT)
    command.append("--json")

    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env={**os.environ, **command_environment, "SEMGREP_BASELINE_COMMIT": ""},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    scanned = {Path(path).resolve() for path in report["paths"]["scanned"]}
    assert scanned == tracked_semgrep_targets(REPOSITORY_ROOT)
    assert any(path.name.startswith("test_") for path in scanned)


def test_inherited_baseline_cannot_suppress_the_canonical_make_scan(
    tmp_path: Path,
) -> None:
    """A real inherited baseline cannot hide a new violation from the Make target."""
    api_venv = REPOSITORY_ROOT / "services" / "api" / ".venv"
    semgrep_venv = REPOSITORY_ROOT / ".semgrep" / ".venv"
    assert api_venv.is_dir()
    assert semgrep_venv.is_dir()

    clone = tmp_path / "baseline-probe"
    cloned = subprocess.run(
        ["git", "clone", "--no-hardlinks", str(REPOSITORY_ROOT), str(clone)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / ".git").is_dir()

    for relative_venv, source_venv in (
        (Path("services/api/.venv"), api_venv),
        (Path(".semgrep/.venv"), semgrep_venv),
    ):
        destination = clone / relative_venv
        if destination.is_symlink() or destination.exists():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.symlink_to(source_venv, target_is_directory=True)

    for key, value in (
        ("user.name", "TailTag-Test"),
        ("user.email", "tailtag-test@example.invalid"),
    ):
        configured = subprocess.run(
            ["git", "config", key, value],
            cwd=clone,
            capture_output=True,
            text=True,
            check=False,
        )
        assert configured.returncode == 0, configured.stderr

    probe = clone / "services" / "api" / "tests" / "test_semgrep_baseline_probe.py"
    probe.write_text("user_input = 'untrusted'\neval(user_input)\n")
    committed = subprocess.run(
        ["git", "add", str(probe.relative_to(clone))],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    )
    assert committed.returncode == 0, committed.stderr
    committed = subprocess.run(
        ["git", "commit", "-m", "test: plant Semgrep baseline probe"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=False,
    )
    assert committed.returncode == 0, committed.stderr

    completed = subprocess.run(
        ["make", "api-semgrep-check"],
        cwd=clone,
        env={**os.environ, "SEMGREP_BASELINE_COMMIT": "HEAD"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    rule_ids = set(
        re.findall(
            r"tailtag\.[a-z0-9]+(?:[.-][a-z0-9]+)+", completed.stdout + completed.stderr
        )
    )
    assert rule_ids == {"tailtag.python.dynamic-execution"}
