"""Acceptance coverage for the guarded Railway Development operator command."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from typing import Any, cast

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError, close_old_connections, connection

from accounts.models import User

COMMAND_MODULE = "accounts.management.commands.bootstrap_development_operator"
COMMAND_NAME = "bootstrap_development_operator"
CONFIRMATION_PHRASE = "bootstrap Railway Development operator"
OPERATOR_IDENTIFIER = "operator_development_170"
INITIAL_PASSWORD = "railway-development-operator-password-2026"
ROTATED_PASSWORD = "reconciled-operator-password-2026"
CREATED_OUTPUT = "Development operator created.\n"
RECONCILED_OUTPUT = "Development operator reconciled.\n"


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
    assert stdout.getvalue() == CREATED_OUTPUT
    assert stderr.getvalue() == ""
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
    assert stdout.getvalue() == RECONCILED_OUTPUT
    assert stderr.getvalue() == ""
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        old_password_hash,
        stored_password_hash(existing),
    )


@pytest.mark.django_db
def test_bootstrap_reconciliation_validates_before_replacing_a_full_operator_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6/8: an invalid rotation leaves the existing full operator unchanged."""
    existing = User.objects.create_superuser(
        OPERATOR_IDENTIFIER, password=INITIAL_PASSWORD
    )
    existing_primary_key = existing.pk
    old_password_hash = stored_password_hash(existing)
    unrelated = User.objects.create_user("unrelated_invalid_reconciliation_user")
    unrelated_before = stored_user_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()
    invalid_replacement_password = "short"

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            private_inputs=(
                OPERATOR_IDENTIFIER,
                invalid_replacement_password,
                invalid_replacement_password,
            ),
            stdout=stdout,
            stderr=stderr,
        )

    existing.refresh_from_db()
    assert existing.pk == existing_primary_key
    assert existing.is_staff
    assert is_superuser(existing)
    assert existing.has_usable_password()
    assert existing.check_password(INITIAL_PASSWORD)
    assert stored_password_hash(existing) == old_password_hash
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        invalid_replacement_password,
        old_password_hash,
        exception_text=str(error.value),
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_bootstraps_create_and_reconcile_one_full_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/6/8: concurrent first runs never leak a duplicate-key failure or secret."""
    command_module = importlib.import_module(COMMAND_MODULE)
    start = Barrier(2, timeout=10)
    shared_terminal = TtyStream()

    def private_input(prompt: str, **_: object) -> str:
        if prompt == "Operator identifier: ":
            return OPERATOR_IDENTIFIER
        return INITIAL_PASSWORD

    def confirmation_input(_: str = "") -> str:
        return CONFIRMATION_PHRASE

    def run_bootstrap() -> tuple[
        CommandError | IntegrityError | None, TtyStream, TtyStream
    ]:
        stdout = TtyStream()
        stderr = TtyStream()
        close_old_connections()
        try:
            start.wait()
            call_command(COMMAND_NAME, stdout=stdout, stderr=stderr)
        except (CommandError, IntegrityError) as error:
            return error, stdout, stderr
        finally:
            close_old_connections()
        return None, stdout, stderr

    monkeypatch.setattr(sys, "stdin", shared_terminal)
    monkeypatch.setattr(sys, "stdout", shared_terminal)
    monkeypatch.setattr("builtins.input", confirmation_input)
    monkeypatch.setattr(command_module.getpass, "getpass", private_input)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_bootstrap)
        second = executor.submit(run_bootstrap)
        first_result = first.result()
        second_result = second.result()

    results = (first_result, second_result)
    assert all(error is None for error, _, _ in results)
    assert {stdout.getvalue() for _, stdout, _ in results} == {
        CREATED_OUTPUT,
        RECONCILED_OUTPUT,
    }
    assert all(stderr.getvalue() == "" for _, _, stderr in results)

    operator = User.objects.get(clerk_user_id=OPERATOR_IDENTIFIER)
    assert operator.is_staff
    assert is_superuser(operator)
    assert operator.check_password(INITIAL_PASSWORD)
    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 1
    assert_sensitive_values_are_not_emitted(
        tuple(stream for _, stdout, stderr in results for stream in (stdout, stderr)),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(operator),
        exception_text="".join(
            str(error) for error, _, _ in results if error is not None
        ),
    )


@pytest.mark.django_db(transaction=True)
def test_bootstrap_converts_database_failure_to_a_generic_secret_safe_command_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: an actual PostgreSQL write failure cannot disclose operator input."""
    unrelated = User.objects.create_user("unrelated_database_failure_user")
    unrelated_before = stored_user_state(unrelated)
    stdout = TtyStream()
    stderr = TtyStream()
    constraint_name = "accounts_user_bootstrap_operator_failure"
    table_name = connection.ops.quote_name(User._meta.db_table)

    with connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} "
            "CHECK (clerk_user_id <> %s)",
            [OPERATOR_IDENTIFIER],
        )
    try:
        with pytest.raises(CommandError) as error:
            invoke_command(
                monkeypatch,
                private_inputs=(
                    OPERATOR_IDENTIFIER,
                    INITIAL_PASSWORD,
                    INITIAL_PASSWORD,
                ),
                stdout=stdout,
                stderr=stderr,
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}"
            )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        stored_password_hash(unrelated),
        exception_text=str(error.value),
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

    with pytest.raises(CommandError) as error:
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
        exception_text=str(error.value),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("environment", "service"),
    (
        (None, "api"),
        ("Development", "api"),
        ("production", "api"),
        ("development", None),
        ("development", "API"),
        ("development", "worker"),
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

    with pytest.raises(CommandError) as error:
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
        (stdout, stderr),
        stored_password_hash(unrelated),
        exception_text=str(error.value),
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

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            stdin=streams["stdin"],
            stdout=streams["stdout"],
            stderr=stderr,
        )

    assert User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).count() == 0
    assert stored_user_state(unrelated) == unrelated_before
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
    """AC-8: confirmation, input, and password validation failures are non-mutating."""
    unrelated = User.objects.create_user("unrelated_input_guard_user")
    unrelated_before = stored_user_state(unrelated)
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
    assert stored_user_state(unrelated) == unrelated_before
    assert_sensitive_values_are_not_emitted(
        (stdout, stderr),
        confirmation,
        *private_inputs,
        stored_password_hash(unrelated),
        exception_text=str(error.value),
    )
