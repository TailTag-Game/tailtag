"""In-memory gameplay API for the acceptance journey tests (#221 unit B).

Builds on pool_support and fixture_support. The only new substitute is the public
gameplay API itself (`Gameplay`, installed as the World's extra authenticated route),
which models the V0 rules the journeys depend on with the response shapes of the
spec's Evidence section. `JourneyWorld` extends the World only where the route cannot
reach: the request itself (body, query, uploaded bytes), the profile read that serves
`avatar_url`, and the bearer check that decides a malformed token.

`Gameplay.break_rule(name)` makes the fake violate exactly one rule: one per journey
(named after it), plus `avatar_redirect`, `avatar_unexpected` and `self_catch_unknown_code`. A broken rule
only changes what that journey observes; every other journey keeps its own state.
"""

import json
import math
import re
import struct
import time
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, cast

import httpx
import pytest
from fixture_support import (
    ACTIVE_PATH,
    CONVENTION_ID,
    FURSUITS_PATH,
    LEAK_SENTINELS,
    FixtureState,
    activation_body,
    enrollment_body,
    fursuit_body,
)
from pool_support import (
    API_HOST,
    SECRET,
    SENSITIVE_PREFIXES,
    World,
    jwt_claims,
    not_onboarded,
    onboarded,
    user_json,
)

INDEXES: Final = 8  # slot 0 is quarantined; the run leases 1..7

CATCH_SESSION: Final = "catch-session/"
CREDENTIAL: Final = "catch-credential/"
ROTATE: Final = "catch-credential/rotate/"
RESOLVE_PATH: Final = f"/api/conventions/{CONVENTION_ID}/catch-credentials/resolve/"
CONFIRM_PATH: Final = "/api/catches/confirm/"
PREVIEW_PATH: Final = "/api/catches/preview/"
REQUESTS_PATH: Final = "/api/catches/requests/"
INCOMING_PATH: Final = "/api/catches/incoming-requests/"
AT: Final = "2026-10-03T12:00:00Z"
HISTORY_PATH: Final = "/api/catches/"
AVATAR_PATH: Final = "/api/profile/avatar/"
CREATE_PATH: Final = FURSUITS_PATH

UNSUPPORTED_FORMAT: Final = "Upload a JPEG, PNG, or static WebP image."
INVALID_IMAGE: Final = "Upload a valid image."
TOO_MANY_PIXELS: Final = "The photo dimensions are too large."
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
MAX_PIXELS: Final = 25_000_000

# Everything the fake serves that simulator output must never repeat.
JOURNEY_LEAKS: Final = (
    *LEAK_SENTINELS,
    "tailtag:catch",
    "http",
    "Sim journey",
    "evil.example",
    SECRET,
    *SENSITIVE_PREFIXES,
)


def path_for(fursuit_id: int, suffix: str = "") -> str:
    return f"/api/conventions/{CONVENTION_ID}/fursuit-activations/{fursuit_id}/{suffix}"


def png_header(width: int, height: int, filler: bytes = b"") -> bytes:
    """A PNG signature and IHDR chunk: all the fake (like the real API) reads first."""
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    chunk = struct.pack(">I", 13) + ihdr + struct.pack(">I", zlib.crc32(ihdr))
    return PNG_SIGNATURE + chunk + filler


VALID_A: Final = png_header(2, 2, b"image-a")
VALID_B: Final = png_header(3, 3, b"image-b")


def image_error(content: bytes) -> str | None:
    """The API's image rejection for these bytes, decided from the bytes alone."""
    if content.startswith(b"GIF8"):
        return UNSUPPORTED_FORMAT
    if content.startswith(PNG_SIGNATURE):
        if len(content) >= 24:
            width, height = struct.unpack(">II", content[16:24])
            if width * height > MAX_PIXELS:
                return TOO_MANY_PIXELS
        return None
    if content.startswith(b"\xff\xd8\xff") or (
        content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    ):
        return None
    return INVALID_IMAGE


def parse_multipart(request: httpx.Request) -> list[tuple[str, bool, bytes]]:
    """(name, is_file, content) for every part of a multipart/form-data request."""
    found = re.search(r"boundary=([^;]+)", request.headers.get("content-type", ""))
    if found is None:
        return []
    delimiter = b"--" + found.group(1).strip('"').encode()
    parts: list[tuple[str, bool, bytes]] = []
    for chunk in request.content.split(delimiter)[1:]:
        if chunk.startswith(b"--"):
            break
        head, _, payload = chunk.removeprefix(b"\r\n").partition(b"\r\n\r\n")
        name = re.search(rb'name="([^"]*)"', head)
        if name is not None:
            parts.append(
                (
                    name.group(1).decode(),
                    b"filename=" in head,
                    payload.removesuffix(b"\r\n"),
                )
            )
    return parts


def media_url(kind: str, ident: int, version: int = 0, scheme: str = "https") -> str:
    return f"{scheme}://media.example/SENTINEL-{kind}-{ident}-v{version}"


def reply(status: int, body: object | None = None) -> httpx.Response:
    return httpx.Response(status) if body is None else httpx.Response(status, json=body)


def failure(status: int, code: str) -> httpx.Response:
    return reply(status, {"code": code, "detail": f"SENTINEL detail for {code}"})


def not_found() -> httpx.Response:
    return reply(404, {"detail": "Not found."})


@dataclass
class Catch:
    id: int
    catcher: int
    fursuit_id: int


@dataclass
class RequestRow:
    id: int
    player: int
    fursuit_id: int
    state: str
    declined_at: float | None = None
    blocked: bool = False
    created_at: float = 0.0


@dataclass
class Uploaded:
    content: bytes
    fields: dict[str, str]


@dataclass
class Gameplay:
    """The V0 gameplay rules over the fixture state the #220 provision populates."""

    state: FixtureState = field(default_factory=FixtureState)
    broken: str | None = None
    request: httpx.Request | None = None

    # (method, path, index of the bearer's identity or None), every API request
    requests: list[tuple[str, str, int | None]] = field(
        default_factory=list[tuple[str, str, int | None]]
    )
    sessions: dict[int, bool] = field(default_factory=dict[int, bool])
    issued: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    fursuit_of: dict[str, int] = field(default_factory=dict[str, int])
    revoked: set[str] = field(default_factory=set[str])
    deactivated: set[int] = field(default_factory=set[int])
    inactive_enrollments: set[int] = field(default_factory=set[int])
    catches: list[Catch] = field(default_factory=list[Catch])
    created: dict[int, dict[str, object]] = field(
        default_factory=dict[int, dict[str, object]]
    )
    created_owner: dict[int, int] = field(default_factory=dict[int, int])
    avatars: dict[int, int] = field(default_factory=dict[int, int])
    # every accepted upload's bytes, in order; every attempted write's target
    stored: list[bytes] = field(default_factory=list[bytes])
    photo_puts: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])
    avatar_puts: list[int] = field(default_factory=list[int])
    # The catch request flow (#508).
    now: float = 0.0
    modes: dict[int, str] = field(default_factory=dict[int, str])
    rows: list[RequestRow] = field(default_factory=list[RequestRow])
    blocks: set[tuple[int, int]] = field(default_factory=set[tuple[int, int]])
    deadline: float | None = None  # wall time; None keeps the window open

    async def advance(self, seconds: float) -> None:
        """The journeys' injected sleep: server time moves, no real wait."""
        self.now += seconds

    def clock(self) -> float:
        """Server wall time: the real clock plus every injected advance."""
        return time.time() + self.now

    def window_open(self) -> bool:
        return self.deadline is None or self.clock() < self.deadline

    def break_rule(self, name: str) -> None:
        self.broken = name

    # -- state helpers -------------------------------------------------------
    def fixture_fursuit_ids(self) -> set[int]:
        return {
            int(str(f["id"])) for owned in self.state.fursuits.values() for f in owned
        }

    def owner_of(self, fursuit_id: int) -> int | None:
        for index, owned in self.state.fursuits.items():
            if fursuit_id in {int(str(f["id"])) for f in owned}:
                return index
        return self.created_owner.get(fursuit_id)

    def fursuit(self, fursuit_id: int) -> dict[str, object]:
        for owned in self.state.fursuits.values():
            for body in owned:
                if body["id"] == fursuit_id:
                    return body
        return self.created[fursuit_id]

    def fursuits_of(self, index: int) -> list[dict[str, object]]:
        mine = [b for f, b in self.created.items() if self.created_owner[f] == index]
        return [*self.state.fursuits.get(index, []), *mine]

    def avatar_url(self, index: int) -> str | None:
        version = self.avatars.get(index)
        return None if version is None else media_url("AVATAR", index, version)

    def live(self, fursuit_id: int, payload: str) -> bool:
        return (
            payload not in self.revoked
            and self.sessions.get(fursuit_id, False)
            and fursuit_id not in self.deactivated
        )

    def issue(self, fursuit_id: int) -> str:
        version = len(self.issued.setdefault(fursuit_id, [])) + 1
        text = f"SENTINEL-{fursuit_id}-{version}-".ljust(43, "x")[:43]
        payload = f"tailtag:catch:v1:{text}"
        self.issued[fursuit_id].append(payload)
        self.fursuit_of[payload] = fursuit_id
        return payload

    def body(self) -> dict[str, object]:
        assert self.request is not None
        return cast(dict[str, object], json.loads(self.request.content))

    # -- routing -------------------------------------------------------------
    def route(self, method: str, path: str, index: int) -> httpx.Response | None:
        request = self.request
        assert request is not None
        if path == ACTIVE_PATH and method in ("DELETE", "PUT"):
            return self.active_convention(method, index)
        if (method, path) == (
            "GET",
            ACTIVE_PATH,
        ) and index in self.inactive_enrollments:
            return reply(200, {"enrollment": None})
        if (method, path) == ("GET", FURSUITS_PATH):
            return reply(200, self.fursuits_of(index))
        if (method, path) == ("POST", CREATE_PATH):
            return self.create_fursuit(index)
        if (method, path) == ("POST", RESOLVE_PATH):
            return self.resolve(index)
        if (method, path) == ("POST", CONFIRM_PATH):
            return self.confirm(index)
        if (method, path) == ("GET", HISTORY_PATH):
            return self.history(index)
        handled = self.request_route(method, path, index)
        if handled is not None:
            return handled
        if path == AVATAR_PATH and method in ("PUT", "DELETE"):
            return self.avatar(method, index)
        photo = re.fullmatch(r"/api/fursuits/(\d+)/photo/", path)
        if method == "PUT" and photo is not None:
            return self.replace_photo(index, int(photo[1]))
        owned = re.fullmatch(
            r"/api/conventions/(\d+)/fursuit-activations/(\d+)/([a-z/-]*)", path
        )
        if owned is not None and int(owned[1]) == CONVENTION_ID:
            return self.owner_action(method, int(owned[2]), owned[3], index)
        return self.state.route(method, path, index)

    def active_convention(self, method: str, index: int) -> httpx.Response:
        if index not in self.state.enrollments:
            return not_found()
        if method == "DELETE":
            self.inactive_enrollments.add(index)
            return reply(204)
        if self.body().get("convention_id") != CONVENTION_ID:
            return not_found()
        self.inactive_enrollments.discard(index)
        return reply(200, enrollment_body(CONVENTION_ID))

    def owner_action(
        self, method: str, fursuit_id: int, suffix: str, index: int
    ) -> httpx.Response | None:
        leaking = self.broken == "not_owner" and (method, suffix) == ("GET", CREDENTIAL)
        if self.owner_of(fursuit_id) != index and not leaking:
            return not_found()  # before the body is parsed
        if (method, suffix) == ("PUT", CATCH_SESSION):
            active = self.body().get("is_active") is True
            if fursuit_id in self.deactivated:
                return failure(409, "activation_inactive")
            # A broken stop leaves the session live although it reports it stopped.
            self.sessions[fursuit_id] = active or self.broken == "stopped_session"
            expires = "2026-10-03T12:00:00Z" if active else None
            return reply(200, {"is_active": active, "expires_at": expires})
        if (method, suffix) == ("GET", CREDENTIAL):
            if fursuit_id in self.deactivated:
                return not_found()
            payload = (self.issued.get(fursuit_id) or [self.issue(fursuit_id)])[-1]
            return reply(200, {"payload": payload})
        if (method, suffix) == ("POST", ROTATE):
            if fursuit_id in self.deactivated:
                return not_found()
            old = (self.issued.get(fursuit_id) or [self.issue(fursuit_id)])[-1]
            if self.broken != "stale_credential":
                self.revoked.add(old)
            return reply(200, {"payload": self.issue(fursuit_id)})
        if (method, suffix) == ("PUT", ""):
            return self.set_activation(fursuit_id)
        return None

    def set_activation(self, fursuit_id: int) -> httpx.Response:
        active = self.body().get("is_active") is True
        if active:
            self.deactivated.discard(fursuit_id)
        elif self.broken != "deactivated":  # broken: only the response changes
            # A reusable tag outlives a deactivation; the session does not.
            self.deactivated.add(fursuit_id)
            self.sessions[fursuit_id] = False
        return reply(200, {**activation_body(fursuit_id), "is_active": active})

    def resolve(self, index: int) -> httpx.Response:
        if index not in self.state.enrollments:
            return reply(403, {"detail": "SENTINEL not enrolled"})
        payload = self.body().get("payload")
        fursuit_id = self.fursuit_of.get(str(payload))
        if fursuit_id is None or not self.live(fursuit_id, str(payload)):
            return not_found()
        fursuit = self.fursuit(fursuit_id)
        return reply(
            200,
            {
                "convention_id": CONVENTION_ID,
                "fursuit": {
                    "tailtag_id": fursuit["tailtag_id"],
                    "name": fursuit["name"],
                    "photo_url": fursuit["photo_url"],
                },
            },
        )

    def confirm(self, index: int) -> httpx.Response:
        unavailable = failure(404, "catch_target_unavailable")
        payload = str(self.body().get("payload"))
        fursuit_id = self.fursuit_of.get(payload)
        if fursuit_id is None:
            return unavailable
        available = self.live(fursuit_id, payload)
        if self.broken == "retry" and not available:
            return unavailable  # target checks wrongly before already-caught
        for caught in self.catches:
            if (caught.catcher, caught.fursuit_id) == (index, fursuit_id):
                return reply(200, self.catch_body("already_caught", caught))
        if index not in self.state.enrollments and self.broken != "ineligible_catcher":
            return failure(403, "catcher_ineligible")
        if index in self.inactive_enrollments and self.broken != "convention_mismatch":
            return failure(409, "active_convention_mismatch")
        if not available:
            return unavailable
        if self.owner_of(fursuit_id) == index and self.broken != "self_catch":
            unknown = self.broken == "self_catch_unknown_code"
            return failure(
                409, "SENTINEL_UNKNOWN_CODE" if unknown else "self_catch_not_allowed"
            )
        caught = Catch(7000 + len(self.catches) + 1, index, fursuit_id)
        self.catches.append(caught)
        if self.broken == "catch":
            return reply(200, self.catch_body("already_caught", caught))
        return reply(201, self.catch_body("created", caught))

    def catch_body(self, outcome: str, caught: Catch) -> dict[str, object]:
        return {"outcome": outcome, "catch": self.catch_view(caught)}

    def catch_view(self, caught: Catch) -> dict[str, object]:
        return {
            "id": caught.id,
            "fursuit": self.fursuit(caught.fursuit_id),
            "caught_at": "2026-10-03T12:00:00Z",
        }

    def history(self, index: int) -> httpx.Response:
        assert self.request is not None
        if self.request.url.params.get("convention_id") != str(CONVENTION_ID):
            results: list[dict[str, object]] = []
        else:
            results = [self.catch_view(c) for c in self.catches if c.catcher == index]
        return reply(
            200,
            {
                "catch_count": len(results),
                "next": None,
                "previous": None,
                "results": results,
            },
        )

    # -- the catch request flow (#508) ----------------------------------------
    def request_route(
        self, method: str, path: str, index: int
    ) -> httpx.Response | None:
        tag = re.fullmatch(r"/api/fursuits/(\d+)/(tag/|tag/replace/|)", path)
        if tag is not None:
            return self.tag_action(method, int(tag[1]), tag[2], index)
        if (method, path) == ("POST", PREVIEW_PATH):
            return self.preview(index)
        if (method, path) == ("POST", REQUESTS_PATH):
            return self.submit(index)
        if (method, path) == ("GET", REQUESTS_PATH):
            mine = [
                r
                for r in reversed(self.rows)
                if r.player == index and self.window_open()
            ]
            return reply(200, {"results": [self.request_view(r) for r in mine]})
        if (method, path) == ("GET", INCOMING_PATH):
            mine = [
                r
                for r in reversed(self.rows)
                if self.owner_of(r.fursuit_id) == index and self.window_open()
            ]
            return reply(
                200,
                {
                    "results": [
                        {
                            **self.request_view(r),
                            "player": {"display_name": "", "handle": ""},
                        }
                        for r in mine
                    ]
                },
            )
        withdraw = re.fullmatch(r"/api/catches/requests/(\d+)/withdraw/", path)
        if method == "POST" and withdraw is not None:
            return self.withdraw(index, int(withdraw[1]))
        action = re.fullmatch(r"/api/catches/incoming-requests/(\d+)/([a-z-]+)/", path)
        if method == "POST" and action is not None:
            return self.decide(index, int(action[1]), action[2])
        return None

    def current_payload(self, fursuit_id: int) -> str:
        return (self.issued.get(fursuit_id) or [self.issue(fursuit_id)])[-1]

    def tag_action(
        self, method: str, fursuit_id: int, suffix: str, index: int
    ) -> httpx.Response | None:
        leaking = self.broken == "not_owner" and (method, suffix) == ("GET", "tag/")
        if self.owner_of(fursuit_id) != index and not leaking:
            return failure(404, "fursuit_not_found")
        if (method, suffix) == ("PATCH", ""):
            self.modes[fursuit_id] = str(self.body()["catch_approval_mode"])
            return reply(
                200, {"id": fursuit_id, "catch_approval_mode": self.modes[fursuit_id]}
            )
        if (method, suffix) == ("GET", "tag/"):
            return reply(200, self.tag_view(fursuit_id))
        if (method, suffix) == ("POST", "tag/replace/"):
            old = self.current_payload(fursuit_id)
            if self.body().get("expected_version") != len(self.issued[fursuit_id]):
                return failure(409, "tag_version_conflict")
            if self.broken != "replaced_tag":
                self.revoked.add(old)
            self.issue(fursuit_id)
            return reply(200, self.tag_view(fursuit_id))
        return None

    def tag_view(self, fursuit_id: int) -> dict[str, object]:
        payload = self.current_payload(fursuit_id)
        return {
            "fursuit_id": fursuit_id,
            "state": "current",
            "tag_version": len(self.issued[fursuit_id]),
            "payload": payload,
        }

    def summary(self, fursuit_id: int) -> dict[str, object]:
        fursuit = self.fursuit(fursuit_id)
        return {
            "id": fursuit_id,
            "tailtag_id": fursuit["tailtag_id"],
            "name": fursuit["name"],
            "photo_url": fursuit["photo_url"],
        }

    def request_view(self, row: RequestRow) -> dict[str, object]:
        return {
            "id": row.id,
            "fursuit": self.summary(row.fursuit_id),
            "convention_id": CONVENTION_ID,
            "state": row.state,
            "requested_at": AT,
            "review_deadline_at": "2026-10-06T04:00:00Z"
            if self.deadline is None
            else datetime.fromtimestamp(self.deadline, UTC).isoformat(),
        }

    def catch_for(self, index: int, fursuit_id: int) -> Catch | None:
        return next(
            (
                c
                for c in self.catches
                if (c.catcher, c.fursuit_id) == (index, fursuit_id)
            ),
            None,
        )

    def eligible(self, index: int) -> bool:
        enrolled = (
            index in self.state.enrollments or self.broken == "ineligible_catcher"
        )
        selected = (
            index not in self.inactive_enrollments
            or self.broken == "convention_mismatch"
        )
        return enrolled and selected

    def preview(self, index: int) -> httpx.Response:
        payload = str(self.body().get("payload"))
        fursuit_id = self.fursuit_of.get(payload)
        if not self.eligible(index):
            return failure(403, "catcher_ineligible")
        known = fursuit_id is not None and (
            self.live(fursuit_id, payload) or self.broken == "replaced_tag"
        )
        if fursuit_id is None or not known or (index, fursuit_id) in self.blocks:
            return failure(404, "catch_target_unavailable")
        return reply(
            200, {"fursuit": self.summary(fursuit_id), "convention_id": CONVENTION_ID}
        )

    def submit(self, index: int) -> httpx.Response:
        unavailable = failure(404, "catch_target_unavailable")
        payload = str(self.body().get("payload"))
        fursuit_id = self.fursuit_of.get(payload)
        if fursuit_id is None:
            return unavailable
        if not self.eligible(index):
            return failure(403, "catcher_ineligible")
        caught = self.catch_for(index, fursuit_id)
        if caught is not None:
            return reply(
                200,
                {
                    "outcome": "already_caught",
                    "request": None,
                    "catch": self.request_catch(caught),
                },
            )
        pending = next(
            (
                r
                for r in self.rows
                if (r.player, r.fursuit_id) == (index, fursuit_id)
                and r.state == "pending"
            ),
            None,
        )
        # Each break is scoped to the catcher its journey uses: retry uses the
        # second catcher (index 4) and duplicate the third (index 5).
        forget = (self.broken, index) in {("retry", 4), ("duplicate", 5)}
        if pending is not None and not forget:
            return reply(
                200,
                {
                    "outcome": "already_pending",
                    "request": self.request_view(pending),
                    "catch": None,
                },
            )
        # Stopped, deactivated, and replaced breaks already keep the target live.
        if not self.live(fursuit_id, payload):
            return unavailable
        if (index, fursuit_id) in self.blocks and self.broken != "decline_block":
            return unavailable
        if self.owner_of(fursuit_id) == index and self.broken != "self_catch":
            unknown = self.broken == "self_catch_unknown_code"
            return failure(
                409, "SENTINEL_UNKNOWN_CODE" if unknown else "self_catch_not_allowed"
            )
        declined = [
            r.declined_at
            for r in self.rows
            if (r.player, r.fursuit_id) == (index, fursuit_id)
            and r.declined_at is not None
        ]
        if declined and self.clock() < max(declined) + 10 and self.broken != "cooldown":
            return httpx.Response(
                429,
                headers={"Retry-After": "10"},
                json={
                    "code": "cooldown_active",
                    "detail": "Try again later.",
                    "retry_after_seconds": 10,
                },
            )
        recent = [
            r.created_at
            for r in self.rows
            if r.player == index and r.created_at > self.clock() - 600
        ]
        if len(recent) >= 30 and self.broken != "abuse_limit":
            wait = max(1, math.ceil(min(recent) + 600 - self.clock()))
            return httpx.Response(
                429,
                headers={"Retry-After": str(wait)},
                json={
                    "code": "rate_limited",
                    "detail": "Try again later.",
                    "retry_after_seconds": wait,
                },
            )
        row = RequestRow(
            8000 + len(self.rows) + 1,
            index,
            fursuit_id,
            "pending",
            created_at=self.clock(),
        )
        self.rows.append(row)
        if self.modes.get(fursuit_id) == "automatic" and self.broken != "automatic":
            caught = self.approve(row)
            return reply(
                201,
                {
                    "outcome": "approved",
                    "request": self.request_view(row),
                    "catch": self.request_catch(caught),
                },
            )
        return reply(
            201,
            {"outcome": "pending", "request": self.request_view(row), "catch": None},
        )

    def request_catch(self, caught: Catch) -> dict[str, object]:
        view = self.catch_view(caught)
        fursuit = cast(dict[str, object], view["fursuit"])
        return {
            **view,
            "approved_at": AT,
            "convention_id": CONVENTION_ID,
            "fursuit": {k: fursuit[k] for k in ("tailtag_id", "name", "photo_url")},
        }

    def approve(self, row: RequestRow) -> Catch:
        row.state = "approved"
        caught = Catch(7000 + len(self.catches) + 1, row.player, row.fursuit_id)
        self.catches.append(caught)
        return caught

    def withdraw(self, index: int, request_id: int) -> httpx.Response:
        row = next(
            (r for r in self.rows if r.id == request_id and r.player == index), None
        )
        if row is None:
            return failure(404, "request_not_found")
        if row.state != "pending":
            return failure(409, "request_state_changed")
        row.state = "withdrawn"
        return reply(200, self.request_view(row))

    def decide(self, index: int, request_id: int, action: str) -> httpx.Response:
        row = next(
            (
                r
                for r in self.rows
                if r.id == request_id and self.owner_of(r.fursuit_id) == index
            ),
            None,
        )
        if row is None:
            return failure(404, "request_not_found")
        if not self.window_open() and self.broken != "expiry":
            return failure(409, "review_window_closed")
        changed = failure(409, "request_state_changed")
        if action == "approve":
            if row.state != "pending" and not (
                self.broken == "withdraw" and row.state == "withdrawn"
            ):
                return changed
            caught = self.approve(row)
            view = self.request_catch(caught)
            if self.broken == "pending_approve":
                view = {**view, "caught_at": "2026-10-03T12:00:01Z"}
            return reply(200, {"request": self.request_view(row), "catch": view})
        if action == "decline":
            if row.state != "pending":
                return changed
            if self.broken != "decline":
                row.state = "declined"
                row.declined_at = self.clock()
                row.blocked = self.body().get("block") is True
                if row.blocked:
                    self.blocks.add((row.player, row.fursuit_id))
            return reply(200, self.request_view(row))
        if action in ("undo-decline", "restore"):
            if row.state != "declined":
                return changed
            expired = (
                row.blocked
                or row.declined_at is None
                or self.clock() >= row.declined_at + 10
            )
            if action == "undo-decline" and (
                self.broken == "undo" or (expired and self.broken != "restore")
            ):
                return failure(409, "undo_expired")
            row.state, row.declined_at = "pending", None
            return reply(200, self.request_view(row))
        return failure(404, "request_not_found")

    # -- images --------------------------------------------------------------
    def read_upload(self, key: str, text: set[str]) -> Uploaded | httpx.Response:
        assert self.request is not None
        parts = parse_multipart(self.request)
        files = sorted(name for name, is_file, _ in parts if is_file)
        texts = sorted(name for name, is_file, _ in parts if not is_file)
        if files != [key] or texts != sorted(text):
            return reply(400, {key: ["This field is required."]})
        content = next(data for name, _, data in parts if name == key)
        error = image_error(content)
        if error == UNSUPPORTED_FORMAT and self.broken == "image_rejections":
            error = None  # the broken API stores a GIF
        if error is not None:
            return reply(400, {key: [error]})
        fields = {n: d.decode() for n, is_file, d in parts if not is_file}
        return Uploaded(content, fields)

    def create_fursuit(self, index: int) -> httpx.Response:
        upload = self.read_upload("photo", {"name"})
        if isinstance(upload, httpx.Response):
            return upload
        name = upload.fields["name"]
        if not 1 <= len(name) <= 50:
            return reply(400, {"name": ["Enter a name of 1 to 50 characters."]})
        fursuit_id = 900 + len(self.created) + 1
        self.stored.append(upload.content)
        self.created[fursuit_id] = {
            **fursuit_body(fursuit_id, name),
            "photo_url": media_url("KEY", fursuit_id),
        }
        self.created_owner[fursuit_id] = index
        return reply(201, self.created[fursuit_id])

    def replace_photo(self, index: int, fursuit_id: int) -> httpx.Response:
        if self.owner_of(fursuit_id) != index:
            return not_found()
        self.photo_puts.append((index, fursuit_id))
        upload = self.read_upload("photo", set())
        if isinstance(upload, httpx.Response):
            return upload
        self.stored.append(upload.content)
        body = dict(self.fursuit(fursuit_id))
        scheme = "http" if self.broken == "fursuit_photo" else "https"
        body["photo_url"] = media_url("KEY", fursuit_id, len(self.stored), scheme)
        if fursuit_id in self.created:
            self.created[fursuit_id] = body
        return reply(200, body)

    def avatar(self, method: str, index: int) -> httpx.Response:
        if method == "DELETE":
            if self.broken != "avatar":
                self.avatars.pop(index, None)
            return reply(204)
        self.avatar_puts.append(index)
        if self.broken == "avatar_redirect":
            return httpx.Response(307, headers={"location": "https://evil.example/x"})
        if self.broken == "avatar_unexpected":
            raise RuntimeError("SENTINEL unexpected failure outside HTTP")
        upload = self.read_upload("avatar", set())
        if isinstance(upload, httpx.Response):
            return upload
        self.stored.append(upload.content)
        self.avatars[index] = len(self.stored)
        return reply(
            200,
            {
                **onboarded(index),
                "avatar_url": self.avatar_url(index),
                "onboarding_complete": True,
                "is_enabled": True,
            },
        )


@dataclass
class JourneyWorld(World):
    """A World for 8 identities whose extra route is the gameplay fake."""

    users: dict[int, dict[str, object]] = field(
        default_factory=lambda: {i: user_json(i) for i in range(INDEXES)}
    )
    profiles: dict[int, dict[str, object]] = field(
        default_factory=lambda: {i: not_onboarded() for i in range(INDEXES)}
    )
    leftover_sessions: dict[int, list[str]] = field(
        default_factory=lambda: {i: [f"sess_old{i}"] for i in range(INDEXES)}
    )
    gameplay: Gameplay = field(default_factory=Gameplay)

    def __post_init__(self) -> None:
        self.route = self.gameplay.route

    def _api(self, request: httpx.Request) -> httpx.Response:
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        identity: int | None
        try:
            identity = int(str(jwt_claims(bearer)["sub"]).removeprefix("user_SECRET"))
        except (IndexError, KeyError, ValueError):
            identity = None
        if request.url.host == API_HOST and request.url.path not in {
            "/health/identity",
            "/health/ready",
        }:
            self.gameplay.requests.append((request.method, request.url.path, identity))
        self.gameplay.request = request
        if self.gameplay.broken == "unauthenticated" and bearer == "not-a-token":
            return httpx.Response(200, json={"id": 1})
        return super()._api(request)

    def _profile(self, index: int) -> httpx.Response:
        body = cast(dict[str, object], json.loads(super()._profile(index).content))
        body["avatar_url"] = self.gameplay.avatar_url(index)
        return httpx.Response(200, json=body)


@pytest.fixture
def journey_world(world: World) -> JourneyWorld:
    # `world` is requested only for its side effect: the re-derived Clerk fingerprint.
    del world
    return JourneyWorld()
