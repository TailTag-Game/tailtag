"""Acceptance coverage for guarded Railway Staging operator provisioning."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command

from accounts.models import User

COMMAND_MODULE = "accounts.management.commands.bootstrap_staging_operator"
COMMAND_NAME = "bootstrap_staging_operator"
CONFIRMATION_PHRASE = "bootstrap Railway Staging operator"
OPERATOR_GROUP_NAME = "TailTag Field Beta Operators"
OPERATOR_IDENTIFIER = "operator_staging_205"
INITIAL_PASSWORD = "railway-staging-operator-password-2026"
ROTATED_PASSWORD = "reconciled-staging-operator-password-2026"
CREATED_OUTPUT = "Staging operator created.\n"
RECONCILED_OUTPUT = "Staging operator reconciled.\n"
GENERIC_INVALID_ARGUMENTS_ERROR = (
    "Invalid command arguments. Use the documented interactive command."
)
EXPECTED_OPERATOR_PERMISSIONS = {
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
API_ROOT = Path(__file__).resolve().parents[1]


def run_invalid_command_arguments(
    arguments: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    """Exercise Django's parser before the command handler is reachable."""
    return subprocess.run(
        [sys.executable, "manage.py", COMMAND_NAME, *arguments],
        cwd=API_ROOT,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )


class TtyStream(StringIO):
    """An in-memory terminal stream for deterministic command invocation."""

    def isatty(self) -> bool:
        return True


class NonTtyStream(StringIO):
    """An in-memory redirected stream for fail-closed terminal checks."""

    def isatty(self) -> bool:
        return False


def stored_account_state(user: User) -> dict[str, Any]:
    """Capture account and authorization state to prove a refusal made no mutation."""
    user_values = User.objects.filter(pk=user.pk).values().get()
    assert isinstance(user_values, dict)
    return {
        "user": user_values,
        "group_ids": set(
            user.groups.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
        ),
        "permission_ids": set(
            user.user_permissions.values_list(  # pyright: ignore[reportUnknownMemberType]
                "pk", flat=True
            )
        ),
    }


def stored_password_hash(user: User) -> str:
    """Return Django's dynamically typed stored password hash as a string."""
    return cast(
        str,
        user.password,  # pyright: ignore[reportUnknownMemberType]
    )


def is_superuser(user: User) -> bool:
    """Read Django's dynamically typed superuser flag as a boolean."""
    return cast(
        bool,
        user.is_superuser,  # pyright: ignore[reportUnknownMemberType]
    )


def required_permissions() -> dict[str, Permission]:
    """Resolve the frozen permission set by its public Django names."""
    permissions = {
        permission_name(permission): permission
        for permission in Permission.objects.select_related("content_type")
        if permission_name(permission) in EXPECTED_OPERATOR_PERMISSIONS
    }
    assert set(permissions) == EXPECTED_OPERATOR_PERMISSIONS
    return permissions


def permission_name(permission: Permission) -> str:
    """Return Django's public app-label permission name."""
    return f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]


def create_exact_managed_operator(
    *,
    identifier: str = OPERATOR_IDENTIFIER,
    password: str = INITIAL_PASSWORD,
) -> User:
    """Seed the existing identity state that Staging may reconcile in place."""
    group = Group.objects.create(name=OPERATOR_GROUP_NAME)
    group.permissions.set(  # pyright: ignore[reportUnknownMemberType]
        required_permissions().values()
    )
    operator = User(
        clerk_user_id=identifier,
        is_staff=True,
        is_superuser=False,
    )
    operator.set_password(password)
    operator.save()
    operator.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
    return operator


def assert_exact_managed_operator(operator: User, password: str) -> None:
    """Assert the supported dedicated-operator identity and permissions exactly."""
    operator.refresh_from_db()
    assert operator.is_staff is True
    assert is_superuser(operator) is False
    assert operator.check_password(password)
    assert set(operator.get_all_permissions()) == EXPECTED_OPERATOR_PERMISSIONS
    assert operator.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert operator.groups.count() == 1  # pyright: ignore[reportUnknownMemberType]
    group = operator.groups.get()  # pyright: ignore[reportUnknownMemberType]
    assert group.name == OPERATOR_GROUP_NAME  # pyright: ignore[reportUnknownMemberType]
    assert {
        permission_name(permission)
        for permission in group.permissions.select_related(  # pyright: ignore[reportUnknownMemberType]
            "content_type"
        )
    } == EXPECTED_OPERATOR_PERMISSIONS


def assert_sensitive_values_are_not_emitted(
    streams: Iterable[StringIO],
    *sensitive_values: str,
    exception_text: str = "",
) -> None:
    """Keep credentials, identifiers, and hashes off command output and errors."""
    rendered = "".join(stream.getvalue() for stream in streams) + exception_text
    for value in sensitive_values:
        assert value not in rendered


def invoke_command(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confirmation: str = CONFIRMATION_PHRASE,
    private_inputs: Iterable[str] = (),
    environment: str | None = "staging",
    service: str | None = "api",
    stdin: StringIO | None = None,
    stdout: StringIO | None = None,
    stderr: StringIO | None = None,
) -> tuple[StringIO, StringIO]:
    """Invoke the public Django command through controlled terminal seams."""
    command_module = importlib.import_module(COMMAND_MODULE)
    stdin = stdin or TtyStream()
    stdout = stdout or TtyStream()
    stderr = stderr or TtyStream()
    private_input_values = iter(private_inputs)

    def private_input(*_: object, **__: object) -> str:
        try:
            return next(private_input_values)
        except StopIteration as error:
            raise AssertionError("unexpected private prompt") from error

    def confirmation_input(_: str = "") -> str:
        return confirmation

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", confirmation_input)
    monkeypatch.setattr(command_module.getpass, "getpass", private_input)
    if environment is None:
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    else:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
    if service is None:
        monkeypatch.delenv("RAILWAY_SERVICE_NAME", raising=False)
    else:
        monkeypatch.setenv("RAILWAY_SERVICE_NAME", service)

    call_command(COMMAND_NAME, stdout=stdout, stderr=stderr)
    return stdout, stderr


@pytest.mark.parametrize(
    ("arguments", "sensitive_value"),
    (
        (
            (
                "--settings=config.settings.build",
                "unexpected-positional-parser-sentinel-205",
            ),
            "unexpected-positional-parser-sentinel-205",
        ),
        (
            (
                "--password",
                "credential-like-parser-sentinel-205",
                "--settings=config.settings.build",
            ),
            "credential-like-parser-sentinel-205",
        ),
    ),
    ids=("positional", "credential-like-option"),
)
def test_bootstrap_rejects_invalid_parser_arguments_without_echoing_them(
    arguments: tuple[str, ...], sensitive_value: str
) -> None:
    """AC-6: Django's pre-handler parser never reflects supplied arguments."""
    completed = run_invalid_command_arguments(arguments)

    rendered_output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert sensitive_value not in rendered_output
    assert completed.stdout == ""
    assert completed.stderr == f"{GENERIC_INVALID_ARGUMENTS_ERROR}\n"


@pytest.mark.django_db
def test_bootstrap_creates_a_dedicated_staging_operator_without_sensitive_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/6/11: the exact interactive Staging/api flow creates one operator."""
    unrelated = User.objects.create_user("unrelated_staging_operator_user")
    unrelated_before = stored_account_state(unrelated)

    stdout, stderr = invoke_command(
        monkeypatch,
        private_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
    )

    operator = User.objects.get(clerk_user_id=OPERATOR_IDENTIFIER)
    assert_exact_managed_operator(operator, INITIAL_PASSWORD)
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert stored_account_state(unrelated) == unrelated_before
    assert stdout.getvalue() == CREATED_OUTPUT
    assert stderr.getvalue() == ""
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(operator),
    )


@pytest.mark.django_db
def test_bootstrap_reconciles_only_an_existing_exact_managed_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/6/11: rerunning rotates only the exact operator identity in place."""
    operator = create_exact_managed_operator()
    operator_primary_key = operator.pk
    old_password_hash = stored_password_hash(operator)
    unrelated = User.objects.create_user("unrelated_staging_reconciliation_user")
    unrelated_before = stored_account_state(unrelated)

    stdout, stderr = invoke_command(
        monkeypatch,
        private_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
    )

    operator.refresh_from_db()
    assert operator.pk == operator_primary_key
    assert_exact_managed_operator(operator, ROTATED_PASSWORD)
    assert not operator.check_password(INITIAL_PASSWORD)
    assert stored_password_hash(operator) != old_password_hash
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert stored_account_state(unrelated) == unrelated_before
    assert stdout.getvalue() == RECONCILED_OUTPUT
    assert stderr.getvalue() == ""
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        old_password_hash,
        stored_password_hash(operator),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("environment", "service"),
    (
        (None, "api"),
        ("Staging", "api"),
        ("production", "api"),
        ("staging", None),
        ("staging", "API"),
        ("staging", "worker"),
    ),
)
def test_bootstrap_rejects_wrong_or_missing_railway_target_without_mutation(
    monkeypatch: pytest.MonkeyPatch, environment: str | None, service: str | None
) -> None:
    """AC-11: only exact Railway Staging api metadata may reach provisioning."""
    unrelated = User.objects.create_user("unrelated_staging_target_guard_user")
    unrelated_before = stored_account_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            environment=environment,
            service=service,
            stdout=stdout,
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_account_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        stored_password_hash(unrelated),
        exception_text=str(error.value),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("non_tty_stream", ("stdin", "stdout"))
def test_bootstrap_rejects_noninteractive_streams_without_mutation(
    monkeypatch: pytest.MonkeyPatch, non_tty_stream: str
) -> None:
    """AC-11: redirected stdin or stdout fails before operator creation."""
    streams: dict[str, StringIO] = {"stdin": TtyStream(), "stdout": TtyStream()}
    streams[non_tty_stream] = NonTtyStream()
    unrelated = User.objects.create_user("unrelated_staging_tty_guard_user")
    unrelated_before = stored_account_state(unrelated)
    stderr = TtyStream()

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            stdin=streams["stdin"],
            stdout=streams["stdout"],
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_account_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (streams["stdout"], stderr),
        stored_password_hash(unrelated),
        exception_text=str(error.value),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("confirmation", "private_inputs"),
    (
        ("not the documented confirmation", ()),
        (CONFIRMATION_PHRASE, ("   ",)),
        (
            CONFIRMATION_PHRASE,
            (OPERATOR_IDENTIFIER, INITIAL_PASSWORD, "different"),
        ),
        (CONFIRMATION_PHRASE, (OPERATOR_IDENTIFIER, "short", "short")),
    ),
    ids=("confirmation", "empty-identifier", "password-mismatch", "validation"),
)
def test_bootstrap_rejects_invalid_input_without_mutation_or_secret_output(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
    private_inputs: tuple[str, ...],
) -> None:
    """AC-6/11: invalid confirmation or hidden input is non-mutating and private."""
    unrelated = User.objects.create_user("unrelated_staging_input_guard_user")
    unrelated_before = stored_account_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            confirmation=confirmation,
            private_inputs=private_inputs,
            stdout=stdout,
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_account_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        confirmation,
        *private_inputs,
        stored_password_hash(unrelated),
        exception_text=str(error.value),
    )


@pytest.mark.django_db
def test_bootstrap_refuses_when_an_expected_permission_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11: incomplete permission provisioning fails before creating an identity."""
    unavailable_permission = required_permissions()["profiles.set_profile_enabled"]
    unavailable_permission.delete()
    unrelated = User.objects.create_user("unrelated_staging_permission_guard_user")
    unrelated_before = stored_account_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            private_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
            stdout=stdout,
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_account_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(unrelated),
        exception_text=str(error.value),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "account_state",
    ("player", "superuser", "other_group", "direct_permission", "ambiguous"),
)
def test_bootstrap_refuses_to_elevate_or_repurpose_an_ambiguous_existing_account(
    monkeypatch: pytest.MonkeyPatch, account_state: str
) -> None:
    """AC-2/11: only the exact dedicated operator may be reconciled in place."""
    if account_state == "player":
        protected = User.objects.create_user(OPERATOR_IDENTIFIER)
    elif account_state == "superuser":
        protected = User.objects.create_superuser(
            OPERATOR_IDENTIFIER, password=INITIAL_PASSWORD
        )
    elif account_state == "other_group":
        protected = User(
            clerk_user_id=OPERATOR_IDENTIFIER,
            is_staff=True,
            is_superuser=False,
        )
        protected.set_password(INITIAL_PASSWORD)
        protected.save()
        protected.groups.add(  # pyright: ignore[reportUnknownMemberType]
            Group.objects.create(name="other operator group")
        )
    elif account_state == "direct_permission":
        protected = create_exact_managed_operator()
        protected.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            required_permissions()["catches.delete_catch"]
        )
    else:
        protected = create_exact_managed_operator()
        protected.groups.add(  # pyright: ignore[reportUnknownMemberType]
            Group.objects.create(name="additional operator group")
        )

    protected_before = stored_account_state(protected)
    unrelated = User.objects.create_user(f"unrelated_{account_state}_staging_user")
    unrelated_before = stored_account_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            private_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
            stdout=stdout,
            stderr=stderr,
        )

    assert stored_account_state(protected) == protected_before
    assert stored_account_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        stored_password_hash(protected),
        exception_text=str(error.value),
    )
