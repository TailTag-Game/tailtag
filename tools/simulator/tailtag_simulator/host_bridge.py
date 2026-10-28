"""Run-scoped maintainer authority and private, independently bounded listeners."""

import asyncio
import json
import math
import os
import re
import stat
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from tailtag_simulator.host_protocol import (
    decode_frame,
    encode_frame,
    validate_manifest,
)
from tailtag_simulator.pool import LAUNCHER_TIMEOUT_SECONDS, run_launcher

RelayDispatch = Callable[
    [str, dict[str, object]], Awaitable[tuple[str, dict[str, object]]]
]
_TARGETS = {
    "pool": "api-sim-pool-ssh",
    "fixture": "api-sim-fixture-ssh",
    "inspection": "api-sim-inspect-ssh",
}
# The replica relays run the pinned Cloud Run jobs instead of Railway SSH (#359).
_REPLICA_TARGETS = {
    "pool": "api-sim-pool-replica",
    "fixture": "api-sim-fixture-replica",
    "inspection": "api-sim-inspect-replica",
}
_MUTATIONS = {
    "allocate",
    "heartbeat",
    "provision",
    "cleanup",
    "retain",
    "quarantine",
    "release",
}
_TERMINAL = {"cleanup", "retain", "quarantine", "release"}
_FAILURES = {
    "FAIL_REQUEST",
    "FAIL_TARGET",
    "FAIL_INSUFFICIENT",
    "FAIL_SLOT",
    "FAIL_BOOTSTRAP",
    "FAIL_RUN_EXISTS",
    "FAIL_LEASE",
    "FAIL_DIRTY",
    "FAIL_INVARIANT",
    "FAIL_ERROR",
    "FAIL_RUN_UNKNOWN",
    "FAIL_ATTRIBUTION",
    "FAIL_STORAGE",
    "FAIL_VERIFY",
    "FAIL_LIMIT",
    "FAIL_LAUNCHER",
}
_UNCERTAIN = {"FAIL_LAUNCHER", "FAIL_BOOTSTRAP", "FAIL_ERROR"}
_REASONS = {"journeys", "reconciliation", "cleanup", "interrupted"}
_REVOCATIONS = {
    "signal_SIGINT",
    "signal_SIGHUP",
    "signal_SIGTERM",
    "child_exit",
    "execution_deadline",
    "terminal_deadline",
    "operator_exit",
}
_HEALTH_COUNTERS = (
    "accepted",
    "refused_at_capacity",
    "replied_live",
    "replied_not_live",
    "invalid",
    "write_failed",
    "close_timeouts",
    "peak_active",
)
_HEARTBEAT_OFFSET_CAP = 64


def _rejected(result: str = "FAIL_REQUEST") -> dict[str, object]:
    return {"result": result, "data": {}}


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError
    return cast(dict[str, object], value)


def _integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _same(left: object, right: object) -> bool:
    # Equality alone treats True as 1, including nested role/index lists.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def relay_dispatch(
    workspace: Path,
    task: Path,
    env: Mapping[str, str] | None,
    target: str = "staging",
) -> Callable[
    [str, dict[str, object]], Coroutine[Any, Any, tuple[str, dict[str, object]]]
]:
    """Trusted argv/cwd/env only; the complete request travels exclusively on stdin."""
    tasks = {"staging": _TARGETS, "replica": _REPLICA_TARGETS}[target]

    async def dispatch(
        channel: str, envelope: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        return await run_launcher(
            [str(task), "-s", tasks[channel]],
            workspace,
            LAUNCHER_TIMEOUT_SECONDS,
            encode_frame(envelope),
            env,
        )

    return dispatch


class BridgeSession:
    def __init__(
        self,
        manifest: dict[str, object],
        dispatch: RelayDispatch,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.manifest = validate_manifest(manifest)
        self._dispatch, self._clock = dispatch, clock
        self._run = cast(str, self.manifest["run_id"])
        self._identity = deepcopy(_dict(self.manifest["backend_identity"]))
        config = _dict(self.manifest["configuration"])
        self._pool = config["pool"]
        self._journeys = self.manifest["scenario_id"] == "journeys"
        if self._journeys:
            # Fixed by journeys.py: 2 owners, 4 catchers and 1 outsider without fixture state.
            self._owners, self._extras, self._count, self._fursuits = 2, 1, 7, 2
        else:
            self._owners = cast(int, config["normal_owners"]) + cast(
                int, config["popular_owners"]
            )
            self._extras = 0
            self._count = self._owners + sum(
                cast(int, config[k])
                for k in ("casual", "active", "heavy", "retry_prone")
            )
            self._fursuits = cast(int, config["fursuits"])
        safety = _dict(self.manifest["safety"])
        self._heartbeat_budget = (
            math.ceil(
                (cast(float, safety["seconds"]) + cast(float, safety["final_seconds"]))
                / 60
            )
            + 16
        )
        self._started = clock()
        self._execution_end = self._started + cast(float, safety["seconds"])
        self._end = self._execution_end + cast(float, safety["final_seconds"])
        self._closed = self._revoked = self._veto = self._terminal = False
        self._attempts: set[str] = set()
        self._indexes: list[int] = []
        self._provisioned = self._recovered = self._released = self._uncertain = False
        self._quarantined: set[int] = set()
        self._outcomes: dict[str, str] = {}
        self._cached: dict[str, dict[str, object]] = {}
        self._tasks: set[asyncio.Task[dict[str, object]]] = set()
        self._mutation: asyncio.Task[dict[str, object]] | None = None
        self._operations = self._heartbeats = 0
        self._mutating_started = False
        # Non-authoritative diagnostics (#230): never read back for decisions.
        self.health_counters = dict.fromkeys(_HEALTH_COUNTERS, 0)
        self._heartbeat_failed = 0
        self._heartbeat_failure_offsets: list[float] = []
        self._revocation: dict[str, object] | None = None

    def health(self) -> dict[str, object]:
        return {
            "run_id": self._run,
            "live": not (self._closed or self._revoked or self._veto)
            and self._clock() < self._execution_end,
        }

    def revoke_workload(self, cause: str = "operator_exit") -> None:
        # Revoke before recording: an unexpected cause must never leave work live.
        self._revoked = True
        if cause not in _REVOCATIONS:
            raise ValueError
        if self._revocation is None:
            self._revocation = {
                "cause": cause,
                "offset_seconds": round(self._clock() - self._started, 1),
            }

    def close(self) -> None:
        # Dispatched operations remain owned until they settle; closing is no rollback.
        self._closed = True

    def receipt(self) -> dict[str, object]:
        disposition = (
            "released"
            if self._released
            else "held"
            if self._mutating_started
            else "no_mutation"
        )
        return {
            "schema_version": 1,
            "run_id": self._run,
            "backend_identity": deepcopy(self._identity),
            "disposition": disposition,
        }

    def evidence(self) -> dict[str, object]:
        """Closed counts/outcomes and receipt; no request, provider detail or secret.

        Attempt/outcome fields retain lost-ACK accounting; pending mutations and
        may_have_committed distinguish settlement holds from acknowledged release.
        """
        return {
            **self.receipt(),
            "dispatches": self._operations,
            "attempts": sorted(self._attempts),
            "outcomes": dict(self._outcomes),
            "allocation_acknowledged": bool(self._indexes),
            "provision_acknowledged": self._provisioned,
            "release_acknowledged": self._released,
            "pending_mutations": int(
                self._mutation is not None and not self._mutation.done()
            ),
            "may_have_committed": self._uncertain,
            "target_veto": self._veto,
            "recovery_hold": self._mutating_started and not self._released,
            "health": dict(self.health_counters),
            "heartbeat": {
                "failed": self._heartbeat_failed,
                "failure_offsets": list(self._heartbeat_failure_offsets),
            },
            "revocation": None if self._revocation is None else dict(self._revocation),
        }

    def _envelope(
        self, channel: str, envelope: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        op = envelope.get("operation")
        if not isinstance(op, str):
            raise TypeError
        expected_channel = (
            "pool"
            if op in {"allocate", "heartbeat", "quarantine", "release"}
            else "inspection"
            if op in {"inspect-population-v1", "inspect"}
            else "fixture"
        )
        keys: set[str] = {"operation", "arguments", "expected_identity"} | (
            {"pool"} if expected_channel == "pool" else set[str]()
        )
        if channel != expected_channel or set(envelope) != keys:
            raise ValueError
        if not _same(envelope["expected_identity"], self._identity) or (
            channel == "pool" and envelope["pool"] != self._pool
        ):
            self._veto = True
            raise ValueError
        args = _dict(envelope["arguments"])
        expected: dict[str, object] = {"run_id": self._run}
        if op == "retained_counts":
            expected = {}
        elif op == "allocate":
            expected.update(count=self._count, ttl_seconds=1800)
        elif op == "heartbeat":
            expected["ttl_seconds"] = 1800
        elif op == "quarantine":
            index = args.get("index")
            if not _integer(index):
                raise ValueError
            if index not in self._indexes:
                self._veto = True
                raise ValueError
            if index in self._quarantined or f"quarantine:{index}" in self._attempts:
                raise ValueError
            expected["index"] = index
        elif op == "provision":
            split = self._count - self._extras
            expected.update(
                pool=self._pool,
                owners=self._indexes[: self._owners],
                catchers=self._indexes[self._owners : split],
                extras=self._indexes[split:],
                fursuits_per_owner=self._fursuits,
            )
        elif op == "inspect" and self._journeys:
            names = ["owner0", "owner1", *(f"catcher{i}" for i in range(4)), "outsider"]
            expected.update(
                pool=self._pool, identities=dict(zip(names, self._indexes, strict=True))
            )
        elif op == "inspect-population-v1" and not self._journeys:
            roles = {
                ("owner" + str(i))
                if i < self._owners
                else ("attendee" + str(i - self._owners)): index
                for i, index in enumerate(self._indexes)
            }
            expected.update(pool=self._pool, identities=roles)
        elif op in {"cleanup", "retain"}:
            expected["pool"] = self._pool
            if op == "retain":
                reason = args.get("reason")
                if not isinstance(reason, str) or reason not in _REASONS:
                    raise ValueError
                expected["reason"] = reason
        elif op != "release":
            raise ValueError
        if set(args) != set(expected):
            raise ValueError
        authority_keys = {
            "run_id",
            "pool",
            "owners",
            "catchers",
            "extras",
            "identities",
        }
        if self._journeys:
            # The journeys partition is wholly fixed, so any deviation is authority.
            authority_keys.add("fursuits_per_owner")
        if any(not _same(args[k], expected[k]) for k in authority_keys & set(expected)):
            self._veto = True
            raise ValueError
        if not all(_same(args[k], v) for k, v in expected.items()):
            raise ValueError
        return op, args

    def _allowed(self, op: str) -> bool:
        if (
            self._closed
            or self._veto
            or self._clock() >= self._end
            or (
                self._heartbeats >= self._heartbeat_budget
                if op == "heartbeat"
                else self._operations - self._heartbeats >= 256
            )
        ):
            return False
        if op not in _TERMINAL and (
            self._revoked or self._clock() >= self._execution_end
        ):
            return False
        if op in {"allocate", "retained_counts"}:
            return (
                not self._terminal
                and "allocate" not in self._attempts
                and op not in self._attempts
            )
        if not self._indexes:
            return False
        if op == "provision":
            return not self._terminal and op not in self._attempts
        if op in {"inspect-population-v1", "inspect"}:
            return self._provisioned and not self._terminal
        if op == "heartbeat":
            return not self._terminal
        if op in _TERMINAL:
            if self._uncertain:
                return False
            if op == "release" and "provision" in self._attempts:
                return self._recovered or self._quarantined == set(self._indexes)
            return op not in self._attempts or op == "quarantine"
        return False

    async def request(
        self, channel: str, envelope: dict[str, object]
    ) -> dict[str, object]:
        try:
            # Detach caller values before awaiting or forwarding.
            envelope = decode_frame(encode_frame(envelope))
            op, args = self._envelope(channel, envelope)
        except (ValueError, TypeError, KeyError, RecursionError):
            return _rejected()
        if op in _TERMINAL and self._mutation is not None and not self._mutation.done():
            self._terminal = True
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._mutation), max(0, self._end - self._clock())
                )
            except TimeoutError:
                self._uncertain = True
                return _rejected("FAIL_LAUNCHER")
        if (
            not self._allowed(op)
            or len(self._tasks) >= 2
            or (
                op in _MUTATIONS
                and self._mutation is not None
                and not self._mutation.done()
            )
        ):
            return _rejected()
        if op in _TERMINAL:
            self._terminal = True
        if op in {
            "allocate",
            "provision",
            "retained_counts",
            "cleanup",
            "retain",
            "release",
        }:
            self._attempts.add(op)
        if op == "quarantine":
            self._attempts.add(f"quarantine:{args['index']}")
        self._operations += 1
        self._heartbeats += op == "heartbeat"
        if op in _MUTATIONS:
            self._mutating_started = True
        self._outcomes[op] = "pending"
        task = asyncio.create_task(self._run_dispatch(channel, envelope, op, args))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        if op in _MUTATIONS:
            self._mutation = task
        return await asyncio.shield(task)

    def _ack(self, op: str, data: dict[str, object]) -> bool:
        if op == "allocate":
            indexes = data.get("indexes")
            return (
                set(data) == {"indexes"}
                and isinstance(indexes, list)
                and len(cast(list[object], indexes)) == self._count
                and all(
                    _integer(i) and cast(int, i) < 1000
                    for i in cast(list[object], indexes)
                )
                and len(set(cast(list[int], indexes))) == self._count
            )
        if op == "quarantine":
            return not data
        if op in {"inspect-population-v1", "inspect"}:
            return _inspection(data)
        shapes: dict[str, set[str]] = {
            "retained_counts": {"retained", "unfinished"},
            "heartbeat": {"extended"},
            "release": {"released"},
            "retain": {"quarantined"},
            "provision": {"convention", "enrollment", "fursuit", "activation"},
            "cleanup": {
                "convention",
                "enrollment",
                "fursuit",
                "activation",
                "catch",
                "session",
                "credential",
                "image",
                "readmitted",
            },
        }
        if set(data) != shapes[op] or not all(_integer(v) for v in data.values()):
            return False
        if op in {"release", "retain"}:
            # Prior quarantine/retention clear leases. Each atomic backend ACK
            # covers all remaining run-owned leases, whose count can be smaller.
            return cast(int, next(iter(data.values()))) <= self._count
        if op == "heartbeat":
            return data["extended"] == self._count
        if op == "provision":
            return data == {
                "convention": 1,
                "enrollment": self._count - self._extras,
                "fursuit": self._owners * self._fursuits,
                "activation": self._owners * self._fursuits,
            }
        return True

    async def _run_dispatch(
        self,
        channel: str,
        envelope: dict[str, object],
        op: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        try:
            result, data = await asyncio.wait_for(
                self._dispatch(channel, envelope), max(0, self._end - self._clock())
            )
            data = decode_frame(encode_frame(data))
            if (
                op == "heartbeat"
                and result == "PASS"
                and set(data) == {"extended"}
                and _integer(data["extended"])
                and data["extended"] != self._count
            ):
                # A well-formed wrong count shows a lost lease, not a lost relay.
                result, data = "FAIL_LEASE", {}
            elif result not in _FAILURES | {"PASS"} or (
                result == "PASS" and not self._ack(op, data)
            ):
                result, data = "FAIL_LAUNCHER", {}
            elif result != "PASS":
                # Failure details do not cross this authority boundary.
                data = {}
        except (Exception, asyncio.CancelledError):  # noqa: BLE001 - owned dispatch loss is uncertain
            result, data = "FAIL_LAUNCHER", {}
        if result == "FAIL_TARGET":
            self._veto = True
        if op == "heartbeat" and result != "PASS":
            self._heartbeat_failed += 1
            if len(self._heartbeat_failure_offsets) < _HEARTBEAT_OFFSET_CAP:
                self._heartbeat_failure_offsets.append(
                    round(self._clock() - self._started, 1)
                )
        if op in _MUTATIONS and op != "heartbeat" and result in _UNCERTAIN:
            self._uncertain = True
        self._outcomes[op] = result
        reply: dict[str, object] = {"result": result, "data": data}
        if result == "PASS":
            if op == "allocate":
                self._indexes = deepcopy(cast(list[int], data["indexes"]))
            elif op == "provision":
                self._provisioned = True
            elif op in {"cleanup", "retain"}:
                self._recovered = True
            elif op == "quarantine":
                self._quarantined.add(cast(int, args["index"]))
            elif op == "release":
                self._released = True
                self.close()
            if op in {"allocate", "provision"}:
                self._cached[op] = deepcopy(reply)
        return reply

    async def settle(self) -> None:
        """Join owned dispatches within their original absolute reserve."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


def _inspection(data: dict[str, object]) -> bool:
    if (
        set(data) != {"catches", "fursuits", "fixture_photos_unchanged", "avatars"}
        or type(data["fixture_photos_unchanged"]) is not bool
    ):
        return False
    for key in ("catches", "fursuits", "avatars"):
        if not isinstance(data[key], list):
            return False
    if not all(_integer(i) for i in cast(list[object], data["avatars"])):
        return False
    for raw in cast(list[object], data["fursuits"]):
        item = _dict(raw)
        if set(item) != {"id", "owner"} or not all(_integer(v) for v in item.values()):
            return False
    for raw in cast(list[object], data["catches"]):
        item = _dict(raw)
        if set(item) != {
            "id",
            "fursuit",
            "catcher",
            "fursuit_owner",
            "run_convention",
            "provenance",
            "in_window",
            "caught_at",
        }:
            return False
        if (
            not all(_integer(item[k]) for k in ("id", "fursuit"))
            or not all(
                item[k] is None or _integer(item[k])
                for k in ("catcher", "fursuit_owner")
            )
            or not all(
                type(item[k]) is bool
                for k in ("run_convention", "provenance", "in_window")
            )
        ):
            return False
        stamp = item["caught_at"]
        if (
            not isinstance(stamp, str)
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z",
                stamp,
            )
            is None
        ):
            return False
    return True


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    # Read available chunks rather than silently splitting a supplied second frame.
    raw = bytearray()
    while b"\n" not in raw and len(raw) <= 65536:
        chunk = await reader.read(65537 - len(raw))
        if not chunk:
            break
        raw.extend(chunk)
    return bytes(raw)


class BridgeServer:
    def __init__(
        self, session: BridgeSession, rpc_path: Path, health_path: Path
    ) -> None:
        self._session = session
        self._paths = {"rpc": rpc_path, "health": health_path}
        self._servers: list[asyncio.Server] = []
        self._owned: dict[Path, tuple[int, int]] = {}
        self._active = {"rpc": 0, "health": 0}
        self._handlers: set[asyncio.Task[None]] = set()

    @classmethod
    def for_paths(
        cls, session: BridgeSession, rpc_path: Path, health_path: Path
    ) -> "BridgeServer":
        """Each socket sits in its own run-owned directory (#316)."""
        return cls(session, rpc_path, health_path)

    @staticmethod
    def _private_parent(parent: Path) -> None:
        info = parent.stat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError("invalid bridge paths")

    async def start(self) -> None:
        if self._servers:
            raise ValueError("invalid bridge paths")
        # Validate every path before binding any: a late refusal must leave no socket.
        for path in self._paths.values():
            if not path.is_absolute() or any(
                p.is_symlink() for p in (path, *path.parents)
            ):
                raise ValueError("invalid bridge paths")
            self._private_parent(path.parent)
            if path.exists() or path.is_symlink():
                raise ValueError("invalid bridge paths")
        previous = os.umask(0o077)
        try:
            for kind, path in self._paths.items():
                server = await asyncio.start_unix_server(
                    lambda r, w, kind=kind: self._accept(kind, r, w),
                    path=path,
                    limit=65536,
                    cleanup_socket=False,
                )
                self._servers.append(server)
                os.chmod(path, 0o600)
                info = path.stat()
                self._owned[path] = (info.st_dev, info.st_ino)
        except BaseException:
            await self.close()
            raise
        finally:
            os.umask(previous)

    def _accept(
        self, kind: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        counters = self._session.health_counters
        if self._active[kind] >= (10 if kind == "rpc" else 2):
            if kind == "health":
                counters["refused_at_capacity"] += 1
            writer.close()
            return
        self._active[kind] += 1
        if kind == "health":
            counters["accepted"] += 1
            counters["peak_active"] = max(counters["peak_active"], self._active[kind])
        task = asyncio.create_task(self._handle(kind, reader, writer))
        self._handlers.add(task)
        task.add_done_callback(self._handlers.discard)

    async def _handle(
        self, kind: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        counters = self._session.health_counters
        try:
            frame = decode_frame(await asyncio.wait_for(_read_frame(reader), 2))
            if (
                type(frame.get("schema_version")) is not int
                or frame["schema_version"] != 1
            ):
                raise ValueError
            if kind == "health":
                if (
                    set(frame) != {"schema_version", "channel", "run_id"}
                    or frame["channel"] != "health"
                    or frame["run_id"] != self._session.health()["run_id"]
                ):
                    raise ValueError
                reply = self._session.health()
            else:
                if (
                    set(frame) != {"schema_version", "channel", "request"}
                    or frame["channel"] not in _TARGETS
                ):
                    raise ValueError
                reply = await self._session.request(
                    cast(str, frame["channel"]), _dict(frame["request"])
                )
            writer.write(encode_frame(reply))
            try:
                await asyncio.wait_for(writer.drain(), 2)
            except (OSError, TimeoutError):
                if kind == "health":
                    counters["write_failed"] += 1
            else:
                if kind == "health":
                    counters[
                        "replied_live" if reply["live"] else "replied_not_live"
                    ] += 1
        except (ValueError, TypeError, OSError, TimeoutError):
            if kind == "health":
                counters["invalid"] += 1
        finally:
            writer.close()
            try:
                # A transport that never finishes closing must not pin a slot.
                await asyncio.wait_for(writer.wait_closed(), 2)
            except TimeoutError:
                if kind == "health":
                    counters["close_timeouts"] += 1
            except OSError:
                pass
            self._active[kind] -= 1

    async def close(self) -> None:
        self._session.close()
        for server in self._servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in self._servers))
        self._servers.clear()
        for task in self._handlers:
            task.cancel()
        await asyncio.gather(*self._handlers, return_exceptions=True)
        await self._session.settle()
        for path, identity in self._owned.items():
            try:
                info = path.lstat()
                if (
                    stat.S_ISSOCK(info.st_mode)
                    and (info.st_dev, info.st_ino) == identity
                ):
                    path.unlink()
            except FileNotFoundError:
                pass
        self._owned.clear()
