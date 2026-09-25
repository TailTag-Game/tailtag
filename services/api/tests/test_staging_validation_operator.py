"""Acceptance coverage for the dedicated #243 limited validation operator."""

from __future__ import annotations

import builtins
import getpass
import hashlib
import importlib
import logging
import os
import pty
import select
import signal
import sys
import termios
import time
from collections.abc import Callable, Iterable
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection
from django.db.models.base import ModelBase
from django.utils import timezone
from pytest_django.fixtures import SettingsWrapper

from accounts.models import User
from catches.models import Catch
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

COMMAND_MODULE = "accounts.management.commands.staging_validation_operator"
COMMAND_NAME = "staging_validation_operator"
GROUP_NAME = "TailTag #243 Validation Operator"
PROVISION_CONFIRMATION = "provision Railway Staging validation operator"
DECOMMISSION_CONFIRMATION = "decommission Railway Staging validation operator"
ROTATE_CONFIRMATION = "rotate Railway Staging validation operator password"
OPERATOR_IDENTIFIER = "validation_operator_243"
INITIAL_PASSWORD = "validation-operator-password-2026"
ROTATED_PASSWORD = "validation-operator-rotated-password-2026"
LIMITED_PERMISSION_NAMES = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)
EXTRA_SENSITIVE_PERMISSION = "fursuits.set_fursuit_enabled"
API_ROOT = Path(__file__).resolve().parents[1]
MANAGED_PERMISSION_NAMES = frozenset(
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


@pytest.fixture(autouse=True)
def non_debug_command_boundary(
    settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give every positive command test the required non-query-logging boundary."""
    settings.DEBUG = False
    monkeypatch.setattr(connection, "force_debug_cursor", False)


class TtyStream(StringIO):
    """Controlled terminal stream for command tests without live input."""

    def isatty(self) -> bool:
        return True


class NonTtyStream(StringIO):
    """Redirected stream proving the command refuses unavailable hidden input."""

    def isatty(self) -> bool:
        return False


def permission_name(permission: Permission) -> str:
    """Return a stable Django permission name."""
    return f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]


def permissions_by_name() -> dict[str, Permission]:
    """Resolve the contract permissions from the real Django registry."""
    resolved = {
        permission_name(permission): permission
        for permission in Permission.objects.select_related("content_type")
        if permission_name(permission) in MANAGED_PERMISSION_NAMES
    }
    assert set(resolved) == MANAGED_PERMISSION_NAMES
    return resolved


def group_permission_ids(group: Group) -> set[int]:
    """Project a dynamic Django relation to its stable primary-key set."""
    return set(
        group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
    )


def create_user(
    identifier: str,
    *,
    is_staff: bool = True,
    is_superuser: bool = False,
    password: str | None = INITIAL_PASSWORD,
) -> User:
    """Create a disposable local identity without using the user manager shortcut."""
    user = User(
        clerk_user_id=identifier,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    user.set_password(password)
    user.save()
    return user


def create_exact_limited_operator(
    *, identifier: str = OPERATOR_IDENTIFIER, password: str = INITIAL_PASSWORD
) -> User:
    """Seed the sole active limited role shape permitted for reconciliation."""
    operator = create_user(identifier, password=password)
    group = Group.objects.create(name=GROUP_NAME)
    group.permissions.set(  # pyright: ignore[reportUnknownMemberType]
        permissions_by_name()[name] for name in LIMITED_PERMISSION_NAMES
    )
    operator.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
    return operator


def create_exact_managed_operator(identifier: str = "managed_operator_205") -> User:
    """Seed an existing normal managed role that this command must never adopt."""
    operator = create_user(identifier)
    group = Group.objects.create(name="TailTag Field Beta Operators")
    group.permissions.set(  # pyright: ignore[reportUnknownMemberType]
        permissions_by_name()[name] for name in MANAGED_PERMISSION_NAMES
    )
    operator.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
    return operator


def attach_gameplay_record(operator: User, attachment: str) -> None:
    """Create the minimal prohibited gameplay relationship for one candidate."""
    if attachment == "profile":
        PlayerProfile.objects.create(user=operator)
        return

    convention = Convention.objects.create(
        name=f"Validation contract {attachment}",
        status=ConventionStatus.ACTIVE,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
    )
    if attachment == "enrollment":
        ConventionEnrollment.objects.create(user=operator, convention=convention)
        return

    owner = operator if attachment == "fursuit" else create_user("other_fursuit_owner")
    fursuit = Fursuit.objects.create(
        owner=owner,
        name="Validation Fursuit",
        photo_key="validation/photo.png",
    )
    if attachment == "fursuit":
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
        catcher_user=operator,
        fursuit=fursuit,
        convention=convention,
        activation=activation,
        catch_session=session,
    )


def exact_limited_state(operator: User) -> dict[str, object]:
    """Capture the contract state needed to prove a guarded refusal made no write."""
    return {
        "staff": operator.is_staff,
        "superuser": cast(
            bool,
            operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        ),
        "usable_password": operator.has_usable_password(),
        "password_fingerprint": hashlib.sha256(
            cast(
                str,
                operator.password,  # pyright: ignore[reportUnknownMemberType]
            ).encode()
        ).hexdigest(),
        "groups": {
            cast(
                str,
                group.name,  # pyright: ignore[reportUnknownMemberType]
            ): frozenset(
                permission_name(permission)
                for permission in group.permissions.select_related("content_type")  # pyright: ignore[reportUnknownMemberType]
            )
            for group in operator.groups.all()  # pyright: ignore[reportUnknownMemberType]
        },
        "direct_permissions": frozenset(
            permission_name(permission)
            for permission in operator.user_permissions.select_related("content_type")  # pyright: ignore[reportUnknownMemberType]
        ),
    }


def assert_exact_active_limited_role(operator: User, password: str) -> None:
    """Assert the frozen active role, including its deliberately narrow authority."""
    operator.refresh_from_db()
    assert operator.is_staff is True
    assert (
        cast(
            bool,
            operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        )
        is False
    )
    assert operator.check_password(password)
    assert operator.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert operator.groups.count() == 1  # pyright: ignore[reportUnknownMemberType]
    group = operator.groups.get()  # pyright: ignore[reportUnknownMemberType]
    assert group.name == GROUP_NAME  # pyright: ignore[reportUnknownMemberType]
    assert set(operator.get_all_permissions()) == LIMITED_PERMISSION_NAMES
    assert {
        permission_name(permission)
        for permission in group.permissions.select_related("content_type")  # pyright: ignore[reportUnknownMemberType]
    } == LIMITED_PERMISSION_NAMES
    assert User.objects.filter(groups=group).count() == 1


def assert_private_values_absent(
    streams: Iterable[StringIO],
    *private_values: str,
    exception_text: str = "",
    caplog: pytest.LogCaptureFixture | None = None,
) -> None:
    """Keep hidden inputs, hashes, and permission details out of all output."""
    rendered = "".join(stream.getvalue() for stream in streams) + exception_text
    log_material = () if caplog is None else (caplog.text,)
    for value in (value for value in private_values if value):
        assert value not in rendered
        assert all(value not in item for item in log_material)


def invoke_command(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    *,
    confirmation: str | None = None,
    hidden_inputs: Iterable[str] = (),
    environment: str | None = "staging",
    service: str | None = "api",
    stdin: StringIO | None = None,
    stdout: StringIO | None = None,
    stderr: StringIO | None = None,
    hidden_prompts: list[str] | None = None,
    after_hidden_prompt: Callable[[str], None] | None = None,
) -> tuple[StringIO, StringIO]:
    """Run the public command through controlled TTY and getpass surfaces."""
    values = tuple(hidden_inputs)
    stdin = stdin or TtyStream()
    stdout = stdout or TtyStream()
    stderr = stderr or TtyStream()
    inputs = iter(values)

    def hidden_input(prompt: str, stream: Any | None = None) -> str:
        del stream
        if hidden_prompts is not None:
            hidden_prompts.append(prompt)
        if after_hidden_prompt is not None:
            after_hidden_prompt(prompt)
        try:
            return next(inputs)
        except StopIteration as error:
            raise AssertionError("unexpected hidden prompt") from error

    try:
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        monkeypatch.setattr(builtins, "input", confirmation_input(confirmation))
        monkeypatch.setattr(getpass, "getpass", hidden_input)
        if environment is None:
            monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
        else:
            monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
        if service is None:
            monkeypatch.delenv("RAILWAY_SERVICE_NAME", raising=False)
        else:
            monkeypatch.setenv("RAILWAY_SERVICE_NAME", service)
        call_command(COMMAND_NAME, action, stdout=stdout, stderr=stderr)
    finally:
        after = dict(os.environ)
        for value in (value for value in values if value):
            assert all(value not in item for item in after.values())
    return stdout, stderr


def confirmation_input(value: str | None) -> Callable[[str], str]:
    """Return a typed public confirmation reader for a controlled test terminal."""

    def read_confirmation(prompt: str = "") -> str:
        del prompt
        return value or ""

    return read_confirmation


def run_provision_with_real_pty(
    *, identifier: str, password: str, confirmation_password: str
) -> tuple[int, str]:
    """Exercise getpass on a disposable local controlling terminal.

    The password mismatch reaches every hidden prompt before any provisioning
    write, so this subprocess never creates an account or group.
    """
    settings = connection.settings_dict
    database_url = (
        "postgresql://"
        f"{settings['USER']}:{settings['PASSWORD']}@"
        f"{settings['HOST']}:{settings['PORT']}/{settings['NAME']}"
    )
    environment = {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "local-pty-command-test",
        "DJANGO_ALLOWED_HOSTS": "localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://localhost",
        "DATABASE_URL": database_url,
        "CLERK_AUTHENTICATION_ENABLED": "false",
        "MEDIA_STORAGE_ENDPOINT_URL": "https://media.example.test",
        "MEDIA_STORAGE_BUCKET_NAME": "test-bucket",
        "MEDIA_STORAGE_REGION": "test-region",
        "MEDIA_STORAGE_ACCESS_KEY_ID": "test-access-key",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY": "test-secret-key",
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_SERVICE_NAME": "api",
        "PYTHONPATH": str(API_ROOT),
    }
    process_id, terminal = pty.fork()
    if process_id == 0:
        os.chdir(API_ROOT)
        os.execve(
            sys.executable,
            [sys.executable, "manage.py", COMMAND_NAME, "provision"],
            environment,
        )

    transcript = bytearray()

    def read_until(expected: bytes) -> None:
        deadline = time.monotonic() + 10
        while expected not in transcript:
            readable, _, _ = select.select([terminal], [], [], 0.1)
            if readable:
                try:
                    chunk = os.read(terminal, 1024)
                except OSError:
                    chunk = b""
                if chunk:
                    transcript.extend(chunk)
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"did not receive expected terminal prompt {expected!r}"
                )

    try:
        for prompt, response in (
            (b"Confirmation: ", PROVISION_CONFIRMATION),
            (b"Operator identifier: ", identifier),
            (b"Password: ", password),
            (b"Confirm password: ", confirmation_password),
        ):
            read_until(prompt)
            os.write(terminal, f"{response}\n".encode())

        deadline = time.monotonic() + 10
        while True:
            completed, status = os.waitpid(process_id, os.WNOHANG)
            readable, _, _ = select.select([terminal], [], [], 0)
            if readable:
                try:
                    transcript.extend(os.read(terminal, 1024))
                except OSError:
                    pass
            if completed:
                return os.waitstatus_to_exitcode(status), transcript.decode(
                    errors="replace"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("PTY command did not exit")
            time.sleep(0.01)
    except BaseException:
        os.kill(process_id, signal.SIGKILL)
        os.waitpid(process_id, 0)
        raise
    finally:
        os.close(terminal)


@pytest.mark.django_db
def test_provision_creates_one_exact_dedicated_limited_operator(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-1/2/3/4/6: provision creates exactly the frozen narrow role."""
    caplog.set_level(logging.DEBUG)
    stdout, stderr = invoke_command(
        monkeypatch,
        "provision",
        confirmation=PROVISION_CONFIRMATION,
        hidden_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
    )
    operator = User.objects.get(clerk_user_id=OPERATOR_IDENTIFIER)
    assert_exact_active_limited_role(operator, INITIAL_PASSWORD)
    assert_private_values_absent(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        cast(
            str,
            operator.password,  # pyright: ignore[reportUnknownMemberType]
        ),
        *LIMITED_PERMISSION_NAMES,
        caplog=caplog,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(os.name == "nt", reason="requires a POSIX controlling terminal")
def test_real_pty_keeps_hidden_identifier_and_passwords_out_of_terminal_echo() -> None:
    """AC-1/4: real getpass input is hidden rather than merely mocked as hidden."""
    identifier = "pty-hidden-identifier-243"
    password = "pty-hidden-password-243"
    confirmation_password = "pty-hidden-confirmation-243"

    return_code, transcript = run_provision_with_real_pty(
        identifier=identifier,
        password=password,
        confirmation_password=confirmation_password,
    )

    assert return_code != 0
    assert "Passwords do not match." in transcript
    assert identifier not in transcript
    assert password not in transcript
    assert confirmation_password not in transcript
    assert not User.objects.filter(clerk_user_id=identifier).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(os.name == "nt", reason="requires a POSIX controlling terminal")
def test_real_pty_terminal_setup_failure_refuses_getpass_fallback_before_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4: a real terminal echo-disable failure cannot fall back to input()."""
    command_module = importlib.import_module(COMMAND_MODULE)

    def fail_terminal_configuration(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise OSError("synthetic terminal configuration failure")

    monkeypatch.setattr(termios, "tcsetattr", fail_terminal_configuration)
    process_id, terminal = pty.fork()
    if process_id == 0:
        try:
            command_module._hidden_input("Operator identifier: ")
        except CommandError:
            os._exit(0)
        os._exit(1)

    transcript = bytearray()
    try:
        deadline = time.monotonic() + 10
        while True:
            completed, status = os.waitpid(process_id, os.WNOHANG)
            readable, _, _ = select.select([terminal], [], [], 0)
            if readable:
                try:
                    transcript.extend(os.read(terminal, 1024))
                except OSError:
                    pass
            if completed:
                assert os.waitstatus_to_exitcode(status) == 0
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("PTY fallback check did not exit")
            time.sleep(0.01)
    except BaseException:
        os.kill(process_id, signal.SIGKILL)
        os.waitpid(process_id, 0)
        raise
    finally:
        os.close(terminal)

    assert OPERATOR_IDENTIFIER.encode() not in transcript
    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
def test_provision_reconciles_only_the_exact_active_limited_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/3: an idempotent rerun may rotate a password, never widen authority."""
    operator = create_exact_limited_operator()
    original_pk = operator.pk

    invoke_command(
        monkeypatch,
        "provision",
        confirmation=PROVISION_CONFIRMATION,
        hidden_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
    )

    operator.refresh_from_db()
    assert operator.pk == original_pk
    assert_exact_active_limited_role(operator, ROTATED_PASSWORD)
    assert not operator.check_password(INITIAL_PASSWORD)


@pytest.mark.django_db
def test_rotate_password_keeps_exact_limited_actor_authority_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A password-only recovery retains the actor and its narrow authority."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=limited,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    before_limited = exact_limited_state(limited)
    before_managed = exact_limited_state(managed)
    before_audit = tuple(OperatorAuditEvent.objects.values_list())
    prompts: list[str] = []
    stdout, stderr = invoke_command(
        monkeypatch,
        "rotate_password",
        confirmation=ROTATE_CONFIRMATION,
        hidden_inputs=(ROTATED_PASSWORD, ROTATED_PASSWORD),
        hidden_prompts=prompts,
    )

    limited.refresh_from_db()
    managed.refresh_from_db()
    assert limited.check_password(ROTATED_PASSWORD)
    assert not limited.check_password(INITIAL_PASSWORD)
    after_limited = exact_limited_state(limited)
    assert {
        key: value
        for key, value in after_limited.items()
        if key != "password_fingerprint"
    } == {
        key: value
        for key, value in before_limited.items()
        if key != "password_fingerprint"
    }
    assert exact_limited_state(managed) == before_managed
    assert tuple(OperatorAuditEvent.objects.values_list()) == before_audit
    assert OperatorAuditEvent.objects.filter(pk=audit.pk, actor=limited).count() == 1
    assert prompts == ["Password: ", "Confirm password: "]
    assert_private_values_absent(
        (stdout, stderr), OPERATOR_IDENTIFIER, INITIAL_PASSWORD, ROTATED_PASSWORD
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure",
    (
        "environment",
        "service",
        "stdin",
        "stdout",
        "confirmation",
        "missing",
        "ambiguous",
        "group_drift",
        "permission_drift",
        "direct_permission",
        "superuser",
        "password_mismatch",
        "password_policy",
    ),
)
def test_rotate_password_refuses_inexact_target_role_or_secret_without_write(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Rotation cannot select or change an inexact limited role."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    if failure == "missing":
        limited.delete()
    elif failure == "ambiguous":
        create_user("second_limited_candidate").user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            permissions_by_name()["profiles.set_profile_enabled"]
        )
    elif failure == "group_drift":
        limited.groups.add(Group.objects.create(name="unrelated group"))  # pyright: ignore[reportUnknownMemberType]
    elif failure == "permission_drift":
        limited.groups.get().permissions.add(  # pyright: ignore[reportUnknownMemberType]
            permissions_by_name()[EXTRA_SENSITIVE_PERMISSION]
        )
    elif failure == "direct_permission":
        limited.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            permissions_by_name()["profiles.set_profile_enabled"]
        )
    elif failure == "superuser":
        limited.is_superuser = True
        limited.save(update_fields={"is_superuser"})
    before = tuple(
        User.objects.values_list("pk", "password", "is_staff", "is_superuser")
    )
    managed_before = exact_limited_state(managed)
    kwargs: dict[str, Any] = {}
    if failure == "environment":
        kwargs["environment"] = "production"
    elif failure == "service":
        kwargs["service"] = "worker"
    elif failure == "stdin":
        kwargs["stdin"] = NonTtyStream()
    elif failure == "stdout":
        kwargs["stdout"] = NonTtyStream()
    kwargs["confirmation"] = (
        "wrong phrase" if failure == "confirmation" else ROTATE_CONFIRMATION
    )
    kwargs["hidden_inputs"] = (
        (ROTATED_PASSWORD, "different-rotated-password-2026")
        if failure == "password_mismatch"
        else ("short", "short")
        if failure == "password_policy"
        else (ROTATED_PASSWORD, ROTATED_PASSWORD)
    )
    with pytest.raises(CommandError) as error:
        invoke_command(monkeypatch, "rotate_password", **kwargs)
    assert (
        tuple(User.objects.values_list("pk", "password", "is_staff", "is_superuser"))
        == before
    )
    assert exact_limited_state(managed) == managed_before
    assert_private_values_absent(
        (),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        exception_text=str(error.value),
    )


@pytest.mark.django_db
def test_rotate_password_rechecks_limited_role_after_hidden_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A role changed while the operator types cannot inherit prior approval."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    old_hash = cast(str, limited.password)  # pyright: ignore[reportUnknownMemberType]
    managed_before = exact_limited_state(managed)
    changed = False

    def drift(prompt: str) -> None:
        nonlocal changed
        if prompt == "Password: " and not changed:
            changed = True
            limited.groups.clear()  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "rotate_password",
            confirmation=ROTATE_CONFIRMATION,
            hidden_inputs=(ROTATED_PASSWORD, ROTATED_PASSWORD),
            after_hidden_prompt=drift,
        )

    limited.refresh_from_db()
    assert changed
    assert cast(str, limited.password) == old_hash  # pyright: ignore[reportUnknownMemberType]
    assert exact_limited_state(managed) == managed_before


@pytest.mark.django_db(transaction=True)
def test_rotate_password_database_failure_rolls_back_password_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a failure after the password save leaves the old credential usable."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    old_hash = cast(str, limited.password)  # pyright: ignore[reportUnknownMemberType]
    managed_before = exact_limited_state(managed)
    original_save = User.save
    raised = False

    def fail_after_save(self: User, *args: Any, **kwargs: Any) -> None:
        nonlocal raised
        original_save(self, *args, **kwargs)
        if self.pk == limited.pk and kwargs.get("update_fields") == {"password"}:
            raised = True
            raise DatabaseError("private database detail must not escape")

    monkeypatch.setattr(User, "save", fail_after_save)
    stdout = TtyStream()
    stderr = TtyStream()
    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            "rotate_password",
            confirmation=ROTATE_CONFIRMATION,
            hidden_inputs=(ROTATED_PASSWORD, ROTATED_PASSWORD),
            stdout=stdout,
            stderr=stderr,
        )

    limited.refresh_from_db()
    assert raised
    assert cast(str, limited.password) == old_hash  # pyright: ignore[reportUnknownMemberType]
    assert exact_limited_state(managed) == managed_before
    assert_private_values_absent(
        (stdout, stderr),
        OPERATOR_IDENTIFIER,
        INITIAL_PASSWORD,
        ROTATED_PASSWORD,
        "private database detail must not escape",
        exception_text=str(error.value),
    )


@pytest.mark.django_db(transaction=True)
def test_rotate_password_failed_postcondition_rolls_back_password_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed after-write role check must not leave a committed new secret."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    old_hash = cast(str, limited.password)  # pyright: ignore[reportUnknownMemberType]
    managed_before = exact_limited_state(managed)
    command_module = importlib.import_module(COMMAND_MODULE)
    original_check = command_module.Command._active_exact
    after_write_reached = False

    def fail_after_write(
        self: Any, operator: User, permissions: tuple[Permission, ...]
    ) -> bool:
        nonlocal after_write_reached
        if operator.check_password(ROTATED_PASSWORD):
            after_write_reached = True
            return False
        return cast(bool, original_check(self, operator, permissions))

    monkeypatch.setattr(
        command_module.Command,
        "_active_exact",
        fail_after_write,
    )
    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "rotate_password",
            confirmation=ROTATE_CONFIRMATION,
            hidden_inputs=(ROTATED_PASSWORD, ROTATED_PASSWORD),
        )

    limited.refresh_from_db()
    assert after_write_reached
    assert cast(str, limited.password) == old_hash  # pyright: ignore[reportUnknownMemberType]
    assert exact_limited_state(managed) == managed_before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "collision",
    (
        "ordinary_player",
        "superuser",
        "managed_operator",
        "other_group",
        "direct_permission",
        "shared_group",
        "group_permission_missing",
        "group_permission_drift",
    ),
)
def test_provision_refuses_colliding_or_drifted_identity_without_mutation(
    monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    """AC-2/6: provision never adopts, elevates, or repurposes an existing account."""
    permissions = permissions_by_name()
    if collision == "ordinary_player":
        protected = create_user(OPERATOR_IDENTIFIER, is_staff=False, password=None)
    elif collision == "superuser":
        protected = create_user(OPERATOR_IDENTIFIER, is_superuser=True)
    elif collision == "managed_operator":
        protected = create_exact_managed_operator(OPERATOR_IDENTIFIER)
    else:
        protected = create_exact_limited_operator()
        if collision == "other_group":
            protected.groups.add(Group.objects.create(name="unrelated group"))  # pyright: ignore[reportUnknownMemberType]
        elif collision == "direct_permission":
            protected.user_permissions.add(permissions["profiles.set_profile_enabled"])  # pyright: ignore[reportUnknownMemberType]
        elif collision == "shared_group":
            create_user("second_validation_group_member").groups.add(  # pyright: ignore[reportUnknownMemberType]
                protected.groups.get()  # pyright: ignore[reportUnknownMemberType]
            )
        else:
            group = protected.groups.get()  # pyright: ignore[reportUnknownMemberType]
            if collision == "group_permission_missing":
                group.permissions.remove(  # pyright: ignore[reportUnknownMemberType]
                    permissions["profiles.view_playerprofile"]
                )
            else:
                group.permissions.add(  # pyright: ignore[reportUnknownMemberType]
                    permissions[EXTRA_SENSITIVE_PERMISSION]
                )
    state_before = exact_limited_state(protected)

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == state_before


@pytest.mark.django_db
def test_provision_refuses_existing_dedicated_group_before_creating_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: a pre-existing dedicated group is never silently adopted."""
    Group.objects.create(name=GROUP_NAME)

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
def test_provision_requires_both_frozen_permissions_before_any_identity_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: unavailable approved authority must fail before creating the actor."""
    permissions_by_name()["profiles.set_profile_enabled"].delete()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()
    assert not Group.objects.filter(name=GROUP_NAME).exists()


@pytest.mark.django_db
def test_provision_rejects_duplicate_permission_name_when_the_other_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: duplicate names cannot disguise an incomplete permission registry."""
    permissions = permissions_by_name()
    duplicate_type = ContentType.objects.create(
        app_label="profiles", model="validation_operator_duplicate"
    )
    Permission.objects.create(
        content_type=duplicate_type,
        codename="set_profile_enabled",
        name="Duplicate validation permission",
    )
    permissions["profiles.view_playerprofile"].delete()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()
    assert not Group.objects.filter(name=GROUP_NAME).exists()


@pytest.mark.django_db
def test_managed_bootstrap_refuses_to_reconcile_the_dedicated_limited_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6: the normal managed bootstrap cannot turn the limited actor into admin."""
    limited = create_exact_limited_operator()
    before = exact_limited_state(limited)
    monkeypatch.setattr(sys, "stdin", TtyStream())
    monkeypatch.setattr(sys, "stdout", TtyStream())
    monkeypatch.setattr(
        builtins, "input", confirmation_input("bootstrap Railway Staging operator")
    )

    def managed_hidden_input(prompt: str, stream: Any | None = None) -> str:
        del stream
        return (
            OPERATOR_IDENTIFIER
            if prompt == "Operator identifier: "
            else ROTATED_PASSWORD
        )

    monkeypatch.setattr(getpass, "getpass", managed_hidden_input)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "api")

    with pytest.raises(CommandError):
        call_command("bootstrap_staging_operator")

    limited.refresh_from_db()
    assert exact_limited_state(limited) == before


@pytest.mark.django_db
@pytest.mark.parametrize("attachment", ("profile", "fursuit", "enrollment", "catch"))
def test_provision_refuses_candidate_with_any_gameplay_attachment(
    monkeypatch: pytest.MonkeyPatch, attachment: str
) -> None:
    """AC-2: the synthetic operator may never acquire product participation state."""
    protected = create_exact_limited_operator()
    attach_gameplay_record(protected, attachment)
    before = exact_limited_state(protected)

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD),
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("provision", "decommission"))
def test_role_reconciliation_refuses_when_group_is_renamed_before_locked_fetch(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """AC-2/5: a stale pre-lock group name cannot authorize either lifecycle action."""
    protected = create_exact_limited_operator()
    group = protected.groups.get()  # pyright: ignore[reportUnknownMemberType]
    before = exact_limited_state(protected)
    original_select_for_update = Group.objects.select_for_update
    locked_names: list[str] = []

    class RenameBeforeLockedFetch:
        def get(self, *, pk: int) -> Group:
            Group.objects.filter(pk=pk).update(name="renamed-during-lock-acquisition")
            locked = original_select_for_update().get(pk=pk)
            locked_names.append(
                cast(
                    str,
                    locked.name,  # pyright: ignore[reportUnknownMemberType]
                )
            )
            return locked

    monkeypatch.setattr(
        Group.objects,
        "select_for_update",
        lambda: RenameBeforeLockedFetch(),
    )
    hidden_inputs = (
        (OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD)
        if action == "provision"
        else (OPERATOR_IDENTIFIER,)
    )
    confirmation = (
        PROVISION_CONFIRMATION if action == "provision" else DECOMMISSION_CONFIRMATION
    )

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            action,
            confirmation=confirmation,
            hidden_inputs=hidden_inputs,
        )

    protected.refresh_from_db()
    assert locked_names == ["renamed-during-lock-acquisition"]
    assert exact_limited_state(protected) == before
    group.refresh_from_db()
    assert group.name == GROUP_NAME  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.django_db
@pytest.mark.parametrize("action", ("provision", "decommission"))
def test_role_reconciliation_refuses_if_group_disappears_before_locked_fetch(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """AC-2/5: a vanished group is a fixed, non-mutating refusal for either action."""
    protected = create_exact_limited_operator()
    before = exact_limited_state(protected)
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=protected,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    private_sentinel = "private-group-disappearance-sentinel-243"

    class MissingLockedGroup:
        def get(self, *, pk: int) -> NoReturn:
            del pk
            raise Group.DoesNotExist(private_sentinel)

    monkeypatch.setattr(
        Group.objects,
        "select_for_update",
        lambda: MissingLockedGroup(),
    )
    hidden_inputs = (
        (OPERATOR_IDENTIFIER, ROTATED_PASSWORD, ROTATED_PASSWORD)
        if action == "provision"
        else (OPERATOR_IDENTIFIER,)
    )
    confirmation = (
        PROVISION_CONFIRMATION if action == "provision" else DECOMMISSION_CONFIRMATION
    )

    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            action,
            confirmation=confirmation,
            hidden_inputs=hidden_inputs,
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor == protected
    assert private_sentinel not in str(error.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("environment", "service"),
    ((None, "api"), ("production", "api"), ("staging", None), ("staging", "worker")),
)
def test_actions_refuse_noncanonical_railway_target_without_prompting_or_writing(
    monkeypatch: pytest.MonkeyPatch, environment: str | None, service: str | None
) -> None:
    """AC-1: neither lifecycle action may reach hidden input outside staging/api."""
    protected = create_user("unrelated_target_guard", is_staff=False, password=None)
    before = exact_limited_state(protected)

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            environment=environment,
            service=service,
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before
    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("stream_name", ("stdin", "stdout"))
def test_provision_refuses_when_hidden_tty_boundary_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, stream_name: str
) -> None:
    """AC-1/4: the command never falls back to echoed credential entry."""
    streams: dict[str, StringIO] = {"stdin": TtyStream(), "stdout": TtyStream()}
    streams[stream_name] = NonTtyStream()

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            stdin=streams["stdin"],
            stdout=streams["stdout"],
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("query_debug", ("settings_debug", "cursor_debug"))
def test_provision_refuses_query_logging_boundary_before_hidden_input(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    query_debug: str,
) -> None:
    """AC-4: query logging cannot observe a hidden provisioning identifier."""
    if query_debug == "settings_debug":
        settings.DEBUG = True
    else:
        monkeypatch.setattr(connection, "force_debug_cursor", True)
    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
def test_hidden_input_refuses_getpass_warning_before_any_echoed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4: an insecure getpass fallback must fail before consuming input."""
    command_module = importlib.import_module(COMMAND_MODULE)
    warning = getpass.GetPassWarning

    def unavailable_hidden_input(prompt: str, stream: Any | None = None) -> NoReturn:
        del prompt, stream
        raise warning("no tty")

    def echoed_input(prompt: str = "") -> NoReturn:
        del prompt
        raise AssertionError("echoed fallback used")

    monkeypatch.setattr(
        getpass,
        "getpass",
        unavailable_hidden_input,
    )
    monkeypatch.setattr(builtins, "input", echoed_input)

    with pytest.raises(CommandError):
        command_module._hidden_input("Operator identifier: ")

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("confirmation", "inputs"),
    (
        ("wrong confirmation", ()),
        (PROVISION_CONFIRMATION, ("", INITIAL_PASSWORD, INITIAL_PASSWORD)),
        (
            PROVISION_CONFIRMATION,
            ("contains whitespace", INITIAL_PASSWORD, INITIAL_PASSWORD),
        ),
        (
            PROVISION_CONFIRMATION,
            ("contains\x00control", INITIAL_PASSWORD, INITIAL_PASSWORD),
        ),
        (PROVISION_CONFIRMATION, ("a" * 256, INITIAL_PASSWORD, INITIAL_PASSWORD)),
        (PROVISION_CONFIRMATION, (OPERATOR_IDENTIFIER, "short", "short")),
        (PROVISION_CONFIRMATION, (OPERATOR_IDENTIFIER, INITIAL_PASSWORD, "different")),
    ),
)
def test_provision_rejects_invalid_hidden_input_privately_and_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
    inputs: tuple[str, ...],
) -> None:
    """AC-1/4: invalid confirmation, identifier, or password is fail-closed."""
    stdout = TtyStream()
    stderr = TtyStream()
    with pytest.raises(CommandError) as error:
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=confirmation,
            hidden_inputs=inputs,
            stdout=stdout,
            stderr=stderr,
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()
    assert_private_values_absent(
        (stdout, stderr), confirmation, *inputs, exception_text=str(error.value)
    )


@pytest.mark.django_db(transaction=True)
def test_provision_rolls_back_creation_when_group_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: a post-user-write database failure leaves no account or group behind."""
    command_module = importlib.import_module(COMMAND_MODULE)
    original_create = Group.objects.create

    def fail_group_create(*args: object, **kwargs: object) -> Group:
        raise DatabaseError("synthetic group failure")

    monkeypatch.setattr(command_module.Group.objects, "create", fail_group_create)
    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "provision",
            confirmation=PROVISION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER, INITIAL_PASSWORD, INITIAL_PASSWORD),
        )

    assert not User.objects.filter(clerk_user_id=OPERATOR_IDENTIFIER).exists()
    assert not Group.objects.filter(name=GROUP_NAME).exists()
    assert Group.objects.create is not original_create


@pytest.mark.django_db
def test_decommission_preserves_actor_and_audit_but_removes_future_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/8: lifecycle cleanup protects audit integrity while revoking access."""
    operator = create_exact_limited_operator()
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=operator,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )

    invoke_command(
        monkeypatch,
        "decommission",
        confirmation=DECOMMISSION_CONFIRMATION,
        hidden_inputs=(OPERATOR_IDENTIFIER,),
    )

    operator.refresh_from_db()
    group = Group.objects.get(name=GROUP_NAME)
    assert operator.is_staff is False
    assert operator.has_usable_password() is False
    assert (
        cast(
            bool,
            operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        )
        is False
    )
    assert operator.groups.get() == group  # pyright: ignore[reportUnknownMemberType]
    assert group.permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor == operator


@pytest.mark.django_db
def test_decommission_is_idempotent_only_for_exact_decommissioned_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5: a safe rerun recognizes only the retained synthetic lifecycle marker."""
    operator = create_exact_limited_operator()
    invoke_command(
        monkeypatch,
        "decommission",
        confirmation=DECOMMISSION_CONFIRMATION,
        hidden_inputs=(OPERATOR_IDENTIFIER,),
    )
    operator.refresh_from_db()
    before = exact_limited_state(operator)

    invoke_command(
        monkeypatch,
        "decommission",
        confirmation=DECOMMISSION_CONFIRMATION,
        hidden_inputs=(OPERATOR_IDENTIFIER,),
    )

    operator.refresh_from_db()
    assert exact_limited_state(operator) == before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "drift",
    (
        "shared_group",
        "direct_permission",
        "missing_group_permission",
        "extra_group_permission",
        "extra_group",
        "gameplay_attachment",
        "superuser",
    ),
)
def test_decommission_refuses_every_drifted_limited_role_without_altering_audit(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    """AC-5/6: decommission is allowed only for the exact retained role shape."""
    protected = create_exact_limited_operator()
    group = protected.groups.get()  # pyright: ignore[reportUnknownMemberType]
    permissions = permissions_by_name()
    if drift == "shared_group":
        create_user("shared_limited_group_member").groups.add(group)  # pyright: ignore[reportUnknownMemberType]
    elif drift == "direct_permission":
        protected.user_permissions.add(permissions["profiles.set_profile_enabled"])  # pyright: ignore[reportUnknownMemberType]
    elif drift == "missing_group_permission":
        group.permissions.remove(permissions["profiles.view_playerprofile"])  # pyright: ignore[reportUnknownMemberType]
    elif drift == "extra_group_permission":
        group.permissions.add(permissions[EXTRA_SENSITIVE_PERMISSION])  # pyright: ignore[reportUnknownMemberType]
    elif drift == "extra_group":
        protected.groups.add(Group.objects.create(name="unexpected decommission group"))  # pyright: ignore[reportUnknownMemberType]
    elif drift == "gameplay_attachment":
        attach_gameplay_record(protected, "profile")
    else:
        protected.is_superuser = True
        protected.save(update_fields={"is_superuser"})
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=protected,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    before = exact_limited_state(protected)
    member_ids_before = set(
        User.objects.filter(groups=group).values_list("pk", flat=True)
    )
    permission_ids_before = set(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "decommission",
            confirmation=DECOMMISSION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER,),
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before
    assert (
        set(User.objects.filter(groups=group).values_list("pk", flat=True))
        == member_ids_before
    )
    assert set(group.permissions.values_list("pk", flat=True)) == permission_ids_before  # pyright: ignore[reportUnknownMemberType]
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor == protected


@pytest.mark.django_db(transaction=True)
def test_decommission_rolls_back_group_clear_when_account_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3/5: failure after clearing authority restores access state and audit links."""
    protected = create_exact_limited_operator()
    group = protected.groups.get()  # pyright: ignore[reportUnknownMemberType]
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=protected,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    before = exact_limited_state(protected)
    permissions_before = set(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
    original_save = User.save

    def fail_decommission_save(
        user: User,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if update_fields == {"is_staff", "password"}:
            raise DatabaseError("synthetic decommission account update failure")
        original_save(
            user,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    monkeypatch.setattr(User, "save", fail_decommission_save)
    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "decommission",
            confirmation=DECOMMISSION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER,),
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before
    assert set(group.permissions.values_list("pk", flat=True)) == permissions_before  # pyright: ignore[reportUnknownMemberType]
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor == protected


@pytest.mark.django_db
def test_decommission_refuses_managed_or_drifted_role_without_touching_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/6: decommission cannot erase access or evidence for another role."""
    protected = create_exact_managed_operator(OPERATOR_IDENTIFIER)
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=protected,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    before = exact_limited_state(protected)

    with pytest.raises(CommandError):
        invoke_command(
            monkeypatch,
            "decommission",
            confirmation=DECOMMISSION_CONFIRMATION,
            hidden_inputs=(OPERATOR_IDENTIFIER,),
        )

    protected.refresh_from_db()
    assert exact_limited_state(protected) == before
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor == protected


@pytest.mark.django_db
def test_actions_reject_unknown_cli_options_without_echoing_private_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-1/4: no argv form can carry a provisioning identity or password."""
    private_value = "private-argv-sentinel-243"
    stdout = TtyStream()
    stderr = TtyStream()
    caplog.set_level(logging.DEBUG)

    with pytest.raises(CommandError) as error:
        call_command(
            COMMAND_NAME,
            "provision",
            "--identifier",
            private_value,
            stdout=stdout,
            stderr=stderr,
        )

    assert_private_values_absent(
        (stdout, stderr), private_value, exception_text=str(error.value), caplog=caplog
    )
    assert not User.objects.filter(clerk_user_id=private_value).exists()
