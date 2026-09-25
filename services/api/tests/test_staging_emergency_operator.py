"""Acceptance tests for a dedicated replacement-Staging emergency operator."""

from __future__ import annotations

import getpass
import importlib
import logging
import os
import subprocess
import sys
import uuid
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier, local
from typing import Any, NoReturn, Self, cast

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command, get_commands
from django.db import DatabaseError, close_old_connections, connection
from django.utils import timezone
from pytest_django.fixtures import SettingsWrapper

from accounts.models import User
from catches.models import Catch
from config import replacement_target_binding
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
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
from profiles.models import PlayerProfile
from rehearsal.models import StagingResetIdentity

COMMAND_MODULE = "accounts.management.commands.bootstrap_staging_emergency_operator"
COMMAND_NAME = "bootstrap_staging_emergency_operator"
CONFIRMATION_PHRASE = "bootstrap Railway Staging emergency operator"
IDENTIFIER = "staging_emergency_243"
PASSWORD = "a-unique-emergency-password-for-243"
SUCCESS = "Staging emergency operator created.\n"
INVALID_ARGUMENTS = (
    "Invalid command arguments. Use the documented interactive command.\n"
)
API_ROOT = Path(__file__).resolve().parents[1]

# These are disposable test selectors. Their matching digest is installed only in
# the test process; the real replacement selector values never enter this file.
PROJECT = "11111111-1111-4111-8111-111111111111"
ENVIRONMENT = "22222222-2222-4222-8222-222222222222"
SERVICE = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"


class TtyStream(StringIO):
    def isatty(self) -> bool:
        return True


class NonTtyStream(StringIO):
    def isatty(self) -> bool:
        return False


def _pin_test_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        replacement_target_binding,
        "_EXPECTED_DIGESTS",
        {
            **replacement_target_binding._EXPECTED_DIGESTS,  # pyright: ignore[reportPrivateUsage]
            "staging-api": replacement_target_binding.fingerprint_tuple(
                "staging-api", PROJECT, ENVIRONMENT, SERVICE
            ),
        },
    )


def _set_target(
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str | None = "staging",
    service_name: str | None = "api",
    project_id: str | None = PROJECT,
    environment_id: str | None = ENVIRONMENT,
    service_id: str | None = SERVICE,
) -> None:
    values = {
        "RAILWAY_ENVIRONMENT_NAME": name,
        "RAILWAY_SERVICE_NAME": service_name,
        "RAILWAY_PROJECT_ID": project_id,
        "RAILWAY_ENVIRONMENT_ID": environment_id,
        "RAILWAY_SERVICE_ID": service_id,
    }
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confirmation: str = CONFIRMATION_PHRASE,
    private_inputs: tuple[str, ...] = (IDENTIFIER, PASSWORD, PASSWORD),
    stdin: StringIO | None = None,
    stdout: StringIO | None = None,
    stderr: StringIO | None = None,
    hidden_reader: Callable[[str], str] | None = None,
) -> tuple[StringIO, StringIO, list[str]]:
    """Exercise the public command with its approved interactive input seam."""
    command = importlib.import_module(COMMAND_MODULE)
    stdin = stdin if stdin is not None else TtyStream()
    stdout = stdout if stdout is not None else TtyStream()
    stderr = stderr if stderr is not None else TtyStream()
    prompts: list[str] = []
    answers = iter(private_inputs)

    def confirmation_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return confirmation

    def hidden_input(prompt: str = "") -> str:
        prompts.append(prompt)
        try:
            return next(answers)
        except StopIteration as error:
            raise AssertionError("Unexpected hidden prompt") from error

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", confirmation_input)
    monkeypatch.setattr(command.getpass, "getpass", hidden_reader or hidden_input)
    call_command(COMMAND_NAME, stdout=stdout, stderr=stderr)
    return stdout, stderr, prompts


def _state(user: User) -> tuple[dict[str, Any], set[int], set[int]]:
    """Capture persisted account state to prove refusal leaves it untouched."""
    user.refresh_from_db()
    row = User.objects.filter(pk=user.pk).values().get()
    assert isinstance(row, dict)
    return (
        row,
        set(user.groups.values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
        set(user.user_permissions.values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
    )


def _install_registry() -> StagingResetIdentity:
    """Bind the disposable #204 singleton to this test's actual PostgreSQL."""
    owner = User.objects.create_user("emergency_registry_owner_243")
    catcher = User.objects.create_user("emergency_registry_catcher_243")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        facts = cursor.fetchone()
    assert facts is not None
    return StagingResetIdentity.objects.create(
        id=1,
        environment_id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
        cluster_identifier=str(facts[1]),
        database_name=str(facts[0]),
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )


def _assert_private(
    stdout: StringIO,
    stderr: StringIO,
    error: BaseException | None,
    caplog: pytest.LogCaptureFixture | None,
    *values: str,
) -> None:
    material = stdout.getvalue() + stderr.getvalue() + str(error or "")
    if caplog is not None:
        material += caplog.text
    for value in values:
        # Whitespace-only rejected input cannot be distinguished from ordinary
        # spaces in a fixed refusal message; keep checking substantive values.
        if not value.strip():
            continue
        assert value not in material
        if caplog is not None:
            assert all(value not in repr(record.__dict__) for record in caplog.records)


def test_dedicated_emergency_command_is_registered() -> None:
    """An absent command cannot be mistaken for a safe parser refusal."""
    assert COMMAND_NAME in get_commands()


@pytest.mark.django_db
def test_creates_one_isolated_superuser_from_hidden_prompts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fresh dedicated account has exactly emergency authority and no gameplay state."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    caplog.set_level(logging.DEBUG)
    unrelated = User.objects.create_user("unrelated_emergency_test_player")
    unrelated_before = _state(unrelated)
    managed = User(
        clerk_user_id="existing_managed_243", is_staff=True, is_superuser=False
    )
    managed.set_password("existing-managed-password-243")
    managed.save()
    managed.groups.add(Group.objects.create(name="TailTag Field Beta Operators"))  # pyright: ignore[reportUnknownMemberType]
    managed_before = _state(managed)
    limited = User(
        clerk_user_id="existing_limited_243", is_staff=True, is_superuser=False
    )
    limited.set_password("existing-limited-password-243")
    limited.save()
    limited.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        Permission.objects.get(
            content_type__app_label="profiles", codename="set_profile_enabled"
        )
    )
    limited_before = _state(limited)

    stdout, stderr, prompts = _invoke(monkeypatch)

    created = User.objects.get(clerk_user_id=IDENTIFIER)
    assert User.objects.filter(clerk_user_id=IDENTIFIER).count() == 1
    assert created.is_staff is True
    assert cast(bool, created.is_superuser) is True  # pyright: ignore[reportUnknownMemberType]
    assert created.check_password(PASSWORD)
    assert created.groups.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert created.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert not PlayerProfile.objects.filter(user=created).exists()
    assert not Fursuit.objects.filter(owner=created).exists()
    assert not ConventionEnrollment.objects.filter(user=created).exists()
    assert _state(unrelated) == unrelated_before
    assert _state(managed) == managed_before
    assert _state(limited) == limited_before
    assert stdout.getvalue() == SUCCESS
    assert stderr.getvalue() == ""
    assert len(prompts) == 4  # confirmation, identifier, password, confirmation
    assert prompts[0].startswith("Confirmation")
    _assert_private(
        stdout,
        stderr,
        None,
        caplog,
        IDENTIFIER,
        PASSWORD,
        cast(str, created.password),  # pyright: ignore[reportUnknownMemberType]
    )
    assert all(
        IDENTIFIER not in value and PASSWORD not in value
        for value in os.environ.values()
    )


@pytest.mark.django_db
def test_refuses_creation_without_a_provisioned_204_registry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A pinned Railway selector alone cannot authorize an unbound database."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout, stderr=stderr)

    assert not StagingResetIdentity.objects.exists()
    assert not User.objects.filter(is_superuser=True).exists()
    assert not User.objects.filter(clerk_user_id=IDENTIFIER).exists()
    assert stdout.getvalue() == ""
    _assert_private(stdout, stderr, error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mismatch", ("registry_database", "registry_cluster", "django_database")
)
def test_refuses_creation_when_persisted_or_configured_database_binding_disagrees(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mismatch: str,
) -> None:
    """Actual PostgreSQL and Django must agree with the persisted #204 binding."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    identity = _install_registry()
    private_value = "different_private_database_243"
    if mismatch == "registry_database":
        identity.database_name = private_value
        identity.save(update_fields=["database_name"])
    elif mismatch == "registry_cluster":
        private_value = "999999999"
        identity.cluster_identifier = private_value
        identity.save(update_fields=["cluster_identifier"])
    else:
        monkeypatch.setitem(django_settings.DATABASES["default"], "NAME", private_value)
    before = User.objects.count()
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout, stderr=stderr)

    assert User.objects.count() == before
    assert not User.objects.filter(is_superuser=True).exists()
    assert not User.objects.filter(clerk_user_id=IDENTIFIER).exists()
    assert stdout.getvalue() == ""
    _assert_private(
        stdout, stderr, error.value, caplog, IDENTIFIER, PASSWORD, private_value
    )


@pytest.mark.django_db
def test_refuses_creation_when_connected_database_facts_cannot_be_queried(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An uncertain PostgreSQL identity is a sanitized, nonmutating refusal."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    before = User.objects.count()
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()
    original_cursor = connection.cursor

    class FactFailureCursor:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate

        def __enter__(self) -> Self:
            self.delegate.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.delegate.__exit__(*args)

        def execute(self, sql: str, params: object = None) -> object:
            if "pg_control_system" in sql:
                raise DatabaseError("private-connected-database-failure-243")
            return self.delegate.execute(sql, params)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.delegate, name)

    def fail_database_fact_query(*args: object, **kwargs: object) -> FactFailureCursor:
        return FactFailureCursor(original_cursor(*args, **kwargs))

    try:
        monkeypatch.setattr(connection, "cursor", fail_database_fact_query)
        with pytest.raises(CommandError) as error:
            _invoke(monkeypatch, stdout=stdout, stderr=stderr)
    finally:
        monkeypatch.setattr(connection, "cursor", original_cursor)

    assert User.objects.count() == before
    assert not User.objects.filter(is_superuser=True).exists()
    assert not User.objects.filter(clerk_user_id=IDENTIFIER).exists()
    assert stdout.getvalue() == ""
    _assert_private(
        stdout,
        stderr,
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "private-connected-database-failure-243",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "service_name", "project_id", "environment_id", "service_id"),
    (
        ("development", "api", PROJECT, ENVIRONMENT, SERVICE),
        ("staging", "worker", PROJECT, ENVIRONMENT, SERVICE),
        ("staging", "api", OTHER, ENVIRONMENT, SERVICE),
        ("staging", "api", PROJECT, OTHER, SERVICE),
        ("staging", "api", PROJECT, ENVIRONMENT, OTHER),
        ("staging", "api", None, ENVIRONMENT, SERVICE),
    ),
)
def test_rejects_wrong_or_incomplete_code_pinned_target_before_prompt(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    service_name: str,
    project_id: str | None,
    environment_id: str,
    service_id: str,
) -> None:
    """The real replacement target binding guards every Railway selector."""
    _pin_test_target(monkeypatch)
    _set_target(
        monkeypatch,
        name=name,
        service_name=service_name,
        project_id=project_id,
        environment_id=environment_id,
        service_id=service_id,
    )
    before = User.objects.count()
    stdout, stderr = TtyStream(), TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, private_inputs=(), stdout=stdout)
    assert User.objects.count() == before
    _assert_private(stdout, stderr, error.value, None, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize("stream", ("stdin", "stdout"))
def test_refuses_non_tty_before_secret_input(
    monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    stdin = NonTtyStream() if stream == "stdin" else TtyStream()
    stdout = NonTtyStream() if stream == "stdout" else TtyStream()
    with pytest.raises(CommandError):
        _invoke(monkeypatch, private_inputs=(), stdin=stdin, stdout=stdout)
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_refuses_getpass_echo_fallback_before_any_user_write(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A TTY is insufficient if hidden input warns that it may echo secrets."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    caplog.set_level(logging.DEBUG)
    stdout = TtyStream()
    prompt_count = 0

    def warned_input(_: str = "") -> str:
        nonlocal prompt_count
        prompt_count += 1
        warnings.warn("getpass-fallback-sentinel-243", getpass.GetPassWarning)
        return IDENTIFIER

    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout, hidden_reader=warned_input)

    assert prompt_count == 1
    assert User.objects.count() == 0
    _assert_private(stdout, TtyStream(), error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_identifier",
    (
        "staging_emergency_",
        "staging_emergency_" + "a" * 49,
        "Staging_emergency_243",
        "staging_managed_243",
        " staging_emergency_243",
        "staging_emergency_243 ",
        "staging_emergency_2 43",
        "staging_emergency_2\t43",
        "staging_emergency_2\n43",
        "staging_emergency_2\x0043",
    ),
)
def test_refuses_malformed_dedicated_identifier_without_mutation_or_leak(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    invalid_identifier: str,
) -> None:
    """The synthetic emergency identity has one narrow, value-free syntax."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    caplog.set_level(logging.DEBUG)
    stdout = TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(
            monkeypatch,
            stdout=stdout,
            private_inputs=(invalid_identifier, PASSWORD, PASSWORD),
        )
    assert User.objects.count() == 0
    _assert_private(
        stdout, TtyStream(), error.value, caplog, invalid_identifier, PASSWORD
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("confirmation", "private_inputs"),
    (
        ("wrong confirmation", ()),
        (CONFIRMATION_PHRASE, (" ",)),
        (CONFIRMATION_PHRASE, (IDENTIFIER, PASSWORD, "different-password")),
        (CONFIRMATION_PHRASE, (IDENTIFIER, "short", "short")),
    ),
)
def test_refuses_invalid_confirmation_and_hidden_input_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    confirmation: str,
    private_inputs: tuple[str, ...],
) -> None:
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(
            monkeypatch,
            confirmation=confirmation,
            private_inputs=private_inputs,
            stdout=stdout,
        )
    assert User.objects.count() == 0
    _assert_private(stdout, stderr, error.value, caplog, confirmation, *private_inputs)


@pytest.mark.django_db
@pytest.mark.parametrize("collision", ("player", "managed", "limited", "superuser"))
def test_never_adopts_or_elevates_an_existing_identity(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    collision: str,
) -> None:
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    if collision == "player":
        existing = User.objects.create_user(IDENTIFIER)
    else:
        existing = User(
            clerk_user_id=IDENTIFIER,
            is_staff=True,
            is_superuser=collision == "superuser",
        )
        existing.set_password("existing-account-password-243")
        existing.save()
        if collision == "managed":
            group = Group.objects.create(name="TailTag Field Beta Operators")
            existing.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
        elif collision == "limited":
            permission = Permission.objects.get(
                content_type__app_label="profiles", codename="set_profile_enabled"
            )
            existing.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
    before = _state(existing)
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout)
    assert User.objects.count() == 3
    assert _state(existing) == before
    _assert_private(stdout, stderr, error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize("existing_staff", (True, False))
def test_refuses_any_other_existing_superuser_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    existing_staff: bool,
) -> None:
    """A different identifier cannot create a second emergency authority."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    existing = User(
        clerk_user_id="different_existing_superuser_243",
        is_staff=existing_staff,
        is_superuser=True,
    )
    if existing_staff:
        existing.set_password("existing-emergency-password-243")
    else:
        # Corrupted nonstaff superuser state must still occupy the singleton.
        existing.set_unusable_password()
    existing.save()
    before = _state(existing)
    caplog.set_level(logging.DEBUG)
    stdout = TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout)

    assert User.objects.count() == 3
    assert User.objects.filter(is_superuser=True).count() == 1
    assert not User.objects.filter(clerk_user_id=IDENTIFIER).exists()
    assert _state(existing) == before
    _assert_private(stdout, TtyStream(), error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db(transaction=True)
def test_concurrent_distinct_identifiers_create_at_most_one_superuser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two simultaneous first uses yield one success and one fixed refusal."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    command = importlib.import_module(COMMAND_MODULE)
    monkeypatch.setattr(sys, "stdin", TtyStream())
    monkeypatch.setattr(sys, "stdout", TtyStream())

    def confirmation_input(_: str = "") -> str:
        return CONFIRMATION_PHRASE

    monkeypatch.setattr("builtins.input", confirmation_input)
    thread_input = local()
    start = Barrier(2, timeout=10)
    identifiers = ("staging_emergency_first_243", "staging_emergency_second_243")

    def hidden_input(_: str = "") -> str:
        responses = cast(tuple[str, str, str], thread_input.responses)
        index = cast(int, thread_input.index)
        thread_input.index = index + 1
        return responses[index]

    def run(identifier: str) -> tuple[str, str, str]:
        thread_input.responses = (identifier, PASSWORD, PASSWORD)
        thread_input.index = 0
        stdout, stderr = TtyStream(), TtyStream()
        close_old_connections()
        try:
            start.wait()
            try:
                call_command(COMMAND_NAME, stdout=stdout, stderr=stderr)
            except CommandError as error:
                return "refused", str(error), stdout.getvalue() + stderr.getvalue()
            return "created", "", stdout.getvalue() + stderr.getvalue()
        finally:
            close_old_connections()

    monkeypatch.setattr(command.getpass, "getpass", hidden_input)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, identifier) for identifier in identifiers]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(result[0] for result in results) == ["created", "refused"]
    assert User.objects.filter(is_superuser=True).count() == 1
    assert User.objects.filter(clerk_user_id__in=identifiers).count() == 1
    assert sorted(result[2] for result in results) == ["", SUCCESS]
    assert all(
        identifier not in error_or_output
        for _, error, output in results
        for identifier in identifiers
        for error_or_output in (error, output)
    )


@pytest.mark.django_db
@pytest.mark.parametrize("failure", (EOFError, OSError, KeyboardInterrupt))
@pytest.mark.parametrize("prompt_index", (0, 1, 2))
def test_hidden_input_failure_is_fixed_and_nonmutating(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: type[BaseException],
    prompt_index: int,
) -> None:
    """Terminal failure at any private prompt cannot write or expose secrets."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    caplog.set_level(logging.DEBUG)
    answers = (IDENTIFIER, PASSWORD, PASSWORD)
    prompt_count = 0

    def failing_input(_: str = "") -> str:
        nonlocal prompt_count
        index = prompt_count
        prompt_count += 1
        if index == prompt_index:
            raise failure("hidden-input-failure-sentinel-243")
        return answers[index]

    stdout = TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout, hidden_reader=failing_input)

    assert prompt_count == prompt_index + 1
    assert str(error.value) == "Hidden terminal input is unavailable."
    assert User.objects.count() == 0
    _assert_private(
        stdout,
        TtyStream(),
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "hidden-input-failure-sentinel-243",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("debug_mode", ("settings", "cursor", "wrapper", "logger"))
def test_query_debugging_is_refused_before_input_or_write(
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    debug_mode: str,
) -> None:
    """Private credentials cannot enter a query-logging execution mode."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    stdout = TtyStream()
    original_debug_cursor = connection.force_debug_cursor
    database_logger = logging.getLogger("django.db.backends")
    original_logger_level = database_logger.level
    if debug_mode == "settings":
        settings.DEBUG = True
    elif debug_mode == "cursor":
        connection.force_debug_cursor = True
    elif debug_mode == "wrapper":
        connection.execute_wrappers.append(
            lambda execute, sql, params, many, context: execute(
                sql, params, many, context
            )
        )
    else:
        database_logger.setLevel(logging.DEBUG)
    try:
        with pytest.raises(CommandError) as error:
            _invoke(monkeypatch, private_inputs=(), stdout=stdout)
        assert str(error.value) == "Query debugging must be disabled."
        assert User.objects.count() == 0
        assert stdout.getvalue() == ""
    finally:
        if debug_mode == "cursor":
            connection.force_debug_cursor = original_debug_cursor
        elif debug_mode == "wrapper":
            connection.execute_wrappers.pop()
        elif debug_mode == "logger":
            database_logger.setLevel(original_logger_level)


@pytest.mark.django_db(transaction=True)
def test_database_failure_after_insert_rolls_back_and_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An uncertain partial insert cannot leave an emergency identity behind."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    original_save = User.save

    def save_then_fail(self: User, **kwargs: Any) -> None:
        original_save(self, **kwargs)
        if self.clerk_user_id == IDENTIFIER:
            raise DatabaseError("private-database-failure-sentinel-243")

    monkeypatch.setattr(User, "save", save_then_fail)
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()
    with pytest.raises(CommandError) as error:
        _invoke(monkeypatch, stdout=stdout)
    assert not User.objects.filter(clerk_user_id=IDENTIFIER).exists()
    _assert_private(
        stdout,
        stderr,
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "private-database-failure-sentinel-243",
    )


def _inspect_emergency_state() -> str:
    """Exercise the command's operational read-only status contract."""
    command = importlib.import_module(COMMAND_MODULE)
    return cast(str, command.inspect_emergency_state())  # pyright: ignore[reportAttributeAccessIssue]


def _make_emergency(
    identifier: str = IDENTIFIER,
    *,
    staff: bool = True,
    usable_password: bool = True,
) -> User:
    user = User(clerk_user_id=identifier, is_staff=staff, is_superuser=True)
    if staff and usable_password:
        user.set_password(PASSWORD)
    else:
        user.set_unusable_password()
    user.save()
    return user


def _attach_emergency_gameplay_record(actor: User, attachment: str) -> None:
    """Seed exactly one prohibited actor attachment using real domain models."""
    if attachment == "profile":
        PlayerProfile.objects.create(user=actor)
        return
    if attachment in ("sentinel_owner", "sentinel_catcher"):
        registry = StagingResetIdentity.objects.get(pk=1)
        field = "owner" if attachment == "sentinel_owner" else "catcher"
        setattr(registry, field, actor)
        registry.save(update_fields=[field])
        return

    convention = Convention.objects.create(
        name=f"Emergency attachment {attachment}",
        status=ConventionStatus.ACTIVE,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
    )
    if attachment == "enrollment":
        ConventionEnrollment.objects.create(user=actor, convention=convention)
        return

    owner = (
        actor
        if attachment == "owned_fursuit"
        else User.objects.create_user("other_emergency_attachment_owner_243")
    )
    fursuit = Fursuit.objects.create(
        owner=owner,
        name="Emergency attachment fursuit",
        photo_key="emergency/attachment.png",
    )
    if attachment == "owned_fursuit":
        return

    now = timezone.now()
    activation = FursuitActivation.objects.create(
        fursuit=fursuit,
        convention=convention,
        is_active=True,
        activated_at=now,
    )
    session = FursuitCatchSession.objects.create(
        activation=activation,
        started_at=now,
        expires_at=now + timedelta(hours=1),
    )
    Catch.objects.create(
        catcher_user=actor,
        fursuit=fursuit,
        convention=convention,
        activation=activation,
        catch_session=session,
    )


@pytest.mark.django_db
def test_read_only_emergency_state_is_absent_with_non_superusers() -> None:
    """Existing players or limited staff do not masquerade as a break-glass role."""
    player = User.objects.create_user("ordinary_player_emergency_status_243")
    managed = User(
        clerk_user_id="managed_emergency_status_243", is_staff=True, is_superuser=False
    )
    managed.set_password("managed-password-emergency-status-243")
    managed.save()
    before = (_state(player), _state(managed))

    assert _inspect_emergency_state() == "ABSENT"
    assert (_state(player), _state(managed)) == before


@pytest.mark.django_db
def test_read_only_emergency_state_requires_exact_staff_superuser(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The approved synthetic singleton is READY without exposing its identity."""
    user = _make_emergency()
    before = _state(user)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()

    assert _inspect_emergency_state() == "READY"
    assert _state(user) == before
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert IDENTIFIER not in caplog.text
    assert PASSWORD not in caplog.text


@pytest.mark.django_db
def test_read_only_emergency_state_recognizes_exact_retained_decommissioned_actor(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A retained audit actor with access removed has a distinct final state."""
    actor = _make_emergency()
    ordinary = User.objects.create_user("ordinary_emergency_status_neighbor_243")
    actor.is_staff = False
    actor.is_superuser = False
    actor.set_unusable_password()
    actor.save(update_fields={"is_staff", "is_superuser", "password"})
    before = (_state(actor), _state(ordinary))
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()

    assert _inspect_emergency_state() == "DECOMMISSIONED"
    assert (_state(actor), _state(ordinary)) == before
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert IDENTIFIER not in caplog.text
    assert PASSWORD not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mismatch",
    (
        "staff",
        "identifier",
        "group",
        "direct_permission",
        "attachment",
        "multiple",
    ),
)
def test_read_only_emergency_state_rejects_inexact_retained_actor(
    mismatch: str,
) -> None:
    """A disabled label must never mask a usable or ambiguously retained role."""
    actor = _make_emergency()
    actor.is_staff = False
    actor.is_superuser = False
    actor.set_unusable_password()
    actor.save(update_fields={"is_staff", "is_superuser", "password"})
    if mismatch == "staff":
        actor.is_staff = True
        actor.save(update_fields={"is_staff"})
    elif mismatch == "identifier":
        actor.clerk_user_id = "staging_emergency_bad-hyphen"
        actor.save(update_fields={"clerk_user_id"})
    elif mismatch == "group":
        actor.groups.add(Group.objects.create(name="retained emergency group"))  # pyright: ignore[reportUnknownMemberType]
    elif mismatch == "direct_permission":
        actor.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_user"
            )
        )
    elif mismatch == "attachment":
        PlayerProfile.objects.create(user=actor)
    else:
        second = _make_emergency("staging_emergency_second_243")
        second.is_staff = False
        second.is_superuser = False
        second.set_unusable_password()
        second.save(update_fields={"is_staff", "is_superuser", "password"})
    before = {row.pk: _state(row) for row in User.objects.all()}

    assert _inspect_emergency_state() == "MISMATCH"
    assert {row.pk: _state(row) for row in User.objects.all()} == before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mismatch",
    (
        "nonstaff",
        "unusable_password",
        "wrong_namespace",
        "group",
        "direct_permission",
        "multiple",
    ),
)
def test_read_only_emergency_state_classifies_inexact_superuser_as_mismatch(
    mismatch: str,
) -> None:
    """Presence alone is insufficient for the exact operational postcondition."""
    if mismatch == "nonstaff":
        user = _make_emergency(staff=False)
    elif mismatch == "unusable_password":
        user = _make_emergency(usable_password=False)
    elif mismatch == "wrong_namespace":
        user = _make_emergency("unrelated_superuser_243")
    else:
        user = _make_emergency()
        if mismatch == "group":
            user.groups.add(Group.objects.create(name="unexpected emergency group"))  # pyright: ignore[reportUnknownMemberType]
        elif mismatch == "direct_permission":
            user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
                Permission.objects.get(
                    content_type__app_label="accounts", codename="view_user"
                )
            )
        else:
            _make_emergency("staging_emergency_second_243")
    before = {row.pk: _state(row) for row in User.objects.all()}

    assert _inspect_emergency_state() == "MISMATCH"
    assert {row.pk: _state(row) for row in User.objects.all()} == before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "attachment",
    (
        "profile",
        "owned_fursuit",
        "enrollment",
        "catch",
        "sentinel_owner",
        "sentinel_catcher",
    ),
)
def test_read_only_emergency_state_rejects_attached_synthetic_actor(
    attachment: str,
) -> None:
    """An emergency actor with gameplay or #204 identity bindings is inexact."""
    _install_registry()
    actor = _make_emergency()
    _attach_emergency_gameplay_record(actor, attachment)
    before = _state(actor)

    assert _inspect_emergency_state() == "MISMATCH"
    assert _state(actor) == before


@pytest.mark.django_db
def test_read_only_emergency_state_query_failure_is_fixed_indeterminate(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed database read cannot imply either absence or readiness."""
    caplog.set_level(logging.DEBUG)

    def fail_query(
        _execute: object,
        _sql: str,
        _params: object,
        _many: bool,
        _context: object,
    ) -> NoReturn:
        raise DatabaseError("private-emergency-query-sentinel-243")

    capsys.readouterr()
    with connection.execute_wrapper(fail_query):
        result = _inspect_emergency_state()

    assert result == "INDETERMINATE"
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert "private-emergency-query-sentinel-243" not in caplog.text


@pytest.mark.parametrize(
    "arguments",
    (
        ("unexpected-identity-243", "--settings=config.settings.build"),
        ("--password", "unexpected-password-243", "--settings=config.settings.build"),
    ),
)
def test_command_parser_never_echoes_identifier_or_password_arguments(
    arguments: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        [sys.executable, "manage.py", COMMAND_NAME, *arguments],
        cwd=API_ROOT,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr == INVALID_ARGUMENTS


# The following tests describe the proposed post-Case-5 cleanup boundary. They
# intentionally remain RED until the separately reviewed decommission command
# exists. They do not authorize a live Staging action.
DECOMMISSION_COMMAND = "decommission_staging_emergency_operator"
DECOMMISSION_CONFIRMATION = "decommission Railway Staging emergency operator"
DECOMMISSION_SUCCESS = "Staging emergency operator decommissioned.\n"


def _invoke_decommission(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confirmation: str = DECOMMISSION_CONFIRMATION,
    stdin: StringIO | None = None,
    stdout: StringIO | None = None,
    stderr: StringIO | None = None,
) -> tuple[StringIO, StringIO, list[str]]:
    """Exercise only the public interactive command seam, without credentials."""
    stdin = stdin if stdin is not None else TtyStream()
    stdout = stdout if stdout is not None else TtyStream()
    stderr = stderr if stderr is not None else TtyStream()
    prompts: list[str] = []

    def confirmation_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return confirmation

    def forbidden_secret_prompt(_prompt: str = "") -> NoReturn:
        raise AssertionError("Decommission must not request an identity or credential")

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", confirmation_input)
    monkeypatch.setattr(getpass, "getpass", forbidden_secret_prompt)
    call_command(DECOMMISSION_COMMAND, stdout=stdout, stderr=stderr)
    return stdout, stderr, prompts


def _make_emergency_audit(actor: User) -> OperatorAuditEvent:
    return OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_FURSUIT_ENABLED,
        actor=actor,
        actor_class=OperatorActorClass.EMERGENCY_SUPERUSER,
        affected_record_type=OperatorTargetType.FURSUIT,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )


def test_emergency_decommission_command_is_registered() -> None:
    """The proposed cleanup action must be a repository-owned command."""
    assert DECOMMISSION_COMMAND in get_commands()


@pytest.mark.django_db
def test_emergency_decommission_revokes_access_and_preserves_actor_audit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Case 5 evidence survives after the exact synthetic actor loses access."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    actor = _make_emergency()
    audit = _make_emergency_audit(actor)
    original_audit = OperatorAuditEvent.objects.filter(pk=audit.pk).values().get()
    unrelated = User.objects.create_user("unrelated_decommission_player_243")
    unrelated_before = _state(unrelated)
    caplog.set_level(logging.DEBUG)

    stdout, stderr, prompts = _invoke_decommission(monkeypatch)

    actor.refresh_from_db()
    assert User.objects.filter(pk=actor.pk, clerk_user_id=IDENTIFIER).exists()
    assert actor.is_staff is False
    assert cast(bool, actor.is_superuser) is False  # pyright: ignore[reportUnknownMemberType]
    assert actor.has_usable_password() is False
    assert actor.check_password(PASSWORD) is False
    assert actor.groups.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert actor.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert (
        OperatorAuditEvent.objects.filter(pk=audit.pk).values().get() == original_audit
    )
    assert _state(unrelated) == unrelated_before
    assert stdout.getvalue() == DECOMMISSION_SUCCESS
    assert stderr.getvalue() == ""
    assert len(prompts) == 1
    assert prompts[0].startswith("Confirmation")
    _assert_private(stdout, stderr, None, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "attachment",
    (
        "profile",
        "owned_fursuit",
        "enrollment",
        "catch",
        "sentinel_owner",
        "sentinel_catcher",
    ),
)
def test_emergency_decommission_refuses_attached_synthetic_actor(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    attachment: str,
) -> None:
    """Unexpected domain or reset ownership must not be silently cleaned up."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    actor = _make_emergency()
    _attach_emergency_gameplay_record(actor, attachment)
    audit = _make_emergency_audit(actor)
    before = _state(actor)
    audit_before = OperatorAuditEvent.objects.filter(pk=audit.pk).values().get()
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke_decommission(monkeypatch, stdout=stdout, stderr=stderr)

    assert _state(actor) == before
    assert OperatorAuditEvent.objects.filter(pk=audit.pk).values().get() == audit_before
    assert stdout.getvalue() == ""
    _assert_private(stdout, stderr, error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    ("ordinary", "managed", "limited", "wrong_namespace", "missing"),
)
def test_emergency_decommission_refuses_non_dedicated_identity(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    role: str,
) -> None:
    """No ordinary or non-emergency operator may be adopted for cleanup."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    candidate: User | None = None
    if role == "ordinary":
        candidate = User.objects.create_user(IDENTIFIER)
    elif role in ("managed", "limited"):
        candidate = User(clerk_user_id=IDENTIFIER, is_staff=True, is_superuser=False)
        candidate.set_password("other-operator-password-243")
        candidate.save()
        if role == "managed":
            candidate.groups.add(  # pyright: ignore[reportUnknownMemberType]
                Group.objects.create(name="TailTag Field Beta Operators")
            )
        else:
            candidate.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
                Permission.objects.get(
                    content_type__app_label="profiles", codename="set_profile_enabled"
                )
            )
    elif role == "wrong_namespace":
        candidate = _make_emergency("other_break_glass_identity_243")
    before = _state(candidate) if candidate is not None else None
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke_decommission(monkeypatch, stdout=stdout, stderr=stderr)

    assert stdout.getvalue() == ""
    if candidate is not None:
        assert _state(candidate) == before
    assert User.objects.filter(is_superuser=True).count() == (
        1 if role == "wrong_namespace" else 0
    )
    _assert_private(
        stdout,
        stderr,
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "other_break_glass_identity_243",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "drift",
    ("nonstaff", "unusable_password", "group", "direct_permission", "second_superuser"),
)
def test_emergency_decommission_refuses_drift_or_ambiguous_authority(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    drift: str,
) -> None:
    """Any inexact or multiple emergency authorities require investigation."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    actor = _make_emergency()
    if drift == "nonstaff":
        actor.is_staff = False
        actor.set_unusable_password()
        actor.save(update_fields={"is_staff", "password"})
    elif drift == "unusable_password":
        actor.set_unusable_password()
        actor.save(update_fields={"password"})
    elif drift == "group":
        actor.groups.add(Group.objects.create(name="unapproved emergency group"))  # pyright: ignore[reportUnknownMemberType]
    elif drift == "direct_permission":
        actor.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_user"
            )
        )
    else:
        _make_emergency("staging_emergency_second_243")
    audit = _make_emergency_audit(actor)
    before = {row.pk: _state(row) for row in User.objects.all()}
    audit_before = OperatorAuditEvent.objects.filter(pk=audit.pk).values().get()
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke_decommission(monkeypatch, stdout=stdout, stderr=stderr)

    assert {row.pk: _state(row) for row in User.objects.all()} == before
    assert OperatorAuditEvent.objects.filter(pk=audit.pk).values().get() == audit_before
    assert stdout.getvalue() == ""
    _assert_private(stdout, stderr, error.value, caplog, IDENTIFIER, PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "service_name", "project_id", "environment_id", "service_id"),
    (
        ("development", "api", PROJECT, ENVIRONMENT, SERVICE),
        ("staging", "worker", PROJECT, ENVIRONMENT, SERVICE),
        ("staging", "api", OTHER, ENVIRONMENT, SERVICE),
        ("staging", "api", PROJECT, OTHER, SERVICE),
        ("staging", "api", PROJECT, ENVIRONMENT, OTHER),
        ("staging", "api", None, ENVIRONMENT, SERVICE),
    ),
)
def test_emergency_decommission_refuses_wrong_replacement_target(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    service_name: str,
    project_id: str | None,
    environment_id: str,
    service_id: str,
) -> None:
    """The command must refuse every selector outside the pinned staging API."""
    _pin_test_target(monkeypatch)
    _set_target(
        monkeypatch,
        name=name,
        service_name=service_name,
        project_id=project_id,
        environment_id=environment_id,
        service_id=service_id,
    )
    actor = _make_emergency()
    before = _state(actor)
    stdout = TtyStream()

    with pytest.raises(CommandError):
        _invoke_decommission(monkeypatch, stdout=stdout)

    assert _state(actor) == before
    assert stdout.getvalue() == ""


@pytest.mark.django_db
@pytest.mark.parametrize("stream", ("stdin", "stdout"))
def test_emergency_decommission_requires_real_tty(
    monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    actor = _make_emergency()
    before = _state(actor)
    stdin = NonTtyStream() if stream == "stdin" else TtyStream()
    stdout = NonTtyStream() if stream == "stdout" else TtyStream()

    with pytest.raises(CommandError):
        _invoke_decommission(monkeypatch, stdin=stdin, stdout=stdout)

    assert _state(actor) == before
    assert stdout.getvalue() == ""


@pytest.mark.django_db
def test_emergency_decommission_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    actor = _make_emergency()
    before = _state(actor)
    stdout = TtyStream()

    with pytest.raises(CommandError):
        _invoke_decommission(
            monkeypatch, confirmation="wrong confirmation", stdout=stdout
        )

    assert _state(actor) == before
    assert stdout.getvalue() == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mismatch", ("missing", "registry_database", "registry_cluster", "django_database")
)
def test_emergency_decommission_refuses_unbound_database(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    """A stale #204 singleton or connected binding cannot authorize cleanup."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    actor = _make_emergency()
    before = _state(actor)
    if mismatch != "missing":
        registry = _install_registry()
        if mismatch == "registry_database":
            registry.database_name = "different_private_database_243"
            registry.save(update_fields=["database_name"])
        elif mismatch == "registry_cluster":
            registry.cluster_identifier = "999999999"
            registry.save(update_fields=["cluster_identifier"])
        else:
            monkeypatch.setitem(
                django_settings.DATABASES["default"],
                "NAME",
                "different_private_database_243",
            )
    stdout = TtyStream()

    with pytest.raises(CommandError):
        _invoke_decommission(monkeypatch, stdout=stdout)

    assert _state(actor) == before
    assert stdout.getvalue() == ""


@pytest.mark.django_db
def test_emergency_decommission_query_failure_is_sanitized_and_nonmutating(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown connected PostgreSQL identity cannot authorize decommission."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    actor = _make_emergency()
    before = _state(actor)
    caplog.set_level(logging.DEBUG)

    original_cursor = connection.cursor
    query_attempted = False

    class FactFailureCursor:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate

        def __enter__(self) -> Self:
            self.delegate.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.delegate.__exit__(*args)

        def execute(self, sql: str, params: object = None) -> object:
            nonlocal query_attempted
            if "pg_control_system" in sql:
                query_attempted = True
                raise DatabaseError("private-decommission-query-sentinel-243")
            return self.delegate.execute(sql, params)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.delegate, name)

    def fail_database_fact_query(*args: object, **kwargs: object) -> FactFailureCursor:
        return FactFailureCursor(original_cursor(*args, **kwargs))

    monkeypatch.setattr(connection, "cursor", fail_database_fact_query)
    stdout, stderr = TtyStream(), TtyStream()
    try:
        with pytest.raises(CommandError) as error:
            _invoke_decommission(monkeypatch, stdout=stdout, stderr=stderr)
    finally:
        monkeypatch.setattr(connection, "cursor", original_cursor)

    assert query_attempted is True
    assert _state(actor) == before
    assert stdout.getvalue() == ""
    _assert_private(
        stdout,
        stderr,
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "private-decommission-query-sentinel-243",
    )


@pytest.mark.django_db(transaction=True)
def test_emergency_decommission_rolls_back_partial_user_update(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A database failure after an account update cannot leave partial cleanup."""
    _pin_test_target(monkeypatch)
    _set_target(monkeypatch)
    _install_registry()
    actor = _make_emergency()
    audit = _make_emergency_audit(actor)
    before = _state(actor)
    audit_before = OperatorAuditEvent.objects.filter(pk=audit.pk).values().get()
    original_save = User.save

    def save_then_fail(self: User, **kwargs: Any) -> None:
        original_save(self, **kwargs)
        if self.pk == actor.pk and not self.is_staff:
            raise DatabaseError("private-decommission-failure-sentinel-243")

    monkeypatch.setattr(User, "save", save_then_fail)
    caplog.set_level(logging.DEBUG)
    stdout, stderr = TtyStream(), TtyStream()

    with pytest.raises(CommandError) as error:
        _invoke_decommission(monkeypatch, stdout=stdout, stderr=stderr)

    assert _state(actor) == before
    assert OperatorAuditEvent.objects.filter(pk=audit.pk).values().get() == audit_before
    assert stdout.getvalue() == ""
    _assert_private(
        stdout,
        stderr,
        error.value,
        caplog,
        IDENTIFIER,
        PASSWORD,
        "private-decommission-failure-sentinel-243",
    )


@pytest.mark.parametrize(
    "arguments",
    (
        ("unexpected-identity-243", "--settings=config.settings.build"),
        ("--password", "unexpected-password-243", "--settings=config.settings.build"),
    ),
)
def test_emergency_decommission_parser_never_echoes_identity_or_secret_arguments(
    arguments: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        [sys.executable, "manage.py", DECOMMISSION_COMMAND, *arguments],
        cwd=API_ROOT,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr == INVALID_ARGUMENTS
