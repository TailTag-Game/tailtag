"""Behavioral tests for the Clerk Backend/Frontend API tooling (#219 P-4, P-7, P-8a).

Only the Clerk HTTP boundary (httpx.MockTransport) and the clock are substituted.
The instance fingerprint constant is re-derived for the fake instance id, because
the real instance id is not in the repository; the pinned literal itself is
asserted separately.
"""

import asyncio
import base64
import hashlib
import itertools
import json
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from tailtag_simulator import clerk
from tailtag_simulator.clerk import (
    ClerkFailed,
    external_id,
    open_admin,
    open_session,
)

REAL_PINS = {
    "BACKEND_API": clerk.BACKEND_API,
    "FRONTEND_API": clerk.FRONTEND_API,
    "TOOLING_ORIGIN": clerk.TOOLING_ORIGIN,
    "INSTANCE_FINGERPRINT": clerk.INSTANCE_FINGERPRINT,
    "PRIMARY_DOMAIN": clerk.PRIMARY_DOMAIN,
    "FRONTEND_API_VERSION": clerk.FRONTEND_API_VERSION,
    "TICKET_SECONDS": clerk.TICKET_SECONDS,
    "REFRESH_MARGIN_SECONDS": clerk.REFRESH_MARGIN_SECONDS,
}

SECRET = "sk_live_SECRETKEY"
INSTANCE_ID = "ins_SECRETINSTANCE"
USER_ID = "user_SECRETUSER"
TICKET_ID = "sit_SECRETTICKETID"
TICKET = "TICKETSECRET"
COOKIE = "COOKIESECRET"
SESSION_ID = "sess_SECRETSESSION"
LEAK = "LEAKY-RESPONSE-TEXT"
SENSITIVE = [SECRET, INSTANCE_ID, USER_ID, TICKET_ID, TICKET, COOKIE, SESSION_ID, LEAK]

POOL = "p1"
INDEX = 1
EXTERNAL_ID = "sim-pool-p1-1"
EMAIL = "sim-pool-p1-1@simulator.staging.tailtag.app"
TOOLING = "https://simulator.staging.tailtag.app"
BACKEND_HOST = "api.clerk.com"
FRONTEND_HOST = "clerk.staging.tailtag.app"
EVIL_HOST = "evil.example"

START = 1_700_000_000.0


@pytest.fixture(autouse=True)
def fake_instance_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha256(INSTANCE_ID.encode()).hexdigest()[:16]
    monkeypatch.setattr(clerk, "INSTANCE_FINGERPRINT", digest)


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


def user_json(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": USER_ID,
        "external_id": EXTERNAL_ID,
        "public_metadata": {
            "tailtag_synthetic": True,
            "tailtag_environment": "staging",
            "tailtag_pool": POOL,
            "tailtag_pool_index": INDEX,
        },
        "banned": False,
        "locked": False,
    }
    return {**base, **overrides}


Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeClerk:
    """Scripted Clerk. Unscripted requests answer 404 with LEAK text; any request to
    another host answers a valid-looking 200, so a followed redirect is visible."""

    clock: Clock = field(default_factory=Clock)
    overrides: dict[tuple[str, str], Handler] = field(
        default_factory=dict[tuple[str, str], Handler]
    )
    users: list[dict[str, object]] = field(default_factory=lambda: [user_json()])
    sessions: list[str] = field(default_factory=lambda: ["sess_A", "sess_B"])
    token_claims: dict[str, object] = field(default_factory=dict[str, object])
    token_drop: tuple[str, ...] = ()
    raw_jwt: str | None = None
    failing: bool = False
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    minted: Iterator[int] = field(default_factory=itertools.count)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def on(self, method: str, path: str, handler: Handler | httpx.Response) -> None:
        self.overrides[(method, path)] = (
            handler if callable(handler) else lambda _r, h=handler: h
        )

    def calls(self, host: str | None = None) -> list[tuple[str, str]]:
        return [
            (r.method, r.url.path)
            for r in self.requests
            if host is None or r.url.host == host
        ]

    def mint(self) -> str:
        if self.raw_jwt is not None:
            return self.raw_jwt
        claims: dict[str, object] = {
            "exp": int(self.clock.now) + 60,
            "azp": TOOLING,
            "sid": SESSION_ID,
            "sub": USER_ID,
            "n": next(self.minted),
            **self.token_claims,
        }
        for key in self.token_drop:
            claims.pop(key, None)
        return make_jwt(claims)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if request.url.host == EVIL_HOST:
            return httpx.Response(200, json={})
        if key in self.overrides:
            return self.overrides[key](request)
        if (
            self.failing
            and request.url.host == BACKEND_HOST
            and key[1] != "/v1/instance"
        ):
            return httpx.Response(500, text="".join(SENSITIVE))
        if request.url.host == BACKEND_HOST:
            return self.backend(request)
        if request.url.host == FRONTEND_HOST:
            return self.frontend(request)
        return httpx.Response(404, text=LEAK)

    def backend(self, request: httpx.Request) -> httpx.Response:
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
            return httpx.Response(200, json=self.users)
        if (method, path) == ("POST", "/v1/users"):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json=user_json(
                    external_id=body["external_id"],
                    public_metadata=body["public_metadata"],
                ),
            )
        if (method, path) == ("GET", "/v1/sessions"):
            return httpx.Response(200, json=[{"id": s} for s in self.sessions])
        if method == "POST" and path.startswith("/v1/sessions/"):
            return httpx.Response(200, json={})
        if (method, path) == ("POST", "/v1/sign_in_tokens"):
            return httpx.Response(
                200,
                json={
                    "id": TICKET_ID,
                    "user_id": USER_ID,
                    "token": TICKET,
                    "status": "pending",
                },
            )
        if method == "POST" and path.startswith("/v1/sign_in_tokens/"):
            return httpx.Response(200, json={})
        return httpx.Response(404, text=LEAK)

    def frontend(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        if (method, path) == ("POST", "/v1/client"):
            return httpx.Response(
                200,
                json={"response": {"object": "client"}},
                headers={"set-cookie": f"__client={COOKIE}; Path=/; Secure"},
            )
        if COOKIE not in request.headers.get("cookie", ""):
            return httpx.Response(401, text=LEAK)
        if (method, path) == ("POST", "/v1/client/sign_ins"):
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "complete",
                        "created_session_id": SESSION_ID,
                    }
                },
            )
        if (method, path) == ("POST", f"/v1/client/sessions/{SESSION_ID}/tokens"):
            return httpx.Response(200, json={"object": "token", "jwt": self.mint()})
        if (method, path) == ("POST", f"/v1/client/sessions/{SESSION_ID}/end"):
            return httpx.Response(200, json={"response": {"status": "ended"}})
        return httpx.Response(404, text=LEAK)


def run[T](body: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return asyncio.run(body())


def assert_clean(*things: object, extra: tuple[str, ...] = ()) -> None:
    text = "\n".join(str(t) + repr(t) for t in things)
    for secret in [*SENSITIVE, *extra]:
        assert secret not in text


def assert_failed_clean(exc: pytest.ExceptionInfo[ClerkFailed], *extra: str) -> None:
    assert_clean(exc.value, extra=extra)
    assert exc.value.__cause__ is None


async def mint_ticket(fake: FakeClerk) -> clerk.Ticket:
    async with open_admin(SECRET, transport=fake.transport) as admin:
        await admin.verify_instance()
        user = await admin.find_pool_user(POOL, INDEX)
        assert user is not None
        return await admin.create_ticket(user)


# -- pinned values ---------------------------------------------------------


def test_pinned_values_match_the_approved_literals() -> None:
    assert REAL_PINS == {
        "BACKEND_API": "https://api.clerk.com",
        "FRONTEND_API": "https://clerk.staging.tailtag.app",
        "TOOLING_ORIGIN": "https://simulator.staging.tailtag.app",
        "INSTANCE_FINGERPRINT": "328b851879c17392",
        "PRIMARY_DOMAIN": "staging.tailtag.app",
        "FRONTEND_API_VERSION": "2026-05-12",
        "TICKET_SECONDS": 60,
        "REFRESH_MARGIN_SECONDS": 15,
    }
    assert external_id("p1", 7) == "sim-pool-p1-7"


# -- ClerkAdmin: instance pin (P-8a) -----------------------------------------


@pytest.mark.parametrize("secret", ["", "sk_test_abc", "pk_live_abc", " sk_live_abc"])
def test_non_live_secret_is_rejected_before_any_request(secret: str) -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(secret, transport=fake.transport):
            pass

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)

    assert fake.requests == []
    assert_failed_clean(exc, *([secret] if secret else []))


def good_domain(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "staging.tailtag.app",
        "is_satellite": False,
        "frontend_api_url": "https://clerk.staging.tailtag.app",
    }
    return {**base, **overrides}


INSTANCE_CASES: dict[str, tuple[dict[str, object], list[dict[str, object]]]] = {
    "development-instance": (
        {"id": INSTANCE_ID, "environment_type": "development"},
        [good_domain()],
    ),
    "other-instance-id": (
        {"id": "ins_SOMEONEELSE", "environment_type": "production"},
        [good_domain()],
    ),
    "no-domains": ({"id": INSTANCE_ID, "environment_type": "production"}, []),
    "wrong-primary-domain": (
        {"id": INSTANCE_ID, "environment_type": "production"},
        [good_domain(name="tailtag.app")],
    ),
    "wrong-frontend-api": (
        {"id": INSTANCE_ID, "environment_type": "production"},
        [good_domain(frontend_api_url="https://clerk.evil.example")],
    ),
    "only-a-satellite": (
        {"id": INSTANCE_ID, "environment_type": "production"},
        [good_domain(is_satellite=True)],
    ),
    "two-primary-domains": (
        {"id": INSTANCE_ID, "environment_type": "production"},
        [good_domain(), good_domain(name="other.example")],
    ),
}


@pytest.mark.parametrize("case", INSTANCE_CASES)
def test_wrong_instance_or_domains_fail_verification_and_block_all_user_calls(
    case: str,
) -> None:
    instance, domains = INSTANCE_CASES[case]
    fake = FakeClerk()
    fake.on("GET", "/v1/instance", httpx.Response(200, json=instance))
    fake.on("GET", "/v1/domains", httpx.Response(200, json={"data": domains}))

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            with pytest.raises(ClerkFailed) as exc:
                await admin.verify_instance()
            assert_failed_clean(exc)
            # A failed verification leaves the admin unusable for user/ticket calls.
            with pytest.raises(ClerkFailed):
                await admin.create_pool_user(POOL, INDEX)
            with pytest.raises(ClerkFailed):
                await admin.find_pool_user(POOL, INDEX)

    run(attempt)

    assert all(r.method == "GET" for r in fake.requests)
    assert {p for _, p in fake.calls()} <= {"/v1/instance", "/v1/domains"}


def test_verified_instance_is_read_with_the_bearer_secret_and_never_redirected() -> (
    None
):
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()

    run(attempt)

    assert {p for _, p in fake.calls()} == {"/v1/instance", "/v1/domains"}
    assert {r.headers["authorization"] for r in fake.requests} == {f"Bearer {SECRET}"}

    redirected = FakeClerk()
    redirected.on(
        "GET",
        "/v1/instance",
        httpx.Response(302, headers={"location": f"https://{EVIL_HOST}/v1/instance"}),
    )

    async def redirect_attempt() -> None:
        async with open_admin(SECRET, transport=redirected.transport) as admin:
            await admin.verify_instance()

    with pytest.raises(ClerkFailed):
        run(redirect_attempt)
    assert EVIL_HOST not in {r.url.host for r in redirected.requests}


def test_ticket_call_on_an_admin_that_never_verified_sends_nothing() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket_user = None
        async with open_admin(SECRET, transport=fake.transport) as verified_admin:
            await verified_admin.verify_instance()
            ticket_user = await verified_admin.find_pool_user(POOL, INDEX)
        assert ticket_user is not None
        before = len(fake.requests)
        async with open_admin(SECRET, transport=fake.transport) as admin:
            calls = [
                admin.find_pool_user(POOL, INDEX),
                admin.create_pool_user(POOL, INDEX),
                admin.revoke_active_sessions(ticket_user),
                admin.create_ticket(ticket_user),
            ]
            for call in calls:
                with pytest.raises(ClerkFailed):
                    await call
        assert len(fake.requests) == before

    run(attempt)


# -- ClerkAdmin: users, markers, sessions, tickets -----------------------------


def test_find_pool_user_looks_up_by_external_id_and_fails_on_ambiguity() -> None:
    async def attempt() -> None:
        none = FakeClerk(users=[])
        async with open_admin(SECRET, transport=none.transport) as admin:
            await admin.verify_instance()
            assert await admin.find_pool_user(POOL, INDEX) is None
        query = [r for r in none.requests if r.url.path == "/v1/users"]
        assert [r.url.params.get("external_id") for r in query] == [EXTERNAL_ID]

        two = FakeClerk(users=[user_json(), user_json(id="user_OTHER")])
        async with open_admin(SECRET, transport=two.transport) as admin:
            await admin.verify_instance()
            with pytest.raises(ClerkFailed):
                await admin.find_pool_user(POOL, INDEX)

    run(attempt)


def test_created_pool_user_carries_exactly_the_marker_payload() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.create_pool_user(POOL, INDEX)
            admin.require_pool_identity(user, POOL, INDEX)

    run(attempt)

    posts = [
        r for r in fake.requests if (r.method, r.url.path) == ("POST", "/v1/users")
    ]
    assert [json.loads(r.content) for r in posts] == [
        {
            "external_id": EXTERNAL_ID,
            "email_address": [EMAIL],
            "skip_password_requirement": True,
            "public_metadata": {
                "tailtag_synthetic": True,
                "tailtag_environment": "staging",
                "tailtag_pool": POOL,
                "tailtag_pool_index": INDEX,
            },
        }
    ]


def meta(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(user_json()["public_metadata"])  # type: ignore[call-overload]
    return {k: v for k, v in {**base, **overrides}.items() if v is not ...}


# (user overrides, pool and index the caller asks for)
IDENTITY_REJECTIONS: dict[str, tuple[dict[str, object], str, int]] = {
    "external-id-of-another-index": ({"external_id": "sim-pool-p1-2"}, POOL, INDEX),
    "external-id-missing": ({"external_id": None}, POOL, INDEX),
    "caller-expects-another-index": ({}, POOL, INDEX + 1),
    "caller-expects-another-pool": ({}, "p2", INDEX),
    "metadata-null": ({"public_metadata": None}, POOL, INDEX),
    "synthetic-missing": (
        {"public_metadata": meta(tailtag_synthetic=...)},
        POOL,
        INDEX,
    ),
    "synthetic-false": (
        {"public_metadata": meta(tailtag_synthetic=False)},
        POOL,
        INDEX,
    ),
    "synthetic-string": (
        {"public_metadata": meta(tailtag_synthetic="true")},
        POOL,
        INDEX,
    ),
    "synthetic-int-one": ({"public_metadata": meta(tailtag_synthetic=1)}, POOL, INDEX),
    "environment-production": (
        {"public_metadata": meta(tailtag_environment="production")},
        POOL,
        INDEX,
    ),
    "environment-missing": (
        {"public_metadata": meta(tailtag_environment=...)},
        POOL,
        INDEX,
    ),
    "pool-marker-other": ({"public_metadata": meta(tailtag_pool="p2")}, POOL, INDEX),
    "pool-marker-missing": ({"public_metadata": meta(tailtag_pool=...)}, POOL, INDEX),
    "index-marker-other": (
        {"public_metadata": meta(tailtag_pool_index=INDEX + 1)},
        POOL,
        INDEX,
    ),
    # INDEX is 1, and True == 1 in Python: a bool must not pass as the index.
    "index-marker-bool": (
        {"public_metadata": meta(tailtag_pool_index=True)},
        POOL,
        INDEX,
    ),
    "index-marker-string": (
        {"public_metadata": meta(tailtag_pool_index="1")},
        POOL,
        INDEX,
    ),
    "banned": ({"banned": True}, POOL, INDEX),
    "locked": ({"locked": True}, POOL, INDEX),
}


@pytest.mark.parametrize("case", IDENTITY_REJECTIONS)
def test_identity_check_rejects_unmarked_mismatched_banned_or_locked_users(
    case: str,
) -> None:
    overrides, pool, index = IDENTITY_REJECTIONS[case]
    fake = FakeClerk(users=[user_json(**overrides)])

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert user is not None
            admin.require_pool_identity(user, pool, index)

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)
    assert_failed_clean(exc)


def test_identity_check_accepts_a_correctly_marked_user() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert user is not None
            admin.require_pool_identity(user, POOL, INDEX)

    run(attempt)


def test_session_revocation_and_ticket_lifecycle_use_the_expected_calls() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert user is not None
            assert await admin.revoke_active_sessions(user) == 2
            fake.sessions.clear()
            assert await admin.revoke_active_sessions(user) == 0
            ticket = await admin.create_ticket(user)
            await admin.revoke_ticket(ticket)

    run(attempt)

    listing = [r for r in fake.requests if r.url.path == "/v1/sessions"]
    assert [dict(r.url.params) for r in listing] == [
        {"user_id": USER_ID, "status": "active"}
    ] * 2
    assert [c for c in fake.calls(BACKEND_HOST) if "/revoke" in c[1]] == [
        ("POST", "/v1/sessions/sess_A/revoke"),
        ("POST", "/v1/sessions/sess_B/revoke"),
        ("POST", f"/v1/sign_in_tokens/{TICKET_ID}/revoke"),
    ]
    (mint,) = [r for r in fake.requests if r.url.path == "/v1/sign_in_tokens"]
    assert json.loads(mint.content) == {"user_id": USER_ID, "expires_in_seconds": 60}


ADMIN_OPERATIONS: dict[str, Callable[[Any, Any, Any], Awaitable[object]]] = {
    "find": lambda admin, _u, _t: admin.find_pool_user(POOL, INDEX),
    "create-user": lambda admin, _u, _t: admin.create_pool_user(POOL, INDEX),
    "revoke-sessions": lambda admin, user, _t: admin.revoke_active_sessions(user),
    "create-ticket": lambda admin, user, _t: admin.create_ticket(user),
    "revoke-ticket": lambda admin, _u, ticket: admin.revoke_ticket(ticket),
}


STALE_USER_REREADS: dict[str, list[dict[str, object]]] = {
    "unmarked": [user_json(public_metadata={})],
    "banned": [user_json(banned=True)],
    "different-id": [user_json(id="user_SOMEONEELSE")],
    "gone": [],
}


@pytest.mark.parametrize("case", STALE_USER_REREADS)
def test_ticket_is_not_created_when_the_fresh_user_read_no_longer_qualifies(
    case: str,
) -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert user is not None
            admin.require_pool_identity(user, POOL, INDEX)
            fake.users = STALE_USER_REREADS[case]
            await admin.create_ticket(user)

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)

    assert_failed_clean(exc)
    assert ("POST", "/v1/sign_in_tokens") not in fake.calls()


@pytest.mark.parametrize("operation", ADMIN_OPERATIONS)
def test_backend_failure_raises_a_detail_free_error(operation: str) -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert user is not None
            ticket = await admin.create_ticket(user)
            fake.failing = True
            await ADMIN_OPERATIONS[operation](admin, user, ticket)

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)
    assert_failed_clean(exc)


def test_credential_bearing_objects_have_no_secret_in_repr() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        async with open_admin(SECRET, transport=fake.transport) as admin:
            await admin.verify_instance()
            user = await admin.find_pool_user(POOL, INDEX)
            assert_clean(admin, user, ticket)
        async with open_session(ticket, transport=fake.transport) as session:
            await session.token()
            assert_clean(session)

    run(attempt)


# -- ClerkSession: Frontend API redemption (P-4, D1, D3) ------------------------


def test_redemption_uses_browser_style_cookie_flow_and_ends_the_session() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        fake.requests.clear()
        async with open_session(
            ticket, transport=fake.transport, clock=fake.clock
        ) as session:
            await session.token()

    run(attempt)

    sid = SESSION_ID
    assert fake.calls() == [
        ("POST", "/v1/client"),
        ("POST", "/v1/client/sign_ins"),
        ("POST", f"/v1/client/sessions/{sid}/tokens"),
        ("POST", f"/v1/client/sessions/{sid}/end"),
    ]
    first, sign_in, *rest = fake.requests
    assert "cookie" not in first.headers
    assert parse_qs(sign_in.content.decode()) == {
        "strategy": ["ticket"],
        "ticket": [TICKET],
    }
    for request in fake.requests:
        assert request.url.host == FRONTEND_HOST
        assert request.headers["origin"] == TOOLING
        assert request.headers["clerk-api-version"] == "2026-05-12"
        assert "authorization" not in request.headers
        assert "_is_native" not in request.url.params
        assert "__clerk_api_version" not in request.url.params
    for request in [sign_in, *rest]:
        assert COOKIE in request.headers["cookie"]


SIGN_IN_FAILURES: dict[str, httpx.Response] = {
    "needs-second-factor": httpx.Response(
        200, json={"response": {"status": "needs_second_factor"}}
    ),
    "complete-without-session": httpx.Response(
        200, json={"response": {"status": "complete"}}
    ),
    "created-session-but-not-complete": httpx.Response(
        200,
        json={"response": {"status": "needs_new_password", "created_session_id": "s"}},
    ),
    "rejected": httpx.Response(422, text=f"{LEAK}{TICKET}"),
    "not-json": httpx.Response(200, text=LEAK),
}


@pytest.mark.parametrize("case", SIGN_IN_FAILURES)
def test_ticket_sign_in_that_is_not_complete_is_rejected_without_a_token(
    case: str,
) -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        fake.on("POST", "/v1/client/sign_ins", SIGN_IN_FAILURES[case])
        async with open_session(ticket, transport=fake.transport):
            pass

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)

    assert_failed_clean(exc)
    assert not [c for c in fake.calls() if c[1].endswith("/tokens")]


def test_frontend_redirect_is_never_followed() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        fake.on(
            "POST",
            "/v1/client",
            httpx.Response(302, headers={"location": f"https://{EVIL_HOST}/v1/client"}),
        )
        async with open_session(ticket, transport=fake.transport):
            pass

    with pytest.raises(ClerkFailed):
        run(attempt)
    assert EVIL_HOST not in {r.url.host for r in fake.requests}


def test_token_is_cached_until_fifteen_seconds_remain_then_refreshed() -> None:
    fake = FakeClerk()
    seen: list[str] = []

    def fetches() -> int:
        return len([c for c in fake.calls() if c[1].endswith("/tokens")])

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        async with open_session(
            ticket, transport=fake.transport, clock=fake.clock
        ) as session:
            seen.append(await session.token())  # exp = START + 60
            assert fetches() == 1
            fake.clock.now = START + 44  # 16s remain: still fresh
            seen.append(await session.token())
            assert fetches() == 1
            fake.clock.now = START + 45  # 15s remain: not more than the margin
            seen.append(await session.token())
            assert fetches() == 2

    run(attempt)

    assert seen[0] == seen[1] != seen[2]


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


# (claim overrides, claims to drop, raw JWT replacing the minted one)
TOKEN_REJECTIONS: dict[str, tuple[dict[str, object], tuple[str, ...], str | None]] = {
    "other-azp": ({"azp": "https://accounts.staging.tailtag.app"}, (), None),
    "missing-azp": ({}, ("azp",), None),
    "other-session": ({"sid": "sess_SOMEONEELSE"}, (), None),
    "missing-sid": ({}, ("sid",), None),
    "missing-exp": ({}, ("exp",), None),
    "two-segments": ({}, (), "aaa.bbb"),
    "payload-not-base64": ({}, (), "aaa.!!!.ccc"),
    "payload-not-json": ({}, (), f"aaa.{b64('not json')}.ccc"),
}


@pytest.mark.parametrize("case", TOKEN_REJECTIONS)
def test_token_that_is_malformed_or_has_wrong_claims_is_rejected(case: str) -> None:
    claims, drop, raw = TOKEN_REJECTIONS[case]
    fake = FakeClerk()
    jwts: list[str] = []

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        fake.token_claims, fake.token_drop, fake.raw_jwt = claims, drop, raw
        async with open_session(
            ticket, transport=fake.transport, clock=fake.clock
        ) as session:
            await session.token()

    original_mint = fake.mint

    def recording_mint() -> str:
        jwts.append(original_mint())
        return jwts[-1]

    fake.mint = recording_mint  # type: ignore[method-assign]

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)
    assert_failed_clean(exc, *jwts)


@pytest.mark.parametrize("fail_in_body", [False, True], ids=["normal", "error"])
def test_session_is_ended_on_exit_even_when_the_body_fails(fail_in_body: bool) -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        async with open_session(ticket, transport=fake.transport):
            if fail_in_body:
                raise RuntimeError("body failed")

    if fail_in_body:
        with pytest.raises(RuntimeError, match="body failed"):
            run(attempt)
    else:
        run(attempt)

    assert ("POST", f"/v1/client/sessions/{SESSION_ID}/end") in fake.calls()


def test_failure_to_end_the_session_is_reported_on_normal_exit() -> None:
    fake = FakeClerk()

    async def attempt() -> None:
        ticket = await mint_ticket(fake)
        fake.on(
            "POST",
            f"/v1/client/sessions/{SESSION_ID}/end",
            httpx.Response(500, text=LEAK),
        )
        async with open_session(ticket, transport=fake.transport):
            pass

    with pytest.raises(ClerkFailed) as exc:
        run(attempt)
    assert_failed_clean(exc)
