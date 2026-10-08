"""#227 U1: real safety/client behavior, only network and time substituted."""

import asyncio
import random
from collections.abc import Mapping
from typing import cast

import httpx
import pytest
from traffic_support import ManualClock

from tailtag_simulator.client import TransportFailed, open_client
from tailtag_simulator.safety import (
    ProbeInvalid,
    ProbeUnavailable,
    SafetyAborted,
    SafetyRuntime,
    resolve_safety_policy,
)
from tailtag_simulator.traffic import TrafficRuntime
from tailtag_simulator.traffic_config import resolve_traffic_config
from tailtag_simulator.traffic_effects import RetryExhausted, TrafficEffects

ORIGIN = "https://staging.tailtag.app"
IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}


def section(runtime: SafetyRuntime, key: str) -> dict[str, object]:
    return cast(dict[str, object], runtime.snapshot()[key])


async def approved_probe() -> dict[str, object]:
    return dict(IDENTITY)


def runtime_at(time: ManualClock, **policy: object) -> SafetyRuntime:
    runtime = SafetyRuntime(policy, monotonic=lambda: time.now, sleep=time.sleep)
    runtime.bind_probe(approved_probe)
    return runtime


@pytest.mark.parametrize(
    "policy",
    [
        {"SENTINEL-secret": 1},
        {"requests": True},
        {"seconds": float("nan")},
        {"final_seconds": float("inf")},
        {"requests": 0},
        {"requests": 1_000_001},
        {"seconds": 86_401},
        {"in_flight": 251},
        {"population": 251},
        {"final_requests": 5_001},
        {"final_seconds": 1_801},
        {"poll_seconds": 4},
        {"poll_seconds": 31},
        {"error_percent": 0},
        {"error_percent": 101},
        {"error_min_samples": 1.5},
        {"error_windows": 0},
        {"error_window_seconds": -1},
    ],
)
def test_invalid_closed_policy_is_rejected_before_a_runtime_can_execute(
    policy: Mapping[str, object],
) -> None:
    with pytest.raises(ValueError):
        resolve_safety_policy(policy)


def test_actual_sends_share_phase_budget_and_finalization_uses_one_reserve() -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, requests=3, final_requests=2)
        sent: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(request.url.path)
            if request.url.path == "/failed":
                raise httpx.ReadTimeout("SENTINEL-secret")
            return httpx.Response(200, json={})

        with runtime.scope():
            await runtime.check_target()
            async with open_client(ORIGIN, transport=httpx.MockTransport(respond)) as c:
                with runtime.phase("setup"):
                    await c.get("/setup")
                with runtime.phase("simulation"), pytest.raises(TransportFailed):
                    await c.get("/failed")
                with runtime.phase("reconciliation"):
                    await c.get("/reconcile")
                assert runtime.abort_reason is None  # Exact exhaustion is not failure.
                with pytest.raises(SafetyAborted):
                    await c.get("/one-too-many")
                assert runtime.abort_reason == "request_ceiling"
                assert await runtime.begin_finalization()
                with runtime.phase("finalization"):
                    await c.get("/retention")
                # Re-entering finalization cannot refresh the reserve.
                assert await runtime.begin_finalization()
                with runtime.phase("finalization"):
                    await c.get("/release")
                    with pytest.raises(SafetyAborted):
                        await c.get("/unbounded-recovery")
        assert sent == ["/setup", "/failed", "/reconcile", "/retention", "/release"]
        assert section(runtime, "execution")["requests"] == 3
        assert section(runtime, "finalization")["requests"] == 2
        assert "SENTINEL" not in str(runtime.snapshot())

    asyncio.run(execute())


def test_control_slot_can_probe_when_ordinary_http_is_full_and_abort_joins_waiters() -> (
    None
):
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, in_flight=1)
        started = asyncio.Event()
        cancelled = asyncio.Event()
        sent: list[str] = []

        async def respond(request: httpx.Request) -> httpx.Response:
            sent.append(request.url.path)
            if request.url.path == "/blocked":
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return httpx.Response(200, json={})

        with runtime.scope(), runtime.phase("simulation"):
            async with open_client(ORIGIN, transport=httpx.MockTransport(respond)) as c:

                async def work() -> None:
                    await asyncio.gather(c.get("/blocked"), c.get("/queued"))

                task = asyncio.create_task(runtime.run_phase(work()))
                try:
                    await started.wait()
                    await time.settle()
                    with runtime.control():
                        await c.get("/control")
                    assert section(runtime, "execution")["ordinary_peak"] == 1
                    assert section(runtime, "execution")["control_peak"] == 1
                    runtime.abort("resource_saturation")
                    runtime.abort("correctness")
                    with pytest.raises(SafetyAborted):
                        await task
                    assert cancelled.is_set()
                    assert sent == ["/blocked", "/control"]
                    assert runtime.abort_reason == "resource_saturation"
                    assert section(runtime, "execution")["ordinary_active"] == 0
                    assert section(runtime, "execution")["control_active"] == 0
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(execute())


@pytest.mark.parametrize("phase", ["execution", "finalization"])
def test_total_deadline_joins_stalled_http_in_each_budget(phase: str) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, seconds=1, final_seconds=1)
        started = asyncio.Event()
        closed = asyncio.Event()

        async def respond(_request: httpx.Request) -> httpx.Response:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
            return httpx.Response(200, json={})

        with runtime.scope():
            await runtime.check_target()
            if phase == "finalization":
                runtime.abort("correctness")
                assert await runtime.begin_finalization()
            with runtime.phase("finalization" if phase == "finalization" else "setup"):
                async with open_client(
                    ORIGIN, transport=httpx.MockTransport(respond)
                ) as c:
                    task = asyncio.create_task(runtime.run_phase(c.get("/stalled")))
                    try:
                        await started.wait()
                        await time.settle()
                        await time.advance(1)
                        assert task.done(), "overall deadline left HTTP alive"
                        with pytest.raises(SafetyAborted):
                            await task
                        assert closed.is_set()
                        assert section(runtime, phase)["exhausted"] == "seconds"
                    finally:
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
        assert not time.waiters

    asyncio.run(execute())


@pytest.mark.parametrize(
    "next_probe", ["recovery", "unavailable", "changed", "invalid"]
)
def test_periodic_probe_pauses_work_then_recovers_or_latches_abort(
    next_probe: str,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time)
        calls = 0
        sent: list[str] = []

        async def probe() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 2 or (calls == 3 and next_probe == "unavailable"):
                raise ProbeUnavailable
            if calls == 3 and next_probe == "invalid":
                raise ProbeInvalid
            return (
                {**IDENTITY, "source_sha": "b" * 40}
                if (calls == 3 and next_probe == "changed")
                else dict(IDENTITY)
            )

        runtime.bind_probe(probe)
        with runtime.scope(), runtime.phase("simulation"):
            await runtime.check_target()
            await runtime.start_monitor()
            try:
                await time.settle()
                await time.advance(10)
                assert section(runtime, "probes")["paused"] is True
                assert runtime.abort_reason is None
                async with open_client(
                    ORIGIN,
                    transport=httpx.MockTransport(
                        lambda r: (
                            sent.append(r.url.path),
                            httpx.Response(200, json={}),
                        )[1]
                    ),
                ) as c:
                    request = asyncio.create_task(c.get("/retry"))
                    try:
                        await time.settle()
                        assert sent == []
                        await time.advance(10)
                        if next_probe == "recovery":
                            assert await request
                            assert sent == ["/retry"]
                            assert runtime.abort_reason is None
                            assert section(runtime, "probes")["paused"] is False
                        else:
                            with pytest.raises(SafetyAborted):
                                await request
                            assert sent == []
                            assert runtime.abort_reason == (
                                "readiness"
                                if next_probe == "unavailable"
                                else "identity_mismatch"
                            )
                    finally:
                        if not request.done():
                            request.cancel()
                        await asyncio.gather(request, return_exceptions=True)
            finally:
                await runtime.stop_monitor()
        assert not time.waiters

    asyncio.run(execute())


@pytest.mark.parametrize("failure", ["unavailable", "invalid", "unexpected"])
def test_phase_gate_fails_closed_on_first_probe_failure(failure: str) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time)

        async def probe() -> dict[str, object]:
            if failure == "unexpected":
                raise OSError("SENTINEL-private-probe")
            raise ProbeUnavailable if failure == "unavailable" else ProbeInvalid

        runtime.bind_probe(probe)
        with pytest.raises(SafetyAborted):
            await runtime.check_target()
        assert runtime.abort_reason == (
            "identity_mismatch" if failure == "invalid" else "readiness"
        )

    asyncio.run(execute())


@pytest.mark.parametrize("middle", ["qualifying", "low-rate", "low-samples", "empty"])
def test_catastrophic_windows_require_two_consecutive_completed_actual_windows(
    middle: str,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time)
        statuses = iter([503] * 10 + [409] * 10)

        def respond(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(next(statuses), json={})

        with runtime.scope(), runtime.phase("simulation"):
            await runtime.check_target()
            await runtime.start_monitor()
            try:
                async with open_client(
                    ORIGIN, transport=httpx.MockTransport(respond)
                ) as c:
                    for _ in range(20):
                        await c.get("/work")
                    await time.settle()
                    await time.advance(10)
                    assert runtime.abort_reason is None
                    count = (
                        0
                        if middle == "empty"
                        else 19
                        if middle == "low-samples"
                        else 20
                    )
                    statuses = iter(
                        [503] * (9 if middle == "low-rate" else 10) + [409] * 20
                    )
                    for _ in range(count):
                        await c.get("/work")
                    await time.advance(10)
                    assert runtime.abort_reason == (
                        "catastrophic_errors" if middle == "qualifying" else None
                    )
                    if middle != "qualifying":
                        statuses = iter([503] * 10 + [200] * 10)
                        for _ in range(20):
                            await c.get("/work")
                        await time.advance(10)
                        assert runtime.abort_reason is None, (
                            "nonqualifying window failed to break streak"
                        )
            finally:
                await runtime.stop_monitor()

    asyncio.run(execute())


@pytest.mark.parametrize("injected", ["pre_send_failure_rate", "lost_response_rate"])
def test_safety_observes_genuine_outcome_below_injection(injected: str) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, error_min_samples=1)
        config = resolve_traffic_config(
            {
                "pool": "alpha",
                "retry": {"attempts": 1},
                "failure": {"operations": ["confirm"], injected: 1},
            }
        )
        traffic = TrafficRuntime(config, clock=time.clock)
        effects = TrafficEffects(config, traffic, time.clock)
        sent: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(request.url.path)
            return httpx.Response(503, json={"SENTINEL-secret": "concealed"})

        with runtime.scope(), runtime.phase("simulation"):
            await runtime.check_target()
            await runtime.start_monitor()
            try:
                async with open_client(
                    ORIGIN, transport=httpx.MockTransport(respond)
                ) as c:
                    for _ in range(2):
                        with pytest.raises(RetryExhausted):
                            await effects.call(
                                "confirm", lambda: c.get("/confirm"), random.Random(0)
                            )
                        await time.settle()
                        await time.advance(10)
                assert runtime.abort_reason == (
                    "catastrophic_errors" if injected == "lost_response_rate" else None
                )
                assert len(sent) == (2 if injected == "lost_response_rate" else 0)
                assert section(runtime, "execution")["requests"] == len(sent)
                assert "SENTINEL" not in str(runtime.snapshot())
            finally:
                await runtime.stop_monitor()

    asyncio.run(execute())


def test_population_bound_is_checked_before_new_identity_work() -> None:
    runtime = SafetyRuntime({"population": 2})
    runtime.validate_population(2)
    assert runtime.abort_reason is None
    with pytest.raises(SafetyAborted):
        runtime.validate_population(3)
    assert runtime.abort_reason == "population_ceiling"


@pytest.mark.parametrize("kind", ["changed", "invalid"])
def test_identity_failure_on_first_periodic_probe_aborts_without_availability_grace(
    kind: str,
) -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time)
        calls = 0

        async def probe() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls > 1:
                if kind == "invalid":
                    raise ProbeInvalid
                return {**IDENTITY, "source_sha": "b" * 40}
            return dict(IDENTITY)

        runtime.bind_probe(probe)
        with runtime.scope():
            await runtime.check_target()
            await runtime.start_monitor()
            try:
                await time.settle()
                await time.advance(10)
                assert runtime.abort_reason == "identity_mismatch"
            finally:
                await runtime.stop_monitor()

    asyncio.run(execute())


def test_identity_denial_keeps_clerk_closure_bounded_without_reopening_tailtag() -> (
    None
):
    """AC21 amendment: independent session closure consumes the same final reserve."""

    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, final_seconds=1)
        closes: list[str] = []
        settled: list[str] = []
        tailtag: list[str] = []

        async def clerk(request: httpx.Request) -> httpx.Response:
            closes.append(request.url.path)
            try:
                await time.sleep(0.6)
                return httpx.Response(200, json={})
            finally:
                settled.append(request.url.path)

        with runtime.scope():
            await runtime.check_target()
            runtime.abort("identity_mismatch")
            assert not await runtime.begin_finalization()
            async with open_client(
                ORIGIN,
                transport=httpx.MockTransport(
                    lambda r: (
                        tailtag.append(r.url.path),
                        httpx.Response(200, json={}),
                    )[1]
                ),
            ) as public:
                with pytest.raises(SafetyAborted):
                    await runtime.run_closure(public.get("/cannot-reopen-tailtag"))
            async with httpx.AsyncClient(
                base_url="https://clerk.example.test",
                transport=httpx.MockTransport(clerk),
            ) as provider:
                first = asyncio.create_task(
                    runtime.run_closure(provider.post("/session-one/close"))
                )
                try:
                    await time.settle()
                    await time.advance(0.6)
                    assert first.done()
                    assert (await first).status_code == 200
                    second = asyncio.create_task(
                        runtime.run_closure(provider.post("/session-two/close"))
                    )
                    try:
                        await time.settle()
                        await time.advance(0.4)
                        assert second.done(), (
                            "second closure reset the global final reserve"
                        )
                        with pytest.raises(SafetyAborted):
                            await second
                    finally:
                        if not second.done():
                            second.cancel()
                        await asyncio.gather(second, return_exceptions=True)
                finally:
                    if not first.done():
                        first.cancel()
                    await asyncio.gather(first, return_exceptions=True)
        assert tailtag == []
        assert closes == settled == ["/session-one/close", "/session-two/close"]
        assert runtime.abort_reason == "identity_mismatch"
        assert section(runtime, "finalization")["exhausted"] == "seconds"
        assert not time.waiters

    asyncio.run(execute())


@pytest.mark.parametrize("completion", ["abort", "late", "started_task"])
def test_phase_success_does_not_win_a_simultaneous_abort_or_elapsed_deadline(
    completion: str,
) -> None:
    """U1 review regression: successful provider work cannot mask a terminal event."""

    async def execute() -> None:
        time = ManualClock()
        runtime = runtime_at(time, seconds=1)

        entered = asyncio.Event()
        closed = asyncio.Event()

        async def provider(_request: httpx.Request) -> httpx.Response:
            if completion == "started_task":
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()
            elif completion == "abort":
                runtime.abort("identity_mismatch")
            else:
                time.now = 2
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(provider)
        ) as external:
            work = external.get("https://provider.example.test/work")
            if completion == "started_task":
                task = asyncio.create_task(work)
                await entered.wait()
                runtime.abort("identity_mismatch")
                try:
                    with pytest.raises(SafetyAborted):
                        await runtime.run_phase(task)
                    assert task.cancelled() and closed.is_set()
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            else:
                with pytest.raises(SafetyAborted):
                    await runtime.run_phase(work)
        assert runtime.abort_reason == (
            "duration_ceiling" if completion == "late" else "identity_mismatch"
        )
        assert not time.waiters

    asyncio.run(execute())


def test_finalization_probe_cannot_grant_permission_after_identity_abort() -> None:
    """U1 review regression: a probe result cannot clear a terminal target veto."""

    async def execute() -> None:
        runtime = SafetyRuntime({})
        calls = 0

        async def probe() -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls > 1:
                runtime.abort("identity_mismatch")
            return dict(IDENTITY)

        runtime.bind_probe(probe)
        await runtime.check_target()
        runtime.abort("correctness")
        assert not await runtime.begin_finalization()
        assert runtime.abort_reason == "correctness"
        with pytest.raises(SafetyAborted):
            await runtime.privileged_identity()
        assert calls == 2

    asyncio.run(execute())


def test_operator_abort_between_admission_and_send_does_not_count_an_http_attempt() -> (
    None
):
    """U1 review regression: permits are not real sends when a queued stop wins."""

    async def execute() -> None:
        scheduled = False
        sent: list[str] = []

        def observe(snapshot: Mapping[str, object]) -> None:
            nonlocal scheduled
            execution = cast(dict[str, object], snapshot["execution"])
            if execution["ordinary_active"] == 1 and not scheduled:
                scheduled = True
                asyncio.get_running_loop().call_soon(
                    runtime.abort, "resource_saturation"
                )

        runtime = SafetyRuntime({}, observe=observe)
        async with open_client(
            ORIGIN,
            transport=httpx.MockTransport(
                lambda r: (sent.append(r.url.path), httpx.Response(200, json={}))[1]
            ),
        ) as client:
            with runtime.scope(), pytest.raises(SafetyAborted):
                await client.get("/stop-before-real-send")
        assert scheduled and sent == []
        assert section(runtime, "execution")["requests"] == 0
        assert section(runtime, "execution")["ordinary_active"] == 0
        assert runtime.abort_reason == "resource_saturation"

    asyncio.run(execute())
