"""Shared public fixture discovery and seeded actor plans for convention runs."""

import hashlib
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from tailtag_simulator.behavior_config import PERSONAS
from tailtag_simulator.client import ApiClient
from tailtag_simulator.gameplay import (
    IntegrityFailed,
    get_value,
    list_items,
    positive_number,
    step,
    text_value,
)
from tailtag_simulator.population_reconciliation import PopulationExpectations


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


async def prepare_population(
    context: PopulationContext,
    config: Mapping[str, object],
    seed: int,
    expectations: PopulationExpectations,
    summaries: dict[str, dict[str, int]],
    action: Callable[..., None],
) -> tuple[int, list[_Target], list[_Actor]]:
    """Discover public fixtures and build stable stateful actor plans for both versions."""

    def number(key: str) -> int:
        return cast(int, config[key])

    def require(valid: bool) -> None:
        if not valid:
            raise IntegrityFailed("population", "valid", "shape")

    convention = 0
    require(len(context.owners) == number("normal_owners") + number("popular_owners"))
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
                    require(expectations.target_owners.get(target_id, label) == label)
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
                    client.get(f"/api/conventions/{convention}/fursuit-activations/"),
                    200,
                )
                require(
                    isinstance(activations, list)
                    and len(list_items(cast(object, activations))) == number("fursuits")
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
    return convention, targets, actors
