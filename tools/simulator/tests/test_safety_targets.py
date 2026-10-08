"""#227 AC10: credential-free Staging identity/readiness/stability transcript."""

import asyncio
from typing import cast

import httpx
import pytest
from traffic_support import ManualClock

from tailtag_simulator.client import open_client
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime
from tailtag_simulator.targets import TargetRejected, resolve_target, verify_target

ORIGIN = "https://staging.tailtag.app"
IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}


@pytest.mark.parametrize("failure", [None, "unready", "malformed-ready", "changed"])
def test_staging_phase_gate_requires_stable_identity_around_readiness(
    failure: str | None,
) -> None:
    seen: list[str] = []
    identities = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal identities
        assert "authorization" not in request.headers
        seen.append(request.url.path)
        if request.url.path == "/health/identity":
            identities += 1
            body = dict(IDENTITY)
            if failure == "changed" and identities == 2:
                body["source_sha"] = "b" * 40
            return httpx.Response(200, json=body)
        assert request.url.path == "/health/ready"
        return httpx.Response(
            503 if failure == "unready" else 200,
            json={"status": "wrong" if failure == "malformed-ready" else "ok"},
        )

    async def execute() -> None:
        async with open_client(
            ORIGIN, transport=httpx.MockTransport(respond)
        ) as client:
            result = await verify_target(client, resolve_target("staging", None))
            assert result.identity() == IDENTITY

    if failure:
        with pytest.raises(TargetRejected):
            asyncio.run(execute())
    else:
        asyncio.run(execute())
    assert seen == ["/health/identity", "/health/ready"] + (
        [] if failure in {"unready", "malformed-ready"} else ["/health/identity"]
    )


@pytest.mark.parametrize("status", [408, 429])
@pytest.mark.parametrize("path", ["/health/identity", "/health/ready"])
def test_transient_health_http_pauses_admission_until_next_healthy_probe(
    status: int, path: str
) -> None:
    """Real target classification must retain periodic pause/resume semantics."""

    async def execute() -> None:
        time = ManualClock()
        runtime = SafetyRuntime({}, monotonic=lambda: time.now, sleep=time.sleep)
        unavailable = False
        sent: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(request.url.path)
            if unavailable and request.url.path == path:
                return httpx.Response(status, json={"status": "unavailable"})
            return httpx.Response(
                200,
                json=IDENTITY
                if request.url.path == "/health/identity"
                else {"status": "ok"}
                if request.url.path == "/health/ready"
                else {},
            )

        async with open_client(
            ORIGIN, transport=httpx.MockTransport(respond)
        ) as client:

            async def probe() -> dict[str, object]:
                return (
                    await verify_target(client, resolve_target("staging", None))
                ).identity()

            runtime.bind_probe(probe)
            with runtime.scope(), runtime.phase("simulation"):
                await runtime.check_target()
                await runtime.start_monitor()
                request: asyncio.Task[object] | None = None
                try:
                    unavailable = True
                    await time.settle()
                    await time.advance(10)
                    for _ in range(5):
                        await time.settle()
                    probes = cast(dict[str, object], runtime.snapshot()["probes"])
                    assert runtime.abort_reason is None
                    assert probes["paused"] is True
                    assert probes["last"] == "unavailable"
                    request = asyncio.create_task(client.get("/business"))
                    await time.settle()
                    assert "/business" not in sent
                    unavailable = False
                    await time.advance(10)
                    await asyncio.wait_for(request, timeout=3)
                    probes = cast(dict[str, object], runtime.snapshot()["probes"])
                    assert probes["paused"] is False
                    assert probes["consecutive_failures"] == 0
                    assert runtime.abort_reason is None
                    assert sent.count("/business") == 1
                finally:
                    if request is not None:
                        if not request.done():
                            request.cancel()
                        await asyncio.gather(request, return_exceptions=True)
                    await runtime.stop_monitor()
        assert not time.waiters

    asyncio.run(execute())


def test_readiness_redirect_is_terminal_and_cannot_resume_after_healthy_probe() -> None:
    async def execute() -> None:
        time = ManualClock()
        runtime = SafetyRuntime({}, monotonic=lambda: time.now, sleep=time.sleep)
        redirect = False
        sent: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            assert "authorization" not in request.headers
            sent.append(str(request.url))
            if redirect and request.url.path == "/health/ready":
                return httpx.Response(
                    307, headers={"location": "https://evil.test/ready"}
                )
            return httpx.Response(
                200,
                json=IDENTITY
                if request.url.path == "/health/identity"
                else {"status": "ok"},
            )

        async with open_client(
            ORIGIN, transport=httpx.MockTransport(respond)
        ) as client:

            async def probe() -> dict[str, object]:
                return (
                    await verify_target(client, resolve_target("staging", None))
                ).identity()

            runtime.bind_probe(probe)
            with runtime.scope(), runtime.phase("simulation"):
                await runtime.check_target()
                await runtime.start_monitor()
                try:
                    redirect = True
                    await time.settle()
                    await time.advance(10)
                    for _ in range(5):
                        await time.settle()
                    assert runtime.abort_reason == "identity_mismatch"
                    probes = cast(dict[str, object], runtime.snapshot()["probes"])
                    assert probes["failed"] == 1
                    assert probes["last"] == "invalid"
                    assert sent == [
                        f"{ORIGIN}/health/identity",
                        f"{ORIGIN}/health/ready",
                        f"{ORIGIN}/health/identity",
                        f"{ORIGIN}/health/identity",
                        f"{ORIGIN}/health/ready",
                    ]
                    redirect = False
                    await time.advance(10)
                    with pytest.raises(SafetyAborted):
                        await runtime.check_target()
                    with pytest.raises(SafetyAborted):
                        await client.get("/business")
                    assert runtime.abort_reason == "identity_mismatch"
                    assert len(sent) == 5
                finally:
                    await runtime.stop_monitor()
        assert not time.waiters

    asyncio.run(execute())
