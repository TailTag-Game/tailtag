"""Acceptance coverage for the guarded Railway Development operator command."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User

COMMAND_MODULE = "accounts.management.commands.bootstrap_development_operator"
COMMAND_NAME = "bootstrap_development_operator"
CONFIRMATION_PHRASE = "bootstrap Railway Development operator"
OPERATOR_IDENTIFIER = "operator_development_170"
INITIAL_PASSWORD = "railway-development-operator-password-2026"
ROTATED_PASSWORD = "reconciled-operator-password-2026"


class TtyStream(StringIO):
    """An in-memory terminal stream for deterministic command invocation."""

    def isatty(self) -> bool:
        return True


class NonTtyStream(StringIO):
    """An in-memory redirected stream for fail-closed terminal checks."""

    def isatty(self) -> bool:
        return False


def stored_user_state(user: User) -> dict[str, Any]:
    """Capture every persisted user value to prove a rejection made no mutation."""
    state = User.objects.filter(pk=user.pk).values().get()
    assert isinstance(state, dict)
    return state


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


def assert_sensitive_values_are_not_emitted(
    streams: Iterable[StringIO], *sensitive_values: str
) -> None:
    """Keep test credentials, identifiers, and persisted password hashes off output."""
    rendered = "".join(stream.getvalue() for stream in streams)
    for value in sensitive_values:
        assert value not in rendered


def invoke_command(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confirmation: str = CONFIRMATION_PHRASE,
    private_inputs: Iterable[str] = (),
    environment: str | None = "development",
    service: str | None = "api",
    stdin: StringIO | None = None,
    stdout: StringIO | None = None,
    stderr: StringIO | None = None,
) -> tuple[StringIO, StringIO]:
    """Invoke the command through its public Django interface with terminal seams."""
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

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    private_input_module = command_module.getpass  # pyright: ignore[reportAttributeAccessIssue]

    def confirmation_input(_: str = "") -> str:
        return confirmation

    monkeypatch.setattr("builtins.input", confirmation_input)
    monkeypatch.setattr(private_input_module, "getpass", private_input)
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


@pytest.mark.django_db
def test_bootstrap_creates_a_new_development_operator_without_sensitive_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/8: the exact interactive Development/api flow creates one safe operator."""
    unrelated = User.objects.create_user("unrelated_operator_bootstrap_user")
    unrelated_before = stored_user_state(unrelated)

    stdout, stderr = invoke_command(
        monkeypatch,
        private_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
    )

    created = User.objects.get(clerk_user_id=OPERATOR_IDENTIFIER)
    assert created.is_staff
    assert is_superuser(created)
    assert created.check_password(INITIAL_PASSWORD)
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(created),
    )


@pytest.mark.django_db
def test_bootstrap_reconciles_only_an_existing_full_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6/8: rerunning rotates one full operator password in place without disclosure."""
    existing = User.objects.create_superuser(
        OPERATOR_IDENTIFIER, password=INITIAL_PASSWORD
    )
    existing_primary_key = existing.pk
    old_password_hash = stored_password_hash(existing)
    unrelated = User.objects.create_user("unrelated_reconciliation_user")
    unrelated_before = stored_user_state(unrelated)

    stdout, stderr = invoke_command(
        monkeypatch,
        private_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
    )

    existing.refresh_from_db()
    assert existing.pk == existing_primary_key
    assert existing.is_staff
    assert is_superuser(existing)
    assert existing.check_password(ROTATED_PASSWORD)
    assert not existing.check_password(INITIAL_PASSWORD)
    assert stored_password_hash(existing) != old_password_hash
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        old_password_hash,
        stored_password_hash(existing),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("privilege", ("ordinary", "staff_only", "superuser_only"))
def test_bootstrap_refuses_to_elevate_existing_nonoperators(
    monkeypatch: pytest.MonkeyPatch, privilege: str
) -> None:
    """AC-7/8: existing players and partial administrators remain byte-for-byte intact."""
    protected = User.objects.create_user(OPERATOR_IDENTIFIER)
    if privilege == "staff_only":
        protected.is_staff = True
        protected.save(update_fields={"is_staff"})
    elif privilege == "superuser_only":
        protected.is_superuser = True
        protected.save(update_fields={"is_superuser"})
    protected_before = stored_user_state(protected)
    unrelated = User.objects.create_user(f"unrelated_{privilege}_operator_user")
    unrelated_before = stored_user_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            private_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
            stdout=stdout,
            stderr=stderr,
        )

    assert stored_user_state(protected) == protected_before
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(protected),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("environment", "service"),
    (
        (None, "api"),
        ("Development", "api"),
        ("development", None),
        ("development", "API"),
    ),
)
def test_bootstrap_rejects_wrong_or_missing_railway_target_without_mutation(
    monkeypatch: pytest.MonkeyPatch, environment: str | None, service: str | None
) -> None:
    """AC-5/8: only exact Railway Development api metadata may reach the command."""
    unrelated = User.objects.create_user("unrelated_target_guard_user")
    unrelated_before = stored_user_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            environment=environment,
            service=service,
            stdout=stdout,
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr), stored_password_hash(unrelated)
    )


@pytest.mark.django_db
@pytest.mark.parametrize("non_tty_stream", ("stdin", "stdout"))
def test_bootstrap_rejects_noninteractive_streams_without_mutation(
    monkeypatch: pytest.MonkeyPatch, non_tty_stream: str
) -> None:
    """AC-5/8: redirected stdin or stdout fails before operator creation."""
    streams: dict[str, StringIO] = {"stdin": TtyStream(), "stdout": TtyStream()}
    streams[non_tty_stream] = NonTtyStream()
    unrelated = User.objects.create_user("unrelated_tty_guard_user")
    unrelated_before = stored_user_state(unrelated)
    stderr = TtyStream()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            stdin=streams["stdin"],
            stdout=streams["stdout"],
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (streams["stdout"], stderr), stored_password_hash(unrelated)
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("confirmation", "private_inputs", "validator_message"),
    (
        ("not the documented confirmation", (), None),
        (CONFIRMATION_PHRASE, ("   ",), None),
        (
            CONFIRMATION_PHRASE,
            (OPERATOR_IDENTIFIER, INITIAL_PASSWORD, "different"),
            None,
        ),
        (CONFIRMATION_PHRASE, (OPERATOR_IDENTIFIER, "short", "short"), "too short"),
    ),
    ids=("confirmation", "empty-identifier", "password-mismatch", "validation"),
)
def test_bootstrap_rejects_invalid_input_without_mutation_or_secret_output(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
    private_inputs: tuple[str, ...],
    validator_message: str | None,
) -> None:
    """AC-8: confirmation, input, and password validation failures are non-mutating."""
    unrelated = User.objects.create_user("unrelated_input_guard_user")
    unrelated_before = stored_user_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            confirmation=confirmation,
            private_inputs=private_inputs,
            stdout=stdout,
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr), confirmation, *private_inputs, stored_password_hash(unrelated)
    )
    if validator_message is not None:
        assert validator_message not in (stdout.getvalue() + stderr.getvalue()).lower()
