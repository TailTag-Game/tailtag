"""Credential/session independence and eligibility-loss lifecycle tests."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions.models import ConventionEnrollment, ConventionStatus
from tests.catch_credential_test_support import (
    PAYLOAD_B,
    TOKEN_A,
    TOKEN_B,
    assert_owner_payload,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
    owner_credential_path,
)
from tests.fursuit_activation_test_support import (
    activation_detail_path,
    create_activation_row,
)
from tests.fursuit_catch_session_test_support import (
    catch_session_path,
    create_catch_session,
)


def _scenario_with_current() -> tuple[object, object, object]:
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session = create_catch_session(activation=activation)
    credential = create_credential(activation=activation, token=TOKEN_A)
    return scenario, session, credential


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mutation",
    (
        "activation",
        "operator_activation",
        "profile",
        "fursuit",
        "enrollment",
        "convention",
    ),
)
def test_every_repository_eligibility_loss_revokes_current_credential_and_preserves_session_precedence(
    mutation: str,
) -> None:
    """AC-08/14/18: rejects any upstream lifecycle bypass or wrong terminal reason."""
    scenario, session, credential = _scenario_with_current()
    operator = User.objects.create_superuser(
        f"credential_{mutation}_operator", password="password"
    )
    admin = Client()
    admin.force_login(operator)
    if mutation == "activation":
        response = scenario.client.put(
            activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
            {"is_active": False},
            content_type="application/json",
        )
    elif mutation == "operator_activation":
        from conventions.services import deactivate_fursuit_activation_as_operator

        deactivate_fursuit_activation_as_operator(
            activation_id=credential.activation_id
        )
        response = None
    elif mutation == "profile":
        response = admin.post(
            reverse("admin:profiles_playerprofile_change", args=(scenario.profile.pk,)),
            {"is_enabled": ""},
        )
    elif mutation == "fursuit":
        response = admin.post(
            reverse("admin:fursuits_fursuit_change", args=(scenario.fursuit.pk,)),
            {"is_enabled": ""},
        )
    elif mutation == "enrollment":
        assert scenario.enrollment is not None
        response = admin.post(
            reverse(
                "admin:conventions_conventionenrollment_delete",
                args=(scenario.enrollment.pk,),
            ),
            {"post": "yes"},
        )
    else:
        response = admin.post(
            reverse(
                "admin:conventions_convention_change", args=(scenario.convention.pk,)
            ),
            {
                "name": scenario.convention.name,
                "status": ConventionStatus.PAUSED,
                "start_date": scenario.convention.start_date,
                "end_date": scenario.convention.end_date,
            },
        )
    if response is not None:
        assert response.status_code in {200, 302}
    credential.refresh_from_db()
    session.refresh_from_db()
    assert (
        credential.revoked_at is not None
        and credential.revocation_reason == "eligibility_lost"
    )
    assert session.ended_at is not None and session.end_reason == "eligibility_lost"
    assert (
        catch_credential_model()
        .objects.filter(activation=credential.activation)
        .count()
        == 1
    )
    if mutation in {"activation", "operator_activation"}:
        assert (
            scenario.client.put(
                activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
                {"is_active": True},
                content_type="application/json",
            ).status_code
            == 200
        )
    elif mutation == "profile":
        assert (
            admin.post(
                reverse(
                    "admin:profiles_playerprofile_change", args=(scenario.profile.pk,)
                ),
                {"is_enabled": "on"},
            ).status_code
            == 302
        )
    elif mutation == "fursuit":
        assert (
            admin.post(
                reverse("admin:fursuits_fursuit_change", args=(scenario.fursuit.pk,)),
                {"is_enabled": "on"},
            ).status_code
            == 302
        )
    elif mutation == "enrollment":
        ConventionEnrollment.objects.create(
            user=scenario.user, convention=scenario.convention
        )
    else:
        assert (
            admin.post(
                reverse(
                    "admin:conventions_convention_change",
                    args=(scenario.convention.pk,),
                ),
                {
                    "name": scenario.convention.name,
                    "status": ConventionStatus.ACTIVE,
                    "start_date": scenario.convention.start_date,
                    "end_date": scenario.convention.end_date,
                },
            ).status_code
            == 302
        )
    from unittest.mock import patch

    with patch("secrets.token_urlsafe", return_value=TOKEN_B):
        response = scenario.client.get(
            owner_credential_path(scenario.convention.pk, scenario.fursuit.pk)
        )
    assert_owner_payload(response, PAYLOAD_B)
    current = catch_credential_model().objects.get(revoked_at__isnull=True)
    assert current.pk != credential.pk and current.token == TOKEN_B


@pytest.mark.django_db
def test_all_routine_session_transitions_do_not_mutate_credential_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07: rejects credential coupling to session start/stop/expiry/restart/operator end."""
    scenario, session, credential = _scenario_with_current()
    before = (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    )
    path = catch_session_path(scenario.convention.pk, scenario.fursuit.pk)
    # Explicit stop then restart are ordinary session transitions.
    assert (
        scenario.client.put(
            path, {"is_active": False}, content_type="application/json"
        ).status_code
        == 200
    )
    assert (
        scenario.client.put(
            path, {"is_active": True}, content_type="application/json"
        ).status_code
        == 200
    )
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == before
    assert (
        catch_credential_model()
        .objects.filter(activation=credential.activation)
        .count()
        == 1
    )
    # Expiration (including finalization by a later start) cannot rewrite credentials.
    session = credential.activation.catch_sessions.get(ended_at__isnull=True)
    now = timezone.now()
    session.expires_at = now
    session.save(update_fields=["expires_at", "updated_at"])
    from conventions import catch_sessions

    monkeypatch.setattr(catch_sessions.timezone, "now", lambda: now)
    assert (
        catch_sessions.get_effective_fursuit_catch_session(
            scenario.user,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
        )
        is None
    )
    assert (
        scenario.client.put(
            path, {"is_active": True}, content_type="application/json"
        ).status_code
        == 200
    )
    # Restricted operator session termination is likewise credential-independent.
    live = (
        catch_credential_model()
        .objects.get(revoked_at__isnull=True)
        .activation.catch_sessions.filter(ended_at__isnull=True)
        .get()
    )
    catch_sessions.terminate_session_as_operator(live.pk)
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == before
