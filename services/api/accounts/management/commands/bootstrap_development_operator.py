"""Bootstrap the local Django operator for Railway Development only."""

from __future__ import annotations

import getpass
import os
import sys
from typing import NoReturn, cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import DatabaseError, IntegrityError, transaction

from accounts.models import User

REQUIRED_ENVIRONMENT = "development"
REQUIRED_SERVICE = "api"
CONFIRMATION_PHRASE = "bootstrap Railway Development operator"

__all__ = ["Command"]


class Command(BaseCommand):
    """Create or reconcile the guarded Railway Development operator."""

    def create_parser(
        self, prog_name: str, subcommand: str, **kwargs: object
    ) -> CommandParser:
        """Use Django's parser while keeping invalid CLI inputs private."""
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.error = self._parser_error
        return parser

    def handle(self, *args: object, **options: object) -> None:
        """Create or rotate a full operator's password after guarded confirmation."""
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

        try:
            with transaction.atomic():
                operator = (
                    User.objects.select_for_update()
                    .filter(clerk_user_id=operator_id)
                    .first()
                )
                if operator is None:
                    candidate = User(
                        clerk_user_id=operator_id,
                        is_staff=True,
                        is_superuser=True,
                    )
                    self._validate_password(password, candidate)
                    try:
                        with transaction.atomic():
                            User.objects.create_superuser(
                                operator_id, password=password
                            )
                    except IntegrityError:
                        operator = (
                            User.objects.select_for_update()
                            .filter(clerk_user_id=operator_id)
                            .first()
                        )
                        if operator is None:
                            raise
                        outcome = self._reconcile_operator(password, operator)
                    else:
                        outcome = "Development operator created."
                else:
                    outcome = self._reconcile_operator(password, operator)
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

    def _reconcile_operator(self, password: str, operator: User) -> str:
        """Validate and rotate the password for an existing full operator."""
        if not operator.is_staff or not cast(
            bool,
            operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        ):
            raise CommandError("Existing account cannot be used as an operator.")

        self._validate_password(password, operator)
        operator.set_password(password)
        operator.save(update_fields={"password"})
        return "Development operator reconciled."

    @staticmethod
    def _validate_password(password: str, user: User) -> None:
        """Validate a password without disclosing validator or input details."""
        try:
            validate_password(password, user)
        except ValidationError:
            raise CommandError(
                "Password does not meet operator requirements."
            ) from None
