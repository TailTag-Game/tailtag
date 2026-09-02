"""Owner fetch and rotation acceptance contract for catch credentials."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from conventions.models import Convention
from fursuits.models import Fursuit
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.catch_credential_test_support import (
    AUTHENTICATION_DETAIL,
    CONCEALED_DETAIL,
    FORBIDDEN_DETAIL,
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
from tests.fursuit_catch_session_test_support import create_catch_session


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
    with patch("secrets.token_urlsafe", return_value=TOKEN_A):
        second = scenario.client.post(path, b"")
    assert_owner_payload(second, PAYLOAD_A)
    replacement.refresh_from_db()
    assert (
        replacement.revoked_at is not None
        and replacement.revocation_reason == "owner_rotation"
    )
    assert catch_credential_model().objects.get(revoked_at__isnull=True).pk not in {
        old.pk,
        replacement.pk,
    }


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
    unauthenticated = getattr(Client(), method)(path)
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {"detail": AUTHENTICATION_DETAIL}
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
        response = wrong(path)
        assert response.status_code == 405
        assert response.json() == {
            "detail": f'Method "{response.request["REQUEST_METHOD"]}" not allowed.'
        }
    other = create_credential_scenario(clerk_user_id="credential_cross_owner")
    cross_path = path.replace(str(scenario.fursuit.pk), str(other.fursuit.pk))
    concealed = getattr(scenario.client, method)(
        cross_path, b"bad" if route == "rotate" else None
    )
    assert concealed.status_code == 404 and concealed.json() == {
        "detail": CONCEALED_DETAIL
    }
    from profiles.models import PlayerProfile

    PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=False)
    forbidden = getattr(scenario.client, method)(
        path, b"" if route == "rotate" else None
    )
    assert forbidden.status_code == 403 and forbidden.json() == {
        "detail": FORBIDDEN_DETAIL
    }
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


@pytest.mark.django_db
def test_credential_routes_do_not_deliberately_expose_tokens_in_repository_logs_or_errors(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-16: rejects secret-bearing repository logging, errors, or preview failures."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    create_catch_session(activation=activation)
    owner_path = owner_credential_path(scenario.convention.pk, scenario.fursuit.pk)
    rotate_path = rotation_path(scenario.convention.pk, scenario.fursuit.pk)
    resolution = f"/api/conventions/{scenario.convention.pk}/catch-credentials/resolve/"
    with caplog.at_level(logging.DEBUG):
        with patch("secrets.token_urlsafe", return_value=TOKEN_A):
            assert_owner_payload(scenario.client.get(owner_path), PAYLOAD_A)
        with patch("secrets.token_urlsafe", return_value=TOKEN_B):
            assert_owner_payload(scenario.client.post(rotate_path, b""), PAYLOAD_B)
        owner_error = scenario.client.post(rotate_path, b"unexpected")
        assert owner_error.status_code == 400
        assert (
            scenario.client.post(
                resolution, {"payload": PAYLOAD_B}, content_type="application/json"
            ).status_code
            == 200
        )
        missing = scenario.client.post(
            resolution,
            {"payload": "tailtag:catch:v1:" + "Z" * 43},
            content_type="application/json",
        )
        assert missing.status_code == 404
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (TOKEN_A, TOKEN_B, PAYLOAD_A, PAYLOAD_B):
        assert secret not in log_text
        assert secret not in missing.content.decode()
        assert secret not in owner_error.content.decode()

    exception_scenario = create_credential_scenario(
        clerk_user_id="credential_exception"
    )
    create_activation_row(
        fursuit=exception_scenario.fursuit,
        convention=exception_scenario.convention,
        active=True,
    )
    from conventions import catch_credentials

    def fail_token_generation(_: int) -> str:
        raise RuntimeError("synthetic credential generator failure")

    monkeypatch.setattr(
        catch_credentials.secrets, "token_urlsafe", fail_token_generation
    )
    with pytest.raises(
        RuntimeError, match="synthetic credential generator failure"
    ) as error:
        exception_scenario.client.get(
            owner_credential_path(
                exception_scenario.convention.pk, exception_scenario.fursuit.pk
            )
        )
    assert TOKEN_A not in str(error.value) and PAYLOAD_A not in str(error.value)
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert TOKEN_A not in log_text and PAYLOAD_A not in log_text
