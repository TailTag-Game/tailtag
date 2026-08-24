"""Acceptance tests for the deliberately narrow PlayerProfile admin surface."""

from __future__ import annotations

from typing import Protocol, cast

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from tests.authentication_support import create_test_user


class _PermissionRelation(Protocol):
    """The runtime manager capability exercised by this admin acceptance test."""

    def add(self, *objects: Permission) -> None: ...


def _superuser_flag(user: User) -> bool:
    """Read Django's dynamically supplied permission flag with its stable bool contract."""
    return cast(bool, user.is_superuser)  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.django_db
def test_profile_admin_limits_staff_operators_to_safe_inspection_and_enabled_edits() -> (
    None
):
    """Rejects an admin that exposes provider data, keys, add/delete, or bulk mutations."""
    from profiles.models import PlayerProfile

    operator = User.objects.create_superuser(
        "operator", password="safe-local-admin-password"
    )
    profile = PlayerProfile.objects.create(
        user=create_test_user(),
        handle="safe_1",
        display_name="Safe",
        avatar_key="images/0123456789abcdef0123456789abcdef.png",
        onboarding_completed_at=timezone.now(),
    )
    client = Client()
    client.force_login(operator)
    list_response = client.get(reverse("admin:profiles_playerprofile_changelist"))
    change_url = reverse("admin:profiles_playerprofile_change", args=(profile.pk,))
    change_response = client.get(change_url)
    add_response = client.get(reverse("admin:profiles_playerprofile_add"))
    delete_response = client.get(
        reverse("admin:profiles_playerprofile_delete", args=(profile.pk,))
    )
    post_response = client.post(change_url, {"is_enabled": ""})
    profile.refresh_from_db()

    assert [response.status_code for response in (list_response, change_response)] == [
        200,
        200,
    ]
    assert [response.status_code for response in (add_response, delete_response)] == [
        403,
        403,
    ]
    assert post_response.status_code == 302
    assert profile.is_enabled is False
    rendered = list_response.content + change_response.content
    assert b"safe_1" in rendered
    assert b"Safe" in rendered
    assert b"images/0123456789abcdef0123456789abcdef.png" not in rendered
    assert profile.user.clerk_user_id.encode() not in rendered
    assert LogEntry.objects.filter(object_id=str(profile.pk)).exists()
    assert not change_response.context["adminform"].form.fields["is_enabled"].disabled


@pytest.mark.django_db
def test_normal_staff_permissions_are_sufficient_but_accounts_admin_stays_read_only() -> (
    None
):
    """Rejects superuser-only profile administration or collateral accounts-admin changes."""
    from profiles.models import PlayerProfile

    staff = create_test_user()
    staff.is_staff = True
    staff.save(update_fields={"is_staff"})
    staff_permissions = cast(
        _PermissionRelation,
        staff.user_permissions,  # pyright: ignore[reportUnknownMemberType]
    )
    for code in ("view_playerprofile", "change_playerprofile"):
        staff_permissions.add(
            Permission.objects.get(content_type__app_label="profiles", codename=code)
        )
    staff_permissions.add(
        Permission.objects.get(
            content_type__app_label="accounts", codename="change_user"
        )
    )
    profile = PlayerProfile.objects.create(user=create_test_user())
    client = Client()
    client.force_login(staff)
    assert (
        client.get(reverse("admin:profiles_playerprofile_changelist")).status_code
        == 200
    )
    assert (
        client.get(
            reverse("admin:profiles_playerprofile_change", args=(profile.pk,))
        ).status_code
        == 200
    )
    profile_change = client.post(
        reverse("admin:profiles_playerprofile_change", args=(profile.pk,)),
        {"is_enabled": ""},
    )
    profile.refresh_from_db()
    assert profile_change.status_code == 302
    assert profile.is_enabled is False
    assert LogEntry.objects.filter(user=staff, object_id=str(profile.pk)).exists()
    owner_before: tuple[bool, bool] = (
        profile.user.is_staff,
        _superuser_flag(profile.user),
    )
    assert (
        client.post(
            reverse("admin:accounts_user_change", args=(profile.user.pk,)),
            {"is_staff": "on"},
        ).status_code
        == 403
    )
    profile.user.refresh_from_db()
    assert (
        profile.user.is_staff,
        _superuser_flag(profile.user),
    ) == owner_before


@pytest.mark.django_db
def test_view_only_staff_can_inspect_but_cannot_change_or_bulk_disable_profiles() -> (
    None
):
    """Rejects treating inspection permission as authority to disable players in bulk or per row."""
    from profiles.models import PlayerProfile

    staff = create_test_user()
    staff.is_staff = True
    staff.save(update_fields={"is_staff"})
    permissions = cast(
        _PermissionRelation,
        staff.user_permissions,  # pyright: ignore[reportUnknownMemberType]
    )
    permissions.add(
        Permission.objects.get(
            content_type__app_label="profiles", codename="view_playerprofile"
        )
    )
    profile = PlayerProfile.objects.create(user=create_test_user())
    client = Client()
    client.force_login(staff)
    change_url = reverse("admin:profiles_playerprofile_change", args=(profile.pk,))
    response = client.get(reverse("admin:profiles_playerprofile_changelist"))
    assert response.status_code == 200
    assert client.get(change_url).status_code == 200
    assert client.post(change_url, {"is_enabled": ""}).status_code == 403
    profile.refresh_from_db()
    assert profile.is_enabled is True
    assert b'name="action"' not in response.content
