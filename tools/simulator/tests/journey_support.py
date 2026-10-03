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
import re
import struct
import zlib
from dataclasses import dataclass, field
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
            self.deactivated.add(fursuit_id)
            self.revoked.update(self.issued.get(fursuit_id, []))
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
        if request.url.host == API_HOST and request.url.path != "/health/identity":
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
