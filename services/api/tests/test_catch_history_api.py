"""Acceptance tests for the authenticated V0 player catch-history endpoint."""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any, cast
from unittest.mock import call, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from conventions.models import (
    Convention,
    ConventionStatus,
    FursuitCatchSessionEndReason,
)
from tests.authentication_support import (
    create_test_user,
    fake_clerk_session_verification,
    force_authenticated_client,
)
from tests.catch_history_test_support import create_history_catch
from tests.catch_test_support import catch_model

PATH = "/api/catches/"
INVALID_QUERY = {
    "code": "invalid_query",
    "detail": "The catch-history query is invalid.",
}
CONVENTION_NOT_FOUND = {
    "code": "convention_not_found",
    "detail": "The convention was not found.",
}
INVALID_PAGE = {
    "code": "invalid_page",
    "detail": "The requested page does not exist.",
}
SERVER_ERROR = {
    "code": "server_error",
    "detail": "An unexpected error occurred.",
}


def _utc(second: int) -> datetime.datetime:
    return datetime.datetime(2026, 9, 10, 12, 0, second, tzinfo=datetime.UTC)


def _response_data(response: Any) -> dict[str, object]:
    data = response.json()
    assert isinstance(data, dict)
    return cast(dict[str, object], data)


def _result_ids(data: dict[str, object]) -> list[int]:
    results = data["results"]
    assert isinstance(results, list)
    rows = cast(list[object], results)
    return [cast(int, cast(dict[str, object], row)["id"]) for row in rows]


def _relative_url(uri: object) -> str:
    assert isinstance(uri, str)
    parsed = urlsplit(uri)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _assert_scoped_link(
    uri: object, *, convention_id: int, page: int, page_size: int
) -> None:
    assert isinstance(uri, str)
    parsed = urlsplit(uri)
    assert parsed.path == PATH
    assert parse_qs(parsed.query, keep_blank_values=True) == {
        "convention_id": [str(convention_id)],
        "page": [str(page)],
        "page_size": [str(page_size)],
    }


@pytest.mark.django_db
def test_catch_history_requires_repository_bearer_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: route authentication uses the repository Bearer boundary."""
    anonymous = Client().get(PATH)

    assert anonymous.status_code == 401
    assert anonymous["WWW-Authenticate"] == "Bearer"
    assert anonymous.json() == {
        "detail": "Authentication credentials were not provided."
    }

    player = create_test_user(clerk_user_id="history_bearer_player")
    history = create_history_catch(catcher_user=player, ordinal=1)
    verified = fake_clerk_session_verification(
        monkeypatch, subject=player.clerk_user_id
    )
    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        bearer = Client().get(PATH, HTTP_AUTHORIZATION="Bearer synthetic")

    assert bearer.status_code == 200
    assert len(verified) == 1
    assert _result_ids(_response_data(bearer)) == [history.catch.pk]


@pytest.mark.django_db
def test_catch_history_returns_only_the_authenticated_players_rows() -> None:
    """AC-02/03: another player's interleaved Catch must never enter the page."""
    player = create_test_user()
    other_player = create_test_user()
    first = create_history_catch(catcher_user=player, ordinal=10, caught_at=_utc(1))
    excluded = create_history_catch(
        catcher_user=other_player, ordinal=11, caught_at=_utc(3)
    )
    second = create_history_catch(catcher_user=player, ordinal=12, caught_at=_utc(2))

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 2
    assert _result_ids(data) == [second.catch.pk, first.catch.pk]
    assert excluded.catch.pk not in _result_ids(data)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "selector", ("user_id", "catcher_id", "player_id", "owner_id", "clerk_user_id")
)
def test_catch_history_rejects_client_selected_identity(selector: str) -> None:
    """AC-02/06: client-selected identity is closed input, never an auth branch."""
    response = force_authenticated_client(user=create_test_user()).get(
        PATH, {selector: "1"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_QUERY


@pytest.mark.django_db
@pytest.mark.parametrize("method", ("post", "put", "patch", "delete"))
def test_catch_history_is_read_only(method: str) -> None:
    """AC-01/14: history reads cannot create, change, or delete Catch rows."""
    player = create_test_user()
    create_history_catch(catcher_user=player, ordinal=20)
    before = catch_model().objects.count()

    response = getattr(force_authenticated_client(user=player), method)(PATH)

    assert response.status_code == 405
    assert catch_model().objects.count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("method", ("head", "options"))
def test_catch_history_rejects_non_get_implicit_http_methods(method: str) -> None:
    """Final review: APIView's automatic HEAD/OPTIONS handlers are not allowed."""
    player = create_test_user()
    create_history_catch(catcher_user=player, ordinal=21)
    before = catch_model().objects.count()

    response = getattr(force_authenticated_client(user=player), method)(PATH)

    assert response.status_code == 405
    assert catch_model().objects.count() == before


@pytest.mark.django_db
def test_catch_history_reports_all_time_matching_count() -> None:
    """AC-03: all-time count is the owner-scoped total, not page length."""
    player = create_test_user()
    first = create_history_catch(catcher_user=player, ordinal=30, caught_at=_utc(1))
    second = create_history_catch(catcher_user=player, ordinal=31, caught_at=_utc(2))

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 2
    assert _result_ids(data) == [second.catch.pk, first.catch.pk]


@pytest.mark.django_db
def test_catch_history_filters_the_owner_scoped_query_by_convention() -> None:
    """AC-04: Convention filtering narrows an already owner-scoped query."""
    player = create_test_user()
    other = create_test_user()
    requested = create_history_catch(catcher_user=player, ordinal=40, caught_at=_utc(1))
    other_convention = create_history_catch(
        catcher_user=player, ordinal=41, caught_at=_utc(3)
    )
    excluded = create_history_catch(
        catcher_user=other,
        ordinal=42,
        convention=requested.convention,
        caught_at=_utc(2),
    )

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(
            PATH, {"convention_id": requested.convention.pk}
        )

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 1
    assert _result_ids(data) == [requested.catch.pk]
    assert other_convention.catch.pk not in _result_ids(data)
    assert excluded.catch.pk not in _result_ids(data)


@pytest.mark.django_db
def test_catch_history_distinguishes_missing_from_existing_empty_convention() -> None:
    """AC-05: Convention existence is independent from the player's matches."""
    player = create_test_user()
    existing_empty = Convention.objects.create(
        name="Catch History Existing Empty Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )
    missing_id = existing_empty.pk + 1
    while Convention.objects.filter(pk=missing_id).exists():
        missing_id += 1
    client = force_authenticated_client(user=player)

    missing = client.get(PATH, {"convention_id": missing_id})
    empty = client.get(PATH, {"convention_id": existing_empty.pk})

    assert missing.status_code == 404
    assert missing["Content-Type"].startswith("application/json")
    assert missing.json() == CONVENTION_NOT_FOUND
    assert empty.status_code == 200
    assert _response_data(empty) == {
        "catch_count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    (
        "unknown=1",
        "convention_id=",
        "convention_id=abc",
        "convention_id=0",
        "convention_id=-1",
        "convention_id=%2B1",
        "convention_id=%201",
        "convention_id=1.0",
        "convention_id=1e2",
        "page=",
        "page=last",
        "page=0",
        "page=-1",
        "page_size=",
        "page_size=0",
        "page_size=101",
        "page=1&page=2",
        "page_size=20&page_size=10",
        "convention_id=1&convention_id=2",
    ),
)
def test_catch_history_rejects_every_noncanonical_query(query: str) -> None:
    """AC-06: malformed, repeated, and unknown query input has one safe reply."""
    response = force_authenticated_client(user=create_test_user()).get(
        f"{PATH}?{query}"
    )

    assert response.status_code == 400
    assert response.json() == INVALID_QUERY
    assert query not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    (
        "format=csv",
        "format=xml",
        "format=csv&unknown=1",
        "format=xml&page=0",
    ),
)
def test_catch_history_does_not_allow_format_to_bypass_closed_query_validation(
    query: str,
) -> None:
    """Final review: renderer-format input is still closed endpoint input."""
    response = force_authenticated_client(user=create_test_user()).get(
        f"{PATH}?{query}"
    )

    assert response.status_code == 400
    assert response.json() == INVALID_QUERY


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parameter", "encoded_value"),
    (
        ("convention_id", "%2B1"),
        ("convention_id", "%201"),
        ("convention_id", "%D9%A1"),
        ("page", "%2B1"),
        ("page", "%201"),
        ("page", "%D9%A1"),
        ("page_size", "%2B1"),
        ("page_size", "%201"),
        ("page_size", "%D9%A1"),
    ),
)
def test_catch_history_rejects_non_ascii_or_permissively_parsed_numeric_query(
    parameter: str, encoded_value: str
) -> None:
    """AC-06: numeric input accepts only positive ASCII decimal digits."""
    query = f"{parameter}={encoded_value}"
    response = force_authenticated_client(user=create_test_user()).get(
        f"{PATH}?{query}"
    )

    assert response.status_code == 400
    assert response.json() == INVALID_QUERY
    assert query not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("parameter", ("convention_id", "page", "page_size"))
def test_catch_history_accepts_arbitrarily_long_leading_zero_small_values(
    parameter: str,
) -> None:
    """Final review: positive decimal grammar preserves leading-zero semantics."""
    player = create_test_user()
    history = create_history_catch(catcher_user=player, ordinal=48)
    small_value = f"{'0' * 5000}1"
    query = {parameter: small_value}
    if parameter == "convention_id":
        query[parameter] = f"{'0' * 5000}{history.convention.pk}"

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH, query)

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 1
    assert _result_ids(data) == [history.catch.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parameter", "expected_status", "expected_body"),
    (
        ("convention_id", 404, CONVENTION_NOT_FOUND),
        ("page", 404, INVALID_PAGE),
        ("page_size", 400, INVALID_QUERY),
    ),
)
def test_catch_history_handles_arbitrarily_long_positive_decimal_values(
    parameter: str, expected_status: int, expected_body: dict[str, str]
) -> None:
    """Final review: huge positive values use their frozen public outcomes."""
    huge_value = "9" * 5000

    response = force_authenticated_client(user=create_test_user()).get(
        PATH, {parameter: huge_value}
    )

    assert response.status_code == expected_status
    assert response.json() == expected_body


@pytest.mark.django_db
def test_catch_history_orders_newest_first_with_descending_id_tie_breaker() -> None:
    """AC-07: ordering is server-owned and stable for matching timestamps."""
    player = create_test_user()
    oldest = create_history_catch(catcher_user=player, ordinal=50, caught_at=_utc(1))
    tie_first = create_history_catch(catcher_user=player, ordinal=51, caught_at=_utc(2))
    tie_second = create_history_catch(
        catcher_user=player, ordinal=52, caught_at=_utc(2)
    )
    newest = create_history_catch(catcher_user=player, ordinal=53, caught_at=_utc(3))

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    assert _result_ids(_response_data(response)) == [
        newest.catch.pk,
        tie_second.catch.pk,
        tie_first.catch.pk,
        oldest.catch.pk,
    ]


@pytest.mark.django_db
def test_catch_history_uses_default_twenty_item_pages_and_total_count() -> None:
    """AC-08: default pagination has stable, disjoint pages and total count."""
    player = create_test_user()
    catches = [
        create_history_catch(
            catcher_user=player, ordinal=100 + index, caught_at=_utc(index)
        )
        for index in range(21)
    ]
    expected = [history.catch.pk for history in reversed(catches)]
    client = force_authenticated_client(user=player)
    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        first = client.get(PATH)
        assert first.status_code == 200
        first_data = _response_data(first)
        second = client.get(_relative_url(first_data["next"]))

    assert second.status_code == 200
    second_data = _response_data(second)
    assert first_data["catch_count"] == second_data["catch_count"] == 21
    assert _result_ids(first_data) == expected[:20]
    assert _result_ids(second_data) == expected[20:]
    assert set(_result_ids(first_data)).isdisjoint(_result_ids(second_data))
    assert first_data["previous"] is None
    assert first_data["next"] is not None
    assert second_data["previous"] is not None
    assert second_data["next"] is None


@pytest.mark.django_db
def test_catch_history_accepts_explicit_page_size_through_one_hundred() -> None:
    """AC-08: the maximum allowed page size remains 100 rather than clamping."""
    player = create_test_user()
    for index in range(101):
        create_history_catch(
            catcher_user=player, ordinal=200 + index, caught_at=_utc(index % 60)
        )

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH, {"page_size": 100})

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 101
    assert len(_result_ids(data)) == 100
    assert data["previous"] is None
    assert data["next"] is not None


@pytest.mark.django_db
def test_catch_history_links_retain_convention_scope_and_page_size() -> None:
    """AC-08: pagination links retain only accepted scope and page-size metadata."""
    player = create_test_user()
    first_history = create_history_catch(catcher_user=player, ordinal=400)
    for index in range(1, 21):
        create_history_catch(
            catcher_user=player,
            ordinal=400 + index,
            convention=first_history.convention,
        )
    client = force_authenticated_client(user=player)
    query = {"convention_id": first_history.convention.pk, "page_size": 10}
    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        first = client.get(PATH, query)
        assert first.status_code == 200
        first_data = _response_data(first)
        second = client.get(_relative_url(first_data["next"]))

    assert second.status_code == 200
    second_data = _response_data(second)
    _assert_scoped_link(
        first_data["next"],
        convention_id=first_history.convention.pk,
        page=2,
        page_size=10,
    )
    _assert_scoped_link(
        second_data["previous"],
        convention_id=first_history.convention.pk,
        page=1,
        page_size=10,
    )
    _assert_scoped_link(
        second_data["next"],
        convention_id=first_history.convention.pk,
        page=3,
        page_size=10,
    )


@pytest.mark.django_db
def test_catch_history_returns_closed_invalid_page_for_out_of_range_page() -> None:
    """AC-08: later pages beyond a nonempty scope use the frozen 404 reply."""
    player = create_test_user()
    create_history_catch(catcher_user=player, ordinal=500)

    response = force_authenticated_client(user=player).get(PATH, {"page": 2})

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == INVALID_PAGE


@pytest.mark.django_db
def test_catch_history_accepts_the_first_page_of_an_empty_scope() -> None:
    """AC-05/08: page one is valid when an existing Convention has no matches."""
    player = create_test_user()
    empty = Convention.objects.create(
        name="Catch History Empty Page Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )

    response = force_authenticated_client(user=player).get(
        PATH, {"convention_id": empty.pk, "page": 1}
    )

    assert response.status_code == 200
    assert _response_data(response) == {
        "catch_count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


@pytest.mark.django_db
def test_catch_history_rejects_second_page_of_an_empty_scope() -> None:
    """Final review: only page one is valid when the filtered scope is empty."""
    player = create_test_user()
    empty = Convention.objects.create(
        name="Catch History Empty Second Page Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )

    response = force_authenticated_client(user=player).get(
        PATH, {"convention_id": empty.pk, "page": 2}
    )

    assert response.status_code == 404
    assert response.json() == INVALID_PAGE


@pytest.mark.django_db
def test_catch_history_rejects_client_selected_ordering() -> None:
    """Final review: ordering remains wholly server-owned."""
    response = force_authenticated_client(user=create_test_user()).get(
        PATH, {"ordering": "caught_at"}
    )

    assert response.status_code == 400
    assert response.json() == INVALID_QUERY


@pytest.mark.django_db
def test_catch_history_projects_only_the_approved_closed_fields() -> None:
    """AC-09/10: the response is an exact safe projection of durable Catch data."""
    player = create_test_user()
    history = create_history_catch(catcher_user=player, ordinal=600, caught_at=_utc(1))

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    data = _response_data(response)
    assert set(data) == {"catch_count", "next", "previous", "results"}
    assert data["catch_count"] == 1
    assert data["next"] is None
    assert data["previous"] is None
    results = cast(list[object], data["results"])
    assert len(results) == 1
    result = cast(dict[str, object], results[0])
    assert set(result) == {"id", "fursuit", "convention", "caught_at"}
    assert result["id"] == history.catch.pk
    fursuit = cast(dict[str, object], result["fursuit"])
    assert set(fursuit) == {"id", "name", "photo_url"}
    assert fursuit == {
        "id": history.fursuit.pk,
        "name": history.fursuit.name,
        "photo_url": "http://testserver/api/media/images/fake-read",
    }
    convention = cast(dict[str, object], result["convention"])
    assert set(convention) == {"id", "name"}
    assert convention == {"id": history.convention.pk, "name": history.convention.name}
    assert result["caught_at"] == "2026-09-10T12:00:01Z"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
        cast(str, result["caught_at"]),
    )
    serialized = json.dumps(data, sort_keys=True)
    for forbidden in (
        "catcher",
        "owner",
        "clerk",
        "activation",
        "session",
        "credential",
        "eligibility",
        "enrollment",
        "lifecycle",
        "progression",
        "rarity",
        "denominator",
    ):
        assert forbidden not in serialized


@pytest.mark.django_db
def test_catch_history_successful_numbers_are_json_integers_and_do_not_write() -> None:
    """Final review: read responses retain integer types and never mutate Catch rows."""
    player = create_test_user()
    history = create_history_catch(catcher_user=player, ordinal=605)
    before = list(
        catch_model()
        .objects.filter(pk=history.catch.pk)
        .values(
            "id",
            "catcher_user_id",
            "fursuit_id",
            "convention_id",
            "activation_id",
            "catch_session_id",
            "caught_at",
        )
    )

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    data = _response_data(response)
    result = cast(dict[str, object], cast(list[object], data["results"])[0])
    fursuit = cast(dict[str, object], result["fursuit"])
    convention = cast(dict[str, object], result["convention"])
    assert all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (
            data["catch_count"],
            result["id"],
            fursuit["id"],
            convention["id"],
        )
    )
    assert (
        list(
            catch_model()
            .objects.filter(pk=history.catch.pk)
            .values(
                "id",
                "catcher_user_id",
                "fursuit_id",
                "convention_id",
                "activation_id",
                "catch_session_id",
                "caught_at",
            )
        )
        == before
    )


@pytest.mark.django_db
def test_catch_history_reads_historical_rows_after_current_state_changes() -> None:
    """Final review: reading durable history ignores present gameplay eligibility."""
    player = create_test_user()
    history = create_history_catch(catcher_user=player, ordinal=606)
    history.convention.status = ConventionStatus.COMPLETED
    history.convention.save(update_fields=["status"])
    history.fursuit.is_enabled = False
    history.fursuit.save(update_fields=["is_enabled"])
    activation = history.catch.activation
    activation.is_active = False
    activation.deactivated_at = _utc(4)
    activation.save(update_fields=["is_active", "deactivated_at"])
    catch_session = history.catch.catch_session
    catch_session.ended_at = catch_session.started_at + datetime.timedelta(seconds=1)
    catch_session.end_reason = FursuitCatchSessionEndReason.OWNER
    catch_session.save(update_fields=["ended_at", "end_reason"])

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        response = force_authenticated_client(user=player).get(
            PATH, {"convention_id": history.convention.pk}
        )

    assert response.status_code == 200
    data = _response_data(response)
    assert data["catch_count"] == 1
    assert _result_ids(data) == [history.catch.pk]


@pytest.mark.django_db
def test_catch_history_generates_one_fresh_photo_url_per_result() -> None:
    """AC-11: each row signs its durable photo key once through the media boundary."""
    player = create_test_user()
    older = create_history_catch(catcher_user=player, ordinal=610, caught_at=_utc(1))
    newer = create_history_catch(catcher_user=player, ordinal=611, caught_at=_utc(2))
    returned_urls = iter(
        ("/api/media/images/fake-first", "/api/media/images/fake-second")
    )

    def fake_read_image_url(_photo_key: str) -> str:
        return next(returned_urls)

    with patch(
        "catches.serializers.media_service.read_image_url",
        side_effect=fake_read_image_url,
    ) as read_image_url:
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 200
    data = _response_data(response)
    assert _result_ids(data) == [newer.catch.pk, older.catch.pk]
    assert read_image_url.call_args_list == [
        call(newer.fursuit.photo_key),
        call(older.fursuit.photo_key),
    ]
    results = cast(list[dict[str, object]], data["results"])
    assert [
        cast(dict[str, object], row["fursuit"])["photo_url"] for row in results
    ] == [
        "http://testserver/api/media/images/fake-first",
        "http://testserver/api/media/images/fake-second",
    ]


@pytest.mark.django_db
def test_catch_history_sanitizes_photo_url_generation_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-11: media errors fail closed without a partial page or diagnostics."""
    player = create_test_user()
    history = create_history_catch(catcher_user=player, ordinal=620)
    signed_url = "https://media.example.test/read?signature=synthetic-signature"
    query_value = "convention_id=987&page=2"
    diagnostic = (
        f"photo_key={history.fursuit.photo_key}; url={signed_url}; "
        f"catch_id={history.catch.pk}; query={query_value}; synthetic secret-like error"
    )
    with (
        caplog.at_level(logging.ERROR, logger="catches.views"),
        patch(
            "catches.serializers.media_service.read_image_url",
            side_effect=RuntimeError(diagnostic),
        ),
    ):
        response = force_authenticated_client(user=player).get(PATH)

    assert response.status_code == 500
    assert response.json() == SERVER_ERROR
    assert set(response.json()) == {"code", "detail"}
    response_text = response.content.decode()
    for sensitive_value in (
        diagnostic,
        history.fursuit.photo_key,
        signed_url,
        "synthetic-signature",
        query_value,
    ):
        assert sensitive_value not in response_text
    records = [record for record in caplog.records if record.name == "catches.views"]
    assert len(records) == 1
    record = records[0]
    assert record.args == ()
    assert record.exc_info is None
    log_material = (caplog.text, repr(record.__dict__), record.getMessage())
    for sensitive_value in (
        diagnostic,
        history.fursuit.photo_key,
        signed_url,
        "synthetic-signature",
        query_value,
    ):
        assert all(sensitive_value not in material for material in log_material)


@pytest.mark.django_db
def test_catch_history_second_signing_failure_is_sanitized_and_retries_next_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Final review: a later-row signing error cannot leak a partial page or extras."""
    player = create_test_user()
    older = create_history_catch(catcher_user=player, ordinal=630, caught_at=_utc(1))
    newer = create_history_catch(catcher_user=player, ordinal=631, caught_at=_utc(2))
    signed_url = "https://media.example.test/read?signature=second-row-secret"
    diagnostic = (
        f"photo_key={older.fursuit.photo_key}; url={signed_url}; "
        f"user_id={player.pk}; catch_id={older.catch.pk}; "
        f"fursuit_id={older.fursuit.pk}; convention_id={older.convention.pk}"
    )
    with (
        caplog.at_level(logging.ERROR, logger="catches.views"),
        patch(
            "catches.serializers.media_service.read_image_url",
            side_effect=(
                "/api/media/images/first-request-first-row",
                RuntimeError(diagnostic),
                "/api/media/images/retry-first-row",
                "/api/media/images/retry-second-row",
            ),
        ) as read_image_url,
    ):
        client = force_authenticated_client(user=player)
        failed = client.get(PATH)
        retried = client.get(PATH)

    assert failed.status_code == 500
    assert failed.json() == SERVER_ERROR
    assert retried.status_code == 200
    assert _result_ids(_response_data(retried)) == [newer.catch.pk, older.catch.pk]
    assert read_image_url.call_args_list == [
        call(newer.fursuit.photo_key),
        call(older.fursuit.photo_key),
        call(newer.fursuit.photo_key),
        call(older.fursuit.photo_key),
    ]
    records = [record for record in caplog.records if record.name == "catches.views"]
    assert len(records) == 1
    record = records[0]
    assert record.args == ()
    assert record.exc_info is None
    assert {
        "user_id",
        "catch_id",
        "fursuit_id",
        "convention_id",
        "photo_key",
        "url",
        "query",
        "exception",
    }.isdisjoint(record.__dict__)
    log_material = (caplog.text, repr(record.__dict__), record.getMessage())
    for sensitive_value in (
        diagnostic,
        signed_url,
        "second-row-secret",
        older.fursuit.photo_key,
        str(player.pk),
        str(older.catch.pk),
        str(older.fursuit.pk),
        str(older.convention.pk),
    ):
        assert all(sensitive_value not in material for material in log_material)


@pytest.mark.django_db
def test_catch_history_database_queries_do_not_grow_with_page_occupancy() -> None:
    """AC-12: serialization eagerly loads fursuit and Convention for each page."""
    player = create_test_user()
    one = create_history_catch(catcher_user=player, ordinal=700)
    many = create_history_catch(catcher_user=player, ordinal=701)
    for index in range(1, 20):
        create_history_catch(
            catcher_user=player,
            ordinal=701 + index,
            convention=many.convention,
        )
    client = force_authenticated_client(user=player)
    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        with CaptureQueriesContext(connection) as one_queries:
            one_response = client.get(PATH, {"convention_id": one.convention.pk})
        with CaptureQueriesContext(connection) as many_queries:
            many_response = client.get(PATH, {"convention_id": many.convention.pk})

    assert one_response.status_code == 200
    assert many_response.status_code == 200
    assert len(_result_ids(_response_data(one_response))) == 1
    assert len(_result_ids(_response_data(many_response))) == 20
    assert len(one_queries) == len(many_queries)
    page_queries = [
        query["sql"].lower()
        for query in many_queries.captured_queries
        if 'from "catches_catch"' in query["sql"].lower()
        and "limit" in query["sql"].lower()
    ]
    assert any(
        'join "fursuits_fursuit"' in query and 'join "conventions_convention"' in query
        for query in page_queries
    )
    matching_count_queries = [
        query["sql"].lower()
        for query in many_queries.captured_queries
        if 'from "catches_catch"' in query["sql"].lower()
        and "count(" in query["sql"].lower()
    ]
    assert len(matching_count_queries) == 1
