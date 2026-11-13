"""Catch request traffic: scenario version 3 under bounded concurrent load (#508).

Catchers preview a suit's reusable tag and submit a catch request. Owners read
their incoming requests on a poll, wait a seeded review delay, and approve or
decline. The seed chooses the automatic suits and every owner decision from
stable labels, so a rerun makes the same choices.
"""

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
    arm_request_session,
    get_value,
    list_items,
    positive_number,
    read_history,
    replace_tag,
    step,
    text_value,
)
from tailtag_simulator.population_reconciliation import (
    PopulationExpectations,
    RequestFact,
)
from tailtag_simulator.reconciliation import Made
from tailtag_simulator.reports_v2 import V6_COUNTERS
from tailtag_simulator.safety import SafetyAborted, active_runtime
from tailtag_simulator.traffic import Clock, Entry, TrafficRuntime, run_schedule
from tailtag_simulator.traffic_effects import RetryExhausted, TrafficEffects

_DEFAULT_CLOCK = Clock()
_PREVIEW = "/api/catches/preview/"
_REQUESTS = "/api/catches/requests/"
_INCOMING = "/api/catches/incoming-requests/"


@dataclass(frozen=True)
class RequestPopulationRun:
    population: PopulationRun
    traffic: dict[str, object]


class RequestTrafficCancelled(asyncio.CancelledError):
    """Cancellation with partial facts, after task-owned work has terminated."""

    def __init__(self, population: PopulationRun) -> None:
        super().__init__()
        self.population = population


class _CountedClient(ApiClient):
    """Count setup and history traffic as `auxiliary`, with no injected effects."""

    def __init__(self, client: ApiClient, runtime: TrafficRuntime) -> None:
        super().__init__(client._client)  # pyright: ignore[reportPrivateUsage]
        self.original = client
        self.runtime = runtime

    async def _send(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, Upload] | None = None,
    ) -> Reply:
        async def counted() -> Reply:
            self.runtime.record("sent")
            return await self.original._send(  # pyright: ignore[reportPrivateUsage]
                method, path, body, data=data, files=files
            )

        return await self.runtime.request(counted, operation="auxiliary")


class _ReadClient(ApiClient):
    """Meter catch history reads as `read`, with the configured effects."""

    def __init__(
        self, client: ApiClient, effects: TrafficEffects, rng: random.Random
    ) -> None:
        super().__init__(client._client)  # pyright: ignore[reportPrivateUsage]
        self.original = client
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

        return await self.effects.call("read", send, self.rng)


def _stream(seed: int, *labels: str) -> random.Random:
    digest = hashlib.sha256(":".join((str(seed), *labels)).encode()).digest()
    return random.Random(int.from_bytes(digest))


async def _sleep_or_drain(clock: Clock, seconds: float, drain: asyncio.Event) -> None:
    """Sleep on the injected clock, waking early when the drain starts."""
    sleeper = asyncio.ensure_future(clock.sleep(seconds))
    waiter = asyncio.ensure_future(drain.wait())
    try:
        await asyncio.wait((sleeper, waiter), return_when=asyncio.FIRST_COMPLETED)
    finally:
        sleeper.cancel()
        waiter.cancel()
        await asyncio.gather(sleeper, waiter, return_exceptions=True)


async def _reply(reply: Reply) -> Reply:
    """Pass an already observed real reply through the shared strict parser."""
    return reply


async def simulate_request_population(
    context: PopulationContext,
    config: Mapping[str, object],
    seed: int,
    *,
    clock: Clock = _DEFAULT_CLOCK,
    runtime: TrafficRuntime | None = None,
) -> RequestPopulationRun:
    """Await all modeled work and return only observable, sanitized partial facts."""
    runtime = runtime or TrafficRuntime(config, clock=clock, request_flow=True)
    runtime.bind_seed(seed)
    effects = TrafficEffects(config, runtime, clock)
    failure = cast(dict[str, object], config["failure"])
    review = cast(dict[str, object], config["review"])
    summaries: dict[str, dict[str, int]] = {
        persona: dict.fromkeys(sorted(V6_COUNTERS), 0) for persona in PERSONAS
    }
    for persona, key in zip(
        PERSONAS, (*PERSONAS[:4], "normal_owners", "popular_owners"), strict=True
    ):
        summaries[persona]["actors"] = cast(int, config[key])
    expectations = PopulationExpectations()
    convention = 0
    failed = False
    bootstrap = PopulationContext(
        tuple(_CountedClient(c, runtime) for c in context.owners),
        tuple(_CountedClient(c, runtime) for c in context.attendees),
    )
    targets: list[_Target] = []
    automatic: set[int] = set()
    deadlines: dict[int, float] = {}
    locks: dict[int, asyncio.Lock] = {}
    streams: dict[str, random.Random] = {}
    transitioned: set[int] = set()
    # A trio is settled once its catcher's submissions have all returned, so an
    # owner never decides a request that a retry or repeat is still observing.
    settled: set[tuple[str, int]] = set()
    labels: dict[int, str] = {}
    drain = asyncio.Event()

    def action(persona: str) -> None:
        summaries[persona]["actions"] += 1

    def owner_persona(owner: int) -> str:
        return (
            "normal_owner"
            if owner < cast(int, config["normal_owners"])
            else "popular_owner"
        )

    def require(valid: bool) -> None:
        if not valid:
            raise IntegrityFailed("traffic", "valid", "shape")

    def activation(target: _Target) -> str:
        return f"/api/conventions/{convention}/fursuit-activations/{target.id}/"

    def refused(reply: Reply) -> None:
        # The load model plans no refusal: any 429 is a correctness failure.
        if reply.status == 429:
            raise IntegrityFailed("submit", "no 429", "429")

    async def submit(
        actor: _Actor,
        target: _Target,
        payload: str,
        *,
        establishing: bool = False,
        expired_missing: bool = False,
    ) -> None:
        action(actor.persona)
        pair = (actor.label, target.id)
        expectations.pairs.setdefault(pair, "forbidden")
        negative = expired_missing or (
            not establishing
            and failure["domain_case"] != "none"
            and not failure["recover_existing"]
        )

        def sent() -> None:
            expectations.attempts.add(pair)
            if (
                pair not in expectations.requests
                and pair not in expectations.made
                and expectations.pairs.get(pair) != "unresolved"
            ):
                expectations.pairs[pair] = "unresolved"
                runtime.record("unresolved")

        rng = random.Random(streams[actor.label].getrandbits(256))
        reply = await effects.call(
            "submit",
            lambda: actor.client.post(_REQUESTS, {"payload": payload}),
            rng,
            on_sent=sent,
        )
        if negative:
            await step(
                "submit",
                _reply(reply),
                404,
                "catch_target_unavailable",
                shape=lambda b: get_value(b, "code") == "catch_target_unavailable",
            )
            if expectations.pairs.get(pair) == "unresolved":
                runtime.record("unresolved", -1)
            expectations.pairs[pair] = "forbidden"
            runtime.expected_rejection("submit")
            summaries[actor.persona]["expected_rejections"] += 1
            return
        refused(reply)
        if reply.status not in (200, 201):
            if 200 <= reply.status < 300:
                raise IntegrityFailed("submit", "200/201", str(reply.status))
            raise StepFailed("submit", "200/201", str(reply.status))
        outcome = text_value(reply.body, "outcome")
        if reply.status == 201:
            expected = ("approved",) if target.id in automatic else ("pending",)
        else:
            expected = ("already_pending", "already_caught")
        require(outcome in expected)
        body = await step("submit", _reply(reply), reply.status, outcome)
        if outcome in ("pending", "already_pending", "approved"):
            fact = RequestFact(
                positive_number(body, "request", "id"),
                text_value(body, "request", "state"),
                text_value(body, "request", "requested_at"),
            )
            require(
                fact.id > 0
                and bool(fact.requested_at)
                and positive_number(body, "request", "fursuit", "id") == target.id
                and positive_number(body, "request", "convention_id") == convention
            )
            known = expectations.requests.get(pair)
            require(known is None or known.id == fact.id)
            if known is None or outcome != "already_pending":
                expectations.requests[pair] = fact
            labels[fact.id] = actor.label
        if outcome in ("approved", "already_caught"):
            made = Made(
                positive_number(body, "catch", "id"),
                text_value(body, "catch", "caught_at"),
            )
            require(
                made.catch_id > 0
                and positive_number(body, "catch", "convention_id") == convention
                and text_value(body, "catch", "fursuit", "tailtag_id") == target.tailtag
            )
            previous = expectations.made.get(pair)
            if previous is not None:
                expectations.seen.setdefault(pair, []).append(made)
                require(previous == made)
            else:
                expectations.made[pair] = made
            if outcome == "approved":
                fact = expectations.requests[pair]
                require(made.caught_at == fact.requested_at)
        if expectations.pairs.get(pair) == "unresolved":
            runtime.record("unresolved", -1)
        decided = expectations.requests.get(pair)
        if not (
            outcome == "already_pending"
            and decided is not None
            and decided.state != "pending"
        ):
            # A stale `already_pending` answered before an owner decision must
            # not undo that decision.
            expectations.pairs[pair] = (
                "required" if outcome in ("approved", "already_caught") else "pending"
            )
        summaries[actor.persona]["automatic" if outcome == "approved" else outcome] += 1

    async def preview(actor: _Actor, target: _Target, payload: str) -> None:
        action(actor.persona)
        reply = await effects.call(
            "preview",
            lambda: actor.client.post(_PREVIEW, {"payload": payload}),
            streams[actor.label],
        )
        expired = (
            failure["domain_case"] == "expired"
            and clock.wall_time() >= deadlines[target.id]
        )
        if expired and reply.status != 200:
            await step("preview", _reply(reply), 404, "catch_target_unavailable")
            runtime.expected_rejection("preview")
            return
        await step(
            "preview",
            _reply(reply),
            200,
            shape=lambda b: (
                positive_number(b, "convention_id") == convention
                and positive_number(b, "fursuit", "id") == target.id
            ),
        )

    async def visit(
        actor: _Actor,
        target: _Target,
        phase: Literal["all", "establish", "recover"] = "all",
    ) -> None:
        async def journey() -> None:
            nonlocal failed
            pair = (actor.label, target.id)
            known = expectations.requests.get(pair)
            if known is not None and known.state == "declined":
                # A later cycle never resubmits a declined pair: the cooldown
                # would refuse it, and the load model plans no 429.
                return
            # Owners wait until this visit's submissions have all returned.
            settled.discard(pair)
            owner = bootstrap.owners[target.owner]
            path = activation(target)
            case = failure["domain_case"]
            if case in ("replaced", "stopped") and target.id in transitioned:
                target.payload = await arm_request_session(
                    owner, path, target.id, automatic=target.id in automatic
                )
                transitioned.discard(target.id)
            payload = target.payload
            if phase != "recover":
                await preview(actor, target, payload)
            expired = case == "expired" and clock.wall_time() >= deadlines[target.id]
            expired_missing = (
                expired
                and failure["recover_existing"]
                and pair not in expectations.requests
                and pair not in expectations.made
            )
            if expired_missing:
                failed = True
            if case != "none":
                if (
                    failure["recover_existing"]
                    and not expired_missing
                    and phase != "recover"
                ):
                    await submit(actor, target, payload, establishing=True)
                if phase == "establish":
                    return
                if case == "replaced":
                    action(owner_persona(target.owner))
                    await replace_tag(owner, target.id)
                elif case == "stopped":
                    action(owner_persona(target.owner))
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
                        submit(
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
                await submit(
                    actor, target, payload, expired_missing=bool(expired_missing)
                )
                for _ in range(cast(int, config[f"{actor.prefix}_repeats"])):
                    summaries[actor.persona]["retries"] += 1
                    await submit(
                        actor, target, payload, expired_missing=bool(expired_missing)
                    )
            settled.add(pair)
            summaries[actor.persona]["completed"] += 1

        if failure["domain_case"] in ("replaced", "stopped"):
            async with locks[target.id]:
                await journey()
        else:
            await journey()

    async def read_requests(actor: _Actor) -> None:
        """Read the player's request list and catch history; both must agree.

        A lost response to an automatic approval leaves only the catch: the
        retry answers `already_caught` with no request. The list then names
        that approved request, and its request time must equal the catch time.
        """
        action(actor.persona)
        reply = await effects.call(
            "read",
            lambda: actor.client.get(f"{_REQUESTS}?convention_id={convention}"),
            streams[actor.label],
        )
        body = await step("requests", _reply(reply), 200)
        rows = list_items(get_value(body, "results"))
        for row in rows:
            pair = (actor.label, positive_number(row, "fursuit", "id"))
            made = expectations.made.get(pair)
            if pair not in expectations.requests and made is not None:
                require(
                    get_value(row, "state") == "approved"
                    and text_value(row, "requested_at") == made.caught_at
                )
                fact = RequestFact(
                    positive_number(row, "id"), "approved", made.caught_at
                )
                expectations.requests[pair] = fact
                labels[fact.id] = actor.label
        listed = {positive_number(row, "id") for row in rows}
        wanted = {
            fact.id
            for (label, _), fact in expectations.requests.items()
            if label == actor.label
        }
        require(listed == wanted)
        action(actor.persona)
        history = await read_history(
            _ReadClient(actor.client, effects, streams[actor.label]), convention
        )
        made_here = {
            fursuit: made
            for (label, fursuit), made in expectations.made.items()
            if label == actor.label
        }
        for entry_row in history:
            made = made_here.get(entry_row.fursuit)
            if made is not None:
                require(made == Made(entry_row.catch_id, entry_row.caught_at))
            else:
                # An owner can approve a pending request between the two reads.
                fact = expectations.requests.get((actor.label, entry_row.fursuit))
                require(fact is not None and fact.state == "pending")
        require(set(made_here) <= {entry_row.fursuit for entry_row in history})
        summaries[actor.persona]["history_reads"] += 1

    async def entry(item: Entry) -> bool:
        nonlocal failed
        actor = actors[item.actor]
        try:
            if failure["domain_case"] == "expired" and failure["recover_existing"]:
                for target in actor.plan:
                    await visit(actor, target, "establish")
                for target in actor.plan:
                    await visit(actor, target, "recover")
            else:
                for target in actor.plan:
                    await visit(actor, target)
            await read_requests(actor)
            summaries[actor.persona]["cycles"] += 1
            return True
        except SafetyAborted as safety_failure:
            failed = True
            runtime.stop(
                "correctness" if safety_failure.reason == "correctness" else "external"
            )
            return False
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

    async def decide(owner: int, row: object, persona: str) -> None:
        request_id = positive_number(row, "id")
        target_id = positive_number(row, "fursuit", "id")
        label = labels.get(request_id)
        require(label is not None)
        pair = (cast(str, label), target_id)
        target = next(t for t in targets if t.id == target_id)
        approve = _stream(
            seed, "decision", cast(str, label), target.label
        ).random() < cast(float, review["approve_rate"])
        action(persona)
        base = f"{_INCOMING}{request_id}/"
        if approve:
            reply = await effects.call(
                "decide",
                lambda: context.owners[owner].post(f"{base}approve/"),
                streams[f"owner{owner}"],
            )
            body = await step(
                "approve",
                _reply(reply),
                200,
                shape=lambda b: (
                    get_value(b, "request", "state") == "approved"
                    and positive_number(b, "catch", "id") > 0
                ),
            )
            made = Made(
                positive_number(body, "catch", "id"),
                text_value(body, "catch", "caught_at"),
            )
            fact = expectations.requests[pair]
            require(made.caught_at == fact.requested_at)
            expectations.made[pair] = made
            expectations.requests[pair] = RequestFact(
                fact.id, "approved", fact.requested_at
            )
            expectations.pairs[pair] = "required"
            summaries[persona]["approved"] += 1
        else:
            reply = await effects.call(
                "decide",
                lambda: context.owners[owner].post(f"{base}decline/", {"block": False}),
                streams[f"owner{owner}"],
            )
            await step(
                "decline",
                _reply(reply),
                200,
                shape=lambda b: get_value(b, "state") == "declined",
            )
            fact = expectations.requests[pair]
            expectations.requests[pair] = RequestFact(
                fact.id, "declined", fact.requested_at
            )
            expectations.pairs[pair] = "forbidden"
            summaries[persona]["declined"] += 1

    async def review_owner(owner: int) -> None:
        """Poll, wait each request's seeded delay, decide; drain when told."""
        persona = owner_persona(owner)
        client = context.owners[owner]
        first_seen: dict[int, float] = {}
        poll = cast(float, review["poll_seconds"])
        low = cast(float, review["delay_min_seconds"])
        high = cast(float, review["delay_max_seconds"])
        while True:
            draining = drain.is_set()
            action(persona)
            reply = await effects.call(
                "review",
                lambda: client.get(f"{_INCOMING}?convention_id={convention}"),
                streams[f"owner{owner}"],
            )
            body = await step("incoming", _reply(reply), 200)
            pending = [
                row
                for row in list_items(get_value(body, "results"))
                if get_value(row, "state") == "pending"
            ]
            now = clock.monotonic()
            for row in pending:
                request_id = positive_number(row, "id")
                label = labels.get(request_id)
                pair = (label or "", positive_number(row, "fursuit", "id"))
                if label is None or pair not in settled:
                    continue
                seen = first_seen.setdefault(request_id, now)
                target = next(t for t in targets if t.id == pair[1])
                delay = _stream(seed, "delay", label, target.label).uniform(low, high)
                if draining or now - seen >= delay:
                    await decide(owner, row, persona)
            if draining and not any(
                (
                    labels.get(positive_number(row, "id"), ""),
                    positive_number(row, "fursuit", "id"),
                )
                in settled
                for row in pending
            ):
                return
            if not draining:
                await _sleep_or_drain(clock, poll, drain)

    owners: list[asyncio.Task[None]] = []
    try:
        convention, targets, actors = await prepare_population(
            bootstrap, config, seed, expectations, summaries, lambda *a: action(a[1])
        )
        for index, actor in enumerate(actors):
            actor.client = context.attendees[index]
            streams[actor.label] = _stream(seed, "effects", actor.label)
        for owner in range(len(context.owners)):
            streams[f"owner{owner}"] = _stream(seed, "effects", f"owner{owner}")
        share = cast(float, review["automatic_share"])
        for target in targets:
            if _stream(seed, "automatic", target.label).random() < share:
                automatic.add(target.id)
        for target in targets:
            owner = bootstrap.owners[target.owner]
            path = activation(target)
            persona = owner_persona(target.owner)
            action(persona)
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

            action(persona)
            target.payload = await arm_request_session(
                owner,
                path,
                target.id,
                automatic=target.id in automatic,
                observed_session=session,
            )
            summaries[persona]["completed"] += 1
            locks[target.id] = asyncio.Lock()
        owners = [
            asyncio.create_task(review_owner(owner))
            for owner in range(len(context.owners))
        ]
        await run_schedule(config, seed, entry, runtime=runtime, clock=clock)
        drain.set()
        draining_from = clock.monotonic()
        await asyncio.gather(*owners)
        # Owner draining is workload too: keep it inside the measured window.
        runtime.drain_seconds += max(0.0, clock.monotonic() - draining_from)
    except asyncio.CancelledError:
        runtime.stop("external")
        for task in owners:
            task.cancel()
        await asyncio.gather(*owners, return_exceptions=True)
        raise RequestTrafficCancelled(
            PopulationRun(
                expectations, convention, False, summaries, "FAIL_SIMULATION", ()
            )
        ) from None
    except SafetyAborted as safety_failure:
        failed = True
        runtime.stop(
            "correctness" if safety_failure.reason == "correctness" else "external"
        )
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
    finally:
        for task in owners:
            if not task.done():
                task.cancel()
        await asyncio.gather(*owners, return_exceptions=True)
    snapshot = runtime.snapshot()
    pending = any(state == "pending" for state in expectations.pairs.values())
    passed = (
        not failed
        and not pending
        and snapshot["stop_reason"] is None
        and not snapshot["unresolved"]
    )
    population = PopulationRun(
        expectations,
        convention,
        passed,
        summaries,
        None if passed else "FAIL_SIMULATION",
        (),
    )
    return RequestPopulationRun(population, snapshot)
