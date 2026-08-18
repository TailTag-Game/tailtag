"""Current TailTag application-identity API views."""

from __future__ import annotations

from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

CURRENT_USER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "integer",
        },
    },
    "required": ["id"],
    "additionalProperties": False,
}

AUTHENTICATION_ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}


class CurrentUserView(APIView):
    """Return the authenticated TailTag application-user identity."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses={
            200: OpenApiResponse(response=CURRENT_USER_RESPONSE_SCHEMA),
            401: OpenApiResponse(response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA),
        },
    )
    def get(self, request: Request) -> Response:
        return Response({"id": request.user.pk})
