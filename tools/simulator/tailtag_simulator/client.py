"""The public API client: the only way simulator code reaches a TailTag API."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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
    """GET-only client bound to one validated origin and an optional bearer token.

    A path that resolves to any other origin, such as an absolute URL taken from a
    response, is refused before sending. Redirects are never followed and any 3xx is
    a failure, so a bearer token cannot be sent anywhere but the origin it was bound
    to. Responses are size-capped.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get(self, path: str) -> Reply:
        bound = self._client.base_url
        url = self._client.build_request("GET", path).url
        if (url.scheme, url.host, url.port) != (bound.scheme, bound.host, bound.port):
            raise RequestFailed
        try:
            async with self._client.stream("GET", path) as response:
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
            body: object | None = json.loads(raw)
        except (RecursionError, UnicodeError, ValueError):
            body = None
        return Reply(status, body)


@asynccontextmanager
async def open_client(
    origin: str,
    *,
    token: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncGenerator[ApiClient]:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with httpx.AsyncClient(
        base_url=origin,
        headers=headers,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        yield ApiClient(client)
