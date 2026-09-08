"""Bootstrap the local Django operator for Railway Development only."""

from __future__ import annotations

import getpass
import os
import sys
from typing import cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User

REQUIRED_ENVIRONMENT = "development"
REQUIRED_SERVICE = "api"
CONFIRMATION_PHRASE = "bootstrap Railway Development operator"

__all__ = ["Command"]


class Command(BaseCommand):
    """Create or reconcile the guarded Railway Development operator."""

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
                User.objects.create_superuser(operator_id, password=password)
                outcome = "Development operator created."
            else:
                if not operator.is_staff or not cast(
                    bool,
                    operator.is_superuser,  # pyright: ignore[reportUnknownMemberType]
                ):
                    raise CommandError(
                        "Existing account cannot be used as an operator."
                    )

                self._validate_password(password, operator)
                operator.set_password(password)
                operator.save(update_fields={"password"})
                outcome = "Development operator reconciled."

        self.stdout.write(outcome)

    @staticmethod
    def _validate_password(password: str, user: User) -> None:
        """Validate a password without disclosing validator or input details."""
        try:
            validate_password(password, user)
        except ValidationError:
            raise CommandError(
                "Password does not meet operator requirements."
            ) from None
