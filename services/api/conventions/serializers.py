"""DRF serializers for convention endpoints."""

from __future__ import annotations

from rest_framework import serializers

from .models import Convention


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
