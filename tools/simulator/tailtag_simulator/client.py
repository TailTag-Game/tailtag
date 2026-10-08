"""The public API client: the only way simulator code reaches a TailTag API."""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http.cookiejar import DefaultCookiePolicy

import httpx

from tailtag_simulator import limits

MAX_RESPONSE_BYTES = limits.MAX_RESPONSE_BYTES
REQUEST_TIMEOUT_SECONDS = limits.REQUEST_TIMEOUT_SECONDS


class RequestFailed(Exception):
    """A request did not complete as a plain, bounded, non-redirect response."""


class TransportFailed(RequestFailed):
    """A genuine transport failure, without external error details."""


@dataclass(frozen=True)
class Reply:
    """One observed response: the status and the parsed JSON body, if it had one."""

    status: int
    body: object | None


@dataclass(frozen=True)
class Upload:
    """One file part of a multipart request. The bytes never appear in a repr."""

    filename: str
    content: bytes = field(repr=False)
    content_type: str


class ApiClient:
    """Client bound to one validated origin, sending a bearer token when it has one.

    The token is fixed on the client or, with a provider, awaited for every request so
    a refreshed token is always the one sent. A path that resolves to any other origin,
    such as an absolute URL taken from a response, is refused before sending. Redirects
    are never followed and any 3xx is a failure, so a bearer token cannot be sent
    anywhere but the origin it was bound to. Responses are size-capped. JSON, bodiless and
    multipart requests all go through the one `_send` path, so none escapes these rules.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        token_provider: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._client = client
        self._token_provider = token_provider

    async def get(self, path: str) -> Reply:
        return await self._send("GET", path)

    async def put(self, path: str, body: Mapping[str, object]) -> Reply:
        return await self._send("PUT", path, body)

    async def post(self, path: str, body: Mapping[str, object] | None = None) -> Reply:
        """POST a JSON body, or no body at all when `body` is None."""
        return await self._send("POST", path, body)

    async def delete(self, path: str) -> Reply:
        return await self._send("DELETE", path)

    async def put_multipart(
        self, path: str, data: Mapping[str, str], files: Mapping[str, Upload]
    ) -> Reply:
        return await self._send("PUT", path, data=data, files=files)

    async def post_multipart(
        self, path: str, data: Mapping[str, str], files: Mapping[str, Upload]
    ) -> Reply:
        return await self._send("POST", path, data=data, files=files)

    async def _send(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, Upload] | None = None,
    ) -> Reply:
        bound = self._client.base_url
        url = self._client.build_request(method, path).url
        if (url.scheme, url.host, url.port) != (bound.scheme, bound.host, bound.port):
            raise RequestFailed
        headers: dict[str, str] = {}
        if self._token_provider is not None:
            headers["Authorization"] = f"Bearer {await self._token_provider()}"
        parts = (
            None
            if files is None
            else {
                key: (upload.filename, upload.content, upload.content_type)
                for key, upload in files.items()
            }
        )
        try:
            async with self._client.stream(
                method, path, headers=headers, json=body, data=data, files=parts
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
            raise TransportFailed from None
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
