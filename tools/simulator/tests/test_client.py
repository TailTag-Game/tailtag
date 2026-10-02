"""The public API client refuses to send to any origin but its bound one (A-4)."""

import asyncio

import httpx
import pytest

from tailtag_simulator.client import RequestFailed, open_client


@pytest.mark.parametrize(
    "path", ["https://evil.example/api/me/", "http://staging.tailtag.app/api/me/"]
)
def test_path_resolving_to_another_origin_is_never_sent(path: str) -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    async def attempt() -> None:
        async with open_client(
            "https://staging.tailtag.app",
            token="a.b.c",
            transport=httpx.MockTransport(handle),
        ) as client:
            await client.get(path)

    with pytest.raises(RequestFailed):
        asyncio.run(attempt())
    assert sent == []
