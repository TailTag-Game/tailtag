"""#508 AC20, AC21, AC30 to AC32: the per-player limit and request expiry."""

import asyncio
from collections.abc import Mapping
from typing import Any

import pool_support
import pytest
from fixture_support import FakeFixtureChannel
from journey_support import JourneyWorld, not_onboarded, user_json
from pool_support import POOL, RUN_ID, SECRET, FakeChannel, World

from tailtag_simulator.request_limit import (
    LIMIT,
    NORMAL_REQUESTS,
    REVIEW_DEADLINE_OFFSET_SECONDS,
    run_request_limit,
)

IDENTITIES = 12  # slot 0 stays quarantined; the run leases 10
world = pool_support.world


class Inspection:
    """inspect-population-v2 data straight from the fake's stored state."""

    def __init__(self, world: JourneyWorld) -> None:
        self.world = world
        self.calls: list[dict[str, int]] = []

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        assert pool == POOL and run_id
        self.calls.append(dict(identities))
        gameplay = self.world.gameplay
        return {
            "catches": [],
            "fursuits": [],
            "fixture_photos_unchanged": True,
            "avatars": [],
            "requests": [
                {
                    "id": row.id,
                    "player": row.player,
                    "fursuit": row.fursuit_id,
                    "run_convention": True,
                    "state": row.state,
                    "requested_at": "2026-10-03T12:00:00Z",
                }
                for row in gameplay.rows
            ],
        }


class Fixtures(FakeFixtureChannel):
    """Provisioning applies the offset to the fake's review deadline."""

    def __init__(self, world: JourneyWorld, leases: FakeChannel) -> None:
        super().__init__(world, leases, world.gameplay.state)
        self.journey_world = world

    async def call(
        self, operation: str, arguments: Mapping[str, object]
    ) -> dict[str, object]:
        result = await super().call(operation, arguments)
        if operation == "provision":
            offset = getattr(self, "review_deadline_offset", None)
            gameplay = self.journey_world.gameplay
            if isinstance(offset, int):
                gameplay.deadline = gameplay.clock() + offset
        return result


def run(rule: str | None = None) -> tuple[int, list[str], JourneyWorld, Fixtures]:
    world = JourneyWorld(
        users={i: user_json(i) for i in range(IDENTITIES)},
        profiles={i: not_onboarded() for i in range(IDENTITIES)},
        leftover_sessions={i: [f"sess_old{i}"] for i in range(IDENTITIES)},
    )
    if rule is not None:
        world.gameplay.break_rule(rule)
    leases = FakeChannel(world, slots=IDENTITIES)
    leases.slots[0].state = "quarantined"
    fixtures = Fixtures(world, leases)
    lines: list[str] = []
    gameplay = world.gameplay
    code = asyncio.run(
        run_request_limit(
            POOL,
            prompt_secret=lambda: SECRET,
            lease_channel=leases,
            fixture_channel=fixtures,
            inspection_channel=Inspection(world),
            emit=lines.append,
            clerk_transport=world.clerk_transport,
            api_transport=world.api_transport,
            clock=world.clock,
            run_id=RUN_ID,
            sleep=gameplay.advance,
            wall=gameplay.clock,
        )
    )
    return code, lines, world, fixtures


def test_normal_play_stays_under_the_limit_abuse_hits_it_and_requests_expire(
    world: World,
) -> None:
    del world
    code, lines, journey_world, fixtures = run()

    assert code == 0, lines
    assert [line for line in lines if "journey" in line] == [
        "PASS journey=normal_play",
        "PASS journey=abuse_limit",
        "PASS journey=expiry",
        "PASS journeys passed=3",
    ]
    rows = journey_world.gameplay.rows
    # 20 normal requests, 30 before the limit, and 1 after the wait; all pending.
    assert len(rows) == NORMAL_REQUESTS + LIMIT + 1
    assert {row.state for row in rows} == {"pending"}
    assert journey_world.gameplay.catches == []
    provision: dict[str, Any] = fixtures.calls_to("provision")[0]
    assert provision["fursuits_per_owner"] == 5 and len(provision["owners"]) == 8
    assert fixtures.review_deadline_offset == REVIEW_DEADLINE_OFFSET_SECONDS
    assert "PASS release" in lines


@pytest.mark.parametrize(
    ("rule", "line"),
    [
        (
            "abuse_limit",
            (
                "FAIL journey=abuse_limit step=submit_limited"
                " expected=429/rate_limited observed=201/pending"
            ),
        ),
        (
            "expiry",
            (
                "FAIL journey=expiry step=approve_closed"
                " expected=409/review_window_closed observed=200/-"
            ),
        ),
    ],
    ids=("limit-not-enforced", "window-not-closed"),
)
def test_each_broken_rule_fails_its_own_journey(
    world: World, rule: str, line: str
) -> None:
    del world
    code, lines, _, fixtures = run(rule)

    assert code != 0
    assert line in lines
    assert "retain" in fixtures.operations and "cleanup" not in fixtures.operations
