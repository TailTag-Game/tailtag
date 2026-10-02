"""The three phase boundaries of a run: SETUP, SIMULATION, RECONCILIATION (A-4, A-5).

Each phase is one function that receives exactly one context type, so what a phase
can reach is fixed by its signature:

- SETUP receives the verified target and the token prompt, and returns credentials.
  Privileged setup (identity pool #219, fixtures #220) extends SetupContext only.
- SIMULATION receives only a public ApiClient already bound to the verified origin
  and bearer token. It has no prompt, no setup inputs, and no privileged access.
- RECONCILIATION receives only the recorded observations. Privileged read-only
  reconciliation (#222) extends ReconciliationContext only.

There is deliberately no registry or plugin system: later issues extend the contexts
and add phase bodies.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, cast

from tailtag_simulator.client import ApiClient, Reply
from tailtag_simulator.targets import VerifiedTarget

ME_PATH: Final = "/api/me/"
ME_REQUESTS: Final = 2

_TOKEN: Final = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2}")


class PhaseFailed(Exception):
    """A phase did not meet its contract. Carries no detail by design."""


@dataclass(frozen=True)
class SetupContext:
    target: VerifiedTarget
    prompt_token: Callable[[], str]


@dataclass(frozen=True)
class Credentials:
    token: str = field(repr=False)


@dataclass(frozen=True)
class SimulationContext:
    client: ApiClient


@dataclass(frozen=True)
class Observations:
    replies: tuple[Reply, ...] = field(repr=False)


@dataclass(frozen=True)
class ReconciliationContext:
    observations: Observations


def setup(context: SetupContext) -> Credentials:
    """Obtain a bearer token and accept only an exact three-segment base64url value."""
    token = context.prompt_token()
    if _TOKEN.fullmatch(token) is None:
        raise PhaseFailed
    return Credentials(token)


async def simulate(context: SimulationContext) -> Observations:
    """Make the two public `GET /api/me/` requests and record what came back."""
    replies: list[Reply] = []
    for _ in range(ME_REQUESTS):
        replies.append(await context.client.get(ME_PATH))
    return Observations(tuple(replies))


def reconcile(context: ReconciliationContext) -> None:
    """Pass only when every response was a 200 object with the same positive `id`."""
    ids: set[int] = set()
    for reply in context.observations.replies:
        body = reply.body
        if reply.status != 200 or not isinstance(body, dict):
            raise PhaseFailed
        user_id = cast(dict[str, object], body).get("id")
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise PhaseFailed
        ids.add(user_id)
    if len(ids) != 1:
        raise PhaseFailed
