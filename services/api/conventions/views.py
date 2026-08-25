"""Player-facing convention and enrollment API views."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ErrorDetail, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from . import services
from .models import Convention, ConventionStatus
from .serializers import (
    ActiveConventionResponseSerializer,
    ConventionEnrollmentSerializer,
    ConventionEnrollRequestSerializer,
    ConventionSerializer,
    SelectActiveConventionRequestSerializer,
    enrollment_response_data,
)

if TYPE_CHECKING:
    ListAPIViewBase = generics.ListAPIView[Convention]
    RetrieveAPIViewBase = generics.RetrieveAPIView[Convention]
else:
    ListAPIViewBase = generics.ListAPIView
    RetrieveAPIViewBase = generics.RetrieveAPIView

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

FORBIDDEN_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}

VALIDATION_ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "convention_id": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


def _user(request: Request) -> User:
    return cast(User, request.user)


class ConventionListView(ListAPIViewBase):
    """List available conventions for player enrollment selection."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ConventionSerializer
    queryset = Convention.objects.filter(status=ConventionStatus.ACTIVE)

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
    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().get(request, *args, **kwargs)


class ConventionDetailView(RetrieveAPIViewBase):
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
    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().get(request, *args, **kwargs)


class ConventionEnrollmentListCreateView(APIView):
    """List current user's convention enrollments or enroll in an active convention."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List convention enrollments",
        description="Retrieve a list of all convention enrollments for the authenticated player.",
        responses={
            200: ConventionEnrollmentSerializer(many=True),
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        enrollments = services.list_user_enrollments(_user(request))
        return Response([enrollment_response_data(e) for e in enrollments])

    @extend_schema(
        summary="Enroll in convention",
        description="Enroll the authenticated player into an active convention. Idempotent on retry.",
        request=ConventionEnrollRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=ConventionEnrollmentSerializer,
                description="User was already enrolled; existing enrollment returned.",
            ),
            201: OpenApiResponse(
                response=ConventionEnrollmentSerializer,
                description="Successfully enrolled in the convention.",
            ),
            400: OpenApiResponse(
                response=VALIDATION_ERROR_RESPONSE_SCHEMA,
                description="Convention is not open for enrollment.",
            ),
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
            403: OpenApiResponse(
                response=FORBIDDEN_RESPONSE_SCHEMA,
                description="The player profile is not eligible for participation.",
            ),
            404: OpenApiResponse(
                response=NOT_FOUND_RESPONSE_SCHEMA,
                description="No convention found matching the given ID.",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ConventionEnrollRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated: dict[str, object] = serializer.validated_data

        try:
            enrollment, created = services.enroll_in_convention(
                _user(request),
                convention_id=cast(int, validated["convention_id"]),
                set_active=cast(bool, validated.get("set_active", False)),
            )
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except Convention.DoesNotExist:
            raise NotFound("No convention found matching the given ID.") from None
        except services.ConventionNotEligibleForEnrollmentError:
            raise serializers.ValidationError(
                {
                    "convention_id": [
                        ErrorDetail(
                            "Convention is not open for enrollment.", code="invalid"
                        )
                    ]
                }
            ) from None

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            enrollment_response_data(enrollment),
            status=status_code,
        )


class ActiveConventionView(APIView):
    """Retrieve, select, or clear the player's active gameplay convention."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Get active convention",
        description="Retrieve the authenticated player's currently selected active convention enrollment, if any.",
        responses={
            200: ActiveConventionResponseSerializer,
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        active_enrollment = services.get_active_enrollment(_user(request))
        data = (
            enrollment_response_data(active_enrollment)
            if active_enrollment is not None
            else None
        )
        return Response({"enrollment": data})

    @extend_schema(
        summary="Select active convention",
        description="Explicitly select an enrolled active convention as the player's active gameplay context.",
        request=SelectActiveConventionRequestSerializer,
        responses={
            200: ActiveConventionResponseSerializer,
            400: OpenApiResponse(
                response=VALIDATION_ERROR_RESPONSE_SCHEMA,
                description="Convention is not enrolled or is not in an active playable state.",
            ),
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
            403: OpenApiResponse(
                response=FORBIDDEN_RESPONSE_SCHEMA,
                description="The player profile is not eligible for participation.",
            ),
        },
    )
    def put(self, request: Request) -> Response:
        serializer = SelectActiveConventionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated: dict[str, object] = serializer.validated_data

        try:
            enrollment = services.set_active_convention(
                _user(request),
                convention_id=cast(int, validated["convention_id"]),
            )
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except services.ConventionNotEnrolledError:
            raise serializers.ValidationError(
                {
                    "convention_id": [
                        ErrorDetail(
                            "You are not enrolled in this convention.", code="invalid"
                        )
                    ]
                }
            ) from None
        except services.ConventionNotActiveError:
            raise serializers.ValidationError(
                {
                    "convention_id": [
                        ErrorDetail(
                            "Convention is not in an active playable state.",
                            code="invalid",
                        )
                    ]
                }
            ) from None

        return Response({"enrollment": enrollment_response_data(enrollment)})

    @extend_schema(
        summary="Clear active convention",
        description="Clear the authenticated player's active convention selection.",
        responses={
            204: OpenApiResponse(
                description="Active convention selection was cleared.",
            ),
            401: OpenApiResponse(
                response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
                description="Authentication credentials were not provided or are invalid.",
            ),
            403: OpenApiResponse(
                response=FORBIDDEN_RESPONSE_SCHEMA,
                description="The player profile is not eligible for participation.",
            ),
        },
    )
    def delete(self, request: Request) -> Response:
        try:
            services.clear_active_convention(_user(request))
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        return Response(status=status.HTTP_204_NO_CONTENT)
