"""Named OpenAPI components for the catch request operations (#505).

Inline schemas make the Dart generator emit one class per response position,
so the same shape appeared many times in the client. These components appear
once. The operations point at them with ``$ref``, and the
``add_catch_request_components`` hook in ``config.openapi`` adds them.

This module imports no Django models, so settings and hooks can import it.
"""

from __future__ import annotations

from typing import Final

_TIME: Final[dict[str, object]] = {"type": "string", "format": "date-time"}


def component_ref(name: str) -> dict[str, object]:
    """Return a ``$ref`` to the component *name*."""
    if name not in CATCH_REQUEST_COMPONENTS:
        message = f"Unknown OpenAPI component {name!r}."
        raise KeyError(message)
    return {"$ref": f"#/components/schemas/{name}"}


CATCH_APPROVAL_MODES: Final = ("manual", "automatic")
PLAYER_REQUEST_STATES: Final = (
    "pending",
    "approved",
    "declined",
    "withdrawn",
    "unavailable",
)
SUBMISSION_OUTCOMES: Final = (
    "pending",
    "approved",
    "already_pending",
    "already_caught",
)

CATCH_REQUEST_COMPONENTS: Final[dict[str, dict[str, object]]] = {
    "CatchApprovalMode": {
        "type": "string",
        "enum": list(CATCH_APPROVAL_MODES),
        "description": "manual by default. A change applies only to new requests.",
    },
    "CatchRequestState": {
        "type": "string",
        "enum": list(PLAYER_REQUEST_STATES),
    },
    "CatchRequestOutcome": {
        "type": "string",
        "enum": list(SUBMISSION_OUTCOMES),
    },
    "FursuitSummary": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "integer"},
            "tailtag_id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "photo_url": {"type": "string", "format": "uri"},
        },
        "required": ["id", "tailtag_id", "name", "photo_url"],
    },
    "PlayerRequest": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "integer"},
            "fursuit": {"$ref": "#/components/schemas/FursuitSummary"},
            "convention_id": {"type": "integer"},
            "state": {"$ref": "#/components/schemas/CatchRequestState"},
            "requested_at": _TIME,
            "review_deadline_at": _TIME,
        },
        "required": [
            "id",
            "fursuit",
            "convention_id",
            "state",
            "requested_at",
            "review_deadline_at",
        ],
    },
    "PlayerRequestList": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/PlayerRequest"},
            }
        },
        "required": ["results"],
    },
    "RequestCatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "integer"},
            "caught_at": _TIME,
            "approved_at": _TIME,
            "convention_id": {"type": "integer"},
            "fursuit": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tailtag_id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "photo_url": {"type": "string", "format": "uri"},
                },
                "required": ["tailtag_id", "name", "photo_url"],
            },
        },
        "required": ["id", "caught_at", "approved_at", "convention_id", "fursuit"],
    },
    # ``nullable`` beside ``$ref`` makes the Dart generator emit a plain nullable
    # field. The ``allOf`` form made it wrap each value in an extra class.
    "CatchRequestSubmission": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "outcome": {"$ref": "#/components/schemas/CatchRequestOutcome"},
            "request": {"$ref": "#/components/schemas/PlayerRequest", "nullable": True},
            "catch": {"$ref": "#/components/schemas/RequestCatch", "nullable": True},
        },
        "required": ["outcome", "request", "catch"],
    },
    "CatchRequestPayload": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "payload": {
                "type": "string",
                "description": (
                    "The full scanned tag payload, https://tailtag.app/t#<token>."
                ),
            }
        },
        "required": ["payload"],
    },
    "CatchRequestError": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"code": {"type": "string"}, "detail": {"type": "string"}},
        "required": ["code", "detail"],
    },
    "CatchRequestNotFound": {
        "type": "object",
        "additionalProperties": False,
        "description": (
            "catch_target_unavailable carries code and detail. While the gate is "
            "off, the generic not-found body carries detail only."
        ),
        "properties": {"code": {"type": "string"}, "detail": {"type": "string"}},
        "required": ["detail"],
    },
    "DetailError": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"detail": {"type": "string"}},
        "required": ["detail"],
    },
}
