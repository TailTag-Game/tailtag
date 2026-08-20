"""Player-facing convention API views."""

from __future__ import annotations

from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Convention
from .serializers import ConventionSerializer

AUTHENTICATION_ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}

NOT_FOUND_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}


class ConventionListView(generics.ListAPIView):
    """List available conventions for player enrollment selection."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ConventionSerializer
    queryset = Convention.objects.all()

    @extend_schema(
        summary="List conventions",
        description="Retrieve a list of conventions with safe public fields for enrollment.",
        responses={
            200: ConventionSerializer(many=True),
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
        },
    )
    def get(self, request, *args, **kwargs):  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        return super().get(request, *args, **kwargs)


class ConventionDetailView(generics.RetrieveAPIView):
    """Retrieve details for a specific convention."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ConventionSerializer
    queryset = Convention.objects.all()

    @extend_schema(
        summary="Retrieve convention",
        description="Retrieve convention details by internal ID.",
        responses={
            200: ConventionSerializer,
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
            404: OpenApiResponse(
                response=NOT_FOUND_RESPONSE_SCHEMA,
                description="No convention found matching the given ID.",
            ),
        },
    )
    def get(self, request, *args, **kwargs):  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        return super().get(request, *args, **kwargs)
