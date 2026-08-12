"""Health endpoint behavior."""

from __future__ import annotations

from typing import NoReturn, Self

import pytest
from django.db import DatabaseError
from django.test import Client
from pytest import MonkeyPatch


def fail_if_called() -> NoReturn:
    """Fail when liveness attempts to reach the database."""
    message = "liveness must not access the database"
    raise AssertionError(message)


def test_liveness_does_not_access_database(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """Liveness is available without a database connection."""
    monkeypatch.setattr("django.db.connection.ensure_connection", fail_if_called)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_returns_success_when_postgresql_is_available(client: Client) -> None:
    """Readiness succeeds after Django connects to PostgreSQL."""
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_hides_database_failure(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """Readiness returns a generic unavailable response when its query fails."""

    class FailingCursor:
        """Minimal cursor context that fails only when executing the health query."""

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, _: str) -> NoReturn:
            raise DatabaseError("health query failed")

    monkeypatch.setattr("django.db.connection.cursor", FailingCursor)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
