"""Restricted inspection-only fursuit administration acceptance contract."""

from __future__ import annotations

from typing import Protocol, cast

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.files.storage import default_storage
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import RECORDING_STORAGES


class _PermissionManager(Protocol):
    def add(self, *permissions: Permission) -> None: ...


class _UserWithPermissions(Protocol):
    user_permissions: _PermissionManager


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_admin_allows_only_enabled_toggle_and_never_exposes_key_or_clerk_identity() -> (
    None
):
    operator = User.objects.create_superuser(
        "operator", password="safe-local-admin-password"
    )
    record = create_fursuit_record(
        owner=create_eligible_user(),
        photo_key="images/0123456789abcdef0123456789abcdef.png",
    )
    client = Client()
    client.force_login(operator)
    list_response = client.get(reverse("admin:fursuits_fursuit_changelist"))
    storage = default_storage
    from tests.profile_test_support import RecordingStorage

    assert isinstance(storage, RecordingStorage)
    assert storage.url_calls == 0
    change = reverse("admin:fursuits_fursuit_change", args=(record.pk,))
    detail = client.get(change)
    assert storage.url_calls == 1
    before_update = record.updated_at
    tailtag_id_before = record.tailtag_id
    posted = client.post(change, {"is_enabled": ""})
    record.refresh_from_db()
    assert [response.status_code for response in (list_response, detail, posted)] == [
        200,
        200,
        302,
    ]
    assert (
        record.is_enabled is False
        and LogEntry.objects.filter(object_id=str(record.pk)).exists()
    )
    assert record.updated_at > before_update
    assert record.tailtag_id == tailtag_id_before
    after_toggle = record.updated_at
    repeated = client.post(change, {"is_enabled": ""})
    record.refresh_from_db()
    assert repeated.status_code == 302
    assert record.is_enabled is False and record.updated_at == after_toggle
    assert record.tailtag_id == tailtag_id_before
    rendered = list_response.content + detail.content
    assert (
        b"0123456789abcdef0123456789abcdef" not in rendered
        and record.owner.clerk_user_id.encode() not in rendered
    )
    assert client.get(reverse("admin:fursuits_fursuit_add")).status_code == 403
    assert (
        client.get(
            reverse("admin:fursuits_fursuit_delete", args=(record.pk,))
        ).status_code
        == 403
    )
    assert b'name="action"' not in list_response.content
    assert b"https://media.example.test/read/" not in list_response.content
    assert b"photo" in list_response.content.lower()
    assert str(tailtag_id_before).encode() in detail.content


@pytest.mark.django_db
def test_admin_search_excludes_clerk_and_opaque_key_but_finds_safe_record_identifiers() -> (
    None
):
    operator = User.objects.create_superuser(
        "search_operator", password="safe-local-admin-password"
    )
    owner = create_eligible_user(clerk_user_id="user_clerk_search_secret_115")
    record = create_fursuit_record(
        owner=owner,
        name="Searchable Character 115",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
    )
    if record.pk == owner.pk:
        record = create_fursuit_record(
            owner=owner,
            name="Searchable Character 115 Alternate",
            photo_key="images/fedcba9876543210fedcba9876543210.png",
        )
    assert str(record.pk) != str(owner.pk)
    client = Client()
    client.force_login(operator)
    changelist = reverse("admin:fursuits_fursuit_changelist")

    for forbidden in (owner.clerk_user_id, record.photo_key):
        response = client.get(changelist, {"q": forbidden})
        assert response.status_code == 200
        assert record.name.encode() not in response.content

    for allowed in (str(record.pk), str(owner.pk), record.name, str(record.tailtag_id)):
        response = client.get(changelist, {"q": allowed})
        assert response.status_code == 200
        assert record.name.encode() in response.content

    partial_tailtag_id = str(record.tailtag_id).split("-", maxsplit=1)[0]
    response = client.get(changelist, {"q": partial_tailtag_id})
    assert response.status_code == 200
    assert record.name.encode() not in response.content


@pytest.mark.django_db
def test_view_only_staff_cannot_toggle_and_change_staff_cannot_forge_hidden_fields() -> (
    None
):
    record = create_fursuit_record(owner=create_eligible_user())
    name_before = record.name
    photo_before = record.photo_key
    owner_before = record.owner_id
    created_before = record.created_at
    for codes, expected in (
        (["view_fursuit"], 403),
        (["view_fursuit", "change_fursuit"], 302),
    ):
        staff = create_eligible_user()
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        cast(_UserWithPermissions, staff).user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="fursuits", codename__in=codes
            )
        )
        client = Client()
        client.force_login(staff)
        url = reverse("admin:fursuits_fursuit_change", args=(record.pk,))
        response = client.post(
            url,
            {
                "is_enabled": "",
                "name": "Forged",
                "photo_key": "forged",
                "owner": staff.pk,
                "created_at": "2000-01-01T00:00:00Z",
                "updated_at": "2000-01-01T00:00:00Z",
            },
        )
        assert response.status_code == expected
        record.refresh_from_db()
        assert record.name == name_before and record.photo_key == photo_before
        assert record.owner_id == owner_before and record.created_at == created_before
        assert record.updated_at.year != 2000
