"""Black-box and persistence acceptance tests for per-Convention activation."""

from __future__ import annotations

import datetime

import pytest
from django.db import IntegrityError, models, transaction
from django.test import Client, override_settings
from django.utils import timezone

from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from conventions.services import get_operational_fursuit_activation
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.fursuit_activation_test_support import (
    ActivationScenario,
    activation_detail_path,
    activation_list_path,
    assert_activation_data,
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record


def _utc(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _operational_activation(
    scenario: ActivationScenario,
) -> FursuitActivation | None:
    return get_operational_fursuit_activation(
        scenario.user,
        convention_id=scenario.convention.pk,
        fursuit_id=scenario.fursuit.pk,
    )


PROFILE_INELIGIBLE_SHAPES = (
    "missing",
    "incomplete",
    "disabled",
)


def _make_profile_ineligible(
    scenario: ActivationScenario,
    profile_shape: str,
) -> None:
    profile = scenario.profile
    if profile_shape == "missing":
        profile.delete()
        return
    updates: dict[str, dict[str, object]] = {
        "incomplete": {
            "onboarding_completed_at": None,
            "handle": None,
            "display_name": None,
        },
        "disabled": {"is_enabled": False},
    }
    PlayerProfile.objects.filter(pk=profile.pk).update(**updates[profile_shape])


@pytest.mark.django_db
def test_activation_identity_is_protected_unique_and_inactive_rows_remain_durable() -> (
    None
):
    scenario = create_activation_scenario()
    first = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=False
    )
    fields = {field.name: field for field in FursuitActivation._meta.fields}
    assert isinstance(fields["id"], models.BigAutoField)
    assert fields["id"].primary_key is True
    for field_name in ("fursuit", "convention", "is_active", "activated_at"):
        assert fields[field_name].null is False
    assert fields["fursuit"].remote_field.on_delete is models.PROTECT  # type: ignore[union-attr]
    assert fields["convention"].remote_field.on_delete is models.PROTECT  # type: ignore[union-attr]
    constraints = FursuitActivation._meta.constraints
    assert any(
        isinstance(constraint, models.UniqueConstraint)
        and tuple(constraint.fields) == ("fursuit", "convention")
        and constraint.name
        for constraint in constraints
    )
    assert any(
        isinstance(constraint, models.CheckConstraint)
        and constraint.name == "conventions_activation_state_timestamps_valid"
        for constraint in constraints
    )
    assert "enrollment" not in fields
    assert FursuitActivation._meta.ordering == ["fursuit_id", "id"]
    with pytest.raises(IntegrityError), transaction.atomic():
        FursuitActivation.objects.create(
            fursuit=scenario.fursuit,
            convention=scenario.convention,
            is_active=True,
            activated_at=timezone.now(),
        )
    other_convention = Convention.objects.create(
        name="Other activation convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 8, 1),
        end_date=datetime.date(2026, 8, 4),
    )
    other_fursuit = create_fursuit_record(owner=scenario.user, name="Other fursuit")
    invalid_timestamp_state = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        FursuitActivation.objects.create(
            fursuit=scenario.fursuit,
            convention=other_convention,
            is_active=True,
            activated_at=invalid_timestamp_state,
            deactivated_at=invalid_timestamp_state,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        FursuitActivation.objects.create(
            fursuit=other_fursuit,
            convention=scenario.convention,
            is_active=False,
            activated_at=invalid_timestamp_state,
            deactivated_at=None,
        )
    assert create_activation_row(
        fursuit=scenario.fursuit, convention=other_convention, active=True
    ).pk
    assert create_activation_row(
        fursuit=other_fursuit, convention=scenario.convention, active=True
    ).pk
    assert FursuitActivation.objects.get(pk=first.pk).is_active is False
    with pytest.raises(models.ProtectedError):
        scenario.fursuit.delete()
    with pytest.raises(models.ProtectedError):
        scenario.convention.delete()


@pytest.mark.django_db
@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_activation_routes_require_authentication_and_reject_unsupported_methods() -> (
    None
):
    assert Client().get(activation_list_path(1)).status_code == 401
    assert (
        Client().put(activation_detail_path(1, 1), {"is_active": True}).status_code
        == 401
    )
    scenario = create_activation_scenario()
    for method, path in (
        (scenario.client.post, activation_list_path(scenario.convention.pk)),
        (
            scenario.client.patch,
            activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
        ),
        (
            scenario.client.delete,
            activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
        ),
    ):
        assert method(path).status_code == 405


@pytest.mark.django_db
def test_list_is_owner_scoped_exact_ascending_and_never_synthesizes_relationships() -> (
    None
):
    scenario = create_activation_scenario()
    second = create_fursuit_record(owner=scenario.user, name="Second")
    unactivated = create_fursuit_record(owner=scenario.user, name="Unactivated")
    first_row = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=False
    )
    second_row = create_activation_row(
        fursuit=second, convention=scenario.convention, active=True
    )
    other = create_activation_scenario(clerk_user_id="other_activation_owner")
    create_activation_row(
        fursuit=other.fursuit, convention=scenario.convention, active=True
    )
    response = scenario.client.get(activation_list_path(scenario.convention.pk))
    assert response.status_code == 200
    data = [assert_activation_data(item) for item in response.json()]
    assert [item["fursuit_id"] for item in data] == sorted(
        [scenario.fursuit.pk, second.pk]
    )
    assert unactivated.pk not in [item["fursuit_id"] for item in data]
    by_fursuit = {item["fursuit_id"]: item for item in data}
    assert set(by_fursuit) == {first_row.fursuit_id, second_row.fursuit_id}
    for item in data:
        assert item["convention_id"] == scenario.convention.pk
        assert item["fursuit_id"] in {scenario.fursuit.pk, second.pk}
    assert by_fursuit[first_row.fursuit_id]["is_active"] is False
    assert by_fursuit[first_row.fursuit_id]["is_eligible"] is True
    assert scenario.client.get(activation_list_path(999999)).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("lost_requirement", ("enrollment", "convention", "fursuit"))
def test_list_projects_current_eligibility_without_rewriting_active_selection(
    lost_requirement: str,
) -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    if lost_requirement == "enrollment":
        assert scenario.enrollment is not None
        scenario.enrollment.delete()
    elif lost_requirement == "convention":
        Convention.objects.filter(pk=scenario.convention.pk).update(
            status=ConventionStatus.PAUSED
        )
    else:
        Fursuit.objects.filter(pk=scenario.fursuit.pk).update(is_enabled=False)
    response = scenario.client.get(activation_list_path(scenario.convention.pk))
    assert response.status_code == 200
    data = assert_activation_data(response.json()[0])
    assert data["is_active"] is True and data["is_eligible"] is False
    activation.refresh_from_db()
    assert activation.is_active is True and activation.deactivated_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("profile_shape", PROFILE_INELIGIBLE_SHAPES)
def test_list_computes_ineligible_for_every_profile_predicate_shape(
    profile_shape: str,
) -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    _make_profile_ineligible(scenario, profile_shape)
    response = scenario.client.get(activation_list_path(scenario.convention.pk))
    assert response.status_code == 200
    data = assert_activation_data(response.json()[0])
    assert data["fursuit_id"] == scenario.fursuit.pk
    assert data["convention_id"] == scenario.convention.pk
    assert data["is_active"] is True and data["is_eligible"] is False
    activation.refresh_from_db()
    assert activation.is_active is True and activation.deactivated_at is None


@pytest.mark.django_db
def test_put_is_closed_and_404_resource_precedence_precedes_body_validation() -> None:
    scenario = create_activation_scenario()
    stranger = create_activation_scenario(clerk_user_id="activation_stranger")
    active = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    inactive_fursuit = create_fursuit_record(
        owner=scenario.user, name="Inactive invalid-body fursuit"
    )
    inactive = create_activation_row(
        fursuit=inactive_fursuit, convention=scenario.convention, active=False
    )
    invalid_requests: tuple[tuple[dict[str, object] | bytes, str], ...] = (
        ({}, "application/json"),
        ({"is_active": True, "ignored": True}, "application/json"),
        ({"activated_at": "now"}, "application/json"),
        ({"is_active": "true"}, "application/json"),
        ({"is_active": 1}, "application/json"),
        ({"is_active": None}, "application/json"),
        (b"not json", "text/plain"),
    )
    for activation in (active, inactive):
        before = (
            activation.is_active,
            activation.activated_at,
            activation.deactivated_at,
            activation.updated_at,
        )
        path = activation_detail_path(scenario.convention.pk, activation.fursuit_id)
        for body, content_type in invalid_requests:
            response = scenario.client.put(path, body, content_type=content_type)
            assert response.status_code == 400
            activation.refresh_from_db()
            assert (
                activation.is_active,
                activation.activated_at,
                activation.deactivated_at,
                activation.updated_at,
            ) == before
    hidden = create_activation_row(
        fursuit=stranger.fursuit, convention=scenario.convention, active=True
    )
    hidden_before = (
        hidden.is_active,
        hidden.activated_at,
        hidden.deactivated_at,
        hidden.updated_at,
    )
    count_before = FursuitActivation.objects.count()
    cross_owner = scenario.client.put(
        activation_detail_path(scenario.convention.pk, stranger.fursuit.pk),
        {"is_active": True},
        content_type="application/json",
    )
    missing = scenario.client.put(
        activation_detail_path(scenario.convention.pk, 999999),
        {"is_active": True},
        content_type="application/json",
    )
    assert cross_owner.status_code == missing.status_code == 404
    assert cross_owner.json() == missing.json()
    combined_cross_owner = scenario.client.put(
        activation_detail_path(999999, stranger.fursuit.pk),
        b"not json",
        content_type="application/json",
    )
    combined_missing = scenario.client.put(
        activation_detail_path(999999, 999998),
        b"not json",
        content_type="application/json",
    )
    assert combined_cross_owner.status_code == combined_missing.status_code == 404
    assert combined_cross_owner.json() == combined_missing.json() == missing.json()
    assert FursuitActivation.objects.count() == count_before
    hidden.refresh_from_db()
    assert (
        hidden.is_active,
        hidden.activated_at,
        hidden.deactivated_at,
        hidden.updated_at,
    ) == hidden_before
    for secret in (
        str(stranger.user.pk),
        stranger.user.clerk_user_id,
        str(hidden.pk),
    ):
        assert secret.encode() not in cross_owner.content
    for fursuit_id in (stranger.fursuit.pk, 999999):
        assert (
            scenario.client.put(
                activation_detail_path(scenario.convention.pk, fursuit_id),
                b"not json",
                content_type="application/json",
            ).status_code
            == 404
        )
    assert (
        scenario.client.put(
            activation_detail_path(999999, scenario.fursuit.pk),
            b"not json",
            content_type="application/json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
@pytest.mark.parametrize("profile_state", PROFILE_INELIGIBLE_SHAPES)
def test_activation_requires_every_profile_eligibility_shape(
    profile_state: str,
) -> None:
    scenario = create_activation_scenario()
    _make_profile_ineligible(scenario, profile_state)
    response = scenario.client.put(
        activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
        {"is_active": True},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not FursuitActivation.objects.exists()


@pytest.mark.django_db
def test_activation_requires_enrollment_playable_convention_and_enabled_fursuit_but_not_active_selection() -> (
    None
):
    succeeds_without_selected_convention = create_activation_scenario(
        enrollment_is_active=False
    )
    response = succeeds_without_selected_convention.client.put(
        activation_detail_path(
            succeeds_without_selected_convention.convention.pk,
            succeeds_without_selected_convention.fursuit.pk,
        ),
        {"is_active": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    created = assert_activation_data(response.json())
    assert created["is_active"] is True
    assert (
        created["convention_id"] == succeeds_without_selected_convention.convention.pk
    )
    assert created["fursuit_id"] == succeeds_without_selected_convention.fursuit.pk
    scenarios = [
        create_activation_scenario(clerk_user_id="no_enrollment", enrolled=False),
        create_activation_scenario(
            clerk_user_id="disabled_fursuit", fursuit_enabled=False
        ),
    ]
    scenarios.extend(
        create_activation_scenario(
            clerk_user_id=f"status_{status}", convention_status=status
        )
        for status in ConventionStatus.values
        if status != ConventionStatus.ACTIVE.value
    )
    for scenario in scenarios:
        response = scenario.client.put(
            activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
            {"is_active": True},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert not FursuitActivation.objects.filter(
            fursuit=scenario.fursuit, convention=scenario.convention
        ).exists()


@pytest.mark.django_db
def test_transitions_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conventions import services

    scenario = create_activation_scenario()
    t1 = _utc("2026-08-31T12:00:00Z")
    t2 = _utc("2026-08-31T12:01:00Z")
    t3 = _utc("2026-08-31T12:02:00Z")
    current_time = t1
    monkeypatch.setattr(services.timezone, "now", lambda: current_time)
    path = activation_detail_path(scenario.convention.pk, scenario.fursuit.pk)
    created = scenario.client.put(
        path, {"is_active": True}, content_type="application/json"
    )
    assert created.status_code == 200
    assert (
        assert_activation_data(created.json())["activated_at"] == "2026-08-31T12:00:00Z"
    )
    assert assert_activation_data(created.json())["is_eligible"] is True
    activation = FursuitActivation.objects.get(
        fursuit=scenario.fursuit, convention=scenario.convention
    )
    assert (
        activation.is_active
        and activation.activated_at == t1
        and activation.deactivated_at is None
        and activation.updated_at == t1
    )
    active_timestamps = (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    )
    active_retry = scenario.client.put(
        path, {"is_active": True}, content_type="application/json"
    )
    assert active_retry.status_code == 200
    active_retry_data = assert_activation_data(active_retry.json())
    assert active_retry_data["fursuit_id"] == scenario.fursuit.pk
    assert active_retry_data["convention_id"] == scenario.convention.pk
    assert active_retry_data["is_active"] is True
    activation.refresh_from_db()
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == active_timestamps
    current_time = t2
    assert (
        scenario.client.put(
            path, {"is_active": False}, content_type="application/json"
        ).status_code
        == 200
    )
    activation.refresh_from_db()
    assert (
        not activation.is_active
        and activation.activated_at == t1
        and activation.deactivated_at == t2
        and activation.updated_at == t2
    )
    assert activation.updated_at > active_timestamps[2]
    inactive_timestamps = (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    )
    inactive_retry = scenario.client.put(
        path, {"is_active": False}, content_type="application/json"
    )
    assert inactive_retry.status_code == 200
    inactive_retry_data = assert_activation_data(inactive_retry.json())
    assert inactive_retry_data["fursuit_id"] == scenario.fursuit.pk
    assert inactive_retry_data["convention_id"] == scenario.convention.pk
    assert inactive_retry_data["is_active"] is False
    assert inactive_retry_data["is_eligible"] is True
    activation.refresh_from_db()
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == inactive_timestamps
    current_time = t3
    assert (
        scenario.client.put(
            path, {"is_active": True}, content_type="application/json"
        ).status_code
        == 200
    )
    activation.refresh_from_db()
    assert (
        activation.is_active
        and activation.activated_at == t3
        and activation.deactivated_at is None
        and activation.updated_at == t3
    )
    assert activation.updated_at > inactive_timestamps[2]
    missing = create_fursuit_record(owner=scenario.user, name="Never activated")
    assert (
        scenario.client.put(
            activation_detail_path(scenario.convention.pk, missing.pk),
            {"is_active": False},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert not FursuitActivation.objects.filter(
        fursuit=missing, convention=scenario.convention
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lost_requirement", ("profile", "fursuit", "enrollment", "convention")
)
def test_deactivation_permits_each_individual_lost_eligibility_requirement(
    lost_requirement: str,
) -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    if lost_requirement == "profile":
        PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=False)
    elif lost_requirement == "fursuit":
        Fursuit.objects.filter(pk=scenario.fursuit.pk).update(is_enabled=False)
    elif lost_requirement == "enrollment":
        assert scenario.enrollment is not None
        scenario.enrollment.delete()
    else:
        Convention.objects.filter(pk=scenario.convention.pk).update(
            status=ConventionStatus.PAUSED
        )
    response = scenario.client.put(
        activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
        {"is_active": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = assert_activation_data(response.json())
    assert data["fursuit_id"] == scenario.fursuit.pk
    assert data["convention_id"] == scenario.convention.pk
    assert data["is_active"] is False
    assert data["is_eligible"] is False
    activation.refresh_from_db()
    assert activation.is_active is False and activation.deactivated_at is not None


@pytest.mark.django_db
def test_operational_query_requires_owned_active_and_currently_eligible_without_writes() -> (
    None
):
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    timestamps = (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    )
    assert _operational_activation(scenario) == activation
    other = create_eligible_user(clerk_user_id="activation_query_other")
    assert (
        get_operational_fursuit_activation(
            other,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
        )
        is None
    )
    FursuitActivation.objects.filter(pk=activation.pk).update(
        is_active=False, deactivated_at=timezone.now()
    )
    assert _operational_activation(scenario) is None
    FursuitActivation.objects.filter(pk=activation.pk).update(
        is_active=True, deactivated_at=None
    )
    assert _operational_activation(scenario) == activation
    PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=False)
    assert _operational_activation(scenario) is None
    PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=True)
    assert _operational_activation(scenario) == activation
    assert scenario.enrollment is not None
    scenario.enrollment.delete()
    assert _operational_activation(scenario) is None
    ConventionEnrollment.objects.create(
        user=scenario.user, convention=scenario.convention
    )
    assert _operational_activation(scenario) == activation
    Convention.objects.filter(pk=scenario.convention.pk).update(
        status=ConventionStatus.PAUSED
    )
    assert _operational_activation(scenario) is None
    Convention.objects.filter(pk=scenario.convention.pk).update(
        status=ConventionStatus.ACTIVE
    )
    assert _operational_activation(scenario) == activation
    Fursuit.objects.filter(pk=scenario.fursuit.pk).update(is_enabled=False)
    assert _operational_activation(scenario) is None
    activation.refresh_from_db()
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == timestamps


@pytest.mark.django_db
@pytest.mark.parametrize("profile_shape", PROFILE_INELIGIBLE_SHAPES)
def test_operational_query_rejects_every_profile_predicate_shape_without_writes(
    profile_shape: str,
) -> None:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    timestamps = (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    )
    _make_profile_ineligible(scenario, profile_shape)
    assert (
        get_operational_fursuit_activation(
            scenario.user,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
        )
        is None
    )
    activation.refresh_from_db()
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == timestamps
