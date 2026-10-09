"""#228 U1: real finite authority/socket state; only provider and time substituted."""

import asyncio
import json
import stat
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
from test_host_protocol import IDENTITY, RUN, SENTINEL, manifest, section

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
        yield Path(directory)


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
    elif operation == "inspect-population-v1":
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
    return "inspection" if operation == "inspect-population-v1" else "fixture"


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
        answer = self.answers.get(operation, ("PASS", deepcopy(ACKS[operation])))
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


def test_pending_provision_settles_before_terminal_mutation_and_release() -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        await advance(session, "allocated")
        relay.held.add("provision")
        provision = asyncio.create_task(call(session, "provision"))
        retain: asyncio.Task[dict[str, object]] | None = None
        try:
            await asyncio.wait_for(relay.started.wait(), 1)
            retain = asyncio.create_task(call(session, "retain"))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert [req["operation"] for _, req in relay.calls] == [
                "allocate",
                "provision",
            ]
            assert not retain.done()
            relay.finish.set()
            assert (await asyncio.wait_for(provision, 1))["result"] == "PASS"
            assert (await asyncio.wait_for(retain, 1))["result"] == "PASS"
            relay.answers["release"] = ("PASS", {"released": 0})
            assert (await call(session, "release"))["result"] == "PASS"
            assert [req["operation"] for _, req in relay.calls] == [
                "allocate",
                "provision",
                "retain",
                "release",
            ]
        finally:
            relay.finish.set()
            session.close()
            await asyncio.gather(
                provision, *([retain] if retain else []), return_exceptions=True
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


@pytest.mark.parametrize("source", ["caller", "relay", "terminal"])
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


@pytest.mark.parametrize("limit", ["time", "revoke", "close", "operations"])
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
            if limit == "operations":
                for _ in range(255):
                    assert (await call(session, "heartbeat"))["result"] == "PASS"
            elif limit == "time":
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
        server = BridgeServer(session, directory)
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
        server = BridgeServer(session, directory)
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


def test_slow_rpc_admission_is_bounded_independent_of_health_and_expires(
    socket_root: Path,
) -> None:
    async def execute() -> None:
        relay = Relay()
        session = BridgeSession(manifest(), relay.dispatch)
        directory = socket_root / "bridge"
        server = BridgeServer(session, directory)
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
        server = BridgeServer(session, directory)
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
