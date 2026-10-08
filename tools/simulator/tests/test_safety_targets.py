"""#227 AC10: credential-free Staging identity/readiness/stability transcript."""

import asyncio

import httpx
import pytest

from tailtag_simulator.client import open_client
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
