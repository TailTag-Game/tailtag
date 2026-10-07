"""#224 independent fixtures: literal JSON, clocks and disposable real Git only."""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from tailtag_simulator import scenarios

if TYPE_CHECKING:
    from tailtag_simulator.reports import RunReport

DATA = Path(__file__).parent / "data/report-v1-smoke.json"
RUN_ID = "123e4567-e89b-42d3-a456-426614174000"
SHA = "0123456789abcdef0123456789abcdef01234567"
DEPLOYMENT = "223e4567-e89b-42d3-a456-426614174000"


def literal_report() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


class ReportClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 10, 5, 12, tzinfo=UTC)
        self.elapsed = 100.0

    def wall_clock(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.elapsed


def recorder(
    root: Path,
    scenario: str = "smoke",
    *,
    config: dict[str, object] | None = None,
    clock: ReportClock | None = None,
    run_id: str | None = RUN_ID,
) -> "RunReport":
    from tailtag_simulator.reports import RunReport

    clock = clock or ReportClock()
    report = RunReport(
        root,
        scenario,
        config=config or {"target": "staging", "base_url": None},
        run_id=run_id,
        wall_clock=clock.wall_clock,
        monotonic=clock.monotonic,
    )
    report.record_source(literal_report()["source"])
    report.begin("provenance")
    report.end("provenance", "passed")
    return report


def git(root: Path, *arguments: str) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Finn the Panther",
        GIT_AUTHOR_EMAIL="finn@finnthepanther.com",
        GIT_COMMITTER_NAME="Finn the Panther",
        GIT_COMMITTER_EMAIL="finn@finnthepanther.com",
    )
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def commit(root: Path, message: str) -> None:
    # Verify the effective identities immediately before each disposable commit.
    for role in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        assert git(root, "var", role).startswith(
            "Finn the Panther <finn@finnthepanther.com> "
        )
    git(root, "add", ".")
    git(root, "commit", "-m", message)


def repository(root: Path, files: dict[str, str | bytes]) -> Path:
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Finn the Panther")
    git(root, "config", "user.email", "finn@finnthepanther.com")
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
    commit(root, "Initial disposable fixture")
    return root


def read_report(path: Path) -> dict[str, Any]:
    """Typed access to the actual reader, without rebuilding expected behavior."""
    from tailtag_simulator.reports import load_report

    return cast(dict[str, Any], load_report(path))


def disposable_catalog(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fault injection owns a copy, never the repository's published descriptors."""
    catalog = root / "catalog"
    shutil.copytree(scenarios.CATALOG, catalog)
    monkeypatch.setattr(scenarios, "CATALOG", catalog)
    return catalog


def fault_descriptor(path: Path, fault: str) -> None:
    if fault == "missing":
        path.unlink()
    elif fault == "invalid":
        path.write_text("{SENTINEL-private-descriptor", encoding="utf-8")
    elif fault == "changed":
        entry = json.loads(path.read_text(encoding="utf-8"))
        # Parseable, digest-consistent JSON still violates the admitted contract.
        entry["roles"] = ["SENTINEL-private-role"]
        descriptor = {k: v for k, v in entry.items() if k != "descriptor_digest"}
        entry["descriptor_digest"] = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        path.write_text(json.dumps(entry), encoding="utf-8")
    else:
        raise AssertionError(f"Unsupported test fault: {fault}")
