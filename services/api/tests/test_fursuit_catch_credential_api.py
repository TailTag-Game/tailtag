"""Owner fetch and rotation acceptance contract for catch credentials."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from conventions.models import Convention
from fursuits.models import Fursuit
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.catch_credential_test_support import (
    OWNER_INELIGIBLE_DETAIL,
    PAYLOAD_A,
    PAYLOAD_B,
    TOKEN_A,
    TOKEN_B,
    assert_owner_payload,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
    owner_credential_path,
    rotation_path,
)
from tests.fursuit_activation_test_support import create_activation_row


@pytest.mark.django_db
def test_owner_fetch_is_lazy_idempotent_raw_token_only_and_does_not_start_a_session() -> (
    None
):
    """AC-04/05/07: rejects wrong generator size/envelope storage or fetch-side writes."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    path = owner_credential_path(scenario.convention.pk, scenario.fursuit.pk)
    with patch("secrets.token_urlsafe", return_value=TOKEN_A) as token_urlsafe:
        first = scenario.client.get(path)
    assert_owner_payload(first, PAYLOAD_A)
    token_urlsafe.assert_called_once_with(32)
    credential = catch_credential_model().objects.get(activation=activation)
    assert credential.token == TOKEN_A
    snapshot = (credential.created_at, credential.updated_at)
    assert_owner_payload(scenario.client.get(path), PAYLOAD_A)
    credential.refresh_from_db()
    assert (credential.created_at, credential.updated_at) == snapshot
    assert catch_credential_model().objects.filter(activation=activation).count() == 1
    assert not activation.catch_sessions.exists()


@pytest.mark.django_db
def test_rotation_revokes_current_once_or_creates_without_a_current_row_and_rejects_nonempty_body() -> (
    None
):
    """AC-06/07: rejects idempotent rotation, editable history, or body parsing ambiguity."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    old = create_credential(activation=activation, token=TOKEN_A)
    path = rotation_path(scenario.convention.pk, scenario.fursuit.pk)
    with patch("secrets.token_urlsafe", return_value=TOKEN_B) as token_urlsafe:
        response = scenario.client.post(path, b"", content_type="application/json")
    assert_owner_payload(response, PAYLOAD_B)
    token_urlsafe.assert_called_once_with(32)
    old.refresh_from_db()
    assert old.revoked_at is not None and old.revocation_reason == "owner_rotation"
    replacement = catch_credential_model().objects.get(revoked_at__isnull=True)
    assert replacement.token == TOKEN_B and replacement.created_at >= old.created_at
    assert (
        scenario.client.post(path, b"{}", content_type="application/json").status_code
        == 400
    )
    replacement.revoked_at = timezone.now()
    replacement.revocation_reason = "operator"
    replacement.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
    with patch("secrets.token_urlsafe", return_value=TOKEN_A):
        assert_owner_payload(scenario.client.post(path, b""), PAYLOAD_A)


@pytest.mark.django_db
@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
@pytest.mark.parametrize("route", ("fetch", "rotate"))
def test_owner_routes_enforce_auth_concealment_precedence_methods_and_operational_errors(
    route: str,
) -> None:
    """AC-06/09: rejects disclosure, body-before-resource handling, or split operational details."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    del activation
    path = (
        owner_credential_path(scenario.convention.pk, scenario.fursuit.pk)
        if route == "fetch"
        else rotation_path(scenario.convention.pk, scenario.fursuit.pk)
    )
    method = "get" if route == "fetch" else "post"
    assert getattr(Client(), method)(path).status_code == 401
    wrong_methods = (
        (
            scenario.client.post,
            scenario.client.put,
            scenario.client.patch,
            scenario.client.delete,
        )
        if route == "fetch"
        else (
            scenario.client.get,
            scenario.client.put,
            scenario.client.patch,
            scenario.client.delete,
        )
    )
    for wrong in wrong_methods:
        assert (
            wrong(
                owner_credential_path(scenario.convention.pk, scenario.fursuit.pk)
            ).status_code
            == 405
        )
    other = create_credential_scenario(clerk_user_id="credential_cross_owner")
    cross_path = path.replace(str(scenario.fursuit.pk), str(other.fursuit.pk))
    assert (
        getattr(scenario.client, method)(
            cross_path, b"bad" if route == "rotate" else None
        ).status_code
        == 404
    )
    for state in (
        "missing_enrollment",
        "inactive_activation",
        "disabled_fursuit",
        "nonplayable_convention",
    ):
        local = create_credential_scenario(clerk_user_id=f"credential_{state}")
        row = create_activation_row(
            fursuit=local.fursuit, convention=local.convention, active=True
        )
        if state == "missing_enrollment":
            assert local.enrollment is not None
            local.enrollment.delete()
        elif state == "inactive_activation":
            row.is_active = False
            row.deactivated_at = timezone.now()
            row.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        elif state == "disabled_fursuit":
            Fursuit.objects.filter(pk=local.fursuit.pk).update(is_enabled=False)
        else:
            Convention.objects.filter(pk=local.convention.pk).update(status="paused")
        local_path = (
            owner_credential_path(local.convention.pk, local.fursuit.pk)
            if route == "fetch"
            else rotation_path(local.convention.pk, local.fursuit.pk)
        )
        response = getattr(local.client, method)(
            local_path, b"" if route == "rotate" else None
        )
        assert response.status_code == 400
        assert response.json() == {"detail": OWNER_INELIGIBLE_DETAIL}
