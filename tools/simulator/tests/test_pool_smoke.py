"""Behavioral tests for the pool smoke run (#219 P-3 to P-9; D4, D5, D8, D9).

Boundaries substituted: Clerk and TailTag HTTP, the lease channel, the secret
prompt and time (see pool_support). Target verification, the Clerk tooling, the
phases and reporting all run for real.
"""

import asyncio
import dataclasses
import re
import typing
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pool_support
import pytest
from pool_support import (
    ALLOWED_API_PATHS,
    POOL,
    RUN_ID,
    SECRET,
    SENSITIVE_PREFIXES,
    SHA,
    FakeChannel,
    World,
    onboarded,
    user_json,
)

from tailtag_simulator.client import ApiClient
from tailtag_simulator.pool import PoolSimulationContext, run_pool_smoke

world = pool_support.world  # the shared fixture

TARGET_LINE = f"PASS target staging source_sha={SHA}"
FIXED_LINES = re.compile(
    rf"PASS target staging source_sha={SHA}"
    r"|PASS setup identities=\d+"
    r"|PASS (simulation|reconciliation|release)"
    r"|FAIL (target|setup|simulation|reconciliation|release)"
)


@dataclass
class Run:
    code: int
    lines: list[str]
    prompts: int


def smoke(
    world: World,
    channel: FakeChannel,
    *,
    count: int = 3,
    run_id: str | None = RUN_ID,
    cancel_in_sleep: bool = False,
) -> Run:
    prompts: list[str] = []

    def prompt() -> str:
        prompts.append(SECRET)
        world.note("prompt")
        return SECRET

    lines: list[str] = []

    def emit(line: str) -> None:
        lines.append(line)
        world.note("emit", line)

    async def sleep(seconds: float) -> None:
        if cancel_in_sleep:
            raise asyncio.CancelledError
        world.clock.now += seconds
        world.note("sleep", str(seconds))

    code = asyncio.run(
        run_pool_smoke(
            POOL,
            count,
            prompt_secret=prompt,
            channel=channel,
            emit=emit,
            clerk_transport=world.clerk_transport,
            api_transport=world.api_transport,
            sleep=sleep,
            clock=world.clock,
            run_id=run_id,
        )
    )
    return Run(code, lines, len(prompts))


@pytest.fixture
def happy(world: World) -> tuple[Run, World, FakeChannel]:
    world.profiles[0] = onboarded(0)  # already onboarded; 1 and 2 are not
    channel = FakeChannel(world)
    return smoke(world, channel), world, channel


def assert_released(world: World, channel: FakeChannel) -> None:
    assert channel.indexes("leased") == set()
    assert set(world.ended_sessions) == set(world.opened_sessions)
    assert len(world.ended_sessions) == len(world.opened_sessions)


# -- the happy path ------------------------------------------------------------


def test_successful_run_reports_only_the_fixed_lines_and_releases_everything(
    happy: tuple[Run, World, FakeChannel],
) -> None:
    run, world, channel = happy

    assert run.code == 0
    assert run.lines == [
        TARGET_LINE,
        "PASS setup identities=3",
        "PASS simulation",
        "PASS reconciliation",
        "PASS release",
    ]
    assert all(FIXED_LINES.fullmatch(line) for line in run.lines)
    assert len(world.opened_sessions) == 3
    assert_released(world, channel)
    assert channel.indexes("free") == set(range(5))
    assert channel.calls_to("release") == [{"run_id": RUN_ID}]
    assert channel.calls_to("quarantine") == []


def test_secret_is_prompted_once_after_target_and_never_leaves_setup(
    happy: tuple[Run, World, FakeChannel],
) -> None:
    run, world, channel = happy

    assert run.prompts == 1
    log = world.log
    assert log.index(("prompt", "")) > log.index(("emit", TARGET_LINE))
    # The admin is closed before SIMULATION: no Backend API call after the first
    # /api/me/, and the secret is on no TailTag request and no lease request.
    backend = [i for i, (kind, _) in enumerate(log) if kind == "backend"]
    first_me = next(i for i, (_, d) in enumerate(log) if "/api/me/" in d)
    assert backend and max(backend) < first_me
    for request in world.api_requests:
        assert SECRET not in f"{request.url}{dict(request.headers)}{request.content!r}"
        assert not any(p in str(request.url) for p in SENSITIVE_PREFIXES)
    assert SECRET not in str(channel.calls)
    # P-9: only these TailTag paths are ever requested; nothing went elsewhere.
    assert {path for _, path, _ in world.api_calls} <= ALLOWED_API_PATHS
    assert world.stray == []


def test_simulation_context_carries_only_api_clients() -> None:
    (only,) = dataclasses.fields(PoolSimulationContext)

    assert (
        typing.get_type_hints(PoolSimulationContext)[only.name] == tuple[ApiClient, ...]
    )


def test_each_identity_stays_authenticated_across_one_token_lifetime(
    happy: tuple[Run, World, FakeChannel],
) -> None:
    run, world, channel = happy

    assert channel.calls_to("allocate") == [
        {"run_id": RUN_ID, "count": 3, "ttl_seconds": 1800}
    ]
    assert channel.calls_to("heartbeat") == [{"run_id": RUN_ID, "ttl_seconds": 1800}]
    # first round of /api/me/, one heartbeat, a wait longer than 60 s, second round
    phases = [
        "me" if "/api/me/" in d else kind
        for kind, d in world.kinds("api", "channel", "sleep")
        if kind == "sleep" or "/api/me/" in d or d.startswith("heartbeat")
    ]
    assert phases == ["me"] * 3 + ["channel", "sleep"] + ["me"] * 3
    assert sum(float(d) for _, d in world.kinds("sleep")) > 60
    # The wait outlives the first token, so the second request must carry a new one
    # (the API fake answers 401 for an expired token, which fails reconciliation).
    for index in range(3):
        first, second = world.me_tokens[index]
        assert first != second
    assert run.code == 0


def test_leftover_sessions_are_revoked_and_profiles_onboarded_only_when_empty(
    happy: tuple[Run, World, FakeChannel],
) -> None:
    _, world, _ = happy

    assert world.revoked_sessions == ["sess_old0", "sess_old1", "sess_old2"]
    for index in range(3):  # a user's leftovers go before that user's ticket
        revoke = world.log.index(
            ("backend", f"POST /v1/sessions/sess_old{index}/revoke")
        )
        assert revoke < world.log.index(("ticket", str(index)))
    # Only never-onboarded identities are PUT, with the pool handle and name, using
    # their own token; the already onboarded one is only read.
    assert world.puts == {
        1: {"handle": "sp_p1_1", "display_name": "Sim p1 1"},
        2: {"handle": "sp_p1_2", "display_name": "Sim p1 2"},
    }
    puts = {
        (m, i) for m, p, i in world.api_calls if p == "/api/profile/" and m == "PUT"
    }
    assert puts == {("PUT", 1), ("PUT", 2)}


def test_a_generated_run_id_is_a_canonical_uuid_the_lease_service_accepts(
    world: World,
) -> None:
    channel = FakeChannel(world)

    assert smoke(world, channel, run_id=None).code == 0
    assert channel.calls_to("release")  # the fake rejects non-canonical run IDs


# -- failures before any identity work -------------------------------------------


def test_unverified_target_fails_before_any_prompt_lease_or_clerk_call(
    world: World,
) -> None:
    world.identity_environment = "development"
    channel = FakeChannel(world)

    run = smoke(world, channel)

    assert (run.code, run.lines, run.prompts) == (1, ["FAIL target"], 0)
    assert channel.calls == []
    assert world.kinds("backend", "frontend", "prompt") == []


def test_shortfall_leases_nothing_and_does_no_identity_work(
    world: World,
) -> None:
    channel = FakeChannel(world, slots=2)

    run = smoke(world, channel, count=3)

    assert run.code == 1
    assert run.lines == [TARGET_LINE, "FAIL setup needed=3 available=2"]
    assert channel.calls_to("release") == []
    assert (run.prompts, channel.indexes("leased"), channel.indexes("quarantined")) == (
        1,
        set(),
        set(),
    )
    assert world.tickets == [] and world.opened_sessions == []
    assert world.kinds("api", "frontend") == [
        ("api", "GET /health/identity"),
        ("api", "GET /health/identity"),
    ]


# -- identity failures are quarantined, the rest released (P-5, P-6, P-8a) ----------

UNMARKED = user_json(
    1,
    public_metadata={
        "tailtag_synthetic": False,
        "tailtag_environment": "staging",
        "tailtag_pool": POOL,
        "tailtag_pool_index": 1,
    },
)


def _drop_user(world: World) -> None:
    del world.users[1]


def _unmarked(world: World) -> None:
    world.users[1] = UNMARKED


def _banned(world: World) -> None:
    world.users[1] = user_json(1, banned=True)


def _sign_in_rejected(world: World) -> None:
    world.sign_in_rejected = {1}


def _handle_drift(world: World) -> None:
    world.profiles[1] = {"handle": "someone_else", "display_name": "Someone"}


def _put_returns_other_handle(world: World) -> None:
    world.put_handle_override = {1: "other_handle"}


def _two_bad(world: World) -> None:
    _drop_user(world)
    world.users[2] = user_json(2, banned=True)


# case -> (break the world, quarantined indexes, ticket created for the bad index)
SETUP_FAILURES: dict[str, tuple[Callable[[World], None], set[int], bool]] = {
    "missing-user": (_drop_user, {1}, False),
    "unmarked-user": (_unmarked, {1}, False),
    "banned-user": (_banned, {1}, False),
    "sign-in-rejected": (_sign_in_rejected, {1}, True),
    "profile-handle-drift": (_handle_drift, {1}, True),
    "onboarding-yields-another-handle": (_put_returns_other_handle, {1}, True),
    "several-bad-identities": (_two_bad, {1, 2}, False),
}


@pytest.mark.parametrize("case", SETUP_FAILURES)
def test_a_broken_identity_is_quarantined_and_the_run_stops_after_releasing(
    world: World,
    case: str,
) -> None:
    break_world, bad, ticket_expected = SETUP_FAILURES[case]
    break_world(world)
    channel = FakeChannel(world)

    run = smoke(world, channel)

    assert run.code == 1
    quarantined = ",".join(str(i) for i in sorted(bad))
    assert run.lines == [
        TARGET_LINE,
        f"FAIL setup quarantined={quarantined}",
        "PASS release",
    ]
    assert channel.indexes("quarantined") == bad
    assert {c["index"] for c in channel.calls_to("quarantine")} == bad
    assert all(c["run_id"] == RUN_ID for c in channel.calls_to("quarantine"))
    assert channel.indexes("free") == set(range(5)) - bad
    assert_released(world, channel)
    assert channel.calls_to("heartbeat") == []
    assert [d for _, d in world.kinds("api") if "/api/me/" in d] == []
    # P-8a: no ticket for a missing, unmarked or banned user.
    assert (bool(bad & set(world.tickets))) is ticket_expected
    # P-5: a drifted profile is never overwritten.
    assert 1 not in world.puts or case == "onboarding-yields-another-handle"


def test_when_every_allocated_identity_fails_nothing_is_quarantined_but_all_is_released(
    world: World,
) -> None:
    world.users[0] = user_json(0, banned=True)
    del world.users[1]
    channel = FakeChannel(world)

    run = smoke(world, channel, count=2)

    assert run.code == 1
    assert run.lines == [TARGET_LINE, "FAIL setup", "PASS release"]
    assert channel.calls_to("quarantine") == []
    assert channel.indexes("quarantined") == set()
    assert channel.indexes("free") == set(range(5))
    assert channel.calls_to("release") == [{"run_id": RUN_ID}]


def test_cancellation_during_the_wait_still_ends_sessions_and_releases_leases(
    world: World,
) -> None:
    channel = FakeChannel(world)

    with pytest.raises(asyncio.CancelledError):
        smoke(world, channel, cancel_in_sleep=True)

    assert len(world.opened_sessions) == 3
    assert_released(world, channel)
    assert channel.calls_to("release") == [{"run_id": RUN_ID}]


# -- release after later failures (P-3) -------------------------------------------

BASE = [TARGET_LINE, "PASS setup identities=3"]
SIMULATION_FAILURES: dict[str, tuple[Callable[[World], None], list[str]]] = {
    "connection-error-after-the-wait": (
        lambda w: w.me_override.update({(1, 1): httpx.ConnectError("x")}),
        ["FAIL simulation"],
    ),
    "id-changes-between-requests": (
        lambda w: w.me_override.update({(1, 1): httpx.Response(200, json={"id": 7})}),
        ["PASS simulation", "FAIL reconciliation"],
    ),
    "two-identities-share-an-id": (
        lambda w: w.me_ids.update({1: 1000}),
        ["PASS simulation", "FAIL reconciliation"],
    ),
    "unauthorized-reply": (
        lambda w: w.me_override.update({(2, 0): httpx.Response(401, json={})}),
        ["PASS simulation", "FAIL reconciliation"],
    ),
    "boolean-id": (
        lambda w: w.me_ids.update({0: True}),
        ["PASS simulation", "FAIL reconciliation"],
    ),
}


@pytest.mark.parametrize("case", SIMULATION_FAILURES)
def test_leases_and_sessions_are_released_after_a_failed_simulation_or_reconciliation(
    world: World,
    case: str,
) -> None:
    break_world, expected = SIMULATION_FAILURES[case]
    break_world(world)
    channel = FakeChannel(world)

    run = smoke(world, channel)

    assert run.code == 1
    assert run.lines == [*BASE, *expected, "PASS release"]
    assert_released(world, channel)
    assert len(world.opened_sessions) == 3
    assert channel.calls_to("release") == [{"run_id": RUN_ID}]


@pytest.mark.parametrize("failing", ["session-end", "lease-release"])
def test_a_failed_release_is_reported_and_the_other_half_still_runs(
    world: World,
    failing: str,
) -> None:
    world.end_fails = failing == "session-end"
    channel = FakeChannel(
        world, fail={"release"} if failing == "lease-release" else None
    )

    run = smoke(world, channel)

    assert run.code == 1
    assert run.lines == [
        *BASE,
        "PASS simulation",
        "PASS reconciliation",
        "FAIL release",
    ]
    assert len(channel.calls_to("release")) == 1  # attempted even if sessions failed
    if failing == "lease-release":
        assert set(world.ended_sessions) == set(world.opened_sessions)


def test_a_lost_lease_stops_the_run_before_the_second_round(world: World) -> None:
    channel = FakeChannel(world, reclaim_before_heartbeat=1)

    run = smoke(world, channel)

    assert run.code == 1
    assert run.lines == [*BASE, "FAIL simulation", "PASS release"]
    assert channel.calls_to("release") == [{"run_id": RUN_ID}]
    assert len(world.opened_sessions) == 3
    assert sorted(world.ended_sessions) == sorted(world.opened_sessions)
    assert not any(kind == "sleep" for kind, _ in world.log)
