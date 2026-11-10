"""#451: exact database statement counts for the catch endpoints.

Each request authenticates through the real TailTag composition with only Clerk
verification faked, so the user lookup is part of every count. Savepoint
statements are not counted, because the test transaction turns every atomic
block into a savepoint that production does not send.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from tests.authentication_support import (
    create_test_user,
    fake_clerk_session_verification,
)
from tests.catch_credential_test_support import resolution_path
from tests.catch_history_test_support import create_history_catch
from tests.catch_test_support import create_catch_confirmation_scenario

_CONFIRM_PATH = "/api/catches/confirm/"
_HISTORY_PATH = "/api/catches/"
_DATA_VERBS = ("SELECT", "INSERT", "UPDATE", "DELETE")


def _client(monkeypatch: pytest.MonkeyPatch, user: User) -> Client:
    fake_clerk_session_verification(monkeypatch, subject=user.clerk_user_id)
    return Client(HTTP_AUTHORIZATION="Bearer synthetic")


def _data_statements(queries: CaptureQueriesContext) -> list[str]:
    return [
        query["sql"]
        for query in queries.captured_queries
        if query["sql"].lstrip().upper().startswith(_DATA_VERBS)
    ]


def _post(client: Client, path: str, payload: str) -> Any:
    return client.post(path, {"payload": payload}, content_type="application/json")


@pytest.mark.django_db
def test_resolve_runs_four_data_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = create_catch_confirmation_scenario()
    client = _client(monkeypatch, scenario.catcher_user)

    with CaptureQueriesContext(connection) as queries:
        response = _post(
            client, resolution_path(scenario.convention.pk), scenario.payload
        )

    assert response.status_code == 200
    statements = _data_statements(queries)
    assert len(statements) == 4, statements


@pytest.mark.django_db
def test_confirm_of_an_existing_catch_runs_four_data_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = create_catch_confirmation_scenario()
    client = _client(monkeypatch, scenario.catcher_user)
    assert _post(client, _CONFIRM_PATH, scenario.payload).status_code == 201

    with CaptureQueriesContext(connection) as queries:
        response = _post(client, _CONFIRM_PATH, scenario.payload)

    assert response.status_code == 200
    statements = _data_statements(queries)
    assert len(statements) == 4, statements


@pytest.mark.django_db
def test_confirm_of_a_new_catch_runs_fourteen_data_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = create_catch_confirmation_scenario()
    client = _client(monkeypatch, scenario.catcher_user)

    with CaptureQueriesContext(connection) as queries:
        response = _post(client, _CONFIRM_PATH, scenario.payload)

    assert response.status_code == 201
    statements = _data_statements(queries)
    assert len(statements) == 14, statements


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filtered", "expected"),
    ((True, 4), (False, 3)),
    ids=("with_convention_id", "without_convention_id"),
)
def test_catch_history_data_statements(
    monkeypatch: pytest.MonkeyPatch, *, filtered: bool, expected: int
) -> None:
    player = create_test_user()
    caught = create_history_catch(catcher_user=player, ordinal=4510)
    client = _client(monkeypatch, player)
    query = {"convention_id": caught.convention.pk} if filtered else {}

    with CaptureQueriesContext(connection) as queries:
        response = client.get(_HISTORY_PATH, query)

    assert response.status_code == 200
    statements = _data_statements(queries)
    assert len(statements) == expected, statements
