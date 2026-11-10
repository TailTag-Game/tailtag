"""Fail-closed, read-only pre-mutation guard for the bounded #243 exercise."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from django.contrib.auth.models import Group

    from accounts.models import User

PASS: Final = "PASS"
FAIL_FIXTURE_MISSING: Final = "FAIL_FIXTURE_MISSING"
FAIL_FIXTURE_AMBIGUOUS: Final = "FAIL_FIXTURE_AMBIGUOUS"
FAIL_FIXTURE_STATE_MISMATCH: Final = "FAIL_FIXTURE_STATE_MISMATCH"
FAIL_MANAGED_OPERATOR_MISSING: Final = "FAIL_MANAGED_OPERATOR_MISSING"
FAIL_MANAGED_OPERATOR_AMBIGUOUS: Final = "FAIL_MANAGED_OPERATOR_AMBIGUOUS"
FAIL_MANAGED_OPERATOR_STATE: Final = "FAIL_MANAGED_OPERATOR_STATE"
FAIL_MANAGED_OPERATOR_PERMISSION: Final = "FAIL_MANAGED_OPERATOR_PERMISSION"
# The group holds exactly the permission set from before #504. The
# managed-upgrade operation moves it to the current set.
FAIL_MANAGED_OPERATOR_UPGRADABLE: Final = "FAIL_MANAGED_OPERATOR_UPGRADABLE"
FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE: Final = (
    "FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE"
)
FAIL_LIMITED_OPERATOR_MISSING: Final = "FAIL_LIMITED_OPERATOR_MISSING"
FAIL_LIMITED_OPERATOR_AMBIGUOUS: Final = "FAIL_LIMITED_OPERATOR_AMBIGUOUS"
FAIL_LIMITED_OPERATOR_STATE: Final = "FAIL_LIMITED_OPERATOR_STATE"
FAIL_LIMITED_OPERATOR_PERMISSION: Final = "FAIL_LIMITED_OPERATOR_PERMISSION"
FAIL_UNEXPECTED_PRIVILEGE: Final = "FAIL_UNEXPECTED_PRIVILEGE"
FAIL_EXECUTION: Final = "FAIL_EXECUTION"
FAIL_INVALID_INPUT: Final = "FAIL_INVALID_INPUT"

STATUS_CODES: Final = frozenset(
    {
        PASS,
        FAIL_FIXTURE_MISSING,
        FAIL_FIXTURE_AMBIGUOUS,
        FAIL_FIXTURE_STATE_MISMATCH,
        FAIL_MANAGED_OPERATOR_MISSING,
        FAIL_MANAGED_OPERATOR_AMBIGUOUS,
        FAIL_MANAGED_OPERATOR_STATE,
        FAIL_MANAGED_OPERATOR_PERMISSION,
        FAIL_MANAGED_OPERATOR_UPGRADABLE,
        FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE,
        FAIL_LIMITED_OPERATOR_MISSING,
        FAIL_LIMITED_OPERATOR_AMBIGUOUS,
        FAIL_LIMITED_OPERATOR_STATE,
        FAIL_LIMITED_OPERATOR_PERMISSION,
        FAIL_UNEXPECTED_PRIVILEGE,
        FAIL_EXECUTION,
        FAIL_INVALID_INPUT,
    }
)

_LIMITED_PERMISSION_NAMES: Final = {
    "profiles.set_profile_enabled",
    "profiles.view_playerprofile",
}
_OPERATOR_GROUP_NAME: Final = "TailTag Field Beta Operators"
_LIMITED_OPERATOR_GROUP_NAME: Final = "TailTag #243 Validation Operator"


def _permission_names(queryset: object) -> set[str]:
    permissions = cast(
        list[tuple[str, str]],
        queryset.values_list("content_type__app_label", "codename"),  # type: ignore[attr-defined]
    )
    return {f"{app_label}.{codename}" for app_label, codename in permissions}


def _validate_fixture() -> str | None:
    from operator_audit.models import OperatorAuditEvent
    from rehearsal.models import StagingResetIdentity
    from rehearsal.reset import validate_baseline
    from rehearsal.safety import ResetSafetyError

    try:
        identity = StagingResetIdentity.objects.get()
    except StagingResetIdentity.DoesNotExist:
        return FAIL_FIXTURE_MISSING
    except StagingResetIdentity.MultipleObjectsReturned:
        return FAIL_FIXTURE_AMBIGUOUS

    if (
        identity.pk != 1
        or identity.environment_id.version != 4
        or identity.owner_id == identity.catcher_id
        or identity.owner.is_staff
        or identity.catcher.is_staff
        or cast(bool, identity.owner.is_superuser)  # pyright: ignore[reportUnknownMemberType]
        or cast(bool, identity.catcher.is_superuser)  # pyright: ignore[reportUnknownMemberType]
    ):
        return FAIL_FIXTURE_STATE_MISMATCH
    try:
        validate_baseline(identity)
        OperatorAuditEvent.objects.exists()
    except ResetSafetyError:
        return FAIL_FIXTURE_STATE_MISMATCH
    return None


def _validate_managed_operator() -> str | None:
    from django.contrib.auth.models import Group

    from accounts.management.commands.bootstrap_staging_operator import (
        EXPECTED_PERMISSION_NAMES,
        OPERATOR_GROUP_NAME,
        PREVIOUS_PERMISSION_NAMES,
    )
    from accounts.models import User

    try:
        group = Group.objects.get(name=OPERATOR_GROUP_NAME)
    except Group.DoesNotExist:
        return FAIL_MANAGED_OPERATOR_MISSING
    except Group.MultipleObjectsReturned:
        return FAIL_MANAGED_OPERATOR_AMBIGUOUS

    members = list(User.objects.filter(groups=group))
    if not members:
        return FAIL_MANAGED_OPERATOR_MISSING
    if len(members) != 1:
        return FAIL_MANAGED_OPERATOR_AMBIGUOUS
    operator = members[0]
    if cast(bool, operator.is_superuser):  # pyright: ignore[reportUnknownMemberType]
        return FAIL_UNEXPECTED_PRIVILEGE
    if (
        not operator.is_staff
        or list(operator.groups.values_list("pk", flat=True)) != [group.pk]  # pyright: ignore[reportUnknownMemberType]
    ):
        return FAIL_MANAGED_OPERATOR_STATE
    if operator.user_permissions.exists():  # pyright: ignore[reportUnknownMemberType]
        return FAIL_MANAGED_OPERATOR_PERMISSION
    group_permissions = _permission_names(group.permissions)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if group_permissions == PREVIOUS_PERMISSION_NAMES:
        return FAIL_MANAGED_OPERATOR_UPGRADABLE
    if group_permissions != EXPECTED_PERMISSION_NAMES:
        return FAIL_MANAGED_OPERATOR_PERMISSION
    if not operator.has_usable_password():
        return FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE
    return None


def _limited_candidates() -> list[User]:
    from django.db.models import Q

    from accounts.models import User

    explicit_profile_permission = Q(
        user_permissions__content_type__app_label="profiles",
        user_permissions__codename__in=("set_profile_enabled", "view_playerprofile"),
    ) | Q(
        groups__permissions__content_type__app_label="profiles",
        groups__permissions__codename__in=(
            "set_profile_enabled",
            "view_playerprofile",
        ),
    )
    return list(
        User.objects.exclude(groups__name=_OPERATOR_GROUP_NAME)
        .filter(
            explicit_profile_permission | Q(groups__name=_LIMITED_OPERATOR_GROUP_NAME)
        )
        .distinct()
    )


def _limited_group(operator: User) -> Group | None:
    from accounts.models import User
    from catches.models import Catch
    from conventions.models import ConventionEnrollment
    from fursuits.models import Fursuit
    from profiles.models import PlayerProfile

    groups = list(operator.groups.all())  # pyright: ignore[reportUnknownMemberType]
    if (
        len(groups) != 1
        or groups[0].name  # pyright: ignore[reportUnknownMemberType]
        != _LIMITED_OPERATOR_GROUP_NAME
    ):
        return None
    group = groups[0]
    if list(User.objects.filter(groups=group).values_list("pk", flat=True)) != [
        operator.pk
    ]:
        return None
    if (
        PlayerProfile.objects.filter(user=operator).exists()
        or Fursuit.objects.filter(owner=operator).exists()
        or ConventionEnrollment.objects.filter(user=operator).exists()
        or Catch.objects.filter(catcher_user=operator).exists()
    ):
        return None
    return group


def _validate_limited_operator() -> str | None:
    from django.contrib.auth.models import Permission

    candidates = _limited_candidates()
    if not candidates:
        return FAIL_LIMITED_OPERATOR_MISSING
    if len(candidates) != 1:
        return FAIL_LIMITED_OPERATOR_AMBIGUOUS
    operator = candidates[0]
    if cast(bool, operator.is_superuser):  # pyright: ignore[reportUnknownMemberType]
        return FAIL_UNEXPECTED_PRIVILEGE
    if not operator.is_staff or not operator.has_usable_password():
        return FAIL_LIMITED_OPERATOR_STATE
    group = _limited_group(operator)
    if group is None:
        return FAIL_LIMITED_OPERATOR_STATE
    canonical_permissions = cast(
        list[tuple[int, str]],
        list(
            Permission.objects.filter(
                content_type__app_label="profiles",
                content_type__model="playerprofile",
                codename__in=("set_profile_enabled", "view_playerprofile"),
            ).values_list("pk", "codename")
        ),
    )
    if (
        len(canonical_permissions) != 2
        or {f"profiles.{codename}" for _, codename in canonical_permissions}
        != _LIMITED_PERMISSION_NAMES
        or operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or set(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
        != {pk for pk, _ in canonical_permissions}
    ):
        return FAIL_LIMITED_OPERATOR_PERMISSION
    return None


def _validate_decommissioned_operator() -> str | None:  # pyright: ignore[reportUnusedFunction]
    candidates = _limited_candidates()
    if not candidates:
        return FAIL_LIMITED_OPERATOR_MISSING
    if len(candidates) != 1:
        return FAIL_LIMITED_OPERATOR_AMBIGUOUS
    operator = candidates[0]
    if cast(bool, operator.is_superuser):  # pyright: ignore[reportUnknownMemberType]
        return FAIL_UNEXPECTED_PRIVILEGE
    if operator.is_staff or operator.has_usable_password():
        return FAIL_LIMITED_OPERATOR_STATE
    group = _limited_group(operator)
    if group is None:
        return FAIL_LIMITED_OPERATOR_STATE
    if (
        operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or group.permissions.exists()  # pyright: ignore[reportUnknownMemberType]
    ):
        return FAIL_LIMITED_OPERATOR_PERMISSION
    return None


def inspect_orm_preconditions() -> str:
    try:
        for check in (
            _validate_fixture,
            _validate_managed_operator,
            _validate_limited_operator,
        ):
            result = check()
            if result is not None:
                return result
    except Exception:  # noqa: BLE001
        return FAIL_EXECUTION
    return PASS
