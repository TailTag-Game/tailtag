"""Keep shared setup's external time boundary deterministic across command tests."""

import asyncio
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
