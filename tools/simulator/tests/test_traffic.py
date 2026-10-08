"""AC8/9/15/16/18: real scheduler and request admission at time/HTTP seams."""

import asyncio
import random
import re
from collections.abc import Mapping
from typing import cast

import httpx
import pytest
from traffic_support import ManualClock

from tailtag_simulator.client import Reply, open_client
from tailtag_simulator.traffic import (
    Entry,
    TrafficRuntime,
    TrafficStopped,
    run_schedule,
)
from tailtag_simulator.traffic_config import resolve_traffic_config


def config(**overrides: object) -> dict[str, object]:
    return resolve_traffic_config({"pool": "alpha", **overrides})


def counts(snapshot: Mapping[str, object]) -> None:
    assert snapshot["offered"] == cast(int, snapshot["admitted"]) + cast(
        int, snapshot["skipped"]
    )
    assert 0 <= cast(int, snapshot["completed"]) <= cast(int, snapshot["admitted"])
    buckets = cast(list[dict[str, object]], snapshot["buckets"])
    assert len(buckets) <= 1000
    for key in ("offered", "admitted", "skipped", "completed"):
        assert sum(cast(int, bucket[key]) for bucket in buckets) == snapshot[key]
    assert re.fullmatch(r"[0-9a-f]{64}", cast(str, snapshot["plan_digest"]))


@pytest.mark.parametrize(("start", "end"), [(0, 4), (4, 0), (2, 2)])
def test_linear_arrivals_offer_hand_checked_total_and_report_actual_timing(
    start: int,
    end: int,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 2, "start": start, "end": end}],
                "think_seconds": 0,
            }
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        observed: list[tuple[Entry, float]] = []

        async def entry(value: Entry) -> bool:
            observed.append((value, time.now))
            return True

        task = asyncio.create_task(
            run_schedule(resolved, 81, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(2.1)
            assert task.done(), "finite arrivals did not finish"
            result = await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # A two-second triangle of height four, or rectangle of height two,
        # offers four journeys. These literal fixtures catch rate-as-RPS ticks.
        assert result["offered"] == result["admitted"] == result["completed"] == 4
        assert result["skipped"] == 0
        assert result["stop_reason"] is None
        assert all(0 <= value.at_seconds <= 2 for value, _ in observed)
        assert all(
            value.at_seconds <= actual + 1e-9 <= value.at_seconds + 0.011
            for value, actual in observed
        )
        if start == 0:
            assert sum(value.at_seconds < 1 for value, _ in observed) <= 1
        if end == 0:
            assert sum(value.at_seconds <= 1 for value, _ in observed) >= 2
        counts(result)
        assert runtime.snapshot() == result

    asyncio.run(execute())


def test_burst_skips_busy_capacity_without_backlog_or_same_actor_overlap() -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            casual=2,
            active=0,
            heavy=0,
            retry_prone=0,
            traffic={
                "segments": [{"duration_seconds": 1, "start": 0, "end": 0}],
                "bursts": [{"at_seconds": 0.1, "count": 8}],
                "think_seconds": 0,
            },
            limits={"active": 1},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        release = asyncio.Event()
        busy: set[int] = set()
        starts: list[Entry] = []

        async def entry(value: Entry) -> bool:
            assert value.actor not in busy, "ordinary journeys overlapped one identity"
            busy.add(value.actor)
            starts.append(value)
            try:
                await release.wait()
                return True
            finally:
                busy.remove(value.actor)

        task = asyncio.create_task(
            run_schedule(resolved, 42, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(0.2)
            assert len(starts) == 1
            assert runtime.snapshot()["offered"] == 8
            release.set()
            await time.through(1.1)
            assert task.done()
            result = await task
            assert len(starts) == 1, (
                "skipped offers were queued and replayed after capacity returned"
            )
            assert (
                result["admitted"] == result["completed"] == result["active_peak"] == 1
            )
            assert result["skipped"] == 7
            assert result["stop_reason"] is None
            assert not busy
            counts(result)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_late_wake_stops_generation_before_admitting_overdue_arrivals() -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 0.4, "start": 10, "end": 10}],
                "think_seconds": 0,
            },
            limits={"generation_seconds": 0.4, "drain_seconds": 0.1},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: list[Entry] = []

        async def entry(value: Entry) -> bool:
            starts.append(value)
            return True

        existing_tasks = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.settle()
            # A blocked event loop wakes after both generation and drain expired.
            await time.advance(1)
            assert task.done(), "late wake did not stop and await traffic work"
            result = await task
            assert starts == [], "overdue offers were admitted after generation expired"
            assert result["admitted"] == result["completed"] == 0
            assert result["stop_reason"] == "generation"
            assert not (set(asyncio.all_tasks()) - existing_tasks)
            counts(result)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_active_actor_plan_is_completion_independent_and_busy_actor_is_skipped() -> (
    None
):
    async def execute(
        short_ordinal: int, *, two_actors: bool = False
    ) -> tuple[dict[int, Entry], dict[str, object]]:
        time = ManualClock()
        population: dict[str, object] = (
            {"casual": 2, "active": 0, "heavy": 0, "retry_prone": 0}
            if two_actors
            else {}
        )
        resolved = config(
            **population,
            traffic={
                "mode": "active",
                "segments": [{"duration_seconds": 0.4, "start": 2, "end": 2}],
                "think_seconds": 0,
            },
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: dict[int, Entry] = {}
        busy: set[int] = set()

        async def entry(value: Entry) -> bool:
            assert value.actor not in busy
            busy.add(value.actor)
            starts[value.ordinal] = value
            try:
                await time.clock.sleep(0.05 if value.ordinal == short_ordinal else 0.3)
                return True
            finally:
                busy.remove(value.actor)

        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(0.8)
            assert task.done()
            result = await task
            assert result["stop_reason"] is None
            assert not busy
            counts(result)
            return starts, result
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    first, _ = asyncio.run(execute(0))
    second, _ = asyncio.run(execute(1))
    assert first[2].at_seconds == second[2].at_seconds == pytest.approx(0.1)
    assert first[2].actor == second[2].actor, (
        "first completed actor changed the intended logical actor for ordinal two"
    )
    blocked, result = asyncio.run(execute(1, two_actors=True))
    assert 2 not in blocked, "busy intended actor was replaced by a free identity"
    assert cast(int, result["skipped"]) > 0


@pytest.mark.parametrize("mode", ["arrivals", "active"])
def test_late_wake_after_profile_end_skips_overdue_admission_groups(mode: str) -> None:
    async def execute() -> None:
        time = ManualClock()
        rate = 4 if mode == "arrivals" else 2
        resolved = config(
            traffic={
                "mode": mode,
                "segments": [{"duration_seconds": 1, "start": rate, "end": rate}],
                "think_seconds": 0,
            },
            limits={"generation_seconds": 3},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: list[tuple[Entry, float]] = []

        async def entry(value: Entry) -> bool:
            starts.append((value, time.now))
            return True

        existing_tasks = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.settle()
            initial_starts = len(starts)
            await time.advance(1.5)
            assert task.done(), "expired profile left scheduled work running"
            result = await task
            assert len(starts) == initial_starts, (
                "missed groups were replayed after the traffic profile ended"
            )
            assert all(actual < 1 for _, actual in starts)
            assert result["admitted"] == result["completed"] == initial_starts
            assert cast(int, result["skipped"]) > 0
            if mode == "arrivals":
                assert result["offered"] == result["skipped"] == 4
            counts(result)
            assert not (set(asyncio.all_tasks()) - existing_tasks)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_midprofile_late_wake_coalesces_arrivals_and_preserves_future_offer() -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 1, "start": 4, "end": 4}],
                "think_seconds": 0,
            },
            limits={"generation_seconds": 3},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: list[tuple[Entry, float]] = []

        async def entry(value: Entry) -> bool:
            starts.append((value, time.now))
            return True

        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.settle()
            await time.advance(0.8)
            assert len(starts) == 1, "older missed groups became a catch-up cluster"
            assert starts[0][0].at_seconds == pytest.approx(0.75)
            snapshot = runtime.snapshot()
            assert snapshot["offered"] == 3
            assert snapshot["admitted"] == snapshot["completed"] == 1
            assert snapshot["skipped"] == 2
            await time.through(1)
            assert task.done(), "future scheduled offer did not complete"
            result = await task
            assert len(starts) == 2
            assert starts[1][0].at_seconds == pytest.approx(1)
            assert starts[1][1] == pytest.approx(1)
            assert result["offered"] == 4
            assert result["admitted"] == result["completed"] == result["skipped"] == 2
            assert result["stop_reason"] is None
            counts(result)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_preparation_elapsed_time_bounds_idle_scheduler_sleep() -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 0.4, "start": 0, "end": 0}],
                "think_seconds": 0,
            },
            limits={"generation_seconds": 0.4, "drain_seconds": 0.1},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        # Runtime starts before public preparation consumes most of its budget.
        await time.advance(0.3)
        starts: list[Entry] = []

        async def entry(value: Entry) -> bool:
            starts.append(value)
            return True

        existing_tasks = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.settle()
            await time.through(0.401)
            assert task.done(), (
                "scheduler sleep ignored the absolute budget consumed by preparation"
            )
            result = await task
            assert result["stop_reason"] == "generation"
            assert starts == []
            assert result["offered"] == result["admitted"] == result["completed"] == 0
            assert not (set(asyncio.all_tasks()) - existing_tasks)
            assert not time.waiters, "shutdown left an owned timer asleep"
            counts(result)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_active_target_replenishes_completed_identity_and_ramp_down_stops_admission() -> (
    None
):
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            casual=2,
            active=0,
            heavy=0,
            retry_prone=0,
            traffic={
                "mode": "active",
                "segments": [
                    {"duration_seconds": 0.5, "start": 2, "end": 2},
                    {"duration_seconds": 0.5, "start": 0, "end": 0},
                ],
                "think_seconds": 0,
            },
            limits={"active": 2, "drain_seconds": 0.2},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        busy: set[int] = set()
        starts: list[tuple[Entry, float]] = []

        async def entry(value: Entry) -> bool:
            assert value.actor not in busy
            busy.add(value.actor)
            starts.append((value, time.now))
            try:
                await time.clock.sleep(0.12)
                return True
            finally:
                busy.remove(value.actor)

        task = asyncio.create_task(
            run_schedule(resolved, 33, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(1.3)
            assert task.done()
            result = await task
            assert len(starts) > 2, "active target never replenished completed actors"
            assert {value.actor for value, _ in starts} == {0, 1}
            assert all(actual < 0.5 + 1e-9 for _, actual in starts)
            assert result["active_peak"] == 2
            assert result["completed"] == result["admitted"] == len(starts)
            assert result["stop_reason"] is None
            assert not busy
            counts(result)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_intended_seed_plan_survives_different_completion_timing_and_global_randomness() -> (
    None
):
    async def execute(delay: float) -> tuple[list[tuple[int, int, float]], object]:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 1, "start": 4, "end": 4}],
                "jitter_seconds": 0.02,
                "think_seconds": 0,
            }
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: list[tuple[int, int, float]] = []

        async def entry(value: Entry) -> bool:
            starts.append((value.actor, value.ordinal, value.at_seconds))
            await time.clock.sleep(delay if value.actor % 2 else delay / 2)
            return True

        task = asyncio.create_task(
            run_schedule(resolved, 91, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(1.3)
            assert task.done()
            result = await task
            assert result["skipped"] == 0
            return sorted(starts, key=lambda item: item[1]), result["plan_digest"]
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    state = random.getstate()
    try:
        random.seed(123)
        first = asyncio.run(execute(0))
        random.seed(789)
        second = asyncio.run(execute(0.03))
        assert first == second
    finally:
        random.setstate(state)


@pytest.mark.parametrize("stop", ["drain", "external", "cancel"])
def test_all_traffic_workers_are_cancelled_and_awaited_before_scheduler_returns(
    stop: str,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 0.3, "start": 0, "end": 0}],
                "bursts": [{"at_seconds": 0.1, "count": 4}],
            },
            limits={"drain_seconds": 0.2},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        workers: list[asyncio.Task[object]] = []
        cleaned: list[int] = []
        never = asyncio.Event()

        async def entry(value: Entry) -> bool:
            worker = asyncio.current_task()
            assert worker is not None
            workers.append(worker)
            try:
                await never.wait()
                return True
            finally:
                cleaned.append(value.ordinal)

        existing_tasks = set(asyncio.all_tasks())
        task = asyncio.create_task(
            run_schedule(resolved, 82, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(0.15)
            assert workers
            if stop == "external":
                runtime.stop("external")
            elif stop == "cancel":
                task.cancel()
            await time.through(0.6)
            assert task.done(), "traffic shutdown exceeded finite drain"
            if stop == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                result = await task
                assert result["stop_reason"] == stop
                assert result["completed"] == 0
            assert all(worker.done() for worker in workers)
            assert len(cleaned) == len(workers)
            assert not (set(asyncio.all_tasks()) - existing_tasks), (
                "scheduler returned with task-owned timers or workers still running"
            )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_entry_ceiling_stops_before_remaining_profile_and_cannot_report_success() -> (
    None
):
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={
                "segments": [{"duration_seconds": 1, "start": 10, "end": 10}],
                "max_entries": 2,
                "think_seconds": 0,
            }
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        starts: list[Entry] = []

        async def entry(value: Entry) -> bool:
            starts.append(value)
            return True

        task = asyncio.create_task(
            run_schedule(resolved, 3, entry, runtime=runtime, clock=time.clock)
        )
        try:
            await time.through(1.2)
            assert task.done()
            result = await task
            assert len(starts) <= 2
            assert result["stop_reason"] == "entries"
            counts(result)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_request_attempt_cap_counts_failed_sends_and_prevents_next_external_call() -> (
    None
):
    async def execute() -> None:
        time = ManualClock()
        runtime = TrafficRuntime(config(limits={"attempts": 2}), clock=time.clock)
        calls = 0

        async def endpoint(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("external unavailable")
            return httpx.Response(200, json={"ok": True})

        async with open_client(
            "https://staging.tailtag.app", transport=httpx.MockTransport(endpoint)
        ) as client:

            async def send() -> Reply:
                runtime.record("sent")
                return await client.get("/api/me/")

            # ApiClient keeps its existing detail-free transport exception contract.
            from tailtag_simulator.client import RequestFailed

            with pytest.raises(RequestFailed):
                await runtime.request(send)
            assert (await runtime.request(send)).status == 200
            with pytest.raises(TrafficStopped):
                await runtime.request(send)
        assert calls == 2
        assert runtime.snapshot()["attempts"] == runtime.snapshot()["sent"] == 2
        assert runtime.snapshot()["stop_reason"] == "attempts"

    asyncio.run(execute())


def test_request_inflight_cap_limits_real_http_without_losing_waiting_requests() -> (
    None
):
    async def execute() -> None:
        time = ManualClock()
        runtime = TrafficRuntime(config(limits={"in_flight": 2}), clock=time.clock)
        release = asyncio.Event()
        active = 0
        peak = 0

        async def endpoint(_request: httpx.Request) -> httpx.Response:
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            try:
                await release.wait()
                return httpx.Response(200, json={"ok": True})
            finally:
                active -= 1

        async with open_client(
            "https://staging.tailtag.app", transport=httpx.MockTransport(endpoint)
        ) as client:

            async def send() -> Reply:
                runtime.record("sent")
                return await client.get("/api/me/")

            tasks = [asyncio.create_task(runtime.request(send)) for _ in range(5)]
            try:
                await time.settle()
                assert active == peak == 2
                release.set()
                await time.settle()
                replies = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
                assert all(reply.status == 200 for reply in replies)
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        assert active == 0 and peak == 2
        assert runtime.snapshot()["in_flight_peak"] == 2
        assert runtime.snapshot()["attempts"] == runtime.snapshot()["sent"] == 5

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("generation", "advance", "budget_expired"), [(20, 10.1, False), (0.5, 0.7, True)]
)
def test_request_has_total_deadline_and_awaits_external_send_cancellation(
    generation: float,
    advance: float,
    budget_expired: bool,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        resolved = config(
            traffic={"segments": [{"duration_seconds": 0.2, "start": 0, "end": 0}]},
            limits={"generation_seconds": generation, "drain_seconds": 0.1},
        )
        runtime = TrafficRuntime(resolved, clock=time.clock)
        entered = asyncio.Event()
        cleaned = asyncio.Event()
        never = asyncio.Event()

        async def endpoint(_request: httpx.Request) -> httpx.Response:
            entered.set()
            try:
                await never.wait()
                return httpx.Response(200, json={"ok": True})
            finally:
                # One async cleanup step proves cancellation is awaited.
                await asyncio.sleep(0)
                cleaned.set()

        async with open_client(
            "https://staging.tailtag.app", transport=httpx.MockTransport(endpoint)
        ) as client:
            task = asyncio.create_task(runtime.request(lambda: client.get("/api/me/")))
            try:
                await time.settle()
                assert entered.is_set()
                await time.through(advance)
                assert task.done(), (
                    "per-I/O timeout left a blocked request alive past total deadline"
                )
                if budget_expired:
                    with pytest.raises(TrafficStopped):
                        await task
                    assert runtime.snapshot()["stop_reason"] in {"generation", "drain"}
                else:
                    with pytest.raises(httpx.TimeoutException):
                        await task
                    assert runtime.snapshot()["stop_reason"] is None
                assert cleaned.is_set(), (
                    "runtime returned before external operation cleanup"
                )
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_runtime_stop_cancels_inflight_send_and_rejects_further_requests() -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = TrafficRuntime(config(), clock=time.clock)
        cleaned = asyncio.Event()
        entered = asyncio.Event()
        never = asyncio.Event()

        async def send() -> Reply:
            entered.set()
            try:
                await never.wait()
                raise AssertionError("blocked send was released")
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        task = asyncio.create_task(runtime.request(send))
        try:
            await time.settle()
            assert entered.is_set()
            runtime.stop("external")
            await time.settle()
            assert task.done()
            with pytest.raises(TrafficStopped):
                await task
            assert cleaned.is_set()
            with pytest.raises(TrafficStopped):
                await runtime.request(send)
            assert runtime.snapshot()["attempts"] == 1
            assert runtime.snapshot()["stop_reason"] == "external"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


def test_runtime_evidence_rejects_unapproved_labels_and_preserves_recovery_count() -> (
    None
):
    runtime = TrafficRuntime(config())
    runtime.record("unresolved")
    runtime.record("unresolved", -1)
    assert runtime.snapshot()["unresolved"] == 0
    for counter, amount in [("SENTINEL-private", 1), ("unresolved", -1), ("sent", -1)]:
        with pytest.raises(ValueError) as caught:
            runtime.record(counter, amount)
        assert "SENTINEL" not in repr(caught.value)
    with pytest.raises(ValueError) as caught:
        runtime.stop("SENTINEL-private")
    assert "SENTINEL" not in repr(caught.value)
    assert runtime.snapshot()["stop_reason"] is None
