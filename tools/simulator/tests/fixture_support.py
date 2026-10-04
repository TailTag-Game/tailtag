"""Shared in-memory boundaries for the fixture smoke tests (#220 unit B).

Builds on pool_support. The only new substitutes are the fixture channel (a fake
speaking the relay's request protocol, backed by the same lease table) and the
public reads that provisioned state would serve (`FixtureState`, installed as the
World's extra authenticated route). The channel speaks all four operations: `provision`,
`retained`, `cleanup` and `retain` (#223, frozen wire shapes in the implementation plan). Response shapes follow the real serializers:
`GET /api/conventions/active/`, `GET /api/fursuits/` and
`GET /api/conventions/<id>/fursuit-activations/`.
"""

import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

import httpx
from pool_support import POOL, FakeChannel, World

from tailtag_simulator.fixtures import FixtureFailed

CONVENTION_ID: Final = 4242
OTHER_CONVENTION_ID: Final = 4343
ACTIVE_PATH: Final = "/api/conventions/active/"
FURSUITS_PATH: Final = "/api/fursuits/"
ACTIVATIONS_PATH: Final = f"/api/conventions/{CONVENTION_ID}/fursuit-activations/"

# Things F-8 forbids in simulator output; the fake responses and requests carry them.
LEAK_SENTINELS: Final = ("SENTINEL", "media.example", "Sim Fursuit", "sp_", "Sim p1")

_ACTIVATIONS: Final = re.compile(r"/api/conventions/(\d+)/fursuit-activations/")
_PROVISION_ARGUMENTS: Final = frozenset(
    {"pool", "run_id", "owners", "catchers", "fursuits_per_owner", "extras"}
)
RETAIN_REASONS: Final = frozenset(
    {"journeys", "reconciliation", "cleanup", "interrupted"}
)

# What `cleanup` returns on PASS, in an order that is not the printed order.
CLEANUP_DATA: Final[dict[str, object]] = {
    "readmitted": 9,
    "image": 8,
    "credential": 7,
    "session": 6,
    "catch": 5,
    "activation": 4,
    "fursuit": 3,
    "enrollment": 2,
    "convention": 1,
}

# The in-run CLEANUP line for `CLEANUP_DATA`: fixed key order, `readmitted` not printed.
CLEANUP_LINE: Final = (
    "PASS cleanup convention=1 enrollment=2 fursuit=3 activation=4"
    " catch=5 session=6 credential=7 image=8"
)


def enrollment_body(convention_id: int | None) -> dict[str, object]:
    if convention_id is None:
        return {"enrollment": None}
    return {
        "enrollment": {
            "id": 9000 + convention_id,
            "convention": {
                "id": convention_id,
                "name": "Sim 123e4567",
                "status": "active",
                "start_date": "2026-10-02",
                "end_date": "2026-10-03",
            },
            "is_active": True,
            "created_at": "2026-10-02T12:00:00Z",
        }
    }


def fursuit_body(fursuit_id: int, name: str) -> dict[str, object]:
    return {
        "id": fursuit_id,
        "tailtag_id": str(uuid.UUID(int=fursuit_id)),
        "name": name,
        "photo_url": f"https://media.example/SENTINEL-KEY-{fursuit_id}.jpg",
        "is_enabled": True,
    }


def activation_body(fursuit_id: int) -> dict[str, object]:
    return {
        "fursuit_id": fursuit_id,
        "convention_id": CONVENTION_ID,
        "is_active": True,
        "is_eligible": True,
        "activated_at": "2026-10-02T12:00:00Z",
        "deactivated_at": None,
    }


@dataclass
class FixtureState:
    """What the public API serves per pool index once `provision` has succeeded."""

    owners: list[int] = field(default_factory=list[int])
    catchers: list[int] = field(default_factory=list[int])
    enrollments: dict[int, dict[str, object]] = field(
        default_factory=dict[int, dict[str, object]]
    )
    fursuits: dict[int, list[dict[str, object]]] = field(
        default_factory=dict[int, list[dict[str, object]]]
    )
    activations: dict[int, list[dict[str, object]]] = field(
        default_factory=dict[int, list[dict[str, object]]]
    )
    # (method, path, index) -> response, consulted before the state above
    reply_override: dict[tuple[str, str, int], httpx.Response | Exception] = field(
        default_factory=dict[tuple[str, str, int], httpx.Response | Exception]
    )

    def populate(
        self, owners: Sequence[int], catchers: Sequence[int], per_owner: int
    ) -> None:
        self.owners, self.catchers = list(owners), list(catchers)
        for index in [*owners, *catchers]:
            self.enrollments[index] = enrollment_body(CONVENTION_ID)
        for position, index in enumerate(owners):
            ids = [100 * (position + 1) + n for n in range(per_owner)]
            self.fursuits[index] = [
                fursuit_body(i, f"Sim Fursuit {position}-{n}")
                for n, i in enumerate(ids)
            ]
            self.activations[index] = [activation_body(i) for i in ids]

    def route(self, method: str, path: str, index: int) -> httpx.Response | None:
        override = self.reply_override.get((method, path, index))
        if isinstance(override, Exception):
            raise override
        if override is not None:
            return override
        if method != "GET" or index not in self.enrollments:
            return None
        if path == ACTIVE_PATH:
            return httpx.Response(200, json=self.enrollments[index])
        if path == FURSUITS_PATH:
            return httpx.Response(200, json=self.fursuits.get(index, []))
        match = _ACTIVATIONS.fullmatch(path)
        if match is not None:
            if int(match.group(1)) != CONVENTION_ID:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=self.activations.get(index, []))
        return None


class FakeFixtureChannel:
    """In-memory relay: enforces the request protocol, the lease binding and F-5.

    A `provision` succeeds only for exactly the right argument names and indexes that
    are leased to the run and onboarded (owners, catchers and extras), like the real
    service. On success it populates `state` (then lets `tamper` break it). `fail` makes
    `provision` fail instead; a FAIL_DIRTY quarantines that many of the requested slots
    server-side first, as the real service does.

    `retained` answers the cap query with `(retained, unfinished)` counts. `cleanup`
    answers `CLEANUP_DATA` and `retain` quarantines every slot still leased to the run,
    answering how many, as the real service does. `ops_fail` makes one of those
    operations fail instead. `leased_during` records which slots were leased at the
    moment of each call.
    """

    def __init__(
        self,
        world: World,
        leases: FakeChannel,
        state: FixtureState,
        *,
        fail: Exception | None = None,
        tamper: Callable[[FixtureState], None] | None = None,
        retained: tuple[int, int] = (0, 0),
        ops_fail: Mapping[str, BaseException] | None = None,
    ) -> None:
        self._world = world
        self._leases = leases
        self.state = state
        self._fail = fail
        self._tamper = tamper
        self._retained = retained
        self._ops_fail = dict(ops_fail or {})
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.leased_during: list[tuple[str, set[int]]] = []

    @property
    def operations(self) -> list[str]:
        return [operation for operation, _ in self.calls]

    def calls_to(self, operation: str) -> list[dict[str, object]]:
        return [args for op, args in self.calls if op == operation]

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        args = dict(arguments)
        self.calls.append((operation, args))
        self.leased_during.append((operation, self._leases.indexes("leased")))
        self._world.note("fixture", operation)
        if operation == "provision":
            return self._provision(args)
        if operation in self._ops_fail:
            raise self._ops_fail[operation]
        run_id = args.get("run_id")
        if operation == "retained" and args == {}:
            return {
                "runs": [],
                "retained": self._retained[0],
                "unfinished": self._retained[1],
            }
        if (
            operation in ("cleanup", "retain")
            and isinstance(run_id, str)
            and args["pool"] == POOL
            and str(uuid.UUID(run_id)) == run_id
        ):
            if operation == "cleanup" and frozenset(args) == frozenset(
                {"pool", "run_id"}
            ):
                return dict(CLEANUP_DATA)
            if (
                operation == "retain"
                and frozenset(args) == frozenset({"pool", "run_id", "reason"})
                and args["reason"] in RETAIN_REASONS
            ):
                mine = [
                    slot
                    for slot in self._leases.slots.values()
                    if slot.state == "leased" and slot.run_id == run_id
                ]
                for slot in mine:
                    slot.state, slot.run_id = "quarantined", None
                return {"quarantined": len(mine)}
        raise FixtureFailed("FAIL_REQUEST")

    def _provision(self, args: dict[str, object]) -> dict[str, object]:
        owners, catchers = args.get("owners"), args.get("catchers")
        extras = args.get("extras")
        per_owner, run_id = args.get("fursuits_per_owner"), args.get("run_id")
        if (
            frozenset(args) != _PROVISION_ARGUMENTS
            or args["pool"] != POOL
            or not isinstance(owners, list)
            or not isinstance(catchers, list)
            or not isinstance(extras, list)
            or type(per_owner) is not int
            or not isinstance(run_id, str)
            or str(uuid.UUID(run_id)) != run_id
        ):
            raise FixtureFailed("FAIL_REQUEST")
        owner_indexes = [int(str(i)) for i in cast(list[object], owners)]
        catcher_indexes = [int(str(i)) for i in cast(list[object], catchers)]
        extra_indexes = [int(str(i)) for i in cast(list[object], extras)]
        requested = [*owner_indexes, *catcher_indexes, *extra_indexes]
        if self._fail is not None:
            if isinstance(self._fail, FixtureFailed) and self._fail.quarantined:
                for index in requested[: self._fail.quarantined]:
                    self._leases.slots[index].state = "quarantined"
                    self._leases.slots[index].run_id = None
            raise self._fail
        for index in requested:
            slot = self._leases.slots.get(index)
            profile = self._world.profiles.get(index, {})
            if (
                slot is None
                or slot.state != "leased"
                or slot.run_id != run_id
                or profile.get("handle") is None
            ):
                raise FixtureFailed("FAIL_LEASE")
        self.state.populate(owner_indexes, catcher_indexes, per_owner)
        if self._tamper is not None:
            self._tamper(self.state)
        return {
            "convention": 1,
            "enrollment": len(owner_indexes) + len(catcher_indexes),
            "fursuit": len(owner_indexes) * per_owner,
            "activation": len(owner_indexes) * per_owner,
        }
