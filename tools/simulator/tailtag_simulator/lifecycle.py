"""Shared ownership of execution safety and its credential-free target probe."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from tailtag_simulator.client import open_client
from tailtag_simulator.reports import RunReport
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime
from tailtag_simulator.targets import resolve_target, verify_target


async def run_guarded(
    work: Callable[[], Awaitable[int]],
    *,
    safety: SafetyRuntime,
    target: str,
    base_url: str | None,
    population: int,
    transport: httpx.AsyncBaseTransport | None,
    report: RunReport | None,
    emit: Callable[[str], None],
) -> int:
    """Cancel and join the run, including its bounded recovery, on a safety stop."""
    try:
        resolved = resolve_target(target, base_url)

        async def probe() -> dict[str, object]:
            async with open_client(resolved.origin, transport=transport) as client:
                return (await verify_target(client, resolved)).identity()

        safety.bind_probe(probe, local=target == "local")
        with safety.scope():
            safety.validate_population(population)
            await safety.check_target()
            await safety.start_monitor()
            try:
                code = await safety.run_phase(work())
            finally:
                await safety.stop_monitor()
    except SafetyAborted:
        code = 1
    except asyncio.CancelledError:
        if report is not None:
            report.record_safety(safety.snapshot())
            report.finish(130)
        raise
    except Exception:  # noqa: BLE001 - no external details escape
        emit("FAIL target")
        code = 1
    if safety.abort_reason is not None:
        code = 1
        emit(f"FAIL safety reason={safety.abort_reason}")
    if report is not None:
        try:
            if safety.abort_reason == "correctness":
                report.set_correctness("failed")
            report.record_safety(safety.snapshot())
        except Exception:  # noqa: BLE001 - persistence must never pass
            safety.abort("report_failure", emit=False)
            code = 1
        return report.finish(code)
    return code
