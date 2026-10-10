"""Measured-traffic evidence produced by the real runtime, for report fixtures."""

import asyncio
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from traffic_support import ManualClock

from tailtag_simulator.client import Reply
from tailtag_simulator.traffic import TrafficRuntime
from tailtag_simulator.traffic_config import resolve_traffic_config
from tailtag_simulator.traffic_effects import InjectedFailure

OPERATIONS = ("auxiliary", "resolve", "confirm", "read")
CLASSES = (
    "success",
    "expected_rejection",
    "client_error",
    "server_error",
    "timeout",
    "transport_error",
    "injected",
)


def traffic_snapshot() -> dict[str, Any]:
    # Independent observed evidence: one offered arrival was skipped, two finished.
    return {
        "plan_digest": "a" * 64,
        "offered": 3,
        "admitted": 2,
        "skipped": 1,
        "completed": 2,
        "active_peak": 2,
        "in_flight_peak": 1,
        "attempts": 8,
        "sent": 7,
        "injected": 1,
        "transient": 0,
        "retries": 1,
        "expected_rejections": 0,
        "exhausted": 0,
        "unresolved": 0,
        "generation_seconds": 2.0,
        "drain_seconds": 0.1,
        "lag_seconds": 0.01,
        "stop_reason": None,
        "buckets": [
            {
                "at_seconds": 0.0,
                "offered": 2,
                "admitted": 1,
                "skipped": 1,
                "completed": 1,
            },
            {
                "at_seconds": 1.0,
                "offered": 1,
                "admitted": 1,
                "skipped": 0,
                "completed": 1,
            },
        ],
    }


def _runtime(snapshot: Mapping[str, Any]) -> tuple[TrafficRuntime, ManualClock]:
    time = ManualClock()
    runtime = TrafficRuntime(
        resolve_traffic_config({"pool": "alpha"}), clock=time.clock
    )
    runtime.generation_seconds = snapshot["generation_seconds"]
    runtime.drain_seconds = snapshot["drain_seconds"]
    return runtime, time


def idle_performance(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The measurement of a run that made no request, over the snapshot's window."""
    runtime, _ = _runtime(snapshot)
    return runtime.performance()


def measured_performance(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Six responses and one injected attempt, consistent with `traffic_snapshot`."""
    runtime, time = _runtime(snapshot)

    async def attempt(
        operation: str, status: int, milliseconds: float, injection: str = "none"
    ) -> None:
        async def send() -> Reply:
            time.now += milliseconds / 1000
            if injection == "pre_send":
                raise InjectedFailure
            return Reply(status, None)

        try:
            await runtime.request(send, operation=operation, injection=injection)
        except InjectedFailure:
            pass

    async def measure() -> None:
        await attempt("resolve", 200, 10)
        await attempt("resolve", 200, 30)
        await attempt("resolve", 404, 20)
        await attempt("confirm", 201, 40)
        await attempt("confirm", 503, 50)
        await attempt("confirm", 0, 1, "pre_send")
        await attempt("read", 200, 5)

    # A fresh loop on a worker thread, so callers may already be inside a loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, measure()).result()
    return runtime.performance()
