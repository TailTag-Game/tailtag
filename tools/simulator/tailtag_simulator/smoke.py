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
from tailtag_simulator.reports import RunReport
from tailtag_simulator.targets import VerifiedTarget, resolve_target, verify_target


class StageFailed(Exception):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


@contextmanager
def stage(name: str, report: RunReport | None = None) -> Generator[None]:
    """Turn any failure inside the block into a fixed stage name, dropping its detail."""
    if report is not None:
        report.begin(name)
    try:
        yield
    except BaseException as failure:
        if report is not None:
            interrupted = not isinstance(failure, Exception)
            report.end(
                name,
                "interrupted" if interrupted else "failed",
                "FAIL_INTERRUPTED" if interrupted else "FAIL_" + name.upper(),
            )
            if name == "reconciliation" and not interrupted:
                report.set_correctness("failed")
        if not isinstance(failure, Exception):
            raise
        raise StageFailed(name) from None
    else:
        if report is not None:
            report.end(name, "passed")


async def attribute(
    verified: VerifiedTarget,
    report: RunReport,
    transport: httpx.AsyncBaseTransport | None,
) -> None:
    with stage("attribution", report):
        async with open_client(verified.target.origin, transport=transport) as probe:
            final = await verify_target(probe, verified.target)
        report.record_target(
            final.target.name, final.target.origin, final.identity(), final=True
        )
        if final != verified:
            raise StageFailed("attribution")


async def run_smoke(
    target: str,
    *,
    base_url: str | None = None,
    prompt_token: Callable[[], str],
    emit: Callable[[str], None],
    transport: httpx.AsyncBaseTransport | None = None,
    report: RunReport | None = None,
) -> int:
    """Run the smoke and return the process exit code: 0 only if every stage passed."""
    try:
        with stage("target", report):
            resolved = resolve_target(target, base_url)
            async with open_client(resolved.origin, transport=transport) as client:
                verified = await verify_target(client, resolved)
        if report is not None:
            report.record_target(resolved.name, resolved.origin, verified.identity())
        source_sha = f" source_sha={verified.source_sha}" if verified.source_sha else ""
        emit(f"PASS target {resolved.name}{source_sha}")

        with stage("setup", report):
            credentials = setup(SetupContext(verified, prompt_token))
        emit("PASS setup")

        with stage("simulation", report):
            async with open_client(
                resolved.origin, token=credentials.token, transport=transport
            ) as client:
                observations = await simulate(SimulationContext(client))
        emit("PASS simulation")

        with stage("reconciliation", report):
            reconcile(ReconciliationContext(observations))
        emit("PASS reconciliation")
        if report is not None:
            report.set_correctness("passed")
            await attribute(verified, report, transport)
    except StageFailed as failure:
        emit(f"FAIL {failure.stage}")
        return report.finish(1) if report is not None else 1
    except BaseException:
        if report is not None:
            report.finish(130)
        raise
    return report.finish(0) if report is not None else 0
