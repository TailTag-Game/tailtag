"""Focused page-number pagination for the player catch-history response."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .serializers import CatchHistoryEntryData


class CatchHistoryPagination(PageNumberPagination):
    """Return the frozen catch-history pagination envelope."""

    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100
    last_page_strings: tuple[str, ...] = ()  # pyright: ignore[reportIncompatibleVariableOverride] - DRF accepts the immutable tuple.

    def get_paginated_response(self, data: list[CatchHistoryEntryData]) -> Response:
        assert self.page is not None  # pyright: ignore[reportUnknownMemberType] - DRF initializes this page before response construction.
        return Response(
            {
                "catch_count": self.page.paginator.count,  # pyright: ignore[reportUnknownMemberType] - DRF initializes this page before response construction.
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
