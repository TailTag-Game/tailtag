"""Tests for Catch admin interface and operator removal service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
from django.contrib import admin
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catches.admin import REDACTED_CREDENTIAL_SEARCH_QUERY, CatchAdmin
from catches.models import Catch
from catches.services import remove_catch_as_operator
from conventions.models import (
    Convention,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.catch_credential_test_support import (
    PAYLOAD_A,
    PAYLOAD_B,
    TOKEN_A,
    TOKEN_B,
    create_credential,
)
from tests.catch_history_test_support import create_history_catch
from tests.catch_test_support import (
    create_catch,
    create_catch_scenario,
)


class _PermissionManager(Protocol):
    def add(self, *permissions: Permission) -> None: ...


class _UserWithPermissions(Protocol):
    is_superuser: bool
    user_permissions: _PermissionManager


@dataclass(frozen=True)
class _AdminUrls:
    changelist: str
    add: str
    change: str
    history: str
    delete: str


def _listed_ids(response: object) -> set[int]:
    context = cast(dict[str, object], response.context)  # type: ignore[attr-defined]
    changelist = cast(ChangeList, context["cl"])
    return {row.pk for row in changelist.result_list}


def _admin_urls(catch: Catch) -> _AdminUrls:
    opts = catch._meta
    prefix = f"admin:{opts.app_label}_{opts.model_name}"
    return _AdminUrls(
        changelist=reverse(f"{prefix}_changelist"),
        add=reverse(f"{prefix}_add"),
        change=reverse(f"{prefix}_change", args=(catch.pk,)),
        history=reverse(f"{prefix}_history", args=(catch.pk,)),
        delete=reverse(f"{prefix}_delete", args=(catch.pk,)),
    )


def _log_entry_repr(entry: LogEntry) -> str:
    return str(cast(Any, entry).object_repr)


def _log_entry_message(entry: LogEntry) -> str:
    return str(cast(Any, entry).change_message)


def _log_entry_action_flag(entry: LogEntry) -> int:
    return int(cast(Any, entry).action_flag)


def _log_entry_user_id(entry: LogEntry) -> int:
    user = cast(User, entry.user)  # pyright: ignore[reportUnknownMemberType]
    return user.pk


def _assert_token_absent(token: str, *responses: Any) -> None:
    for response in responses:
        if isinstance(response, (str, bytes)):
            text = response.decode() if isinstance(response, bytes) else response
            assert token not in text
        else:
            assert token not in response.content.decode()


def _assert_sensitive_search_request_is_sanitized(response: Any) -> None:
    query_string = response.wsgi_request.META["QUERY_STRING"]
    assert TOKEN_A not in query_string and PAYLOAD_A not in query_string
    assert TOKEN_B not in query_string and PAYLOAD_B not in query_string
    assert parse_qs(query_string) == {"q": [REDACTED_CREDENTIAL_SEARCH_QUERY]}


def _catch_history_result_ids(data: dict[str, object]) -> set[int]:
    results = data["results"]
    assert isinstance(results, list)
    rows = cast(list[object], results)
    return {cast(int, cast(dict[str, object], row)["id"]) for row in rows}


@pytest.mark.django_db(transaction=True)
def test_remove_catch_as_operator_atomically_deletes_catch_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Issue #179 ADMIN-04: removal preserves participation history and logs safely."""
    scenario = create_catch_scenario()
    historical_credential = create_credential(
        activation=scenario.activation,
        token=TOKEN_A,
        revoked_at=timezone.now(),
        revocation_reason="owner_rotation",
    )
    current_credential = create_credential(
        activation=scenario.activation, token=TOKEN_B
    )
    catch = create_catch(scenario=scenario)
    catch_id = catch.pk
    catcher_user_id = catch.catcher_user_id
    fursuit_id = catch.fursuit_id
    convention_id = catch.convention_id
    activation_id = catch.activation_id
    catch_session_id = catch.catch_session_id
    credential_history_before = list(
        FursuitCatchCredential.objects.filter(activation_id=activation_id)
        .order_by("created_at", "pk")
        .values(
            "id",
            "activation_id",
            "token",
            "revoked_at",
            "revocation_reason",
            "created_at",
            "updated_at",
        )
    )
    assert [row["id"] for row in credential_history_before] == [
        historical_credential.pk,
        current_credential.pk,
    ]

    with caplog.at_level(logging.INFO):
        remove_catch_as_operator(catch_id=catch_id)

    assert not Catch.objects.filter(pk=catch_id).exists()
    assert User.objects.filter(pk=catcher_user_id).exists()
    assert Fursuit.objects.filter(pk=fursuit_id).exists()
    assert Convention.objects.filter(pk=convention_id).exists()
    assert FursuitActivation.objects.filter(pk=activation_id).exists()
    assert FursuitCatchSession.objects.filter(pk=catch_session_id).exists()
    assert (
        list(
            FursuitCatchCredential.objects.filter(activation_id=activation_id)
            .order_by("created_at", "pk")
            .values(
                "id",
                "activation_id",
                "token",
                "revoked_at",
                "revocation_reason",
                "created_at",
                "updated_at",
            )
        )
        == credential_history_before
    )

    expected_log = (
        f"Operator removed catch {catch_id} (catcher_user_id={catcher_user_id}, "
        f"fursuit_id={fursuit_id}, convention_id={convention_id}, "
        f"activation_id={activation_id}, catch_session_id={catch_session_id})."
    )
    assert any(
        record.levelno == logging.INFO and expected_log in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db(transaction=True)
def test_remove_catch_as_operator_rollback_does_not_emit_audit_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the transaction rolls back or fails, on_commit audit log is not emitted."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)
    catch_id = catch.pk

    with (
        caplog.at_level(logging.INFO),
        pytest.raises(RuntimeError, match="simulated failure"),
        transaction.atomic(),
    ):
        remove_catch_as_operator(catch_id=catch_id)
        raise RuntimeError("simulated failure")

    assert Catch.objects.filter(pk=catch_id).exists()
    assert not any(
        "Operator removed catch" in record.getMessage() for record in caplog.records
    )


@pytest.mark.django_db
def test_remove_catch_as_operator_raises_when_not_found() -> None:
    """Nonexistent catch ID raises Catch.DoesNotExist with exact message."""
    with pytest.raises(
        Catch.DoesNotExist, match="Catch with ID 999999 does not exist."
    ):
        remove_catch_as_operator(catch_id=999999)


@pytest.mark.django_db
def test_catch_admin_configuration_and_immutability() -> None:
    """Verify CatchAdmin configuration, field definitions, and disabled actions."""
    assert Catch in admin.site._registry  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    model_admin = cast(
        CatchAdmin,
        admin.site._registry[Catch],  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    )
    assert isinstance(model_admin, CatchAdmin)

    assert model_admin.fields == (
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
        "caught_at",
    )
    assert model_admin.readonly_fields == model_admin.fields
    assert model_admin.list_display == (
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "caught_at",
        "activation",
        "catch_session",
    )
    assert model_admin.list_select_related == (
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
    )
    assert model_admin.list_filter == ("convention", "caught_at")
    assert model_admin.search_fields == (
        "id__exact",
        "catcher_user__id__exact",
        "catcher_user__clerk_user_id",
        "fursuit__name",
        "fursuit__tailtag_id__exact",
        "convention__name",
    )
    assert model_admin.ordering == ("-caught_at", "-id")
    assert model_admin.actions is None


@pytest.mark.django_db
def test_catch_admin_permissions_and_bulk_delete_denial() -> None:
    """Add and change are disallowed; bulk deletion raises PermissionDenied."""
    factory = RequestFactory()
    model_admin = cast(
        CatchAdmin,
        admin.site._registry[Catch],  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    )

    operator = User.objects.create_superuser("catch_admin_operator", password="pw")
    staff_user = create_test_user(clerk_user_id="catch_admin_staff")
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])
    non_staff = create_test_user(clerk_user_id="catch_admin_non_staff")

    add_perm = Permission.objects.get(
        content_type__app_label="catches", codename="add_catch"
    )
    change_perm = Permission.objects.get(
        content_type__app_label="catches", codename="change_catch"
    )
    delete_perm = Permission.objects.get(
        content_type__app_label="catches", codename="delete_catch"
    )

    # Add and change permissions return False regardless of user role or explicit permission
    for user in (operator, staff_user, non_staff):
        request = factory.get("/")
        request.user = user
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False

    # Staff with explicit add and change permissions is still denied
    staff_with_all = create_test_user(clerk_user_id="catch_admin_staff_all")
    staff_with_all.is_staff = True
    staff_with_all.save(update_fields=["is_staff"])
    cast(_UserWithPermissions, staff_with_all).user_permissions.add(
        add_perm, change_perm
    )
    staff_with_all = User.objects.get(pk=staff_with_all.pk)
    request_staff_with_all = factory.get("/")
    request_staff_with_all.user = staff_with_all
    assert model_admin.has_add_permission(request_staff_with_all) is False
    assert model_admin.has_change_permission(request_staff_with_all) is False

    # Anonymous user has no delete, view, add, or change permission
    request_anon = factory.get("/")
    request_anon.user = AnonymousUser()
    assert model_admin.has_add_permission(request_anon) is False
    assert model_admin.has_change_permission(request_anon) is False
    assert model_admin.has_delete_permission(request_anon) is False
    assert model_admin.has_view_permission(request_anon) is False

    # Non-staff has no delete or view permission
    request_non_staff = factory.get("/")
    request_non_staff.user = non_staff
    assert model_admin.has_delete_permission(request_non_staff) is False
    assert model_admin.has_view_permission(request_non_staff) is False

    # Staff without delete permission
    request_staff = factory.get("/")
    request_staff.user = staff_user
    assert model_admin.has_delete_permission(request_staff) is False

    # Explicit view_catch permits inspection but never the correction control.
    view_perm = Permission.objects.get(
        content_type__app_label="catches", codename="view_catch"
    )
    staff_with_view_only = create_test_user(clerk_user_id="catch_admin_staff_view_only")
    staff_with_view_only.is_staff = True
    staff_with_view_only.save(update_fields=["is_staff"])
    cast(_UserWithPermissions, staff_with_view_only).user_permissions.add(view_perm)
    staff_with_view_only = User.objects.get(pk=staff_with_view_only.pk)
    request_staff_view_only = factory.get("/")
    request_staff_view_only.user = staff_with_view_only
    assert model_admin.has_delete_permission(request_staff_view_only) is False
    assert model_admin.has_view_permission(request_staff_view_only) is True

    # Staff with delete permission has both delete and view
    cast(_UserWithPermissions, staff_user).user_permissions.add(delete_perm)
    staff_user = User.objects.get(pk=staff_user.pk)
    request_staff_with_perm = factory.get("/")
    request_staff_with_perm.user = staff_user
    assert model_admin.has_delete_permission(request_staff_with_perm) is True
    assert model_admin.has_view_permission(request_staff_with_perm) is True

    # Superuser has delete and view
    request_op = factory.get("/")
    request_op.user = operator
    assert model_admin.has_delete_permission(request_op) is True
    assert model_admin.has_view_permission(request_op) is True

    # Bulk delete queryset raises PermissionDenied
    with pytest.raises(PermissionDenied, match="Bulk catch deletion is not permitted."):
        model_admin.delete_queryset(request_op, Catch.objects.none())


@pytest.mark.django_db
def test_catch_admin_unauthorized_access_redirects() -> None:
    """Unauthenticated and non-staff requests cannot access catch admin views."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)
    client = Client()

    urls = _admin_urls(catch)
    tested_urls = (urls.changelist, urls.add, urls.change, urls.delete)

    # Anonymous user is redirected to login for both GET and POST
    for url in tested_urls:
        resp_get = client.get(url)
        assert resp_get.status_code == 302
        assert "/admin/login/" in resp_get.headers.get("Location", "")

        resp_post = client.post(url, {})
        assert resp_post.status_code == 302
        assert "/admin/login/" in resp_post.headers.get("Location", "")

    # Authenticated non-staff player is rejected (302 redirecting to login or 403)
    player = create_test_user(clerk_user_id="unauthorized_player")
    client.force_login(player)
    for url in tested_urls:
        resp_get = client.get(url)
        assert resp_get.status_code in (302, 403)
        if resp_get.status_code == 302:
            assert "/admin/login/" in resp_get.headers.get("Location", "")

        resp_post = client.post(url, {})
        assert resp_post.status_code in (302, 403)
        if resp_post.status_code == 302:
            assert "/admin/login/" in resp_post.headers.get("Location", "")


@pytest.mark.django_db
def test_catch_admin_add_view_forbidden_for_all_users() -> None:
    """Add view cannot be reached and returns 403 even for operators and staff."""
    add_url = reverse("admin:catches_catch_add")
    initial_catch_count = Catch.objects.count()

    # Superuser cannot reach add view via GET or POST
    operator = User.objects.create_superuser("catch_add_op", password="pw")
    client = Client()
    client.force_login(operator)

    assert client.get(add_url).status_code == 403
    assert client.post(add_url, {"catcher_user": operator.pk}).status_code == 403

    # Staff with explicit add_catch permission is still forbidden
    staff_user = create_test_user(clerk_user_id="catch_add_staff")
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])
    add_perm = Permission.objects.get(
        content_type__app_label="catches", codename="add_catch"
    )
    cast(_UserWithPermissions, staff_user).user_permissions.add(add_perm)

    client.force_login(staff_user)
    assert client.get(add_url).status_code == 403
    assert client.post(add_url, {"catcher_user": staff_user.pk}).status_code == 403

    # Staff with delete_catch permission is also forbidden from adding
    delete_perm = Permission.objects.get(
        content_type__app_label="catches", codename="delete_catch"
    )
    cast(_UserWithPermissions, staff_user).user_permissions.add(delete_perm)
    client.force_login(staff_user)
    assert client.get(add_url).status_code == 403
    assert client.post(add_url, {"catcher_user": staff_user.pk}).status_code == 403

    assert Catch.objects.count() == initial_catch_count


@pytest.mark.django_db
def test_catch_admin_staff_without_delete_permission_is_forbidden() -> None:
    """Staff user without catches.delete_catch cannot reach delete view or trigger deletion."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)
    staff_user = create_test_user(clerk_user_id="staff_no_delete")
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])

    client = Client()
    client.force_login(staff_user)
    urls = _admin_urls(catch)

    with patch(
        "catches.admin.remove_catch_as_operator", wraps=remove_catch_as_operator
    ) as spy_remove:
        assert client.get(urls.delete).status_code == 403
        assert client.post(urls.delete, {"post": "yes"}).status_code == 403
        spy_remove.assert_not_called()

    assert Catch.objects.filter(pk=catch.pk).exists()
    assert not LogEntry.objects.filter(
        content_type__app_label="catches", object_id=str(catch.pk)
    ).exists()

    # Staff user with only catches.view_catch may inspect but cannot delete.
    view_perm = Permission.objects.get(
        content_type__app_label="catches", codename="view_catch"
    )
    cast(_UserWithPermissions, staff_user).user_permissions.add(view_perm)
    staff_user = User.objects.get(pk=staff_user.pk)
    client.force_login(staff_user)
    assert client.get(urls.changelist).status_code == 200
    assert client.get(urls.change).status_code == 200
    assert client.get(urls.delete).status_code == 403


@pytest.mark.django_db
def test_catch_admin_renders_safe_fields_and_conceals_secrets() -> None:
    """Change and changelist views render safe fields as read-only with zero secret leaks."""
    scenario = create_catch_scenario()
    create_credential(activation=scenario.activation, token=TOKEN_A)
    catch = create_catch(scenario=scenario)
    urls = _admin_urls(catch)

    operator = User.objects.create_superuser("catch_safe_fields_op", password="pw")
    client = Client()
    client.force_login(operator)

    # 1. Changelist view renders safe fields and conceals secrets
    list_response = client.get(urls.changelist)
    assert list_response.status_code == 200
    assert _listed_ids(list_response) == {catch.pk}
    assert b'name="action"' not in list_response.content
    _assert_token_absent(TOKEN_A, list_response)
    _assert_token_absent(PAYLOAD_A, list_response)

    # 2. Change detail view renders safe fields as read-only
    change_response = client.get(urls.change)
    assert change_response.status_code == 200
    change_content = change_response.content.decode()

    # Verify all safe fields are present in the change view
    assert str(catch.pk) in change_content
    assert str(catch.catcher_user) in change_content
    assert str(catch.fursuit) in change_content
    assert str(catch.convention) in change_content
    assert str(catch.activation) in change_content
    assert str(catch.catch_session) in change_content

    for field_name in (
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
        "caught_at",
    ):
        assert f"field-{field_name}" in change_content

    # Form inputs for editing are NOT rendered (change view is read-only)
    for field_name in (
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
        "caught_at",
    ):
        assert f'name="{field_name}"'.encode() not in change_response.content
    for save_btn in ("_save", "_continue", "_addanother"):
        assert f'name="{save_btn}"'.encode() not in change_response.content

    # Zero secrets / token material present in HTML
    _assert_token_absent(TOKEN_A, change_response)
    _assert_token_absent(PAYLOAD_A, change_response)
    _assert_token_absent(TOKEN_B, change_response)
    _assert_token_absent(PAYLOAD_B, change_response)


@pytest.mark.django_db
def test_catch_admin_operator_deletion_lifecycle_and_log_entry() -> None:
    """Superuser can delete an individual catch through the admin with audit trail."""
    scenario = create_catch_scenario()
    create_credential(activation=scenario.activation, token=TOKEN_A)
    catch = create_catch(scenario=scenario)
    catch_id = catch.pk
    catcher_user_id = catch.catcher_user_id
    fursuit_id = catch.fursuit_id
    convention_id = catch.convention_id
    activation_id = catch.activation_id
    catch_session_id = catch.catch_session_id

    operator = User.objects.create_superuser("catch_lifecycle_op", password="pw")
    client = Client()
    client.force_login(operator)
    urls = _admin_urls(catch)

    # Delete confirmation page renders
    delete_get = client.get(urls.delete)
    assert delete_get.status_code == 200
    assert b"Are you sure you want to delete" in delete_get.content

    # POST delete calls remove_catch_as_operator and deletes catch
    with patch(
        "catches.admin.remove_catch_as_operator", wraps=remove_catch_as_operator
    ) as spy_remove:
        delete_post = client.post(urls.delete, {"post": "yes"}, follow=True)
        assert delete_post.status_code == 200
        spy_remove.assert_called_once_with(catch_id=catch_id)

    assert not Catch.objects.filter(pk=catch_id).exists()

    # Verify referential integrity: related upstream models remain completely intact
    assert User.objects.filter(pk=catcher_user_id).exists()
    assert Fursuit.objects.filter(pk=fursuit_id).exists()
    assert Convention.objects.filter(pk=convention_id).exists()
    assert FursuitActivation.objects.filter(pk=activation_id).exists()
    assert FursuitCatchSession.objects.filter(pk=catch_session_id).exists()

    # Verify safe LogEntry was recorded in Django admin history
    entries = list(
        LogEntry.objects.filter(
            content_type__app_label="catches",
            object_id=str(catch_id),
        )
    )
    assert len(entries) == 1
    log_entry = entries[0]
    assert _log_entry_action_flag(log_entry) == DELETION
    assert _log_entry_action_flag(log_entry) == 3
    assert _log_entry_user_id(log_entry) == operator.pk
    entry_repr = _log_entry_repr(log_entry)
    entry_msg = _log_entry_message(log_entry)
    assert entry_repr == str(catch)
    assert str(catch_id) in entry_repr
    assert str(catcher_user_id) in entry_repr
    assert str(fursuit_id) in entry_repr
    assert str(convention_id) in entry_repr
    _assert_token_absent(TOKEN_A, entry_repr, entry_msg)
    _assert_token_absent(PAYLOAD_A, entry_repr, entry_msg)


@pytest.mark.django_db
def test_catch_admin_authorized_staff_deletion_lifecycle_and_log_entry() -> None:
    """Authorized non-superuser staff with delete_catch can access views and delete."""
    scenario = create_catch_scenario()
    create_credential(activation=scenario.activation, token=TOKEN_A)
    catch = create_catch(scenario=scenario)
    catch_id = catch.pk
    catcher_user_id = catch.catcher_user_id
    fursuit_id = catch.fursuit_id
    convention_id = catch.convention_id
    activation_id = catch.activation_id
    catch_session_id = catch.catch_session_id

    staff_user = create_test_user(clerk_user_id="authorized_staff_delete")
    staff_user.is_staff = True
    staff_user.save(update_fields=["is_staff"])
    delete_perm = Permission.objects.get(
        content_type__app_label="catches", codename="delete_catch"
    )
    cast(_UserWithPermissions, staff_user).user_permissions.add(delete_perm)

    client = Client()
    client.force_login(staff_user)
    urls = _admin_urls(catch)

    # Authorized staff can view changelist and change views
    assert client.get(urls.changelist).status_code == 200
    assert client.get(urls.change).status_code == 200

    # Authorized staff cannot add
    assert client.get(urls.add).status_code == 403

    # Authorized staff can view delete confirmation page
    delete_get = client.get(urls.delete)
    assert delete_get.status_code == 200
    assert b"Are you sure you want to delete" in delete_get.content

    # Authorized staff POST delete removes catch via operator seam
    with patch(
        "catches.admin.remove_catch_as_operator", wraps=remove_catch_as_operator
    ) as spy_remove:
        delete_post = client.post(urls.delete, {"post": "yes"}, follow=True)
        assert delete_post.status_code == 200
        spy_remove.assert_called_once_with(catch_id=catch_id)

    assert not Catch.objects.filter(pk=catch_id).exists()
    assert User.objects.filter(pk=catcher_user_id).exists()
    assert Fursuit.objects.filter(pk=fursuit_id).exists()
    assert Convention.objects.filter(pk=convention_id).exists()
    assert FursuitActivation.objects.filter(pk=activation_id).exists()
    assert FursuitCatchSession.objects.filter(pk=catch_session_id).exists()

    # LogEntry attributed to the staff user
    entries = list(
        LogEntry.objects.filter(
            content_type__app_label="catches",
            object_id=str(catch_id),
        )
    )
    assert len(entries) == 1
    log_entry = entries[0]
    assert _log_entry_action_flag(log_entry) == DELETION
    assert _log_entry_action_flag(log_entry) == 3
    assert _log_entry_user_id(log_entry) == staff_user.pk
    entry_repr = _log_entry_repr(log_entry)
    entry_msg = _log_entry_message(log_entry)
    assert str(catch_id) in entry_repr
    _assert_token_absent(TOKEN_A, entry_repr, entry_msg)
    _assert_token_absent(PAYLOAD_A, entry_repr, entry_msg)


@pytest.mark.django_db
def test_authorized_admin_correction_updates_authenticated_player_history() -> None:
    """Issue #193: admin correction removes only the erroneous history entry."""
    player = create_test_user(clerk_user_id="admin_correction_history_player")
    erroneous = create_history_catch(catcher_user=player, ordinal=193)
    unaffected = create_history_catch(catcher_user=player, ordinal=194)
    erroneous_catch_id = erroneous.catch.pk
    unaffected_catch_id = unaffected.catch.pk

    activation = FursuitActivation.objects.get(pk=erroneous.catch.activation_id)
    activation_state = {
        "id": activation.pk,
        "fursuit_id": activation.fursuit_id,
        "convention_id": activation.convention_id,
        "is_active": activation.is_active,
        "activated_at": activation.activated_at,
        "deactivated_at": activation.deactivated_at,
    }
    catch_session = FursuitCatchSession.objects.get(pk=erroneous.catch.catch_session_id)
    catch_session_state = {
        "id": catch_session.pk,
        "activation_id": catch_session.activation_id,
        "started_at": catch_session.started_at,
        "expires_at": catch_session.expires_at,
        "ended_at": catch_session.ended_at,
        "end_reason": catch_session.end_reason,
    }
    assert activation_state["is_active"] is True
    assert activation_state["deactivated_at"] is None
    assert catch_session_state["ended_at"] is None
    assert catch_session_state["end_reason"] is None

    history_client = force_authenticated_client(user=player)
    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        before_response = history_client.get("/api/catches/")

    assert before_response.status_code == 200
    before_data = cast(dict[str, object], before_response.json())
    assert before_data["catch_count"] == 2
    assert _catch_history_result_ids(before_data) == {
        erroneous_catch_id,
        unaffected_catch_id,
    }

    operator = create_test_user(clerk_user_id="admin_correction_history_operator")
    operator.is_staff = True
    operator.save(update_fields=["is_staff"])
    assert not cast(_UserWithPermissions, operator).is_superuser
    delete_permission = Permission.objects.get(
        content_type__app_label="catches", codename="delete_catch"
    )
    cast(_UserWithPermissions, operator).user_permissions.add(delete_permission)

    admin_client = Client()
    admin_client.force_login(operator)
    admin_urls = _admin_urls(erroneous.catch)
    delete_confirmation = admin_client.get(admin_urls.delete)
    assert delete_confirmation.status_code == 200
    assert b"Are you sure you want to delete" in delete_confirmation.content
    delete_response = admin_client.post(admin_urls.delete, {"post": "yes"}, follow=True)
    assert delete_response.status_code == 200

    assert not Catch.objects.filter(pk=erroneous_catch_id).exists()

    activation.refresh_from_db()
    assert {
        "id": activation.pk,
        "fursuit_id": activation.fursuit_id,
        "convention_id": activation.convention_id,
        "is_active": activation.is_active,
        "activated_at": activation.activated_at,
        "deactivated_at": activation.deactivated_at,
    } == activation_state
    catch_session.refresh_from_db()
    assert {
        "id": catch_session.pk,
        "activation_id": catch_session.activation_id,
        "started_at": catch_session.started_at,
        "expires_at": catch_session.expires_at,
        "ended_at": catch_session.ended_at,
        "end_reason": catch_session.end_reason,
    } == catch_session_state

    with patch(
        "catches.serializers.media_service.read_image_url",
        return_value="/api/media/images/fake-read",
    ):
        after_response = history_client.get("/api/catches/")

    assert after_response.status_code == 200
    after_data = cast(dict[str, object], after_response.json())
    assert after_data["catch_count"] == 1
    assert erroneous_catch_id not in _catch_history_result_ids(after_data)
    assert _catch_history_result_ids(after_data) == {unaffected_catch_id}


@pytest.mark.django_db
def test_catch_admin_search_and_credential_sanitization() -> None:
    """Search works for valid query terms and sanitizes raw credential tokens/payloads."""
    scenario_a = create_catch_scenario(
        catcher_clerk_user_id="catcher_search_alpha",
        target_owner_clerk_user_id="target_search_alpha",
    )
    scenario_a.fursuit.name = "AlphaFox"
    scenario_a.fursuit.save(update_fields=["name"])
    scenario_a.convention.name = "AlphaCon"
    scenario_a.convention.save(update_fields=["name"])
    catch_a = create_catch(scenario=scenario_a)

    scenario_b = create_catch_scenario(
        catcher_clerk_user_id="catcher_search_beta",
        target_owner_clerk_user_id="target_search_beta",
    )
    scenario_b.fursuit.name = "BetaWolf"
    scenario_b.fursuit.save(update_fields=["name"])
    scenario_b.convention.name = "BetaCon"
    scenario_b.convention.save(update_fields=["name"])
    catch_b = create_catch(scenario=scenario_b)

    operator = User.objects.create_superuser("catch_search_op", password="pw")
    client = Client()
    client.force_login(operator)

    urls = _admin_urls(catch_a)

    # 1. Valid searches return matching rows
    # Search by exact catch ID
    resp = client.get(urls.changelist, {"q": str(catch_a.pk)})
    assert resp.status_code == 200
    assert _listed_ids(resp) == {catch_a.pk}
    assert catch_b.pk not in _listed_ids(resp)

    # Search by fursuit name
    resp = client.get(urls.changelist, {"q": "AlphaFox"})
    assert resp.status_code == 200
    assert _listed_ids(resp) == {catch_a.pk}
    assert catch_b.pk not in _listed_ids(resp)

    # Search by fursuit tailtag_id
    resp = client.get(urls.changelist, {"q": str(scenario_a.fursuit.tailtag_id)})
    assert resp.status_code == 200
    assert _listed_ids(resp) == {catch_a.pk}
    assert catch_b.pk not in _listed_ids(resp)

    # Search by catcher clerk_user_id
    resp = client.get(urls.changelist, {"q": scenario_a.catcher_user.clerk_user_id})
    assert resp.status_code == 200
    assert _listed_ids(resp) == {catch_a.pk}
    assert catch_b.pk not in _listed_ids(resp)

    # Search by convention name
    resp = client.get(urls.changelist, {"q": "AlphaCon"})
    assert resp.status_code == 200
    assert catch_a.pk in _listed_ids(resp)
    assert catch_b.pk not in _listed_ids(resp)

    # 2. Sensitive searches (raw tokens, payloads, adversarial forms) are sanitized
    sensitive_queries = (
        TOKEN_A,
        PAYLOAD_A,
        TOKEN_B,
        PAYLOAD_B,
        f"prefix-{TOKEN_A}-suffix",
        f'"{TOKEN_A}"',
        f"'{TOKEN_A}'",
        f'  "{TOKEN_A}"  ',
        f"prefix-{PAYLOAD_A}-suffix",
        f'"{PAYLOAD_A}"',
        f"'{PAYLOAD_A}'",
        f"  '{PAYLOAD_A}'  ",
        f"{{{TOKEN_A}}}",
        f"{{{PAYLOAD_A}}}",
    )

    for sensitive_query in sensitive_queries:
        # 2a. Server detects sensitive query and immediately redirects (302) to sanitized URL
        redirect_resp = client.get(urls.changelist, {"q": sensitive_query})
        assert redirect_resp.status_code == 302
        expected_location = f"{urls.changelist}?q={REDACTED_CREDENTIAL_SEARCH_QUERY}"
        assert redirect_resp.headers["Location"] == expected_location
        _assert_token_absent(TOKEN_A, redirect_resp.headers["Location"])
        _assert_token_absent(TOKEN_B, redirect_resp.headers["Location"])
        _assert_token_absent(PAYLOAD_A, redirect_resp.headers["Location"])
        _assert_token_absent(PAYLOAD_B, redirect_resp.headers["Location"])

        # 2b. Browser following redirect receives sanitized changelist with zero matches
        followed_resp = client.get(urls.changelist, {"q": sensitive_query}, follow=True)
        assert followed_resp.status_code == 200
        assert followed_resp.redirect_chain == [(expected_location, 302)]
        _assert_sensitive_search_request_is_sanitized(followed_resp)
        _assert_token_absent(TOKEN_A, followed_resp)
        _assert_token_absent(TOKEN_B, followed_resp)
        _assert_token_absent(PAYLOAD_A, followed_resp)
        _assert_token_absent(PAYLOAD_B, followed_resp)
        assert _listed_ids(followed_resp) == set()


@pytest.mark.django_db
def test_catch_admin_changelist_template_renders_client_search_guard() -> None:
    """Catch changelist template includes client-side interception script against credential search."""
    operator = User.objects.create_superuser("catch_template_op", password="pw")
    client = Client()
    client.force_login(operator)

    changelist_url = reverse("admin:catches_catch_changelist")
    resp = client.get(changelist_url)
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert 'id="changelist-search"' in content
    assert "event.preventDefault()" in content
    assert "Sensitive catch credential tokens cannot be searched" in content
    assert REDACTED_CREDENTIAL_SEARCH_QUERY in content


@pytest.mark.django_db
def test_catch_admin_multi_parameter_credential_sanitization_and_drop() -> None:
    """Multi-parameter requests containing credentials drop non-q parameters and sanitize q."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)
    operator = User.objects.create_superuser("catch_multi_param_op", password="pw")
    client = Client()
    client.force_login(operator)

    urls = _admin_urls(catch)

    # 1. Sensitive token in q and extra parameter foo: foo is dropped, q is redacted
    resp = client.get(urls.changelist, {"q": TOKEN_A, "foo": TOKEN_A})
    assert resp.status_code == 302
    expected_location = f"{urls.changelist}?q={REDACTED_CREDENTIAL_SEARCH_QUERY}"
    assert resp.headers["Location"] == expected_location
    _assert_token_absent(TOKEN_A, resp.headers["Location"])
    assert "foo=" not in resp.headers["Location"]

    # Following redirect returns 200 with zero matches and no token leak
    followed = client.get(urls.changelist, {"q": TOKEN_A, "foo": TOKEN_A}, follow=True)
    assert followed.status_code == 200
    assert followed.redirect_chain == [(expected_location, 302)]
    _assert_token_absent(TOKEN_A, followed)
    assert _listed_ids(followed) == set()

    # 2. Sensitive token in q and foo, with a valid filter preserved
    resp = client.get(
        urls.changelist,
        {"q": TOKEN_A, "foo": TOKEN_A, "convention": scenario.convention.pk},
    )
    assert resp.status_code == 302
    expected_location_with_conv = f"{urls.changelist}?q={REDACTED_CREDENTIAL_SEARCH_QUERY}&convention={scenario.convention.pk}"
    assert resp.headers["Location"] == expected_location_with_conv
    _assert_token_absent(TOKEN_A, resp.headers["Location"])
    assert "foo=" not in resp.headers["Location"]

    # 3. Sensitive token only in non-q parameter (e.g. ?foo=<token>)
    resp = client.get(urls.changelist, {"foo": TOKEN_A})
    assert resp.status_code == 302
    assert resp.headers["Location"] == urls.changelist
    _assert_token_absent(TOKEN_A, resp.headers["Location"])

    # 4. Sensitive token in parameter along with a safe parameter
    resp = client.get(
        urls.changelist, {"safe_param": "valid", "sensitive_param": TOKEN_A}
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"{urls.changelist}?safe_param=valid"
    _assert_token_absent(TOKEN_A, resp.headers["Location"])
    assert "sensitive_param=" not in resp.headers["Location"]

    # 5. Sensitive token in parameter key itself (e.g. ?<token>=bar)
    resp = client.get(urls.changelist, {TOKEN_A: "bar"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == urls.changelist
    _assert_token_absent(TOKEN_A, resp.headers["Location"])

    # 6. Valid q with sensitive extra parameter: q preserved, extra dropped
    scenario.fursuit.name = "MultiFox"
    scenario.fursuit.save(update_fields=["name"])
    resp = client.get(urls.changelist, {"q": "MultiFox", "leak": TOKEN_A})
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"{urls.changelist}?q=MultiFox"
    _assert_token_absent(TOKEN_A, resp.headers["Location"])
    assert "leak=" not in resp.headers["Location"]


def _catch_staff(*permissions: tuple[str, str]) -> User:
    user = create_test_user()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    cast(_UserWithPermissions, user).user_permissions.add(
        *[
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
            for app_label, codename in permissions
        ]
    )
    return User.objects.get(pk=user.pk)


def _assert_catch_event(
    user: User,
    catch_id: int,
    actor_class: OperatorActorClass,
    outcome: OperatorAuditOutcome,
) -> None:
    events = list(
        OperatorAuditEvent.objects.filter(affected_record_id=catch_id, actor=user)
    )
    assert len(events) == 1
    event = events[0]
    assert (
        event.action,
        event.actor_class,
        event.affected_record_type,
        event.outcome,
    ) == (
        OperatorAction.REMOVE_CATCH,
        actor_class,
        OperatorTargetType.CATCH,
        outcome,
    )


@pytest.mark.django_db
def test_catch_removal_role_matrix_preserves_delete_catch_as_the_exact_correction_authority() -> (
    None
):
    """AC-1/2/4/9: only the documented Catch deletion authority removes one record."""
    unrelated = _catch_staff(("conventions", "revoke_catch_credential"))
    cases = (
        (
            _catch_staff(),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            unrelated,
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _catch_staff(("catches", "change_catch")),
            False,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorAuditOutcome.DENIED,
        ),
        (
            _catch_staff(("catches", "delete_catch")),
            True,
            OperatorActorClass.OPERATOR,
            OperatorAuditOutcome.SUCCEEDED,
        ),
        (
            User.objects.create_superuser("catch_emergency", password="pw"),
            True,
            OperatorActorClass.EMERGENCY_SUPERUSER,
            OperatorAuditOutcome.SUCCEEDED,
        ),
    )
    player = create_test_user()
    player_target = create_catch(scenario=create_catch_scenario())
    player_url = _admin_urls(player_target).delete
    player_client = Client()
    player_client.force_login(player)
    player_response = player_client.post(player_url, {"post": "yes"})
    assert player_response.status_code == 302
    assert player_response["Location"] == f"/admin/login/?next={player_url}"
    assert Catch.objects.filter(pk=player_target.pk).exists()
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=player_target.pk
    ).exists()

    for user, permitted, actor_class, outcome in cases:
        catch = create_catch(scenario=create_catch_scenario())
        client = Client()
        client.force_login(user)
        response = client.post(_admin_urls(catch).delete, {"post": "yes"})
        assert response.status_code == (302 if permitted else 403)
        assert Catch.objects.filter(pk=catch.pk).exists() is (not permitted)
        _assert_catch_event(user, catch.pk, actor_class, outcome)


@pytest.mark.django_db
def test_catch_view_permission_is_read_only_and_catch_add_edit_bulk_paths_remain_closed() -> (
    None
):
    """AC-3/4/9: a viewer can inspect but cannot create, edit, bulk-award, or delete."""
    catch = create_catch(scenario=create_catch_scenario())
    viewer = _catch_staff(("catches", "view_catch"))
    client = Client()
    client.force_login(viewer)
    urls = _admin_urls(catch)
    assert client.get(urls.changelist).status_code == 200
    assert client.get(urls.change).status_code == 200
    assert OperatorAuditEvent.objects.count() == 0
    assert client.post(urls.delete, {"post": "yes"}).status_code == 403
    assert client.post(urls.add, {}).status_code == 403
    assert (
        client.post(
            urls.changelist, {"action": "delete_selected", "_selected_action": catch.pk}
        ).status_code
        == 403
    )
    assert Catch.objects.filter(pk=catch.pk).exists()
    _assert_catch_event(
        viewer,
        catch.pk,
        OperatorActorClass.UNAUTHORIZED_ACTOR,
        OperatorAuditOutcome.DENIED,
    )

    operator = _catch_staff(("catches", "delete_catch"))
    client.force_login(operator)
    assert client.get(urls.changelist).status_code == 200
    assert client.get(urls.change).status_code == 200
    assert OperatorAuditEvent.objects.filter(affected_record_id=catch.pk).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("after_service", [False, True])
def test_catch_removal_failure_rolls_back_and_records_only_failed(
    after_service: bool,
) -> None:
    """AC-4/5: failures before or after the removal service cannot commit success."""
    catch = create_catch(scenario=create_catch_scenario())
    operator = _catch_staff(("catches", "delete_catch"))
    client = Client()
    client.force_login(operator)
    failure_target = (
        "catches.admin.CatchAdmin.log_deletions"
        if after_service
        else "catches.admin.remove_catch_as_operator"
    )
    with (
        patch(failure_target, side_effect=RuntimeError("forced catch failure")),
        pytest.raises(RuntimeError, match="forced catch failure"),
    ):
        client.post(_admin_urls(catch).delete, {"post": "yes"})
    assert Catch.objects.filter(pk=catch.pk).exists()
    _assert_catch_event(
        operator,
        catch.pk,
        OperatorActorClass.OPERATOR,
        OperatorAuditOutcome.FAILED,
    )
    assert not OperatorAuditEvent.objects.filter(
        affected_record_id=catch.pk, outcome=OperatorAuditOutcome.SUCCEEDED
    ).exists()
