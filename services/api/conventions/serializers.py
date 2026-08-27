"""DRF serializers and response projections for convention and enrollment endpoints."""

from __future__ import annotations

from typing import TypedDict

from rest_framework import serializers

from .models import Convention, ConventionEnrollment


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
