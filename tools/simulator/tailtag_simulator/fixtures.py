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

from tailtag_simulator.client import ApiClient, Reply, open_client
from tailtag_simulator.phases import PhaseFailed
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
from tailtag_simulator.smoke import StageFailed, stage
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
        request = json.dumps(
            {"operation": operation, "arguments": dict(arguments)}
        ).encode()
        try:
            result, data = await run_launcher(
                self._command, self._cwd, self._timeout_seconds, request
            )
        except LAUNCHER_ERRORS:
            raise FixtureFailed("FAIL_LAUNCHER") from None
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
RETENTION_CAP: Final = 5
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
        raise PhaseFailed
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


async def simulate_fixtures(context: FixtureSimulationContext) -> FixtureObservations:
    """Public reads only: every identity reads its active Convention; owners read more."""
    owners: list[OwnerReads] = []
    for client in context.owners:
        active = await client.get(ACTIVE_PATH)
        fursuits = await client.get(FURSUITS_PATH)
        try:
            path = f"/api/conventions/{_convention_id(active)}/fursuit-activations/"
        except PhaseFailed:
            owners.append(OwnerReads(active, fursuits, None))
            continue
        owners.append(OwnerReads(active, fursuits, await client.get(path)))
    return FixtureObservations(
        tuple(owners),
        tuple([await client.get(ACTIVE_PATH) for client in context.catchers]),
    )


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
        listed = _body(reads.fursuits)
        if not isinstance(listed, list):
            raise PhaseFailed
        ids: set[int] = set()
        for item in cast(list[object], listed):
            fursuit = _object(item)
            photo = fursuit.get("photo_url")
            if (
                fursuit.get("is_enabled") is not True
                or not isinstance(photo, str)
                or not photo
            ):
                raise PhaseFailed
            ids.add(_positive_int(fursuit.get("id")))
        activated = _body(reads.activations)
        if len(ids) != fursuits_per_owner or not isinstance(activated, list):
            raise PhaseFailed
        entries = [_object(item) for item in cast(list[object], activated)]
        if (
            len(entries) != len(ids)
            or {
                entry.get("fursuit_id")
                for entry in entries
                if entry.get("is_active") is True
                and entry.get("convention_id") == convention_id
            }
            != ids
        ):
            raise PhaseFailed


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
    channel: FixtureChannel, pool: str, run: str, emit: Callable[[str], None]
) -> bool:
    """CLEANUP: delete the run's state and print the counts; False after a fixed FAIL line."""
    try:
        data = await channel.call("cleanup", {"pool": pool, "run_id": run})
        counts = cleanup_counts(data)
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
    except Exception:  # noqa: BLE001 - failures become a fixed line
        emit("FAIL retain")
        return False
    emit(f"RETAIN reason={reason} quarantined={quarantined}")
    return True


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
    run = run_id or str(uuid.uuid4())
    provisioned = owners + catchers
    count = provisioned + extra_identities
    stack = AsyncExitStack()
    held = Held()
    code = 1
    outcome: Outcome | None = None  # None until provision has passed
    try:
        try:
            with stage("target"):
                resolved = resolve_target("staging", None)
                async with open_client(
                    resolved.origin, transport=api_transport
                ) as probe:
                    verified = await verify_target(probe, resolved)
            emit(f"PASS target staging source_sha={verified.source_sha}")
            emit(f"RUN run_id={run}")
            await _check_retained(fixture_channel, emit)

            try:
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
                # Every identity is onboarded and the Clerk secret is gone: provision.
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
            except SetupFailed as failure:
                raise StageFailed(f"setup{failure.detail}") from None
            except FixtureFailed as failure:
                suffix = (
                    ""
                    if failure.quarantined is None
                    else f" quarantined={failure.quarantined}"
                )
                raise StageFailed(f"setup result={failure.result}{suffix}") from None
            except Exception:  # noqa: BLE001 - failures become a fixed stage
                raise StageFailed("setup") from None
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
            if outcome == "pass":
                outcome = (
                    "interrupted"  # an interrupt during CLEANUP is not a failure of it
                )
                if await _clean(fixture_channel, pool, run, emit):
                    outcome, code = "pass", 0
                else:
                    outcome = "cleanup"
        except StageFailed as failure:
            emit(f"FAIL {failure.stage}")
    finally:
        try:
            if outcome not in (None, "pass") and not await _retain(
                fixture_channel, pool, run, str(outcome), emit
            ):
                code = 1
        finally:  # RELEASE runs even if RETAIN is interrupted
            if held.leases:
                released = await release(stack, lease_channel, pool, run)
                emit("PASS release" if released else "FAIL release")
                if not released:
                    code = 1
            else:
                await stack.aclose()
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
) -> int:
    """Run the fixture smoke on Staging and return the exit code: 0 only if all passed."""

    async def simulate_and_reconcile(
        _origin: str, clients: tuple[ApiClient, ...], _indexes: tuple[int, ...]
    ) -> Literal["pass"]:
        with stage("simulation"):
            observed = await simulate_fixtures(
                FixtureSimulationContext(clients[:owners], clients[owners:])
            )
        emit("PASS simulation")

        with stage("reconciliation"):
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
        simulate_and_reconcile=simulate_and_reconcile,
    )
