"""DRF serializers for convention endpoints."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from .models import Convention


class ConventionSerializer(serializers.ModelSerializer[Convention]):
    """Serializer exposing safe, read-only convention representation."""

    class Meta:
        model = Convention
        fields: ClassVar[list[str]] = [
            "id",
            "name",
            "status",
            "start_date",
            "end_date",
        ]
        read_only_fields: ClassVar[list[str]] = [
            "id",
            "name",
            "status",
            "start_date",
            "end_date",
        ]
