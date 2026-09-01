"""Repository-owned upstream lifecycle acceptance tests for #118."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions.models import ConventionEnrollment, ConventionStatus
from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    create_catch_session,
)


def _live_session() -> tuple[object, object, object]:
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    return scenario, activation, create_catch_session(activation=activation)


def _assert_eligibility_lost(session: object) -> None:
    session.refresh_from_db()  # type: ignore[attr-defined]
    assert session.ended_at is not None and session.end_reason == "eligibility_lost"  # type: ignore[attr-defined]


def _start_catch_session(scenario: object) -> object:
    return scenario.client.put(  # type: ignore[attr-defined]
        f"/api/conventions/{scenario.convention.pk}/fursuit-activations/{scenario.fursuit.pk}/catch-session/",  # type: ignore[attr-defined]
        {"is_active": True},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_profile_admin_disablement_ends_live_session_without_rewriting_activation_or_resurrecting_on_restore() -> (
    None
):
    """AC-09/14: rejects a profile-admin bypass or restoration of a terminal session."""
    scenario, activation, session = _live_session()
    operator = User.objects.create_superuser(
        "catch_profile_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    url = reverse("admin:profiles_playerprofile_change", args=(scenario.profile.pk,))
    assert client.post(url, {"is_enabled": ""}).status_code == 302
    _assert_eligibility_lost(session)
    activation.refresh_from_db()
    assert activation.is_active
    assert client.post(url, {"is_enabled": "on"}).status_code == 302
    session.refresh_from_db()
    assert session.ended_at is not None
    assert _start_catch_session(scenario).status_code == 200
    assert catch_session_model().objects.filter(activation=activation).count() == 2


@pytest.mark.django_db
def test_fursuit_admin_disablement_ends_live_session_and_reenable_requires_explicit_new_start() -> (
    None
):
    """AC-09/14: rejects a fursuit-admin direct update that leaves a live session."""
    scenario, activation, session = _live_session()
    operator = User.objects.create_superuser(
        "catch_fursuit_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    url = reverse("admin:fursuits_fursuit_change", args=(scenario.fursuit.pk,))
    assert client.post(url, {"is_enabled": ""}).status_code == 302
    _assert_eligibility_lost(session)
    assert client.post(url, {"is_enabled": "on"}).status_code == 302
    session.refresh_from_db()
    assert session.ended_at is not None
    assert catch_session_model().objects.filter(activation=activation).count() == 1
    assert _start_catch_session(scenario).status_code == 200
    assert catch_session_model().objects.filter(activation=activation).count() == 2


@pytest.mark.django_db
def test_enrollment_admin_removal_ends_live_session_but_active_selection_changes_do_not() -> (
    None
):
    """AC-09/14/17: rejects confusing selected-convention state with enrollment existence."""
    scenario, activation, session = _live_session()
    assert scenario.enrollment is not None
    scenario.enrollment.is_active = True
    scenario.enrollment.save(update_fields=["is_active", "updated_at"])
    session.refresh_from_db()
    assert session.ended_at is None
    operator = User.objects.create_superuser(
        "catch_enrollment_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    url = reverse(
        "admin:conventions_conventionenrollment_delete", args=(scenario.enrollment.pk,)
    )
    assert client.post(url, {"post": "yes"}).status_code == 302
    _assert_eligibility_lost(session)
    activation.refresh_from_db()
    assert activation.is_active
    ConventionEnrollment.objects.create(
        user=scenario.user, convention=scenario.convention
    )
    assert _start_catch_session(scenario).status_code == 200
    assert catch_session_model().objects.filter(activation=activation).count() == 2


@pytest.mark.django_db
def test_owner_and_operator_activation_deactivation_use_eligibility_lost_and_inactive_noop_preserves_history() -> (
    None
):
    """AC-10/14: rejects owner/operator reasons or rewrites on an inactive retry."""
    scenario, activation, session = _live_session()
    response = scenario.client.put(
        f"/api/conventions/{scenario.convention.pk}/fursuit-activations/{scenario.fursuit.pk}/",
        {"is_active": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    _assert_eligibility_lost(session)
    before = (session.ended_at, session.end_reason, session.updated_at)
    assert (
        scenario.client.put(
            f"/api/conventions/{scenario.convention.pk}/fursuit-activations/{scenario.fursuit.pk}/",
            {"is_active": False},
            content_type="application/json",
        ).status_code
        == 200
    )
    session.refresh_from_db()
    assert (session.ended_at, session.end_reason, session.updated_at) == before
    assert (
        scenario.client.put(
            f"/api/conventions/{scenario.convention.pk}/fursuit-activations/{scenario.fursuit.pk}/",
            {"is_active": True},
            content_type="application/json",
        ).status_code
        == 200
    )
    assert _start_catch_session(scenario).status_code == 200
    assert catch_session_model().objects.filter(activation=activation).count() == 2
    # Registered admin is a separate required product entry point.
    _other, _, other_session = _live_session()
    operator = User.objects.create_superuser(
        "catch_activation_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    assert (
        client.post(
            reverse(
                "admin:conventions_fursuitactivation_change",
                args=(other_session.activation_id,),
            ),
            {"is_active": ""},
        ).status_code
        == 302
    )
    _assert_eligibility_lost(other_session)


@pytest.mark.django_db
def test_convention_admin_non_playable_transition_ends_live_session_and_restore_does_not_resurrect() -> (
    None
):
    """AC-09/14: rejects ConventionAdmin bypass and resurrection on ACTIVE restore."""
    scenario, activation, session = _live_session()
    operator = User.objects.create_superuser(
        "catch_convention_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    url = reverse("admin:conventions_convention_change", args=(scenario.convention.pk,))
    assert (
        client.post(
            url,
            {
                "name": scenario.convention.name,
                "status": ConventionStatus.PAUSED,
                "start_date": scenario.convention.start_date,
                "end_date": scenario.convention.end_date,
            },
        ).status_code
        == 302
    )
    _assert_eligibility_lost(session)
    assert (
        client.post(
            url,
            {
                "name": scenario.convention.name,
                "status": ConventionStatus.ACTIVE,
                "start_date": scenario.convention.start_date,
                "end_date": scenario.convention.end_date,
            },
        ).status_code
        == 302
    )
    session.refresh_from_db()
    assert session.ended_at is not None and activation.is_active
    assert _start_catch_session(scenario).status_code == 200
    assert catch_session_model().objects.filter(activation=activation).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mutation", ("profile", "fursuit", "enrollment", "activation", "convention")
)
def test_every_eligibility_loss_path_gives_expired_row_expiration_precedence(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-04/09/10: rejects relabeling an already expired row eligibility_lost."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    now = timezone.now()
    from conventions import services

    monkeypatch.setattr(services.timezone, "now", lambda: now)
    expired_at = now
    stale = create_catch_session(
        activation=activation,
        started_at=expired_at - CATCH_SESSION_LIFETIME,
        expires_at=expired_at,
        ended_at=None,
    )
    if mutation == "activation":
        response = scenario.client.put(
            f"/api/conventions/{scenario.convention.pk}/fursuit-activations/{scenario.fursuit.pk}/",
            {"is_active": False},
            content_type="application/json",
        )
        assert response.status_code == 200
    else:
        operator = User.objects.create_superuser(
            f"catch_expired_{mutation}_operator", password="password"
        )
        client = Client()
        client.force_login(operator)
        if mutation == "profile":
            response = client.post(
                reverse(
                    "admin:profiles_playerprofile_change", args=(scenario.profile.pk,)
                ),
                {"is_enabled": ""},
            )
        elif mutation == "fursuit":
            response = client.post(
                reverse("admin:fursuits_fursuit_change", args=(scenario.fursuit.pk,)),
                {"is_enabled": ""},
            )
        elif mutation == "enrollment":
            assert scenario.enrollment is not None
            response = client.post(
                reverse(
                    "admin:conventions_conventionenrollment_delete",
                    args=(scenario.enrollment.pk,),
                ),
                {"post": "yes"},
            )
        else:
            response = client.post(
                reverse(
                    "admin:conventions_convention_change",
                    args=(scenario.convention.pk,),
                ),
                {
                    "name": scenario.convention.name,
                    "status": ConventionStatus.PAUSED,
                    "start_date": scenario.convention.start_date,
                    "end_date": scenario.convention.end_date,
                },
            )
        assert response.status_code == 302
    stale.refresh_from_db()
    assert stale.ended_at == expired_at and stale.end_reason == "expired"
