"""The public API client refuses to send to any origin but its bound one (A-4)."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from tailtag_simulator.client import (
    MAX_RESPONSE_BYTES,
    Reply,
    RequestFailed,
    open_client,
)


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


# -- token provider, PUT, and cookie separation (#219 P-4, D5) ----------------

ORIGIN = "https://staging.tailtag.app"


def serve(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return seen, httpx.MockTransport(record)


def test_provider_is_awaited_per_request_so_a_refreshed_token_is_sent() -> None:
    tokens = iter(["a.b.one", "a.b.two"])
    seen, transport = serve(lambda _r: httpx.Response(200, json={}))

    async def provider() -> str:
        return next(tokens)

    async def attempt() -> None:
        async with open_client(
            ORIGIN, token_provider=provider, transport=transport
        ) as c:
            await c.get("/api/me/")
            await c.put("/api/profile/", {"handle": "x"})

    asyncio.run(attempt())

    assert [r.headers["authorization"] for r in seen] == [
        "Bearer a.b.one",
        "Bearer a.b.two",
    ]


def test_a_fixed_token_and_a_provider_together_are_refused() -> None:
    async def provider() -> str:
        return "a.b.c"

    async def attempt() -> None:
        async with open_client(ORIGIN, token="a.b.c", token_provider=provider):
            pass

    with pytest.raises(ValueError):
        asyncio.run(attempt())


def test_put_sends_a_json_body_with_the_bearer_token() -> None:
    seen, transport = serve(lambda _r: httpx.Response(200, json={"ok": True}))

    async def attempt() -> Reply:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            return await c.put("/api/profile/", {"handle": "sp_p1_1"})

    reply = asyncio.run(attempt())

    assert reply == Reply(200, {"ok": True})
    (request,) = seen
    assert request.method == "PUT"
    assert json.loads(request.content) == {"handle": "sp_p1_1"}
    assert request.headers["content-type"] == "application/json"
    assert request.headers["authorization"] == "Bearer a.b.c"


@pytest.mark.parametrize("case", ["cross-origin", "redirect", "oversized"])
def test_put_is_origin_pinned_unredirected_and_size_capped(case: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "evil.example":
            return httpx.Response(200, json={})
        if case == "redirect":
            return httpx.Response(307, headers={"location": "https://evil.example/x"})
        return httpx.Response(200, content=b"{}" + b" " * (MAX_RESPONSE_BYTES + 1))

    seen, transport = serve(respond)
    path = "https://evil.example/api/profile/" if case == "cross-origin" else "/p/"

    async def attempt() -> None:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            await c.put(path, {"handle": "x"})

    with pytest.raises(RequestFailed):
        asyncio.run(attempt())
    assert all(r.url.host != "evil.example" for r in seen)
    assert (seen == []) == (case == "cross-origin")


def test_api_client_never_stores_or_sends_cookies() -> None:
    seen, transport = serve(
        lambda _r: httpx.Response(
            200, json={}, headers={"set-cookie": "session=COOKIE-VALUE; Path=/"}
        )
    )

    async def attempt() -> None:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            await c.get("/api/me/")
            await c.get("/api/me/")

    asyncio.run(attempt())

    assert len(seen) == 2
    assert all("cookie" not in r.headers for r in seen)
