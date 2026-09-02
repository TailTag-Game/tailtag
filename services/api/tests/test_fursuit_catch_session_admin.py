"""Restricted support-admin acceptance contract for catch sessions."""

from __future__ import annotations

import datetime
from typing import Any, cast

import pytest
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    create_catch_session,
)


def _listed_session_ids(response: object) -> set[int]:
    context = cast(dict[str, object], response.context)  # type: ignore[attr-defined]
    changelist = cast(ChangeList, context["cl"])
    return {row.pk for row in changelist.result_list}


@pytest.mark.django_db
def test_catch_session_admin_inspects_history_but_prohibits_add_delete_bulk_and_raw_lifecycle_edits() -> (
    None
):
    """AC-01/11: rejects an editable, deletable, or bulk-mutable session admin."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    session = create_catch_session(activation=activation)
    nonmatching = create_activation_scenario(clerk_user_id="catch_session_search_other")
    nonmatching_activation = create_activation_row(
        fursuit=nonmatching.fursuit,
        convention=nonmatching.convention,
        active=True,
    )
    historical_now = timezone.now()
    historical = create_catch_session(
        activation=nonmatching_activation,
        started_at=historical_now - CATCH_SESSION_LIFETIME,
        ended_at=historical_now,
        end_reason="owner",
    )
    session_model = catch_session_model()
    model_admin: Any = admin.site._registry[session_model]  # type: ignore[reportPrivateUsage]
    assert model_admin.actions is None
    assert model_admin.search_fields and model_admin.list_filter
    operator = User.objects.create_superuser(
        "catch_session_operator", password="password"
    )
    client = Client()
    client.force_login(operator)
    change = reverse("admin:conventions_fursuitcatchsession_change", args=(session.pk,))
    changelist = reverse("admin:conventions_fursuitcatchsession_changelist")
    searched = client.get(changelist, {"q": scenario.fursuit.name})
    assert searched.status_code == 200
    assert _listed_session_ids(searched) == {session.pk}
    searched_changelist = cast(ChangeList, searched.context["cl"])
    listed_session = next(iter(searched_changelist.result_list))
    assert model_admin.is_effectively_active(listed_session) is True
    assert model_admin.is_effectively_active(session) is False
    filtered = client.get(changelist, {"is_effectively_active": "1"})
    assert filtered.status_code == 200
    assert _listed_session_ids(filtered) == {session.pk}
    assert historical.pk not in _listed_session_ids(searched)
    assert historical.pk not in _listed_session_ids(filtered)
    detail = client.get(change)
    assert detail.status_code == 200
    for field in (
        "activation",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "created_at",
        "updated_at",
    ):
        assert f'name="{field}"'.encode() not in detail.content
    assert (
        client.get(reverse("admin:conventions_fursuitcatchsession_add")).status_code
        == 403
    )
    assert (
        client.get(
            reverse("admin:conventions_fursuitcatchsession_delete", args=(session.pk,))
        ).status_code
        == 403
    )
    assert (
        b'name="action"'
        not in client.get(
            reverse("admin:conventions_fursuitcatchsession_changelist")
        ).content
    )


@pytest.mark.django_db
def test_admin_per_object_operator_termination_ends_only_live_row_and_never_relables_expired_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11/12: rejects raw field editing or rewriting an expired terminal reason."""
    scenario = create_activation_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    live = create_catch_session(activation=activation)
    operator = User.objects.create_superuser(
        "catch_session_terminator", password="password"
    )
    client = Client()
    client.force_login(operator)
    change = reverse("admin:conventions_fursuitcatchsession_change", args=(live.pk,))
    assert client.post(change, {"terminate": "1"}).status_code == 302
    live.refresh_from_db()
    assert live.ended_at is not None and live.end_reason == "operator"
    before = (live.ended_at, live.end_reason, live.updated_at)
    assert client.post(change, {"terminate": "1"}).status_code in {200, 302, 403}
    live.refresh_from_db()
    assert (live.ended_at, live.end_reason, live.updated_at) == before
    # A separate stale unended row is allowed only after the live row is terminal.
    from conventions import services

    now = timezone.now()
    monkeypatch.setattr(services.timezone, "now", lambda: now)
    expired = create_catch_session(
        activation=activation,
        started_at=now - datetime.timedelta(hours=12),
        expires_at=now,
    )
    expired_change = reverse(
        "admin:conventions_fursuitcatchsession_change", args=(expired.pk,)
    )
    assert client.post(expired_change, {"terminate": "1"}).status_code == 302
    expired.refresh_from_db()
    assert expired.ended_at == now and expired.end_reason == "expired"
