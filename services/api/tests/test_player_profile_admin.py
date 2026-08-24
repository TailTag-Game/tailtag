"""Acceptance tests for the deliberately narrow PlayerProfile admin surface."""

from __future__ import annotations

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from tests.authentication_support import create_test_user


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
    for code in ("view_playerprofile", "change_playerprofile"):
        staff.user_permissions.add(
            Permission.objects.get(content_type__app_label="profiles", codename=code)
        )  # pyright: ignore[reportUnknownMemberType]
    staff.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="accounts", codename="change_user"
        )
    )  # pyright: ignore[reportUnknownMemberType]
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
    owner_before = (profile.user.is_staff, profile.user.is_superuser)
    assert (
        client.post(
            reverse("admin:accounts_user_change", args=(profile.user.pk,)),
            {"is_staff": "on"},
        ).status_code
        == 403
    )
    profile.user.refresh_from_db()
    assert (profile.user.is_staff, profile.user.is_superuser) == owner_before
