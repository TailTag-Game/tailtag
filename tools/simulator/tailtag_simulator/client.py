"""The public API client: the only way simulator code reaches a TailTag API."""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from http.cookiejar import DefaultCookiePolicy

import httpx

MAX_RESPONSE_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 10.0


class RequestFailed(Exception):
    """A request did not complete as a plain, bounded, non-redirect response."""


@dataclass(frozen=True)
class Reply:
    """One observed response: the status and the parsed JSON body, if it had one."""

    status: int
    body: object | None


class ApiClient:
    """Client bound to one validated origin, sending a bearer token when it has one.

    The token is fixed on the client or, with a provider, awaited for every request so
    a refreshed token is always the one sent. A path that resolves to any other origin,
    such as an absolute URL taken from a response, is refused before sending. Redirects
    are never followed and any 3xx is a failure, so a bearer token cannot be sent
    anywhere but the origin it was bound to. Responses are size-capped.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        token_provider: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._client = client
        self._token_provider = token_provider

    async def get(self, path: str) -> Reply:
        return await self._send("GET", path, None)

    async def put(self, path: str, body: Mapping[str, object]) -> Reply:
        return await self._send("PUT", path, body)

    async def _send(
        self, method: str, path: str, body: Mapping[str, object] | None
    ) -> Reply:
        bound = self._client.base_url
        url = self._client.build_request(method, path).url
        if (url.scheme, url.host, url.port) != (bound.scheme, bound.host, bound.port):
            raise RequestFailed
        headers: dict[str, str] = {}
        if self._token_provider is not None:
            headers["Authorization"] = f"Bearer {await self._token_provider()}"
        try:
            async with self._client.stream(
                method, path, headers=headers, json=body
            ) as response:
                if 300 <= response.status_code < 400:
                    raise RequestFailed
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise RequestFailed
                status = response.status_code
        except httpx.HTTPError:
            raise RequestFailed from None
        try:
            parsed: object | None = json.loads(raw)
        except (RecursionError, UnicodeError, ValueError):
            parsed = None
        return Reply(status, parsed)


@asynccontextmanager
async def open_client(
    origin: str,
    *,
    token: str | None = None,
    token_provider: Callable[[], Awaitable[str]] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncGenerator[ApiClient]:
    if token is not None and token_provider is not None:
        raise ValueError("pass a fixed token or a token provider, not both")
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with httpx.AsyncClient(
        base_url=origin,
        headers=headers,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        # The API client never stores or sends cookies (#219 D5).
        client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        yield ApiClient(client, token_provider)
