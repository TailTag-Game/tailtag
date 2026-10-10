"""#229 U1: client-side measurement at the traffic request boundary (AC8-10).

The real runtime runs under the injected traffic clock; sends are the only substitute.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from performance_support import CLASSES, OPERATIONS
from traffic_support import ManualClock

from tailtag_simulator.client import Reply, RequestFailed, TransportFailed, open_client
from tailtag_simulator.limits import REQUEST_TIMEOUT_SECONDS
from tailtag_simulator.traffic import TrafficRuntime, TrafficStopped
from tailtag_simulator.traffic_config import resolve_traffic_config
from tailtag_simulator.traffic_effects import InjectedFailure, TrafficEffects
from tailtag_simulator.traffic_metrics import nearest_rank

Send = Callable[[], Awaitable[Reply]]
NOT_OBSERVED = {"value": None, "reason": "not_observed"}


def runtime_for(time: ManualClock, **overrides: object) -> TrafficRuntime:
    return TrafficRuntime(
        resolve_traffic_config({"pool": "alpha", **overrides}), clock=time.clock
    )


def replying(status: int) -> Send:
    async def send() -> Reply:
        return Reply(status, None)

    return send


def failing(error: Exception) -> Send:
    async def send() -> Reply:
        raise error

    return send


def only(operation: str, **counts: int) -> dict[str, dict[str, int]]:
    """Every operation and the total, all zero except one operation's classes."""
    zero: dict[str, int] = dict.fromkeys(CLASSES, 0)
    row = {**zero, **counts}
    return {
        **{name: dict(zero) for name in OPERATIONS},
        operation: row,
        "total": dict(row),
    }


@pytest.mark.parametrize(
    ("samples", "expected"),
    [
        ([7.0], {0.5: 7.0, 0.95: 7.0, 0.99: 7.0, 1.0: 7.0}),
        ([float(n) for n in range(1, 11)], {0.5: 5.0, 0.95: 10.0, 0.99: 10.0}),
        ([float(n) for n in range(1, 21)], {0.5: 10.0, 0.95: 19.0, 0.99: 20.0}),
        (
            [float(n) for n in range(1, 101)],
            {0.5: 50.0, 0.95: 95.0, 0.99: 99.0, 1.0: 100.0},
        ),
    ],
)
def test_nearest_rank_selects_rank_ceil_q_times_n_from_sorted_samples(
    samples: list[float], expected: dict[float, float]
) -> None:
    for q, value in expected.items():
        assert nearest_rank(samples, q) == value


# Each row: reply or failure, injection, resulting class (None: not a measured outcome).
CLASSIFICATIONS = [
    pytest.param(replying(199), "none", "client_error", True, id="199-other"),
    pytest.param(replying(200), "none", "success", True, id="200"),
    pytest.param(replying(299), "none", "success", True, id="299"),
    pytest.param(replying(300), "none", "client_error", True, id="300"),
    pytest.param(replying(404), "none", "client_error", True, id="404"),
    pytest.param(replying(500), "none", "server_error", True, id="500"),
    pytest.param(replying(599), "none", "server_error", True, id="599"),
    pytest.param(replying(600), "none", "client_error", True, id="600-other"),
    pytest.param(replying(201), "lost_response", "injected", False, id="lost-2xx"),
    pytest.param(replying(503), "lost_response", "injected", False, id="lost-5xx"),
    pytest.param(
        failing(InjectedFailure()), "pre_send", "injected", False, id="pre-send"
    ),
    pytest.param(
        failing(TransportFailed(timed_out=True)),
        "none",
        "timeout",
        False,
        id="transport-timeout",
    ),
    pytest.param(
        failing(TransportFailed()), "none", "transport_error", False, id="transport"
    ),
    pytest.param(
        failing(RequestFailed()), "none", "transport_error", False, id="request"
    ),
]


@pytest.mark.parametrize(("send", "injection", "outcome", "sampled"), CLASSIFICATIONS)
def test_each_attempt_is_classified_once_and_only_replies_carry_send_latency(
    send: Send, injection: str, outcome: str, sampled: bool
) -> None:
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time)

        async def timed() -> Reply:
            time.now += 0.007
            return await send()

        try:
            await runtime.request(timed, operation="confirm", injection=injection)
        except (RequestFailed, InjectedFailure):
            pass
        assert runtime.snapshot()["attempts"] == 1
        return runtime.performance()

    performance = asyncio.run(execute())
    assert performance["attempts"] == only("confirm", **{outcome: 1})
    for name in ("confirm", "total"):
        latency = performance["latency_percentiles"][name]
        assert latency["samples"] == int(sampled)
        assert latency["p50"] == (
            {"value": 7.0, "reason": None} if sampled else NOT_OBSERVED
        )


def test_modeled_timeout_is_a_timeout_without_a_latency_sample() -> None:
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time)
        never = asyncio.Event()

        async def send() -> Reply:
            await never.wait()
            raise AssertionError("blocked send was released")

        task = asyncio.create_task(runtime.request(send, operation="read"))
        try:
            await time.settle()
            await time.through(REQUEST_TIMEOUT_SECONDS + 0.1)
            with pytest.raises(httpx.TimeoutException):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return runtime.performance()

    performance = asyncio.run(execute())
    assert performance["attempts"] == only("read", timeout=1)
    assert performance["latency_percentiles"]["total"]["samples"] == 0


def test_attempts_cut_off_by_a_stop_or_an_unrelated_error_are_not_recorded() -> None:
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time)
        entered = asyncio.Event()
        never = asyncio.Event()

        async def blocked() -> Reply:
            entered.set()
            await never.wait()
            raise AssertionError("blocked send was released")

        task = asyncio.create_task(runtime.request(blocked, operation="confirm"))
        try:
            await entered.wait()
            runtime.stop("external")
            with pytest.raises(TrafficStopped):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return runtime.performance()

    assert asyncio.run(execute())["attempts"] == only("confirm")

    async def unrelated() -> Any:
        runtime = runtime_for(ManualClock())
        with pytest.raises(ValueError):
            await runtime.request(failing(ValueError()), operation="resolve")
        return runtime.performance()

    assert asyncio.run(unrelated())["attempts"] == only("resolve")


def test_latency_is_the_send_duration_and_excludes_traffic_queue_wait() -> None:
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time, limits={"in_flight": 1})

        async def send_for(seconds: float) -> Reply:
            await time.sleep(seconds)
            return Reply(200, None)

        first = asyncio.create_task(
            runtime.request(lambda: send_for(0.002), operation="read")
        )
        await time.settle()
        second = asyncio.create_task(
            runtime.request(lambda: send_for(0.003), operation="read")
        )
        await time.settle()
        await time.advance(0.002)  # The second request queued for this long.
        await time.advance(0.003)
        await asyncio.gather(first, second)
        return runtime.performance()["latency_percentiles"]["read"]

    latency = asyncio.run(execute())
    assert latency["samples"] == 2
    assert latency["p50"]["value"] == 2.0
    assert latency["max"]["value"] == 3.0  # 5.0 if queue wait were included


def test_summary_is_exact_per_operation_and_total_with_rounded_values() -> None:
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time)
        runtime.generation_seconds, runtime.drain_seconds = 4.0, 1.0

        async def attempt(operation: str, status: int, milliseconds: float) -> None:
            async def send() -> Reply:
                time.now += milliseconds / 1000
                return Reply(status, None)

            await runtime.request(send, operation=operation)

        for milliseconds in range(1, 11):
            await attempt("resolve", 200, milliseconds)
        await attempt("confirm", 201, 1.23456)
        await attempt("auxiliary", 404, 100)
        return runtime.performance()

    performance = asyncio.run(execute())
    assert performance["attempts"]["resolve"]["success"] == 10
    assert performance["attempts"]["confirm"]["success"] == 1
    assert performance["attempts"]["auxiliary"]["client_error"] == 1
    assert performance["attempts"]["total"]["success"] == 11
    assert performance["throughput"] == pytest.approx(
        {"auxiliary": 0.2, "resolve": 2.0, "confirm": 0.2, "read": 0.0, "total": 2.4}
    )

    def row(samples: int, value: float | None) -> dict[str, Any]:
        measured = NOT_OBSERVED if value is None else {"value": value, "reason": None}
        return {
            "samples": samples,
            **dict.fromkeys(("p50", "p95", "p99", "max"), measured),
        }

    latency = performance["latency_percentiles"]
    assert latency["read"] == row(0, None)
    assert latency["confirm"] == row(1, 1.235)
    assert latency["auxiliary"] == row(1, 100.0)
    assert {k: v for k, v in latency["resolve"].items() if k != "p50"} == {
        "samples": 10,
        "p95": {"value": 10.0, "reason": None},
        "p99": {"value": 10.0, "reason": None},
        "max": {"value": 10.0, "reason": None},
    }
    assert latency["resolve"]["p50"] == {"value": 5.0, "reason": None}
    # Twelve samples pooled: the total is not an average of per-operation values.
    assert latency["total"] == {
        "samples": 12,
        "p50": {"value": 5.0, "reason": None},
        "p95": {"value": 100.0, "reason": None},
        "p99": {"value": 100.0, "reason": None},
        "max": {"value": 100.0, "reason": None},
    }


def test_expected_rejection_moves_one_client_error_and_needs_one_to_move() -> None:
    async def execute() -> None:
        runtime = runtime_for(ManualClock())
        await runtime.request(replying(404), operation="confirm")
        runtime.expected_rejection("confirm")
        performance = runtime.performance()
        assert performance["attempts"] == only("confirm", expected_rejection=1)
        assert runtime.snapshot()["expected_rejections"] == 1
        # The rejected reply was still a response, so it keeps its latency sample.
        assert performance["latency_percentiles"]["confirm"]["samples"] == 1
        for operation in ("confirm", "resolve"):
            with pytest.raises(ValueError):
                runtime.expected_rejection(operation)
        assert runtime.snapshot()["expected_rejections"] == 1
        assert runtime.performance()["attempts"] == performance["attempts"]

    asyncio.run(execute())


def test_request_refuses_an_unknown_operation_label_before_sending() -> None:
    async def execute() -> None:
        runtime = runtime_for(ManualClock())
        with pytest.raises(ValueError):
            await runtime.request(replying(200), operation="SENTINEL-route")
        assert runtime.performance()["attempts"] == only("read")

    asyncio.run(execute())


def test_stop_during_the_response_delay_keeps_injected_evidence_consistent() -> None:
    """A lost reply is metered once received; the counter must agree if cut off."""

    async def execute() -> TrafficRuntime:
        time = ManualClock()
        config = resolve_traffic_config(
            {
                "pool": "alpha",
                "failure": {
                    "operations": ["confirm"],
                    "lost_response_rate": 1,
                    "response_delay_seconds": 1.0,
                },
            }
        )
        runtime = TrafficRuntime(config, clock=time.clock)
        effects = TrafficEffects(config, runtime, time.clock)

        async def send() -> Reply:
            return Reply(201, None)

        task = asyncio.create_task(effects.call("confirm", send, random.Random(1)))
        await time.settle()  # The reply has arrived; the response delay is pending.
        task.cancel()  # What run_schedule does to in-flight workers on stop/drain.
        await asyncio.gather(task, return_exceptions=True)
        return runtime

    runtime = asyncio.run(execute())
    assert (
        runtime.performance()["attempts"]["total"]["injected"]
        == runtime.snapshot()["injected"]
    )


def test_latency_starts_when_the_http_request_is_issued_not_at_token_resolution() -> (
    None
):
    async def execute() -> Any:
        time = ManualClock()
        runtime = runtime_for(time)

        async def token() -> str:
            time.now += 0.5  # Provider time precedes the request being issued.
            return "a.b.c"

        async def endpoint(_request: httpx.Request) -> httpx.Response:
            time.now += 0.02
            return httpx.Response(200, json={"ok": True})

        async with open_client(
            "https://staging.tailtag.app",
            token_provider=token,
            transport=httpx.MockTransport(endpoint),
        ) as client:
            await runtime.request(lambda: client.get("/api/me/"), operation="read")
        return runtime.performance()["latency_percentiles"]["read"]

    latency = asyncio.run(execute())
    assert latency["samples"] == 1
    assert latency["max"] == {"value": 20.0, "reason": None}  # 520.0 if included
