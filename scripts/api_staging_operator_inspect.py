"""Fail-closed, read-only pre-mutation guard for the bounded #243 exercise."""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn, cast

# ``__file__`` is deliberately a stable in-image name when this source is
# executed by the SSH bootstrap.  A direct ``python -`` invocation has no
# repository parent, however, so derive a possible local root without indexed
# ``parents`` access before deciding whether it is usable.
_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if _API_ROOT.is_dir() and str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

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

_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_LIMITED_PERMISSION_NAMES: Final = {
    "profiles.set_profile_enabled",
    "profiles.view_playerprofile",
}
_PRODUCTION_SETTINGS: Final = "config.settings.production"
_OPERATOR_GROUP_NAME: Final = "TailTag Field Beta Operators"
_LIMITED_OPERATOR_GROUP_NAME: Final = "TailTag #243 Validation Operator"


class _SafeArgumentParser(argparse.ArgumentParser):
    """Avoid reflecting command arguments into retained validation evidence."""

    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


def get_identity() -> Mapping[str, object]:
    """Load build identity only inside the sanitized execution boundary."""
    from config.build_identity import get_identity as read_identity

    return read_identity()


def _valid_expected_identity(source_sha: object, deployment_id: object) -> bool:
    if not isinstance(source_sha, str) or _SOURCE_SHA.fullmatch(source_sha) is None:
        return False
    if not isinstance(deployment_id, str):
        return False
    try:
        return str(uuid.UUID(deployment_id)) == deployment_id
    except ValueError:
        return False


def _target_identity_matches(source_sha: str, deployment_id: str) -> bool:
    identity = get_identity()
    if (
        identity.get("source_sha") != source_sha
        or identity.get("deployment_id") != deployment_id
        or identity.get("environment") != "staging"
    ):
        return False
    from config.replacement_target_binding import (
        TargetBindingError,
        validate_runtime_target,
    )

    if os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging":
        return False
    try:
        validate_runtime_target(os.environ)
    except TargetBindingError:
        return False
    return True


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
    if (
        operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or _permission_names(group.permissions) != EXPECTED_PERMISSION_NAMES  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    ):
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


def inspect_preconditions(expected_source_sha: str, expected_deployment_id: str) -> str:
    """Return one sanitized status for the exact, read-only #243 preconditions."""
    try:
        if not _valid_expected_identity(expected_source_sha, expected_deployment_id):
            return FAIL_INVALID_INPUT
        if not _target_identity_matches(expected_source_sha, expected_deployment_id):
            return FAIL_INVALID_INPUT
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


def _inspect_orm_preconditions() -> str:
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


def _arguments() -> tuple[str, str] | None:
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-deployment-id")
    try:
        arguments = parser.parse_args()
    except (SystemExit, ValueError):
        return None
    if (
        arguments.expected_source_sha is None
        or arguments.expected_deployment_id is None
    ):
        return None
    return arguments.expected_source_sha, arguments.expected_deployment_id


def _bootstrap() -> None:
    import django

    django.setup()


def main() -> int:
    """Run the repository-owned inspector and emit only its fixed status code."""
    arguments = _arguments()
    if arguments is None:
        result = FAIL_INVALID_INPUT
    else:
        try:
            if (
                not _valid_expected_identity(*arguments)
                or not _target_identity_matches(*arguments)
                or os.environ.get("DJANGO_SETTINGS_MODULE") != _PRODUCTION_SETTINGS
            ):
                result = FAIL_INVALID_INPUT
            else:
                _bootstrap()
                result = _inspect_orm_preconditions()
        except Exception:  # noqa: BLE001
            result = FAIL_EXECUTION
    if result == PASS:
        print(result)
        return 0
    print(result, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
