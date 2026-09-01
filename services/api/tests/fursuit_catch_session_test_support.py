"""Literal fixtures and projections for catch-session acceptance tests."""

from __future__ import annotations

import datetime
from typing import Any, cast

from django.apps import apps
from django.utils import timezone

from conventions.models import FursuitActivation

EXPECTED_CATCH_SESSION_KEYS = {
    "fursuit_id",
    "convention_id",
    "is_active",
    "started_at",
    "expires_at",
    "ended_at",
    "end_reason",
}
EMPTY_CATCH_SESSION = {
    "is_active": False,
    "started_at": None,
    "expires_at": None,
    "ended_at": None,
    "end_reason": None,
}
CATCH_SESSION_LIFETIME = datetime.timedelta(hours=12)


def catch_session_path(convention_id: int, fursuit_id: int) -> str:
    return (
        f"/api/conventions/{convention_id}/fursuit-activations/"
        f"{fursuit_id}/catch-session/"
    )


def catch_session_model() -> type[Any]:
    """Look up the future model at runtime so RED is an observable missing feature."""
    return apps.get_model("conventions", "FursuitCatchSession")


def create_catch_session(
    *,
    activation: FursuitActivation,
    started_at: datetime.datetime | None = None,
    expires_at: datetime.datetime | None = None,
    ended_at: datetime.datetime | None = None,
    end_reason: str | None = None,
) -> Any:
    """Create an invariant-valid historical row; invalid probes override explicitly."""
    start = started_at or timezone.now()
    return catch_session_model().objects.create(
        activation=activation,
        started_at=start,
        expires_at=expires_at or start + CATCH_SESSION_LIFETIME,
        ended_at=ended_at,
        end_reason=end_reason,
    )


def assert_catch_session_data(
    data: object, *, fursuit_id: int, convention_id: int
) -> dict[str, object]:
    """Assert the closed public representation with hand-written expected keys."""
    assert isinstance(data, dict)
    result = cast(dict[str, object], data)
    assert set(result) == EXPECTED_CATCH_SESSION_KEYS
    assert result["fursuit_id"] == fursuit_id
    assert result["convention_id"] == convention_id
    assert isinstance(result["is_active"], bool)
    for name in ("started_at", "expires_at", "ended_at", "end_reason"):
        assert result[name] is None or isinstance(result[name], str)
    return result


def assert_empty_catch_session_data(
    data: object, *, fursuit_id: int, convention_id: int
) -> None:
    """Assert the exact non-persistent empty desired-state projection."""
    result = assert_catch_session_data(
        data, fursuit_id=fursuit_id, convention_id=convention_id
    )
    assert {key: result[key] for key in EMPTY_CATCH_SESSION} == EMPTY_CATCH_SESSION


def unended_sessions_for(activation: FursuitActivation) -> Any:
    return catch_session_model().objects.filter(
        activation=activation, ended_at__isnull=True
    )
