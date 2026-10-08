"""Finite convention populations using the established fixture lifecycle."""

import time
import uuid
from collections.abc import Callable, Mapping
from typing import Literal, cast

import httpx

from tailtag_simulator.behavior import (
    PopulationCancelled,
    PopulationContext,
    PopulationRun,
    simulate_population,
)
from tailtag_simulator.behavior_config import resolve_behavior_config
from tailtag_simulator.client import ApiClient
from tailtag_simulator.fixtures import FixtureChannel, run_provisioned
from tailtag_simulator.pool import LeaseChannel
from tailtag_simulator.population_reconciliation import (
    PopulationInspectionChannel,
    population_reconciliation_lines,
    reconcile_population,
)
from tailtag_simulator.reports import ReportFailed, RunReport
from tailtag_simulator.safety import SafetyRuntime, active_runtime
from tailtag_simulator.scenarios import ScenarioRejected
from tailtag_simulator.smoke import StageFailed, guarded_stage
from tailtag_simulator.traffic import Clock, TrafficRuntime
from tailtag_simulator.traffic_behavior import (
    TrafficCancelled,
    simulate_traffic_population,
)
from tailtag_simulator.traffic_config import resolve_traffic_config

_DEFAULT_TRAFFIC_CLOCK = Clock()


async def run_convention(
    pool: str,
    *,
    config: Mapping[str, object],
    seed: int,
    scenario_version: int = 1,
    traffic_clock: Clock = _DEFAULT_TRAFFIC_CLOCK,
    prompt_secret: Callable[[], str],
    lease_channel: LeaseChannel,
    fixture_channel: FixtureChannel,
    inspection_channel: PopulationInspectionChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
) -> int:
    try:
        if type(scenario_version) is not int or scenario_version not in (1, 2):
            raise ScenarioRejected
        normalized = (
            resolve_traffic_config if scenario_version == 2 else resolve_behavior_config
        )(config)
        if normalized["pool"] != pool or type(seed) is not int:
            raise ScenarioRejected
    except (ScenarioRejected, ValueError):
        emit("FAIL configuration")
        return 1
    owners = cast(int, normalized["normal_owners"]) + cast(
        int, normalized["popular_owners"]
    )
    attendees = sum(
        cast(int, normalized[p]) for p in ("casual", "active", "heavy", "retry_prone")
    )
    run = report.run_id if report is not None else run_id or str(uuid.uuid4())

    partial: PopulationRun | None = None
    recovery_clients: tuple[ApiClient, ...] = ()
    recovery_indexes: tuple[int, ...] = ()
    reconciliation_state: Literal["not_observed", "passed", "failed"] = "not_observed"

    async def reconcile_partial() -> None:
        if reconciliation_state != "not_observed":
            if reconciliation_state == "failed":
                raise StageFailed("reconciliation")
            return
        if partial is None:
            return
        labels = tuple(f"owner{n}" for n in range(owners)) + tuple(
            f"attendee{n}" for n in range(attendees)
        )
        checked = await reconcile_population(
            partial.expectations,
            dict(zip(labels, recovery_clients, strict=True)),
            dict(zip(labels, recovery_indexes, strict=True)),
            inspection_channel,
            pool=pool,
            run_id=run,
            convention=partial.convention,
        )

        if report is not None:
            report.record_population_checks(
                {
                    "items": [
                        {
                            "check": d.check,
                            "actor": d.actor,
                            "expected": d.expected,
                            "observed": d.observed,
                        }
                        for d in checked.discrepancies
                    ],
                    "count": checked.count,
                    "reason": None,
                }
            )
        for line in population_reconciliation_lines(checked):
            emit(line)

        if not checked.passed:
            if checked.integrity_failed:
                safety_runtime = active_runtime()
                if safety_runtime is not None:
                    safety_runtime.abort("correctness")
            raise StageFailed("reconciliation")

    async def population(
        origin: str,
        clients: tuple[ApiClient, ...],
        indexes: tuple[int, ...],
    ) -> Literal["pass", "journeys", "reconciliation"]:
        nonlocal partial, recovery_clients, recovery_indexes, reconciliation_state
        del origin
        recovery_clients, recovery_indexes = clients, indexes
        context = PopulationContext(clients[:owners], clients[owners:])
        runtime = (
            TrafficRuntime(normalized, clock=traffic_clock)
            if scenario_version == 2
            else None
        )
        async with guarded_stage("simulation", report):
            if runtime is None:
                try:
                    simulated = await simulate_population(context, normalized, seed)
                except PopulationCancelled as cancellation:
                    partial = cancellation.population
                    if report is not None:
                        try:
                            report.record_behavior(partial.summaries, partial.failure)
                        except ReportFailed:
                            pass  # Durable report failure cannot prevent recovery.
                    raise
            else:
                try:
                    traffic_run = await simulate_traffic_population(
                        context, normalized, seed, clock=traffic_clock, runtime=runtime
                    )
                except TrafficCancelled as cancellation:
                    partial = cancellation.population
                    if report is not None:
                        try:
                            report.record_behavior(
                                cancellation.population.summaries,
                                cancellation.population.failure,
                            )
                            report.record_traffic(runtime.snapshot())
                        except ReportFailed:
                            pass  # Persistence cannot prevent cancellation/finalization.
                    raise
                simulated = traffic_run.population
        partial = simulated
        report_failed = False
        if report is not None:
            try:
                report.record_behavior(simulated.summaries, simulated.failure)
                if runtime is not None:
                    report.record_traffic(runtime.snapshot())
            except ReportFailed:
                report_failed = True
        labels = tuple(f"owner{n}" for n in range(owners)) + tuple(
            f"attendee{n}" for n in range(attendees)
        )
        async with guarded_stage("reconciliation", report):
            checked = await reconcile_population(
                simulated.expectations,
                dict(zip(labels, clients, strict=True)),
                dict(zip(labels, indexes, strict=True)),
                inspection_channel,
                pool=pool,
                run_id=run,
                convention=simulated.convention,
            )
        reconciliation_state = "passed" if checked.passed else "failed"
        if report is not None:
            try:
                report.record_population_checks(
                    {
                        "items": [
                            {
                                "check": d.check,
                                "actor": d.actor,
                                "expected": d.expected,
                                "observed": d.observed,
                            }
                            for d in checked.discrepancies
                        ],
                        "count": checked.count,
                        "reason": None,
                    }
                )
                if runtime is not None:
                    report.set_correctness("passed" if checked.passed else "failed")
            except ReportFailed:
                report_failed = True
        for line in population_reconciliation_lines(checked):
            emit(line)
        if checked.integrity_failed:
            safety_runtime = active_runtime()
            if safety_runtime is not None:
                safety_runtime.abort("correctness")
            return "reconciliation"
        if report_failed:
            raise StageFailed("report")
        traffic = runtime.snapshot() if runtime is not None else None
        if not simulated.passed or (
            traffic is not None
            and (
                traffic["stop_reason"] is not None
                or traffic["exhausted"]
                or traffic["unresolved"]
            )
        ):
            emit("FAIL simulation result=FAIL_SIMULATION")
            return "journeys"
        return "pass" if checked.passed else "reconciliation"

    return await run_provisioned(
        pool,
        owners,
        cast(int, normalized["fursuits"]),
        attendees,
        0,
        prompt_secret=prompt_secret,
        lease_channel=lease_channel,
        fixture_channel=fixture_channel,
        emit=emit,
        clerk_transport=clerk_transport,
        api_transport=api_transport,
        clock=clock,
        run_id=run,
        report=report,
        safety=safety,
        simulate_and_reconcile=population,
        renew_leases=True,
        reconcile_partial=reconcile_partial,
    )
