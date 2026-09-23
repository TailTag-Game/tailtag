"""Acceptance coverage for the read-only #243 Staging pre-mutation inspector."""

from __future__ import annotations

import builtins
import datetime
import importlib
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import FieldDoesNotExist
from django.db import DatabaseError
from django.utils import timezone

from accounts.management.commands.bootstrap_staging_operator import (
    EXPECTED_PERMISSION_NAMES,
    OPERATOR_GROUP_NAME,
)
from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from rehearsal import baseline
from rehearsal.models import StagingResetIdentity

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_operator_inspect.py"
SOURCE_SHA = "a" * 40
DEPLOYMENT_ID = "11111111-1111-4111-8111-111111111111"
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"
RUNTIME_SELECTORS = {
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "RAILWAY_SERVICE_NAME": "api",
    "RAILWAY_PROJECT_ID": "85324de4-be6a-49c3-a3f9-6cac13877849",
    "RAILWAY_ENVIRONMENT_ID": "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e",
    "RAILWAY_SERVICE_ID": "2247da27-97df-4d5d-b1dc-d21eeb7901d9",
}
# #204's reset sentinel is an independently generated identity. It deliberately
# differs from the Railway environment selector above.
RESET_ENVIRONMENT_ID = "a5f9e443-b520-437d-84cd-cf984f6eb3ba"

PASS = "PASS"
FAIL_FIXTURE_MISSING = "FAIL_FIXTURE_MISSING"
FAIL_FIXTURE_AMBIGUOUS = "FAIL_FIXTURE_AMBIGUOUS"
FAIL_FIXTURE_STATE_MISMATCH = "FAIL_FIXTURE_STATE_MISMATCH"
FAIL_MANAGED_OPERATOR_MISSING = "FAIL_MANAGED_OPERATOR_MISSING"
FAIL_MANAGED_OPERATOR_AMBIGUOUS = "FAIL_MANAGED_OPERATOR_AMBIGUOUS"
FAIL_MANAGED_OPERATOR_STATE = "FAIL_MANAGED_OPERATOR_STATE"
FAIL_MANAGED_OPERATOR_PERMISSION = "FAIL_MANAGED_OPERATOR_PERMISSION"
FAIL_LIMITED_OPERATOR_MISSING = "FAIL_LIMITED_OPERATOR_MISSING"
FAIL_LIMITED_OPERATOR_AMBIGUOUS = "FAIL_LIMITED_OPERATOR_AMBIGUOUS"
FAIL_LIMITED_OPERATOR_STATE = "FAIL_LIMITED_OPERATOR_STATE"
FAIL_LIMITED_OPERATOR_PERMISSION = "FAIL_LIMITED_OPERATOR_PERMISSION"
FAIL_UNEXPECTED_PRIVILEGE = "FAIL_UNEXPECTED_PRIVILEGE"
FAIL_EXECUTION = "FAIL_EXECUTION"
FAIL_INVALID_INPUT = "FAIL_INVALID_INPUT"
ALL_CODES = frozenset(
    {
        PASS,
        FAIL_FIXTURE_MISSING,
        FAIL_FIXTURE_AMBIGUOUS,
        FAIL_FIXTURE_STATE_MISMATCH,
        FAIL_MANAGED_OPERATOR_MISSING,
        FAIL_MANAGED_OPERATOR_AMBIGUOUS,
        FAIL_MANAGED_OPERATOR_STATE,
        FAIL_MANAGED_OPERATOR_PERMISSION,
        FAIL_LIMITED_OPERATOR_MISSING,
        FAIL_LIMITED_OPERATOR_AMBIGUOUS,
        FAIL_LIMITED_OPERATOR_STATE,
        FAIL_LIMITED_OPERATOR_PERMISSION,
        FAIL_UNEXPECTED_PRIVILEGE,
        FAIL_EXECUTION,
        FAIL_INVALID_INPUT,
    }
)
LIMITED_PERMISSION_NAMES = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)


class PermissionRelation(Protocol):
    """The narrow Django relation surface used to construct disposable roles."""

    def set(self, objects: object) -> None: ...

    def add(self, *objects: Permission) -> None: ...

    def remove(self, *objects: Permission) -> None: ...


class GroupRelation(Protocol):
    """The narrow Django relation surface used to construct disposable roles."""

    def add(self, *objects: Group) -> None: ...

    def get(self) -> Group: ...


class GroupWithPermissions(Protocol):
    """The managed group relation inspected by the frozen #205 contract."""

    permissions: PermissionRelation


class UserWithRoles(Protocol):
    """The role relations inspected by the frozen #205 and #243 contracts."""

    groups: GroupRelation
    user_permissions: PermissionRelation


def permission_name(permission: Permission) -> str:
    """Return the stable Django permission name despite incomplete third-party stubs."""
    return f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]


def permission_map() -> dict[str, Permission]:
    """Resolve the frozen #205 permission contract from the real Django registry."""
    permissions = {
        permission_name(permission): permission
        for permission in Permission.objects.select_related("content_type")
        if permission_name(permission) in EXPECTED_PERMISSION_NAMES
    }
    assert set(permissions) == EXPECTED_PERMISSION_NAMES
    return permissions


def staff_user(identifier: str, *, superuser: bool = False) -> User:
    """Create a disposable staff identity with the local-admin credential shape."""
    user = User(clerk_user_id=identifier, is_staff=True, is_superuser=superuser)
    user.set_password("local-inspector-test-password")
    user.save()
    return user


def create_managed_operator() -> User:
    """Build precisely the managed #205 bootstrap shape with real relations."""
    operator = staff_user("managed-operator")
    group = Group.objects.create(name=OPERATOR_GROUP_NAME)
    cast(GroupWithPermissions, group).permissions.set(tuple(permission_map().values()))
    cast(UserWithRoles, operator).groups.add(group)
    return operator


def create_limited_operator(
    permission_names: frozenset[str] = LIMITED_PERMISSION_NAMES,
) -> User:
    """Build the distinct one-action #243 operator using direct permissions only."""
    operator = staff_user("limited-operator")
    permissions = permission_map()
    cast(UserWithRoles, operator).user_permissions.add(
        *(permissions[name] for name in permission_names)
    )
    return operator


def create_owned_baseline() -> StagingResetIdentity:
    """Build the exact disposable #204 semantic baseline expected by the guard."""
    owner = User.objects.create_user("rehearsal-owner")
    catcher = User.objects.create_user("rehearsal-catcher")
    now = timezone.now()
    PlayerProfile.objects.create(
        user=owner,
        handle="tt_rehearsal_owner",
        display_name="TailTag Rehearsal Owner",
        avatar_key=MEDIA_KEY,
        onboarding_completed_at=now,
        is_enabled=True,
    )
    PlayerProfile.objects.create(
        user=catcher,
        handle="tt_rehearsal_catcher",
        display_name="TailTag Rehearsal Catcher",
        avatar_key=MEDIA_KEY,
        onboarding_completed_at=now,
        is_enabled=True,
    )
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2036, 9, 1),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=True,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=True,
    )
    for user in (owner, catcher):
        ConventionEnrollment.objects.create(
            user=user, convention=convention, is_active=True
        )
    for fursuit in (first, second):
        FursuitActivation.objects.create(
            fursuit=fursuit,
            convention=convention,
            is_active=True,
            activated_at=now,
        )
    return StagingResetIdentity.objects.create(
        id=1,
        environment_id=uuid.UUID(RESET_ENVIRONMENT_ID),
        cluster_identifier="123",
        database_name="test_tailtag",
        media_key=MEDIA_KEY,
        owner=owner,
        catcher=catcher,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )


@pytest.fixture
def inspector() -> ModuleType:
    """Import the repository-owned read-only inspector once it exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_operator_inspect.py must exist"
    return importlib.import_module("scripts.api_staging_operator_inspect")


@pytest.fixture
def configured_inspector(
    inspector: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> ModuleType:
    """Bind every local run to the only accepted runtime identity tuple."""
    for name, value in RUNTIME_SELECTORS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        inspector,
        "get_identity",
        lambda: {
            "source_sha": SOURCE_SHA,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
        },
    )
    return inspector


def inspect(script: ModuleType) -> str:
    """Exercise the public pre-mutation guard with its expected build identity."""
    return cast(str, script.inspect_preconditions(SOURCE_SHA, DEPLOYMENT_ID))


@pytest.mark.django_db
def test_real_user_model_has_no_mapped_is_active_field() -> None:
    """Regression: #243 must never filter the custom User ORM model by is_active."""
    with pytest.raises(FieldDoesNotExist):
        User._meta.get_field("is_active")


@pytest.mark.django_db
def test_exact_owned_baseline_and_distinct_exact_roles_pass(
    configured_inspector: ModuleType,
) -> None:
    """The guard accepts only a real #204 baseline with both required role shapes."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    assert inspect(configured_inspector) == PASS


@pytest.mark.django_db
def test_distinct_railway_and_reset_environment_uuids_reach_both_role_checks(
    configured_inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Railway selector and #204 sentinel are separate UUID namespaces."""
    assert RESET_ENVIRONMENT_ID != RUNTIME_SELECTORS["RAILWAY_ENVIRONMENT_ID"]
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    managed_check = configured_inspector._validate_managed_operator
    limited_check = configured_inspector._validate_limited_operator
    reached: list[str] = []

    def validate_managed() -> str | None:
        reached.append("managed")
        return cast(str | None, managed_check())

    def validate_limited() -> str | None:
        reached.append("limited")
        return cast(str | None, limited_check())

    monkeypatch.setattr(
        configured_inspector, "_validate_managed_operator", validate_managed
    )
    monkeypatch.setattr(
        configured_inspector, "_validate_limited_operator", validate_limited
    )

    assert inspect(configured_inspector) == PASS
    assert reached == ["managed", "limited"]


@pytest.mark.django_db
def test_previous_unmapped_is_active_lookup_cannot_hide_a_valid_preflight(
    configured_inspector: ModuleType,
) -> None:
    """Regression: a valid fixture reaches PASS, which an is_active ORM query cannot."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    assert inspect(configured_inspector) == PASS


@pytest.mark.django_db
def test_missing_owned_baseline_has_distinct_failure(
    configured_inspector: ModuleType,
) -> None:
    """A missing #204 registry cannot be relabelled as an operator failure."""
    create_managed_operator()
    create_limited_operator()

    assert inspect(configured_inspector) == FAIL_FIXTURE_MISSING


@pytest.mark.django_db
def test_ambiguous_owned_baseline_has_distinct_failure(
    configured_inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The singleton guard reports impossible registry corruption without guessing."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    def ambiguous(*_: object, **__: object) -> None:
        raise StagingResetIdentity.MultipleObjectsReturned

    monkeypatch.setattr(StagingResetIdentity.objects, "get", ambiguous)

    assert inspect(configured_inspector) == FAIL_FIXTURE_AMBIGUOUS


@pytest.mark.django_db
def test_malformed_registry_baseline_has_distinct_failure(
    configured_inspector: ModuleType,
) -> None:
    """A present but noncanonical #204 baseline fails before role assertions."""
    identity = create_owned_baseline()
    create_managed_operator()
    create_limited_operator()
    Fursuit.objects.filter(pk=identity.first_fursuit_id).update(is_enabled=False)

    assert inspect(configured_inspector) == FAIL_FIXTURE_STATE_MISMATCH


@pytest.mark.django_db
def test_non_v4_reset_sentinel_remains_a_fixture_state_failure(
    configured_inspector: ModuleType,
) -> None:
    """The #204 reset UUID is validated by its own sentinel contract, not Railway."""
    identity = create_owned_baseline()
    create_managed_operator()
    create_limited_operator()
    identity.environment_id = uuid.uuid1()
    identity.save(update_fields={"environment_id"})

    assert inspect(configured_inspector) == FAIL_FIXTURE_STATE_MISMATCH


@pytest.mark.django_db
def test_missing_managed_operator_has_distinct_failure(
    configured_inspector: ModuleType,
) -> None:
    """The inspector requires the bootstrap-managed role even when limited is valid."""
    create_owned_baseline()
    create_limited_operator()

    assert inspect(configured_inspector) == FAIL_MANAGED_OPERATOR_MISSING


@pytest.mark.django_db
def test_multiple_members_of_managed_group_fail_closed_as_ambiguous(
    configured_inspector: ModuleType,
) -> None:
    """The normal managed group must have exactly one associated operator."""
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    extra = staff_user("another-managed-operator")
    cast(UserWithRoles, extra).groups.add(cast(UserWithRoles, managed).groups.get())

    assert inspect(configured_inspector) == FAIL_MANAGED_OPERATOR_AMBIGUOUS


@pytest.mark.django_db
def test_managed_operator_permission_drift_has_distinct_failure(
    configured_inspector: ModuleType,
) -> None:
    """Managed authority must retain the exact group permission contract."""
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    group = cast(UserWithRoles, managed).groups.get()
    cast(GroupWithPermissions, group).permissions.remove(
        permission_map()["fursuits.set_fursuit_enabled"]
    )

    assert inspect(configured_inspector) == FAIL_MANAGED_OPERATOR_PERMISSION


@pytest.mark.django_db
def test_managed_superuser_is_unexpected_privilege(
    configured_inspector: ModuleType,
) -> None:
    """A managed-shaped normal operator may never silently become superuser."""
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    managed.is_superuser = True
    managed.save(update_fields={"is_superuser"})

    assert inspect(configured_inspector) == FAIL_UNEXPECTED_PRIVILEGE


@pytest.mark.django_db
def test_managed_operator_direct_permission_drift_fails_distinctly(
    configured_inspector: ModuleType,
) -> None:
    """The bootstrap-managed role receives its authority only through its sole group."""
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    cast(UserWithRoles, managed).user_permissions.add(
        permission_map()["profiles.set_profile_enabled"]
    )

    assert inspect(configured_inspector) == FAIL_MANAGED_OPERATOR_PERMISSION


@pytest.mark.django_db
def test_managed_operator_role_state_drift_is_not_permission_drift(
    configured_inspector: ModuleType,
) -> None:
    """Managed staff shape remains distinct from its exact permission contract."""
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    managed.is_staff = False
    managed.save(update_fields={"is_staff"})

    assert inspect(configured_inspector) == FAIL_MANAGED_OPERATOR_STATE


@pytest.mark.django_db
def test_distinct_limited_operator_with_exact_profile_permissions_passes(
    configured_inspector: ModuleType,
) -> None:
    """The one-action operator is independently validated rather than inferred."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    assert inspect(configured_inspector) == PASS


@pytest.mark.django_db
def test_full_managed_operator_cannot_satisfy_limited_operator_fixture(
    configured_inspector: ModuleType,
) -> None:
    """A broader managed role cannot be reused for the restricted matrix actor."""
    create_owned_baseline()
    create_managed_operator()

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_MISSING


@pytest.mark.django_db
def test_limited_operator_excess_sensitive_permission_fails_distinctly(
    configured_inspector: ModuleType,
) -> None:
    """The limited role must not inherit the fursuit action it is meant to fail."""
    create_owned_baseline()
    create_managed_operator()
    limited = create_limited_operator()
    cast(UserWithRoles, limited).user_permissions.add(
        permission_map()["fursuits.set_fursuit_enabled"]
    )

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_PERMISSION


@pytest.mark.django_db
def test_limited_superuser_is_unexpected_privilege(
    configured_inspector: ModuleType,
) -> None:
    """A restricted rehearsal role must never silently gain emergency authority."""
    create_owned_baseline()
    create_managed_operator()
    limited = create_limited_operator()
    limited.is_superuser = True
    limited.save(update_fields={"is_superuser"})

    assert inspect(configured_inspector) == FAIL_UNEXPECTED_PRIVILEGE


@pytest.mark.django_db
def test_limited_operator_missing_profile_action_fails_distinctly(
    configured_inspector: ModuleType,
) -> None:
    """The permitted profile action must be present before an attempted denial run."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator(frozenset({"profiles.view_playerprofile"}))

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_PERMISSION


@pytest.mark.django_db
def test_limited_operator_role_state_drift_is_not_permission_drift(
    configured_inspector: ModuleType,
) -> None:
    """The limited actor's staff credential shape is distinct from its authority."""
    create_owned_baseline()
    create_managed_operator()
    limited = create_limited_operator()
    limited.set_unusable_password()
    limited.save(update_fields={"password"})

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_STATE


@pytest.mark.django_db
def test_nonstaff_limited_shape_is_role_state_mismatch_not_missing(
    configured_inspector: ModuleType,
) -> None:
    """A discoverable limited fixture with invalid staff state must not be relabelled absent."""
    create_owned_baseline()
    create_managed_operator()
    limited = User(clerk_user_id="nonstaff-limited-operator", is_staff=False)
    limited.save()
    permissions = permission_map()
    cast(UserWithRoles, limited).user_permissions.add(
        *(permissions[name] for name in LIMITED_PERMISSION_NAMES)
    )

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_STATE


@pytest.mark.django_db
def test_multiple_limited_candidates_fail_closed_as_ambiguous(
    configured_inspector: ModuleType,
) -> None:
    """The guard refuses to guess which exact limited identity owns the rehearsal."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()
    extra = staff_user("another-limited-operator")
    cast(UserWithRoles, extra).user_permissions.add(
        *(permission_map()[name] for name in LIMITED_PERMISSION_NAMES)
    )

    assert inspect(configured_inspector) == FAIL_LIMITED_OPERATOR_AMBIGUOUS


@pytest.mark.django_db
def test_query_failure_is_sanitized_as_execution_failure(
    configured_inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected ORM failure must not be misreported as a live fixture diagnosis."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()

    def unavailable(*_: object, **__: object) -> None:
        raise DatabaseError("secret database endpoint")

    monkeypatch.setattr(StagingResetIdentity.objects, "get", unavailable)

    assert inspect(configured_inspector) == FAIL_EXECUTION


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("source_sha", "deployment_id"),
    (("not-a-sha", DEPLOYMENT_ID), (SOURCE_SHA, "not-a-deployment")),
)
def test_malformed_expected_identity_fails_before_fixture_inspection(
    configured_inspector: ModuleType, source_sha: str, deployment_id: str
) -> None:
    """Malformed public inputs fail closed without reading private fixture state."""
    result = configured_inspector.inspect_preconditions(source_sha, deployment_id)

    assert result == FAIL_INVALID_INPUT


@pytest.mark.django_db
def test_mismatched_running_build_identity_fails_before_fixture_inspection(
    configured_inspector: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The target-bound public tuple cannot be substituted for another deployment."""
    monkeypatch.setattr(
        configured_inspector,
        "get_identity",
        lambda: {
            "source_sha": "b" * 40,
            "deployment_id": DEPLOYMENT_ID,
            "environment": "staging",
        },
    )

    assert inspect(configured_inspector) == FAIL_INVALID_INPUT


@pytest.mark.django_db
def test_mismatched_railway_environment_selector_fails_before_orm_inspection(
    configured_inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Railway selector drift remains a target failure despite an independent reset UUID."""
    create_owned_baseline()
    create_managed_operator()
    create_limited_operator()
    reached_fixture_guard = False

    def fixture_guard() -> str | None:
        nonlocal reached_fixture_guard
        reached_fixture_guard = True
        return None

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "00000000-0000-4000-8000-000000000000")
    monkeypatch.setattr(configured_inspector, "_validate_fixture", fixture_guard)

    assert inspect(configured_inspector) == FAIL_INVALID_INPUT
    assert not reached_fixture_guard


def test_main_prints_one_allowlisted_code_for_malformed_arguments(
    inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI preserves the no-identifiers/no-permission-dumps evidence boundary."""
    monkeypatch.setattr(sys, "argv", ["api_staging_operator_inspect.py", "--bad"])

    assert inspector.main() != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == FAIL_INVALID_INPUT


def test_stdin_inspector_from_root_cwd_fails_closed_without_traceback() -> None:
    """A streamed inspector must not depend on its checkout path being its cwd."""
    result = subprocess.run(
        [sys.executable, "-", "--bad"],
        cwd=Path("/"),
        input=SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == FAIL_INVALID_INPUT
    assert "Traceback" not in result.stderr


def test_main_never_reflects_an_execution_exception(
    inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed inspector never leaks an exception message into durable evidence."""
    secret = "private-operator-identity"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_operator_inspect.py",
            "--expected-source-sha",
            SOURCE_SHA,
            "--expected-deployment-id",
            DEPLOYMENT_ID,
        ],
    )

    def unavailable() -> None:
        raise DatabaseError(secret)

    monkeypatch.setattr(inspector, "get_identity", unavailable)

    assert inspector.main() != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == FAIL_EXECUTION
    assert secret not in captured.err


def test_main_sanitizes_build_identity_import_failure(
    inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A streamed runner must not print a traceback if identity code cannot load."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_operator_inspect.py",
            "--expected-source-sha",
            SOURCE_SHA,
            "--expected-deployment-id",
            DEPLOYMENT_ID,
        ],
    )
    original_import = builtins.__import__

    def unavailable(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "config.build_identity":
            raise ImportError("private-path-detail")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)

    assert inspector.main() != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == FAIL_EXECUTION
    assert "private-path-detail" not in captured.err


def test_all_rendered_statuses_are_fixed_sanitized_codes(
    inspector: ModuleType,
) -> None:
    """Evidence cannot render identities, permissions, target values, or exceptions."""
    assert frozenset(inspector.STATUS_CODES) == ALL_CODES
    assert all(
        value.isascii()
        and value.replace("_", "").isalnum()
        and " " not in value
        and "@" not in value
        for value in inspector.STATUS_CODES
    )
