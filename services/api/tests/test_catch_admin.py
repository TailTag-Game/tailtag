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

from accounts.models import User
from catches.admin import REDACTED_CREDENTIAL_SEARCH_QUERY, CatchAdmin
from catches.models import Catch
from catches.services import remove_catch_as_operator
from conventions.models import (
    Convention,
    FursuitActivation,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from tests.authentication_support import create_test_user
from tests.catch_credential_test_support import (
    PAYLOAD_A,
    PAYLOAD_B,
    TOKEN_A,
    TOKEN_B,
    create_credential,
)
from tests.catch_test_support import (
    create_catch,
    create_catch_scenario,
)


class _PermissionManager(Protocol):
    def add(self, *permissions: Permission) -> None: ...


class _UserWithPermissions(Protocol):
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


@pytest.mark.django_db(transaction=True)
def test_remove_catch_as_operator_atomically_deletes_catch_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Operator catch removal deletes the catch, preserves related models, and logs safely."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)
    catch_id = catch.pk
    catcher_user_id = catch.catcher_user_id
    fursuit_id = catch.fursuit_id
    convention_id = catch.convention_id
    activation_id = catch.activation_id
    catch_session_id = catch.catch_session_id

    with caplog.at_level(logging.INFO):
        remove_catch_as_operator(catch_id=catch_id)

    assert not Catch.objects.filter(pk=catch_id).exists()
    assert User.objects.filter(pk=catcher_user_id).exists()
    assert Fursuit.objects.filter(pk=fursuit_id).exists()
    assert Convention.objects.filter(pk=convention_id).exists()
    assert FursuitActivation.objects.filter(pk=activation_id).exists()
    assert FursuitCatchSession.objects.filter(pk=catch_session_id).exists()

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

    # Staff with only view_catch permission is denied both delete and view
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
    assert model_admin.has_view_permission(request_staff_view_only) is False

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

    # Staff user with only catches.view_catch is also forbidden from changelist, change, and delete
    view_perm = Permission.objects.get(
        content_type__app_label="catches", codename="view_catch"
    )
    cast(_UserWithPermissions, staff_user).user_permissions.add(view_perm)
    staff_user = User.objects.get(pk=staff_user.pk)
    client.force_login(staff_user)
    assert client.get(urls.changelist).status_code == 403
    assert client.get(urls.change).status_code == 403
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
        sensitive_resp = client.get(urls.changelist, {"q": sensitive_query})
        assert sensitive_resp.status_code == 200
        _assert_sensitive_search_request_is_sanitized(sensitive_resp)
        _assert_token_absent(TOKEN_A, sensitive_resp)
        _assert_token_absent(TOKEN_B, sensitive_resp)
        _assert_token_absent(PAYLOAD_A, sensitive_resp)
        _assert_token_absent(PAYLOAD_B, sensitive_resp)
        assert _listed_ids(sensitive_resp) == set()
