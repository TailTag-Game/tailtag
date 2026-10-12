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

from tailtag_simulator import limits
from tailtag_simulator.clerk import (
    ClerkAdmin,
    ClerkFailed,
    SetupDiagnostic,
    SetupStep,
    open_admin,
    open_session,
    setup_boundary,
    setup_failure,
)
from tailtag_simulator.client import (
    ApiClient,
    Reply,
    RequestFailed,
    TransportFailed,
    open_client,
)
from tailtag_simulator.lifecycle import run_guarded
from tailtag_simulator.phases import (
    ME_PATH,
    Observations,
    PhaseFailed,
    ReconciliationContext,
    observe_identity,
    reconcile,
)
from tailtag_simulator.reports import RunReport
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime, active_runtime
from tailtag_simulator.smoke import StageFailed, attribute, guarded_stage
from tailtag_simulator.targets import resolve_target, verify_target

LEASE_TTL_SECONDS: Final = limits.LEASE_TTL_SECONDS
MAX_POOL_SIZE: Final = 1000
# One ordinary token lives 60 seconds; waiting one second longer forces a refresh.
TOKEN_WAIT_SECONDS: Final = 61.0
SETUP_WAIT_SECONDS: Final = 4.0
PROFILE_PATH: Final = "/api/profile/"

LAUNCHER_TIMEOUT_SECONDS: Final = limits.LAUNCHER_TIMEOUT_SECONDS
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
        envelope: dict[str, object] = {
            "operation": operation,
            "pool": pool,
            "arguments": dict(arguments),
        }
        runtime = active_runtime()
        if runtime is not None:
            envelope["expected_identity"] = await runtime.privileged_identity()
        request = json.dumps(envelope).encode()
        try:
            result, fields = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise LeaseFailed("FAIL_LAUNCHER") from None
        if result == "FAIL_TARGET" and runtime is not None:
            runtime.abort("identity_mismatch")
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
    replies: list[Reply] = []
    identities: set[int] = set()
    for client in context.clients:
        reply = await client.get(ME_PATH)
        replies.append(reply)
        identity = observe_identity(reply)
        if identity is not None:
            if identity in identities:
                runtime = active_runtime()
                if runtime is not None:
                    runtime.abort("correctness")
                raise PhaseFailed
            identities.add(identity)
    return tuple(replies)


def _profile(reply: Reply) -> tuple[object, object, object]:
    raw = reply.body
    if reply.status != 200 or not isinstance(raw, dict):
        runtime = active_runtime()
        if runtime is not None and 200 <= reply.status < 300:
            runtime.abort("correctness")
        raise PhaseFailed
    body = cast(dict[str, object], raw)
    return body.get("handle"), body.get("display_name"), body.get("onboarding_complete")


async def _profile_request(
    client: ApiClient, step: SetupStep, body: Mapping[str, object] | None = None
) -> tuple[object, object, object]:
    with setup_boundary(step):
        try:
            reply = (
                await client.get(PROFILE_PATH)
                if body is None
                else await client.put(PROFILE_PATH, body)
            )
        except TransportFailed as error:
            raise setup_failure("timeout" if error.timed_out else "transport") from None
        except RequestFailed:
            raise setup_failure("invalid_response") from None
        try:
            return _profile(reply)
        except PhaseFailed:
            if reply.status != 200:
                raise setup_failure("http", reply.status) from None
            raise setup_failure("invalid_response") from None


async def _ensure_profile(client: ApiClient, pool: str, index: int) -> None:
    """Onboard a never-onboarded identity once; accept only the exact pool profile."""
    handle, name = pool_handle(pool, index), pool_display_name(pool, index)
    current = await _profile_request(client, "profile_read")
    if current == (None, None, False):
        current = await _profile_request(
            client, "profile_write", {"handle": handle, "display_name": name}
        )
    with setup_boundary("profile_validation", "identity_invalid"):
        if current[:2] != (handle, name) or current[2] is not True:
            runtime = active_runtime()
            if runtime is not None:
                runtime.abort("correctness")
            raise ClerkFailed from None


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
    with setup_boundary("identity_validation", "identity_invalid"):
        if user is None:
            raise ClerkFailed from None
    admin.require_pool_identity(user, pool, index)
    await admin.revoke_active_sessions(user)
    ticket = await admin.create_ticket(user)
    try:
        session = await stack.enter_async_context(
            open_session(ticket, transport=clerk_transport, clock=clock)
        )
    except Exception:
        with suppress(Exception):
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
    stack: AsyncExitStack,
    channel: LeaseChannel,
    pool: str,
    run_id: str,
    *,
    permit_release: bool = True,
    quarantine_indexes: Sequence[int] = (),
) -> bool:
    """Close owned Clerk sessions and release only a freshly allowed pinned target."""
    runtime = active_runtime()
    released = True
    interruption: BaseException | None = None
    try:
        if runtime is None:
            await stack.aclose()
        else:
            await runtime.run_closure(stack.aclose())
            runtime.record_finalization("clerk_closure", "passed")
    except BaseException as failure:  # noqa: BLE001 - complete both obligations before propagating cancellation
        released = False
        if runtime is not None:
            runtime.record_finalization("clerk_closure", "uncertain")
        if not isinstance(failure, Exception):
            interruption = failure
    try:
        if quarantine_indexes:
            quarantined = True
            if runtime is not None and not bool(
                cast(dict[str, object], runtime.snapshot()["finalization"])["allowed"]
            ):
                quarantined = False
            else:
                for index in quarantine_indexes:
                    try:
                        if runtime is None:
                            await channel.call(
                                "quarantine", pool, {"index": index, "run_id": run_id}
                            )
                        else:
                            with runtime.phase("retention"):
                                await runtime.check_target()
                                await runtime.run_phase(
                                    channel.call(
                                        "quarantine",
                                        pool,
                                        {"index": index, "run_id": run_id},
                                    )
                                )
                    except Exception:  # noqa: BLE001 - an unacknowledged quarantine must keep its lease
                        quarantined = False
            permit_release = permit_release and quarantined
            if runtime is not None:
                runtime.record_finalization(
                    "retention", "passed" if quarantined else "uncertain"
                )
        if not permit_release or (
            runtime is not None
            and not bool(
                cast(dict[str, object], runtime.snapshot()["finalization"])["allowed"]
            )
        ):
            if runtime is not None:
                runtime.record_finalization("release", "skipped")
            released = False
        else:
            if runtime is None:
                await channel.call("release", pool, {"run_id": run_id})
            else:
                with runtime.phase("release"):
                    await runtime.check_target()
                    await runtime.run_phase(
                        channel.call("release", pool, {"run_id": run_id})
                    )
                runtime.record_finalization("release", "passed")
    except BaseException as failure:  # noqa: BLE001 - complete both obligations before propagating cancellation
        released = False
        if runtime is not None:
            runtime.record_finalization("release", "uncertain")
        if not isinstance(failure, Exception):
            interruption = failure
    if interruption is not None:
        raise interruption
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
    quarantine_indexes: tuple[int, ...] = ()


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
    emit: Callable[[str], None] | None = None,
    setup_sleep: Callable[[float], Awaitable[None]] | None = None,
) -> tuple[tuple[int, ...], tuple[ApiClient, ...]]:
    """The only place the Clerk secret and the admin exist; neither outlives this call.

    Returns the allocated pool indexes and, in the same order, the per-identity
    clients. Their sessions are registered on `stack`. Shared by every Staging run
    that leases identities (#219, #220).
    """
    wait = asyncio.sleep if setup_sleep is None else setup_sleep
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
        for position, index in enumerate(cast(list[int], indexes)):
            if position:
                await wait(SETUP_WAIT_SECONDS)
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
            except Exception as error:  # noqa: BLE001 - quarantined below
                diagnostic = (
                    error.diagnostic
                    if isinstance(error, ClerkFailed) and error.diagnostic is not None
                    else SetupDiagnostic("unknown", "unknown")
                )
                if emit is not None:
                    # Diagnostics are observational; cancellation still propagates.
                    with suppress(Exception):
                        emit(diagnostic.line(index))
                bad.append(index)
                # Preserve known failures if the next cooldown is interrupted.
                held.quarantine_indexes = tuple(bad)
                runtime = active_runtime()
                if runtime is not None and runtime.abort_reason is not None:
                    bad.extend(cast(list[int], indexes)[position + 1 :])
                    break
        runtime = active_runtime()
        if len(bad) == count and (runtime is None or runtime.abort_reason is None):
            # Every identity failing points at the environment, not the identities.
            held.quarantine_indexes = ()
            raise SetupFailed
        held.quarantine_indexes = tuple(bad)
        if runtime is None or runtime.abort_reason is None:
            for index in bad:
                try:
                    await channel.call(
                        "quarantine", pool, {"index": index, "run_id": run}
                    )
                except LeaseFailed:
                    continue
                held.quarantine_indexes = tuple(
                    pending for pending in held.quarantine_indexes if pending != index
                )
        if bad:
            if held.quarantine_indexes:
                raise SetupFailed(
                    " pending_quarantine="
                    + ",".join(str(i) for i in sorted(held.quarantine_indexes))
                )
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
    setup_sleep: Callable[[float], Awaitable[None]] | None = None,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
) -> int:
    """Run the pool smoke on Staging and return the exit code: 0 only if all passed.

    Once an allocation might have leased slots, RELEASE always runs, even after a
    failure or an interrupt.
    """
    runtime = (
        safety
        or active_runtime()
        or SafetyRuntime(
            {},
            observe=report.cache_safety if report else None,
            persist=report.record_safety if report else None,
        )
    )
    if active_runtime() is not runtime:
        return await run_guarded(
            lambda: run_pool_smoke(
                pool,
                count,
                prompt_secret=prompt_secret,
                channel=channel,
                emit=emit,
                clerk_transport=clerk_transport,
                api_transport=api_transport,
                sleep=sleep,
                setup_sleep=setup_sleep,
                clock=clock,
                run_id=run_id,
                report=report,
                safety=runtime,
            ),
            safety=runtime,
            target="staging",
            base_url=None,
            population=count,
            transport=api_transport,
            report=report,
            emit=emit,
        )
    run = report.run_id if report is not None else run_id or str(uuid.uuid4())
    stack = AsyncExitStack()
    held = Held()
    code = 1
    try:
        try:
            async with guarded_stage("target", report):
                resolved = resolve_target("staging", None)
                async with open_client(
                    resolved.origin, transport=api_transport
                ) as probe:
                    verified = await verify_target(probe, resolved)
            if report is not None:
                report.record_target(
                    resolved.name, resolved.origin, verified.identity()
                )
                report.begin("setup")
            emit(f"PASS target staging source_sha={verified.source_sha}")

            try:
                await runtime.check_target()
                with runtime.phase("setup"):
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
                        emit=emit,
                        setup_sleep=setup_sleep,
                    )
            except SafetyAborted:
                raise
            except SetupFailed as failure:
                raise StageFailed(f"setup{failure.detail}") from None
            except Exception:  # noqa: BLE001 - failures become a fixed stage
                raise StageFailed("setup") from None
            if report is not None:
                report.end("setup", "passed")
            emit(f"PASS setup identities={count}")

            async with guarded_stage("simulation", report):
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

            async with guarded_stage("reconciliation", report):
                _reconcile(first, second)
            emit("PASS reconciliation")
            if report is not None:
                report.set_correctness("passed")
                await attribute(verified, report, api_transport)
            code = 0
        except StageFailed as failure:
            if report is not None and failure.stage.split()[0] == "setup":
                report.end("setup", "failed", "FAIL_SETUP")
            emit(f"FAIL {failure.stage}")
    except BaseException:
        code = 130
        raise
    finally:

        async def finalize() -> None:
            nonlocal code
            if report is not None and report.write_failed:
                runtime.abort("report_failure", emit=False)
            await runtime.stop_monitor()
            await runtime.begin_finalization()
            try:
                if held.leases:
                    if report is not None:
                        report.begin("release")
                    try:
                        released = await release(
                            stack,
                            channel,
                            pool,
                            run,
                            quarantine_indexes=held.quarantine_indexes,
                        )
                    except BaseException:
                        code = 130
                        if report is not None:
                            report.end("release", "interrupted", "FAIL_INTERRUPTED")
                        raise
                    emit("PASS release" if released else "FAIL release")
                    if report is not None:
                        report.end(
                            "release",
                            "passed" if released else "failed",
                            None if released else "FAIL_RELEASE",
                        )
                    if not released:
                        code = 1
                else:
                    await runtime.run_closure(stack.aclose())
                    runtime.record_finalization("clerk_closure", "passed")
            finally:
                if report is not None:
                    report.record_safety(runtime.snapshot())

        finalizer = asyncio.create_task(finalize())
        try:
            await asyncio.shield(finalizer)
        except asyncio.CancelledError:
            await finalizer
            raise

    return code
