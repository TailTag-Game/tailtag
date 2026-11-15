"""Acceptance tests for the catch_session field of the activation list (#509)."""

from __future__ import annotations

import datetime
from typing import cast

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from conventions.models import Convention, ConventionStatus, FursuitActivation
from fursuits.models import Fursuit
from tests.fursuit_activation_test_support import (
    ActivationScenario,
    activation_list_path,
    assert_activation_data,
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    assert_catch_session_data,
    create_catch_session,
    unended_sessions_for,
)
from tests.fursuit_test_support import create_fursuit_record


def _z(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


def _list_by_fursuit(scenario: ActivationScenario) -> dict[int, dict[str, object]]:
    response = scenario.client.get(activation_list_path(scenario.convention.pk))
    assert response.status_code == 200
    items = [assert_activation_data(item, list_item=True) for item in response.json()]
    return {cast(int, item["fursuit_id"]): item for item in items}


def _session(
    item: dict[str, object], activation: FursuitActivation
) -> dict[str, object]:
    return assert_catch_session_data(
        item["catch_session"],
        fursuit_id=activation.fursuit_id,
        convention_id=activation.convention_id,
    )


@pytest.mark.django_db
def test_catch_session_is_null_without_a_session_and_the_latest_session_otherwise() -> (
    None
):
    scenario = create_activation_scenario()
    live_activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    never_started = create_activation_row(
        fursuit=create_fursuit_record(owner=scenario.user, name="Never started"),
        convention=scenario.convention,
        active=True,
    )
    now = timezone.now()
    create_catch_session(
        activation=live_activation,
        started_at=now - datetime.timedelta(hours=5),
        ended_at=now - datetime.timedelta(hours=4),
        end_reason="owner",
    )
    live = create_catch_session(
        activation=live_activation, started_at=now - datetime.timedelta(hours=1)
    )

    by_fursuit = _list_by_fursuit(scenario)

    assert by_fursuit[never_started.fursuit_id]["catch_session"] is None
    assert _session(by_fursuit[live_activation.fursuit_id], live_activation) == {
        "fursuit_id": live_activation.fursuit_id,
        "convention_id": live_activation.convention_id,
        "is_active": True,
        "started_at": _z(live.started_at),
        "expires_at": _z(live.expires_at),
        "ended_at": None,
        "end_reason": None,
    }


@pytest.mark.django_db
def test_catch_session_reports_a_finalized_session_as_stored() -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    now = timezone.now()
    ended = create_catch_session(
        activation=activation,
        started_at=now - datetime.timedelta(hours=2),
        ended_at=now - datetime.timedelta(hours=1),
        end_reason="operator",
    )

    session = _session(_list_by_fursuit(scenario)[activation.fursuit_id], activation)

    assert session["is_active"] is False
    assert session["ended_at"] == _z(ended.ended_at)
    assert session["end_reason"] == "operator"


@pytest.mark.django_db
def test_catch_session_reports_an_unfinalized_expired_session_without_a_write() -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    started = timezone.now() - datetime.timedelta(hours=13)
    expired = create_catch_session(activation=activation, started_at=started)

    session = _session(_list_by_fursuit(scenario)[activation.fursuit_id], activation)

    assert session["is_active"] is False
    assert session["ended_at"] == _z(expired.expires_at)
    assert session["end_reason"] == "expired"
    assert unended_sessions_for(activation).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("lost_requirement", ("convention", "fursuit", "selection"))
def test_catch_session_is_not_active_when_the_activation_is_not_operational(
    lost_requirement: str,
) -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    create_catch_session(activation=activation)
    if lost_requirement == "convention":
        Convention.objects.filter(pk=scenario.convention.pk).update(
            status=ConventionStatus.PAUSED
        )
    elif lost_requirement == "fursuit":
        Fursuit.objects.filter(pk=scenario.fursuit.pk).update(is_enabled=False)
    else:
        FursuitActivation.objects.filter(pk=activation.pk).update(
            is_active=False, deactivated_at=timezone.now()
        )

    session = _session(_list_by_fursuit(scenario)[activation.fursuit_id], activation)

    assert session["is_active"] is False
    assert session["ended_at"] is None and session["end_reason"] is None
    assert unended_sessions_for(activation).count() == 1


def _list_queries(scenario: ActivationScenario) -> int:
    with CaptureQueriesContext(connection) as queries:
        response = scenario.client.get(activation_list_path(scenario.convention.pk))
    assert response.status_code == 200
    return len(queries)


@pytest.mark.django_db
def test_list_query_count_does_not_grow_with_activations() -> None:
    scenario = create_activation_scenario()
    first = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    create_catch_session(activation=first)
    one = _list_queries(scenario)

    for name in ("Second", "Third", "Fourth"):
        activation = create_activation_row(
            fursuit=create_fursuit_record(owner=scenario.user, name=name),
            convention=scenario.convention,
            active=True,
        )
        create_catch_session(activation=activation)

    assert _list_queries(scenario) == one
