"""Deterministic offered journeys and finite, awaited traffic execution."""

import asyncio
import hashlib
import json
import math
import random
import time
from bisect import bisect_right
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar, cast

import httpx

from tailtag_simulator.behavior_config import PERSONAS
from tailtag_simulator.client import Reply
from tailtag_simulator.limits import REQUEST_TIMEOUT_SECONDS
from tailtag_simulator.traffic_config import (
    resolve_traffic_config,
    traffic_bucket_count,
)


@dataclass(frozen=True)
class Clock:
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    wall_time: Callable[[], float] = time.time


@dataclass(frozen=True)
class Entry:
    actor: int
    ordinal: int
    at_seconds: float


class TrafficStopped(Exception):
    """A finite workload budget or explicit safety stop ended admission."""


DEFAULT_CLOCK = Clock()
T = TypeVar("T")
_COUNTERS = (
    "injected",
    "transient",
    "retries",
    "expected_rejections",
    "exhausted",
    "unresolved",
    "sent",
)
_STOPS = ("attempts", "generation", "drain", "external", "correctness", "entries")


class TrafficRuntime:
    def __init__(
        self, config: Mapping[str, object], *, clock: Clock = DEFAULT_CLOCK
    ) -> None:
        self.config = resolve_traffic_config(config)
        self.clock = clock
        self.limits = cast(dict[str, object], self.config["limits"])
        self.traffic = cast(dict[str, object], self.config["traffic"])
        self.started = clock.monotonic()
        self.semaphore = asyncio.Semaphore(cast(int, self.limits["in_flight"]))
        self.stopped = asyncio.Event()
        self.stop_reason: str | None = None
        self.in_flight = 0
        self.sending: set[asyncio.Task[object]] = set()
        self.values: dict[str, int] = dict.fromkeys(
            (
                "offered",
                "admitted",
                "skipped",
                "completed",
                "active_peak",
                "in_flight_peak",
                "attempts",
                *_COUNTERS,
            ),
            0,
        )
        self.bind_seed(0)
        self.generation_seconds = 0.0
        self.drain_seconds = 0.0
        self.lag_seconds = 0.0
        self.buckets: list[dict[str, object]] = []

    def bind_seed(self, seed: int) -> None:
        self.plan_digest = hashlib.sha256(
            json.dumps(
                {"config": self.config, "seed": seed},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def record(self, counter: str, amount: int = 1) -> None:
        if (
            counter not in _COUNTERS
            or type(amount) is not int
            or (amount < 0 and counter != "unresolved")
            or not 0 <= self.values[counter] + amount <= 1000000
        ):
            raise ValueError("invalid traffic evidence")
        self.values[counter] += amount
        if counter == "sent" and amount > 0:
            try:
                task = asyncio.current_task()
            except RuntimeError:
                task = None
            if task is not None:
                self.sending.add(task)
                self.values["in_flight_peak"] = max(
                    self.values["in_flight_peak"], len(self.sending)
                )

    def stop(self, reason: str) -> None:
        if reason not in _STOPS:
            raise ValueError("invalid traffic stop")
        if self.stop_reason is None:
            self.stop_reason = reason
            self.stopped.set()

    async def _bounded(self, work: Awaitable[T], seconds: float) -> T:
        """Race injected time and stop, then join every owned child on all exits."""
        operation = asyncio.ensure_future(work)
        timer = asyncio.ensure_future(self.clock.sleep(max(0, seconds)))
        stop = asyncio.create_task(self.stopped.wait())
        try:
            done, _ = await asyncio.wait(
                (operation, timer, stop), return_when=asyncio.FIRST_COMPLETED
            )
            if self.stopped.is_set():
                raise TrafficStopped
            if operation in done:
                return await operation
            raise TimeoutError
        finally:
            for task in (operation, timer, stop):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation, timer, stop, return_exceptions=True)

    async def request(self, send: Callable[[], Awaitable[Reply]]) -> Reply:
        if self.stopped.is_set():
            raise TrafficStopped
        if self.values["attempts"] >= cast(int, self.limits["attempts"]):
            self.stop("attempts")
            raise TrafficStopped
        self.values["attempts"] += 1
        budget_end = (
            self.started
            + cast(float, self.limits["generation_seconds"])
            + cast(float, self.limits["drain_seconds"])
        )
        remaining = budget_end - self.clock.monotonic()
        if remaining <= 0:
            self.stop("drain")
            raise TrafficStopped

        async def invoke() -> Reply:
            try:
                return await send()
            finally:
                task = asyncio.current_task()
                if task is not None:
                    self.sending.discard(task)

        async def guarded() -> Reply:
            async with self.semaphore:
                if self.stopped.is_set():
                    raise TrafficStopped
                self.in_flight += 1
                try:
                    remaining_call = budget_end - self.clock.monotonic()
                    try:
                        return await self._bounded(
                            invoke(), min(REQUEST_TIMEOUT_SECONDS, remaining_call)
                        )
                    except TimeoutError:
                        if self.clock.monotonic() >= budget_end - 1e-9:
                            self.stop("drain")
                            raise TrafficStopped from None
                        raise httpx.TimeoutException(
                            "modeled request timed out"
                        ) from None
                finally:
                    self.in_flight -= 1

        try:
            return await self._bounded(guarded(), remaining)
        except TimeoutError:
            self.stop("drain")
            raise TrafficStopped from None

    def _count(self, counter: str, bucket: int) -> None:
        self.values[counter] += 1
        self.buckets[bucket][counter] = cast(int, self.buckets[bucket][counter]) + 1

    def snapshot(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            **self.values,
            "generation_seconds": self.generation_seconds,
            "drain_seconds": self.drain_seconds,
            "lag_seconds": self.lag_seconds,
            "stop_reason": self.stop_reason,
            "buckets": [dict(bucket) for bucket in self.buckets],
        }


def _arrival_offsets(
    segments: list[dict[str, object]], cap: int
) -> tuple[list[float], bool]:
    offsets: list[float] = []
    elapsed, integrated = 0.0, 0.0
    next_offer = 1
    for segment in segments:
        duration = cast(float, segment["duration_seconds"])
        start, end = cast(float, segment["start"]), cast(float, segment["end"])
        area = duration * (start + end) / 2
        while next_offer <= integrated + area + 1e-9:
            if len(offsets) > cap:
                return offsets, True
            # Invert the continuous integral; bisection handles flat/zero ramps.
            low, high = 0.0, duration
            required = next_offer - integrated
            for _ in range(50):
                mid = (low + high) / 2
                if start * mid + (end - start) * mid * mid / (2 * duration) < required:
                    low = mid
                else:
                    high = mid
            offsets.append(elapsed + (low + high) / 2)
            next_offer += 1
        integrated += area
        elapsed += duration
    return offsets, len(offsets) > cap


# The scheduler shares module-private runtime accounting and task ownership.
async def run_schedule(
    config: Mapping[str, object],
    seed: int,
    run_entry: Callable[[Entry], Awaitable[bool]],
    *,
    runtime: TrafficRuntime,
    clock: Clock = DEFAULT_CLOCK,
) -> dict[str, object]:
    resolved = resolve_traffic_config(config)
    traffic = cast(dict[str, object], resolved["traffic"])
    limits = cast(dict[str, object], resolved["limits"])
    segments = cast(list[dict[str, object]], traffic["segments"])
    duration = sum(cast(float, segment["duration_seconds"]) for segment in segments)
    width = cast(float, traffic["bucket_seconds"])
    runtime.buckets = [
        {
            "at_seconds": index * width,
            "offered": 0,
            "admitted": 0,
            "skipped": 0,
            "completed": 0,
        }
        for index in range(traffic_bucket_count(duration, width))
    ]
    runtime.bind_seed(seed)
    actors = list(range(sum(cast(int, resolved[k]) for k in PERSONAS[:4])))
    rng = random.Random(seed)
    rng.shuffle(actors)
    cap = cast(int, traffic["max_entries"])
    offsets, truncated = (
        _arrival_offsets(segments, cap)
        if traffic["mode"] == "arrivals"
        else ([], False)
    )
    offsets = [
        min(
            duration,
            max(
                0,
                offset
                + rng.uniform(
                    -cast(float, traffic["jitter_seconds"]),
                    cast(float, traffic["jitter_seconds"]),
                ),
            ),
        )
        for offset in offsets
    ]
    for burst in cast(list[dict[str, object]], traffic["bursts"]):
        offsets.extend([cast(float, burst["at_seconds"])] * cast(int, burst["count"]))
    offsets.sort()
    truncated = truncated or len(offsets) > cap
    offsets = offsets[:cap]
    busy: set[int] = set()
    workers: set[asyncio.Task[None]] = set()
    started = clock.monotonic()
    ordinal = 0
    drain_start: float | None = None

    async def worker(entry: Entry, bucket: int) -> None:
        try:
            if await run_entry(entry):
                runtime._count("completed", bucket)  # pyright: ignore[reportPrivateUsage]
            await clock.sleep(cast(float, traffic["think_seconds"]))
        except TrafficStopped:
            pass
        except Exception:  # noqa: BLE001 - boundary stops arbitrary entry failures safely
            runtime.stop("correctness")
        finally:
            busy.remove(entry.actor)

    def check_generation() -> None:
        if (
            clock.monotonic() - runtime.started
            > cast(float, limits["generation_seconds"]) + 1e-9
        ):
            runtime.stop("generation")
            raise TrafficStopped

    def offer(at: float, *, skipped: bool = False) -> None:
        nonlocal ordinal
        check_generation()
        bucket = int(
            min(len(runtime.buckets) - 1, max(0, clock.monotonic() - started) / width)
        )
        runtime._count("offered", bucket)  # pyright: ignore[reportPrivateUsage]
        actor = actors[ordinal % len(actors)]
        entry = Entry(actor, ordinal, at)
        ordinal += 1
        runtime.lag_seconds = max(
            runtime.lag_seconds, max(0, clock.monotonic() - started - at)
        )
        if skipped or actor in busy or len(busy) >= cast(int, limits["active"]):
            runtime._count("skipped", bucket)  # pyright: ignore[reportPrivateUsage]
            return
        runtime._count("admitted", bucket)  # pyright: ignore[reportPrivateUsage]
        busy.add(actor)
        runtime.values["active_peak"] = max(runtime.values["active_peak"], len(busy))
        task = asyncio.create_task(worker(entry, bucket))
        workers.add(task)
        task.add_done_callback(workers.discard)

    async def until(at: float) -> None:
        deadline = runtime.started + cast(float, limits["generation_seconds"])
        delay = min(started + at, deadline) - clock.monotonic()
        if delay > 1e-9:
            await runtime._bounded(clock.sleep(delay), delay + 1)  # pyright: ignore[reportPrivateUsage]
        if runtime.stopped.is_set():
            raise TrafficStopped
        runtime.lag_seconds = max(
            runtime.lag_seconds, max(0, clock.monotonic() - started - at)
        )
        if started + at > deadline + 1e-9:
            runtime.stop("generation")
            raise TrafficStopped
        check_generation()

    try:
        if traffic["mode"] == "arrivals":
            index = 0
            while index < len(offsets):
                await until(offsets[index])
                elapsed = clock.monotonic() - started
                due_end = bisect_right(offsets, elapsed + 1e-9)
                latest = offsets[due_end - 1]
                for at in offsets[index:due_end]:
                    offer(at, skipped=at < latest - 1e-9 or elapsed > duration + 1e-9)
                index = due_end
            if truncated:
                runtime.stop("entries")
            else:
                await until(duration)
        else:
            burst_index = 0
            tick = 0
            while tick * 0.1 < duration - 1e-9 or burst_index < len(offsets):
                tick_at = tick * 0.1 if tick * 0.1 < duration - 1e-9 else math.inf
                at = min(
                    tick_at,
                    offsets[burst_index] if burst_index < len(offsets) else math.inf,
                )
                await until(at)
                elapsed = clock.monotonic() - started
                next_tick = (tick + 1) * 0.1 if at >= tick_at - 1e-9 else tick_at
                if next_tick >= duration - 1e-9:
                    next_tick = math.inf
                next_burst_index = bisect_right(offsets, at + 1e-9)
                next_burst = (
                    offsets[next_burst_index]
                    if next_burst_index < len(offsets)
                    else math.inf
                )
                skipped = (
                    elapsed > duration + 1e-9
                    or min(next_tick, next_burst) <= elapsed + 1e-9
                )
                while burst_index < len(offsets) and offsets[burst_index] <= at + 1e-9:
                    if ordinal >= cap:
                        runtime.stop("entries")
                        raise TrafficStopped
                    offer(offsets[burst_index], skipped=skipped)
                    burst_index += 1
                if at < tick_at - 1e-9:
                    continue
                segment_start = 0.0
                target = 0
                for segment in segments:
                    seconds = cast(float, segment["duration_seconds"])
                    if at < segment_start + seconds - 1e-9:
                        ratio = (at - segment_start) / seconds
                        target = math.floor(
                            cast(float, segment["start"])
                            + (
                                cast(float, segment["end"])
                                - cast(float, segment["start"])
                            )
                            * ratio
                            + 1e-9
                        )
                        break
                    segment_start += seconds
                for _ in range(max(0, target - len(busy))):
                    if ordinal >= cap:
                        runtime.stop("entries")
                        raise TrafficStopped
                    offer(at, skipped=skipped)
                tick += 1
            if truncated:
                runtime.stop("entries")
            else:
                await until(duration)
        runtime.generation_seconds = max(0, clock.monotonic() - started)
        drain_start = clock.monotonic()
        if workers and not runtime.stopped.is_set():
            try:
                await runtime._bounded(  # pyright: ignore[reportPrivateUsage]
                    asyncio.gather(*workers), cast(float, limits["drain_seconds"])
                )
            except TimeoutError:
                runtime.stop("drain")
        runtime.drain_seconds = max(0, clock.monotonic() - drain_start)
    except TrafficStopped:
        pass
    except asyncio.CancelledError:
        runtime.stop("external")
        raise
    finally:
        remaining = tuple(workers)
        for task in remaining:
            if not task.done():
                task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        if drain_start is None:
            runtime.generation_seconds = max(0, clock.monotonic() - started)
        else:
            runtime.drain_seconds = max(0, clock.monotonic() - drain_start)
    return runtime.snapshot()
