"""Controlled nondeterministic time boundary for real traffic execution."""

import asyncio

from tailtag_simulator.traffic import Clock


class ManualClock:
    """Time advances only when the test chooses, including concurrent sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.waiters: dict[asyncio.Future[None], float] = {}
        self.clock = Clock(
            monotonic=lambda: self.now,
            sleep=self.sleep,
            wall_time=lambda: 1_800_000_000.0 + self.now,
        )

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiters[future] = self.now + seconds
        try:
            await future
        finally:
            self.waiters.pop(future, None)

    async def settle(self) -> None:
        # Yield to bounded layers of scheduler/request tasks without moving time.
        for _ in range(30):
            await asyncio.sleep(0)

    async def advance(self, seconds: float) -> None:
        self.now += seconds
        for future, deadline in tuple(self.waiters.items()):
            if deadline <= self.now + 1e-9 and not future.done():
                future.set_result(None)
        await self.settle()

    async def through(self, at_seconds: float) -> None:
        await self.settle()
        while self.now < at_seconds - 1e-9:
            await self.advance(min(0.01, at_seconds - self.now))
