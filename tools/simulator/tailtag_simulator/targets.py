"""Closed target set and fail-closed backend identity verification (A-6, A-7)."""

import hashlib
import re
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, cast
from urllib.parse import urlsplit

from tailtag_simulator.client import ApiClient, RequestFailed, TransportFailed
from tailtag_simulator.safety import ProbeInvalid, ProbeUnavailable, valid_identity

STAGING_ORIGIN: Final = "https://staging.tailtag.app"
LOCAL_ORIGINS: Final = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://host.docker.internal:8000",
)
IDENTITY_PATH: Final = "/health/identity"
# The replica origin is private, so only its pin digest is committed. It must
# equal `_EXPECTED_HOST_DIGEST` in services/api/config/replica_binding.py (#359).
REPLICA_HOST_DIGEST: Final = (
    "a78605fc99f91d19d469ea8f20de7fb5a301360cd4014b561d311cdb35fdd21a"
)
_HOST_LABEL: Final = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST: Final = re.compile(rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})+")


class TargetRejected(ProbeInvalid):
    """The target name, origin, or reported identity is not an allowed target."""


class TargetUnavailable(TargetRejected, ProbeUnavailable):
    """A valid target did not provide readiness or an available response."""


@dataclass(frozen=True)
class Target:
    """A permitted target name and its exact origin. Not yet identity-verified."""

    name: str
    origin: str

    @property
    def report_origin(self) -> str:
        """The origin as evidence records it: the private replica host only by digest."""
        return replica_origin_label() if self.name == "replica" else self.origin


def replica_host_digest(host: str) -> str:
    """The domain-separated pin digest of a replica host, as the API computes it."""
    return hashlib.sha256(f"tailtag-replica-host-v1\0{host}".encode()).hexdigest()


def replica_origin_label() -> str:
    return f"sha256:{REPLICA_HOST_DIGEST}"


def _replica_origin(base_url: str | None) -> str:
    if base_url is None:
        raise TargetRejected
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if (
        parts.scheme != "https"
        or base_url != f"https://{host}"
        or _HOST.fullmatch(host) is None
        or replica_host_digest(host) != REPLICA_HOST_DIGEST
    ):
        raise TargetRejected
    return base_url


@dataclass(frozen=True)
class VerifiedTarget:
    """A target whose two `/health/identity` reads agreed with its expectations."""

    target: Target
    source_sha: str | None
    deployment_id: str | None = None
    environment: str | None = None

    def identity(self) -> dict[str, object]:
        return {
            "source_sha": self.source_sha,
            "deployment_id": self.deployment_id,
            "environment": self.environment,
        }


def resolve_target(name: str, base_url: str | None) -> Target:
    """Resolve a target name; there is no way to name Production or Development."""
    if name == "staging" and base_url is None:
        return Target("staging", STAGING_ORIGIN)
    if name == "local" and (base_url is None or base_url in LOCAL_ORIGINS):
        return Target("local", base_url or LOCAL_ORIGINS[0])
    if name == "replica":
        return Target("replica", _replica_origin(base_url))
    raise TargetRejected


_BOUND: ContextVar[Target | None] = ContextVar("tailtag_simulator_target", default=None)


@contextmanager
def bind_target(target: Target) -> Generator[Target]:
    """Make `target` the run target for the code inside the block (#359)."""
    token = _BOUND.set(
        resolve_target(target.name, None if target.name == "staging" else target.origin)
    )
    try:
        yield target
    finally:
        _BOUND.reset(token)


def bound_target() -> Target:
    """The run target that `bind_target` set, or Staging when none is set."""
    return _BOUND.get() or resolve_target("staging", None)


async def _read_identity(client: ApiClient, target: Target) -> dict[str, object]:
    try:
        reply = await client.get(IDENTITY_PATH)
    except TransportFailed:
        raise TargetUnavailable from None
    except RequestFailed:
        raise TargetRejected from None
    if reply.status in (408, 429) or reply.status >= 500:
        raise TargetUnavailable
    body = reply.body
    if reply.status != 200 or not isinstance(body, dict):
        raise TargetRejected
    identity = cast(dict[str, object], body)
    if not valid_identity(target.name, identity):
        raise TargetRejected
    return identity


async def verify_target(client: ApiClient, target: Target) -> VerifiedTarget:
    """Require two agreeing, expected identity reads before any token is involved."""
    if target != resolve_target(
        target.name, None if target.name == "staging" else target.origin
    ):
        raise TargetRejected
    first = await _read_identity(client, target)
    if target.name in ("staging", "replica"):
        try:
            ready = await client.get("/health/ready")
        except TransportFailed:
            raise TargetUnavailable from None
        except RequestFailed:
            raise TargetRejected from None
        if ready.status != 200:
            raise TargetUnavailable
        if ready.body != {"status": "ok"}:
            raise TargetRejected
    second = await _read_identity(client, target)
    if first != second:
        raise TargetRejected
    source_sha = first["source_sha"]
    return VerifiedTarget(
        target,
        source_sha if isinstance(source_sha, str) else None,
        cast(str | None, first["deployment_id"]),
        cast(str | None, first["environment"]),
    )
