"""Clerk tooling for the synthetic identity pool (#219): SETUP-only privileged calls.

`ClerkAdmin` holds the Staging Clerk secret and exists only for SETUP. `ClerkSession`
redeems one single-use sign-in ticket through the Frontend API with the pinned tooling
origin and the client cookie, then hands out ordinary 60-second session tokens. The
two use separate httpx clients, and neither is the TailTag API client.

Every failure is a `ClerkFailed` with no detail, raised from None, so no secret, ID,
ticket, token, cookie, or response text can reach an exception. Credential-bearing
objects have no field values in their `repr`.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import re
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

import httpx

BACKEND_API = "https://api.clerk.com"
FRONTEND_API = "https://clerk.staging.tailtag.app"
TOOLING_ORIGIN = "https://simulator.staging.tailtag.app"
INSTANCE_FINGERPRINT = "328b851879c17392"
PRIMARY_DOMAIN = "staging.tailtag.app"
FRONTEND_API_VERSION = "2026-05-12"
TICKET_SECONDS = 60
REFRESH_MARGIN_SECONDS = 15

MAX_RESPONSE_BYTES = 65536
REQUEST_TIMEOUT_SECONDS = 10.0

_SECRET_PREFIX = "sk_live_"
_ID = re.compile(r"[A-Za-z0-9_]+")


class ClerkFailed(Exception):
    """A Clerk step failed. Deliberately carries no detail."""


def external_id(pool: str, index: int) -> str:
    return f"sim-pool-{pool}-{index}"


@dataclass(frozen=True, repr=False)
class PoolUser:
    """A Clerk user as read from the Backend API; not yet known to be a pool identity."""

    id: str
    external_id: str | None
    public_metadata: dict[str, object] | None
    banned: bool
    locked: bool


@dataclass(frozen=True, repr=False)
class Ticket:
    """A single-use sign-in ticket: a credential."""

    id: str
    token: str


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ClerkFailed from None
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ClerkFailed from None
    return cast(list[object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ClerkFailed from None
    return value


def _path_id(value: object) -> str:
    text = _text(value)
    if _ID.fullmatch(text) is None:
        raise ClerkFailed from None
    return text


async def _call(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
    form: dict[str, str] | None = None,
) -> object:
    """One bounded call: 2xx and JSON, never redirected, never more than the cap."""
    try:
        async with client.stream(
            method, path, params=params, json=body, data=form
        ) as response:
            if not 200 <= response.status_code < 300:
                raise ClerkFailed from None
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ClerkFailed from None
    except httpx.HTTPError:
        raise ClerkFailed from None
    try:
        return json.loads(raw)
    except (RecursionError, UnicodeError, ValueError):
        raise ClerkFailed from None


def _client(
    base: str,
    headers: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base,
        headers=headers,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


class ClerkAdmin:
    """Backend API access for SETUP. Unusable until `verify_instance` succeeds."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._verified = False

    def __repr__(self) -> str:
        return "ClerkAdmin()"

    def _require_verified(self) -> None:
        if not self._verified:
            raise ClerkFailed from None

    async def verify_instance(self) -> None:
        """Pin the Production instance and its single primary domain (P-8a)."""
        self._verified = False
        instance = _object(await _call(self._client, "GET", "/v1/instance"))
        digest = hashlib.sha256(_text(instance.get("id")).encode()).hexdigest()[:16]
        if (
            digest != INSTANCE_FINGERPRINT
            or instance.get("environment_type") != "production"
        ):
            raise ClerkFailed from None
        domains = _object(await _call(self._client, "GET", "/v1/domains")).get("data")
        primaries = [
            d
            for d in (_object(item) for item in _list(domains))
            if d.get("is_satellite") is False
        ]
        if len(primaries) != 1 or (
            primaries[0].get("name") != PRIMARY_DOMAIN
            or primaries[0].get("frontend_api_url") != FRONTEND_API
        ):
            raise ClerkFailed from None
        self._verified = True

    @staticmethod
    def _user(raw: object) -> PoolUser:
        data = _object(raw)
        metadata = data.get("public_metadata")
        external = data.get("external_id")
        return PoolUser(
            id=_path_id(data.get("id")),
            external_id=external if isinstance(external, str) else None,
            public_metadata=_object(metadata) if metadata is not None else None,
            banned=data.get("banned") is not False,
            locked=data.get("locked") is not False,
        )

    async def find_pool_user(self, pool: str, index: int) -> PoolUser | None:
        self._require_verified()
        found = await _call(
            self._client,
            "GET",
            "/v1/users",
            params={"external_id": external_id(pool, index)},
        )
        users = _list(found)
        if len(users) > 1:
            raise ClerkFailed from None
        return self._user(users[0]) if users else None

    async def create_pool_user(self, pool: str, index: int) -> PoolUser:
        self._require_verified()
        name = external_id(pool, index)
        host = urlsplit(TOOLING_ORIGIN).hostname
        return self._user(
            await _call(
                self._client,
                "POST",
                "/v1/users",
                body={
                    "external_id": name,
                    "email_address": [f"{name}@{host}"],
                    "skip_password_requirement": True,
                    "public_metadata": {
                        "tailtag_synthetic": True,
                        "tailtag_environment": "staging",
                        "tailtag_pool": pool,
                        "tailtag_pool_index": index,
                    },
                },
            )
        )

    def require_pool_identity(self, user: PoolUser, pool: str, index: int) -> None:
        """Fail unless the user is an unbanned, unlocked, correctly marked pool user."""
        metadata = user.public_metadata or {}
        recorded_index = metadata.get("tailtag_pool_index")
        if not (
            user.external_id == external_id(pool, index)
            and metadata.get("tailtag_synthetic") is True
            and metadata.get("tailtag_environment") == "staging"
            and metadata.get("tailtag_pool") == pool
            and type(recorded_index) is int
            and recorded_index == index
            and not user.banned
            and not user.locked
        ):
            raise ClerkFailed from None

    async def revoke_active_sessions(self, user: PoolUser) -> int:
        self._require_verified()
        listed = await _call(
            self._client,
            "GET",
            "/v1/sessions",
            params={"user_id": user.id, "status": "active"},
        )
        ids = [_path_id(_object(item).get("id")) for item in _list(listed)]
        for session_id in ids:
            await _call(self._client, "POST", f"/v1/sessions/{session_id}/revoke")
        return len(ids)

    async def create_ticket(self, user: PoolUser) -> Ticket:
        """Mint a ticket only for a user that Clerk currently shows as a pool identity."""
        self._require_verified()
        metadata = user.public_metadata or {}
        pool, index = metadata.get("tailtag_pool"), metadata.get("tailtag_pool_index")
        if not isinstance(pool, str) or type(index) is not int:
            raise ClerkFailed from None
        current = await self.find_pool_user(pool, index)
        if current is None or current.id != user.id:
            raise ClerkFailed from None
        self.require_pool_identity(current, pool, index)
        created = _object(
            await _call(
                self._client,
                "POST",
                "/v1/sign_in_tokens",
                body={"user_id": user.id, "expires_in_seconds": TICKET_SECONDS},
            )
        )
        if created.get("user_id") != user.id:
            raise ClerkFailed from None
        return Ticket(id=_path_id(created.get("id")), token=_text(created.get("token")))

    async def revoke_ticket(self, ticket: Ticket) -> None:
        self._require_verified()
        await _call(
            self._client, "POST", f"/v1/sign_in_tokens/{_path_id(ticket.id)}/revoke"
        )


@asynccontextmanager
async def open_admin(
    secret: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> AsyncGenerator[ClerkAdmin]:
    if not secret.startswith(_SECRET_PREFIX) or secret != secret.strip():
        raise ClerkFailed from None
    async with _client(
        BACKEND_API, {"Authorization": f"Bearer {secret}"}, transport
    ) as client:
        yield ClerkAdmin(client)


class ClerkSession:
    """One Clerk session for a run: a lazily refreshed, cached ordinary token."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        clock: Callable[[], float],
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._clock = clock
        self._lock = asyncio.Lock()
        self._cached: tuple[str, int] | None = None

    def __repr__(self) -> str:
        return "ClerkSession()"

    async def token(self) -> str:
        """A token with more than the refresh margin of life left."""
        async with self._lock:
            if (
                self._cached is not None
                and self._cached[1] - self._clock() > REFRESH_MARGIN_SECONDS
            ):
                return self._cached[0]
            fetched = _object(
                await _call(
                    self._client,
                    "POST",
                    f"/v1/client/sessions/{self._session_id}/tokens",
                )
            )
            jwt = _text(fetched.get("jwt"))
            claims = _claims(jwt)
            expires = claims.get("exp")
            if (
                claims.get("azp") != TOOLING_ORIGIN
                or claims.get("sid") != self._session_id
                or type(expires) is not int
            ):
                raise ClerkFailed from None
            self._cached = (jwt, expires)
            return jwt

    async def end(self) -> None:
        await _call(self._client, "POST", f"/v1/client/sessions/{self._session_id}/end")


def _claims(jwt: str) -> dict[str, object]:
    parts = jwt.split(".")
    if len(parts) != 3:
        raise ClerkFailed from None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return _object(json.loads(base64.urlsafe_b64decode(padded)))
    except (binascii.Error, RecursionError, UnicodeError, ValueError):
        raise ClerkFailed from None


@asynccontextmanager
async def open_session(
    ticket: Ticket,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> AsyncGenerator[ClerkSession]:
    """Redeem the ticket with the browser-style client cookie (D1), end it on exit.

    Ending is attempted on every exit. A failure to end is reported only on a normal
    exit; on an error exit the body's own exception propagates.
    """
    headers = {"Origin": TOOLING_ORIGIN, "Clerk-API-Version": FRONTEND_API_VERSION}
    async with _client(FRONTEND_API, headers, transport) as client:
        await _call(client, "POST", "/v1/client")
        signed_in = _object(
            await _call(
                client,
                "POST",
                "/v1/client/sign_ins",
                form={"strategy": "ticket", "ticket": ticket.token},
            )
        )
        result = _object(signed_in.get("response"))
        if result.get("status") != "complete":
            raise ClerkFailed from None
        session = ClerkSession(
            client, _path_id(result.get("created_session_id")), clock
        )
        try:
            yield session
        except BaseException:
            with suppress(ClerkFailed):
                await session.end()
            raise
        await session.end()
