"""Restricted Django-admin and repository-controlled token-exposure tests."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.admin.views.main import ChangeList
from django.test import Client
from django.urls import reverse

from accounts.models import User
from tests.catch_credential_test_support import (
    PAYLOAD_B,
    TOKEN_A,
    TOKEN_B,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
    rotation_path,
)
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session


def _listed_ids(response: object) -> set[int]:
    context = cast(dict[str, object], response.context)  # type: ignore[attr-defined]
    changelist = cast(ChangeList, context["cl"])
    return {row.pk for row in changelist.result_list}


def _admin_urls(credential: Any) -> tuple[str, str, str, str]:
    opts = credential._meta
    prefix = f"admin:{opts.app_label}_{opts.model_name}"
    return (
        reverse(f"{prefix}_changelist"),
        reverse(f"{prefix}_change", args=(credential.pk,)),
        reverse(f"{prefix}_history", args=(credential.pk,)),
        reverse(f"{prefix}_delete", args=(credential.pk,)),
    )


def _assert_token_absent(token: str, *responses: Any) -> None:
    for response in responses:
        assert token not in response.content.decode()


@pytest.mark.django_db
def test_credential_admin_is_staff_only_safe_history_with_exact_search_and_no_mutation_paths() -> (
    None
):
    """AC-15/16/18: reject an admin that edits, searches, or displays a token."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    credential = create_credential(activation=activation, token=TOKEN_A)
    other = create_credential_scenario(clerk_user_id="credential_admin_other")
    other_activation = create_activation_row(
        fursuit=other.fursuit, convention=other.convention, active=True
    )
    create_credential(activation=other_activation, token=TOKEN_B)
    session = create_catch_session(activation=activation)
    model = catch_credential_model()
    model_admin: Any = admin.site._registry[model]  # type: ignore[reportPrivateUsage]
    operator = User.objects.create_superuser("credential_admin_operator", password="pw")
    client = Client()
    client.force_login(operator)
    changelist, change, history, delete = _admin_urls(credential)

    assert model_admin.actions is None
    assert set(model_admin.search_fields) == {
        "id__exact",
        "activation__id__exact",
        "activation__fursuit__id__exact",
        "activation__fursuit__tailtag_id__exact",
        "activation__fursuit__owner__id__exact",
        "activation__convention__id__exact",
        "activation__fursuit__name",
        "activation__convention__name",
    }
    by_name = client.get(changelist, {"q": scenario.fursuit.name})
    by_token = client.get(changelist, {"q": TOKEN_A})
    detail = client.get(change)
    assert by_name.status_code == by_token.status_code == detail.status_code == 200
    assert _listed_ids(by_name) == {credential.pk}
    assert _listed_ids(by_token) == set()
    listed = next(iter(cast(ChangeList, by_name.context["cl"]).result_list))
    assert model_admin.is_current(listed) is True
    assert model_admin.is_current(credential) is True
    assert b'name="revoke"' in detail.content
    assert b"Revoke current credential" in detail.content
    for raw_or_mutable_field in (
        "activation",
        "token",
        "created_at",
        "updated_at",
        "revoked_at",
        "revocation_reason",
        "rotate",
        "replacement",
    ):
        assert f'name="{raw_or_mutable_field}"'.encode() not in detail.content
    assert (
        client.get(reverse("admin:conventions_fursuitcatchcredential_add")).status_code
        == 403
    )
    assert client.get(delete).status_code == 403
    assert b'name="action"' not in client.get(changelist).content
    _assert_token_absent(TOKEN_A, by_name, by_token, detail)

    # The sole mutation is a per-object revoke; it must not couple to a session.
    assert client.post(change, {"revoke": "1"}).status_code == 302
    credential.refresh_from_db()
    session.refresh_from_db()
    assert credential.revoked_at is not None
    assert credential.revocation_reason == "operator"
    assert session.ended_at is None
    before = (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    )
    assert client.post(change, {"revoke": "1"}).status_code in {200, 302, 403}
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == before
    history_response = client.get(history)
    log = LogEntry.objects.filter(
        content_type__app_label="conventions", object_id=str(credential.pk)
    ).latest("action_time")
    assert TOKEN_A not in str(credential)
    assert TOKEN_A not in log.object_repr
    assert history_response.status_code == 200
    _assert_token_absent(TOKEN_A, history_response)


@pytest.mark.django_db
def test_admin_stale_revoke_cannot_overwrite_rotation_or_eligibility_history_or_leak_payload() -> (
    None
):
    """AC-06/07/08/15/16: reject stale admin terminal rewrites and secret messages."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    old = create_credential(activation=activation, token=TOKEN_A)
    operator = User.objects.create_superuser("credential_stale_operator", password="pw")
    client = Client()
    client.force_login(operator)
    changelist, old_change, old_history, _ = _admin_urls(old)
    stale_form = client.get(old_change)
    assert stale_form.status_code == 200

    with patch("secrets.token_urlsafe", return_value=TOKEN_B):
        rotated = scenario.client.post(
            rotation_path(scenario.convention.pk, scenario.fursuit.pk), b""
        )
    assert rotated.json() == {"payload": PAYLOAD_B}
    old.refresh_from_db()
    snapshot = (old.revoked_at, old.revocation_reason, old.updated_at)
    replacement = catch_credential_model().objects.get(revoked_at__isnull=True)
    assert replacement.pk != old.pk
    stale_post = client.post(old_change, {"revoke": "1"})
    old.refresh_from_db()
    replacement.refresh_from_db()
    assert (old.revoked_at, old.revocation_reason, old.updated_at) == snapshot
    assert replacement.revoked_at is None
    assert replacement.token == TOKEN_B
    _assert_token_absent(TOKEN_A, stale_form, stale_post, client.get(old_history))
    _assert_token_absent(TOKEN_B, client.get(changelist), client.get(old_change))

    # An operator revocation creates neither a replacement nor an owner payload.
    replacement_change = _admin_urls(replacement)[1]
    response = client.post(replacement_change, {"revoke": "1"})
    replacement.refresh_from_db()
    assert response.status_code == 302
    assert replacement.revocation_reason == "operator"
    assert catch_credential_model().objects.filter(activation=activation).count() == 2
