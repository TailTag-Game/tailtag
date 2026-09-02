"""PostgreSQL persistence acceptance contract for catch sessions."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    catch_session_path,
    create_catch_session,
)


@pytest.mark.django_db
def test_catch_session_has_protected_activation_append_only_shape_and_newest_history_order() -> (
    None
):
    """AC-01/02: rejects CASCADE activation history or mutable non-historical ordering."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session_model = catch_session_model()
    fields = {field.name: field for field in session_model._meta.fields}
    assert isinstance(fields["id"], models.BigAutoField) and fields["id"].primary_key
    assert fields["activation"].null is False
    assert fields["activation"].remote_field.on_delete is models.PROTECT
    assert fields["activation"].remote_field.related_name == "catch_sessions"
    for name in ("started_at", "expires_at", "created_at", "updated_at"):
        assert fields[name].null is False
    assert fields["ended_at"].null is True and fields["end_reason"].null is True
    now = timezone.now()
    first = create_catch_session(
        activation=activation,
        started_at=now - CATCH_SESSION_LIFETIME,
        ended_at=now - datetime.timedelta(hours=11),
        end_reason="owner",
    )
    second = create_catch_session(activation=activation, started_at=now)
    assert list(session_model.objects.filter(activation=activation)) == [second, first]
    with pytest.raises(models.ProtectedError):
        activation.delete()


@pytest.mark.django_db
def test_catch_session_database_constraints_reject_invalid_lifecycle_states_and_second_unended_row() -> (
    None
):
    """AC-02: rejects omitted/weak check constraints and missing conditional uniqueness."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session_model = catch_session_model()
    named = {constraint.name for constraint in session_model._meta.constraints}
    assert named == {
        "conventions_catch_session_expiry_after_start",
        "conventions_catch_session_end_fields_paired",
        "conventions_catch_session_end_not_before_start",
        "conventions_catch_session_end_reason_valid",
        "conventions_catch_session_one_unended_per_activation",
    }
    start = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
    invalid_rows: tuple[dict[str, Any], ...] = (
        {"expires_at": start},
        {"ended_at": start},
        {"end_reason": "owner"},
        {"ended_at": start - datetime.timedelta(microseconds=1), "end_reason": "owner"},
        {"ended_at": start, "end_reason": "not-a-reason"},
    )
    for overrides in invalid_rows:
        with pytest.raises(IntegrityError), transaction.atomic():
            create_catch_session(activation=activation, started_at=start, **overrides)
    create_catch_session(activation=activation, started_at=start)
    with pytest.raises(IntegrityError), transaction.atomic():
        create_catch_session(
            activation=activation, started_at=start + datetime.timedelta(minutes=1)
        )


@pytest.mark.django_db
def test_catch_session_exact_twelve_hour_lifetime_is_server_controlled_for_a_real_start() -> (
    None
):
    """AC-04: rejects a lifetime other than exactly twelve hours."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    response = scenario.client.put(
        catch_session_path(scenario.convention.pk, scenario.fursuit.pk),
        {"is_active": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    session = catch_session_model().objects.get(activation=activation)
    assert session.expires_at - session.started_at == CATCH_SESSION_LIFETIME
