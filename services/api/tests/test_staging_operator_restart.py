"""Acceptance tests for the bounded #243 three-operator restart.

The command is exercised against disposable PostgreSQL with real User, group,
permission, session, #204 registry, domain, and operator-audit rows. Only the
terminal and the external deployment identity are supplied by the test.
"""

from __future__ import annotations

import getpass
import importlib
import logging
import secrets
import sys
from io import StringIO
from typing import Any, cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError
from django.db import DatabaseError, connection
from django.test import Client

from accounts.models import User
from config import build_identity, replacement_target_binding
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
from rehearsal.reset import validate_baseline
from tests.test_staging_operator_inspector import create_owned_baseline

COMMAND = "accounts.management.commands.restart_staging_validation_operators"
CONFIRMATION = "restart Railway Staging validation operators"
IDENTITY = {
    "environment": "staging",
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
}
SELECTORS = {
    "RAILWAY_PROJECT_ID": "a1111111-1111-4111-8111-111111111111",
    "RAILWAY_ENVIRONMENT_ID": "c3333333-3333-4333-8333-333333333333",
    "RAILWAY_SERVICE_ID": "d4444444-4444-4444-8444-444444444444",
}
PASSWORDS = {
    "managed": "new-managed-password-for-restart-243",
    "limited": "new-limited-password-for-restart-243",
    "emergency": "new-emergency-password-for-restart-243",
}
OLD_PASSWORD = "old-operator-password-for-restart-243"
MANAGED_GROUP = "TailTag Field Beta Operators"
LIMITED_GROUP = "TailTag #243 Validation Operator"
LIMITED_PERMISSIONS = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


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


def staff_user(identifier: str, *, superuser: bool = False) -> User:
    user = User(clerk_user_id=identifier, is_staff=True, is_superuser=superuser)
    user.set_password(OLD_PASSWORD)
    user.save()
    return user


def seed_exact_state() -> tuple[
    dict[str, User], dict[str, Group], StagingResetIdentity
]:
    registry = create_owned_baseline()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        facts = cursor.fetchone()
    assert facts is not None
    registry.database_name = str(facts[0])
    registry.cluster_identifier = str(facts[1])
    registry.save(update_fields={"database_name", "cluster_identifier"})

    from accounts.management.commands.bootstrap_staging_operator import (
        EXPECTED_PERMISSION_NAMES,
    )

    managed_group = Group.objects.create(name=MANAGED_GROUP)
    managed_group.permissions.set(permissions(frozenset(EXPECTED_PERMISSION_NAMES)))  # pyright: ignore[reportUnknownMemberType]
    limited_group = Group.objects.create(name=LIMITED_GROUP)
    limited_group.permissions.set(permissions(LIMITED_PERMISSIONS))  # pyright: ignore[reportUnknownMemberType]
    actors = {
        "managed": staff_user("staging_managed_prior_243"),
        "limited": staff_user("staging_validation_prior_243"),
        "emergency": staff_user("staging_emergency_prior_243", superuser=True),
    }
    actors["managed"].groups.add(managed_group)  # pyright: ignore[reportUnknownMemberType]
    actors["limited"].groups.add(limited_group)  # pyright: ignore[reportUnknownMemberType]
    return actors, {"managed": managed_group, "limited": limited_group}, registry


def audit_snapshot() -> tuple[tuple[object, ...], ...]:
    return tuple(
        OperatorAuditEvent.objects.order_by("pk").values_list(
            "pk",
            "actor_id",
            "action",
            "actor_class",
            "affected_record_type",
            "affected_record_id",
            "outcome",
            "occurred_at",
        )
    )


def persisted_state() -> tuple[object, ...]:
    return (
        tuple(
            User.objects.order_by("pk").values_list(
                "pk", "clerk_user_id", "is_staff", "is_superuser", "password"
            )
        ),
        tuple(
            (
                user.pk,
                tuple(user.groups.order_by("pk").values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
                tuple(
                    user.user_permissions.order_by("pk").values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
                ),
            )
            for user in User.objects.order_by("pk")
        ),
        tuple(
            (
                group.pk,
                tuple(group.permissions.order_by("pk").values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
            )
            for group in Group.objects.order_by("pk")
        ),
        audit_snapshot(),
        tuple(
            StagingResetIdentity.objects.values_list(
                "pk",
                "owner_id",
                "catcher_id",
                "convention_id",
                "first_fursuit_id",
                "second_fursuit_id",
                "environment_id",
                "cluster_identifier",
                "database_name",
                "media_key",
            )
        ),
    )


def set_target(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str = "staging",
    service: str = "api",
) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", environment)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", service)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", IDENTITY["deployment_id"])
    for name, value in SELECTORS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        replacement_target_binding,
        "_EXPECTED_DIGESTS",
        {
            **replacement_target_binding._EXPECTED_DIGESTS,  # pyright: ignore[reportPrivateUsage]
            "staging-api": replacement_target_binding.fingerprint_tuple(
                "staging-api",
                SELECTORS["RAILWAY_PROJECT_ID"],
                SELECTORS["RAILWAY_ENVIRONMENT_ID"],
                SELECTORS["RAILWAY_SERVICE_ID"],
            ),
        },
    )
    monkeypatch.setattr(build_identity, "get_identity", lambda: dict(IDENTITY))


def invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    passwords: dict[str, str] = PASSWORDS,
    confirmation: str = CONFIRMATION,
    stdin: Terminal | None = None,
    stdout: Terminal | None = None,
    stderr: Terminal | None = None,
    expected_identity: dict[str, str] | None = IDENTITY,
    on_password_prompt: Any = None,
) -> tuple[Terminal, Terminal, list[str]]:
    command = importlib.import_module(COMMAND)
    stdin = stdin or Terminal()
    stdout = stdout or Terminal()
    stderr = stderr or Terminal()
    prompts: list[str] = []
    answers = iter(
        value
        for role in ("managed", "limited", "emergency")
        for value in (passwords[role], passwords[role])
    )

    def hidden_input(prompt: str) -> str:
        prompts.append(prompt)
        if on_password_prompt is not None:
            on_password_prompt(prompt)
        return next(answers)

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", lambda prompt="": confirmation)
    monkeypatch.setattr(getpass, "getpass", hidden_input)
    command.Command().execute(
        expected_identity=expected_identity,
        stdout=stdout,
        stderr=stderr,
        force_color=False,
        no_color=False,
        skip_checks=True,
    )
    return stdout, stderr, prompts


@pytest.fixture(autouse=True)
def safe_query_boundary(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = False
    monkeypatch.setattr(connection, "force_debug_cursor", False)


@pytest.mark.django_db(transaction=True)
def test_restart_retires_all_three_and_preserves_audit_and_baseline(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-2/3/4/5: generated replacements are exact; predecessors and audit persist."""
    actors, groups, registry = seed_exact_state()
    set_target(monkeypatch)
    old_pks = {actor.pk for actor in actors.values()}
    for role, actor in actors.items():
        OperatorAuditEvent.objects.create(
            action=OperatorAction.SET_PROFILE_ENABLED,
            actor=actor,
            actor_class=(
                OperatorActorClass.EMERGENCY_SUPERUSER
                if role == "emergency"
                else OperatorActorClass.OPERATOR
            ),
            affected_record_type=OperatorTargetType.PLAYER_PROFILE,
            affected_record_id=PlayerProfile.objects.get(user=registry.owner).pk,
            outcome=OperatorAuditOutcome.SUCCEEDED,
        )
    before_audit = audit_snapshot()
    before_baseline = persisted_state()[-1]
    before_players = tuple(
        User.objects.filter(pk__in=(registry.owner_id, registry.catcher_id))
        .order_by("pk")
        .values_list("pk", "clerk_user_id", "is_staff", "is_superuser", "password")
    )
    caplog.set_level(logging.INFO)

    stdout, stderr, prompts = invoke(monkeypatch)

    new_actors = list(User.objects.filter(is_staff=True))
    assert len(new_actors) == 3
    assert not old_pks.intersection({actor.pk for actor in new_actors})
    assert len({actor.clerk_user_id for actor in new_actors}) == 3
    assert all(actor.clerk_user_id.startswith("staging_") for actor in new_actors)
    assert User.objects.count() == 8  # two #204 identities, three old, three new
    for old in actors.values():
        old.refresh_from_db()
        assert old.is_staff is False
        assert cast(bool, old.is_superuser) is False  # pyright: ignore[reportUnknownMemberType]
        assert not old.has_usable_password()
        assert old.groups.count() == 0  # pyright: ignore[reportUnknownMemberType]
        assert old.user_permissions.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert audit_snapshot() == before_audit
    assert persisted_state()[-1] == before_baseline
    assert (
        tuple(
            User.objects.filter(pk__in=(registry.owner_id, registry.catcher_id))
            .order_by("pk")
            .values_list("pk", "clerk_user_id", "is_staff", "is_superuser", "password")
        )
        == before_players
    )
    assert validate_baseline(StagingResetIdentity.objects.get(pk=1))
    assert {row[1] for row in before_audit} == old_pks

    managed = User.objects.get(groups=groups["managed"])
    limited = User.objects.get(groups=groups["limited"])
    emergency = User.objects.get(is_superuser=True)
    assert {managed.pk, limited.pk, emergency.pk} == {actor.pk for actor in new_actors}
    assert managed.clerk_user_id.startswith("staging_managed_")
    assert limited.clerk_user_id.startswith("staging_validation_")
    assert emergency.clerk_user_id.startswith("staging_emergency_")
    assert managed.is_staff and not cast(bool, managed.is_superuser)  # pyright: ignore[reportUnknownMemberType]
    assert limited.is_staff and not cast(bool, limited.is_superuser)  # pyright: ignore[reportUnknownMemberType]
    assert emergency.is_staff and cast(bool, emergency.is_superuser)  # pyright: ignore[reportUnknownMemberType]
    assert managed.groups.count() == limited.groups.count() == 1  # pyright: ignore[reportUnknownMemberType]
    assert emergency.groups.count() == 0  # pyright: ignore[reportUnknownMemberType]
    assert all(actor.user_permissions.count() == 0 for actor in new_actors)  # pyright: ignore[reportUnknownMemberType]
    from accounts.management.commands.bootstrap_staging_operator import (
        EXPECTED_PERMISSION_NAMES,
    )

    assert set(managed.get_all_permissions()) == set(EXPECTED_PERMISSION_NAMES)
    assert set(limited.get_all_permissions()) == LIMITED_PERMISSIONS
    assert not LIMITED_PERMISSIONS.issuperset(EXPECTED_PERMISSION_NAMES)
    assert managed.check_password(PASSWORDS["managed"])
    assert limited.check_password(PASSWORDS["limited"])
    assert emergency.check_password(PASSWORDS["emergency"])
    for actor, role in (
        (managed, "managed"),
        (limited, "limited"),
        (emergency, "emergency"),
    ):
        client = Client()
        assert client.login(username=actor.clerk_user_id, password=PASSWORDS[role])
        assert client.get("/admin/").status_code == 200
    assert stdout.getvalue().count("POSTCONDITION_PASS") == 1
    assert len(prompts) == 6
    assert all("identifier" not in prompt.lower() for prompt in prompts)
    rendered = stdout.getvalue() + stderr.getvalue() + caplog.text
    for old in actors.values():
        assert old.clerk_user_id not in rendered
    for new in new_actors:
        assert new.clerk_user_id not in rendered
        assert cast(str, new.password) not in rendered  # pyright: ignore[reportUnknownMemberType]
    for secret in PASSWORDS.values():
        assert secret not in rendered
    for permission in EXPECTED_PERMISSION_NAMES:
        assert permission not in rendered


@pytest.mark.django_db(transaction=True)
def test_existing_admin_sessions_lose_access_after_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3/5: retained old Users cannot keep an already issued admin session."""
    actors, _, _ = seed_exact_state()
    set_target(monkeypatch)
    clients = [Client() for _ in actors]
    for client, actor in zip(clients, actors.values(), strict=True):
        assert client.login(username=actor.clerk_user_id, password=OLD_PASSWORD)
        assert client.get("/admin/").status_code == 200
    invoke(monkeypatch)
    for client in clients:
        assert client.get("/admin/").status_code in {302, 403}


@pytest.mark.django_db(transaction=True)
def test_successful_restart_cannot_be_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4/5: a second invocation cannot create a third dedicated emergency row."""
    seed_exact_state()
    set_target(monkeypatch)
    first_output, _, _ = invoke(monkeypatch)
    assert first_output.getvalue().count("POSTCONDITION_PASS") == 1
    after_first = persisted_state()

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert persisted_state() == after_first
    assert (
        User.objects.filter(clerk_user_id__startswith="staging_emergency_").count() == 2
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "attachment",
    (
        "managed_profile",
        "limited_fursuit",
        "managed_reset_owner",
        "limited_reset_catcher",
    ),
)
def test_attached_managed_or_limited_actor_cannot_be_transferred(
    monkeypatch: pytest.MonkeyPatch,
    attachment: str,
) -> None:
    """AC-3/4: a gameplay or #204 identity cannot become a throwaway operator."""
    actors, _, registry = seed_exact_state()
    set_target(monkeypatch)
    if attachment == "managed_profile":
        PlayerProfile.objects.create(user=actors["managed"])
    elif attachment == "limited_fursuit":
        Fursuit.objects.create(
            owner=actors["limited"],
            name="Unexpected limited role fursuit",
            photo_key="images/disposable-test.png",
        )
    elif attachment == "managed_reset_owner":
        registry.owner = actors["managed"]
        registry.save(update_fields={"owner"})
    else:
        registry.catcher = actors["limited"]
        registry.save(update_fields={"catcher"})
    before = persisted_state()
    before_profiles = tuple(PlayerProfile.objects.order_by("pk").values())
    before_fursuits = tuple(Fursuit.objects.order_by("pk").values())

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert persisted_state() == before
    assert tuple(PlayerProfile.objects.order_by("pk").values()) == before_profiles
    assert tuple(Fursuit.objects.order_by("pk").values()) == before_fursuits


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "drift",
    (
        "extra_staff",
        "extra_superuser",
        "managed_permission",
        "limited_permission",
        "emergency_group",
        "retired_emergency",
        "fixture",
    ),
)
def test_drift_fails_without_partial_change(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    """AC-1/4: any current role or #204 baseline drift blocks all three writes."""
    actors, groups, registry = seed_exact_state()
    set_target(monkeypatch)
    if drift == "extra_staff":
        staff_user("unrelated_staff")
    elif drift == "extra_superuser":
        staff_user("unrelated_superuser", superuser=True)
    elif drift == "managed_permission":
        permission = groups["managed"].permissions.first()  # pyright: ignore[reportUnknownMemberType]
        assert permission is not None
        groups["managed"].permissions.remove(  # pyright: ignore[reportUnknownMemberType]
            permission
        )
    elif drift == "limited_permission":
        actors["limited"].user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="catches", codename="delete_catch"
            )
        )
    elif drift == "emergency_group":
        actors["emergency"].groups.add(groups["managed"])  # pyright: ignore[reportUnknownMemberType]
    elif drift == "retired_emergency":
        actors["emergency"].is_staff = False
        actors["emergency"].is_superuser = False
        actors["emergency"].set_unusable_password()
        actors["emergency"].save()
    else:
        fursuit = registry.first_fursuit
        assert fursuit is not None
        fursuit.is_enabled = False
        fursuit.save(update_fields={"is_enabled"})
    before = persisted_state()
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    assert persisted_state() == before
    if drift == "fixture":
        fursuit = registry.first_fursuit
        assert fursuit is not None
        fursuit.refresh_from_db()
        assert not fursuit.is_enabled


@pytest.mark.django_db(transaction=True)
def test_wrong_model_same_codename_limited_permission_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3/4: an app-label/codename match on the wrong model is not authority."""
    _, groups, _ = seed_exact_state()
    set_target(monkeypatch)
    canonical = Permission.objects.get(
        content_type__app_label="profiles",
        content_type__model="playerprofile",
        codename="set_profile_enabled",
    )
    wrong_model = ContentType.objects.create(
        app_label="profiles", model="restart_wrong_profile_model"
    )
    counterfeit = Permission.objects.create(
        content_type=wrong_model,
        codename="set_profile_enabled",
        name="Counterfeit profile permission for disposable test",
    )
    groups["limited"].permissions.remove(canonical)  # pyright: ignore[reportUnknownMemberType]
    groups["limited"].permissions.add(counterfeit)  # pyright: ignore[reportUnknownMemberType]
    before = persisted_state()

    with pytest.raises(CommandError):
        invoke(monkeypatch)

    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "environment,service", (("development", "api"), ("staging", "web"))
)
def test_wrong_runtime_target_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    service: str,
) -> None:
    """AC-1: the command is bound to Railway Staging's API service."""
    seed_exact_state()
    set_target(monkeypatch, environment=environment, service=service)
    before = persisted_state()
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
def test_public_instance_identity_mismatch_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4: a stale deployment receipt cannot authorize a restart."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()
    with pytest.raises(CommandError):
        invoke(monkeypatch, expected_identity={**IDENTITY, "source_sha": "b" * 40})
    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
def test_runtime_selector_mismatch_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1: a different Railway resource cannot satisfy the replacement pin."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "f5555555-5555-4555-8555-555555555555")
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
def test_generated_identifier_collision_refuses_without_adopting_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/4: an occupied generated name blocks the entire role transfer."""
    seed_exact_state()
    set_target(monkeypatch)
    suffix = "deadbeef01234567"
    occupied = User.objects.create_user(f"staging_managed_{suffix}")
    before = persisted_state()
    monkeypatch.setattr(secrets, "token_hex", lambda _nbytes=8: suffix)
    with pytest.raises(CommandError):
        invoke(monkeypatch)
    assert persisted_state() == before
    occupied.refresh_from_db()
    assert not occupied.is_staff
    assert not occupied.has_usable_password()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "terminal,confirmation",
    ((Terminal(attached=False), CONFIRMATION), (Terminal(), "wrong phrase")),
)
def test_tty_and_confirmation_are_required_before_write(
    monkeypatch: pytest.MonkeyPatch,
    terminal: Terminal,
    confirmation: str,
) -> None:
    """AC-2: a real hidden terminal and exact public confirmation are mandatory."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()
    with pytest.raises(CommandError):
        invoke(monkeypatch, stdin=terminal, confirmation=confirmation)
    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
def test_password_policy_failure_is_all_or_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2/4: one weak role password cannot rotate the other roles."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()
    with pytest.raises(CommandError):
        invoke(monkeypatch, passwords={**PASSWORDS, "emergency": "short"})
    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "first,second",
    (("managed", "limited"), ("managed", "emergency"), ("limited", "emergency")),
)
def test_role_passwords_must_be_distinct(
    monkeypatch: pytest.MonkeyPatch,
    first: str,
    second: str,
) -> None:
    """AC-2/4: one shared credential must not create a partially rotated set."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()
    passwords = {**PASSWORDS, second: PASSWORDS[first]}

    with pytest.raises(CommandError):
        invoke(monkeypatch, passwords=passwords)

    assert persisted_state() == before


@pytest.mark.django_db(transaction=True)
def test_hidden_input_failure_refuses_without_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: inability to suppress terminal echo cannot leak into a write."""
    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()

    def fail_hidden_input(_: str) -> None:
        raise getpass.GetPassWarning("private fallback detail")

    with pytest.raises(CommandError) as error:
        invoke(monkeypatch, on_password_prompt=fail_hidden_input)
    assert persisted_state() == before
    assert "private fallback detail" not in str(error.value)


@pytest.mark.django_db(transaction=True)
def test_midrun_role_drift_is_rechecked_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: pre-prompt state cannot be trusted once a human has entered secrets."""
    actors, _, _ = seed_exact_state()
    set_target(monkeypatch)
    changed = False
    after_drift: tuple[object, ...] | None = None

    def drift(_: str) -> None:
        nonlocal changed, after_drift
        if not changed:
            actors["limited"].is_staff = False
            actors["limited"].set_unusable_password()
            actors["limited"].save()
            after_drift = persisted_state()
            changed = True

    with pytest.raises(CommandError):
        invoke(monkeypatch, on_password_prompt=drift)
    assert changed
    assert persisted_state() == after_drift


@pytest.mark.django_db(transaction=True)
def test_audit_drift_during_hidden_input_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: an audit event added during prompts must not be overwritten or ignored."""
    actors, _, registry = seed_exact_state()
    set_target(monkeypatch)
    after_drift: tuple[object, ...] | None = None

    def add_audit(_: str) -> None:
        nonlocal after_drift
        if after_drift is None:
            OperatorAuditEvent.objects.create(
                action=OperatorAction.SET_PROFILE_ENABLED,
                actor=actors["managed"],
                actor_class=OperatorActorClass.OPERATOR,
                affected_record_type=OperatorTargetType.PLAYER_PROFILE,
                affected_record_id=PlayerProfile.objects.get(user=registry.owner).pk,
                outcome=OperatorAuditOutcome.SUCCEEDED,
            )
            after_drift = persisted_state()

    with pytest.raises(CommandError):
        invoke(monkeypatch, on_password_prompt=add_audit)
    assert after_drift is not None
    assert persisted_state() == after_drift


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("drift", ("owner_clerk_id", "catcher_password"))
def test_preserved_player_identity_drift_during_prompt_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    """AC-1/4: #204 preserved User identity state is pinned across human input."""
    _, _, registry = seed_exact_state()
    set_target(monkeypatch)
    after_drift: tuple[object, ...] | None = None

    def change_preserved_identity(_: str) -> None:
        nonlocal after_drift
        if after_drift is not None:
            return
        if drift == "owner_clerk_id":
            registry.owner.clerk_user_id = "changed_disposable_owner_subject"
            registry.owner.save(update_fields={"clerk_user_id"})
        else:
            registry.catcher.set_unusable_password()
            registry.catcher.save(update_fields={"password"})
        after_drift = persisted_state()

    with pytest.raises(CommandError):
        invoke(monkeypatch, on_password_prompt=change_preserved_identity)

    assert after_drift is not None
    assert persisted_state() == after_drift


@pytest.mark.django_db(transaction=True)
def test_database_write_failure_rolls_back_all_role_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: failure after an insert cannot leave a half-restarted operator set."""
    from django.db.models.signals import post_save

    seed_exact_state()
    set_target(monkeypatch)
    before = persisted_state()

    def fail_on_new_actor(
        sender: type[User], instance: User, created: bool, **_: object
    ) -> None:
        if created and instance.is_staff:
            raise DatabaseError("private database failure sentinel")

    post_save.connect(fail_on_new_actor, sender=User, weak=False)  # pyright: ignore[reportUnknownMemberType]
    try:
        with pytest.raises(CommandError) as error:
            invoke(monkeypatch)
    finally:
        post_save.disconnect(fail_on_new_actor, sender=User)  # pyright: ignore[reportUnknownMemberType]
    assert persisted_state() == before
    assert "private database failure sentinel" not in str(error.value)


@pytest.mark.django_db
def test_emergency_inspector_recognizes_exact_two_row_lifecycle() -> None:
    """AC-5: one active actor plus one exact retired predecessor is READY."""
    from accounts.management.commands.bootstrap_staging_emergency_operator import (
        inspect_emergency_state,
    )

    old = staff_user("staging_emergency_prior_243", superuser=True)
    old.is_staff = False
    old.is_superuser = False
    old.set_unusable_password()
    old.save(update_fields={"is_staff", "is_superuser", "password"})
    current = staff_user("staging_emergency_new_243", superuser=True)
    assert inspect_emergency_state() == "READY"
    current.is_staff = False
    current.is_superuser = False
    current.set_unusable_password()
    current.save(update_fields={"is_staff", "is_superuser", "password"})
    assert inspect_emergency_state() == "DECOMMISSIONED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "abnormal", ("two_active", "third_row", "extra_superuser", "abnormal_old")
)
def test_emergency_inspector_rejects_ambiguous_two_row_lifecycle(abnormal: str) -> None:
    """AC-5: a retained predecessor cannot hide another privileged actor."""
    from accounts.management.commands.bootstrap_staging_emergency_operator import (
        inspect_emergency_state,
    )

    old = staff_user("staging_emergency_prior_243", superuser=True)
    if abnormal != "two_active":
        old.is_staff = False
        old.is_superuser = False
        old.set_unusable_password()
        old.save(update_fields={"is_staff", "is_superuser", "password"})
    staff_user("staging_emergency_new_243", superuser=True)
    if abnormal == "third_row":
        third = staff_user("staging_emergency_third_243", superuser=True)
        third.is_staff = False
        third.is_superuser = False
        third.set_unusable_password()
        third.save(update_fields={"is_staff", "is_superuser", "password"})
    elif abnormal == "extra_superuser":
        staff_user("unrelated_admin", superuser=True)
    elif abnormal == "abnormal_old":
        old.is_staff = True
        old.save(update_fields={"is_staff"})
    assert inspect_emergency_state() == "MISMATCH"
