"""Acceptance tests for #243 password-only managed login recovery."""

from __future__ import annotations

import getpass
import importlib
import sys
from io import StringIO
from typing import Any, cast

import pytest
from django.core.management import CommandError
from django.db import DatabaseError, transaction
from django.test import Client

from accounts.models import User
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from tests.test_staging_managed_operator_recovery import (
    EXPECTED_IDENTITY,
    LIMITED_PASSWORD,
    MANAGED_PERMISSIONS,
    OLD_IDENTIFIER,
    OLD_PASSWORD,
    RAILWAY_SELECTORS,
    group_state,
    seed_roles,
    state,
)

COMMAND = "rotate_staging_managed_password"
CONFIRMATION = "rotate Railway Staging managed operator password"
NEW_PASSWORD = "final-managed-password-2026-local-only"


class Tty(StringIO):
    def isatty(self) -> bool:
        return True


class NonTty(StringIO):
    def isatty(self) -> bool:
        return False


def invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    password: str = NEW_PASSWORD,
    confirmation_password: str | None = None,
    confirmation: str = CONFIRMATION,
    environment: str = "staging",
    service: str = "api",
    terminal: StringIO | None = None,
    expected_identity: object = EXPECTED_IDENTITY,
    live_identity: object = EXPECTED_IDENTITY,
    after_prompt: Any = None,
) -> tuple[StringIO, StringIO, list[str]]:
    stdout = terminal if terminal is not None else Tty()
    stderr = Tty()
    prompts: list[str] = []
    values = iter(
        (password, password if confirmation_password is None else confirmation_password)
    )

    def hidden(prompt: str) -> str:
        prompts.append(prompt)
        if after_prompt is not None:
            after_prompt(len(prompts))
        return next(values)

    monkeypatch.setattr(sys, "stdin", stdout)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(getpass, "getpass", hidden)
    monkeypatch.setattr("builtins.input", lambda _prompt="": confirmation)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", service)
    for key, value in RAILWAY_SELECTORS.items():
        monkeypatch.setenv(key, value)
    from config import build_identity

    monkeypatch.setattr(build_identity, "get_identity", lambda: live_identity)
    command = importlib.import_module(f"accounts.management.commands.{COMMAND}")
    command.Command().execute(
        expected_identity=expected_identity,
        force_color=False,
        no_color=False,
        skip_checks=True,
        stdout=stdout,
        stderr=stderr,
    )
    return stdout, stderr, prompts


def assert_private_absent(*streams: StringIO) -> None:
    output = "".join(stream.getvalue() for stream in streams)
    for value in (OLD_IDENTIFIER, OLD_PASSWORD, NEW_PASSWORD, LIMITED_PASSWORD):
        assert value not in output
    for value in MANAGED_PERMISSIONS:
        assert value not in output


@pytest.mark.django_db(transaction=True)
def test_rotation_changes_only_exact_managed_password_and_preserves_audit_and_limited(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """AC-1/2: the sole managed User is retained; role, audit, limited state are exact."""
    settings.DEBUG = False
    managed, limited, managed_group, limited_group = seed_roles()
    original_pk = managed.pk
    managed_before = state(managed)
    managed_group_before = group_state(managed_group)
    limited_before = state(limited)
    limited_group_before = group_state(limited_group)
    audit = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_PROFILE_ENABLED,
        actor=managed,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.PLAYER_PROFILE,
        affected_record_id=1,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )
    audit_before = tuple(OperatorAuditEvent.objects.values_list())
    old_client = Client()
    assert old_client.login(clerk_user_id=OLD_IDENTIFIER, password=OLD_PASSWORD)

    stdout, stderr, prompts = invoke(monkeypatch)

    managed.refresh_from_db()
    assert User.objects.count() == 2
    assert managed.pk == original_pk and managed.clerk_user_id == OLD_IDENTIFIER
    assert managed.check_password(NEW_PASSWORD)
    assert not managed.check_password(OLD_PASSWORD)
    assert state(managed)[:4] == managed_before[:4]
    assert state(managed)[5:] == managed_before[5:]
    assert group_state(managed_group) == managed_group_before
    assert state(limited) == limited_before
    assert group_state(limited_group) == limited_group_before
    assert tuple(OperatorAuditEvent.objects.values_list()) == audit_before
    assert OperatorAuditEvent.objects.get(pk=audit.pk).actor_id == original_pk
    assert old_client.get("/admin/").status_code == 302
    new_client = Client()
    assert new_client.login(clerk_user_id=OLD_IDENTIFIER, password=NEW_PASSWORD)
    assert new_client.get("/admin/").status_code == 200
    assert len(prompts) == 2
    assert all("password" in prompt.lower() for prompt in prompts)
    assert all("identifier" not in prompt.lower() for prompt in prompts)
    assert stdout.getvalue().count("PREPARED") == 1
    assert stdout.getvalue().count("POSTCONDITION_PASS") == 1
    assert_private_absent(stdout, stderr)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "bad",
    [
        "wrong_environment",
        "wrong_service",
        "wrong_target",
        "non_tty",
        "wrong_phrase",
        "debug_logging",
    ],
)
def test_prewrite_guards_refuse_without_prompt_or_mutation(
    monkeypatch: pytest.MonkeyPatch, settings: Any, bad: str
) -> None:
    """AC-1: target, TTY, and confirmation are hard boundaries."""
    settings.DEBUG = False
    managed, limited, managed_group, limited_group = seed_roles()
    before = (
        state(managed),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    )
    kwargs: dict[str, Any] = {}
    if bad == "wrong_environment":
        kwargs["environment"] = "production"
    elif bad == "wrong_service":
        kwargs["service"] = "worker"
    elif bad == "wrong_target":
        kwargs["live_identity"] = {**EXPECTED_IDENTITY, "source_sha": "f" * 40}
    elif bad == "non_tty":
        kwargs["terminal"] = NonTty()
    elif bad == "debug_logging":
        settings.DEBUG = True
    else:
        kwargs["confirmation"] = "wrong phrase"
    prompts: list[str] = []
    kwargs["after_prompt"] = lambda number: prompts.append(str(number))
    with pytest.raises(CommandError):
        invoke(monkeypatch, **kwargs)
    assert prompts == []
    assert (
        state(managed),
        state(limited),
        group_state(managed_group),
        group_state(limited_group),
    ) == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bad_password", ["short", "mismatched"])
def test_password_policy_and_confirmation_fail_without_write(
    monkeypatch: pytest.MonkeyPatch, settings: Any, bad_password: str
) -> None:
    """AC-2: only a policy-valid confirmed secret may enter the transaction."""
    settings.DEBUG = False
    managed, limited, _, _ = seed_roles()
    before = (state(managed), state(limited))
    kwargs: dict[str, Any] = (
        {"password": "short"}
        if bad_password == "short"
        else {"confirmation_password": "a-different-long-password"}
    )
    with pytest.raises(CommandError):
        invoke(monkeypatch, **kwargs)
    assert (state(managed), state(limited)) == before


@pytest.mark.django_db(transaction=True)
def test_managed_role_drift_during_hidden_input_rolls_back(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """AC-2: a pre-input pin must not authorize a changed role after input."""
    settings.DEBUG = False
    managed, limited, managed_group, _ = seed_roles()
    old_hash = cast(str, managed.password)  # pyright: ignore[reportUnknownMemberType]

    def drift(prompt_number: int) -> None:
        if prompt_number == 1:
            managed.groups.clear()  # pyright: ignore[reportUnknownMemberType]

    with pytest.raises(CommandError):
        invoke(monkeypatch, after_prompt=drift)
    managed.refresh_from_db()
    assert cast(str, managed.password) == old_hash  # pyright: ignore[reportUnknownMemberType]
    assert not User.objects.filter(groups=managed_group).exists()
    assert state(limited)[4]  # limited remains present


@pytest.mark.django_db(transaction=True)
def test_unexpected_privilege_and_ambiguous_managed_role_fail_closed(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """AC-1: a superuser or second managed group member is never selected."""
    settings.DEBUG = False
    managed, _, managed_group, _ = seed_roles()
    extra = User.objects.create_user("extra-managed-role")
    extra.is_staff = True
    extra.set_password("extra-managed-password")
    extra.save(update_fields={"is_staff", "password"})
    extra.groups.add(managed_group)  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    assert managed.check_password(OLD_PASSWORD)
    extra.groups.clear()  # pyright: ignore[reportUnknownMemberType]
    managed.is_superuser = True
    managed.save(update_fields={"is_superuser"})
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    managed.refresh_from_db()
    assert managed.check_password(OLD_PASSWORD)


@pytest.mark.django_db(transaction=True)
def test_database_failure_after_password_write_rolls_back_atomically(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """AC-2: a failed save cannot leave a changed password or partial role state."""
    settings.DEBUG = False
    managed, limited, group, limited_group = seed_roles()
    before = (
        state(managed),
        state(limited),
        group_state(group),
        group_state(limited_group),
    )
    original_save = User.save

    def fail_after_write(self: User, *args: object, **kwargs: object) -> None:
        original_save(self, *args, **kwargs)
        if self.pk == managed.pk and self.check_password(NEW_PASSWORD):
            raise DatabaseError("private-database-failure")

    monkeypatch.setattr(User, "save", fail_after_write)
    output = Tty()
    with pytest.raises(CommandError) as error:
        invoke(monkeypatch, terminal=output)
    assert (
        state(managed),
        state(limited),
        group_state(group),
        group_state(limited_group),
    ) == before
    assert "POSTCONDITION_PASS" not in output.getvalue()
    assert "private-database-failure" not in str(error.value) + output.getvalue()


@pytest.mark.django_db(transaction=True)
def test_postcommit_must_check_entered_password_not_merely_usable_hash(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """AC-2: a usable but wrong committed hash cannot earn POSTCONDITION_PASS."""
    settings.DEBUG = False
    managed, _, _, _ = seed_roles()
    # Simulate a separate writer after the command's atomic commit but before
    # its read-only postcommit check. The command must withhold its PASS marker.
    original_save = User.save

    def save_with_wrong_hash(self: User, *args: object, **kwargs: object) -> None:
        original_save(self, *args, **kwargs)
        if self.pk == managed.pk and self.check_password(NEW_PASSWORD):

            def tamper_after_commit() -> None:
                changed = User.objects.get(pk=managed.pk)
                changed.set_password("different-policy-valid-password")
                User.objects.filter(pk=managed.pk).update(password=changed.password)

            transaction.on_commit(tamper_after_commit)

    monkeypatch.setattr(User, "save", save_with_wrong_hash)
    output = Tty()
    with pytest.raises(CommandError):
        invoke(monkeypatch, terminal=output)
    assert "POSTCONDITION_PASS" not in output.getvalue()
    assert User.objects.get(pk=managed.pk).clerk_user_id == OLD_IDENTIFIER
