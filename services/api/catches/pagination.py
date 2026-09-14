"""Focused page-number pagination for the player catch-history response."""

from __future__ import annotations

from django.core.paginator import EmptyPage, Paginator
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import CatchHistoryEntryData


class _PrevalidatedPageNumberPaginator(Paginator):  # pyright: ignore[reportMissingTypeArgument] - Django's runtime class is not subscriptable.
    """Avoid reparsing a page number accepted by the closed query parser."""

    def validate_number(self, number: float | str) -> int:
        if not isinstance(number, int):
            raise EmptyPage(self.error_messages["no_results"])
        if number < 1:
            raise EmptyPage(self.error_messages["min_page"])
        if number > self.num_pages:
            raise EmptyPage(self.error_messages["no_results"])
        return number


class CatchHistoryPagination(PageNumberPagination):
    """Return the frozen catch-history pagination envelope."""

    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100
    last_page_strings: tuple[str, ...] = ()  # pyright: ignore[reportIncompatibleVariableOverride] - DRF accepts the immutable tuple.
    django_paginator_class = _PrevalidatedPageNumberPaginator

    def __init__(self, *, page_number: int, page_size: int) -> None:
        """Accept values already validated by the closed query parser."""
        super().__init__()
        self._page_number = page_number
        self._page_size = page_size

    def get_page_number(
        self,
        request: Request,
        paginator: Paginator,  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType] - Django's runtime class is not subscriptable.
    ) -> int:
        """Use the parser's integer without asking DRF to parse request text again."""
        del request, paginator
        return self._page_number

    def get_page_size(self, request: Request) -> int:
        """Use the parser's bounded size without a second DRF conversion."""
        del request
        return self._page_size

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
