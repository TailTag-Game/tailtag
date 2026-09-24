"""Atomically replace the exact local managed Staging login for #243."""

from __future__ import annotations

import getpass
import logging
import os
import re
import sys
import warnings
from typing import NoReturn, cast

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, connection, transaction

from accounts.models import User
from catches.models import Catch
from config import build_identity
from conventions.models import ConventionEnrollment
from fursuits.models import Fursuit
from operator_audit.models import OperatorAuditEvent
from profiles.models import PlayerProfile
from rehearsal.models import StagingResetIdentity

from .bootstrap_staging_operator import EXPECTED_PERMISSION_NAMES, OPERATOR_GROUP_NAME

CONFIRMATION_PHRASE = "replace Railway Staging managed operator"
LIMITED_GROUP_NAME = "TailTag #243 Validation Operator"
LIMITED_PERMISSION_NAMES = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)
_IDENTIFIER = re.compile(r"staging_managed_[a-z0-9_]{1,64}\Z", re.ASCII)
_RAILWAY_SELECTORS = {
    "RAILWAY_PROJECT_ID": "85324de4-be6a-49c3-a3f9-6cac13877849",
    "RAILWAY_ENVIRONMENT_ID": "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e",
    "RAILWAY_SERVICE_ID": "2247da27-97df-4d5d-b1dc-d21eeb7901d9",
}
_MAX_AUDIT_ROWS = 10_000


def _hidden_input(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise CommandError("Hidden terminal input is unavailable.") from None


class Command(BaseCommand):
    """Transfer one exact managed role while retaining the predecessor User."""

    def create_parser(
        self, prog_name: str, subcommand: str, **kwargs: object
    ) -> CommandParser:
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.error = self._parser_error
        return parser

    def _parser_error(self, message: str) -> NoReturn:
        message = "Invalid command arguments. Use the documented interactive command."
        if getattr(self, "_called_from_command_line", False):
            self.stderr.write(message)
            raise SystemExit(2)
        raise CommandError(message)

    def handle(self, *args: object, **options: object) -> None:
        expected = options.get("expected_identity")
        if not self._target_matches(expected):
            raise CommandError("This command is unavailable for the current target.")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError("This command requires an interactive terminal.")
        if (
            settings.DEBUG
            or connection.force_debug_cursor
            or connection.execute_wrappers
            or logging.getLogger("django.db.backends").isEnabledFor(logging.DEBUG)
        ):
            raise CommandError("Query debugging must be disabled.")

        try:
            group, predecessor = self._exact_predecessor()
            pinned_pk = predecessor.pk
            pinned_identifier = predecessor.clerk_user_id
            pinned_group_pk = group.pk
            pinned_limited = self._limited_state()
            pinned_audit = self._audit_snapshot()
        except (
            DatabaseError,
            Group.DoesNotExist,
            Group.MultipleObjectsReturned,
            User.DoesNotExist,
        ):
            raise CommandError("Managed operator replacement failed.") from None

        if input("Confirmation: ") != CONFIRMATION_PHRASE:
            raise CommandError("Confirmation failed.")
        identifier = _hidden_input("New operator identifier: ")
        if not _IDENTIFIER.fullmatch(identifier):
            raise CommandError("Operator identifier is invalid.")
        try:
            if (
                identifier == predecessor.clerk_user_id
                or User.objects.filter(clerk_user_id=identifier).exists()
            ):
                raise CommandError("Operator identifier is unavailable.")
        except DatabaseError:
            raise CommandError("Managed operator replacement failed.") from None
        self.stdout.write("PREPARED")
        password = _hidden_input("Password: ")
        if password != _hidden_input("Confirm password: "):
            raise CommandError("Passwords do not match.")
        candidate = User(clerk_user_id=identifier, is_staff=True, is_superuser=False)
        try:
            validate_password(password, candidate)
        except ValidationError:
            raise CommandError(
                "Password does not meet operator requirements."
            ) from None

        try:
            with transaction.atomic():
                if not self._target_matches(expected):
                    raise CommandError(
                        "This command is unavailable for the current target."
                    )
                group, predecessor = self._exact_predecessor(lock=True)
                if group.pk != pinned_group_pk or predecessor.pk != pinned_pk:
                    raise CommandError("Managed operator state changed.")
                if (
                    self._limited_state() != pinned_limited
                    or self._audit_snapshot() != pinned_audit
                ):
                    raise CommandError("Staging prerequisite state changed.")
                permission_ids = set(
                    group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
                )
                if User.objects.filter(clerk_user_id=identifier).exists():
                    raise CommandError("Operator identifier is unavailable.")
                candidate.set_password(password)
                candidate.save(force_insert=True)
                predecessor.groups.remove(group)  # pyright: ignore[reportUnknownMemberType]
                candidate.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
                predecessor.is_staff = False
                predecessor.set_unusable_password()
                predecessor.save(update_fields={"is_staff", "password"})
                predecessor.refresh_from_db()
                candidate.refresh_from_db()
                if (
                    predecessor.pk != pinned_pk
                    or predecessor.clerk_user_id != pinned_identifier
                    or predecessor.is_staff
                    or cast(bool, predecessor.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                    or predecessor.has_usable_password()
                    or predecessor.groups.exists()  # pyright: ignore[reportUnknownMemberType]
                    or predecessor.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    or candidate.clerk_user_id != identifier
                    or not candidate.is_staff
                    or cast(bool, candidate.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                    or not candidate.has_usable_password()
                    or set(candidate.groups.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                    != {pinned_group_pk}
                    or candidate.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    or set(
                        User.objects.filter(groups=group).values_list("pk", flat=True)
                    )
                    != {candidate.pk}
                    or set(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                    != permission_ids
                ):
                    raise CommandError("Managed operator replacement failed.")
        except (
            DatabaseError,
            Group.DoesNotExist,
            Group.MultipleObjectsReturned,
            User.DoesNotExist,
        ):
            raise CommandError("Managed operator replacement failed.") from None
        self._postcommit_check(
            expected,
            pinned_pk,
            pinned_identifier,
            identifier,
            pinned_group_pk,
            permission_ids,
            pinned_limited,
            pinned_audit,
        )
        self.stdout.write("POSTCONDITION_PASS")

    def _postcommit_check(
        self,
        expected: object,
        old_pk: int,
        old_identifier: str,
        new_identifier: str,
        group_pk: int,
        permission_ids: set[int],
        limited_state: tuple[object, ...],
        audit_state: tuple[tuple[object, ...], ...],
    ) -> None:
        """Read the committed state without permitting another write."""
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                if not self._target_matches(expected):
                    raise CommandError("Managed operator postcondition failed.")
                retired = User.objects.get(pk=old_pk)
                replacement = User.objects.get(clerk_user_id=new_identifier)
                retained_group = Group.objects.get(pk=group_pk)
                if (
                    retired.clerk_user_id != old_identifier
                    or retired.is_staff
                    or cast(bool, retired.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                    or retired.has_usable_password()
                    or retired.groups.exists()  # pyright: ignore[reportUnknownMemberType]
                    or retired.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    or not replacement.is_staff
                    or cast(bool, replacement.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                    or not replacement.has_usable_password()
                    or set(replacement.groups.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                    != {group_pk}
                    or replacement.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    or set(
                        retained_group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
                    )
                    != permission_ids
                    or set(
                        User.objects.filter(groups=retained_group).values_list(
                            "pk", flat=True
                        )
                    )
                    != {replacement.pk}
                    or self._limited_state() != limited_state
                    or self._audit_snapshot() != audit_state
                ):
                    raise CommandError("Managed operator postcondition failed.")
        except (
            DatabaseError,
            Group.DoesNotExist,
            User.DoesNotExist,
        ):
            raise CommandError("Managed operator postcondition failed.") from None

    @staticmethod
    def _limited_state() -> tuple[object, ...]:
        group = Group.objects.get(name=LIMITED_GROUP_NAME)
        members = tuple(User.objects.filter(groups=group))
        if len(members) != 1:
            raise CommandError("Limited operator prerequisite failed.")
        operator = members[0]
        required_permissions = tuple(
            item
            for item in Permission.objects.select_related("content_type")
            if f"{item.content_type.app_label}.{item.codename}"  # pyright: ignore[reportUnknownMemberType]
            in LIMITED_PERMISSION_NAMES
        )
        group_permission_ids = set(
            group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
        )
        if (
            not operator.is_staff
            or cast(bool, operator.is_superuser)  # pyright: ignore[reportUnknownMemberType]
            or not operator.has_usable_password()
            or operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
            or set(operator.groups.values_list("pk", flat=True)) != {group.pk}  # pyright: ignore[reportUnknownMemberType]
            or len(required_permissions) != len(LIMITED_PERMISSION_NAMES)
            or any(
                cast(str, item.content_type.model)  # pyright: ignore[reportUnknownMemberType]
                != "playerprofile"
                for item in required_permissions
            )
            or group_permission_ids != {item.pk for item in required_permissions}
        ):
            raise CommandError("Limited operator prerequisite failed.")
        return (
            group.pk,
            operator.pk,
            operator.clerk_user_id,
            cast(str, operator.password),  # pyright: ignore[reportUnknownMemberType]
            tuple(sorted(group_permission_ids)),
        )

    @staticmethod
    def _audit_snapshot() -> tuple[tuple[object, ...], ...]:
        rows = tuple(
            OperatorAuditEvent.objects.order_by("pk").values_list(
                "pk",
                "action",
                "actor_id",
                "actor_class",
                "affected_record_type",
                "affected_record_id",
                "outcome",
                "occurred_at",
            )[: _MAX_AUDIT_ROWS + 1]
        )
        if len(rows) > _MAX_AUDIT_ROWS:
            raise CommandError("Audit prerequisite exceeds bounded inspection.")
        return rows

    @staticmethod
    def _target_matches(expected: object) -> bool:
        if not isinstance(expected, dict):
            return False
        identity = cast(dict[str, object], expected)
        if set(identity) != {
            "environment",
            "source_sha",
            "deployment_id",
        }:
            return False
        if (
            identity.get("environment") != "staging"
            or not isinstance(identity.get("source_sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", cast(str, identity["source_sha"])) is None
            or not isinstance(identity.get("deployment_id"), str)
            or os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
            or os.environ.get("RAILWAY_SERVICE_NAME") != "api"
            or any(
                os.environ.get(key) != value
                for key, value in _RAILWAY_SELECTORS.items()
            )
        ):
            return False
        try:
            return build_identity.get_identity() == identity
        except (ValueError, OSError):
            return False

    @staticmethod
    def _exact_predecessor(*, lock: bool = False) -> tuple[Group, User]:
        groups = Group.objects.filter(name=OPERATOR_GROUP_NAME)
        if lock:
            groups = groups.select_for_update()
        group = groups.get()
        permissions = tuple(Permission.objects.select_related("content_type"))
        required = {
            item.pk
            for item in permissions
            if f"{item.content_type.app_label}.{item.codename}"  # pyright: ignore[reportUnknownMemberType]
            in EXPECTED_PERMISSION_NAMES
        }
        if (
            len(required) != len(EXPECTED_PERMISSION_NAMES)
            or set(
                group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
            )
            != required
        ):
            raise CommandError("Managed operator state changed.")
        members = User.objects.filter(groups=group)
        if lock:
            members = members.select_for_update()
        member_ids = tuple(members.values_list("pk", flat=True))
        if len(member_ids) != 1:
            raise CommandError("Managed operator state changed.")
        operator = (
            User.objects.select_for_update().get(pk=member_ids[0])
            if lock
            else User.objects.get(pk=member_ids[0])
        )
        if (
            not operator.is_staff
            or cast(bool, operator.is_superuser)  # pyright: ignore[reportUnknownMemberType]
            or not operator.has_usable_password()
            or operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
            or set(operator.groups.values_list("pk", flat=True)) != {group.pk}  # pyright: ignore[reportUnknownMemberType]
            or PlayerProfile.objects.filter(user=operator).exists()
            or Fursuit.objects.filter(owner=operator).exists()
            or ConventionEnrollment.objects.filter(user=operator).exists()
            or Catch.objects.filter(catcher_user=operator).exists()
            or StagingResetIdentity.objects.filter(owner=operator).exists()
            or StagingResetIdentity.objects.filter(catcher=operator).exists()
        ):
            raise CommandError("Managed operator state changed.")
        return group, operator
