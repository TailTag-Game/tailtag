"""Owner-route acceptance contract for #118 catch sessions."""

from __future__ import annotations

import datetime
import re
from typing import Any

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from conventions.models import Convention, ConventionStatus
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.fursuit_activation_test_support import (
    ActivationScenario,
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    assert_catch_session_data,
    assert_empty_catch_session_data,
    catch_session_model,
    catch_session_path,
    create_catch_session,
)


def _put(scenario: ActivationScenario, active: bool) -> Any:
    return scenario.client.put(
        catch_session_path(scenario.convention.pk, scenario.fursuit.pk),
        {"is_active": active},
        content_type="application/json",
    )


def _assert_rfc3339_utc_timestamp(value: object) -> None:
    assert isinstance(value, str)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value)


@pytest.mark.django_db
def test_put_starts_and_stops_with_closed_seven_field_projection() -> None:
    """AC-05/07: rejects missing route, open projection, or non-owner terminal reason."""
    scenario = create_activation_scenario()
    create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    started = _put(scenario, True)
    assert started.status_code == 200
    data = assert_catch_session_data(
        started.json(),
        fursuit_id=scenario.fursuit.pk,
        convention_id=scenario.convention.pk,
    )
    assert (
        data["is_active"] is True
        and data["ended_at"] is None
        and data["end_reason"] is None
    )
    _assert_rfc3339_utc_timestamp(data["started_at"])
    _assert_rfc3339_utc_timestamp(data["expires_at"])
    stopped = _put(scenario, False)
    assert stopped.status_code == 200
    stopped_data = assert_catch_session_data(
        stopped.json(),
        fursuit_id=scenario.fursuit.pk,
        convention_id=scenario.convention.pk,
    )
    assert stopped_data["is_active"] is False and stopped_data["end_reason"] == "owner"
    _assert_rfc3339_utc_timestamp(stopped_data["started_at"])
    _assert_rfc3339_utc_timestamp(stopped_data["expires_at"])
    _assert_rfc3339_utc_timestamp(stopped_data["ended_at"])


@pytest.mark.django_db
def test_start_and_stop_retries_preserve_history_and_timestamps_and_first_stop_is_exact_empty_state() -> (
    None
):
    """AC-06/07: rejects expiry extension, retry writes, inactive-row synthesis, or 404 stop."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    empty = _put(scenario, False)
    assert empty.status_code == 200
    assert_empty_catch_session_data(
        empty.json(),
        fursuit_id=scenario.fursuit.pk,
        convention_id=scenario.convention.pk,
    )
    assert catch_session_model().objects.filter(activation=activation).count() == 0
    assert _put(scenario, True).status_code == 200
    session = catch_session_model().objects.get(activation=activation)
    snapshot = (
        session.started_at,
        session.expires_at,
        session.ended_at,
        session.end_reason,
        session.updated_at,
    )
    retry = _put(scenario, True)
    assert retry.status_code == 200
    session.refresh_from_db()
    assert (
        session.started_at,
        session.expires_at,
        session.ended_at,
        session.end_reason,
        session.updated_at,
    ) == snapshot
    assert catch_session_model().objects.filter(activation=activation).count() == 1
    first_stop = _put(scenario, False)
    assert first_stop.status_code == 200
    first_stop_data = assert_catch_session_data(
        first_stop.json(),
        fursuit_id=scenario.fursuit.pk,
        convention_id=scenario.convention.pk,
    )
    assert (
        first_stop_data["ended_at"] is not None
        and first_stop_data["end_reason"] == "owner"
    )
    session.refresh_from_db()
    terminal = (session.ended_at, session.end_reason, session.updated_at)
    repeated_stop = _put(scenario, False)
    assert repeated_stop.status_code == 200
    repeated_stop_data = assert_catch_session_data(
        repeated_stop.json(),
        fursuit_id=scenario.fursuit.pk,
        convention_id=scenario.convention.pk,
    )
    assert repeated_stop_data == first_stop_data
    session.refresh_from_db()
    assert (session.ended_at, session.end_reason, session.updated_at) == terminal


@pytest.mark.django_db
def test_expired_restart_finalizes_at_exact_expiry_then_creates_one_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-03/04/06: rejects now==expiry activity or ending expiry at observation time."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    expiry = timezone.now()
    from conventions import services

    monkeypatch.setattr(services.timezone, "now", lambda: expiry)
    old = create_catch_session(
        activation=activation,
        started_at=expiry - CATCH_SESSION_LIFETIME,
        expires_at=expiry,
    )
    response = _put(scenario, True)
    assert response.status_code == 200
    old.refresh_from_db()
    assert old.ended_at == expiry and old.end_reason == "expired"
    assert catch_session_model().objects.filter(activation=activation).count() == 2
    assert (
        catch_session_model()
        .objects.filter(activation=activation, ended_at__isnull=True)
        .count()
        == 1
    )


@pytest.mark.django_db
def test_effective_catchability_is_inactive_at_expiry_without_finalizing_or_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-03/16: rejects `now == expires_at` activity or read-side cleanup writes."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    now = timezone.now()
    session = create_catch_session(
        activation=activation,
        started_at=now - CATCH_SESSION_LIFETIME,
        expires_at=now,
    )
    from conventions import catch_sessions

    monkeypatch.setattr(catch_sessions.timezone, "now", lambda: now)

    before = (session.ended_at, session.end_reason, session.updated_at)
    assert (
        catch_sessions.get_effective_fursuit_catch_session(
            scenario.user,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
        )
        is None
    )
    assert (
        catch_sessions.get_effective_fursuit_catch_session(
            scenario.user,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
        )
        is None
    )
    session.refresh_from_db()
    assert (session.ended_at, session.end_reason, session.updated_at) == before


@pytest.mark.django_db
@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_owner_route_authentication_concealment_resource_precedence_and_closed_body_contract() -> (
    None
):
    """AC-05/08: rejects body-first parsing, cross-owner disclosure, and permissive JSON."""
    scenario = create_activation_scenario()
    create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    other = create_activation_scenario(clerk_user_id="catch_session_other")
    create_activation_row(
        fursuit=other.fursuit, convention=scenario.convention, active=True
    )
    path = catch_session_path(scenario.convention.pk, scenario.fursuit.pk)
    assert (
        Client()
        .put(path, {"is_active": True}, content_type="application/json")
        .status_code
        == 401
    )
    for method in (
        scenario.client.get,
        scenario.client.post,
        scenario.client.patch,
        scenario.client.delete,
    ):
        assert method(path).status_code == 405
    invalid_bodies: tuple[tuple[Any, str], ...] = (
        ({}, "application/json"),
        ({"is_active": True, "extra": 1}, "application/json"),
        ({"is_active": None}, "application/json"),
        ({"is_active": 1}, "application/json"),
        ([], "application/json"),
        ("not-an-object", "application/json"),
        (b'{"is_active": true}', "text/plain"),
    )
    for body, content_type in invalid_bodies:
        assert (
            scenario.client.put(path, body, content_type=content_type).status_code
            == 400
        )
    assert (
        scenario.client.put(
            catch_session_path(scenario.convention.pk, other.fursuit.pk),
            b"bad",
            content_type="text/plain",
        ).status_code
        == 404
    )
    assert (
        scenario.client.put(
            catch_session_path(999999, scenario.fursuit.pk),
            b"bad",
            content_type="text/plain",
        ).status_code
        == 404
    )
    missing = Fursuit.objects.create(
        owner=scenario.user,
        name="No activation",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
    )
    assert (
        scenario.client.put(
            catch_session_path(scenario.convention.pk, missing.pk),
            b"bad",
            content_type="text/plain",
        ).status_code
        == 404
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure, expected",
    (
        ("profile", 403),
        ("enrollment", 400),
        ("convention", 400),
        ("fursuit", 400),
        ("activation", 400),
    ),
)
def test_start_rejects_each_operational_failure_but_stop_converges_after_loss(
    failure: str, expected: int
) -> None:
    """AC-08: rejects omitted profile/enrollment/convention/fursuit/activation validation."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    create_catch_session(activation=activation)
    if failure == "profile":
        PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=False)
    elif failure == "enrollment":
        scenario.enrollment.delete()  # type: ignore[union-attr]
    elif failure == "convention":
        Convention.objects.filter(pk=scenario.convention.pk).update(
            status=ConventionStatus.PAUSED
        )
    elif failure == "fursuit":
        Fursuit.objects.filter(pk=scenario.fursuit.pk).update(is_enabled=False)
    else:
        activation.is_active = False
        activation.deactivated_at = datetime.datetime.now(datetime.UTC)
        activation.save(update_fields=["is_active", "deactivated_at", "updated_at"])
    assert _put(scenario, True).status_code == expected
    assert _put(scenario, False).status_code == 200
