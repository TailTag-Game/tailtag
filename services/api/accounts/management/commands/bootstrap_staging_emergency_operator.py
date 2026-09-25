"""Create one dedicated emergency operator on the pinned Railway Staging API."""

from __future__ import annotations

import getpass
import logging
import os
import re
import sys
import warnings
from typing import NoReturn, cast

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, connection, transaction

from accounts.models import User
from catches.models import Catch
from config.replacement_target_binding import (
    TargetBindingError,
    validate_runtime_target,
)
from conventions.models import ConventionEnrollment
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from rehearsal.models import StagingResetIdentity

CONFIRMATION_PHRASE = "bootstrap Railway Staging emergency operator"
_IDENTIFIER = re.compile(r"staging_emergency_[a-z0-9_]{1,48}\Z", re.ASCII)


def _has_forbidden_attachment(user: User) -> bool:
    return (
        PlayerProfile.objects.filter(user=user).exists()
        or Fursuit.objects.filter(owner=user).exists()
        or ConventionEnrollment.objects.filter(user=user).exists()
        or Catch.objects.filter(catcher_user=user).exists()
        or StagingResetIdentity.objects.filter(owner=user).exists()
        or StagingResetIdentity.objects.filter(catcher=user).exists()
    )


def inspect_emergency_state() -> str:
    """Classify the synthetic emergency singleton without disclosing identity."""
    try:
        superusers = list(User.objects.filter(is_superuser=True)[:2])
        dedicated = list(
            User.objects.filter(clerk_user_id__startswith="staging_emergency_")[:2]
        )
        if not superusers and not dedicated:
            return "ABSENT"
        if len(superusers) > 1 or len(dedicated) != 1:
            return "MISMATCH"
        user = dedicated[0]
        if _IDENTIFIER.fullmatch(user.clerk_user_id) is None:
            return "MISMATCH"
        if not superusers:
            if (
                user.is_staff
                or cast(bool, user.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                or user.has_usable_password()
                or user.groups.exists()  # pyright: ignore[reportUnknownMemberType]
                or user.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                or _has_forbidden_attachment(user)
            ):
                return "MISMATCH"
            return "DECOMMISSIONED"
        if (
            superusers[0].pk != user.pk
            or not user.is_staff
            or not user.has_usable_password()
            or user.groups.exists()  # pyright: ignore[reportUnknownMemberType]
            or user.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
            or _has_forbidden_attachment(user)
        ):
            return "MISMATCH"
        return "READY"
    except Exception:  # noqa: BLE001
        return "INDETERMINATE"


def _hidden_input(prompt: str) -> str:
    """Refuse getpass's echoed-input fallback and sanitize terminal failures."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise CommandError("Hidden terminal input is unavailable.") from None


def _require_database_binding() -> None:
    """Bind the same transactional connection to the provisioned #204 sentinel."""
    registry = StagingResetIdentity.objects.get(pk=1)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        database_facts = cursor.fetchone()
    if (
        database_facts is None
        or str(database_facts[0]) != registry.database_name
        or str(database_facts[0]) != str(settings.DATABASES["default"].get("NAME", ""))
        or str(database_facts[1]) != registry.cluster_identifier
    ):
        raise CommandError("Staging database binding is unavailable.")


class Command(BaseCommand):
    """Provision a fresh emergency-only Django identity without adopting users."""

    def create_parser(
        self, prog_name: str, subcommand: str, **kwargs: object
    ) -> CommandParser:
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.error = self._parser_error
        return parser

    def handle(self, *args: object, **options: object) -> None:
        if (
            os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
            or os.environ.get("RAILWAY_SERVICE_NAME") != "api"
        ):
            raise CommandError("This command is unavailable for the current target.")
        try:
            validate_runtime_target(os.environ)
        except TargetBindingError:
            raise CommandError(
                "This command is unavailable for the current target."
            ) from None
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError("This command requires an interactive terminal.")
        if (
            settings.DEBUG
            or connection.force_debug_cursor
            or connection.execute_wrappers
            or logging.getLogger("django.db.backends").isEnabledFor(logging.DEBUG)
        ):
            raise CommandError("Query debugging must be disabled.")
        if input("Confirmation: ") != CONFIRMATION_PHRASE:
            raise CommandError("Confirmation failed.")

        identifier = _hidden_input("Operator identifier: ")
        if not _IDENTIFIER.fullmatch(identifier):
            raise CommandError("Operator identifier is invalid.")
        password = _hidden_input("Password: ")
        if password != _hidden_input("Confirm password: "):
            raise CommandError("Passwords do not match.")

        candidate = User(
            clerk_user_id=identifier,
            is_staff=True,
            is_superuser=True,
        )
        try:
            validate_password(password, candidate)
        except ValidationError:
            raise CommandError(
                "Password does not meet operator requirements."
            ) from None

        try:
            with transaction.atomic():
                # Serialize first use even when no emergency User row exists yet.
                # This stable, pre-existing row is shared by every invocation.
                ContentType.objects.select_for_update().get(
                    app_label="accounts", model="user"
                )
                _require_database_binding()
                if (
                    User.objects.filter(is_superuser=True).exists()
                    or User.objects.filter(clerk_user_id=identifier).exists()
                ):
                    raise CommandError(
                        "Existing account cannot be used as an emergency operator."
                    )
                candidate.set_password(password)
                candidate.save(force_insert=True)
        except (
            DatabaseError,
            ContentType.DoesNotExist,
            StagingResetIdentity.DoesNotExist,
        ):
            raise CommandError("Emergency operator bootstrap failed.") from None

        self.stdout.write("Staging emergency operator created.")

    def _parser_error(self, message: str) -> NoReturn:
        """Avoid reflecting secret or identifier arguments in parser errors."""
        message = "Invalid command arguments. Use the documented interactive command."
        if getattr(self, "_called_from_command_line", False):
            self.stderr.write(message)
            raise SystemExit(2)
        raise CommandError(message)
