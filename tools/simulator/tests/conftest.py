"""Keep shared setup's external time boundary deterministic across command tests."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tailtag_simulator import pool

_REAL_SLEEP = asyncio.sleep


@pytest.fixture(autouse=True)
def immediate_setup_time(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(_seconds: float) -> None:
        await _REAL_SLEEP(0)

    # Isolate setup time: token refresh, JWT expiry, safety, traffic and lease
    # renewal retain their separate existing clocks and sleep boundaries.
    monkeypatch.setattr(
        pool, "asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": sleep})
    )


# The simulation host workflow needs macOS or Linux (maintainer decision D1,
# issue #315 slice 3): it relays Unix-domain sockets over OpenSSH stream-local
# forwards, uses fcntl locks, and walks evidence trees with directory
# descriptors. These modules stay POSIX-only by design; the sim-host-* tasks
# fail fast on Windows instead. Linux CI runs them; the report header names
# them so the skip is visible.
WINDOWS_SKIPPED_MODULES = frozenset(
    {
        "test_host_artifacts.py",
        "test_host_bridge.py",
        "test_host_channel.py",
        "test_host_cli.py",
        "test_host_collect.py",
        "test_host_release.py",
        "test_host_runtime.py",
        "test_host_ssh.py",
    }
)


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Skip host-tooling modules on native Windows; collect normally elsewhere."""
    if sys.platform == "win32" and collection_path.name in WINDOWS_SKIPPED_MODULES:
        return True
    return None


def pytest_report_header() -> str | None:
    """Name the host-tooling modules that native Windows does not collect."""
    if sys.platform != "win32":
        return None
    return "Windows: skipping host-tooling test modules: " + ", ".join(
        sorted(WINDOWS_SKIPPED_MODULES)
    )
