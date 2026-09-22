"""Bootstrap the limited Django operator for Railway Staging only."""

from __future__ import annotations

import getpass
import os
import sys
from collections.abc import Iterable
from typing import NoReturn, cast

from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, IntegrityError, transaction

from accounts.models import User

REQUIRED_ENVIRONMENT = "staging"
REQUIRED_SERVICE = "api"
CONFIRMATION_PHRASE = "bootstrap Railway Staging operator"
OPERATOR_GROUP_NAME = "TailTag Field Beta Operators"
EXPECTED_PERMISSION_NAMES = {
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

__all__ = ["Command"]


class Command(BaseCommand):
    """Create or reconcile the guarded Railway Staging operator."""

    def create_parser(
        self, prog_name: str, subcommand: str, **kwargs: object
    ) -> CommandParser:
        """Use Django's parser while keeping invalid CLI inputs private."""
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.error = self._parser_error
        return parser

    def handle(self, *args: object, **options: object) -> None:
        """Create or rotate the limited operator after guarded confirmation."""
        if (
            os.environ.get("RAILWAY_ENVIRONMENT_NAME") != REQUIRED_ENVIRONMENT
            or os.environ.get("RAILWAY_SERVICE_NAME") != REQUIRED_SERVICE
        ):
            raise CommandError("This command is unavailable for the current target.")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError("This command requires an interactive terminal.")
        if input("Confirmation: ") != CONFIRMATION_PHRASE:
            raise CommandError("Confirmation failed.")

        operator_id = getpass.getpass("Operator identifier: ")
        if not operator_id.strip():
            raise CommandError("Operator identifier is required.")
        password = getpass.getpass("Password: ")
        password_confirmation = getpass.getpass("Confirm password: ")
        if password != password_confirmation:
            raise CommandError("Passwords do not match.")

        candidate = User(
            clerk_user_id=operator_id,
            is_staff=True,
            is_superuser=False,
        )
        self._validate_password(password, candidate)

        try:
            permissions = self._required_permissions()
            with transaction.atomic():
                operator = (
                    User.objects.select_for_update()
                    .filter(clerk_user_id=operator_id)
                    .first()
                )
                if operator is None:
                    outcome = self._create_operator(operator_id, password, permissions)
                else:
                    outcome = self._reconcile_operator(password, operator, permissions)
        except DatabaseError:
            raise CommandError("Operator bootstrap failed.") from None

        self.stdout.write(outcome)

    def _parser_error(self, message: str) -> NoReturn:
        """Reject invalid command-line arguments without reflecting their values."""
        message = "Invalid command arguments. Use the documented interactive command."
        if getattr(self, "_called_from_command_line", False):
            self.stderr.write(message)
            raise SystemExit(2)
        raise CommandError(message)

    def _create_operator(
        self,
        operator_id: str,
        password: str,
        permissions: Iterable[Permission],
    ) -> str:
        """Create the dedicated operator, recovering safely from an insert race."""
        try:
            with transaction.atomic():
                operator = User(
                    clerk_user_id=operator_id,
                    is_staff=True,
                    is_superuser=False,
                )
                operator.set_password(password)
                operator.save()
                self._set_operator_group(operator, permissions)
        except IntegrityError:
            operator = (
                User.objects.select_for_update()
                .filter(clerk_user_id=operator_id)
                .first()
            )
            if operator is None:
                raise
            return self._reconcile_operator(password, operator, permissions)
        return "Staging operator created."

    def _reconcile_operator(
        self,
        password: str,
        operator: User,
        permissions: Iterable[Permission],
    ) -> str:
        """Rotate an existing password only for the exact managed operator."""
        permission_ids = {permission.pk for permission in permissions}
        if not self._is_exact_managed_operator(operator, permission_ids):
            raise CommandError("Existing account cannot be used as an operator.")

        operator.set_password(password)
        operator.save(update_fields={"password"})
        return "Staging operator reconciled."

    @staticmethod
    def _required_permissions() -> tuple[Permission, ...]:
        """Resolve the frozen permission set before any provisioning mutation."""
        permissions = tuple(Permission.objects.select_related("content_type"))
        matching_permissions = tuple(
            permission
            for permission in permissions
            if Command._permission_name(permission) in EXPECTED_PERMISSION_NAMES
        )
        if {
            Command._permission_name(permission) for permission in matching_permissions
        } != EXPECTED_PERMISSION_NAMES:
            raise CommandError("Required operator permissions are unavailable.")
        return matching_permissions

    @staticmethod
    def _permission_name(permission: Permission) -> str:
        """Return Django's stable app-label permission name."""
        return f"{permission.content_type.app_label}.{permission.codename}"  # pyright: ignore[reportUnknownMemberType]

    def _set_operator_group(
        self, operator: User, permissions: Iterable[Permission]
    ) -> None:
        """Attach the created operator to its sole exact-permission group."""
        group, _ = Group.objects.get_or_create(name=OPERATOR_GROUP_NAME)
        group.permissions.set(permissions)  # pyright: ignore[reportUnknownMemberType]
        operator.groups.set((group,))  # pyright: ignore[reportUnknownMemberType]

    def _is_exact_managed_operator(
        self, operator: User, permission_ids: set[int]
    ) -> bool:
        """Return whether an existing account is safe to reconcile in place."""
        if not operator.is_staff or cast(
            bool,
            operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        ):
            return False
        if operator.user_permissions.exists():  # pyright: ignore[reportUnknownMemberType]
            return False
        groups = tuple(operator.groups.all())  # pyright: ignore[reportUnknownMemberType]
        if (
            len(groups) != 1
            or cast(
                str,
                groups[0].name,  # pyright: ignore[reportUnknownMemberType]
            )
            != OPERATOR_GROUP_NAME
        ):
            return False
        return (
            set(
                groups[0].permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
            )
            == permission_ids
        )

    @staticmethod
    def _validate_password(password: str, user: User) -> None:
        """Validate a password without disclosing validator or input details."""
        try:
            validate_password(password, user)
        except ValidationError:
            raise CommandError(
                "Password does not meet operator requirements."
            ) from None
