"""Operator tag revocation through the restricted admin (#504 AC8, AC9, AC13)."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import parse_qs

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from accounts.models import User
from fursuits.models import Fursuit, FursuitTag
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.authentication_support import create_test_user
from tests.fursuit_tag_test_support import (
    assert_logs_hold_no_token,
    assert_no_token_leak,
    create_player,
    create_suit,
    read_payload,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


def _staff(*codenames: str) -> User:
    user = create_test_user()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        *[
            Permission.objects.get(
                content_type__app_label="fursuits", codename=codename
            )
            for codename in codenames
        ]
    )
    return User.objects.get(pk=user.pk)


def _tag(label: str) -> FursuitTag:
    owner, _ = create_player(label)
    fursuit = create_suit(owner)
    read_payload(owner, fursuit)
    return FursuitTag.objects.get(fursuit=fursuit)


def _urls(tag: FursuitTag) -> tuple[str, str, str]:
    return (
        reverse("admin:fursuits_fursuittag_changelist"),
        reverse("admin:fursuits_fursuittag_change", args=(tag.pk,)),
        reverse("admin:fursuits_fursuittag_history", args=(tag.pk,)),
    )


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _events(tag: FursuitTag) -> list[tuple[str, str, str, str]]:
    return list(
        OperatorAuditEvent.objects.filter(affected_record_id=tag.pk)
        .order_by("occurred_at")
        .values_list("action", "actor_class", "affected_record_type", "outcome")
    )


def test_operator_revokes_the_current_tag_without_seeing_it_or_replacing_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tag = _tag("admin_revoke")
    operator = _staff("revoke_fursuit_tag")
    client = _client(operator)
    changelist, change, history = _urls(tag)

    pages = [client.get(changelist), client.get(change), client.get(history)]
    response = client.post(change, {"revoke": "1"})

    assert all(page.status_code == 200 for page in pages)
    assert b'name="revoke"' in pages[1].content
    assert response.status_code == 302
    tag.refresh_from_db()
    assert tag.revocation_reason == "operator"
    assert Fursuit.objects.get(pk=tag.fursuit_id).tag_version == 2
    assert FursuitTag.objects.filter(fursuit_id=tag.fursuit_id).count() == 1
    assert _events(tag) == [
        (
            OperatorAction.REVOKE_FURSUIT_TAG,
            OperatorActorClass.OPERATOR,
            OperatorTargetType.FURSUIT_TAG,
            OperatorAuditOutcome.SUCCEEDED,
        )
    ]
    for page in [*pages, response, client.get(change)]:
        assert_no_token_leak(page.content.decode())
    assert_logs_hold_no_token(caplog)


def test_token_shaped_search_is_redacted_and_search_never_matches_a_token() -> None:
    tag = _tag("admin_search")
    model_admin = cast(Any, admin.site)._registry[FursuitTag]
    client = _client(_staff("revoke_fursuit_tag"))
    changelist, _, _ = _urls(tag)

    response = client.get(changelist, {"q": tag.token})

    assert all("token" not in field for field in model_admin.search_fields)
    assert "token" not in model_admin.fields
    assert parse_qs(response.wsgi_request.META["QUERY_STRING"]) == {
        "q": ["__tailtag_admin_tag_query_redacted__"]
    }
    assert_no_token_leak(response.content.decode())


@pytest.mark.parametrize(
    "lookup",
    ["token", "token__startswith", "created_version"],
)
def test_url_lookups_cannot_filter_on_the_token_or_other_fields(lookup: str) -> None:
    tag = _tag(f"admin_lookup_{lookup}")
    _tag(f"admin_lookup_other_{lookup}")
    client = _client(_staff("revoke_fursuit_tag"))
    changelist, _, _ = _urls(tag)
    value = tag.token[:5] if lookup.endswith("startswith") else tag.token

    response = client.get(changelist, {lookup: value})
    reason = client.get(changelist, {"revocation_reason__exact": "operator"})

    assert response.status_code == 400
    assert_no_token_leak(response.content.decode())
    assert reason.status_code == 200


@pytest.mark.parametrize(
    "codenames", [(), ("change_fursuittag",), ("set_fursuit_enabled",)]
)
def test_staff_without_the_exact_permission_is_denied_and_audited(
    codenames: tuple[str, ...],
) -> None:
    tag = _tag(f"admin_denied_{'_'.join(codenames) or 'none'}")
    _, change, _ = _urls(tag)

    response = _client(_staff(*codenames)).post(change, {"revoke": "1"})

    assert response.status_code == 403
    tag.refresh_from_db()
    assert tag.is_current
    assert _events(tag) == [
        (
            OperatorAction.REVOKE_FURSUIT_TAG,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorTargetType.FURSUIT_TAG,
            OperatorAuditOutcome.DENIED,
        )
    ]


def test_a_stale_form_on_a_revoked_tag_is_rejected_without_change() -> None:
    tag = _tag("admin_stale")
    client = _client(_staff("revoke_fursuit_tag"))
    _, change, _ = _urls(tag)
    client.post(change, {"revoke": "1"})
    tag.refresh_from_db()
    revoked_at = tag.revoked_at

    stale = client.post(change, {"revoke": "1"})

    assert stale.status_code == 403
    tag.refresh_from_db()
    assert tag.revoked_at == revoked_at
    assert Fursuit.objects.get(pk=tag.fursuit_id).tag_version == 2
    assert [event[3] for event in _events(tag)] == [
        OperatorAuditOutcome.SUCCEEDED,
        OperatorAuditOutcome.REJECTED,
    ]
