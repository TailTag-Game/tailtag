"""Rotate only the exact managed Staging operator's local password for #243."""

from __future__ import annotations

import logging
import sys
from typing import cast

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import CommandError
from django.db import DatabaseError, connection, transaction

from .replace_staging_managed_operator import Command as _GuardedCommand
from .replace_staging_managed_operator import (
    _hidden_input,  # pyright: ignore[reportPrivateUsage]
)

CONFIRMATION_PHRASE = "rotate Railway Staging managed operator password"


class Command(_GuardedCommand):
    """Keep the current managed identity and rotate only its password."""

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
            group, operator = self._exact_predecessor()
            pinned_pk = operator.pk
            pinned_identifier = operator.clerk_user_id
            pinned_password = cast(str, operator.password)  # pyright: ignore[reportUnknownMemberType]
            pinned_group_pk = group.pk
            pinned_permissions = frozenset(
                group.permissions.values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
            )
            pinned_limited = self._limited_state()
            pinned_audit = self._audit_snapshot()
        except DatabaseError:
            raise CommandError("Managed password rotation failed.") from None

        if input("Confirmation: ") != CONFIRMATION_PHRASE:
            raise CommandError("Confirmation failed.")
        self.stdout.write("PREPARED")
        password = _hidden_input("Password: ")
        if password != _hidden_input("Confirm password: "):
            raise CommandError("Passwords do not match.")
        try:
            validate_password(password, operator)
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
                group, operator = self._exact_predecessor(lock=True)
                if (
                    group.pk != pinned_group_pk
                    or operator.pk != pinned_pk
                    or operator.clerk_user_id != pinned_identifier
                    or cast(str, operator.password) != pinned_password  # pyright: ignore[reportUnknownMemberType]
                    or frozenset(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                    != pinned_permissions
                    or self._limited_state() != pinned_limited
                    or self._audit_snapshot() != pinned_audit
                ):
                    raise CommandError("Staging prerequisite state changed.")
                operator.set_password(password)
                operator.save(update_fields={"password"})
        except DatabaseError:
            raise CommandError("Managed password rotation failed.") from None

        self._verify_password_postcommit(
            expected,
            pinned_pk,
            pinned_identifier,
            pinned_group_pk,
            pinned_permissions,
            pinned_limited,
            pinned_audit,
            password,
        )
        self.stdout.write("POSTCONDITION_PASS")

    def _verify_password_postcommit(
        self,
        expected: object,
        operator_pk: int,
        identifier: str,
        group_pk: int,
        permissions: frozenset[int],
        limited_state: tuple[object, ...],
        audit_state: tuple[tuple[object, ...], ...],
        password: str,
    ) -> None:
        """Prove the committed hash and unchanged authority in a new read-only transaction."""
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                if not self._target_matches(expected):
                    raise CommandError("Managed password postcondition failed.")
                group, operator = self._exact_predecessor()
                if (
                    operator.pk != operator_pk
                    or operator.clerk_user_id != identifier
                    or group.pk != group_pk
                    or frozenset(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                    != permissions
                    or not check_password(
                        password,
                        cast(str, operator.password),  # pyright: ignore[reportUnknownMemberType]
                    )
                    or self._limited_state() != limited_state
                    or self._audit_snapshot() != audit_state
                ):
                    raise CommandError("Managed password postcondition failed.")
        except DatabaseError:
            raise CommandError("Managed password postcondition failed.") from None
