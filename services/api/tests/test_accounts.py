"""TailTag application-user identity contract."""

from __future__ import annotations

from typing import cast

import pytest
from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.test import Client
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_application_user_is_the_canonical_tailtag_identity() -> None:
    """A Clerk identity resolves to a separate TailTag-owned primary key."""
    user = User.objects.create_user(clerk_user_id="user_external_identity")

    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User
    assert User._meta.pk.get_internal_type() == "BigAutoField"
    assert isinstance(user.pk, int)
    assert user.pk > 0
    assert str(user.pk) not in user.clerk_user_id
    assert not user.has_usable_password()
    assert str(user) == f"TailTag user {user.pk}"


@pytest.mark.django_db
def test_application_user_requires_a_clerk_identity() -> None:
    """An application user cannot exist without its external identity link."""
    with pytest.raises(ValueError, match="Clerk user ID must be set"):
        User.objects.create_user(clerk_user_id="")


@pytest.mark.django_db
def test_database_rejects_an_empty_clerk_identity() -> None:
    """Every persistence path must preserve the required Clerk identity link."""
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(clerk_user_id="")


@pytest.mark.django_db
def test_application_user_rejects_a_local_django_password() -> None:
    """Clerk-authenticated application users cannot gain fallback credentials."""
    with pytest.raises(ValueError, match="do not use Django passwords"):
        User.objects.create_user(
            clerk_user_id="user_no_local_password",
            password="must-not-become-a-credential",
        )


@pytest.mark.django_db
def test_application_user_cannot_set_a_local_django_password() -> None:
    """The model API preserves Clerk as the ordinary-user auth authority."""
    user = User.objects.create_user(clerk_user_id="user_password_mutation")

    with pytest.raises(ValueError, match="Only Django superusers"):
        user.set_password("must-not-become-a-credential")

    user.refresh_from_db()
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_internal_user_creation_rejects_a_malformed_local_admin() -> None:
    """The shared manager helper cannot bypass the complete admin contract."""
    with pytest.raises(ValueError, match="staff and superuser flags"):
        User.objects._create_user(  # pyright: ignore[reportPrivateUsage]
            clerk_user_id="user_malformed_local_admin",
            password="must-not-become-a-credential",
            is_staff=False,
            is_superuser=True,
        )


@pytest.mark.django_db
def test_application_user_rejects_privileged_flags() -> None:
    """The ordinary-user path cannot provision Django privileges."""
    with pytest.raises(ValueError, match="is_staff=False"):
        User.objects.create_user(
            clerk_user_id="user_privileged_staff",
            is_staff=True,
        )
    with pytest.raises(ValueError, match="is_superuser=False"):
        User.objects.create_user(
            clerk_user_id="user_privileged_superuser",
            is_superuser=True,
        )


@pytest.mark.django_db
def test_superuser_requires_admin_flags_and_uses_its_local_password() -> None:
    """Only the Django superuser bootstrap path accepts a local password."""
    password = "local-admin-password"
    superuser = User.objects.create_superuser(
        clerk_user_id="user_superuser_contract",
        password=password,
    )

    assert superuser.is_staff
    assert cast(
        bool,
        superuser.is_superuser,  # pyright: ignore[reportUnknownMemberType]
    )
    assert superuser.check_password(password)

    with pytest.raises(ValueError, match="is_staff=True"):
        User.objects.create_superuser(
            clerk_user_id="user_not_staff",
            password=password,
            is_staff=False,
        )
    with pytest.raises(ValueError, match="is_superuser=True"):
        User.objects.create_superuser(
            clerk_user_id="user_not_superuser",
            password=password,
            is_superuser=False,
        )


@pytest.mark.django_db
def test_demoted_superuser_loses_its_local_password() -> None:
    """A non-superuser cannot retain a usable local credential after saving."""
    superuser = User.objects.create_superuser(
        clerk_user_id="user_demoted_admin",
        password="local-admin-password",
    )

    superuser.is_superuser = False  # pyright: ignore[reportUnknownMemberType]
    superuser.save(update_fields={"is_superuser"})
    superuser.refresh_from_db()

    assert not cast(
        bool,
        superuser.is_superuser,  # pyright: ignore[reportUnknownMemberType]
    )
    assert not superuser.has_usable_password()

    staff_admin = User.objects.create_superuser(
        clerk_user_id="user_demoted_staff_admin",
        password="another-local-admin-password",
    )
    staff_admin.is_staff = False
    staff_admin.save(update_fields={"is_staff"})
    staff_admin.refresh_from_db()

    assert not staff_admin.is_staff
    assert not staff_admin.has_usable_password()


@pytest.mark.django_db
def test_database_rejects_bulk_demotion_with_a_usable_password() -> None:
    """Bulk writes cannot bypass the local-password persistence contract."""
    superuser = User.objects.create_superuser(
        clerk_user_id="user_bulk_demoted_admin",
        password="local-admin-password",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=superuser.pk).update(is_superuser=False)


def test_superuser_password_cannot_match_the_clerk_identity() -> None:
    """Admin password validation uses this model's actual login attribute."""
    clerk_user_id = "user_admin_password_similarity"
    superuser = User(
        clerk_user_id=clerk_user_id,
        is_staff=True,
        is_superuser=True,
    )

    with pytest.raises(ValidationError) as error:
        validate_password(clerk_user_id, superuser)

    assert any(item.code == "password_too_similar" for item in error.value.error_list)


@pytest.mark.django_db
def test_clerk_identity_link_is_unique_and_not_the_tailtag_primary_key() -> None:
    """Two TailTag users cannot claim the same opaque Clerk identity."""
    clerk_user_id = "user_CaseSensitiveExternalIdentity"
    first_user = User.objects.create_user(clerk_user_id=clerk_user_id)
    field = cast(
        "models.CharField[str, str]",
        User._meta.get_field("clerk_user_id"),
    )

    assert first_user.clerk_user_id == clerk_user_id
    assert field.unique
    assert not field.primary_key
    assert not field.null
    assert not field.blank

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(clerk_user_id=clerk_user_id)


def test_application_user_has_no_profile_or_product_lifecycle_fields() -> None:
    """The identity model contains only its link and Django infrastructure."""
    concrete_fields = {
        field.name
        for field in User._meta.get_fields()
        if field.concrete and not field.many_to_many
    }
    many_to_many_fields = {
        field.name for field in User._meta.get_fields() if field.many_to_many
    }

    assert concrete_fields == {
        "id",
        "password",
        "last_login",
        "is_superuser",
        "clerk_user_id",
        "is_staff",
    }
    assert many_to_many_fields == {"groups", "user_permissions"}


@pytest.mark.django_db
def test_downstream_relationships_store_the_tailtag_user_identity() -> None:
    """A real Django relation targets the TailTag key, never the Clerk ID."""
    user = User.objects.create_user(clerk_user_id="user_external_relationship")
    content_type = ContentType.objects.get_for_model(User)

    log_entry = LogEntry.objects.create(
        user=user,
        content_type=content_type,
        object_id=str(user.pk),
        object_repr=str(user),
        action_flag=CHANGE,
        change_message="Identity relationship verification",
    )

    stored_entry = LogEntry.objects.select_related("user").get(pk=log_entry.pk)
    stored_user = cast(
        User,
        stored_entry.user,  # pyright: ignore[reportUnknownMemberType]
    )
    stored_user_id = cast(
        int,
        stored_entry.user_id,  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
    )
    assert stored_user == user
    assert stored_user_id == user.pk
    assert stored_user_id != user.clerk_user_id


@pytest.mark.django_db
def test_admin_inspects_identity_without_exposing_password_material(
    client: Client,
) -> None:
    """Django admin exposes stable IDs but no local credential material."""
    admin_password = "local-admin-password-not-for-clerk"
    admin_user = User.objects.create_superuser(
        clerk_user_id="user_admin_identity",
        password=admin_password,
    )
    ordinary_user = User.objects.create_user(
        clerk_user_id="user_searchable_identity",
    )
    User.objects.create_user(clerk_user_id="USER_SEARCHABLE_IDENTITY")
    User.objects.create_user(clerk_user_id="user_unrelated_identity")
    client.force_login(admin_user)

    changelist_response = client.get(
        reverse("admin:accounts_user_changelist"),
        {"q": ordinary_user.clerk_user_id},
    )
    change_response = client.get(
        reverse("admin:accounts_user_change", args=(ordinary_user.pk,))
    )
    add_response = client.get(reverse("admin:accounts_user_add"))
    delete_response = client.get(
        reverse("admin:accounts_user_delete", args=(ordinary_user.pk,))
    )
    rendered_responses = changelist_response.content + change_response.content

    assert changelist_response.status_code == 200
    assert change_response.status_code == 200
    assert add_response.status_code == 403
    assert delete_response.status_code == 403
    assert ordinary_user.clerk_user_id.encode() in rendered_responses
    assert str(ordinary_user.pk).encode() in rendered_responses
    assert b"USER_SEARCHABLE_IDENTITY" not in changelist_response.content
    assert b"user_unrelated_identity" not in changelist_response.content
    assert admin_password.encode() not in rendered_responses
    admin_password_hash = cast(
        str,
        admin_user.password,  # pyright: ignore[reportUnknownMemberType]
    )
    ordinary_password_hash = cast(
        str,
        ordinary_user.password,  # pyright: ignore[reportUnknownMemberType]
    )
    assert admin_password_hash.encode() not in rendered_responses
    assert ordinary_password_hash.encode() not in rendered_responses


@pytest.mark.django_db
def test_staff_admin_cannot_edit_application_identity(
    client: Client,
) -> None:
    """Change permission permits inspection but never identity mutation."""
    staff_user = User.objects.create_user(clerk_user_id="user_staff_inspector")
    staff_user.is_staff = True
    staff_user.save(update_fields={"is_staff"})
    change_user_permission = Permission.objects.get(
        content_type__app_label="accounts",
        codename="change_user",
    )
    staff_user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        change_user_permission,
    )

    protected_user = User.objects.create_user(
        clerk_user_id="user_protected_identity",
    )
    protected_group = Group.objects.create(name="protected identity group")
    protected_permission = Permission.objects.get(
        content_type__app_label="accounts",
        codename="view_user",
    )
    protected_user.groups.add(  # pyright: ignore[reportUnknownMemberType]
        protected_group,
    )
    protected_user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        protected_permission,
    )
    client.force_login(staff_user)
    change_url = reverse(
        "admin:accounts_user_change",
        args=(protected_user.pk,),
    )

    get_response = client.get(change_url)
    post_response = client.post(
        change_url,
        {
            "is_superuser": "on",
            "groups": [],
            "user_permissions": [],
        },
    )
    protected_user.refresh_from_db()

    assert get_response.status_code == 200
    assert post_response.status_code == 403
    assert not cast(
        bool,
        protected_user.is_superuser,  # pyright: ignore[reportUnknownMemberType]
    )
    assert set(
        protected_user.groups.all(),  # pyright: ignore[reportUnknownMemberType]
    ) == {protected_group}
    assert set(
        protected_user.user_permissions.all(),  # pyright: ignore[reportUnknownMemberType]
    ) == {
        protected_permission,
    }
