"""Authenticated owner-scoped fursuit endpoints."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import Fursuit
from .serializers import FursuitSerializer


@extend_schema_view(
    get=extend_schema(
        operation_id="fursuits_list", responses={200: FursuitSerializer(many=True)}
    ),
    post=extend_schema(
        operation_id="fursuits_create",
        request=FursuitSerializer,
        responses={201: FursuitSerializer},
    ),
)
class FursuitListView(APIView):
    """List and create fursuits belonging to the authenticated user."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        """Return only the caller's fursuits."""
        fursuits = Fursuit.objects.filter(owner=cast(User, request.user))
        return Response(FursuitSerializer(fursuits, many=True).data)

    def post(self, request: Request) -> Response:
        """Create a fursuit owned by the authenticated user."""
        serializer = FursuitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fursuit = serializer.save(owner=cast(User, request.user))
        return Response(FursuitSerializer(fursuit).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        operation_id="fursuits_retrieve", responses={200: FursuitSerializer}
    ),
    patch=extend_schema(
        operation_id="fursuits_partial_update",
        request=FursuitSerializer,
        responses={200: FursuitSerializer},
    ),
    delete=extend_schema(operation_id="fursuits_destroy", responses={204: None}),
)
class FursuitDetailView(APIView):
    """Retrieve, update, or delete only the caller's fursuit."""

    permission_classes = (IsAuthenticated,)

    @staticmethod
    def get_fursuit(request: Request, fursuit_id: UUID) -> Fursuit:
        """Look up a fursuit through the owner-scoped queryset."""
        queryset = Fursuit.objects.filter(owner=cast(User, request.user))
        return get_object_or_404(queryset, pk=fursuit_id)

    def get(self, request: Request, fursuit_id: UUID) -> Response:
        """Return one owned fursuit."""
        return Response(FursuitSerializer(self.get_fursuit(request, fursuit_id)).data)

    def patch(self, request: Request, fursuit_id: UUID) -> Response:
        """Partially update one owned fursuit."""
        fursuit = self.get_fursuit(request, fursuit_id)
        serializer = FursuitSerializer(fursuit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(FursuitSerializer(serializer.save()).data)

    def delete(self, request: Request, fursuit_id: UUID) -> Response:
        """Hard-delete one owned POC fursuit."""
        self.get_fursuit(request, fursuit_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
