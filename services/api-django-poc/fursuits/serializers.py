"""API serialization for owned fursuit profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import serializers

from .models import Fursuit

if TYPE_CHECKING:
    FursuitModelSerializer = serializers.ModelSerializer[Fursuit]
else:
    FursuitModelSerializer = serializers.ModelSerializer


class FursuitSerializer(FursuitModelSerializer):
    """Validate fursuit text fields without allowing owner reassignment."""

    description = serializers.CharField(
        allow_blank=True,
        max_length=2000,
        required=False,
        trim_whitespace=True,
    )

    class Meta:
        """Configure public fursuit fields."""

        fields = (
            "id",
            "owner_id",
            "name",
            "species",
            "description",
            "created_at",
            "updated_at",
        )
        model = Fursuit
        read_only_fields = ("id", "owner_id", "created_at", "updated_at")

    def validate_name(self, value: str) -> str:
        """Reject a name that becomes blank after trimming."""
        if not value:
            message = "This field may not be blank."
            raise serializers.ValidationError(message)
        return value

    def validate_species(self, value: str) -> str:
        """Reject a species that becomes blank after trimming."""
        if not value:
            message = "This field may not be blank."
            raise serializers.ValidationError(message)
        return value
