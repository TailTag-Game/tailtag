"""Seeded operation-local effects and bounded retries around protected real calls."""

import random
from collections.abc import Awaitable, Callable, Mapping
from typing import cast

import httpx

from tailtag_simulator.client import Reply, TransportFailed
from tailtag_simulator.gameplay import StepFailed
from tailtag_simulator.traffic import Clock, TrafficRuntime


class RetryExhausted(StepFailed):
    """An actor exhausted its configured attempts."""

    def __init__(self) -> None:
        super().__init__("retry", "completed", "exhausted")


class InjectedFailure(Exception):
    """A simulated detail-free client failure."""


class TrafficEffects:
    def __init__(
        self, config: Mapping[str, object], runtime: TrafficRuntime, clock: Clock
    ) -> None:
        self.failure = cast(dict[str, object], config["failure"])
        self.retry = cast(dict[str, object], config["retry"])
        self.runtime = runtime
        self.clock = clock

    async def call(
        self,
        operation: str,
        send: Callable[[], Awaitable[Reply]],
        rng: random.Random,
        *,
        on_sent: Callable[[], None] = lambda: None,
    ) -> Reply:
        selected = operation in cast(list[str], self.failure["operations"])
        for attempt in range(cast(int, self.retry["attempts"])):
            # Draw before the request to keep intended choices independent of completion.
            pre, outcome = rng.random(), rng.random()

            async def affected(pre: float = pre) -> Reply:
                if selected and pre < cast(
                    float, self.failure["pre_send_failure_rate"]
                ):
                    self.runtime.record("injected")
                    raise InjectedFailure
                self.runtime.record("sent")
                on_sent()
                return await send()

            try:
                if selected:
                    await self.clock.sleep(
                        cast(float, self.failure["pre_send_delay_seconds"])
                    )
                reply = await self.runtime.request(affected)
                if selected:
                    await self.clock.sleep(
                        cast(float, self.failure["response_delay_seconds"])
                    )
                    if outcome < cast(float, self.failure["lost_response_rate"]) + cast(
                        float, self.failure["timeout_rate"]
                    ):
                        self.runtime.record("injected")
                        raise InjectedFailure
                if reply.status not in (502, 503, 504):
                    return reply
                self.runtime.record("transient")
            except (TransportFailed, httpx.HTTPError):
                self.runtime.record("transient")
            except InjectedFailure:
                pass
            if attempt + 1 == cast(int, self.retry["attempts"]):
                self.runtime.record("exhausted")
                raise RetryExhausted
            self.runtime.record("retries")
            delay = min(
                cast(float, self.retry["cap_seconds"]),
                cast(float, self.retry["base_seconds"]) * 2**attempt
                + rng.uniform(0, cast(float, self.retry["jitter_seconds"])),
            )
            await self.clock.sleep(delay)
        raise RetryExhausted
