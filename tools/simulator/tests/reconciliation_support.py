"""The inspection channel fake for the reconciliation tests (#222 unit U2).

Builds on journey_support. The only new substitute is the privileged `inspect`
channel. Its `PASS` data is computed from the gameplay fake's own state (catches,
created fursuits, avatars, photo writes), exactly as the real relay would read it
from the database, so the fake API and the fake inspection cannot drift apart.

The gameplay fake models no sessions, activations or clocks. Everything it persists
was created from a live session, inside the run window, in the run Convention, so
`provenance`, `in_window` and `run_convention` are true for every catch it holds.

Faults are injected one of two ways:

- `corrupt(data) -> data` edits the `PASS` data (for what only the database knows:
  `provenance`, `in_window`, `fixture_photos_unchanged`, `caught_at` as stored, a
  foreign catch, the non-ledger fursuits).
- `change_reconciliation_history` edits what the public API serves, but only to the
  reconciliation's own history reads (the ones that ask for `page_size`), so the
  journeys still see a healthy API. Use it where the database and the API must stay
  consistent with each other.
"""

import json
import uuid
from collections.abc import Callable, Mapping
from typing import Final, cast

import httpx
import pytest
from journey_support import Gameplay, JourneyWorld
from pool_support import POOL

from tailtag_simulator.reconciliation import InspectionFailed, Role

Data = dict[str, object]
Corrupt = Callable[[Data], Data]

SHIFTED_CAUGHT_AT: Final = "2031-01-02T03:04:05.678901Z"

# A catch by nobody in the run, on nobody's fursuit, in another Convention.
FOREIGN_CATCH: Final[Data] = {
    "id": 9001,
    "catcher": None,
    "fursuit": 999,
    "fursuit_owner": None,
    "run_convention": False,
    "provenance": True,
    "in_window": True,
    "caught_at": SHIFTED_CAUGHT_AT,
}

# What the inspection data carries that reconciliation output must never repeat.
RECONCILIATION_LEAKS: Final = (
    "2026-10-03",
    "2031-01-02",
    "T12:00",
    "7001",
    "7002",
    "7003",
    "8001",
    "8002",
    "9001",
)


def _is_uuid(text: str) -> bool:
    try:
        return str(uuid.UUID(text)) == text
    except ValueError:
        return False


class FakeInspectionChannel:
    """In-memory relay: enforces the request shape, then reports the gameplay state.

    `fail` makes every call raise it instead. `corrupt` edits the data before it is
    returned. Every call is recorded and noted in the world's log, so a test can
    place it between the journeys and the release.
    """

    def __init__(
        self,
        world: JourneyWorld,
        *,
        corrupt: Corrupt | None = None,
        fail: InspectionFailed | None = None,
    ) -> None:
        self._world = world
        self._corrupt = corrupt
        self._fail = fail
        self.calls: list[tuple[str, str, dict[Role, int]]] = []

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[Role, int]
    ) -> Mapping[str, object]:
        self.calls.append((pool, run_id, dict(identities)))
        self._world.note("inspection", "inspect")
        if self._fail is not None:
            raise self._fail
        if pool != POOL or not _is_uuid(run_id) or set(identities) != set(Role):
            raise InspectionFailed("FAIL_REQUEST")
        data = self._state(identities)
        return data if self._corrupt is None else self._corrupt(data)

    def _state(self, identities: Mapping[Role, int]) -> Data:
        gameplay = self._world.gameplay
        run = set(identities.values())

        def person(index: int | None) -> int | None:
            return index if index in run else None

        photo_writes = {fursuit for _, fursuit in gameplay.photo_puts}
        return {
            "catches": [
                {
                    "id": caught.id,
                    "catcher": person(caught.catcher),
                    "fursuit": caught.fursuit_id,
                    "fursuit_owner": person(gameplay.owner_of(caught.fursuit_id)),
                    "run_convention": True,
                    "provenance": True,
                    "in_window": True,
                    "caught_at": gameplay.catch_view(caught)["caught_at"],
                }
                for caught in sorted(gameplay.catches, key=lambda c: c.id)
            ],
            "fursuits": [
                {"id": fursuit, "owner": gameplay.created_owner[fursuit]}
                for fursuit in sorted(gameplay.created)
            ],
            "fixture_photos_unchanged": not (
                photo_writes & gameplay.fixture_fursuit_ids()
            ),
            "avatars": sorted(index for index in gameplay.avatars if index in run),
        }


# -- fault injection ----------------------------------------------------------------


def edit(**changes: object) -> Corrupt:
    """Replace top-level keys of the `PASS` data."""
    return lambda data: {**data, **changes}


def edit_catch(catcher: int, **changes: object) -> Corrupt:
    """Change fields of the one catch the pool index `catcher` made."""

    def corrupt(data: Data) -> Data:
        catches = cast(list[Data], data["catches"])
        return {
            **data,
            "catches": [
                {**caught, **changes} if caught["catcher"] == catcher else caught
                for caught in catches
            ],
        }

    return corrupt


def add_catch(catch: Data) -> Corrupt:
    return lambda data: {**data, "catches": [*cast(list[Data], data["catches"]), catch]}


def chain(*corruptions: Corrupt) -> Corrupt:
    def corrupt(data: Data) -> Data:
        for each in corruptions:
            data = each(data)
        return data

    return corrupt


def change_reconciliation_history(
    monkeypatch: pytest.MonkeyPatch,
    gameplay: Gameplay,
    *,
    before: Callable[[Gameplay], None] | None = None,
    edit_body: Callable[[int, Data], Data] | None = None,
) -> None:
    """Change what the public history serves to the reconciliation's reads only.

    `before` runs once, just ahead of the first such read (a change to the stored
    rows). `edit_body(index, body)` edits each such response. The journeys' own
    history reads never ask for `page_size`, so they are untouched.
    """
    original = gameplay.history
    ran: list[bool] = []

    def history(index: int) -> httpx.Response:
        assert gameplay.request is not None
        if "page_size" not in gameplay.request.url.params:
            return original(index)
        if before is not None and not ran:
            ran.append(True)
            before(gameplay)
        response = original(index)
        if edit_body is None:
            return response
        body = cast(Data, json.loads(response.content))
        return httpx.Response(200, json=edit_body(index, body))

    monkeypatch.setattr(gameplay, "history", history)
