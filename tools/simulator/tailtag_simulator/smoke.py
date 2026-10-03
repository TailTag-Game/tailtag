"""The manual authenticated smoke run: target check, then the three phases (A-2, A-9).

Output is a fixed set of stage lines. Failures map to a fixed stage name; exception
text, tokens, response bodies, and user IDs are never written.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager

import httpx

from tailtag_simulator.client import open_client
from tailtag_simulator.phases import (
    ReconciliationContext,
    SetupContext,
    SimulationContext,
    reconcile,
    setup,
    simulate,
)
from tailtag_simulator.targets import resolve_target, verify_target


class StageFailed(Exception):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


@contextmanager
def stage(name: str) -> Generator[None]:
    """Turn any failure inside the block into a fixed stage name, dropping its detail."""
    try:
        yield
    except Exception:  # noqa: BLE001 - failures become a fixed stage, never detail
        raise StageFailed(name) from None


async def run_smoke(
    target: str,
    *,
    base_url: str | None = None,
    prompt_token: Callable[[], str],
    emit: Callable[[str], None],
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Run the smoke and return the process exit code: 0 only if every stage passed."""
    try:
        with stage("target"):
            resolved = resolve_target(target, base_url)
            async with open_client(resolved.origin, transport=transport) as client:
                verified = await verify_target(client, resolved)
        source_sha = f" source_sha={verified.source_sha}" if verified.source_sha else ""
        emit(f"PASS target {resolved.name}{source_sha}")

        with stage("setup"):
            credentials = setup(SetupContext(verified, prompt_token))
        emit("PASS setup")

        with stage("simulation"):
            async with open_client(
                resolved.origin, token=credentials.token, transport=transport
            ) as client:
                observations = await simulate(SimulationContext(client))
        emit("PASS simulation")

        with stage("reconciliation"):
            reconcile(ReconciliationContext(observations))
        emit("PASS reconciliation")
    except StageFailed as failure:
        emit(f"FAIL {failure.stage}")
        return 1
    return 0
