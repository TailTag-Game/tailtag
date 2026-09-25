"""Manage the dedicated #243 validation operator on Railway Staging."""

from __future__ import annotations

import getpass
import os
import sys
import unicodedata
import warnings
from typing import NoReturn, cast

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, connection, transaction
from django.db.models import Q

from accounts.models import User
from catches.models import Catch
from conventions.models import ConventionEnrollment
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

GROUP_NAME = "TailTag #243 Validation Operator"
PERMISSION_NAMES = frozenset(
    {"profiles.set_profile_enabled", "profiles.view_playerprofile"}
)
CONFIRMATIONS = {
    "provision": "provision Railway Staging validation operator",
    "decommission": "decommission Railway Staging validation operator",
    "rotate_password": "rotate Railway Staging validation operator password",
}


def _hidden_input(prompt: str) -> str:
    """Read a secret only when getpass can disable terminal echo."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise CommandError("Hidden terminal input is unavailable.") from None


class Command(BaseCommand):
    """Manage the exact limited validation role."""

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=tuple(CONFIRMATIONS))

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
        action = options.get("action")
        if not isinstance(action, str) or action not in CONFIRMATIONS:
            raise CommandError("Invalid command arguments.")
        if (
            os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
            or os.environ.get("RAILWAY_SERVICE_NAME") != "api"
        ):
            raise CommandError("This command is unavailable for the current target.")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError("This command requires an interactive terminal.")
        if settings.DEBUG or connection.force_debug_cursor:
            raise CommandError("Query debugging must be disabled.")
        if input("Confirmation: ") != CONFIRMATIONS[action]:
            raise CommandError("Confirmation failed.")

        operator: User | None = None
        if action == "rotate_password":
            try:
                with transaction.atomic():
                    operator = self._sole_limited_operator()
                    if not self._active_exact(operator, self._required_permissions()):
                        raise CommandError(
                            "Existing account cannot be used as an operator."
                        )
            except DatabaseError:
                raise CommandError("Validation operator action failed.") from None
            identifier = operator.clerk_user_id
        else:
            identifier = _hidden_input("Operator identifier: ")
            if (
                not identifier
                or len(identifier) > 255
                or any(
                    character.isspace() or unicodedata.category(character) == "Cc"
                    for character in identifier
                )
            ):
                raise CommandError("Operator identifier is invalid.")

        password = ""
        if action in {"provision", "rotate_password"}:
            password = _hidden_input("Password: ")
            if password != _hidden_input("Confirm password: "):
                raise CommandError("Passwords do not match.")
            candidate = User(
                clerk_user_id=identifier, is_staff=True, is_superuser=False
            )
            try:
                validate_password(password, candidate)
            except ValidationError:
                raise CommandError(
                    "Password does not meet operator requirements."
                ) from None

        try:
            permissions = self._required_permissions()
            with transaction.atomic():
                if action == "rotate_password":
                    current = self._sole_limited_operator()
                    if (
                        operator is None
                        or current.pk != operator.pk
                        or current.clerk_user_id != identifier
                    ):
                        raise CommandError(
                            "Existing account cannot be used as an operator."
                        )
                    operator = User.objects.select_for_update().get(pk=current.pk)
                else:
                    operator = (
                        User.objects.select_for_update()
                        .filter(clerk_user_id=identifier)
                        .first()
                    )
                if action == "provision":
                    if operator is None:
                        outcome = self._create(identifier, password, permissions)
                    else:
                        outcome = self._reconcile(operator, password, permissions)
                elif action == "decommission":
                    outcome = self._decommission(operator, permissions)
                else:
                    if operator is None or not self._active_exact(
                        operator, permissions
                    ):
                        raise CommandError(
                            "Existing account cannot be used as an operator."
                        )
                    operator.set_password(password)
                    operator.save(update_fields={"password"})
                    confirmed = self._sole_limited_operator()
                    if (
                        confirmed.pk != operator.pk
                        or not self._active_exact(confirmed, permissions)
                        or not check_password(
                            password,
                            cast(str, confirmed.password),  # pyright: ignore[reportUnknownMemberType]
                        )
                    ):
                        raise CommandError("Validation operator postcondition failed.")
                    outcome = "Validation operator password rotated."
        except DatabaseError:
            raise CommandError("Validation operator action failed.") from None

        self.stdout.write(outcome)

    @staticmethod
    def _required_permissions() -> tuple[Permission, ...]:
        permissions = tuple(Permission.objects.select_related("content_type"))
        matching = tuple(
            permission
            for permission in permissions
            if f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]
            in PERMISSION_NAMES
        )
        if (
            len(matching) != len(PERMISSION_NAMES)
            or {
                f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]
                for permission in matching
            }
            != set(PERMISSION_NAMES)
            or any(
                cast(str, permission.content_type.model)  # pyright: ignore[reportUnknownMemberType]
                != "playerprofile"
                for permission in matching
            )
        ):
            raise CommandError("Required operator permissions are unavailable.")
        return matching

    def _create(
        self, identifier: str, password: str, permissions: tuple[Permission, ...]
    ) -> str:
        if Group.objects.filter(name=GROUP_NAME).exists():
            raise CommandError("Existing group cannot be used as an operator.")
        operator = User(clerk_user_id=identifier, is_staff=True, is_superuser=False)
        operator.set_password(password)
        operator.save()
        group = Group.objects.create(name=GROUP_NAME)
        group.permissions.set(permissions)  # pyright: ignore[reportUnknownMemberType]
        operator.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
        return "Validation operator created."

    def _reconcile(
        self, operator: User, password: str, permissions: tuple[Permission, ...]
    ) -> str:
        group = self._exact_group(operator, {item.pk for item in permissions})
        if group is None or not operator.is_staff or not operator.has_usable_password():
            raise CommandError("Existing account cannot be used as an operator.")
        operator.set_password(password)
        operator.save(update_fields={"password"})
        return "Validation operator reconciled."

    @staticmethod
    def _sole_limited_operator() -> User:
        profile_permission = Q(
            user_permissions__content_type__app_label="profiles",
            user_permissions__codename__in=(
                "set_profile_enabled",
                "view_playerprofile",
            ),
        ) | Q(
            groups__permissions__content_type__app_label="profiles",
            groups__permissions__codename__in=(
                "set_profile_enabled",
                "view_playerprofile",
            ),
        )
        candidates = list(
            User.objects.exclude(groups__name="TailTag Field Beta Operators")
            .filter(profile_permission | Q(groups__name=GROUP_NAME))
            .distinct()[:2]
        )
        if len(candidates) != 1:
            raise CommandError("Existing account cannot be used as an operator.")
        return candidates[0]

    def _active_exact(
        self, operator: User, permissions: tuple[Permission, ...]
    ) -> bool:
        return bool(
            operator.is_staff
            and operator.has_usable_password()
            and self._exact_group(operator, {item.pk for item in permissions})
            is not None
        )

    def _decommission(
        self, operator: User | None, permissions: tuple[Permission, ...]
    ) -> str:
        if operator is None:
            raise CommandError("Existing account cannot be used as an operator.")
        active_group = self._exact_group(operator, {item.pk for item in permissions})
        if (
            active_group is not None
            and operator.is_staff
            and operator.has_usable_password()
        ):
            active_group.permissions.clear()  # pyright: ignore[reportUnknownMemberType]
            operator.is_staff = False
            operator.set_unusable_password()
            operator.save(update_fields={"is_staff", "password"})
            return "Validation operator decommissioned."
        inactive_group = self._exact_group(operator, set())
        if (
            inactive_group is not None
            and not operator.is_staff
            and not operator.has_usable_password()
        ):
            return "Validation operator already decommissioned."
        raise CommandError("Existing account cannot be used as an operator.")

    @staticmethod
    def _exact_group(operator: User, permission_ids: set[int]) -> Group | None:
        if cast(bool, operator.is_superuser) or operator.user_permissions.exists():  # pyright: ignore[reportUnknownMemberType]
            return None
        groups = tuple(operator.groups.all())  # pyright: ignore[reportUnknownMemberType]
        if len(groups) != 1 or groups[0].name != GROUP_NAME:  # pyright: ignore[reportUnknownMemberType]
            return None
        try:
            group = Group.objects.select_for_update().get(pk=groups[0].pk)
        except Group.DoesNotExist:
            return None
        if group.name != GROUP_NAME:  # pyright: ignore[reportUnknownMemberType]
            return None
        if set(group.permissions.values_list("pk", flat=True)) != permission_ids:  # pyright: ignore[reportUnknownMemberType]
            return None
        if set(User.objects.filter(groups=group).values_list("pk", flat=True)) != {
            operator.pk
        }:
            return None
        if (
            PlayerProfile.objects.filter(user=operator).exists()
            or Fursuit.objects.filter(owner=operator).exists()
            or ConventionEnrollment.objects.filter(user=operator).exists()
            or Catch.objects.filter(catcher_user=operator).exists()
        ):
            return None
        return group
