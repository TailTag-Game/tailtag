"""Stateful public gameplay under bounded concurrent convention traffic."""

import asyncio
import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from tailtag_simulator.behavior import (
    PopulationContext,
    PopulationRun,
    _Actor,  # pyright: ignore[reportPrivateUsage]
    _Target,  # pyright: ignore[reportPrivateUsage]
    prepare_population,
)
from tailtag_simulator.behavior_config import PERSONAS
from tailtag_simulator.client import (
    ApiClient,
    Reply,
    RequestFailed,
    TransportFailed,
    Upload,
)
from tailtag_simulator.gameplay import (
    IntegrityFailed,
    StepFailed,
    arm_session,
    get_value,
    positive_number,
    read_history,
    step,
    text_value,
)
from tailtag_simulator.population_reconciliation import PopulationExpectations
from tailtag_simulator.reconciliation import Made
from tailtag_simulator.safety import active_runtime
from tailtag_simulator.traffic import Clock, Entry, TrafficRuntime, run_schedule
from tailtag_simulator.traffic_effects import RetryExhausted, TrafficEffects


@dataclass(frozen=True)
class TrafficPopulationRun:
    population: PopulationRun
    traffic: dict[str, object]


class TrafficCancelled(asyncio.CancelledError):
    """Cancellation with partial facts, after task-owned work has terminated."""

    def __init__(self, population: PopulationRun) -> None:
        super().__init__()
        self.population = population


_DEFAULT_CLOCK = Clock()


class _CountedClient(ApiClient):
    """Reuse public parsing with operation-local accounting and effects."""

    def __init__(
        self,
        client: ApiClient,
        runtime: TrafficRuntime,
        effects: TrafficEffects | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(client._client)  # pyright: ignore[reportPrivateUsage]
        self.original = client
        self.runtime = runtime
        self.effects = effects
        self.rng = rng

    async def _send(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, Upload] | None = None,
    ) -> Reply:
        async def send() -> Reply:
            return await self.original._send(  # pyright: ignore[reportPrivateUsage]
                method, path, body, data=data, files=files
            )

        if self.effects is not None and self.rng is not None:
            return await self.effects.call("read", send, self.rng)

        async def counted() -> Reply:
            self.runtime.record("sent")
            return await send()

        return await self.runtime.request(counted)


async def simulate_traffic_population(
    context: PopulationContext,
    config: Mapping[str, object],
    seed: int,
    *,
    clock: Clock = _DEFAULT_CLOCK,
    runtime: TrafficRuntime | None = None,
) -> TrafficPopulationRun:
    """Await all modeled work and return only observable, sanitized partial facts."""
    runtime = runtime or TrafficRuntime(config, clock=clock)
    runtime.bind_seed(seed)
    effects = TrafficEffects(config, runtime, clock)
    failure = cast(dict[str, object], config["failure"])
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
        summaries[persona]["actors"] = cast(int, config[key])
    expectations = PopulationExpectations()
    # Aggregate action counts rather than retaining an unbounded per-entry trace.
    convention = 0
    failed = False
    bootstrap = PopulationContext(
        tuple(_CountedClient(c, runtime) for c in context.owners),
        tuple(_CountedClient(c, runtime) for c in context.attendees),
    )

    def action(_actor: str, persona: str, _name: str, _target: str = "-") -> None:
        summaries[persona]["actions"] += 1

    def require(valid: bool) -> None:
        if not valid:
            raise IntegrityFailed("traffic", "valid", "shape")

    def activation(target: _Target) -> str:
        return f"/api/conventions/{convention}/fursuit-activations/{target.id}/"

    deadlines: dict[int, float] = {}
    locks: dict[int, asyncio.Lock] = {}
    streams: dict[str, random.Random] = {}
    transitioned: set[int] = set()

    async def confirm(
        actor: _Actor,
        target: _Target,
        payload: str,
        *,
        establishing: bool = False,
        expired_missing: bool = False,
    ) -> None:
        action(actor.label, actor.persona, "confirm")
        pair = (actor.label, target.id)
        expectations.pairs.setdefault(pair, "forbidden")
        previous = expectations.made.get(pair)
        negative = expired_missing or (
            not establishing
            and failure["domain_case"] != "none"
            and not failure["recover_existing"]
        )

        def sent() -> None:
            expectations.attempts.add(pair)
            if previous is None and expectations.pairs.get(pair) != "unresolved":
                expectations.pairs[pair] = "unresolved"
                runtime.record("unresolved")

        rng = random.Random(streams[actor.label].getrandbits(256))
        reply = await effects.call(
            "confirm",
            lambda: actor.client.post("/api/catches/confirm/", {"payload": payload}),
            rng,
            on_sent=sent,
        )
        if negative:
            await step(
                "confirm",
                _reply(reply),
                404,
                "catch_target_unavailable",
                shape=lambda b: get_value(b, "code") == "catch_target_unavailable",
            )
            if expectations.pairs.get(pair) == "unresolved":
                runtime.record("unresolved", -1)
            expectations.pairs[pair] = "forbidden"
            runtime.record("expected_rejections")
            summaries[actor.persona]["expected_rejections"] += 1
            return
        # Concurrent duplicates and lost replies can observe already_caught first.
        if reply.status not in (200, 201):
            if 200 <= reply.status < 300:
                raise IntegrityFailed("confirm", "200/201", str(reply.status))
            raise StepFailed("confirm", "200/201", str(reply.status))
        require(previous is None or reply.status == 200)
        body = await step(
            "confirm",
            _reply(reply),
            reply.status,
            "created" if reply.status == 201 else "already_caught",
            shape=lambda b: (
                positive_number(b, "catch", "id") > 0
                and positive_number(b, "catch", "convention_id") == convention
                and text_value(b, "catch", "fursuit", "tailtag_id") == target.tailtag
                and bool(text_value(b, "catch", "caught_at"))
            ),
        )
        made = Made(
            positive_number(body, "catch", "id"), text_value(body, "catch", "caught_at")
        )
        previous = expectations.made.get(pair)
        if previous is not None:
            expectations.seen.setdefault(pair, []).append(made)
            require(previous == made)
        else:
            expectations.made[pair] = made
        if expectations.pairs.get(pair) == "unresolved":
            runtime.record("unresolved", -1)
        expectations.pairs[pair] = "required"
        summaries[actor.persona][
            "created" if reply.status == 201 else "already_caught"
        ] += 1

    async def visit(
        actor: _Actor,
        target: _Target,
        phase: Literal["all", "establish", "recover"] = "all",
    ) -> None:
        # Target transitions are serialized only for explicit domain experiments.
        async def journey() -> None:
            nonlocal failed
            owner = bootstrap.owners[target.owner]
            path = activation(target)
            case = failure["domain_case"]
            if case in ("stale", "stopped") and target.id in transitioned:
                target.payload = await arm_session(owner, path)
            payload = target.payload
            expired = case == "expired" and clock.wall_time() >= deadlines[target.id]
            if phase != "recover":
                action(actor.label, actor.persona, "resolve")
                reply = await effects.call(
                    "resolve",
                    lambda: actor.client.post(
                        f"/api/conventions/{convention}/catch-credentials/resolve/",
                        {"payload": payload},
                    ),
                    streams[actor.label],
                )
                expired = (
                    case == "expired" and clock.wall_time() >= deadlines[target.id]
                )
                if expired and reply.status != 200:
                    await step(
                        "resolve",
                        _reply(reply),
                        404,
                        "catch_target_unavailable",
                        shape=lambda b: (
                            get_value(b, "code") == "catch_target_unavailable"
                        ),
                    )
                    runtime.record("expected_rejections")
                else:
                    await step(
                        "resolve",
                        _reply(reply),
                        200,
                        shape=lambda b: (
                            positive_number(b, "convention_id") == convention
                            and text_value(b, "fursuit", "tailtag_id") == target.tailtag
                        ),
                    )
            expired_missing = (
                expired
                and failure["recover_existing"]
                and (actor.label, target.id) not in expectations.made
            )
            if expired_missing:
                failed = True
            if case != "none":
                if (
                    failure["recover_existing"]
                    and not expired_missing
                    and phase != "recover"
                ):
                    await confirm(actor, target, payload, establishing=True)
                if phase == "establish":
                    return
                if case == "stale":
                    await step(
                        "rotate",
                        owner.post(f"{path}catch-credential/rotate/"),
                        200,
                        shape=lambda b: bool(text_value(b, "payload")),
                    )
                elif case == "stopped":
                    await step(
                        "stop",
                        owner.put(f"{path}catch-session/", {"is_active": False}),
                        200,
                        shape=lambda b: get_value(b, "is_active") is False,
                    )
                elif case == "expired":
                    await clock.sleep(
                        max(0, deadlines[target.id] - clock.wall_time()) + 0.001
                    )
                transitioned.add(target.id)
                await clock.sleep(cast(float, failure["confirmation_delay_seconds"]))
            if failure["duplicate_overlap"]:
                tasks = [
                    asyncio.create_task(
                        confirm(
                            actor,
                            target,
                            payload,
                            expired_missing=bool(expired_missing),
                        )
                    )
                    for _ in range(2)
                ]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            else:
                await confirm(
                    actor, target, payload, expired_missing=bool(expired_missing)
                )
                for _ in range(cast(int, config[f"{actor.prefix}_repeats"])):
                    summaries[actor.persona]["retries"] += 1
                    await confirm(
                        actor, target, payload, expired_missing=bool(expired_missing)
                    )
            summaries[actor.persona]["completed"] += 1

        if failure["domain_case"] in ("stale", "stopped"):
            async with locks[target.id]:
                await journey()
        else:
            await journey()

    async def entry(item: Entry) -> bool:
        nonlocal failed
        actor = actors[item.actor]
        try:
            if failure["domain_case"] == "expired" and failure["recover_existing"]:
                # All planned catches must exist before any target's natural wait.
                for target in actor.plan:
                    await visit(actor, target, "establish")
                for target in actor.plan:
                    await visit(actor, target, "recover")
            else:
                for target in actor.plan:
                    await visit(actor, target)
            reader = _CountedClient(
                actor.client, runtime, effects, streams[actor.label]
            )
            action(actor.label, actor.persona, "history")
            rows = await read_history(reader, convention)
            require(
                {row.fursuit: Made(row.catch_id, row.caught_at) for row in rows}
                == {
                    target: made
                    for (label, target), made in expectations.made.items()
                    if label == actor.label
                }
            )
            summaries[actor.persona]["history_reads"] += 1
            summaries[actor.persona]["cycles"] += 1
            return True
        except RetryExhausted:
            failed = True
            summaries[actor.persona]["exhausted"] += 1
            return False
        except TransportFailed:
            failed = True
            return False
        except (IntegrityFailed, RequestFailed):
            failed = True
            safety = active_runtime()
            if safety is not None:
                safety.abort("correctness")
            runtime.stop("correctness")
            return False
        except Exception:  # noqa: BLE001 - ordinary rejection/transport failures
            failed = True
            return False

    try:
        convention, targets, actors = await prepare_population(
            bootstrap, config, seed, expectations, summaries, action
        )
        # Preparation clients are counted; ordinary actor clients receive effects once.
        for index, actor in enumerate(actors):
            actor.client = context.attendees[index]
            streams[actor.label] = random.Random(
                int.from_bytes(
                    hashlib.sha256(f"{seed}:effects:{actor.label}".encode()).digest()
                )
            )
        for target in targets:
            owner = bootstrap.owners[target.owner]
            path = activation(target)
            persona = (
                "normal_owner"
                if target.owner < cast(int, config["normal_owners"])
                else "popular_owner"
            )
            action(f"owner{target.owner}", persona, "activate")
            await step(
                "activate",
                owner.put(path, {"is_active": True}),
                200,
                shape=lambda b, target=target: (
                    get_value(b, "is_active") is True
                    and positive_number(b, "fursuit_id") == target.id
                    and positive_number(b, "convention_id") == convention
                ),
            )

            def session(body: object, target: _Target = target) -> None:
                if failure["domain_case"] == "expired":
                    expires = text_value(body, "expires_at")
                    deadline = datetime.fromisoformat(expires)
                    require(deadline.tzinfo is not None)
                    deadlines[target.id] = deadline.timestamp()
                    require(deadlines[target.id] > clock.wall_time())

            action(f"owner{target.owner}", persona, "arm_session")
            target.payload = await arm_session(owner, path, observed_session=session)
            summaries[persona]["completed"] += 1
            locks[target.id] = asyncio.Lock()
        await run_schedule(config, seed, entry, runtime=runtime, clock=clock)
    except asyncio.CancelledError:
        runtime.stop("external")
        raise TrafficCancelled(
            PopulationRun(
                expectations, convention, False, summaries, "FAIL_SIMULATION", ()
            )
        ) from None
    except TransportFailed:
        failed = True
    except (IntegrityFailed, RequestFailed):
        safety = active_runtime()
        if safety is not None:
            safety.abort("correctness")
        failed = True
        if runtime.snapshot()["stop_reason"] is None:
            runtime.stop("correctness")
    except Exception:  # noqa: BLE001 - ordinary rejection/transport failures
        failed = True
    snapshot = runtime.snapshot()
    passed = (
        not failed and snapshot["stop_reason"] is None and not snapshot["unresolved"]
    )
    population = PopulationRun(
        expectations,
        convention,
        passed,
        summaries,
        None if passed else "FAIL_SIMULATION",
        (),
    )
    return TrafficPopulationRun(population, snapshot)


async def _reply(reply: Reply) -> Reply:
    """Pass an already observed real reply through the shared strict parser."""
    return reply
