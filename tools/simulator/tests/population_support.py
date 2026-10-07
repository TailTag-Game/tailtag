"""Dynamic HTTP/inspection boundaries for #225; no internal simulator substitutes.

Reuse the legacy public gameplay fake, complete its wire envelopes, and keep real
client/config/engine/comparator behavior. U3 may rebind slots after lease allocation.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from fixture_support import CONVENTION_ID, activation_body, fursuit_body
from journey_support import Gameplay
from pool_support import jwt_claims

ATTENDEE_PERSONAS = ("casual", "active", "heavy", "retry_prone")


def complete_public_reply(
    gameplay: Gameplay, index: int, request: httpx.Request, response: httpx.Response
) -> httpx.Response:
    """Legacy fake payloads omit fields the complete public population flow needs."""
    if not response.content:
        return response
    body: Any = json.loads(response.content)
    if request.url.path == "/api/catches/confirm/" and response.status_code in {
        200,
        201,
    }:
        body["catch"]["convention_id"] = CONVENTION_ID
    if request.url.path == "/api/catches/" and response.status_code == 200:
        for row in body["results"]:
            row["convention"] = {
                "id": CONVENTION_ID,
                "name": "SENTINEL-private-convention",
            }
        number = int(request.url.params.get("page", "1"))
        size = int(request.url.params.get("page_size", "20"))
        start, end = (number - 1) * size, number * size
        if end < len(body["results"]):
            next_url = request.url.copy_set_param("page", str(number + 1))
            body["next"] = str(next_url)
        body["results"] = body["results"][start:end]
    return httpx.Response(response.status_code, json=body)


class PopulationWorld:
    """Variable fixture population behind the approved HTTP and inspection seams."""

    def __init__(self, config: Mapping[str, object], *, id_offset: int = 0) -> None:
        self.config = config
        self.id_offset = id_offset
        self.gameplay = Gameplay()
        self.requests: list[tuple[str, str, str, dict[str, Any]]] = []
        self.fault: str | None = None
        self.failed = False
        self.failure_at: int | None = None
        owners = int(str(config["normal_owners"])) + int(str(config["popular_owners"]))
        attendees = sum(int(str(config[name])) for name in ATTENDEE_PERSONAS)
        self.rebind(range(17, 17 + owners), range(31, 31 + attendees))

    def rebind(self, owners: Sequence[int], attendees: Sequence[int]) -> None:
        self.owners = tuple(owners)
        self.attendees = tuple(attendees)
        self.indexes = {
            **{f"owner{n}": index for n, index in enumerate(owners)},
            **{f"attendee{n}": index for n, index in enumerate(attendees)},
        }
        # Rebinding replaces the synthetic run's fixture population. Keep the
        # state object shared with the fixture channel, but discard old actor
        # mappings so the same logical fursuit cannot have two owners.
        self.gameplay.state.enrollments.clear()
        self.gameplay.state.fursuits.clear()
        self.gameplay.state.activations.clear()
        self.gameplay.state.populate(
            owners, attendees, int(str(self.config["fursuits"]))
        )
        if self.id_offset:
            for index in owners:
                original = self.gameplay.state.fursuits[index]
                shifted = [
                    fursuit_body(int(str(row["id"])) + self.id_offset, str(row["name"]))
                    for row in original
                ]
                self.gameplay.state.fursuits[index] = list(reversed(shifted))
                self.gameplay.state.activations[index] = [
                    activation_body(int(str(row["id"]))) for row in shifted
                ]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.serve)

    def serve(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "staging.tailtag.app"
        token = request.headers["Authorization"].removeprefix("Bearer ")
        if token in self.indexes:
            index = self.indexes[token]
        else:
            index = int(str(jwt_claims(token)["sub"]).removeprefix("user_SECRET"))
        self.gameplay.request = request
        response = self.route(request.method, request.url.path, index)
        assert response is not None, (
            f"unsupported population request: {request.method} {request.url.path}"
        )
        return response

    def route(self, method: str, path: str, index: int) -> httpx.Response | None:
        request = self.gameplay.request
        assert request is not None
        actor = next(actor for actor, slot in self.indexes.items() if slot == index)
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        self.requests.append((actor, method, path, body))
        if path == "/api/me/" and method == "GET":
            return httpx.Response(200, json={"id": self.id_offset + 1000 + index})
        # Reactivation gives the next cycle a new credential, as the real API does.
        if path.endswith("/catch-credential/") and method == "GET":
            fursuit = int(path.split("/")[-3])
            issued = self.gameplay.issued.get(fursuit, [])
            if issued and issued[-1] in self.gameplay.revoked:
                self.gameplay.issue(fursuit)
        response = self.gameplay.route(method, path, index)
        if response is None:
            return None
        response = complete_public_reply(self.gameplay, index, request, response)
        if not self.failed and self.fault is not None:
            if (
                path.endswith("/catch-credentials/resolve/")
                and self.fault == "wrong-target"
            ):
                changed = json.loads(response.content)
                changed["fursuit"]["tailtag_id"] = (
                    "00000000-0000-0000-0000-000000009999"
                )
                self.failed = True
                self.failure_at = len(self.requests) - 1
                return httpx.Response(200, json=changed)
            if path == "/api/catches/confirm/":
                if self.fault == "ambiguous-positive":
                    self.failed = True
                    self.failure_at = len(self.requests) - 1
                    raise httpx.ReadError("SENTINEL-secret-lost-response")
                if self.fault == "wrong-status":
                    self.failed = True
                    self.failure_at = len(self.requests) - 1
                    return httpx.Response(
                        500,
                        json={"code": "SENTINEL-private", "detail": "SENTINEL-private"},
                    )
                if self.fault == "nonconvergent" and response.status_code == 200:
                    self.failed = True
                    self.failure_at = len(self.requests) - 1
                    changed = json.loads(response.content)
                    changed["catch"]["id"] += 123
                    return httpx.Response(200, json=changed)
            if (
                path == "/api/catches/"
                and self.fault == "wrong-history"
                and self.gameplay.catches
            ):
                self.failed = True
                self.failure_at = len(self.requests) - 1
                return httpx.Response(
                    200,
                    json={
                        "catch_count": 0,
                        "next": None,
                        "previous": None,
                        "results": [],
                    },
                )
        return response

    async def inspect(
        self, pool: str, run_id: str, identities: Mapping[str, int]
    ) -> Mapping[str, object]:
        assert dict(identities) == self.indexes
        assert pool and run_id
        return {
            "catches": [
                {
                    "id": caught.id,
                    "catcher": caught.catcher,
                    "fursuit": caught.fursuit_id,
                    "fursuit_owner": self.gameplay.owner_of(caught.fursuit_id),
                    "run_convention": True,
                    "provenance": True,
                    "in_window": True,
                    "caught_at": "2026-10-03T12:00:00Z",
                }
                for caught in self.gameplay.catches
            ],
            "fursuits": [],
            "fixture_photos_unchanged": True,
            "avatars": [],
        }

    def owner_targets(self, owner: int) -> tuple[int, ...]:
        return tuple(
            sorted(int(str(row["id"])) for row in self.gameplay.state.fursuits[owner])
        )
