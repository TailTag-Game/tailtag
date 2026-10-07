"""AC1/3/5/7–12/16: real finite persona sequences through public HTTP.

The config, behavior engine, gameplay primitives and reconciliation execute for
real. PopulationWorld substitutes only public HTTP and authoritative inspection.
"""

import asyncio
import random
from collections import Counter
from collections.abc import Mapping
from contextlib import AsyncExitStack

import pytest
from fixture_support import CONVENTION_ID
from population_support import PopulationWorld

from tailtag_simulator.behavior import (
    PopulationContext,
    PopulationRun,
    simulate_population,
)
from tailtag_simulator.behavior_config import resolve_behavior_config
from tailtag_simulator.client import open_client
from tailtag_simulator.population_reconciliation import reconcile_population

PERSONAS = ("casual", "active", "heavy", "retry_prone", "normal_owner", "popular_owner")
COUNTERS = {
    "actors",
    "actions",
    "completed",
    "created",
    "already_caught",
    "expected_rejections",
    "retries",
    "history_reads",
    "exhausted",
    "unused_budget",
    "cycles",
}
FAMILIES = ("baseline", "post-event", "hotspot", "retry", "soak")


def run(
    world: PopulationWorld, config: Mapping[str, object], *, seed: int = 728
) -> PopulationRun:
    async def execute() -> PopulationRun:
        async with AsyncExitStack() as stack:
            clients = {
                actor: await stack.enter_async_context(
                    open_client(
                        "https://staging.tailtag.app",
                        token=actor,
                        transport=world.transport,
                    )
                )
                for actor in world.indexes
            }
            context = PopulationContext(
                owners=tuple(clients[f"owner{n}"] for n in range(len(world.owners))),
                attendees=tuple(
                    clients[f"attendee{n}"] for n in range(len(world.attendees))
                ),
            )
            result = await simulate_population(context, config, seed)
            if result.passed:
                compared = await reconcile_population(
                    result.expectations,
                    clients,
                    world.indexes,
                    world,
                    pool="alpha",
                    run_id="aaaaaaaa-1111-4111-8111-111111111111",
                    convention=result.convention,
                )
                assert compared.passed, compared.discrepancies
            return result

    return asyncio.run(execute())


@pytest.mark.parametrize("family", FAMILIES)
def test_all_families_execute_distinct_finite_persona_behavior_and_reconcile(
    family: str,
) -> None:
    config = resolve_behavior_config({"pool": "alpha", "family": family})
    world = PopulationWorld(config)
    result = run(world, config)

    assert result.passed and result.failure is None
    assert result.convention == CONVENTION_ID
    assert set(result.summaries) == set(PERSONAS)
    cycles = 3 if family == "soak" else 1
    budgets = (1, 1, 1, 1) if family == "hotspot" else (1, 3, 8, 3)
    for persona, budget in zip(PERSONAS[:4], budgets, strict=True):
        summary = result.summaries[persona]
        assert set(summary) == COUNTERS
        assert summary["actors"] == 1
        assert summary["completed"] == budget * cycles
        assert summary["created"] == budget
        assert summary["cycles"] == cycles
        assert summary["expected_rejections"] == 0
        assert all(type(value) is int and value >= 0 for value in summary.values())
    assert sum(summary["created"] for summary in result.summaries.values()) == (
        4 if family == "hotspot" else 15
    )
    assert sum(summary["already_caught"] for summary in result.summaries.values()) == (
        48 if family == "soak" else 2 if family == "hotspot" else 6
    )
    assert result.summaries["retry_prone"]["retries"] == (
        18 if family == "soak" else 2 if family == "hotspot" else 6
    )
    if family != "hotspot":
        assert [result.summaries[name]["history_reads"] for name in PERSONAS[:4]] == [
            cycles,
            cycles,
            8 * cycles,
            3 * cycles,
        ]
    assert [result.summaries[name]["unused_budget"] for name in PERSONAS[:4]] == (
        [0, 2, 7, 2] if family == "hotspot" else [0, 0, 0, 0]
    )
    for owner in PERSONAS[4:]:
        assert result.summaries[owner]["completed"] == 4 * cycles
        assert result.summaries[owner]["cycles"] == cycles
        assert (
            result.summaries[owner]["created"]
            == result.summaries[owner]["already_caught"]
            == 0
        )
    assert len(world.gameplay.catches) == (4 if family == "hotspot" else 15)
    assert world.gameplay.sessions and not any(world.gameplay.sessions.values())
    assert all(caught.catcher in world.attendees for caught in world.gameplay.catches)
    assert all(
        actor.startswith("owner")
        for actor, _method, path, _body in world.requests
        if "/fursuit-activations/" in path
        and not path.endswith("/fursuit-activations/")
    )

    confirmations = [
        actor
        for actor, _method, path, _body in world.requests
        if path == "/api/catches/confirm/"
    ]
    if family == "baseline":
        assert confirmations[:4] == ["attendee0", "attendee1", "attendee2", "attendee3"]
    elif family == "post-event":
        assert confirmations == [
            "attendee0",
            *["attendee1"] * 3,
            *["attendee2"] * 8,
            *["attendee3"] * 9,
        ]
        first = next(
            n
            for n, (_actor, _method, path, _body) in enumerate(world.requests)
            if path == "/api/catches/confirm/"
        )
        prepared = {
            actor
            for actor, method, path, _body in world.requests[:first]
            if (method, path) == ("GET", "/api/me/")
        }
        assert prepared == set(world.indexes)
    elif family == "hotspot":
        assert {caught.fursuit_id for caught in world.gameplay.catches} == {200}


def test_retry_family_finishes_first_confirmations_before_configured_duplicate_phase() -> (
    None
):
    """AC7/12: a retry family must not silently execute the baseline visit ordering."""
    config = resolve_behavior_config({"pool": "alpha", "family": "retry"})
    world = PopulationWorld(config)

    result = run(world, config)

    assert result.passed
    pairs = [
        (actor, world.gameplay.fursuit_of[str(body["payload"])])
        for actor, _method, path, body in world.requests
        if path == "/api/catches/confirm/"
    ]
    # The hand-derived default workload has 1+3+8+3 first confirmations, followed
    # by 2 additional confirmations of each retry-prone attendee's three targets.
    first_phase, duplicate_phase = pairs[:15], pairs[15:]
    assert len(set(first_phase)) == 15
    retry_targets = {pair for pair in first_phase if pair[0] == "attendee3"}
    assert len(retry_targets) == 3
    assert Counter(duplicate_phase) == {pair: 2 for pair in retry_targets}
    assert len(world.gameplay.catches) == len(result.expectations.made) == 15
    for pair in retry_targets:
        assert result.expectations.seen[pair] == [result.expectations.made[pair]] * 2


def test_configured_owner_weights_change_seeded_public_target_choices() -> None:
    """AC8/11: uniform or fixed weights must not ignore operator configuration."""
    shared: dict[str, object] = {
        "pool": "alpha",
        "family": "baseline",
        "casual": 40,
        "active": 0,
        "heavy": 0,
        "retry_prone": 0,
        "fursuits": 1,
    }
    normal_config = resolve_behavior_config(
        {**shared, "normal_weight": 100, "popular_weight": 1}
    )
    popular_config = resolve_behavior_config(
        {**shared, "normal_weight": 1, "popular_weight": 100}
    )
    normal_world, popular_world = (
        PopulationWorld(normal_config),
        PopulationWorld(popular_config),
    )

    normal_result = run(normal_world, normal_config, seed=9347)
    popular_result = run(popular_world, popular_config, seed=9347)

    assert normal_result.passed and popular_result.passed
    normal_choices = Counter(
        catch.fursuit_id for catch in normal_world.gameplay.catches
    )
    popular_choices = Counter(
        catch.fursuit_id for catch in popular_world.gameplay.catches
    )
    # Same actor streams and logical fixtures: reversing only the weights must
    # move observed selections toward the newly favored target, without timing.
    assert normal_choices[100] > popular_choices[100]
    assert popular_choices[200] > normal_choices[200]
    assert sum(normal_choices.values()) == sum(popular_choices.values()) == 40


@pytest.mark.parametrize(
    ("repeats", "cadence", "confirmations", "extra", "history_progress"),
    [(3, 2, 20, 15, [2, 4, 5, 5]), (1, 0, 10, 5, [5, 5])],
    ids=("custom-repeats-periodic-history", "custom-repeats-completion-only-history"),
)
def test_nondefault_repeats_and_history_cadence_drive_public_sequences(
    repeats: int,
    cadence: int,
    confirmations: int,
    extra: int,
    history_progress: list[int],
) -> None:
    """AC8/9: defaults must not replace configured repeat counts or read cadence."""
    config = resolve_behavior_config(
        {
            "pool": "alpha",
            "family": "baseline",
            "casual": 0,
            "active": 1,
            "heavy": 0,
            "retry_prone": 0,
            "normal_owners": 1,
            "popular_owners": 0,
            "fursuits": 5,
            "active_budget": 5,
            "active_repeats": repeats,
            "active_history": cadence,
        }
    )
    world = PopulationWorld(config)

    result = run(world, config)

    assert result.passed
    summary = result.summaries["active"]
    assert {
        key: summary[key]
        for key in (
            "completed",
            "created",
            "already_caught",
            "retries",
            "history_reads",
        )
    } == {
        "completed": 5,
        "created": 5,
        "already_caught": extra,
        "retries": extra,
        "history_reads": len(history_progress) - 1,
    }
    distinct: set[int] = set()
    observed_reads: list[int] = []
    observed_confirms = 0
    for actor, _method, path, body in world.requests:
        if actor != "attendee0":
            continue
        if path == "/api/catches/confirm/":
            observed_confirms += 1
            distinct.add(world.gameplay.fursuit_of[str(body["payload"])])
        elif path == "/api/catches/":
            observed_reads.append(len(distinct))
    # The final repeated count is the real comparator's required complete history
    # read. Before that, history follows configured cadence and final completion.
    assert observed_confirms == confirmations
    assert observed_reads == history_progress
    assert len(world.gameplay.catches) == 5


def test_actor_seed_and_target_ordinals_survive_shifted_ids_and_global_randomness() -> (
    None
):
    config = resolve_behavior_config(
        {"pool": "alpha", "family": "baseline", "casual": 2}
    )
    first = run(PopulationWorld(config), config, seed=9347)
    previous_random_state = random.getstate()
    try:
        random.seed(987654)
        for _ in range(40):
            random.random()
        shifted = run(PopulationWorld(config, id_offset=90_000), config, seed=9347)
    finally:
        random.setstate(previous_random_state)

    assert first.passed and shifted.passed
    assert first.trace == shifted.trace
    assert first.summaries == shifted.summaries
    assert len(first.expectations.made) == 16
    assert all(
        "SENTINEL" not in str(step) and "900" not in str(step) for step in shifted.trace
    )
    # One actor consuming fewer random choices must not perturb another actor's stream.
    reduced = resolve_behavior_config({**config, "active_budget": 1})
    independent = run(PopulationWorld(reduced), reduced, seed=9347)
    # With two casuals, attendee3 is the heavy collector in both populations.
    assert tuple(step for step in first.trace if step[0] == "attendee3") == tuple(
        step for step in independent.trace if step[0] == "attendee3"
    )


def test_public_fixture_owner_facts_include_uncaught_targets_across_shifted_ids() -> (
    None
):
    """AC12: reconciliation needs public owner facts for every validated fixture."""
    config = resolve_behavior_config(
        {
            "pool": "alpha",
            "family": "baseline",
            "casual": 1,
            "active": 0,
            "heavy": 0,
            "retry_prone": 0,
        }
    )

    original = run(PopulationWorld(config), config)
    shifted = run(PopulationWorld(config, id_offset=90_000), config)

    assert original.passed and shifted.passed
    assert len(original.expectations.made) == len(shifted.expectations.made) == 1
    assert original.expectations.target_owners == {
        100: "owner0",
        101: "owner0",
        102: "owner0",
        103: "owner0",
        200: "owner1",
        201: "owner1",
        202: "owner1",
        203: "owner1",
    }
    assert shifted.expectations.target_owners == {
        90100: "owner0",
        90101: "owner0",
        90102: "owner0",
        90103: "owner0",
        90200: "owner1",
        90201: "owner1",
        90202: "owner1",
        90203: "owner1",
    }


def test_exhaustion_finishes_once_and_soak_revisits_the_plan_after_activation_breaks() -> (
    None
):
    config = resolve_behavior_config(
        {
            "pool": "alpha",
            "family": "soak",
            "cycles": 2,
            "normal_owners": 1,
            "popular_owners": 0,
            "fursuits": 1,
            "casual": 0,
            "active": 0,
            "retry_prone": 0,
            "heavy": 1,
            "activation_break": True,
        }
    )
    world = PopulationWorld(config)
    result = run(world, config)

    assert result.passed
    heavy = result.summaries["heavy"]
    assert {
        key: heavy[key]
        for key in (
            "completed",
            "created",
            "already_caught",
            "exhausted",
            "unused_budget",
            "cycles",
        )
    } == {
        "completed": 2,
        "created": 1,
        "already_caught": 1,
        "exhausted": 1,
        "unused_budget": 7,
        "cycles": 2,
    }
    lifecycle = [
        (path, body["is_active"])
        for actor, method, path, body in world.requests
        if actor == "owner0" and method == "PUT"
    ]
    activation = f"/api/conventions/{CONVENTION_ID}/fursuit-activations/100/"
    session_events = [
        active for path, active in lifecycle if path == activation + "catch-session/"
    ]
    assert session_events == [True, False, True, False]
    activation_events = [active for path, active in lifecycle if path == activation]
    assert False in activation_events
    inactive = activation_events.index(False)
    assert activation_events[inactive + 1 :] == [True]
    assert len(world.gameplay.catches) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "ambiguous-positive",
        "wrong-status",
        "wrong-target",
        "wrong-confirm-target",
        "nonconvergent",
        "wrong-history",
    ],
)
def test_unexpected_outcome_stops_collection_and_preserves_partial_expectations(
    fault: str,
) -> None:
    config = resolve_behavior_config({"pool": "alpha", "family": "baseline"})
    world = PopulationWorld(config)
    world.fault = fault
    result = run(world, config)

    assert world.failed
    assert not result.passed and result.failure is not None
    assert "SENTINEL" not in str(result.failure)
    confirmations = [
        actor
        for actor, _method, path, _body in world.requests
        if path == "/api/catches/confirm/"
    ]
    assert world.failure_at is not None
    for actor, method, path, body in world.requests[world.failure_at + 1 :]:
        assert (
            actor.startswith("owner")
            and method == "PUT"
            and path.endswith("/catch-session/")
            and body == {"is_active": False}
        ), "failure must stop all future modeled actions"
    if fault in {"ambiguous-positive", "wrong-status", "wrong-confirm-target"}:
        assert len(confirmations) == 1
        assert len(result.expectations.attempts) == 1
        assert result.expectations.made == {}
        assert len(world.gameplay.catches) == 1
    if fault == "wrong-target":
        assert confirmations == []
        assert result.expectations.attempts == set()
