"""Acceptance tests for the bounded #243 managed-login replacement."""

from __future__ import annotations

import getpass
import importlib
import logging
import os
import sys
import warnings
from collections.abc import Callable
from io import StringIO
from typing import Any, cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError
from django.db import DatabaseError, connection
from django.db.models.signals import post_save
from django.test import Client

from accounts.models import User
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)

COMMAND = "replace_staging_managed_operator"
CONFIRMATION = "replace Railway Staging managed operator"
DEPLOYMENT_ID = "cbe83780-0256-49c2-b026-34709ddb69b0"
SOURCE_SHA = "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a"
EXPECTED_IDENTITY = {
    "environment": "staging",
    "source_sha": SOURCE_SHA,
    "deployment_id": DEPLOYMENT_ID,
}
RAILWAY_SELECTORS = {
    "RAILWAY_PROJECT_ID": "85324de4-be6a-49c3-a3f9-6cac13877849",
    "RAILWAY_ENVIRONMENT_ID": "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e",
    "RAILWAY_SERVICE_ID": "2247da27-97df-4d5d-b1dc-d21eeb7901d9",
}
REPLACEMENT_SELECTORS = {
    "RAILWAY_PROJECT_ID": "a1111111-1111-4111-8111-111111111111",
    "RAILWAY_ENVIRONMENT_ID": "c3333333-3333-4333-8333-333333333333",
    "RAILWAY_SERVICE_ID": "d4444444-4444-4444-8444-444444444444",
}


def pin_replacement_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind disposable selectors to the same code-owned replacement contract."""
    from config import replacement_target_binding as binding

    monkeypatch.setattr(
        binding,
        "_EXPECTED_DIGESTS",
        {
            **binding._EXPECTED_DIGESTS,  # pyright: ignore[reportPrivateUsage]
            "staging-api": binding.fingerprint_tuple(
                "staging-api",
                REPLACEMENT_SELECTORS["RAILWAY_PROJECT_ID"],
                REPLACEMENT_SELECTORS["RAILWAY_ENVIRONMENT_ID"],
                REPLACEMENT_SELECTORS["RAILWAY_SERVICE_ID"],
            ),
        },
    )


MANAGED_GROUP = "TailTag Field Beta Operators"
LIMITED_GROUP = "TailTag #243 Validation Operator"
OLD_IDENTIFIER = "operator_staging_205"
NEW_IDENTIFIER = "staging_managed_recovery_243"
OLD_PASSWORD = "old-managed-operator-password-2026"
NEW_PASSWORD = "new-managed-operator-password-2026"
LIMITED_PASSWORD = "limited-operator-password-2026"
MANAGED_PERMISSIONS = frozenset(
    {
        "catches.delete_catch",
        "catches.view_catch",
        "conventions.revoke_catch_credential",
        "conventions.view_fursuitcatchcredential",
        "conventions.terminate_catch_session",
        "conventions.view_fursuitcatchsession",
        "conventions.deactivate_fursuit_activation",
        "conventions.view_fursuitactivation",
        "conventions.remove_convention_enrollment",
        "conventions.view_conventionenrollment",
        "conventions.set_convention_playability",
        "conventions.view_convention",
        "profiles.set_profile_enabled",
        "profiles.view_playerprofile",
        "fursuits.set_fursuit_enabled",
        "fursuits.view_fursuit",
    }
)
LIMITED_PERMISSIONS = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)


class Tty(StringIO):
    def isatty(self) -> bool:
        return True


class NonTty(StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture(autouse=True)
def safe_query_boundary(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = False
    monkeypatch.setattr(connection, "force_debug_cursor", False)


def permission_name(permission: Permission) -> str:
    return f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]


def permissions(names: frozenset[str]) -> list[Permission]:
    found = [
        permission
        for permission in Permission.objects.select_related("content_type")
        if permission_name(permission) in names
    ]
    assert {permission_name(permission) for permission in found} == names
    return found


def local_staff(identifier: str, password: str) -> User:
    user = User(clerk_user_id=identifier, is_staff=True, is_superuser=False)
    user.set_password(password)
    user.save()
    return user


def seed_roles() -> tuple[User, User, Group, Group]:
    managed_group = Group.objects.create(name=MANAGED_GROUP)
    managed_group.permissions.set(permissions(MANAGED_PERMISSIONS))  # pyright: ignore[reportUnknownMemberType]
    old = local_staff(OLD_IDENTIFIER, OLD_PASSWORD)
    old.groups.add(managed_group)  # pyright: ignore[reportUnknownMemberType]

    limited_group = Group.objects.create(name=LIMITED_GROUP)
    limited_group.permissions.set(permissions(LIMITED_PERMISSIONS))  # pyright: ignore[reportUnknownMemberType]
    limited = local_staff("validation_operator_243", LIMITED_PASSWORD)
    limited.groups.add(limited_group)  # pyright: ignore[reportUnknownMemberType]
    return old, limited, managed_group, limited_group


def state(user: User) -> tuple[object, ...]:
    user.refresh_from_db()
    return (
        user.pk,
        user.clerk_user_id,
        user.is_staff,
        cast(bool, user.is_superuser),  # pyright: ignore[reportUnknownMemberType]
        cast(str, user.password),  # pyright: ignore[reportUnknownMemberType]
        frozenset(user.groups.values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
        frozenset(user.user_permissions.values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
    )


def group_state(group: Group) -> tuple[frozenset[int], frozenset[int]]:
    return (
        frozenset(User.objects.filter(groups=group).values_list("pk", flat=True)),
        frozenset(group.permissions.values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
    )


def invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    identifier: str = NEW_IDENTIFIER,
    password: str = NEW_PASSWORD,
    password_confirmation: str | None = None,
    confirmation: str = CONFIRMATION,
    environment: str = "staging",
    service: str = "api",
    terminal: StringIO | None = None,
    stderr: StringIO | None = None,
    on_hidden_prompt: Callable[[str], None] | None = None,
    expected_identity: dict[str, str] | None = EXPECTED_IDENTITY,
    live_identity: dict[str, str] | None = EXPECTED_IDENTITY,
    live_identity_provider: Callable[[], dict[str, str] | None] | None = None,
    selector_override: tuple[str, str] | None = None,
) -> tuple[StringIO, StringIO]:
    terminal = terminal if terminal is not None else Tty()
    stderr = stderr if stderr is not None else Tty()
    inputs = iter(
        (
            identifier,
            password,
            password if password_confirmation is None else password_confirmation,
        )
    )

    def hidden_input(prompt: str, **_: object) -> str:
        if on_hidden_prompt is not None:
            on_hidden_prompt(prompt)
        return next(inputs)

    monkeypatch.setattr(sys, "stdin", terminal)
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", lambda _prompt="": confirmation)
    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", service)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", DEPLOYMENT_ID)
    pin_replacement_runtime(monkeypatch)
    for key, value in REPLACEMENT_SELECTORS.items():
        monkeypatch.setenv(key, value)
    if selector_override is not None:
        monkeypatch.setenv(*selector_override)
    from config import build_identity

    monkeypatch.setattr(
        build_identity,
        "get_identity",
        live_identity_provider or (lambda: live_identity),
    )
    environment_before = dict(os.environ)
    try:
        command_module = importlib.import_module(
            f"accounts.management.commands.{COMMAND}"
        )
        command_module.Command().execute(
            expected_identity=expected_identity,
            force_color=False,
            no_color=False,
            skip_checks=True,
            stdout=terminal,
            stderr=stderr,
        )
    finally:
        assert dict(os.environ) == environment_before
    return terminal, stderr


@pytest.mark.parametrize(
    "command_name",
    ("replace_staging_managed_operator", "rotate_staging_managed_password"),
)
@pytest.mark.parametrize(
    ("runtime_selectors", "expected"),
    ((REPLACEMENT_SELECTORS, True), (RAILWAY_SELECTORS, False)),
    ids=("pinned-replacement", "retired-project"),
)
def test_managed_recovery_target_guard_uses_replacement_pin(
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    runtime_selectors: dict[str, str],
    expected: bool,
) -> None:
    """Both managed recovery commands accept only the code-pinned runtime."""
    from config import build_identity

    pin_replacement_runtime(monkeypatch)
    for key, value in runtime_selectors.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "api")
    monkeypatch.setattr(build_identity, "get_identity", lambda: EXPECTED_IDENTITY)
    command = importlib.import_module(f"accounts.management.commands.{command_name}")

    assert command.Command()._target_matches(EXPECTED_IDENTITY) is expected


def assert_sanitized(
    stdout: StringIO,
    stderr: StringIO,
    *,
    error: Exception | None = None,
    caplog: pytest.LogCaptureFixture | None = None,
) -> None:
    rendered = stdout.getvalue() + stderr.getvalue() + (str(error) if error else "")
    if caplog is not None:
        rendered += caplog.text
        rendered += "".join(repr(record.__dict__) for record in caplog.records)
    for secret in (OLD_IDENTIFIER, NEW_IDENTIFIER, OLD_PASSWORD, NEW_PASSWORD):
        assert secret not in rendered
    for permission in MANAGED_PERMISSIONS:
        assert permission not in rendered


@pytest.mark.django_db(transaction=True)
def test_replacement_transfers_exact_managed_role_and_preserves_old_audit_actor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-3/5: one new admin, retired old login, stable audit and limited role."""
    old, limited, managed_group, limited_group = seed_roles()
    old_pk = old.pk
    limited_before = state(limited)
    limited_group_before = group_state(limited_group)
    original_permissions = group_state(managed_group)[1]
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=old,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    caplog.set_level(logging.INFO)

    stdout, stderr = invoke(monkeypatch)

    old.refresh_from_db()
    replacement = User.objects.get(clerk_user_id=NEW_IDENTIFIER)
    assert User.objects.count() == 3
    assert replacement.pk != old_pk
    assert replacement.is_staff is True
    assert cast(bool, replacement.is_superuser) is False  # pyright: ignore[reportUnknownMemberType]
    assert replacement.check_password(NEW_PASSWORD)
    assert replacement.groups.count() == 1  # pyright: ignore[reportUnknownMemberType]
    assert replacement.groups.get().pk == managed_group.pk  # pyright: ignore[reportUnknownMemberType]
    assert replacement.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert set(replacement.get_all_permissions()) == MANAGED_PERMISSIONS
    assert group_state(managed_group) == (
        frozenset({replacement.pk}),
        original_permissions,
    )
    assert old.pk == old_pk and old.clerk_user_id == OLD_IDENTIFIER
    assert old.is_staff is False
    assert cast(bool, old.is_superuser) is False  # pyright: ignore[reportUnknownMemberType]
    assert not old.has_usable_password()
    assert old.groups.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert old.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor.pk == old_pk
    assert state(limited) == limited_before
    assert group_state(limited_group) == limited_group_before
    assert stdout.getvalue().count("POSTCONDITION_PASS") == 1
    assert_sanitized(stdout, stderr, caplog=caplog)


@pytest.mark.django_db(transaction=True)
def test_prepared_marker_follows_unused_identifier_and_precedes_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/4: the one fixed marker binds the attempt before its secret write phase."""
    seed_roles()
    terminal = Tty()
    password_prompt_seen = False

    def inspect_prompt(prompt: str) -> None:
        nonlocal password_prompt_seen
        if prompt == "Password: ":
            password_prompt_seen = True
            assert terminal.getvalue().count("PREPARED") == 1
            assert NEW_IDENTIFIER not in terminal.getvalue()

    invoke(monkeypatch, terminal=terminal, on_hidden_prompt=inspect_prompt)

    assert password_prompt_seen
    assert terminal.getvalue().count("PREPARED") == 1
    assert terminal.getvalue().count("POSTCONDITION_PASS") == 1


@pytest.mark.django_db
@pytest.mark.parametrize("identifier", ("invalid_identifier", NEW_IDENTIFIER))
def test_rejected_identifier_does_not_emit_prepared_marker(
    monkeypatch: pytest.MonkeyPatch, identifier: str
) -> None:
    """AC-2/4: invalid or occupied names cannot create a false attempt binding."""
    seed_roles()
    if identifier == NEW_IDENTIFIER:
        User.objects.create_user(NEW_IDENTIFIER)
    terminal = Tty()
    with pytest.raises(CommandError):
        invoke(monkeypatch, identifier=identifier, terminal=terminal)
    assert "PREPARED" not in terminal.getvalue()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "collision",
    ("ordinary", "managed", "limited", "retired"),
)
def test_existing_identifier_collision_never_adopts_an_account(
    monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    """AC-2/4: every existing User blocks replacement without any write."""
    old, limited, managed_group, limited_group = seed_roles()
    if collision == "ordinary":
        colliding = User.objects.create_user(NEW_IDENTIFIER)
        identifier = NEW_IDENTIFIER
    elif collision == "managed":
        colliding = old
        identifier = OLD_IDENTIFIER
    elif collision == "limited":
        colliding = limited
        identifier = limited.clerk_user_id
    else:
        colliding = User.objects.create_user(NEW_IDENTIFIER)
        colliding.set_unusable_password()
        colliding.save(update_fields={"password"})
        identifier = NEW_IDENTIFIER
    before = (
        state(old),
        state(limited),
        state(colliding),
        group_state(managed_group),
        group_state(limited_group),
        User.objects.count(),
    )
    stdout, stderr = Tty(), Tty()

    with pytest.raises(CommandError) as error:
        invoke(monkeypatch, identifier=identifier, terminal=stdout, stderr=stderr)

    assert (
        state(old),
        state(limited),
        state(colliding),
        group_state(managed_group),
        group_state(limited_group),
        User.objects.count(),
    ) == before
    assert_sanitized(stdout, stderr, error=error.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "identifier",
    (
        "operator_fresh",
        "staging_managed_",
        "staging_managed_é",
        "staging_managed_bad space",
        "staging_managed_" + "x" * 256,
    ),
)
def test_replacement_rejects_invalid_or_unreserved_identifier(
    monkeypatch: pytest.MonkeyPatch, identifier: str
) -> None:
    """AC-2: fresh local-only identifier has a bounded ASCII namespace."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    with pytest.raises(CommandError):
        invoke(monkeypatch, identifier=identifier)
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("password", "password_confirmation"),
    (("short", "short"), (NEW_PASSWORD, "different-password-confirmation")),
)
def test_bad_password_input_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch, password: str, password_confirmation: str
) -> None:
    """AC-4: password policy and confirmation failures preserve the old login."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    terminal, stderr = Tty(), Tty()

    with pytest.raises(CommandError) as error:
        invoke(
            monkeypatch,
            password=password,
            password_confirmation=password_confirmation,
            terminal=terminal,
            stderr=stderr,
        )

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2
    assert password not in terminal.getvalue() + stderr.getvalue() + str(error.value)
    assert password_confirmation not in terminal.getvalue() + stderr.getvalue() + str(
        error.value
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "drift",
    (
        "extra_member",
        "extra_permission",
        "missing_permission",
        "direct_permission",
        "superuser",
        "extra_group",
        "missing_group",
    ),
)
def test_managed_role_drift_refuses_without_partial_transfer(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    """AC-2/4: the existing role must exactly match #205 at the write gate."""
    old, limited, managed_group, limited_group = seed_roles()
    if drift == "extra_member":
        limited.groups.add(managed_group)  # pyright: ignore[reportUnknownMemberType]
    elif drift == "extra_permission":
        managed_group.permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_user"
            )
        )
    elif drift == "missing_permission":
        managed_group.permissions.remove(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="profiles", codename="view_playerprofile"
            )
        )
    elif drift == "direct_permission":
        old.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_user"
            )
        )
    elif drift == "superuser":
        old.is_superuser = True
        old.save(update_fields={"is_superuser"})
    elif drift == "extra_group":
        old.groups.add(Group.objects.create(name="unrelated_group"))  # pyright: ignore[reportUnknownMemberType]
    else:
        old.groups.remove(managed_group)  # pyright: ignore[reportUnknownMemberType]
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db
def test_stale_pre_prompt_managed_identity_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: replacing the pinned predecessor during input cannot retire the successor."""
    old, limited, managed_group, _ = seed_roles()
    changed = False

    def replace_predecessor(_prompt: str) -> None:
        nonlocal changed
        if changed:
            return
        changed = True
        old.groups.remove(managed_group)  # pyright: ignore[reportUnknownMemberType]
        successor = local_staff("staging_managed_intervening", OLD_PASSWORD)
        successor.groups.add(managed_group)  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(CommandError):
        invoke(monkeypatch, on_hidden_prompt=replace_predecessor)

    assert changed
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()
    assert old.is_staff is True
    assert old.check_password(OLD_PASSWORD)
    assert User.objects.get(clerk_user_id="staging_managed_intervening").is_staff
    assert state(limited)[2] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("environment", "service", "confirmation", "tty"),
    (
        ("production", "api", CONFIRMATION, True),
        ("staging", "worker", CONFIRMATION, True),
        ("staging", "api", "wrong confirmation", True),
        ("staging", "api", CONFIRMATION, False),
    ),
)
def test_target_and_interactive_guards_refuse_before_write(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    service: str,
    confirmation: str,
    tty: bool,
) -> None:
    """AC-1/4: wrong target, phrase, or terminal cannot transfer authority."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    terminal: StringIO = Tty() if tty else NonTty()

    with pytest.raises(CommandError):
        invoke(
            monkeypatch,
            environment=environment,
            service=service,
            confirmation=confirmation,
            terminal=terminal,
        )

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("selector", tuple(REPLACEMENT_SELECTORS))
def test_wrong_railway_resource_selector_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch, selector: str
) -> None:
    """AC-1: project, environment, and service resources must be exact."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    with pytest.raises(CommandError):
        invoke(
            monkeypatch,
            selector_override=(selector, "00000000-0000-4000-8000-000000000000"),
        )

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("expected", "observed"),
    (
        (None, EXPECTED_IDENTITY),
        (EXPECTED_IDENTITY, None),
        (
            EXPECTED_IDENTITY,
            {
                **EXPECTED_IDENTITY,
                "deployment_id": "f97225b9-d7bb-4d8b-9ea1-fd1f433a7a9e",
            },
        ),
        (EXPECTED_IDENTITY, {**EXPECTED_IDENTITY, "source_sha": "a" * 40}),
    ),
)
def test_missing_or_mismatched_exact_instance_identity_refuses(
    monkeypatch: pytest.MonkeyPatch,
    expected: dict[str, str] | None,
    observed: dict[str, str] | None,
) -> None:
    """AC-1/4: no direct command use or mismatched source/deployment can write."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    with pytest.raises(CommandError):
        invoke(monkeypatch, expected_identity=expected, live_identity=observed)

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
def test_target_drift_after_hidden_input_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: target is checked again after the user has entered credentials."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    reads = 0

    def changing_identity() -> dict[str, str]:
        nonlocal reads
        reads += 1
        if reads == 1:
            return EXPECTED_IDENTITY
        return {
            **EXPECTED_IDENTITY,
            "deployment_id": "f97225b9-d7bb-4d8b-9ea1-fd1f433a7a9e",
        }

    with pytest.raises(CommandError):
        invoke(monkeypatch, live_identity_provider=changing_identity)

    assert reads >= 2
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "unsafe_boundary", ("debug", "debug_cursor", "query_wrapper", "sql_logger")
)
def test_query_logging_or_wrapper_refuses_before_write(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    caplog: pytest.LogCaptureFixture,
    unsafe_boundary: str,
) -> None:
    """AC-1: hidden credentials must not run under query capture/logging."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    original_wrappers = list(connection.execute_wrappers)
    if unsafe_boundary == "debug":
        settings.DEBUG = True
    elif unsafe_boundary == "debug_cursor":
        monkeypatch.setattr(connection, "force_debug_cursor", True)
    elif unsafe_boundary == "query_wrapper":
        connection.execute_wrappers.append(
            lambda execute, sql, params, many, context: execute(
                sql, params, many, context
            )
        )
    else:
        caplog.set_level(logging.DEBUG, logger="django.db.backends")
    try:
        with pytest.raises(CommandError):
            invoke(monkeypatch)
    finally:
        connection.execute_wrappers[:] = original_wrappers

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
def test_getpass_echo_fallback_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4: a real TTY that cannot suppress echo must fail closed."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    def unsafe_getpass(_prompt: str) -> None:
        warnings.warn("terminal echo fallback", getpass.GetPassWarning)

    with pytest.raises(CommandError):
        invoke(monkeypatch, on_hidden_prompt=unsafe_getpass)
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2


@pytest.mark.django_db
def test_mid_transaction_database_failure_rolls_back_entire_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: a failure after new User insertion leaves the old login usable."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    def fail_after_insert(
        sender: type[User], instance: User, created: bool, **_: object
    ) -> None:
        del sender
        if created and instance.clerk_user_id == NEW_IDENTIFIER:
            raise DatabaseError("private-injected-db-failure")

    post_save.connect(fail_after_insert, sender=User, weak=False)  # pyright: ignore[reportUnknownMemberType]
    try:
        with pytest.raises(CommandError) as error:
            invoke(monkeypatch)
    finally:
        post_save.disconnect(fail_after_insert, sender=User)  # pyright: ignore[reportUnknownMemberType]

    assert "private-injected-db-failure" not in str(error.value)
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() == 2
    assert old.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_successful_but_incomplete_transfer_write_is_detected_and_rolled_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3/4: a silent membership loss before commit must not leave two unusable logins."""
    old, limited, managed_group, limited_group = seed_roles()
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    injected = False

    def drop_new_membership_after_old_retirement(
        sender: type[User], instance: User, created: bool, **_: object
    ) -> None:
        del sender
        nonlocal injected
        if created or instance.pk != old.pk or instance.is_staff:
            return
        injected = True
        replacement = User.objects.get(clerk_user_id=NEW_IDENTIFIER)
        replacement.groups.remove(managed_group)  # pyright: ignore[reportUnknownMemberType]

    post_save.connect(  # pyright: ignore[reportUnknownMemberType]
        drop_new_membership_after_old_retirement,
        sender=User,
        weak=False,
    )
    try:
        with pytest.raises(CommandError):
            invoke(monkeypatch)
    finally:
        post_save.disconnect(  # pyright: ignore[reportUnknownMemberType]
            drop_new_membership_after_old_retirement, sender=User
        )

    assert injected
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert old.check_password(OLD_PASSWORD)
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("association", ("profile", "fursuit", "enrollment", "catch"))
def test_player_domain_association_refuses_old_account_retirement(
    monkeypatch: pytest.MonkeyPatch, association: str
) -> None:
    """AC-2: a managed account linked to gameplay is not disposable admin-only state."""
    from tests.test_staging_validation_operator import attach_gameplay_record

    old, limited, managed_group, limited_group = seed_roles()
    attach_gameplay_record(old, association)
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert User.objects.count() >= 2
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("binding", ("owner", "catcher"))
def test_reset_identity_binding_refuses_old_account_retirement(
    monkeypatch: pytest.MonkeyPatch, binding: str
) -> None:
    """AC-2: #204 owner/catcher bindings cannot be demoted by admin recovery."""
    import uuid

    from rehearsal.models import StagingResetIdentity

    old, limited, managed_group, limited_group = seed_roles()
    other = User.objects.create_user("unrelated_reset_identity")
    StagingResetIdentity.objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="test-cluster",
        database_name="test_database",
        owner=old if binding == "owner" else other,
        catcher=old if binding == "catcher" else other,
        media_key="test/media",
    )
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db
def test_limited_permission_name_on_wrong_content_type_refuses_before_prepared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: app-label/codename coincidence cannot authorize a different model."""
    old, limited, managed_group, limited_group = seed_roles()
    wrong_model = ContentType.objects.create(
        app_label="profiles", model="wrong_validation_fixture"
    )
    wrong_view = Permission.objects.create(
        content_type=wrong_model,
        codename="view_playerprofile",
        name="View unrelated fixture",
    )
    valid_action = Permission.objects.get(
        content_type__app_label="profiles",
        content_type__model="playerprofile",
        codename="set_profile_enabled",
    )
    limited_group.permissions.set([wrong_view, valid_action])  # pyright: ignore[reportUnknownMemberType]
    before = (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    command_module = importlib.import_module(f"accounts.management.commands.{COMMAND}")

    with pytest.raises(CommandError):
        command_module.Command._limited_state()

    terminal, stderr = Tty(), Tty()
    with pytest.raises(CommandError):
        invoke(monkeypatch, terminal=terminal, stderr=stderr)

    assert "PREPARED" not in terminal.getvalue()
    assert (
        state(old),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before
    assert not User.objects.filter(clerk_user_id=NEW_IDENTIFIER).exists()


@pytest.mark.django_db(transaction=True)
def test_postcommit_audit_mismatch_is_uncertain_without_pass_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4/5: a committed transfer with changed audit evidence cannot report PASS."""
    old, limited, managed_group, limited_group = seed_roles()
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=old,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    limited_before = state(limited)
    limited_group_before = group_state(limited_group)
    command_module = importlib.import_module(f"accounts.management.commands.{COMMAND}")
    original_check = command_module.Command._postcommit_check
    postcommit_calls = 0

    def change_audit_then_check(
        self: Any,
        expected: object,
        old_pk: int,
        old_identifier: str,
        new_identifier: str,
        group_pk: int,
        permission_ids: set[int],
        limited_state: tuple[object, ...],
        audit_state: tuple[tuple[object, ...], ...],
    ) -> None:
        nonlocal postcommit_calls
        postcommit_calls += 1
        OperatorAuditEvent.objects.filter(pk=audit.pk).update(affected_record_id=2)
        original_check(
            self,
            expected,
            old_pk,
            old_identifier,
            new_identifier,
            group_pk,
            permission_ids,
            limited_state,
            audit_state,
        )

    monkeypatch.setattr(
        command_module.Command, "_postcommit_check", change_audit_then_check
    )
    terminal, stderr = Tty(), Tty()

    with pytest.raises(CommandError) as error:
        invoke(monkeypatch, terminal=terminal, stderr=stderr)

    old.refresh_from_db()
    audit.refresh_from_db()
    replacement = User.objects.get(clerk_user_id=NEW_IDENTIFIER)
    assert postcommit_calls == 1
    assert "PREPARED" in terminal.getvalue()
    assert "POSTCONDITION_PASS" not in terminal.getvalue() + stderr.getvalue()
    assert "postcondition" in str(error.value).lower()
    assert old.is_staff is False and not old.has_usable_password()
    assert replacement.is_staff and replacement.check_password(NEW_PASSWORD)
    assert group_state(managed_group)[0] == frozenset({replacement.pk})
    assert audit.affected_record_id == 2
    assert state(limited) == limited_before
    assert group_state(limited_group) == limited_group_before
    assert_sanitized(terminal, stderr, error=error.value)


@pytest.mark.django_db(transaction=True)
def test_existing_admin_session_is_invalidated_by_old_password_retirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3/5: old sessions cannot retain Django-admin authority after handoff."""
    old, _limited, _group, _limited_group = seed_roles()
    old_client = Client()
    assert old_client.login(clerk_user_id=OLD_IDENTIFIER, password=OLD_PASSWORD)
    assert old_client.get("/admin/").status_code == 200

    invoke(monkeypatch)

    assert old_client.get("/admin/").status_code == 302
    assert old_client.session.get("_auth_user_id") is None
    new_client = Client()
    assert new_client.login(clerk_user_id=NEW_IDENTIFIER, password=NEW_PASSWORD)
    assert new_client.get("/admin/").status_code == 200
    old.refresh_from_db()
    assert not old.has_usable_password()
