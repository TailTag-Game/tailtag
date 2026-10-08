"""Simulation fixture provisioning and the fixture smoke run (#220).

SETUP leases pool identities (#219), then asks the fixture channel to give the run its
own Convention, enrollments, photo-bearing fursuits and activations. The channel is a
privileged call into the Staging API that this package only drives as a subprocess.
Provisioning happens after every identity is onboarded and never overlaps SIMULATION,
which receives only the per-identity public clients.

Output is fixed stage lines, the run ID and counts. Failures map to a fixed stage name
and result code; no database ID, handle, media key, token, secret or response text is
ever written.
"""

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, cast

import httpx

from tailtag_simulator import limits
from tailtag_simulator.client import ApiClient, Reply, open_client
from tailtag_simulator.lifecycle import run_guarded
from tailtag_simulator.phases import PhaseFailed, RejectedResponse
from tailtag_simulator.pool import (
    LAUNCHER_ERRORS,
    LAUNCHER_TIMEOUT_SECONDS,
    Held,
    LeaseChannel,
    SetupFailed,
    open_identities,
    release,
    run_launcher,
)
from tailtag_simulator.reports import RunReport
from tailtag_simulator.safety import SafetyAborted, SafetyRuntime, active_runtime
from tailtag_simulator.smoke import StageFailed, attribute, guarded_stage
from tailtag_simulator.targets import resolve_target, verify_target

ACTIVE_PATH: Final = "/api/conventions/active/"
FURSUITS_PATH: Final = "/api/fursuits/"

_RESULT: Final = re.compile(r"FAIL_[A-Z_]{1,32}")


# -- fixture channel ---------------------------------------------------------------


class FixtureFailed(Exception):
    """A fixture operation failed. Carries a fixed result code and a count, no detail."""

    def __init__(self, result: str, quarantined: int | None = None) -> None:
        super().__init__(result)
        self.result = result
        self.quarantined = quarantined


class FixtureChannel(Protocol):
    """One privileged fixture operation: returns the response data or raises FixtureFailed."""

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]: ...


class FixtureLauncherChannel:
    """Drives the fixture launcher as a subprocess: request on stdin, one JSON on stdout.

    The request never appears in arguments and the child's stderr is discarded, so
    nothing it prints can reach this process's output. Any deviation from the exact
    launcher response shape, or a failure code that is not a plain `FAIL_*` name, is a
    `FAIL_LAUNCHER` with no detail.
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
        self, operation: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        envelope: dict[str, object] = {
            "operation": operation,
            "arguments": dict(arguments),
        }
        runtime = active_runtime()
        if runtime is not None:
            envelope["expected_identity"] = await runtime.privileged_identity()
        request = json.dumps(envelope).encode()
        try:
            result, data = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise FixtureFailed("FAIL_LAUNCHER") from None
        if result == "FAIL_TARGET" and runtime is not None:
            runtime.abort("identity_mismatch")
        if result == "PASS":
            return data
        if _RESULT.fullmatch(result) is None:
            raise FixtureFailed("FAIL_LAUNCHER") from None
        quarantined = data.get("quarantined")
        raise FixtureFailed(
            result,
            quarantined if type(quarantined) is int and quarantined >= 0 else None,
        ) from None


# -- cleanup and retention replies (#223) ------------------------------------------

CLEANUP_KINDS: Final = (
    "convention",
    "enrollment",
    "fursuit",
    "activation",
    "catch",
    "session",
    "credential",
    "image",
)
RETENTION_CAP: Final = limits.RETENTION_CAP
MAX_RETAINED_RUNS: Final = 100
RETAINED_REASONS: Final = frozenset(
    {"journeys", "reconciliation", "cleanup", "interrupted", "unfinished"}
)

# Why a failed run is retained; `pass` means the callback found nothing wrong.
Outcome = Literal["pass", "journeys", "reconciliation", "cleanup", "interrupted"]


def count_of(data: Mapping[str, object], key: str) -> int:
    """A non-negative int the channel reported, or FAIL_LAUNCHER for anything else."""
    value = data.get(key)
    if type(value) is not int or value < 0:
        raise FixtureFailed("FAIL_LAUNCHER")
    return value


def cleanup_counts(data: Mapping[str, object]) -> str:
    """The eight deleted-object counts of a passing `cleanup`, in fixed order."""
    return " ".join(f"{kind}={count_of(data, kind)}" for kind in CLEANUP_KINDS)


# -- the fixture smoke run ---------------------------------------------------------


@dataclass(frozen=True)
class FixtureSimulationContext:
    """All SIMULATION receives: public clients only, owners first then catchers."""

    owners: tuple[ApiClient, ...]
    catchers: tuple[ApiClient, ...]


@dataclass(frozen=True)
class OwnerReads:
    active: Reply
    fursuits: Reply
    activations: Reply | None


@dataclass(frozen=True)
class FixtureObservations:
    owners: tuple[OwnerReads, ...]
    catchers: tuple[Reply, ...]


def _body(reply: Reply) -> object:
    if reply.status != 200:
        if 200 <= reply.status < 300:
            raise PhaseFailed
        raise RejectedResponse
    return reply.body


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PhaseFailed
    return cast(dict[str, object], value)


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise PhaseFailed
    return value


def _convention_id(reply: Reply) -> int:
    """The id of the one active, enrolled Convention an identity reports."""
    enrollment = _object(_object(_body(reply)).get("enrollment"))
    convention = _object(enrollment.get("convention"))
    if enrollment.get("is_active") is not True or convention.get("status") != "active":
        raise PhaseFailed
    return _positive_int(convention.get("id"))


def _fixture_fursuits(reply: Reply) -> set[int]:
    listed = _body(reply)
    if not isinstance(listed, list):
        raise PhaseFailed
    ids: set[int] = set()
    for item in cast(list[object], listed):
        fursuit = _object(item)
        photo = fursuit.get("photo_url")
        identity = _positive_int(fursuit.get("id"))
        if (
            fursuit.get("is_enabled") is not True
            or not isinstance(photo, str)
            or not photo
            or identity in ids
        ):
            raise PhaseFailed
        ids.add(identity)
    return ids


def _fixture_activations(reply: Reply, ids: set[int] | None, convention: int) -> None:
    activated = _body(reply)
    if not isinstance(activated, list):
        raise PhaseFailed
    observed: set[int] = set()
    for item in cast(list[object], activated):
        entry = _object(item)
        identity = _positive_int(entry.get("fursuit_id"))
        if (
            entry.get("is_active") is not True
            or _positive_int(entry.get("convention_id")) != convention
            or identity in observed
        ):
            raise PhaseFailed
        observed.add(identity)
    if ids is not None and observed != ids:
        raise PhaseFailed


def _observe_fixture(check: Callable[[], object]) -> None:
    try:
        check()
    except RejectedResponse:
        return
    except PhaseFailed:
        runtime = active_runtime()
        if runtime is not None:
            runtime.abort("correctness")
        raise


async def simulate_fixtures(context: FixtureSimulationContext) -> FixtureObservations:
    """Validate successful reads before admitting the next public request."""
    owners: list[OwnerReads] = []
    convention: int | None = None

    def observe_active(reply: Reply) -> None:
        nonlocal convention
        seen = _convention_id(reply)
        if convention is not None and seen != convention:
            raise PhaseFailed
        convention = seen

    for client in context.owners:
        active = await client.get(ACTIVE_PATH)
        _observe_fixture(lambda active=active: observe_active(active))
        fursuits = await client.get(FURSUITS_PATH)
        _observe_fixture(lambda fursuits=fursuits: _fixture_fursuits(fursuits))
        try:
            current = _convention_id(active)
        except RejectedResponse:
            owners.append(OwnerReads(active, fursuits, None))
            continue
        activations = await client.get(
            f"/api/conventions/{current}/fursuit-activations/"
        )
        _observe_fixture(
            lambda activations=activations, fursuits=fursuits, current=current: (
                _fixture_activations(
                    activations,
                    _fixture_fursuits(fursuits) if fursuits.status == 200 else None,
                    current,
                )
            )
        )
        owners.append(OwnerReads(active, fursuits, activations))
    catchers: list[Reply] = []
    for client in context.catchers:
        reply = await client.get(ACTIVE_PATH)
        _observe_fixture(lambda reply=reply: observe_active(reply))
        catchers.append(reply)
    return FixtureObservations(tuple(owners), tuple(catchers))


def reconcile_fixtures(observed: FixtureObservations, fursuits_per_owner: int) -> None:
    """Everyone sees one Convention; each owner's fursuits are enabled, photographed, active."""
    seen = {_convention_id(reads.active) for reads in observed.owners}
    seen |= {_convention_id(reply) for reply in observed.catchers}
    if len(seen) != 1:
        raise PhaseFailed
    (convention_id,) = seen
    for reads in observed.owners:
        if reads.activations is None:
            raise PhaseFailed
        ids = _fixture_fursuits(reads.fursuits)
        if len(ids) != fursuits_per_owner:
            raise PhaseFailed
        _fixture_activations(reads.activations, ids, convention_id)


async def _check_retained(channel: FixtureChannel, emit: Callable[[str], None]) -> None:
    """Refuse a run at the retained cap, and warn when anything is retained or unfinished."""
    try:
        data = await channel.call("retained_counts", {})
        retained, unfinished = count_of(data, "retained"), count_of(data, "unfinished")
    except FixtureFailed as failure:
        raise StageFailed(f"setup result={failure.result}") from None
    except Exception:  # noqa: BLE001 - failures become a fixed stage
        raise StageFailed("setup") from None
    if retained >= RETENTION_CAP:
        raise StageFailed("setup result=FAIL_RETAINED_LIMIT")
    if retained or unfinished:
        emit(f"WARN retained={retained} unfinished={unfinished}")


async def _clean(
    channel: FixtureChannel,
    pool: str,
    run: str,
    emit: Callable[[str], None],
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
) -> bool:
    """CLEANUP: delete the run's state and print the counts; False after a fixed FAIL line."""
    try:
        data = await channel.call("cleanup", {"pool": pool, "run_id": run})
        counts = cleanup_counts(data)
        if report is not None:
            report.record_results(
                cleanup={
                    "value": {
                        kind: count_of(data, kind)
                        for kind in (*CLEANUP_KINDS, "readmitted")
                    },
                    "reason": None,
                }
            )
    except FixtureFailed as failure:
        emit(f"FAIL cleanup result={failure.result}")
        return False
    except Exception:  # noqa: BLE001 - failures become a fixed line
        emit("FAIL cleanup result=FAIL_ERROR")
        return False
    emit(f"PASS cleanup {counts}")
    return True


async def _retain(
    channel: FixtureChannel,
    pool: str,
    run: str,
    reason: str,
    emit: Callable[[str], None],
) -> bool:
    """RETAIN: quarantine the run's slots and keep its state; False after FAIL retain."""
    try:
        data = await channel.call(
            "retain", {"pool": pool, "run_id": run, "reason": reason}
        )
        quarantined = count_of(data, "quarantined")
    except KeyboardInterrupt:
        # Child tasks transport interruption as cancellation so asyncio can join recovery.
        raise asyncio.CancelledError from None
    except Exception:  # noqa: BLE001 - failures become a fixed line
        emit("FAIL retain")
        return False
    emit(f"RETAIN reason={reason} quarantined={quarantined}")
    return True


class _Renewal:
    """Run-owned renewal; only orchestration can see the privileged channel."""

    def __init__(self, channel: LeaseChannel) -> None:
        self.channel = channel
        self.worker: asyncio.Task[int] | None = None
        self.timer: asyncio.Task[None] | None = None
        self.failed = False

    async def call(
        self, operation: str, pool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        data = await self.channel.call(operation, pool, arguments)
        if operation == "allocate":
            self.timer = asyncio.create_task(self._renew(pool, arguments))
        return data

    async def _renew(self, pool: str, allocation: Mapping[str, object]) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                data = await self.channel.call(
                    "heartbeat",
                    pool,
                    {
                        "run_id": allocation["run_id"],
                        "ttl_seconds": limits.LEASE_TTL_SECONDS,
                    },
                )
                if (
                    type(data.get("extended")) is not int
                    or data["extended"] != allocation["count"]
                ):
                    raise FixtureFailed("FAIL_LEASE")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never expose launcher details
            self.failed = True
            if self.worker is not None:
                self.worker.cancel()

    async def stop(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
            try:
                await self.timer
            except asyncio.CancelledError:
                pass


async def run_provisioned(
    pool: str,
    owners: int,
    fursuits_per_owner: int,
    catchers: int,
    extra_identities: int,
    *,
    prompt_secret: Callable[[], str],
    lease_channel: LeaseChannel,
    fixture_channel: FixtureChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None,
    api_transport: httpx.AsyncBaseTransport | None,
    clock: Callable[[], float],
    run_id: str | None,
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
    reconcile_partial: Callable[[], Awaitable[None]] | None = None,
    renew_leases: bool = False,
    _renewal: _Renewal | None = None,
    simulate_and_reconcile: Callable[
        [str, tuple[ApiClient, ...], tuple[int, ...]],
        Awaitable[Literal["pass", "journeys", "reconciliation"]],
    ],
) -> int:
    """The Staging run both fixture commands share: target, lease, provision, clean, release.

    Before leasing, the run refuses at the retained cap and warns when anything is
    retained or unfinished. It leases `owners + catchers + extra_identities` identities
    and provisions the first `owners + catchers`; the rest are passed to `provision` as
    extras. Once SETUP passes, `simulate_and_reconcile` gets the verified origin, every
    identity's client and every leased pool index, in lease order, and reports `pass` or
    which part failed; a `StageFailed` it raises prints its fixed stage line.

    Once provision has passed, a `pass` outcome runs CLEANUP and anything else (a
    failure, a CLEANUP failure, any exception or an interrupt) runs RETAIN, which keeps
    the run's state and quarantines its slots. Once an allocation might have leased
    slots, RELEASE always runs last, even after a failure or an interrupt. The exit code
    is 0 only if everything passed.
    """
    runtime = (
        safety
        or active_runtime()
        or SafetyRuntime({}, observe=report.record_safety if report else None)
    )
    if active_runtime() is not runtime:
        return await run_guarded(
            lambda: run_provisioned(
                pool,
                owners,
                fursuits_per_owner,
                catchers,
                extra_identities,
                prompt_secret=prompt_secret,
                lease_channel=lease_channel,
                fixture_channel=fixture_channel,
                emit=emit,
                clerk_transport=clerk_transport,
                api_transport=api_transport,
                clock=clock,
                run_id=run_id,
                report=report,
                safety=runtime,
                simulate_and_reconcile=simulate_and_reconcile,
                reconcile_partial=reconcile_partial,
                renew_leases=renew_leases,
            ),
            safety=runtime,
            target="staging",
            base_url=None,
            population=owners + catchers + extra_identities,
            transport=api_transport,
            report=report,
            emit=emit,
        )
    if renew_leases:
        renewal = _Renewal(lease_channel)
        renewal.worker = asyncio.create_task(
            run_provisioned(
                pool,
                owners,
                fursuits_per_owner,
                catchers,
                extra_identities,
                prompt_secret=prompt_secret,
                lease_channel=renewal,
                fixture_channel=fixture_channel,
                emit=emit,
                clerk_transport=clerk_transport,
                api_transport=api_transport,
                clock=clock,
                run_id=run_id,
                report=report,
                simulate_and_reconcile=simulate_and_reconcile,
                _renewal=renewal,
                safety=runtime,
                reconcile_partial=reconcile_partial,
            )
        )
        try:
            return await renewal.worker
        except asyncio.CancelledError:
            if renewal.failed:
                emit("FAIL lease result=FAIL_LEASE")
                return 1
            raise
        finally:
            # Await work acknowledgement before the caller may finalize anything.
            if not renewal.worker.done():
                renewal.worker.cancel()
            try:
                await renewal.worker
            except asyncio.CancelledError:
                pass
            await renewal.stop()
    run = report.run_id if report is not None else run_id or str(uuid.uuid4())
    provisioned = owners + catchers
    count = provisioned + extra_identities
    stack = AsyncExitStack()
    held = Held()
    code = 1
    outcome: Outcome | None = (
        None  # Set before provisioning can commit, even without acknowledgement.
    )
    indexes: tuple[int, ...] = ()
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
            emit(f"RUN run_id={run}")
            await runtime.check_target()
            await _check_retained(fixture_channel, emit)

            try:
                with runtime.phase("setup"):
                    indexes, clients = await open_identities(
                        pool,
                        count,
                        run,
                        prompt_secret=prompt_secret,
                        channel=lease_channel,
                        stack=stack,
                        held=held,
                        origin=resolved.origin,
                        clerk_transport=clerk_transport,
                        api_transport=api_transport,
                        clock=clock,
                    )
                    # A sent provision may commit even if its acknowledgement is lost.
                    outcome = "interrupted"
                    await fixture_channel.call(
                        "provision",
                        {
                            "pool": pool,
                            "run_id": run,
                            "owners": list(indexes[:owners]),
                            "catchers": list(indexes[owners:provisioned]),
                            "fursuits_per_owner": fursuits_per_owner,
                            "extras": list(indexes[provisioned:]),
                        },
                    )
            except SafetyAborted:
                raise
            except SetupFailed as failure:
                raise StageFailed(f"setup{failure.detail}") from None
            except FixtureFailed as failure:
                if failure.result in {"FAIL_DIRTY", "FAIL_LEASE", "FAIL_INVARIANT"}:
                    outcome = None  # Definitive rejection/transactional rollback created no fixture state.
                suffix = (
                    ""
                    if failure.quarantined is None
                    else f" quarantined={failure.quarantined}"
                )
                raise StageFailed(f"setup result={failure.result}{suffix}") from None
            except Exception:  # noqa: BLE001 - failures become a fixed stage
                raise StageFailed("setup") from None
            outcome = (
                "interrupted"  # successful provision must retain even if report fails
            )
            if report is not None:
                report.end("setup", "passed")
            emit(
                f"PASS setup identities={count} fursuits={owners * fursuits_per_owner}"
            )

            outcome = "interrupted"  # unless the run reports otherwise
            try:
                outcome = await simulate_and_reconcile(
                    resolved.origin, clients, indexes
                )
            except StageFailed as failure:
                if failure.stage.split()[0] == "reconciliation":
                    outcome = "reconciliation"
                raise
            if report is not None:
                if report.scenario_version != 2 or report.correctness == "not_observed":
                    report.set_correctness("passed" if outcome == "pass" else "failed")
                if outcome == "pass":
                    outcome = "interrupted"
                    await attribute(verified, report, api_transport)
                    if not report.write_failed:
                        outcome = "pass"
            if outcome == "pass":
                outcome = (
                    "interrupted"  # an interrupt during CLEANUP is not a failure of it
                )
                if report is not None:
                    report.begin("cleanup")
                    if report.write_failed:
                        report.end("cleanup", "failed", "FAIL_REPORT")
                        raise StageFailed("report")
                await runtime.check_target()
                with runtime.phase("cleanup"):
                    cleaned = await _clean(fixture_channel, pool, run, emit, report)
                if report is not None:
                    report.end(
                        "cleanup",
                        "passed" if cleaned else "failed",
                        None if cleaned else "FAIL_CLEANUP",
                    )
                if cleaned:
                    outcome, code = "pass", 0
                else:
                    outcome = "cleanup"
        except StageFailed as failure:
            if report is not None and failure.stage.split()[0] == "setup":
                report.end("setup", "failed", "FAIL_SETUP")
            emit(f"FAIL {failure.stage}")
    except asyncio.CancelledError:
        if _renewal is not None and _renewal.failed:
            code = 1
            if report is not None:
                report.record_lease_failure()
        else:
            code = 130
        raise
    except BaseException:
        code = 130
        raise
    finally:

        async def finalize() -> None:
            nonlocal code, outcome
            if report is not None and report.write_failed:
                runtime.abort("report_failure", emit=False)
            if runtime.abort_reason == "correctness" and outcome == "interrupted":
                outcome = "journeys"
            if _renewal is not None:
                await _renewal.stop()
            await runtime.stop_monitor()
            allowed = await runtime.begin_finalization()
            release_safe = True
            try:
                if runtime.abort_reason is not None:
                    code = 1
                    if runtime.can_reconcile() and reconcile_partial is not None:
                        try:
                            with runtime.phase("reconciliation"):
                                await runtime.check_target()
                                await runtime.run_phase(reconcile_partial())
                            runtime.record_finalization("reconciliation", "passed")
                        except Exception:  # noqa: BLE001 - bounded diagnostic failure
                            runtime.record_finalization("reconciliation", "failed")
                    else:
                        runtime.record_finalization("reconciliation", "skipped")
                try:
                    if outcome not in (None, "pass"):
                        if not allowed:
                            runtime.record_finalization("retention", "skipped")
                        else:
                            if report is not None:
                                report.begin("retention")
                            try:
                                with runtime.phase("retention"):
                                    await runtime.check_target()
                                    retained = await runtime.run_phase(
                                        _retain(
                                            fixture_channel,
                                            pool,
                                            run,
                                            str(outcome),
                                            emit,
                                        )
                                    )
                            except SafetyAborted:
                                retained = False
                            runtime.record_finalization(
                                "retention", "passed" if retained else "uncertain"
                            )
                            if report is not None:
                                report.end(
                                    "retention",
                                    "passed" if retained else "failed",
                                    None if retained else "FAIL_RETAIN",
                                )
                            if not retained:
                                code = 1
                                # Quarantine independently before releasing possibly live fixture identities.
                                for index in indexes:
                                    try:
                                        with runtime.phase("retention"):
                                            await runtime.check_target()
                                            await runtime.run_phase(
                                                lease_channel.call(
                                                    "quarantine",
                                                    pool,
                                                    {"index": index, "run_id": run},
                                                )
                                            )
                                    except Exception:  # noqa: BLE001 - uncertain quarantine must not readmit leases
                                        release_safe = False
                                if not indexes:
                                    release_safe = False
                finally:
                    if held.leases:
                        if report is not None:
                            report.begin("release")
                        released = await release(
                            stack,
                            lease_channel,
                            pool,
                            run,
                            permit_release=release_safe,
                            quarantine_indexes=held.quarantine_indexes,
                        )
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


async def run_fixture_smoke(
    pool: str,
    owners: int,
    fursuits_per_owner: int,
    catchers: int,
    *,
    prompt_secret: Callable[[], str],
    lease_channel: LeaseChannel,
    fixture_channel: FixtureChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
    report: RunReport | None = None,
    safety: SafetyRuntime | None = None,
) -> int:
    """Run the fixture smoke on Staging and return the exit code: 0 only if all passed."""

    async def simulate_and_reconcile(
        _origin: str, clients: tuple[ApiClient, ...], _indexes: tuple[int, ...]
    ) -> Literal["pass"]:
        async with guarded_stage("simulation", report):
            observed = await simulate_fixtures(
                FixtureSimulationContext(clients[:owners], clients[owners:])
            )
        emit("PASS simulation")

        async with guarded_stage("reconciliation", report):
            reconcile_fixtures(observed, fursuits_per_owner)
        emit("PASS reconciliation")
        return "pass"

    return await run_provisioned(
        pool,
        owners,
        fursuits_per_owner,
        catchers,
        0,
        prompt_secret=prompt_secret,
        lease_channel=lease_channel,
        fixture_channel=fixture_channel,
        emit=emit,
        clerk_transport=clerk_transport,
        api_transport=api_transport,
        clock=clock,
        run_id=run_id,
        report=report,
        simulate_and_reconcile=simulate_and_reconcile,
        safety=safety,
    )
