"""Restricted Django-admin acceptance tests for fursuit activation."""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from typing import cast

import pytest
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions.admin import FursuitActivationAdmin
from conventions.models import Convention, ConventionStatus, FursuitActivation
from tests.fursuit_activation_test_support import create_activation_scenario
from tests.fursuit_test_support import create_fursuit_record


def _admin_result_ids(response: object) -> set[int]:
    context = cast(Mapping[str, object], response.context)  # type: ignore[attr-defined]
    changelist = cast(ChangeList, context["cl"])
    result_list = cast(Iterable[FursuitActivation], changelist.result_list)
    return {activation.pk for activation in result_list}


@pytest.mark.django_db
def test_activation_admin_is_searchable_filterable_and_has_no_add_delete_or_actions() -> (
    None
):
    scenario = create_activation_scenario()
    activation = FursuitActivation.objects.create(
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    inactive_fursuit = create_fursuit_record(
        owner=scenario.user, name="Inactive activation fursuit"
    )
    inactive = FursuitActivation.objects.create(
        fursuit=inactive_fursuit,
        convention=scenario.convention,
        is_active=False,
        activated_at=timezone.now(),
        deactivated_at=timezone.now(),
    )
    other_convention = Convention.objects.create(
        name="Other admin activation convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 8, 1),
        end_date=datetime.date(2026, 8, 4),
    )
    other_convention_activation = FursuitActivation.objects.create(
        fursuit=scenario.fursuit,
        convention=other_convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    registry = cast(
        dict[type[object], object],
        admin.site._registry,  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    )
    assert FursuitActivation in registry
    model_admin = cast(FursuitActivationAdmin, registry[FursuitActivation])
    assert isinstance(model_admin, FursuitActivationAdmin)
    assert model_admin.actions is None
    assert {"fursuit", "convention", "is_active"}.issubset(set(model_admin.list_filter))
    assert model_admin.search_fields
    operator = User.objects.create_superuser("activation_operator", password="password")
    client = Client()
    client.force_login(operator)
    changelist = client.get(reverse("admin:conventions_fursuitactivation_changelist"))
    assert changelist.status_code == 200
    assert activation.pk and str(activation.pk).encode() in changelist.content
    changelist_url = reverse("admin:conventions_fursuitactivation_changelist")
    searched = client.get(changelist_url, {"q": str(scenario.fursuit.pk)})
    assert searched.status_code == 200
    assert activation.pk in _admin_result_ids(searched)
    active_only = client.get(changelist_url, {"is_active__exact": "1"})
    assert active_only.status_code == 200
    assert _admin_result_ids(active_only) == {
        activation.pk,
        other_convention_activation.pk,
    }
    inactive_only = client.get(changelist_url, {"is_active__exact": "0"})
    assert inactive_only.status_code == 200
    assert _admin_result_ids(inactive_only) == {inactive.pk}
    convention_only = client.get(
        changelist_url, {"convention__id__exact": str(scenario.convention.pk)}
    )
    assert convention_only.status_code == 200
    assert _admin_result_ids(convention_only) == {activation.pk, inactive.pk}
    fursuit_only = client.get(
        changelist_url, {"fursuit__id__exact": str(scenario.fursuit.pk)}
    )
    assert fursuit_only.status_code == 200
    assert _admin_result_ids(fursuit_only) == {
        activation.pk,
        other_convention_activation.pk,
    }
    assert (
        client.get(reverse("admin:conventions_fursuitactivation_add")).status_code
        == 403
    )
    assert (
        client.get(
            reverse("admin:conventions_fursuitactivation_delete", args=(activation.pk,))
        ).status_code
        == 403
    )
    assert b'name="action"' not in changelist.content


@pytest.mark.django_db
def test_activation_admin_only_allows_active_to_inactive_and_preserves_timestamps_on_noop() -> (
    None
):
    scenario = create_activation_scenario()
    activation = FursuitActivation.objects.create(
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    operator = User.objects.create_superuser(
        "activation_moderator", password="password"
    )
    client = Client()
    client.force_login(operator)
    change = reverse(
        "admin:conventions_fursuitactivation_change", args=(activation.pk,)
    )
    detail = client.get(change)
    assert detail.status_code == 200
    for forbidden in (
        "fursuit",
        "convention",
        "activated_at",
        "deactivated_at",
        "created_at",
        "updated_at",
    ):
        assert f'name="{forbidden}"'.encode() not in detail.content
    before = (activation.activated_at, activation.deactivated_at, activation.updated_at)
    assert client.post(change, {"is_active": ""}).status_code == 302
    activation.refresh_from_db()
    assert not activation.is_active
    assert (
        activation.activated_at == before[0] and activation.deactivated_at is not None
    )
    assert activation.updated_at > before[2]
    deactivated = (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    )
    assert client.post(change, {"is_active": ""}).status_code == 302
    activation.refresh_from_db()
    assert (
        activation.activated_at,
        activation.deactivated_at,
        activation.updated_at,
    ) == deactivated
    rejected = client.post(change, {"is_active": "on"})
    assert rejected.status_code in {200, 403}
    activation.refresh_from_db()
    assert not activation.is_active and activation.deactivated_at == deactivated[1]
