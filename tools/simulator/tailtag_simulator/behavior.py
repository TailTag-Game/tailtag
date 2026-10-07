"""Finite public-API convention behavior, independent of orchestration channels."""

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from tailtag_simulator.behavior_config import PERSONAS
from tailtag_simulator.client import ApiClient
from tailtag_simulator.gameplay import (
    StepFailed,
    arm_session,
    get_value,
    list_items,
    positive_number,
    read_history,
    step,
    stop_session,
    text_value,
)
from tailtag_simulator.population_reconciliation import PopulationExpectations
from tailtag_simulator.reconciliation import Made


@dataclass(frozen=True)
class PopulationContext:
    owners: tuple[ApiClient, ...]
    attendees: tuple[ApiClient, ...]


@dataclass(frozen=True)
class PopulationRun:
    expectations: PopulationExpectations
    convention: int
    passed: bool
    summaries: dict[str, dict[str, int]]
    failure: str | None
    trace: tuple[tuple[str, str, str], ...]


@dataclass
class _Target:
    owner: int
    id: int
    tailtag: str
    label: str
    payload: str = field(default="", repr=False)


@dataclass
class _Actor:
    label: str
    persona: str
    prefix: str
    client: ApiClient
    plan: list[_Target]


async def simulate_population(
    context: PopulationContext, config: Mapping[str, object], seed: int
) -> PopulationRun:
    """Execute the resolved configuration; retain facts on any unexpected failure."""

    def number(key: str) -> int:
        return cast(int, config[key])

    counters = (
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
    )
    summaries: dict[str, dict[str, int]] = {
        persona: dict.fromkeys(counters, 0) for persona in PERSONAS
    }
    for persona, key in zip(
        PERSONAS, (*PERSONAS[:4], "normal_owners", "popular_owners"), strict=True
    ):
        summaries[persona]["actors"] = number(key)
    expectations = PopulationExpectations()
    trace: list[tuple[str, str, str]] = []
    convention = 0

    def action(actor: str, persona: str, name: str, target: str = "-") -> None:
        trace.append((actor, name, target))
        summaries[persona]["actions"] += 1

    def require(valid: bool) -> None:
        if not valid:
            raise StepFailed("population", "valid", "shape")

    async def history(actor: _Actor) -> None:
        action(actor.label, actor.persona, "history")
        rows = await read_history(actor.client, convention)
        actual = {row.fursuit: Made(row.catch_id, row.caught_at) for row in rows}
        wanted = {
            target: made
            for (label, target), made in expectations.made.items()
            if label == actor.label
        }
        require(actual == wanted)
        summaries[actor.persona]["history_reads"] += 1

    async def visit(actor: _Actor, target: _Target, phase: str = "all") -> None:
        summary = summaries[actor.persona]
        if phase != "duplicates":
            action(actor.label, actor.persona, "resolve", target.label)
            await step(
                "resolve",
                actor.client.post(
                    f"/api/conventions/{convention}/catch-credentials/resolve/",
                    {"payload": target.payload},
                ),
                200,
                shape=lambda b: (
                    positive_number(b, "convention_id") == convention
                    and text_value(b, "fursuit", "tailtag_id") == target.tailtag
                ),
            )
        pair = (actor.label, target.id)
        repeats = number(f"{actor.prefix}_repeats")
        confirmations = (
            range(1, repeats + 1)
            if phase == "duplicates"
            else range(1)
            if phase == "first"
            else range(repeats + 1)
        )
        for repeat in confirmations:
            previous = expectations.made.get(pair)
            action(
                actor.label,
                actor.persona,
                "retry" if repeat else "confirm",
                target.label,
            )
            expectations.attempts.add(pair)
            if repeat:
                summary["retries"] += 1
            body = await step(
                "confirm",
                actor.client.post(
                    "/api/catches/confirm/",
                    {"convention_id": convention, "payload": target.payload},
                ),
                200 if previous else 201,
                "already_caught" if previous else "created",
                shape=lambda b: (
                    positive_number(b, "catch", "id") > 0
                    and positive_number(b, "catch", "convention_id") == convention
                    and positive_number(b, "catch", "fursuit", "id") == target.id
                    and text_value(b, "catch", "fursuit", "tailtag_id")
                    == target.tailtag
                    and bool(text_value(b, "catch", "caught_at"))
                ),
            )
            made = Made(
                positive_number(body, "catch", "id"),
                text_value(body, "catch", "caught_at"),
            )
            if previous:
                expectations.seen.setdefault(pair, []).append(made)
                require(made == previous)
                summary["already_caught"] += 1
            else:
                expectations.made[pair] = made
                summary["created"] += 1
        if phase != "first" or not repeats:
            summary["completed"] += 1

    try:
        require(
            len(context.owners) == number("normal_owners") + number("popular_owners")
        )
        require(len(context.attendees) == sum(number(p) for p in PERSONAS[:4]))
        targets: list[_Target] = []
        identities: set[int] = set()
        for group, clients in (
            ("owner", context.owners),
            ("attendee", context.attendees),
        ):
            for ordinal, client in enumerate(clients):
                label = f"{group}{ordinal}"
                if group == "owner":
                    persona = (
                        "normal_owner"
                        if ordinal < number("normal_owners")
                        else "popular_owner"
                    )
                else:
                    position = ordinal
                    persona = PERSONAS[0]
                    for candidate in PERSONAS[:4]:
                        if position < number(candidate):
                            persona = candidate
                            break
                        position -= number(candidate)
                action(label, persona, "me")
                body = await step(
                    "me",
                    client.get("/api/me/"),
                    200,
                    shape=lambda b: positive_number(b, "id") > 0,
                )
                identity = positive_number(body, "id")
                require(identity not in identities)
                identities.add(identity)
                action(label, persona, "context")
                body = await step(
                    "context",
                    client.get("/api/conventions/active/"),
                    200,
                    shape=lambda b: (
                        positive_number(b, "enrollment", "convention", "id") > 0
                        and get_value(b, "enrollment", "is_active") is True
                    ),
                )
                observed = positive_number(body, "enrollment", "convention", "id")
                require(convention in (0, observed))
                convention = observed
                if group == "owner":
                    action(label, persona, "owned_fixtures")
                    body = await step(
                        "fursuits",
                        client.get("/api/fursuits/"),
                        200,
                        shape=lambda b: (
                            isinstance(b, list)
                            and len(cast(list[object], b)) == number("fursuits")
                        ),
                    )
                    owned = list_items(body)
                    require(
                        all(
                            positive_number(row, "id")
                            and text_value(row, "tailtag_id")
                            and get_value(row, "is_enabled") is True
                            for row in owned
                        )
                    )
                    for position, row in enumerate(
                        sorted(owned, key=lambda row: positive_number(row, "id"))
                    ):
                        target_id = positive_number(row, "id")
                        require(
                            expectations.target_owners.get(target_id, label) == label
                        )
                        expectations.target_owners[target_id] = label
                        targets.append(
                            _Target(
                                ordinal,
                                target_id,
                                text_value(row, "tailtag_id"),
                                f"owner{ordinal}:fursuit{position}",
                            )
                        )
                    action(label, persona, "activations")
                    activations = await step(
                        "activations",
                        client.get(
                            f"/api/conventions/{convention}/fursuit-activations/"
                        ),
                        200,
                    )
                    require(
                        isinstance(activations, list)
                        and len(list_items(cast(object, activations)))
                        == number("fursuits")
                    )
                    require(
                        {
                            positive_number(row, "fursuit_id")
                            for row in list_items(cast(object, activations))
                        }
                        == {t.id for t in targets if t.owner == ordinal}
                    )
                    require(
                        all(
                            positive_number(row, "convention_id") == convention
                            and get_value(row, "is_eligible") is True
                            for row in list_items(cast(object, activations))
                        )
                    )
        require(
            len({t.id for t in targets}) == len(targets)
            and len({t.tailtag for t in targets}) == len(targets)
        )
        actors: list[_Actor] = []
        for persona, prefix in zip(
            PERSONAS[:4], ("casual", "active", "heavy", "retry"), strict=True
        ):
            for _ in range(number(persona)):
                ordinal = len(actors)
                label = f"attendee{ordinal}"
                rng = random.Random(
                    int.from_bytes(
                        hashlib.sha256(f"{seed}:attendee:{ordinal}".encode()).digest()
                    )
                )
                available = (
                    [next(t for t in targets if t.owner == number("normal_owners"))]
                    if config["family"] == "hotspot"
                    else list(targets)
                )
                plan: list[_Target] = []
                while available and len(plan) < number(f"{prefix}_budget"):
                    weights = [
                        number(
                            "normal_weight"
                            if t.owner < number("normal_owners")
                            else "popular_weight"
                        )
                        for t in available
                    ]
                    selected = rng.choices(available, weights=weights, k=1)[0]
                    plan.append(selected)
                    available.remove(selected)
                unused = number(f"{prefix}_budget") - len(plan)
                summaries[persona]["exhausted"] += int(unused > 0)
                summaries[persona]["unused_budget"] += unused
                actors.append(
                    _Actor(label, persona, prefix, context.attendees[ordinal], plan)
                )
        for cycle in range(number("cycles")):
            for owner, client in enumerate(context.owners):
                persona = (
                    "normal_owner"
                    if owner < number("normal_owners")
                    else "popular_owner"
                )
                label = f"owner{owner}"
                for target in targets:
                    if target.owner != owner:
                        continue
                    activation = f"/api/conventions/{convention}/fursuit-activations/{target.id}/"
                    action(label, persona, "activate", target.label)
                    await step(
                        "activate",
                        client.put(activation, {"is_active": True}),
                        200,
                        shape=lambda b, target=target: (
                            get_value(b, "is_active") is True
                            and positive_number(b, "fursuit_id") == target.id
                            and positive_number(b, "convention_id") == convention
                        ),
                    )
                    action(label, persona, "arm_session", target.label)
                    target.payload = await arm_session(client, activation)
                    summaries[persona]["completed"] += 1
            visits = (
                [(actor, index) for actor in actors for index in range(len(actor.plan))]
                if config["family"] == "post-event"
                else [
                    (actor, index)
                    for index in range(max(len(a.plan) for a in actors))
                    for actor in actors
                    if index < len(actor.plan)
                ]
            )
            phases = (
                ("first", "duplicates") if config["family"] == "retry" else ("all",)
            )
            for phase in phases:
                for actor, index in visits:
                    repeats = number(f"{actor.prefix}_repeats")
                    if phase == "duplicates" and not repeats:
                        continue
                    await visit(actor, actor.plan[index], phase)
                    if phase == "first" and repeats:
                        continue
                    cadence = number(f"{actor.prefix}_history")
                    final = index + 1 == len(actor.plan)
                    if final or (cadence and (index + 1) % cadence == 0):
                        await history(actor)
                    if final:
                        summaries[actor.persona]["cycles"] += 1
            for owner, client in enumerate(context.owners):
                persona = (
                    "normal_owner"
                    if owner < number("normal_owners")
                    else "popular_owner"
                )
                for target in targets:
                    if target.owner != owner:
                        continue
                    activation = f"/api/conventions/{convention}/fursuit-activations/{target.id}/"
                    action(f"owner{owner}", persona, "stop_session", target.label)
                    await stop_session(client, activation)
                    if cycle + 1 < number("cycles") and config["activation_break"]:
                        action(f"owner{owner}", persona, "deactivate", target.label)
                        await step(
                            "deactivate",
                            client.put(activation, {"is_active": False}),
                            200,
                            shape=lambda b: get_value(b, "is_active") is False,
                        )
                summaries[persona]["cycles"] += 1
    except Exception:  # noqa: BLE001 - no external error or response details escape
        return PopulationRun(
            expectations, convention, False, summaries, "FAIL_SIMULATION", tuple(trace)
        )
    return PopulationRun(expectations, convention, True, summaries, None, tuple(trace))
