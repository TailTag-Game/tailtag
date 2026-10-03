"""Shared in-memory boundaries for the fixture smoke tests (#220 unit B).

Builds on pool_support. The only new substitutes are the fixture channel (a fake
speaking the relay's request protocol, backed by the same lease table) and the
public reads that provisioned state would serve (`FixtureState`, installed as the
World's extra authenticated route). Response shapes follow the real serializers:
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
_ARGUMENT_NAMES: Final = frozenset(
    {"pool", "run_id", "owners", "catchers", "fursuits_per_owner"}
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

    A `provision` succeeds only for exactly the right argument names, indexes that are
    leased to the run and onboarded, like the real service. On success it populates
    `state` (then lets `tamper` break it). `fail` makes every call fail instead; a
    FAIL_DIRTY quarantines that many of the requested slots server-side first, as the
    real service does.
    """

    def __init__(
        self,
        world: World,
        leases: FakeChannel,
        state: FixtureState,
        *,
        fail: Exception | None = None,
        tamper: Callable[[FixtureState], None] | None = None,
    ) -> None:
        self._world = world
        self._leases = leases
        self.state = state
        self._fail = fail
        self._tamper = tamper
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        args = dict(arguments)
        self.calls.append((operation, args))
        self._world.note("fixture", operation)
        owners, catchers = args.get("owners"), args.get("catchers")
        per_owner, run_id = args.get("fursuits_per_owner"), args.get("run_id")
        if (
            operation != "provision"
            or frozenset(args) != _ARGUMENT_NAMES
            or args["pool"] != POOL
            or not isinstance(owners, list)
            or not isinstance(catchers, list)
            or type(per_owner) is not int
            or not isinstance(run_id, str)
            or str(uuid.UUID(run_id)) != run_id
        ):
            raise FixtureFailed("FAIL_REQUEST")
        owner_indexes = [int(str(i)) for i in cast(list[object], owners)]
        catcher_indexes = [int(str(i)) for i in cast(list[object], catchers)]
        requested = [*owner_indexes, *catcher_indexes]
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
            "enrollment": len(requested),
            "fursuit": len(owner_indexes) * per_owner,
            "activation": len(owner_indexes) * per_owner,
        }
