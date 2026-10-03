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
from collections.abc import Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

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
    """Run the fixture smoke on Staging and return the exit code: 0 only if all passed.

    Once an allocation might have leased slots, RELEASE always runs, even after a
    failure or an interrupt. The fixtures themselves stay in place for #222 and #223.
    """
    run = run_id or str(uuid.uuid4())
    count = owners + catchers
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
            emit(f"RUN run_id={run}")

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
                        "catchers": list(indexes[owners:]),
                        "fursuits_per_owner": fursuits_per_owner,
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

            with stage("simulation"):
                observed = await simulate_fixtures(
                    FixtureSimulationContext(clients[:owners], clients[owners:])
                )
            emit("PASS simulation")

            with stage("reconciliation"):
                reconcile_fixtures(observed, fursuits_per_owner)
            emit("PASS reconciliation")
            code = 0
        except StageFailed as failure:
            emit(f"FAIL {failure.stage}")
    finally:
        if held.leases:
            released = await release(stack, lease_channel, pool, run)
            emit("PASS release" if released else "FAIL release")
            if not released:
                code = 1
        else:
            await stack.aclose()
    return code
