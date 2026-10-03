"""The synthetic identity pool lifecycle and the pool smoke run (#219).

The pool is provisioned in Clerk and leased through the lease channel, a privileged
call into the Staging API that this package only drives as a subprocess. Allocation
and every Clerk credential step happen in SETUP, which holds the Staging Clerk secret
only while it runs. SIMULATION receives one public `ApiClient` per identity, each
with an opaque token provider, and nothing else.

Output is fixed stage lines and counts. Failures map to a fixed stage name; no ID,
handle, token, secret, or response text is ever written.
"""

import asyncio
import json
import os
import re
import signal
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

import httpx

from tailtag_simulator.clerk import (
    ClerkAdmin,
    ClerkFailed,
    open_admin,
    open_session,
)
from tailtag_simulator.client import ApiClient, Reply, open_client
from tailtag_simulator.phases import (
    ME_PATH,
    Observations,
    PhaseFailed,
    ReconciliationContext,
    reconcile,
)
from tailtag_simulator.smoke import StageFailed, stage
from tailtag_simulator.targets import resolve_target, verify_target

LEASE_TTL_SECONDS: Final = 1800
MAX_POOL_SIZE: Final = 1000
# One ordinary token lives 60 seconds; waiting one second longer forces a refresh.
TOKEN_WAIT_SECONDS: Final = 61.0
PROFILE_PATH: Final = "/api/profile/"

LAUNCHER_TIMEOUT_SECONDS: Final = 180
MAX_LAUNCHER_OUTPUT_BYTES: Final = 65536

_POOL_NAME: Final = re.compile(r"[a-z0-9]{1,12}")


def validate_pool_name(name: str) -> str:
    if _POOL_NAME.fullmatch(name) is None:
        raise ValueError("invalid pool name")
    return name


def pool_handle(pool: str, index: int) -> str:
    return f"sp_{pool}_{index}"


def pool_display_name(pool: str, index: int) -> str:
    return f"Sim {pool} {index}"


# -- lease channel -----------------------------------------------------------------


class LeaseFailed(Exception):
    """A lease operation failed. Carries a fixed result code and a count, no detail."""

    def __init__(self, result: str, available: int | None = None) -> None:
        super().__init__(result)
        self.result = result
        self.available = available


class LeaseChannel(Protocol):
    """One privileged lease operation: returns the response data or raises LeaseFailed."""

    async def call(
        self, operation: str, pool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]: ...


LAUNCHER_ERRORS: Final = (
    OSError,
    TimeoutError,
    UnicodeError,
    ValueError,
    RecursionError,
)


async def run_launcher(
    command: Sequence[str], cwd: Path | None, timeout_seconds: float, request: bytes
) -> tuple[str, dict[str, object]]:
    """Run one launcher child and return its `(result, data)`; any deviation raises.

    The request goes on stdin only and the child's stderr is discarded. Only the exact
    `{"result", "data"}` shape is accepted, and `PASS` must go with exit code 0 and
    nothing else. Raises one of `LAUNCHER_ERRORS` for every deviation, with no detail.
    """
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        output, _ = await asyncio.wait_for(
            process.communicate(request), timeout_seconds
        )
    except BaseException:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        raise
    if len(output) > MAX_LAUNCHER_OUTPUT_BYTES:
        raise ValueError
    parsed = json.loads(output)
    reply = cast(dict[str, object], parsed) if isinstance(parsed, dict) else {}
    result, data = reply.get("result"), reply.get("data")
    if (
        frozenset(reply) != frozenset({"result", "data"})
        or not isinstance(result, str)
        or not isinstance(data, dict)
        or (result == "PASS") != (process.returncode == 0)
    ):
        raise ValueError
    return result, cast(dict[str, object], data)


class LauncherChannel:
    """Drives the lease launcher as a subprocess: request on stdin, one JSON on stdout.

    The request never appears in arguments, and the child's stderr is discarded, so
    nothing it prints can reach this process's output. Any deviation from the exact
    launcher response shape is a `FAIL_LAUNCHER` with no detail.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: float = LAUNCHER_TIMEOUT_SECONDS,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._timeout_seconds = timeout_seconds

    async def call(
        self, operation: str, pool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        request = json.dumps(
            {"operation": operation, "pool": pool, "arguments": dict(arguments)}
        ).encode()
        try:
            result, fields = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise LeaseFailed("FAIL_LAUNCHER") from None
        if result != "PASS":
            available = fields.get("available")
            raise LeaseFailed(
                result, available if type(available) is int else None
            ) from None
        return fields


# -- provisioning and the recovery commands ---------------------------------------------


async def provision(
    pool: str, size: int, *, admin: ClerkAdmin, channel: LeaseChannel
) -> int:
    """Bring the pool to `size`: create only missing Clerk users, then register slots.

    The instance is pinned first and every existing user is checked before anything is
    created or registered, so a bad instance or identity leaves everything unchanged.
    Returns how many Clerk users were created.
    """
    if not 1 <= size <= MAX_POOL_SIZE:
        raise ValueError("invalid pool size")
    await admin.verify_instance()
    missing: list[int] = []
    for index in range(size):
        existing = await admin.find_pool_user(pool, index)
        if existing is None:
            missing.append(index)
        else:
            admin.require_pool_identity(existing, pool, index)
    for index in missing:
        admin.require_pool_identity(
            await admin.create_pool_user(pool, index), pool, index
        )
    await channel.call("register", pool, {"size": size})
    return len(missing)


async def run_provision(
    pool: str,
    size: int,
    *,
    prompt_secret: Callable[[], str],
    channel: LeaseChannel,
    emit: Callable[[str], None],
) -> int:
    try:
        async with open_admin(prompt_secret()) as admin:
            created = await provision(pool, size, admin=admin, channel=channel)
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        emit("FAIL provision")
        return 1
    emit(f"PASS provision created={created}")
    return 0


async def run_status(
    pool: str, *, channel: LeaseChannel, emit: Callable[[str], None]
) -> int:
    try:
        data = await channel.call("status", pool, {})
        counts = [
            data[name] for name in ("total", "available", "leased", "quarantined")
        ]
        if not all(type(count) is int for count in counts):
            raise ValueError
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        emit("FAIL status")
        return 1
    total, available, leased, quarantined = counts
    emit(
        f"PASS status total={total} available={available} "
        f"leased={leased} quarantined={quarantined}"
    )
    return 0


async def run_readmit(
    pool: str, index: int, *, channel: LeaseChannel, emit: Callable[[str], None]
) -> int:
    try:
        await channel.call("readmit", pool, {"index": index})
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        emit("FAIL readmit")
        return 1
    emit("PASS readmit")
    return 0


# -- the pool smoke run ----------------------------------------------------------------


@dataclass(frozen=True)
class PoolSimulationContext:
    """All SIMULATION receives: one public client per identity, each with its provider."""

    clients: tuple[ApiClient, ...]


async def simulate_round(context: PoolSimulationContext) -> tuple[Reply, ...]:
    """One public `GET /api/me/` per identity, recorded as it came back."""
    return tuple([await client.get(ME_PATH) for client in context.clients])


def _profile(reply: Reply) -> tuple[object, object, object]:
    raw = reply.body
    if reply.status != 200 or not isinstance(raw, dict):
        raise PhaseFailed
    body = cast(dict[str, object], raw)
    return body.get("handle"), body.get("display_name"), body.get("onboarding_complete")


async def _ensure_profile(client: ApiClient, pool: str, index: int) -> None:
    """Onboard a never-onboarded identity once; accept only the exact pool profile."""
    handle, name = pool_handle(pool, index), pool_display_name(pool, index)
    current = _profile(await client.get(PROFILE_PATH))
    if current == (None, None, False):
        current = _profile(
            await client.put(PROFILE_PATH, {"handle": handle, "display_name": name})
        )
    if current[:2] != (handle, name) or current[2] is not True:
        raise PhaseFailed


async def _open_identity(
    admin: ClerkAdmin,
    stack: AsyncExitStack,
    pool: str,
    index: int,
    *,
    origin: str,
    clerk_transport: httpx.AsyncBaseTransport | None,
    api_transport: httpx.AsyncBaseTransport | None,
    clock: Callable[[], float],
) -> ApiClient:
    user = await admin.find_pool_user(pool, index)
    if user is None:
        raise PhaseFailed
    admin.require_pool_identity(user, pool, index)
    await admin.revoke_active_sessions(user)
    ticket = await admin.create_ticket(user)
    try:
        session = await stack.enter_async_context(
            open_session(ticket, transport=clerk_transport, clock=clock)
        )
    except Exception:
        with suppress(ClerkFailed):
            await admin.revoke_ticket(ticket)
        raise
    client = await stack.enter_async_context(
        open_client(origin, token_provider=session.token, transport=api_transport)
    )
    await _ensure_profile(client, pool, index)
    return client


def _reconcile(first: Sequence[Reply], second: Sequence[Reply]) -> None:
    """Each identity keeps one positive id and no two identities share one."""
    ids: list[object] = []
    for replies in zip(first, second, strict=True):
        reconcile(ReconciliationContext(Observations(replies)))
        ids.append(cast(dict[str, object], replies[0].body)["id"])
    if len(set(ids)) != len(ids):
        raise PhaseFailed


async def release(
    stack: AsyncExitStack, channel: LeaseChannel, pool: str, run_id: str
) -> bool:
    """End every Clerk session and release the leases; one half failing never skips the other."""
    released = True
    try:
        await stack.aclose()
    except Exception:  # noqa: BLE001 - reported as a fixed release failure
        released = False
    try:
        await channel.call("release", pool, {"run_id": run_id})
    except LeaseFailed:
        released = False
    return released


class SetupFailed(Exception):
    """SETUP failed; `detail` is the fixed, count-or-index-only suffix of the FAIL line."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("setup")
        self.detail = detail


@dataclass
class Held:
    """Whether an allocation may have leased slots, so RELEASE must run."""

    leases: bool = False


async def open_identities(
    pool: str,
    count: int,
    run: str,
    *,
    prompt_secret: Callable[[], str],
    channel: LeaseChannel,
    stack: AsyncExitStack,
    held: Held,
    origin: str,
    clerk_transport: httpx.AsyncBaseTransport | None,
    api_transport: httpx.AsyncBaseTransport | None,
    clock: Callable[[], float],
) -> tuple[tuple[int, ...], tuple[ApiClient, ...]]:
    """The only place the Clerk secret and the admin exist; neither outlives this call.

    Returns the allocated pool indexes and, in the same order, the per-identity
    clients. Their sessions are registered on `stack`. Shared by every Staging run
    that leases identities (#219, #220).
    """
    async with open_admin(prompt_secret(), transport=clerk_transport) as admin:
        await admin.verify_instance()
        held.leases = True
        try:
            allocated = await channel.call(
                "allocate",
                pool,
                {"run_id": run, "count": count, "ttl_seconds": LEASE_TTL_SECONDS},
            )
        except LeaseFailed as failure:
            if failure.result != "FAIL_INSUFFICIENT":
                raise
            held.leases = False
            if failure.available is None:
                raise
            raise SetupFailed(
                f" needed={count} available={failure.available}"
            ) from None
        indexes = allocated.get("indexes")
        if (
            not isinstance(indexes, list)
            or len(cast(list[object], indexes)) != count
            or not all(type(i) is int for i in cast(list[object], indexes))
        ):
            raise PhaseFailed
        clients: list[ApiClient] = []
        bad: list[int] = []
        for index in cast(list[int], indexes):
            try:
                clients.append(
                    await _open_identity(
                        admin,
                        stack,
                        pool,
                        index,
                        origin=origin,
                        clerk_transport=clerk_transport,
                        api_transport=api_transport,
                        clock=clock,
                    )
                )
            except Exception:  # noqa: BLE001 - quarantined below
                bad.append(index)
        if len(bad) == count:
            # Every identity failing points at the environment, not the identities.
            raise SetupFailed
        for index in bad:
            with suppress(LeaseFailed):
                await channel.call("quarantine", pool, {"index": index, "run_id": run})
        if bad:
            raise SetupFailed(" quarantined=" + ",".join(str(i) for i in sorted(bad)))
    return tuple(cast(list[int], indexes)), tuple(clients)


async def run_pool_smoke(
    pool: str,
    count: int,
    *,
    prompt_secret: Callable[[], str],
    channel: LeaseChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
) -> int:
    """Run the pool smoke on Staging and return the exit code: 0 only if all passed.

    Once an allocation might have leased slots, RELEASE always runs, even after a
    failure or an interrupt.
    """
    run = run_id or str(uuid.uuid4())
    stack = AsyncExitStack()
    held = Held()
    code = 1
    try:
        try:
            with stage("target"):
                resolved = resolve_target("staging", None)
                async with open_client(
                    resolved.origin, transport=api_transport
                ) as probe:
                    verified = await verify_target(probe, resolved)
            emit(f"PASS target staging source_sha={verified.source_sha}")

            try:
                _, clients = await open_identities(
                    pool,
                    count,
                    run,
                    prompt_secret=prompt_secret,
                    channel=channel,
                    stack=stack,
                    held=held,
                    origin=resolved.origin,
                    clerk_transport=clerk_transport,
                    api_transport=api_transport,
                    clock=clock,
                )
            except SetupFailed as failure:
                raise StageFailed(f"setup{failure.detail}") from None
            except Exception:  # noqa: BLE001 - failures become a fixed stage
                raise StageFailed("setup") from None
            emit(f"PASS setup identities={count}")

            with stage("simulation"):
                context = PoolSimulationContext(clients)
                first = await simulate_round(context)
                beat = await channel.call(
                    "heartbeat", pool, {"run_id": run, "ttl_seconds": LEASE_TTL_SECONDS}
                )
                extended = beat.get("extended")
                if type(extended) is not int or extended != count:
                    raise StageFailed("simulation")  # a lease was lost mid-run
                await sleep(TOKEN_WAIT_SECONDS)
                second = await simulate_round(context)
            emit("PASS simulation")

            with stage("reconciliation"):
                _reconcile(first, second)
            emit("PASS reconciliation")
            code = 0
        except StageFailed as failure:
            emit(f"FAIL {failure.stage}")
    finally:
        if held.leases:
            released = await release(stack, channel, pool, run)
            emit("PASS release" if released else "FAIL release")
            if not released:
                code = 1
        else:
            await stack.aclose()
    return code
