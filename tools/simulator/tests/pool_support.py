"""Shared in-memory boundaries for the pool tests (#219 unit C).

Only real boundaries are substituted: Clerk and TailTag HTTP (one httpx.MockTransport
each, routed by host), the lease channel (a faithful in-memory slot table speaking the
launcher's request protocol), the secret prompt, and time (an injected clock that the
injected sleep advances). The Clerk fake mirrors the one in test_clerk.py, extended
to several pool users.
"""

import base64
import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import parse_qs

import httpx
import pytest

from tailtag_simulator import clerk
from tailtag_simulator.pool import LeaseFailed

SECRET: Final = "sk_live_POOLSECRETKEY"
INSTANCE_ID: Final = "ins_POOLSECRETINSTANCE"
POOL: Final = "p1"
RUN_ID: Final = str(uuid.UUID("123e4567-e89b-42d3-a456-426614174000"))
TOOLING: Final = "https://simulator.staging.tailtag.app"
SHA: Final = "0123456789abcdef0123456789abcdef01234567"
DEPLOYMENT_ID: Final = "223e4567-e89b-42d3-a456-426614174000"

BACKEND_HOST: Final = "api.clerk.com"
FRONTEND_HOST: Final = "clerk.staging.tailtag.app"
API_HOST: Final = "staging.tailtag.app"
ALLOWED_API_PATHS: Final = frozenset({"/health/identity", "/api/me/", "/api/profile/"})

# Far in the future, so a session that is not handed the injected clock sees every
# fake token as fresh and visibly fails to refresh.
START: Final = 4_000_000_000.0

SENSITIVE_PREFIXES: Final = (
    "sk_live_",
    "ins_",
    "user_SECRET",
    "TICKET",
    "COOKIE",
    "sess_",
)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


def make_jwt(payload: dict[str, object]) -> str:
    def part(data: dict[str, object]) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(payload)}.c2ln"


def jwt_claims(token: str) -> dict[str, object]:
    segment = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def user_json(index: int, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": f"user_SECRET{index}",
        "external_id": f"sim-pool-{POOL}-{index}",
        "public_metadata": {
            "tailtag_synthetic": True,
            "tailtag_environment": "staging",
            "tailtag_pool": POOL,
            "tailtag_pool_index": index,
        },
        "banned": False,
        "locked": False,
    }
    return {**base, **overrides}


def pool_handle(index: int) -> str:
    return f"sp_{POOL}_{index}"


def onboarded(index: int) -> dict[str, object]:
    return {"handle": pool_handle(index), "display_name": f"Sim {POOL} {index}"}


def not_onboarded() -> dict[str, object]:
    return {"handle": None, "display_name": None}


@dataclass
class World:
    """Scripted Clerk plus TailTag API for pool identities 0..n-1."""

    clock: Clock = field(default_factory=Clock)
    users: dict[int, dict[str, object]] = field(
        default_factory=lambda: {i: user_json(i) for i in range(5)}
    )
    profiles: dict[int, dict[str, object]] = field(
        default_factory=lambda: {i: not_onboarded() for i in range(5)}
    )
    leftover_sessions: dict[int, list[str]] = field(
        default_factory=lambda: {i: [f"sess_old{i}"] for i in range(5)}
    )
    sign_in_rejected: set[int] = field(default_factory=set[int])
    end_fails: bool = False
    end_interrupt: BaseException | None = None
    identity_reply: Callable[[], httpx.Response] | None = None
    identity_environment: str | None = "staging"
    me_ids: dict[int, object] = field(default_factory=dict[int, object])
    # (index, 0-based /api/me/ request number) -> response or exception to raise
    me_override: dict[tuple[int, int], httpx.Response | Exception] = field(
        default_factory=dict[tuple[int, int], httpx.Response | Exception]
    )
    put_handle_override: dict[int, str] = field(default_factory=dict[int, str])
    # Extra authenticated TailTag routes (method, path, user index) -> response, for
    # runs that read more than the pool endpoints (#220). None means "not mine".
    route: Callable[[str, str, int], httpx.Response | None] | None = None

    log: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    stray: list[str] = field(default_factory=list[str])
    created_users: list[int] = field(default_factory=list[int])
    tickets: list[int] = field(default_factory=list[int])
    revoked_sessions: list[str] = field(default_factory=list[str])
    ended_sessions: list[str] = field(default_factory=list[str])
    opened_sessions: list[str] = field(default_factory=list[str])
    # (method, path, index of the bearer token's user or None)
    api_calls: list[tuple[str, str, int | None]] = field(
        default_factory=list[tuple[str, str, int | None]]
    )
    api_requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    me_tokens: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    puts: dict[int, object] = field(default_factory=dict[int, object])
    _mints: int = 0
    _clients: int = 0

    # -- transports --------------------------------------------------------
    @property
    def clerk_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._clerk)

    @property
    def api_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._api)

    def note(self, kind: str, detail: str = "") -> None:
        self.log.append((kind, detail))

    def kinds(self, *kinds: str) -> list[tuple[str, str]]:
        return [entry for entry in self.log if entry[0] in kinds]

    # -- Clerk ---------------------------------------------------------------
    def _clerk(self, request: httpx.Request) -> httpx.Response:
        host, method, path = request.url.host, request.method, request.url.path
        if host == BACKEND_HOST:
            self.note("backend", f"{method} {path}")
            return self._backend(request)
        if host == FRONTEND_HOST:
            self.note("frontend", f"{method} {path}")
            return self._frontend(request)
        self.stray.append(f"{host}{path}")
        return httpx.Response(404)

    def _backend(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        if (method, path) == ("GET", "/v1/instance"):
            return httpx.Response(
                200, json={"id": INSTANCE_ID, "environment_type": "production"}
            )
        if (method, path) == ("GET", "/v1/domains"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "staging.tailtag.app",
                            "is_satellite": False,
                            "frontend_api_url": "https://clerk.staging.tailtag.app",
                        }
                    ]
                },
            )
        if (method, path) == ("GET", "/v1/users"):
            wanted = request.url.params.get("external_id", "")
            found = [
                u for i, u in self.users.items() if wanted == f"sim-pool-{POOL}-{i}"
            ]
            return httpx.Response(200, json=found)
        if (method, path) == ("POST", "/v1/users"):
            body = json.loads(request.content)
            index = int(str(body["external_id"]).rsplit("-", 1)[1])
            self.created_users.append(index)
            self.users[index] = user_json(
                index,
                external_id=body["external_id"],
                public_metadata=body["public_metadata"],
            )
            return httpx.Response(200, json=self.users[index])
        if (method, path) == ("GET", "/v1/sessions"):
            user_id = request.url.params["user_id"]
            index = int(user_id.removeprefix("user_SECRET"))
            return httpx.Response(
                200, json=[{"id": s} for s in self.leftover_sessions.get(index, [])]
            )
        if method == "POST" and re.fullmatch(r"/v1/sessions/[^/]+/revoke", path):
            self.revoked_sessions.append(path.split("/")[3])
            return httpx.Response(200, json={})
        if (method, path) == ("POST", "/v1/sign_in_tokens"):
            index = int(
                json.loads(request.content)["user_id"].removeprefix("user_SECRET")
            )
            self.tickets.append(index)
            self.note("ticket", str(index))
            return httpx.Response(
                200,
                json={
                    "id": f"sit_{index}",
                    "user_id": f"user_SECRET{index}",
                    "token": f"TICKET{index}",
                    "status": "pending",
                },
            )
        if method == "POST" and path.startswith("/v1/sign_in_tokens/"):
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def _frontend(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        if (method, path) == ("POST", "/v1/client"):
            self._clients += 1
            return httpx.Response(
                200,
                json={"response": {"object": "client"}},
                headers={
                    "set-cookie": f"__client=COOKIE{self._clients}; Path=/; Secure"
                },
            )
        if "COOKIE" not in request.headers.get("cookie", ""):
            return httpx.Response(401)
        if (method, path) == ("POST", "/v1/client/sign_ins"):
            ticket = parse_qs(request.content.decode())["ticket"][0]
            index = int(ticket.removeprefix("TICKET"))
            if index in self.sign_in_rejected:
                return httpx.Response(422, text="rejected")
            self.opened_sessions.append(f"sess_{index}")
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "complete",
                        "created_session_id": f"sess_{index}",
                    }
                },
            )
        match = re.fullmatch(r"/v1/client/sessions/(sess_\d+)/(tokens|end)", path)
        if method == "POST" and match:
            sid, action = match.groups()
            if action == "end":
                if self.end_interrupt is not None:
                    raise self.end_interrupt
                if self.end_fails:
                    return httpx.Response(500, text="boom")
                self.ended_sessions.append(sid)
                return httpx.Response(200, json={"response": {"status": "ended"}})
            self._mints += 1
            index = int(sid.removeprefix("sess_"))
            claims: dict[str, object] = {
                "exp": int(self.clock.now) + 60,
                "azp": TOOLING,
                "sid": sid,
                "sub": f"user_SECRET{index}",
                "n": self._mints,
            }
            return httpx.Response(
                200, json={"object": "token", "jwt": make_jwt(claims)}
            )
        return httpx.Response(404)

    # -- TailTag API -----------------------------------------------------------
    def _api(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.api_requests.append(request)
        if request.url.host != API_HOST:
            self.stray.append(f"{request.url.host}{path}")
            return httpx.Response(404)
        if path == "/health/identity":
            self.note("api", f"{method} {path}")
            self.api_calls.append((method, path, None))
            if self.identity_reply is not None:
                return self.identity_reply()
            return httpx.Response(
                200,
                json={
                    "source_sha": SHA,
                    "deployment_id": DEPLOYMENT_ID,
                    "environment": self.identity_environment,
                },
            )
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        try:
            claims = jwt_claims(bearer)
            index = int(str(claims["sub"]).removeprefix("user_SECRET"))
            fresh = float(str(claims["exp"])) > self.clock.now
        except (IndexError, KeyError, ValueError):
            self.stray.append(f"unauthenticated {method} {path}")
            return httpx.Response(401)
        self.note("api", f"{method} {path} {index}")
        self.api_calls.append((method, path, index))
        if not fresh or claims.get("azp") != TOOLING:
            return httpx.Response(401)
        if (method, path) == ("GET", "/api/me/"):
            tokens = self.me_tokens.setdefault(index, [])
            override = self.me_override.get((index, len(tokens)))
            tokens.append(bearer)
            if isinstance(override, Exception):
                raise override
            if override is not None:
                return override
            return httpx.Response(
                200, json={"id": self.me_ids.get(index, 1000 + index)}
            )
        if (method, path) == ("GET", "/api/profile/"):
            return self._profile(index)
        if (method, path) == ("PUT", "/api/profile/"):
            body = json.loads(request.content)
            self.puts[index] = body
            self.profiles[index] = {
                "handle": self.put_handle_override.get(index, body["handle"]),
                "display_name": body["display_name"],
            }
            return self._profile(index)
        extra = self.route(method, path, index) if self.route is not None else None
        if extra is not None:
            return extra
        self.stray.append(f"{method} {path}")
        return httpx.Response(404)

    def _profile(self, index: int) -> httpx.Response:
        profile = self.profiles[index]
        return httpx.Response(
            200,
            json={
                **profile,
                "avatar_url": None,
                "onboarding_complete": profile["handle"] is not None,
                "is_enabled": True,
            },
        )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    # The real instance id is not in the repository, so the pinned fingerprint is
    # re-derived for the fake instance (as test_clerk.py does).
    digest = hashlib.sha256(INSTANCE_ID.encode()).hexdigest()[:16]
    monkeypatch.setattr(clerk, "INSTANCE_FINGERPRINT", digest)
    return World()


# -- lease channel ------------------------------------------------------------

_ARGUMENT_NAMES: Final[dict[str, frozenset[str]]] = {
    "register": frozenset({"size"}),
    "allocate": frozenset({"run_id", "count", "ttl_seconds"}),
    "heartbeat": frozenset({"run_id", "ttl_seconds"}),
    "release": frozenset({"run_id"}),
    "quarantine": frozenset({"index", "run_id"}),
    "readmit": frozenset({"index"}),
    "status": frozenset(),
}


@dataclass
class Slot:
    state: str = "free"  # free | leased | quarantined
    run_id: str | None = None


OTHER_RUN_ID = "99999999-9999-4999-8999-999999999999"


class FakeChannel:
    """In-memory lease table that enforces the launcher's request protocol."""

    def __init__(
        self,
        world: World,
        *,
        slots: int = 5,
        fail: set[str] | None = None,
        reclaim_before_heartbeat: int = 0,
    ):
        self._world = world
        self.slots: dict[int, Slot] = {i: Slot() for i in range(slots)}
        self.fail = fail or set()
        # Simulates leases that expired and were taken by another run mid-run.
        self.reclaim_before_heartbeat = reclaim_before_heartbeat
        self.calls: list[tuple[str, dict[str, object]]] = []

    def indexes(self, state: str) -> set[int]:
        return {i for i, s in self.slots.items() if s.state == state}

    def calls_to(self, operation: str) -> list[dict[str, object]]:
        return [args for op, args in self.calls if op == operation]

    async def call(
        self, operation: str, pool: str, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        args = dict(arguments)
        self.calls.append((operation, args))
        self._world.note("channel", f"{operation} {json.dumps(args, sort_keys=True)}")
        if operation in self.fail:
            raise LeaseFailed("FAIL_LAUNCHER", None)
        if pool != POOL or frozenset(args) != _ARGUMENT_NAMES.get(operation):
            raise LeaseFailed("FAIL_REQUEST", None)
        if "run_id" in args and (
            not isinstance(args["run_id"], str)
            or str(uuid.UUID(args["run_id"])) != args["run_id"]
        ):
            raise LeaseFailed("FAIL_REQUEST", None)
        if any(type(v) is not int for k, v in args.items() if k != "run_id"):
            raise LeaseFailed("FAIL_REQUEST", None)
        run_id = args.get("run_id")
        if operation == "allocate":
            free = sorted(self.indexes("free"))
            count = int(str(args["count"]))
            if len(free) < count:
                raise LeaseFailed("FAIL_INSUFFICIENT", len(free))
            for index in free[:count]:
                self.slots[index] = Slot("leased", str(run_id))
            return {"indexes": free[:count]}
        if operation == "heartbeat":
            mine = [s for s in self.slots.values() if s.run_id == run_id]
            for slot in mine[: self.reclaim_before_heartbeat]:
                slot.run_id = OTHER_RUN_ID
            leased = [s for s in self.slots.values() if s.run_id == run_id]
            return {"extended": len(leased)}
        if operation == "release":
            held = [s for s in self.slots.values() if s.state == "leased"]
            released = [s for s in held if s.run_id == run_id]
            for slot in released:
                slot.state, slot.run_id = "free", None
            return {"released": len(released)}
        if operation == "quarantine":
            slot = self.slots.get(int(str(args["index"])))
            if slot is None or slot.state != "leased" or slot.run_id != run_id:
                raise LeaseFailed("FAIL_SLOT", None)
            slot.state, slot.run_id = "quarantined", None
            return {}
        if operation == "register":
            size = int(str(args["size"]))
            created = [i for i in range(size) if i not in self.slots]
            for index in created:
                self.slots[index] = Slot()
            return {"created": len(created)}
        raise LeaseFailed("FAIL_REQUEST", None)
