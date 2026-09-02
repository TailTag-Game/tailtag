"""Player-facing convention and enrollment API views."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import (  # pyright: ignore[reportUnknownVariableType]
    OpenApiResponse,
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from rest_framework import generics, serializers, status
from rest_framework.exceptions import (
    ErrorDetail,
    NotFound,
    ParseError,
    UnsupportedMediaType,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from fursuits.models import Fursuit

from . import catch_credentials, catch_sessions, services
from .models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from .serializers import (
    FURSUIT_ACTIVATION_REQUEST_SCHEMA,
    FURSUIT_ACTIVATION_RESPONSE_SCHEMA,
    FURSUIT_CATCH_CREDENTIAL_RESOLUTION_REQUEST_SCHEMA,
    FURSUIT_CATCH_CREDENTIAL_RESOLUTION_RESPONSE_SCHEMA,
    FURSUIT_CATCH_CREDENTIAL_RESPONSE_SCHEMA,
    FURSUIT_CATCH_SESSION_RESPONSE_SCHEMA,
    ActiveConventionResponseSerializer,
    ConventionEnrollmentSerializer,
    ConventionEnrollRequestSerializer,
    ConventionSerializer,
    FursuitActivationRequestSerializer,
    FursuitCatchCredentialResolutionRequestSerializer,
    SelectActiveConventionRequestSerializer,
    enrollment_response_data,
    fursuit_activation_response_data,
    fursuit_catch_credential_resolution_response_data,
    fursuit_catch_credential_response_data,
    fursuit_catch_session_response_data,
)

if TYPE_CHECKING:
    ListAPIViewBase = generics.ListAPIView[Convention]
    RetrieveAPIViewBase = generics.RetrieveAPIView[Convention]
else:
    ListAPIViewBase = generics.ListAPIView
    RetrieveAPIViewBase = generics.RetrieveAPIView

AUTHENTICATION_ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}

NOT_FOUND_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detail": {
            "type": "string",
        },
    },
    "required": ["detail"],
}

FORBIDDEN_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
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


_AUTH_401 = OpenApiResponse(
    response=AUTHENTICATION_ERROR_RESPONSE_SCHEMA,
    description="Authentication credentials were not provided.",
)
_FORBIDDEN_403 = OpenApiResponse(
    response=FORBIDDEN_RESPONSE_SCHEMA,
    description="The player profile is not eligible for participation.",
)
_NOT_FOUND_404 = OpenApiResponse(
    response=NOT_FOUND_RESPONSE_SCHEMA,
    description="The requested resource was not found.",
)
_INVALID_400 = OpenApiResponse(
    response=NOT_FOUND_RESPONSE_SCHEMA,
    description="The supplied activation state is invalid.",
)
_METHOD_405 = OpenApiResponse(
    response=NOT_FOUND_RESPONSE_SCHEMA, description="Method not allowed."
)
_FURSUIT_ACTIVATION_LIST_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": FURSUIT_ACTIVATION_RESPONSE_SCHEMA,
}
_FURSUIT_CATCH_SESSION_OPENAPI_OPERATION: dict[str, object] = {
    "operationId": "convention_fursuit_catch_session_set_state",
    "description": (
        "Idempotently set the desired current catchability. A live session has a "
        "fixed 12-hour expiration; is_active is computed from unexpired session "
        "state and current operational participation. This endpoint is not catch "
        "authorization and catch creation must revalidate its own requirements."
    ),
    "parameters": [
        {
            "in": "path",
            "name": "convention_id",
            "schema": {"type": "integer"},
            "required": True,
        },
        {
            "in": "path",
            "name": "fursuit_id",
            "schema": {"type": "integer"},
            "required": True,
        },
    ],
    "tags": ["conventions"],
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": FURSUIT_ACTIVATION_REQUEST_SCHEMA}},
    },
    "security": [{"BearerAuth": []}],
    "responses": {
        "200": {
            "description": "The canonical desired catch-session state.",
            "content": {
                "application/json": {"schema": FURSUIT_CATCH_SESSION_RESPONSE_SCHEMA}
            },
        },
        "400": {"description": "The supplied activation state is invalid."},
        "401": {"description": "Authentication credentials were not provided."},
        "403": {"description": "The player profile is not eligible for participation."},
        "404": {"description": "The requested resource was not found."},
        "405": {"description": "Method not allowed."},
    },
}
_FURSUIT_CATCH_CREDENTIAL_OPENAPI_RESPONSES: dict[int, OpenApiResponse] = {
    200: OpenApiResponse(response=FURSUIT_CATCH_CREDENTIAL_RESPONSE_SCHEMA),
    400: _INVALID_400,
    401: _AUTH_401,
    403: _FORBIDDEN_403,
    404: _NOT_FOUND_404,
    405: _METHOD_405,
}
_FURSUIT_CATCH_CREDENTIAL_RESOLUTION_OPENAPI_RESPONSES: dict[int, OpenApiResponse] = {
    200: OpenApiResponse(response=FURSUIT_CATCH_CREDENTIAL_RESOLUTION_RESPONSE_SCHEMA),
    400: _INVALID_400,
    401: _AUTH_401,
    403: _FORBIDDEN_403,
    404: OpenApiResponse(
        response=NOT_FOUND_RESPONSE_SCHEMA, description="Catch credential not found."
    ),
    405: _METHOD_405,
}


class _FursuitActivationAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, UnsupportedMediaType):
            return Response(
                {
                    "is_active": [
                        ErrorDetail("Provide a JSON desired state.", code="invalid")
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)


class FursuitCatchCredentialResolutionView(APIView):
    """Resolve a credential preview without mutating credential or session state."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (ParseError, UnsupportedMediaType)):
            return Response(
                {
                    "payload": [
                        ErrorDetail("Invalid catch credential payload.", code="invalid")
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)

    @extend_schema(
        operation_id="convention_fursuit_catch_credential_resolve",
        description=(
            "Resolve an opaque catch credential to a safe current preview only. This is "
            "not catch authorization; future Wave 3 catch writes must submit and "
            "independently revalidate the original payload."
        ),
        request={
            "application/json": FURSUIT_CATCH_CREDENTIAL_RESOLUTION_REQUEST_SCHEMA
        },
        responses=_FURSUIT_CATCH_CREDENTIAL_RESOLUTION_OPENAPI_RESPONSES,
    )
    def post(self, request: Request, convention_id: int) -> Response:
        serializer = FursuitCatchCredentialResolutionRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        convention = Convention.objects.filter(pk=convention_id).first()
        if convention is None:
            raise NotFound() from None
        try:
            services.require_convention_participation_eligible(_user(request))
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        if not ConventionEnrollment.objects.filter(
            user=_user(request), convention=convention
        ).exists():
            raise PermissionDenied from None
        try:
            credential = catch_credentials.resolve_catch_credential(
                convention_id=convention.pk,
                payload=serializer.validated_data["payload"],
            )
        except catch_credentials.CatchCredentialNotFoundError:
            raise NotFound("Catch credential not found.") from None
        return Response(
            fursuit_catch_credential_resolution_response_data(
                credential.activation, request=request
            )
        )


def _owned_fursuit_or_404(user: User, fursuit_id: int) -> Fursuit:
    try:
        return Fursuit.objects.get(pk=fursuit_id, owner=user)
    except Fursuit.DoesNotExist:
        raise NotFound("No fursuit found matching the given ID.") from None


def _convention_or_404(convention_id: int) -> Convention:
    try:
        return Convention.objects.get(pk=convention_id)
    except Convention.DoesNotExist:
        raise NotFound("No convention found matching the given ID.") from None


def _fursuit_activation_response(activation: FursuitActivation) -> Response:
    return Response(
        fursuit_activation_response_data(
            activation,
            is_eligible=services.is_fursuit_activation_eligible(activation),
        )
    )


def _catch_session_response(
    state: catch_sessions.FursuitCatchSessionState,
) -> Response:
    return Response(fursuit_catch_session_response_data(state))


def _owner_catch_credential_error() -> Response:
    return Response(
        {"detail": "The fursuit cannot currently participate in this convention."},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _resolve_owner_credential_resources(
    user: User, *, convention_id: int, fursuit_id: int
) -> None:
    """Resolve owner resources in the public route's required precedence order."""
    if not Fursuit.objects.filter(pk=fursuit_id, owner=user).exists():
        raise NotFound() from None
    _convention_or_404(convention_id)
    if not FursuitActivation.objects.filter(
        fursuit_id=fursuit_id, convention_id=convention_id
    ).exists():
        raise NotFound("No fursuit activation found matching the given ID.")


class FursuitCatchCredentialFetchView(_FursuitActivationAPIView):
    """Fetch an owned activation's opaque credential."""

    @extend_schema(
        operation_id="convention_fursuit_catch_credential_get",
        description=(
            "Return the owner's current opaque catch credential, creating it lazily "
            "when absent. This does not start a catch session and is not catch authorization."
        ),
        responses=_FURSUIT_CATCH_CREDENTIAL_OPENAPI_RESPONSES,
    )
    def get(self, request: Request, convention_id: int, fursuit_id: int) -> Response:
        _resolve_owner_credential_resources(
            _user(request), convention_id=convention_id, fursuit_id=fursuit_id
        )
        try:
            payload = catch_credentials.get_or_create_owner_catch_credential(
                _user(request), convention_id=convention_id, fursuit_id=fursuit_id
            )
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except (
            Convention.DoesNotExist,
            Fursuit.DoesNotExist,
            FursuitActivation.DoesNotExist,
        ):
            raise NotFound() from None
        except (
            services.ConventionNotEnrolledError,
            services.FursuitActivationNotEligibleError,
        ):
            return _owner_catch_credential_error()
        return Response(fursuit_catch_credential_response_data(payload))


class FursuitCatchCredentialRotationView(_FursuitActivationAPIView):
    """Explicitly rotate an owned activation's opaque credential."""

    @extend_schema(
        operation_id="convention_fursuit_catch_credential_rotate",
        description=(
            "Revoke the owner's current opaque catch credential and create a replacement. "
            "The request accepts zero body bytes only and is not catch authorization."
        ),
        responses=_FURSUIT_CATCH_CREDENTIAL_OPENAPI_RESPONSES,
    )
    def post(self, request: Request, convention_id: int, fursuit_id: int) -> Response:
        _resolve_owner_credential_resources(
            _user(request), convention_id=convention_id, fursuit_id=fursuit_id
        )
        if len(request.body) > 0:
            return _owner_catch_credential_error()
        try:
            payload = catch_credentials.rotate_owner_catch_credential(
                _user(request), convention_id=convention_id, fursuit_id=fursuit_id
            )
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except (
            Convention.DoesNotExist,
            Fursuit.DoesNotExist,
            FursuitActivation.DoesNotExist,
        ):
            raise NotFound() from None
        except (
            services.ConventionNotEnrolledError,
            services.FursuitActivationNotEligibleError,
        ):
            return _owner_catch_credential_error()
        return Response(fursuit_catch_credential_response_data(payload))


class FursuitActivationListView(_FursuitActivationAPIView):
    """List the caller's durable fursuit selections for one Convention."""

    @extend_schema(
        operation_id="convention_fursuit_activations_list",
        description=(
            "Return existing owner selections in ascending fursuit_id order. "
            "is_active is the stored selection; is_eligible is computed from "
            "current upstream state. Operational participation requires both."
        ),
        responses={
            200: OpenApiResponse(response=_FURSUIT_ACTIVATION_LIST_SCHEMA),
            401: _AUTH_401,
            404: _NOT_FOUND_404,
            405: _METHOD_405,
        },
    )
    def get(self, request: Request, convention_id: int) -> Response:
        convention = _convention_or_404(convention_id)
        activations = services.list_owned_fursuit_activations(
            _user(request), convention=convention
        )
        return Response(
            [
                fursuit_activation_response_data(
                    activation,
                    is_eligible=services.is_fursuit_activation_eligible(activation),
                )
                for activation in activations
            ]
        )


class FursuitActivationDetailView(_FursuitActivationAPIView):
    """Set the caller's desired fursuit participation state for one Convention."""

    @extend_schema(
        operation_id="convention_fursuit_activations_set_state",
        description=(
            "Idempotently set the stored is_active owner selection. "
            "is_eligible is computed from current upstream state; operational "
            "participation requires both the stored selection and computed eligibility."
        ),
        request={"application/json": FURSUIT_ACTIVATION_REQUEST_SCHEMA},
        responses={
            200: OpenApiResponse(response=FURSUIT_ACTIVATION_RESPONSE_SCHEMA),
            400: _INVALID_400,
            401: _AUTH_401,
            403: _FORBIDDEN_403,
            404: _NOT_FOUND_404,
            405: _METHOD_405,
        },
    )
    def put(self, request: Request, convention_id: int, fursuit_id: int) -> Response:
        # Resolve owner-scoped resources before parsing to preserve concealment.
        _owned_fursuit_or_404(_user(request), fursuit_id)
        _convention_or_404(convention_id)
        if request.content_type.split(";", maxsplit=1)[0] != "application/json":
            raise serializers.ValidationError(
                {
                    "is_active": [
                        ErrorDetail("Provide a JSON desired state.", code="invalid")
                    ]
                }
            )
        serializer = FursuitActivationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            activation = services.set_fursuit_activation_state(
                _user(request),
                convention_id=convention_id,
                fursuit_id=fursuit_id,
                is_active=serializer.validated_data["is_active"],
            )
        except (Fursuit.DoesNotExist, FursuitActivation.DoesNotExist):
            raise NotFound(
                "No fursuit activation found matching the given ID."
            ) from None
        except Convention.DoesNotExist:
            raise NotFound("No convention found matching the given ID.") from None
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except (
            services.ConventionNotEnrolledError,
            services.FursuitActivationNotEligibleError,
        ):
            raise serializers.ValidationError(
                {
                    "is_active": [
                        ErrorDetail(
                            "The fursuit cannot currently participate in this convention.",
                            code="invalid",
                        )
                    ]
                }
            ) from None
        return _fursuit_activation_response(activation)


class FursuitCatchSessionDetailView(_FursuitActivationAPIView):
    """Set the caller's desired current catchability for one activation."""

    @extend_schema(operation=_FURSUIT_CATCH_SESSION_OPENAPI_OPERATION)
    def put(self, request: Request, convention_id: int, fursuit_id: int) -> Response:
        # Resolve resources before parsing to preserve ownership concealment.
        fursuit = _owned_fursuit_or_404(_user(request), fursuit_id)
        convention = _convention_or_404(convention_id)
        if not FursuitActivation.objects.filter(
            fursuit=fursuit, convention=convention
        ).exists():
            raise NotFound("No fursuit activation found matching the given ID.")
        if request.content_type.split(";", maxsplit=1)[0] != "application/json":
            raise serializers.ValidationError(
                {
                    "is_active": [
                        ErrorDetail("Provide a JSON desired state.", code="invalid")
                    ]
                }
            )
        serializer = FursuitActivationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            state = catch_sessions.set_fursuit_catch_session_state(
                _user(request),
                convention_id=convention_id,
                fursuit_id=fursuit_id,
                is_active=serializer.validated_data["is_active"],
            )
        except (Fursuit.DoesNotExist, FursuitActivation.DoesNotExist):
            raise NotFound(
                "No fursuit activation found matching the given ID."
            ) from None
        except Convention.DoesNotExist:
            raise NotFound("No convention found matching the given ID.") from None
        except services.ConventionParticipationIneligibleError:
            raise PermissionDenied from None
        except (
            services.ConventionNotEnrolledError,
            services.FursuitActivationNotEligibleError,
        ):
            raise serializers.ValidationError(
                {
                    "is_active": [
                        ErrorDetail(
                            "The fursuit cannot currently participate in this convention.",
                            code="invalid",
                        )
                    ]
                }
            ) from None
        return _catch_session_response(state)


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
                description="Convention does not exist, is not enrolled, or is not in an active playable state.",
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
