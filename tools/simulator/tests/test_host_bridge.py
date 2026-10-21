"""#228 U1: real finite authority/socket state; only provider and time substituted."""

import asyncio
import json
import os
import stat
import sys
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
from test_host_protocol import (
    IDENTITY,
    RUN,
    SENTINEL,
    expiration_manifest,
    journeys_manifest,
    manifest,
    section,
)

from tailtag_simulator import host_bridge
from tailtag_simulator.host_bridge import BridgeServer, BridgeSession
from tailtag_simulator.host_protocol import decode_frame, encode_frame

INDEXES = [17, 23, 31, 37, 41, 43]
ROLES = {
    "owner0": 17,
    "owner1": 23,
    "attendee0": 31,
    "attendee1": 37,
    "attendee2": 41,
    "attendee3": 43,
}
ACKS: dict[str, dict[str, object]] = {
    "retained_counts": {"retained": 0, "unfinished": 0},
    "allocate": {"indexes": INDEXES},
    "heartbeat": {"extended": 6},
    "quarantine": {},
    "provision": {"convention": 1, "enrollment": 6, "fursuit": 8, "activation": 8},
    "inspect-population-v1": {
        "catches": [],
        "fursuits": [{"id": 101, "owner": 17}],
        "fixture_photos_unchanged": True,
        "avatars": [],
    },
    "cleanup": {
        "convention": 1,
        "enrollment": 6,
        "fursuit": 8,
        "activation": 8,
        "catch": 0,
        "session": 0,
        "credential": 0,
        "image": 0,
        "readmitted": 0,
    },
    "retain": {"quarantined": 6},
    "release": {"released": 6},
}


@pytest.fixture
def socket_root() -> Iterator[Path]:
    # macOS Unix socket paths are limited to 104 bytes; pytest's default
    # temporary root beneath /private/var/folders can already exceed that.
    with TemporaryDirectory(prefix="tt228-", dir="/tmp") as directory:
        # for_paths refuses a symlink in any ancestor, and /tmp is one on macOS.
        yield Path(directory).resolve()


def private_server(session: BridgeSession, directory: Path) -> BridgeServer:
    """Bind both sockets inside one existing owner-only directory (for_paths)."""
    if not directory.exists() and not directory.is_symlink():
        directory.mkdir(mode=0o700)
    return BridgeServer.for_paths(
        session, directory / "rpc.sock", directory / "health.sock"
    )


def envelope(operation: str, **changes: object) -> dict[str, object]:
    arguments: dict[str, object] = {"run_id": RUN}
    if operation == "allocate":
        arguments.update(count=6, ttl_seconds=1800)
    elif operation == "heartbeat":
        arguments["ttl_seconds"] = 1800
    elif operation == "quarantine":
        arguments["index"] = 17
    elif operation == "retained_counts":
        arguments = {}
    elif operation == "provision":
        arguments.update(
            pool="alpha",
            owners=[17, 23],
            catchers=[31, 37, 41, 43],
            extras=[],
            fursuits_per_owner=4,
        )
    elif operation in {"inspect-population-v1", "inspect"}:
        arguments.update(pool="alpha", identities=dict(ROLES))
    elif operation in {"cleanup", "retain"}:
        arguments["pool"] = "alpha"
        if operation == "retain":
            arguments["reason"] = "interrupted"
    arguments.update(changes)
    result: dict[str, object] = {
        "operation": operation,
        "arguments": arguments,
        "expected_identity": dict(IDENTITY),
    }
    if operation in {"allocate", "heartbeat", "quarantine", "release"}:
        result["pool"] = "alpha"
    return result


def channel_for(operation: str) -> str:
    if operation in {"allocate", "heartbeat", "quarantine", "release"}:
        return "pool"
    if operation in {"inspect-population-v1", "inspect"}:
        return "inspection"
    return "fixture"


class Relay:
    """The external privileged relay boundary, with complete literal wire ACKs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.answers: dict[str, tuple[str, dict[str, object]] | Exception] = {}
        self.held: set[str] = set()
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.settled = asyncio.Event()
        self.cancelled = False

    async def dispatch(
        self, channel: str, request: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        self.calls.append((channel, deepcopy(request)))
        operation = cast(str, request["operation"])
        if operation in self.held:
            self.started.set()
            try:
                await self.finish.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        answer = (
            self.answers[operation]
            if operation in self.answers
            else ("PASS", deepcopy(ACKS[operation]))
        )
        self.settled.set()
        if isinstance(answer, Exception):
            raise answer
        return answer


async def call(
    session: BridgeSession, operation: str, **changes: object
) -> dict[str, object]:
    return await session.request(channel_for(operation), envelope(operation, **changes))


def assert_rejected(reply: dict[str, object]) -> None:
    assert set(reply) == {"result", "data"}
    assert reply["result"] != "PASS"
    assert SENTINEL not in json.dumps(reply)


async def advance(session: BridgeSession, phase: str) -> None:
    if phase in {"allocated", "provisioned"}:
        assert (await call(session, "allocate"))["result"] == "PASS"
    if phase == "provisioned":
        assert (await call(session, "provision"))["result"] == "PASS"


async def wire(
    directory: Path, listener: str, value: dict[str, object]
) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(str(directory / listener))
    try:
        writer.write(encode_frame(value))
        await writer.drain()
        return decode_frame(await asyncio.wait_for(reader.readline(), 1))
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.parametrize("recovery", ["cleanup", "retain", "quarantine"])
def test_exact_lifecycle_releases_only_after_complete_acknowledged_recovery(
    recovery: str,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            assert await call(session, "retained_counts") == {
                "result": "PASS",
                "data": {"retained": 0, "unfinished": 0},
            }
            assert_rejected(await call(session, "retained_counts"))
            allocation = envelope("allocate")
            if recovery == "cleanup":
                allocation["expected_identity"] = dict(reversed(list(IDENTITY.items())))
            assert await session.request("pool", allocation) == {
                "result": "PASS",
                "data": {"indexes": INDEXES},
            }
            assert_rejected(await call(session, "retained_counts"))
            assert await call(session, "heartbeat") == {
                "result": "PASS",
                "data": {"extended": 6},
            }
            assert await call(session, "provision") == {
                "result": "PASS",
                "data": ACKS["provision"],
            }
            inspection = envelope("inspect-population-v1")
            if recovery == "cleanup":
                section(inspection, "arguments")["identities"] = dict(
                    reversed(list(ROLES.items()))
                )
            assert await session.request("inspection", inspection) == {
                "result": "PASS",
                "data": ACKS["inspect-population-v1"],
            }
            before = len(relay.calls)
            assert_rejected(await call(session, "release"))
            assert len(relay.calls) == before
            if recovery == "quarantine":
                for index in INDEXES[:-1]:
                    assert (await call(session, "quarantine", index=index))[
                        "result"
                    ] == "PASS"
                before = len(relay.calls)
                assert_rejected(await call(session, "release"))
                assert_rejected(await call(session, "quarantine", index=17))
                assert len(relay.calls) == before
                assert (await call(session, "quarantine", index=43))["result"] == "PASS"
            else:
                recovery_ack: dict[str, object] = ACKS[recovery]
                if recovery == "retain":
                    # Backend retain reports live leases it quarantines, not
                    # the already-quarantined part of the allocation.
                    assert (await call(session, "quarantine", index=17))[
                        "result"
                    ] == "PASS"
                    recovery_ack = {"quarantined": 5}
                    relay.answers["retain"] = ("PASS", recovery_ack)
                assert await call(session, recovery) == {
                    "result": "PASS",
                    "data": recovery_ack,
                }
            # Retain and quarantine clear their leases; live cleanup leaves
            # leases for release. The returned count is not allocation size.
            released = 6 if recovery == "cleanup" else 0
            relay.answers["release"] = ("PASS", {"released": released})
            assert await call(session, "release") == {
                "result": "PASS",
                "data": {"released": released},
            }
            before = len(relay.calls)
            for op in ("allocate", "provision", "heartbeat", "cleanup", "release"):
                assert_rejected(await call(session, op))
            assert len(relay.calls) == before
            assert session.health() == {"run_id": RUN, "live": False}
            assert relay.calls[:5] == [
                ("fixture", envelope("retained_counts")),
                ("pool", envelope("allocate")),
                ("pool", envelope("heartbeat")),
                ("fixture", envelope("provision")),
                ("inspection", envelope("inspect-population-v1")),
            ]
        finally:
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("quarantined", "released", "accepted"),
    [(0, 6, True), (1, 5, True), (6, 0, True), (0, 7, False), (0, True, False)],
)
def test_release_accepts_remaining_lease_counts_but_rejects_invalid_acknowledgement(
    quarantined: int,
    released: object,
    accepted: bool,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            await advance(session, "allocated")
            for index in INDEXES[:quarantined]:
                assert (await call(session, "quarantine", index=index))[
                    "result"
                ] == "PASS"
            relay.answers["release"] = ("PASS", {"released": released})
            response = await call(session, "release")
            if accepted:
                assert response == {"result": "PASS", "data": {"released": released}}
                assert session.health() == {"run_id": RUN, "live": False}
            else:
                assert_rejected(response)
            assert relay.calls[-1] == ("pool", envelope("release"))
        finally:
            session.close()

    asyncio.run(execute())


AUTHORITY_CASES = [
    ("initial", "allocate", "channel", "channel", "arbitrary"),
    ("initial", "allocate", "pool", "pool", "other"),
    (
        "initial",
        "allocate",
        "arguments",
        "run_id",
        "66666666-6666-4666-8666-666666666666",
    ),
    ("initial", "allocate", "arguments", "count", 7),
    ("initial", "allocate", "arguments", "count", True),
    ("initial", "allocate", "arguments", "ttl_seconds", 1801),
    ("initial", "allocate", "arguments", SENTINEL, "$(unsafe)"),
    ("initial", "allocate", "pool", "operation", "register"),
    ("initial", "allocate", "pool", "expected_identity", None),
    ("initial", "allocate", "pool", "phase", "finalization"),
    ("initial", "provision", "arguments", "pool", "alpha"),
    ("allocated", "quarantine", "arguments", "index", 99),
    ("allocated", "provision", "arguments", "owners", [23, 17]),
    ("allocated", "provision", "arguments", "catchers", [31, 37, 41, 99]),
    ("allocated", "provision", "arguments", "extras", [99]),
    ("allocated", "provision", "arguments", "fursuits_per_owner", 3),
    ("allocated", "inspect-population-v1", "arguments", "identities", ROLES),
    (
        "provisioned",
        "inspect-population-v1",
        "arguments",
        "identities",
        {**ROLES, "owner0": 31, "attendee0": 17},
    ),
    ("provisioned", "inspect-population-v1", "pool", "operation", "inspect"),
    ("provisioned", "retain", "arguments", "reason", SENTINEL),
    ("provisioned", "retain", "arguments", "reason", "unfinished"),
    ("provisioned", "cleanup", "arguments", "pool", "other"),
]


@pytest.mark.parametrize(
    ("phase", "operation", "where", "key", "value"), AUTHORITY_CASES
)
def test_wrong_authority_never_reaches_privileged_relay(
    phase: str,
    operation: str,
    where: str,
    key: str,
    value: object,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            await advance(session, phase)
            request = envelope(operation)
            target = section(request, "arguments") if where == "arguments" else request
            if where != "channel":
                target[key] = value
            before = len(relay.calls)
            channel = cast(str, value) if where == "channel" else channel_for(operation)
            assert_rejected(await session.request(channel, request))
            assert len(relay.calls) == before
            if (
                key == "pool"
                and value == "other"
                or key == "run_id"
                or key in {"owners", "catchers", "extras"}
                or key == "identities"
                and phase == "provisioned"
            ):
                # These are well-formed authority mismatches, distinct from
                # generic malformed input: matching retries cannot reopen it.
                assert_rejected(await call(session, operation))
                assert len(relay.calls) == before
                assert session.health() == {"run_id": RUN, "live": False}
            elif key == "reason":
                # A rejected reason must not consume terminal authority. The
                # backend's mutating REASONS excludes listed-status unfinished.
                assert await call(session, "retain") == {
                    "result": "PASS",
                    "data": {"quarantined": 6},
                }
                assert relay.calls[before:] == [("fixture", envelope("retain"))]
        finally:
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize("operation", ["allocate", "provision"])
def test_concurrent_replay_and_caller_cancellation_never_repeat_one_attempt(
    operation: str,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        if operation == "provision":
            await advance(session, "allocated")
        relay.held.add(operation)
        relay.settled.clear()
        first = asyncio.create_task(call(session, operation))
        try:
            await asyncio.wait_for(relay.started.wait(), 1)
            assert_rejected(await asyncio.wait_for(call(session, operation), 0.5))
            changed = envelope(operation)
            section(changed, "arguments")["run_id"] = (
                "66666666-6666-4666-8666-666666666666"
            )
            assert_rejected(await session.request(channel_for(operation), changed))
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
            assert not relay.cancelled
            relay.finish.set()
            await asyncio.wait_for(relay.settled.wait(), 1)
            await asyncio.sleep(0)
            assert_rejected(await call(session, operation))
            assert sum(req["operation"] == operation for _, req in relay.calls) == 1
            assert not relay.cancelled
        finally:
            relay.finish.set()
            session.close()
            if not first.done():
                first.cancel()
            await asyncio.gather(first, return_exceptions=True)

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("mutation", "outcome"),
    [
        ("provision", "PASS"),
        ("heartbeat", "FAIL_LAUNCHER"),
        ("heartbeat", "FAIL_ERROR"),
        ("heartbeat", "FAIL_BOOTSTRAP"),
        ("heartbeat", "exception"),
        ("heartbeat", "malformed"),
    ],
)
def test_pending_mutation_settles_before_terminal_recovery_and_release(
    mutation: str, outcome: str
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        await advance(
            session, "provisioned" if mutation == "heartbeat" else "allocated"
        )
        relay.held.add(mutation)
        if outcome == "exception":
            relay.answers[mutation] = RuntimeError(SENTINEL)
        elif outcome == "malformed":
            relay.answers[mutation] = ("PASS", {"extended": True})
        elif outcome != "PASS":
            relay.answers[mutation] = (outcome, {})
        pending = asyncio.create_task(call(session, mutation))
        recovery = "cleanup" if mutation == "heartbeat" else "retain"
        terminal: asyncio.Task[dict[str, object]] | None = None
        try:
            await asyncio.wait_for(relay.started.wait(), 1)
            if mutation == "heartbeat":
                session.revoke_workload()
                assert_rejected(await asyncio.wait_for(call(session, "heartbeat"), 0.5))
            before = [req["operation"] for _, req in relay.calls]
            terminal = asyncio.create_task(call(session, recovery))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert [req["operation"] for _, req in relay.calls] == before
            assert not terminal.done()
            relay.finish.set()
            response = await asyncio.wait_for(pending, 1)
            if outcome == "PASS":
                assert response["result"] == "PASS"
            else:
                assert_rejected(response)
            assert (await asyncio.wait_for(terminal, 1))["result"] == "PASS"
            relay.answers["release"] = (
                "PASS",
                {"released": 6 if recovery == "cleanup" else 0},
            )
            assert (await call(session, "release"))["result"] == "PASS"
            assert [req["operation"] for _, req in relay.calls] == before + [
                recovery,
                "release",
            ]
            assert session.receipt()["disposition"] == "released"
            assert not relay.cancelled
            assert SENTINEL not in json.dumps(session.evidence())
        finally:
            relay.finish.set()
            session.close()
            await asyncio.gather(
                pending, *([terminal] if terminal else []), return_exceptions=True
            )

    asyncio.run(execute())


@pytest.mark.parametrize("outcome", ["lost", "exception", "malformed"])
def test_indeterminate_provision_cannot_be_replayed_or_released(outcome: str) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            await advance(session, "allocated")
            relay.answers["provision"] = {
                "lost": ("FAIL_LAUNCHER", {}),
                "exception": RuntimeError(SENTINEL),
                "malformed": ("PASS", {**ACKS["provision"], SENTINEL: 1}),
            }[outcome]
            assert_rejected(await call(session, "provision"))
            before = len(relay.calls)
            for op in (
                "provision",
                "inspect-population-v1",
                "cleanup",
                "retain",
                "release",
            ):
                assert_rejected(await asyncio.wait_for(call(session, op), 0.5))
            assert len(relay.calls) == before
            assert SENTINEL not in json.dumps(session.evidence(), allow_nan=False)
            assert len(json.dumps(session.evidence())) < 65536
        finally:
            session.close()

    asyncio.run(execute())


BAD_ACKS: list[tuple[str, str, tuple[str, dict[str, object]]]] = [
    ("initial", "allocate", ("PASS", {"indexes": [17, 17, 31, 37, 41, 43]})),
    ("initial", "allocate", ("PASS", {"indexes": [True, 23, 31, 37, 41, 43]})),
    ("allocated", "provision", ("PASS", {**ACKS["provision"], "enrollment": True})),
    ("provisioned", "cleanup", ("PASS", {"convention": 1})),
    ("provisioned", "retain", ("PASS", {"quarantined": -1})),
    (
        "provisioned",
        "inspect-population-v1",
        ("PASS", {**ACKS["inspect-population-v1"], SENTINEL: 1}),
    ),
    ("allocated", "heartbeat", ("FAIL_" + SENTINEL, {SENTINEL: 1})),
]


@pytest.mark.parametrize(("phase", "operation", "answer"), BAD_ACKS)
def test_malformed_relay_acknowledgements_cannot_grant_authority_or_leak(
    phase: str,
    operation: str,
    answer: tuple[str, dict[str, object]],
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            await advance(session, phase)
            relay.answers[operation] = answer
            assert_rejected(await call(session, operation))
            assert SENTINEL not in json.dumps(session.evidence(), allow_nan=False)
            before = len(relay.calls)
            if operation == "allocate":
                assert_rejected(await call(session, "provision"))
            elif operation == "provision":
                assert_rejected(await call(session, "inspect-population-v1"))
            elif operation in {"cleanup", "retain"}:
                assert_rejected(await call(session, "release"))
            assert len(relay.calls) == before
        finally:
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize("source", ["caller", "relay", "heartbeat", "terminal"])
def test_target_veto_or_terminal_entry_never_reopens_authority(
    source: str,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        try:
            if source == "terminal":
                await advance(session, "provisioned")
                relay.answers["cleanup"] = ("FAIL_ATTRIBUTION", {})
                assert_rejected(await call(session, "cleanup"))
                prohibited = (
                    "allocate",
                    "provision",
                    "inspect-population-v1",
                    "release",
                )
            elif source == "heartbeat":
                await advance(session, "provisioned")
                relay.answers["heartbeat"] = ("FAIL_TARGET", {})
                assert_rejected(await call(session, "heartbeat"))
                prohibited = ("heartbeat", "cleanup", "retain", "release")
            else:
                request = envelope("allocate")
                if source == "caller":
                    section(request, "expected_identity")["source_sha"] = "e" * 40
                else:
                    relay.answers["allocate"] = ("FAIL_TARGET", {})
                assert_rejected(await session.request("pool", request))
                assert len(relay.calls) == (0 if source == "caller" else 1)
                prohibited = (
                    "allocate",
                    "retained_counts",
                    "heartbeat",
                    "cleanup",
                    "release",
                )
            before = len(relay.calls)
            for op in prohibited:
                assert_rejected(await call(session, op))
            assert len(relay.calls) == before
            if source != "terminal":
                assert session.health() == {"run_id": RUN, "live": False}
        finally:
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize("limit", ["time", "revoke", "close"])
def test_authority_and_dispatch_budget_cannot_be_renewed(limit: str) -> None:
    async def execute() -> None:
        now = [100.0]
        relay = Relay()
        launch = manifest()
        section(launch, "safety").update(seconds=10, final_seconds=5)
        session = BridgeSession(launch, relay.dispatch, clock=lambda: now[0])
        try:
            await advance(session, "allocated")
            assert session.health() == {"run_id": RUN, "live": True}
            if limit == "time":
                now[0] = 109.0
                assert (await call(session, "heartbeat"))["result"] == "PASS"
                assert session.health()["live"] is True
                now[0] = 110.0
                assert session.health()["live"] is False
            elif limit == "revoke":
                session.revoke_workload()
                assert session.health()["live"] is False
            else:
                session.close()
            before = len(relay.calls)
            assert_rejected(await call(session, "heartbeat"))
            assert_rejected(await call(session, "provision"))
            assert len(relay.calls) == before
            if limit in {"time", "revoke"}:
                assert (await call(session, "release"))["result"] == "PASS"
            if limit == "time":
                # A separate session's recovery allowance also has an absolute end.
                other = BridgeSession(launch, relay.dispatch, clock=lambda: now[0])
                await advance(other, "allocated")
                now[0] = 125.0
                before = len(relay.calls)
                assert_rejected(await call(other, "release"))
                assert len(relay.calls) == before
                other.close()
        finally:
            session.close()

    asyncio.run(execute())


def test_two_dispatch_ceiling_keeps_health_responsive_and_rejects_extra_work() -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        await advance(session, "provisioned")
        relay.held.update({"heartbeat", "inspect-population-v1"})
        tasks = [
            asyncio.create_task(call(session, op))
            for op in ("heartbeat", "inspect-population-v1")
        ]
        try:
            await asyncio.wait_for(relay.started.wait(), 1)
            for _ in range(4):
                await asyncio.sleep(0)
            assert len(relay.calls) == 4
            before = len(relay.calls)
            assert_rejected(await asyncio.wait_for(call(session, "heartbeat"), 0.5))
            assert len(relay.calls) == before
            assert session.health() == {"run_id": RUN, "live": True}
        finally:
            relay.finish.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            session.close()

    asyncio.run(execute())


def test_socket_disconnect_does_not_cancel_or_repeat_allocation(
    socket_root: Path,
) -> None:
    async def execute() -> None:
        relay = Relay()
        relay.held.add("allocate")
        session = BridgeSession(manifest(), relay.dispatch)
        directory = socket_root / "bridge"
        server = private_server(session, directory)
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(directory / "rpc.sock"))
        del reader
        request: dict[str, object] = {
            "schema_version": 1,
            "channel": "pool",
            "request": envelope("allocate"),
        }
        try:
            writer.write(encode_frame(request))
            await writer.drain()
            await asyncio.wait_for(relay.started.wait(), 1)
            writer.close()
            await writer.wait_closed()
            assert_rejected(await wire(directory, "rpc.sock", request))
            relay.finish.set()
            await asyncio.wait_for(relay.settled.wait(), 1)
            await asyncio.sleep(0)
            assert_rejected(await wire(directory, "rpc.sock", request))
            assert relay.calls == [("pool", envelope("allocate"))]
            assert not relay.cancelled
        finally:
            relay.finish.set()
            writer.close()
            await writer.wait_closed()
            await server.close()
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize(
    "obstacle", ["none", "directory-symlink", "rpc-file", "health-symlink"]
)
def test_socket_paths_are_private_owned_and_never_replace_foreign_paths(
    socket_root: Path, obstacle: str
) -> None:
    async def execute() -> None:
        directory = socket_root / "bridge"
        foreign = socket_root / "foreign"
        foreign.mkdir()
        marker = foreign / "keep"
        marker.write_text(SENTINEL)
        if obstacle == "directory-symlink":
            directory.symlink_to(foreign, target_is_directory=True)
        elif obstacle in {"rpc-file", "health-symlink"}:
            directory.mkdir(mode=0o700)
            if obstacle == "rpc-file":
                (directory / "rpc.sock").write_text(SENTINEL)
            else:
                (directory / "health.sock").symlink_to(marker)
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        server = private_server(session, directory)
        try:
            if obstacle == "none":
                await server.start()
                assert stat.S_IMODE(directory.stat().st_mode) == 0o700
                for name in ("rpc.sock", "health.sock"):
                    assert stat.S_ISSOCK((directory / name).stat().st_mode)
                    assert stat.S_IMODE((directory / name).stat().st_mode) & 0o077 == 0
                (directory / "unrelated").write_text("keep")
                await server.close()
                assert (directory / "unrelated").read_text() == "keep"
                assert not (directory / "rpc.sock").exists()
                assert not (directory / "health.sock").exists()
            else:
                with pytest.raises((ValueError, OSError)):
                    await server.start()
                if obstacle == "directory-symlink":
                    assert directory.is_symlink()
                elif obstacle == "rpc-file":
                    assert (directory / "rpc.sock").read_text() == SENTINEL
                else:
                    assert (directory / "health.sock").is_symlink()
            assert marker.read_text() == SENTINEL
            assert relay.calls == []
        finally:
            await server.close()
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize(
    "case",
    [
        "none",
        "replaced-before-close",
        "ancestor-symlink",
        "health-parent-mode",
        "missing-parent",
        "health-path-exists",
    ],
)
def test_explicit_socket_paths_are_validated_private_and_unlinked_only_when_owned(
    socket_root: Path, case: str
) -> None:
    """#316 C3: local mode binds `runs/<UUID>/rpc` and `control` directories separately."""

    async def execute() -> None:
        # /tmp is itself a symlink on macOS; the contract forbids any link in the path.
        socket_root_real = socket_root.resolve()
        rpc_dir, health_dir = socket_root_real / "rpc", socket_root_real / "control"
        rpc_dir.mkdir(mode=0o700)
        health_dir.mkdir(mode=0o700)
        foreign = socket_root_real / "foreign"
        foreign.mkdir()
        marker = foreign / "keep"
        marker.write_text(SENTINEL)
        rpc_path, health_path = rpc_dir / "rpc.sock", health_dir / "health.sock"
        if case == "ancestor-symlink":
            # The parent itself is a private real directory; only the link above it is wrong.
            (foreign / "rpc").mkdir(mode=0o700)
            (socket_root_real / "link").symlink_to(foreign, target_is_directory=True)
            rpc_path = socket_root_real / "link" / "rpc" / "rpc.sock"
        elif case == "health-parent-mode":
            health_dir.chmod(0o755)
        elif case == "missing-parent":
            rpc_dir.rmdir()
        elif case == "health-path-exists":
            health_path.write_text(SENTINEL)
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        server = BridgeServer.for_paths(session, rpc_path, health_path)
        previous = os.umask(0)  # the server must not depend on the caller's umask
        try:
            if case in {"none", "replaced-before-close"}:
                await server.start()
                for path in (rpc_path, health_path):
                    assert stat.S_ISSOCK(path.stat().st_mode)
                    assert stat.S_IMODE(path.stat().st_mode) == 0o600
                assert await wire(rpc_dir, "rpc.sock", envelope_frame()) == {
                    "result": "PASS",
                    "data": {"retained": 0, "unfinished": 0},
                }
                assert await wire(
                    health_dir,
                    "health.sock",
                    {"schema_version": 1, "channel": "health", "run_id": RUN},
                ) == {"run_id": RUN, "live": True}
                if case == "replaced-before-close":
                    rpc_path.unlink()
                    rpc_path.write_text(SENTINEL)
                await server.close()
                assert not health_path.exists()
                assert rpc_path.exists() == (case == "replaced-before-close")
                if case == "replaced-before-close":
                    assert rpc_path.read_text() == SENTINEL
            else:
                with pytest.raises((ValueError, OSError)):
                    await server.start()
                assert not any(
                    p.is_socket() for p in (rpc_path, health_path) if p.exists()
                )
                if case == "missing-parent":
                    assert not rpc_dir.exists()  # prepare owns directory creation
                if case == "health-path-exists":
                    assert health_path.read_text() == SENTINEL
                    assert not rpc_path.exists()
                if case == "ancestor-symlink":
                    assert list((foreign / "rpc").iterdir()) == []
            assert marker.read_text() == SENTINEL
        finally:
            os.umask(previous)
            await server.close()
            session.close()

    asyncio.run(execute())


def envelope_frame() -> dict[str, object]:
    return {
        "schema_version": 1,
        "channel": "fixture",
        "request": envelope("retained_counts"),
    }


def test_relay_dispatch_runs_the_given_task_in_the_workspace_with_exactly_the_given_env(
    socket_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#316 C2: the relay never derives its root from this module's file location."""
    workspace = socket_root / "workspace"
    task = socket_root / "tools" / "bin" / "task"
    task.parent.mkdir(parents=True)
    workspace.mkdir()
    task.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "print(json.dumps({'result': 'PASS', 'data': {'argv': sys.argv, 'cwd': os.getcwd(),\n"
        "    'env': dict(os.environ), 'stdin': sys.stdin.read()}}))\n"
    )
    task.chmod(0o700)
    environment = {
        "PATH": f"{task.parent}:/usr/bin:/bin",
        "UV": "/srv/tools/uv",
        "RAILWAY_NO_AUTO_UPDATE": "1",
        "HOME": str(socket_root),
    }
    monkeypatch.setenv("TT316_INHERITED_SENTINEL", "leak")
    request: dict[str, object] = {
        "channel": "inspection",
        "request": {"operation": "x"},
    }

    result, data = asyncio.run(
        host_bridge.relay_dispatch(workspace, task, environment)("inspection", request)
    )

    assert result == "PASS"
    assert data["argv"] == [str(task), "-s", "api-sim-inspect-ssh"]
    assert Path(cast(str, data["cwd"])).resolve() == workspace.resolve()
    assert data["stdin"] == encode_frame(request).decode()
    actual = cast(dict[str, str], data["env"])
    assert {k: v for k, v in actual.items() if k in environment} == environment
    # Interpreters may add locale/CoreFoundation keys; nothing else may be inherited.
    assert set(actual) - set(environment) <= {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}


def test_slow_rpc_admission_is_bounded_independent_of_health_and_expires(
    socket_root: Path,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        directory = socket_root / "bridge"
        server = private_server(session, directory)
        connections: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []
        await server.start()
        try:
            for _ in range(10):
                reader, writer = await asyncio.open_unix_connection(
                    str(directory / "rpc.sock")
                )
                connections.append((reader, writer))
                writer.write(b'{"schema_version":')
                await writer.drain()
            health: dict[str, object] = {
                "schema_version": 1,
                "channel": "health",
                "run_id": RUN,
            }
            slow_health: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []
            for position in range(2):
                reader, writer = await asyncio.open_unix_connection(
                    str(directory / "health.sock")
                )
                slow_health.append((reader, writer))
                connections.append((reader, writer))
                writer.write(b'{"schema_version":')
                await writer.drain()
                if position == 0:
                    assert await wire(directory, "health.sock", health) == {
                        "run_id": RUN,
                        "live": True,
                    }
            (
                health_overflow_reader,
                health_overflow_writer,
            ) = await asyncio.open_unix_connection(str(directory / "health.sock"))
            connections.append((health_overflow_reader, health_overflow_writer))
            health_overflow = await asyncio.wait_for(
                health_overflow_reader.readline(), 0.5
            )
            if health_overflow:
                assert_rejected(decode_frame(health_overflow))
            overflow_reader, overflow_writer = await asyncio.open_unix_connection(
                str(directory / "rpc.sock")
            )
            connections.append((overflow_reader, overflow_writer))
            # Excess admission closes or returns a fixed rejection without waiting
            # for a frame; neither behavior admits another expensive relay.
            overflow = await asyncio.wait_for(overflow_reader.readline(), 0.5)
            if overflow:
                assert_rejected(decode_frame(overflow))
            for reader, _ in [*connections[:10], *slow_health]:
                expired = await asyncio.wait_for(reader.readline(), 2.7)
                if expired:
                    assert_rejected(decode_frame(expired))
            assert await wire(
                directory,
                "rpc.sock",
                {
                    "schema_version": 1,
                    "channel": "fixture",
                    "request": envelope("retained_counts"),
                },
            ) == {
                "result": "PASS",
                "data": {"retained": 0, "unfinished": 0},
            }
            assert relay.calls == [("fixture", envelope("retained_counts"))]
            assert await wire(directory, "health.sock", health) == {
                "run_id": RUN,
                "live": True,
            }
        finally:
            for _, writer in connections:
                writer.close()
            await asyncio.gather(
                *(writer.wait_closed() for _, writer in connections),
                return_exceptions=True,
            )
            await server.close()
            session.close()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("listener", "raw"),
    [
        (
            "rpc.sock",
            encode_frame(
                {
                    "schema_version": True,
                    "channel": "fixture",
                    "request": envelope("retained_counts"),
                }
            ),
        ),
        (
            "rpc.sock",
            encode_frame(
                {
                    "schema_version": 1,
                    "channel": "fixture",
                    "request": envelope("retained_counts"),
                    SENTINEL: 1,
                }
            ),
        ),
        (
            "rpc.sock",
            encode_frame({"schema_version": 1, "channel": "health", "run_id": RUN}),
        ),
        (
            "health.sock",
            encode_frame(
                {
                    "schema_version": 1,
                    "channel": "fixture",
                    "request": envelope("retained_counts"),
                }
            ),
        ),
        (
            "health.sock",
            encode_frame(
                {
                    "schema_version": 1,
                    "channel": "health",
                    "run_id": "66666666-6666-4666-8666-666666666666",
                }
            ),
        ),
        ("rpc.sock", b'{"x":1,"x":2}\n'),
        ("rpc.sock", b"x" * 65537 + b"\n"),
    ],
)
def test_invalid_socket_frames_never_dispatch_or_echo_input(
    socket_root: Path, listener: str, raw: bytes
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        directory = socket_root / "bridge"
        server = private_server(session, directory)
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(directory / listener))
        try:
            writer.write(raw)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(65537), 1)
            assert len(response) <= 65536
            assert SENTINEL.encode() not in response
            if response:
                assert_rejected(decode_frame(response))
            assert relay.calls == []
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()
            session.close()

    asyncio.run(execute())


HEALTH_FRAME: dict[str, object] = {
    "schema_version": 1,
    "channel": "health",
    "run_id": RUN,
}
HEALTH_COUNTERS = {
    "accepted",
    "refused_at_capacity",
    "replied_live",
    "replied_not_live",
    "invalid",
    "write_failed",
    "close_timeouts",
    "peak_active",
}


def health_counters(**counts: int) -> dict[str, int]:
    assert set(counts) <= HEALTH_COUNTERS
    return {key: counts.get(key, 0) for key in sorted(HEALTH_COUNTERS)}


async def settled_health(
    session: BridgeSession, expected: dict[str, int], *, peak: set[int]
) -> None:
    """Exact closed counters once handlers finish their bookkeeping.

    Sequential connections may overlap their final close, so callers that cannot
    pin concurrency pass the admissible peak values instead of an exact one.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 1
    while True:
        counters = cast(dict[str, int], session.evidence()["health"])
        if (
            {k: v for k, v in counters.items() if k != "peak_active"}
            == {k: v for k, v in expected.items() if k != "peak_active"}
            and counters["peak_active"] in peak
        ) or loop.time() >= deadline:
            break
        await asyncio.sleep(0.01)
    assert {k: v for k, v in counters.items() if k != "peak_active"} == {
        k: v for k, v in expected.items() if k != "peak_active"
    }
    assert set(counters) == HEALTH_COUNTERS
    assert counters["peak_active"] in peak


def test_unfinished_health_close_is_bounded_and_never_pins_capacity(
    socket_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #230: wait_closed is the provider/transport boundary. Two accepted handlers
    # never complete their close; each slot must still come back after the bound.
    original = asyncio.StreamWriter.wait_closed
    unfinished = [2]

    async def wait_closed(self: asyncio.StreamWriter) -> None:
        if unfinished[0] and self.get_extra_info("sockname"):  # accepted side only
            unfinished[0] -= 1
            await asyncio.Event().wait()
        await original(self)

    monkeypatch.setattr(asyncio.StreamWriter, "wait_closed", wait_closed)

    async def execute() -> None:
        session = BridgeSession(manifest(), Relay().dispatch)
        directory = socket_root / "bridge"
        server = private_server(session, directory)
        await server.start()
        writers: list[asyncio.StreamWriter] = []

        async def ask() -> bytes:
            reader, writer = await asyncio.open_unix_connection(
                str(directory / "health.sock")
            )
            writers.append(writer)
            try:
                writer.write(encode_frame(HEALTH_FRAME))
                await writer.drain()
            except OSError:
                pass
            try:
                return await asyncio.wait_for(reader.read(), 1)
            except ConnectionResetError:
                # Linux resets a refused socket with unread input; macOS sends EOF.
                return b""

        try:
            live = {"run_id": RUN, "live": True}
            for _ in range(2):
                assert decode_frame(await ask()) == live
            # Both slots are in the unfinished close: the third is closed unanswered.
            assert await ask() == b""
            await asyncio.sleep(2.5)  # past the 2 s close bound
            reply = await ask()
            assert reply, "a health slot stayed pinned past the close bound"
            assert decode_frame(reply) == live
            await settled_health(
                session,
                health_counters(
                    accepted=3,
                    refused_at_capacity=1,
                    replied_live=3,
                    close_timeouts=2,
                ),
                peak={2},
            )
            assert session.evidence()["revocation"] is None
        finally:
            for writer in writers:
                writer.close()
            await server.close()
            session.close()

    asyncio.run(execute())


def test_health_evidence_is_closed_and_counts_live_not_live_and_invalid(
    socket_root: Path,
) -> None:
    async def execute() -> None:
        now = [100.0]
        launch = manifest()
        section(launch, "safety").update(seconds=10, final_seconds=5)
        session = BridgeSession(launch, Relay().dispatch, clock=lambda: now[0])
        directory = socket_root / "bridge"
        server = private_server(session, directory)
        await server.start()
        try:
            evidence = session.evidence()
            assert set(evidence) == {
                "schema_version",
                "run_id",
                "backend_identity",
                "disposition",
                "dispatches",
                "attempts",
                "outcomes",
                "allocation_acknowledged",
                "provision_acknowledged",
                "release_acknowledged",
                "pending_mutations",
                "may_have_committed",
                "target_veto",
                "recovery_hold",
                "health",
                "heartbeat",
                "revocation",
            }
            assert evidence["health"] == health_counters()
            assert evidence["heartbeat"] == {"failed": 0, "failure_offsets": []}
            assert evidence["revocation"] is None

            assert await wire(directory, "health.sock", HEALTH_FRAME) == {
                "run_id": RUN,
                "live": True,
            }
            reader, writer = await asyncio.open_unix_connection(
                str(directory / "health.sock")
            )
            writer.write(encode_frame({**HEALTH_FRAME, "run_id": SENTINEL}))
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""
            writer.close()
            now[0] = 110.0  # the execution window has ended
            assert await wire(directory, "health.sock", HEALTH_FRAME) == {
                "run_id": RUN,
                "live": False,
            }
            await settled_health(
                session,
                health_counters(
                    accepted=3, replied_live=1, replied_not_live=1, invalid=1
                ),
                peak={1, 2},
            )
            assert SENTINEL not in json.dumps(session.evidence())
            assert session.evidence()["revocation"] is None
        finally:
            await server.close()
            session.close()

    asyncio.run(execute())


# #230 U2: journeys partition, `inspect` and the expiration-tier heartbeat budget.
JOURNEY_INDEXES = [17, 23, 31, 37, 41, 43, 47]
JOURNEY_ROLES = {
    "owner0": 17,
    "owner1": 23,
    "catcher0": 31,
    "catcher1": 37,
    "catcher2": 41,
    "catcher3": 43,
    "outsider": 47,
}
JOURNEY_PROVISION: dict[str, object] = {
    "owners": [17, 23],
    "catchers": [31, 37, 41, 43],
    "extras": [47],
    "fursuits_per_owner": 2,
}
JOURNEY_ACK = {"convention": 1, "enrollment": 6, "fursuit": 4, "activation": 4}
CATCH_ROW: dict[str, object] = {
    "id": 5,
    "fursuit": 101,
    "catcher": 31,
    "fursuit_owner": 17,
    "run_convention": True,
    "provenance": True,
    "in_window": True,
    "caught_at": "2026-10-10T12:00:00.123456Z",
}
JOURNEY_INSPECTION: dict[str, object] = {
    "catches": [CATCH_ROW],
    "fursuits": [{"id": 101, "owner": 17}],
    "fixture_photos_unchanged": True,
    "avatars": [17],
}


def journeys_relay() -> Relay:
    relay = Relay()
    relay.answers.update(
        allocate=("PASS", {"indexes": JOURNEY_INDEXES}),
        heartbeat=("PASS", {"extended": 7}),
        provision=("PASS", dict(JOURNEY_ACK)),
        inspect=("PASS", deepcopy(JOURNEY_INSPECTION)),
    )
    return relay


async def journeys_session(relay: Relay, *, provisioned: bool) -> BridgeSession:
    session = BridgeSession(journeys_manifest(), relay.dispatch)
    assert (await call(session, "allocate", count=7))["result"] == "PASS"
    if provisioned:
        reply = await call(session, "provision", **JOURNEY_PROVISION)
        assert reply == {"result": "PASS", "data": JOURNEY_ACK}
    return session


def test_journeys_session_grants_only_the_fixed_seven_role_partition() -> None:
    async def execute() -> None:
        relay = journeys_relay()
        session = await journeys_session(relay, provisioned=True)
        try:
            assert await call(session, "inspect", identities=JOURNEY_ROLES) == {
                "result": "PASS",
                "data": JOURNEY_INSPECTION,
            }
            provision_call = next(
                req for _, req in relay.calls if req["operation"] == "provision"
            )
            assert section(provision_call, "arguments") == {
                "run_id": RUN,
                "pool": "alpha",
                **JOURNEY_PROVISION,
            }
        finally:
            session.close()

    asyncio.run(execute())


WRONG_PARTITIONS: list[dict[str, object]] = [
    {"owners": [17, 23, 31], "catchers": [37, 41, 43]},
    {"owners": [23, 17]},
    {"owners": [31, 37], "catchers": [17, 23, 41, 43]},
    {"extras": []},
    {"extras": [43], "catchers": [31, 37, 41, 47]},
    {"fursuits_per_owner": 4},
]


@pytest.mark.parametrize("change", WRONG_PARTITIONS)
def test_journeys_provision_outside_the_partition_never_reaches_the_relay(
    change: dict[str, object],
) -> None:
    async def execute() -> None:
        relay = journeys_relay()
        session = await journeys_session(relay, provisioned=False)
        try:
            before = len(relay.calls)
            wrong = {**JOURNEY_PROVISION, **change}
            assert_rejected(await call(session, "provision", **wrong))
            assert len(relay.calls) == before
            assert session.health() == {"run_id": RUN, "live": False}
        finally:
            session.close()

    asyncio.run(execute())


def test_journeys_provision_acknowledgement_must_be_the_fixed_counts() -> None:
    async def execute() -> None:
        relay = journeys_relay()
        # The convention formula would count seven enrollments and eight fursuits.
        relay.answers["provision"] = (
            "PASS",
            {"convention": 1, "enrollment": 7, "fursuit": 4, "activation": 4},
        )
        session = BridgeSession(journeys_manifest(), relay.dispatch)
        try:
            assert (await call(session, "allocate", count=7))["result"] == "PASS"
            assert_rejected(await call(session, "provision", **JOURNEY_PROVISION))
            before = len(relay.calls)
            assert_rejected(await call(session, "inspect", identities=JOURNEY_ROLES))
            assert len(relay.calls) == before
        finally:
            session.close()

    asyncio.run(execute())


def test_journeys_inspect_with_the_wrong_role_mapping_is_a_veto() -> None:
    async def execute() -> None:
        relay = journeys_relay()
        session = await journeys_session(relay, provisioned=True)
        try:
            before = len(relay.calls)
            swapped = {**JOURNEY_ROLES, "owner0": 23, "owner1": 17}
            assert_rejected(await call(session, "inspect", identities=swapped))
            assert len(relay.calls) == before
            assert session.health() == {"run_id": RUN, "live": False}
        finally:
            session.close()

    asyncio.run(execute())


def drop(value: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in value.items() if k != key}


BAD_INSPECTIONS: list[dict[str, object]] = [
    {**JOURNEY_INSPECTION, SENTINEL: 1},
    drop(JOURNEY_INSPECTION, "avatars"),
    {**JOURNEY_INSPECTION, "fixture_photos_unchanged": 1},
    {**JOURNEY_INSPECTION, "avatars": [True]},
    {**JOURNEY_INSPECTION, "catches": [drop(CATCH_ROW, "provenance")]},
    {**JOURNEY_INSPECTION, "catches": [{**CATCH_ROW, "caught_at": "yesterday"}]},
    {**JOURNEY_INSPECTION, "fursuits": [{"id": 101, "owner": 17, "x": 1}]},
]


@pytest.mark.parametrize("answer", BAD_INSPECTIONS)
def test_malformed_journeys_inspection_response_is_a_launcher_failure(
    answer: dict[str, object],
) -> None:
    async def execute() -> None:
        relay = journeys_relay()
        relay.answers["inspect"] = ("PASS", answer)
        session = await journeys_session(relay, provisioned=True)
        try:
            reply = await call(session, "inspect", identities=JOURNEY_ROLES)
            assert reply == {"result": "FAIL_LAUNCHER", "data": {}}
            assert SENTINEL not in json.dumps(session.evidence(), allow_nan=False)
        finally:
            session.close()

    asyncio.run(execute())


def test_inspection_operations_are_not_interchangeable_between_scenarios() -> None:
    async def execute() -> None:
        relay = journeys_relay()
        journeys = await journeys_session(relay, provisioned=True)
        convention_relay = Relay()
        convention = BridgeSession(manifest(), convention_relay.dispatch)
        try:
            await advance(convention, "provisioned")
            before = len(relay.calls), len(convention_relay.calls)
            assert_rejected(
                await call(journeys, "inspect-population-v1", identities=JOURNEY_ROLES)
            )
            assert_rejected(await call(convention, "inspect"))
            assert (len(relay.calls), len(convention_relay.calls)) == before
        finally:
            journeys.close()
            convention.close()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("kind", "budget"),
    [("standard", 41), ("journeys", 41), ("expiration", 806)],
)
def test_heartbeat_budget_follows_safety_and_never_consumes_other_operations(
    kind: str, budget: int
) -> None:
    async def execute() -> None:
        relay = journeys_relay()
        launch = {
            "standard": manifest,
            "journeys": journeys_manifest,
            "expiration": expiration_manifest,
        }[kind]()
        count = {"standard": 6, "journeys": 7, "expiration": 2}[kind]
        relay.answers.update(
            allocate=("PASS", {"indexes": JOURNEY_INDEXES[:count]}),
            heartbeat=("PASS", {"extended": count}),
            release=("PASS", {"released": count}),
        )
        session = BridgeSession(launch, relay.dispatch, clock=lambda: 100.0)
        try:
            assert (await call(session, "allocate", count=count))["result"] == "PASS"
            for _ in range(budget):
                assert (await call(session, "heartbeat"))["result"] == "PASS"
            before = len(relay.calls)
            assert_rejected(await call(session, "heartbeat"))
            assert len(relay.calls) == before
            assert (await call(session, "release"))["result"] == "PASS"
        finally:
            session.close()

    asyncio.run(execute())


def test_heartbeat_failures_are_diagnostics_only_with_rounded_capped_offsets() -> None:
    async def execute() -> None:
        now = [100.0]
        # The long expiration tier admits well over 64 heartbeats.
        launch = expiration_manifest()
        relay = Relay()
        relay.answers["allocate"] = ("PASS", {"indexes": INDEXES[:2]})
        session = BridgeSession(launch, relay.dispatch, clock=lambda: now[0])

        async def beat(
            offset: float, answer: tuple[str, dict[str, object]] | Exception
        ):
            now[0] = 100.0 + offset
            relay.answers["heartbeat"] = answer
            return (await call(session, "heartbeat"))["result"]

        passed: tuple[str, dict[str, object]] = ("PASS", {"extended": 2})
        try:
            assert (await call(session, "allocate", count=2))["result"] == "PASS"
            assert await beat(5.0, passed) == "PASS"
            receipt = session.receipt()
            # Any non-PASS dispatch counts: a relay verdict, then a lost relay.
            assert await beat(12.34, ("FAIL_REQUEST", {})) == "FAIL_REQUEST"
            assert await beat(20.06, RuntimeError()) == "FAIL_LAUNCHER"
            assert await beat(25.0, passed) == "PASS"
            for offset in range(30, 98):
                assert await beat(float(offset), ("FAIL_LAUNCHER", {})) != "PASS"
            relay.answers["quarantine"] = ("FAIL_REQUEST", {})
            assert (await call(session, "quarantine"))["result"] == "FAIL_REQUEST"

            evidence = session.evidence()
            # The count is exact; the offsets stop at the first 64.
            assert evidence["heartbeat"] == {
                "failed": 70,
                "failure_offsets": [12.3, 20.1, *[float(o) for o in range(30, 92)]],
            }
            assert session.receipt() == receipt
            assert len(json.dumps(evidence, allow_nan=False)) < 65536
        finally:
            session.close()

    asyncio.run(execute())


def test_heartbeats_never_extend_the_non_heartbeat_operation_cap() -> None:
    async def execute() -> None:
        relay = journeys_relay()
        relay.answers["heartbeat"] = ("PASS", {"extended": 7})
        session = await journeys_session(relay, provisioned=True)
        try:
            for _ in range(10):
                assert (await call(session, "heartbeat"))["result"] == "PASS"
            # allocate and provision used 2 of the 256 non-heartbeat operations.
            for _ in range(254):
                reply = await call(session, "inspect", identities=JOURNEY_ROLES)
                assert reply["result"] == "PASS"
            before = len(relay.calls)
            assert_rejected(await call(session, "inspect", identities=JOURNEY_ROLES))
            assert len(relay.calls) == before
        finally:
            session.close()

    asyncio.run(execute())
