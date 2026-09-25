"""Revoke access for the exact synthetic #243 emergency actor, preserving audit."""

from __future__ import annotations

import logging
import os
import sys
from typing import NoReturn

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, connection, transaction

from accounts.management.commands.bootstrap_staging_emergency_operator import (
    _IDENTIFIER,  # pyright: ignore[reportPrivateUsage]
    _has_forbidden_attachment,  # pyright: ignore[reportPrivateUsage]
    _require_database_binding,  # pyright: ignore[reportPrivateUsage]
)
from accounts.models import User
from config.replacement_target_binding import (
    TargetBindingError,
    validate_runtime_target,
)
from rehearsal.models import StagingResetIdentity

CONFIRMATION_PHRASE = "decommission Railway Staging emergency operator"


class Command(BaseCommand):
    """Atomically remove access while retaining the audit-linked User row."""

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

        try:
            with transaction.atomic():
                ContentType.objects.select_for_update().get(
                    app_label="accounts", model="user"
                )
                _require_database_binding()
                candidates = list(
                    User.objects.select_for_update().filter(is_superuser=True)[:2]
                )
                if len(candidates) != 1:
                    raise CommandError("Emergency operator state is unavailable.")
                actor = candidates[0]
                if (
                    not actor.is_staff
                    or _IDENTIFIER.fullmatch(actor.clerk_user_id) is None
                    or not actor.has_usable_password()
                    or actor.groups.exists()  # pyright: ignore[reportUnknownMemberType]
                    or actor.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    or _has_forbidden_attachment(actor)
                ):
                    raise CommandError("Emergency operator state is unavailable.")
                actor.is_staff = False
                actor.is_superuser = False
                actor.set_unusable_password()
                actor.save(update_fields={"is_staff", "is_superuser", "password"})
        except (
            DatabaseError,
            ContentType.DoesNotExist,
            StagingResetIdentity.DoesNotExist,
            StagingResetIdentity.MultipleObjectsReturned,
        ):
            raise CommandError("Emergency operator decommission failed.") from None

        self.stdout.write("Staging emergency operator decommissioned.")

    def _parser_error(self, message: str) -> NoReturn:
        message = "Invalid command arguments. Use the documented interactive command."
        if getattr(self, "_called_from_command_line", False):
            self.stderr.write(message)
            raise SystemExit(2)
        raise CommandError(message)
