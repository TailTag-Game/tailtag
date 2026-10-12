"""The public API client refuses to send to any origin but its bound one (A-4)."""

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest

from tailtag_simulator.client import (
    MAX_RESPONSE_BYTES,
    ApiClient,
    Reply,
    RequestFailed,
    Upload,
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


UPLOAD = Upload(filename="a.png", content=b"\x89PNG-bytes", content_type="image/png")
Send = Callable[[ApiClient, str], Awaitable[Reply]]
# Every way a request can be written, each of which must keep every protection.
WRITES: dict[str, Send] = {
    "put": lambda c, p: c.put(p, {"handle": "x"}),
    "post-json": lambda c, p: c.post(p, {"payload": "x"}),
    "post-empty": lambda c, p: c.post(p, None),
    "delete": lambda c, p: c.delete(p),
    "put-multipart": lambda c, p: c.put_multipart(p, {}, {"photo": UPLOAD}),
    "post-multipart": lambda c, p: c.post_multipart(
        p, {"name": "Sim journey"}, {"photo": UPLOAD}
    ),
}


def serve(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return seen, httpx.MockTransport(record)


@pytest.mark.parametrize("write", WRITES)
def test_provider_is_awaited_per_request_so_a_refreshed_token_is_sent(
    write: str,
) -> None:
    tokens = iter(["a.b.one", "a.b.two"])
    seen, transport = serve(lambda _r: httpx.Response(200, json={}))

    async def provider() -> str:
        return next(tokens)

    async def attempt() -> None:
        async with open_client(
            ORIGIN, token_provider=provider, transport=transport
        ) as c:
            await c.get("/api/me/")
            await WRITES[write](c, "/api/profile/")

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


@pytest.mark.parametrize("write", WRITES)
@pytest.mark.parametrize("case", ["cross-origin", "redirect", "oversized"])
def test_every_write_is_origin_pinned_unredirected_and_size_capped(
    case: str, write: str
) -> None:
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
            await WRITES[write](c, path)

    with pytest.raises(RequestFailed):
        asyncio.run(attempt())
    assert all(r.url.host != "evil.example" for r in seen)
    assert (seen == []) == (case == "cross-origin")


@pytest.mark.parametrize("write", WRITES)
def test_api_client_never_stores_or_sends_cookies(write: str) -> None:
    seen, transport = serve(
        lambda _r: httpx.Response(
            200, json={}, headers={"set-cookie": "session=COOKIE-VALUE; Path=/"}
        )
    )

    async def attempt() -> None:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            await c.get("/api/me/")
            await WRITES[write](c, "/api/me/")

    asyncio.run(attempt())

    assert len(seen) == 2
    assert all("cookie" not in r.headers for r in seen)


@pytest.mark.parametrize(
    ("write", "method", "body"),
    [
        ("post-json", "POST", {"payload": "x"}),
        ("post-empty", "POST", None),
        ("delete", "DELETE", None),
    ],
)
def test_json_and_bodiless_writes_send_the_documented_method_and_body(
    write: str, method: str, body: dict[str, str] | None
) -> None:
    seen, transport = serve(lambda _r: httpx.Response(200, json={"ok": True}))

    async def attempt() -> Reply:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            return await WRITES[write](c, "/api/catches/confirm/")

    assert asyncio.run(attempt()) == Reply(200, {"ok": True})
    (request,) = seen
    assert request.method == method
    assert request.headers["authorization"] == "Bearer a.b.c"
    if body is None:
        assert request.content == b""
    else:
        assert json.loads(request.content) == body
        assert request.headers["content-type"] == "application/json"


@pytest.mark.parametrize(
    ("write", "method"),
    [("put-multipart", "PUT"), ("post-multipart", "POST")],
)
def test_multipart_writes_send_text_and_file_parts(write: str, method: str) -> None:
    seen, transport = serve(lambda _r: httpx.Response(201, json={}))

    async def attempt() -> None:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            await WRITES[write](c, "/api/fursuits/")

    asyncio.run(attempt())

    (request,) = seen
    assert request.method == method
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b'filename="a.png"' in request.content
    assert b"Content-Type: image/png\r\n\r\n\x89PNG-bytes\r\n" in request.content
    assert (b'name="name"' in request.content) == (write == "post-multipart")


@pytest.mark.parametrize(("size", "allowed"), [(65536, True), (65537, False)])
def test_the_response_cap_is_exactly_65536_bytes(size: int, allowed: bool) -> None:
    # A JSON string of exactly `size` bytes: two quotes around the filler.
    content = b'"' + b"x" * (size - 2) + b'"'
    _, transport = serve(lambda _r: httpx.Response(200, content=content))

    async def attempt() -> Reply:
        async with open_client(ORIGIN, token="a.b.c", transport=transport) as c:
            return await c.get("/api/catches/")

    if allowed:
        assert asyncio.run(attempt()) == Reply(200, "x" * (size - 2))
    else:
        with pytest.raises(RequestFailed):
            asyncio.run(attempt())
