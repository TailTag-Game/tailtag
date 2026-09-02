"""DRF serializers and response projections for convention and enrollment endpoints."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypedDict, cast

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from media import service as media_service

from .catch_credential_protocol import CATCH_CREDENTIAL_PAYLOAD_PATTERN
from .catch_sessions import FursuitCatchSessionState
from .models import Convention, ConventionEnrollment, FursuitActivation

FURSUIT_CATCH_SESSION_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fursuit_id": {"type": "integer", "readOnly": True},
        "convention_id": {"type": "integer", "readOnly": True},
        "is_active": {"type": "boolean", "readOnly": True},
        "started_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "readOnly": True,
        },
        "expires_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "readOnly": True,
        },
        "ended_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "readOnly": True,
        },
        "end_reason": {
            "type": "string",
            "nullable": True,
            "enum": ["owner", "operator", "eligibility_lost", "expired"],
            "readOnly": True,
        },
    },
    "required": [
        "fursuit_id",
        "convention_id",
        "is_active",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
    ],
}

FURSUIT_ACTIVATION_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fursuit_id": {"type": "integer", "readOnly": True},
        "convention_id": {"type": "integer", "readOnly": True},
        "is_active": {"type": "boolean", "readOnly": True},
        "is_eligible": {"type": "boolean", "readOnly": True},
        "activated_at": {"type": "string", "format": "date-time", "readOnly": True},
        "deactivated_at": {
            "type": "string",
            "format": "date-time",
            "nullable": True,
            "readOnly": True,
        },
    },
    "required": [
        "fursuit_id",
        "convention_id",
        "is_active",
        "is_eligible",
        "activated_at",
        "deactivated_at",
    ],
}

FURSUIT_ACTIVATION_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"is_active": {"type": "boolean"}},
    "required": ["is_active"],
}

FURSUIT_CATCH_CREDENTIAL_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "payload": {
            "type": "string",
            "pattern": CATCH_CREDENTIAL_PAYLOAD_PATTERN,
        }
    },
    "required": ["payload"],
}

FURSUIT_CATCH_CREDENTIAL_RESOLUTION_REQUEST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "payload": {
            "type": "string",
            "pattern": CATCH_CREDENTIAL_PAYLOAD_PATTERN,
        }
    },
    "required": ["payload"],
}

FURSUIT_CATCH_CREDENTIAL_RESOLUTION_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "convention_id": {"type": "integer", "readOnly": True},
        "fursuit": {
            "type": "object",
            "additionalProperties": False,
            "readOnly": True,
            "properties": {
                "tailtag_id": {
                    "type": "string",
                    "format": "uuid",
                    "readOnly": True,
                },
                "name": {"type": "string", "readOnly": True},
                "photo_url": {
                    "type": "string",
                    "format": "uri",
                    "readOnly": True,
                },
            },
            "required": ["tailtag_id", "name", "photo_url"],
        },
    },
    "required": ["convention_id", "fursuit"],
}

FURSUIT_CATCH_CREDENTIAL_RESOLUTION_VALIDATION_ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "payload": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["payload"],
}


class ConventionSerializer(serializers.ModelSerializer[Convention]):
    """Serializer exposing safe, read-only convention representation."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Convention
        fields = (
            "id",
            "name",
            "status",
            "start_date",
            "end_date",
        )
        read_only_fields = (
            "id",
            "name",
            "status",
            "start_date",
            "end_date",
        )


class ConventionEnrollmentSerializer(serializers.ModelSerializer[ConventionEnrollment]):
    """Serializer for convention enrollments."""

    convention = ConventionSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = ConventionEnrollment
        fields = (
            "id",
            "convention",
            "is_active",
            "created_at",
        )
        read_only_fields = (
            "id",
            "convention",
            "is_active",
            "created_at",
        )


class ConventionEnrollRequestSerializer(serializers.Serializer[dict[str, object]]):
    """Request serializer for enrolling into an active convention."""

    convention_id = serializers.IntegerField(min_value=1, required=True)
    set_active = serializers.BooleanField(default=False, required=False)


class SelectActiveConventionRequestSerializer(
    serializers.Serializer[dict[str, object]]
):
    """Request serializer for selecting an active convention."""

    convention_id = serializers.IntegerField(min_value=1, required=True)


class FursuitActivationRequestSerializer(serializers.Serializer[dict[str, bool]]):
    """Accept exactly one explicit desired activation state."""

    is_active = serializers.BooleanField(required=True, allow_null=False)

    def to_internal_value(self, data: Any) -> dict[str, bool]:
        if (
            not isinstance(data, Mapping)
            or set(cast(Mapping[str, object], data)) != {"is_active"}
            or type(cast(Mapping[str, object], data)["is_active"]) is not bool
        ):
            raise serializers.ValidationError(
                {
                    "is_active": [
                        ErrorDetail(
                            "Provide exactly the is_active field.", code="invalid"
                        )
                    ]
                }
            )
        return cast(dict[str, bool], super().to_internal_value(data))


class FursuitCatchCredentialResolutionRequestSerializer(
    serializers.Serializer[dict[str, str]]
):
    """Accept only the exact V1 credential-payload request body."""

    payload = serializers.CharField(allow_blank=False, trim_whitespace=False)

    def to_internal_value(self, data: Any) -> dict[str, str]:
        from .catch_credentials import (
            CatchCredentialPayloadInvalidError,
            parse_catch_credential_payload,
        )

        invalid = {
            "payload": [
                ErrorDetail("Invalid catch credential payload.", code="invalid")
            ]
        }
        if (
            not isinstance(data, Mapping)
            or set(cast(Mapping[str, object], data)) != {"payload"}
            or not isinstance(cast(Mapping[str, object], data)["payload"], str)
        ):
            raise serializers.ValidationError(invalid)
        try:
            parse_catch_credential_payload(cast(Mapping[str, str], data)["payload"])
        except CatchCredentialPayloadInvalidError:
            raise serializers.ValidationError(invalid) from None
        return cast(dict[str, str], super().to_internal_value(data))


class ActiveConventionResponseSerializer(serializers.Serializer[dict[str, object]]):
    """Response wrapper for active convention enrollment query."""

    enrollment = ConventionEnrollmentSerializer(allow_null=True)


class ConventionResponseData(TypedDict):
    id: int
    name: str
    status: str
    start_date: str
    end_date: str


class ConventionEnrollmentResponseData(TypedDict):
    id: int
    convention: ConventionResponseData
    is_active: bool
    created_at: str


class ActiveConventionResponseData(TypedDict):
    enrollment: ConventionEnrollmentResponseData | None


class FursuitActivationResponseData(TypedDict):
    fursuit_id: int
    convention_id: int
    is_active: bool
    is_eligible: bool
    activated_at: str
    deactivated_at: str | None


class FursuitCatchSessionResponseData(TypedDict):
    fursuit_id: int
    convention_id: int
    is_active: bool
    started_at: str | None
    expires_at: str | None
    ended_at: str | None
    end_reason: str | None


class FursuitCatchCredentialResponseData(TypedDict):
    payload: str


class FursuitCatchCredentialResolutionFursuitData(TypedDict):
    tailtag_id: str
    name: str
    photo_url: str


class FursuitCatchCredentialResolutionResponseData(TypedDict):
    convention_id: int
    fursuit: FursuitCatchCredentialResolutionFursuitData


def convention_response_data(convention: Convention) -> ConventionResponseData:
    """Project durable convention state to player-facing representation."""
    return {
        "id": convention.pk,
        "name": convention.name,
        "status": convention.status,
        "start_date": convention.start_date.isoformat(),
        "end_date": convention.end_date.isoformat(),
    }


def enrollment_response_data(
    enrollment: ConventionEnrollment,
) -> ConventionEnrollmentResponseData:
    """Project durable enrollment state to player-facing representation."""
    return {
        "id": enrollment.pk,
        "convention": convention_response_data(enrollment.convention),
        "is_active": enrollment.is_active,
        "created_at": enrollment.created_at.isoformat(),
    }


def fursuit_activation_response_data(
    activation: FursuitActivation, *, is_eligible: bool
) -> FursuitActivationResponseData:
    """Project an activation and its current computed eligibility."""
    return {
        "fursuit_id": activation.fursuit_id,
        "convention_id": activation.convention_id,
        "is_active": activation.is_active,
        "is_eligible": is_eligible,
        "activated_at": activation.activated_at.isoformat().replace("+00:00", "Z"),
        "deactivated_at": (
            activation.deactivated_at.isoformat().replace("+00:00", "Z")
            if activation.deactivated_at is not None
            else None
        ),
    }


def fursuit_catch_session_response_data(
    state: FursuitCatchSessionState,
) -> FursuitCatchSessionResponseData:
    """Project the domain's canonical desired-state result without internal IDs."""
    session = state.session
    if session is None:
        return {
            "fursuit_id": state.activation.fursuit_id,
            "convention_id": state.activation.convention_id,
            "is_active": False,
            "started_at": None,
            "expires_at": None,
            "ended_at": None,
            "end_reason": None,
        }

    def timestamp(value: datetime.datetime) -> str:
        return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")

    return {
        "fursuit_id": state.activation.fursuit_id,
        "convention_id": state.activation.convention_id,
        "is_active": state.is_active,
        "started_at": timestamp(session.started_at),
        "expires_at": timestamp(session.expires_at),
        "ended_at": timestamp(session.ended_at)
        if session.ended_at is not None
        else None,
        "end_reason": session.end_reason,
    }


def fursuit_catch_credential_response_data(
    payload: str,
) -> FursuitCatchCredentialResponseData:
    """Project an opaque credential only through its public payload envelope."""
    return {"payload": payload}


def fursuit_catch_credential_resolution_response_data(
    activation: FursuitActivation, *, request: Any
) -> FursuitCatchCredentialResolutionResponseData:
    """Project a resolved target through the intentionally safe preview shape."""
    fursuit = activation.fursuit
    return {
        "convention_id": activation.convention_id,
        "fursuit": {
            "tailtag_id": str(fursuit.tailtag_id),
            "name": fursuit.name,
            "photo_url": request.build_absolute_uri(
                media_service.read_image_url(fursuit.photo_key)
            ),
        },
    }
