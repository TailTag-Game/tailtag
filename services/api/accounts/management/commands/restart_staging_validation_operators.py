"""Atomically replace the three synthetic #243 Staging operators."""

from __future__ import annotations

import getpass
import logging
import os
import secrets
import sys
import warnings
from typing import NoReturn, cast

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.management.base import CommandParser
from django.db import connection, transaction

from accounts.management.commands.bootstrap_staging_emergency_operator import (
    _has_forbidden_attachment,  # pyright: ignore[reportPrivateUsage]
    _require_database_binding,  # pyright: ignore[reportPrivateUsage]
    inspect_emergency_state,
)
from accounts.management.commands.bootstrap_staging_operator import (
    EXPECTED_PERMISSION_NAMES,
    OPERATOR_GROUP_NAME,
)
from accounts.management.commands.staging_validation_operator import (
    GROUP_NAME as LIMITED_GROUP_NAME,
)
from accounts.management.commands.staging_validation_operator import (
    PERMISSION_NAMES as LIMITED_PERMISSION_NAMES,
)
from accounts.models import User
from config.build_identity import get_identity
from config.replacement_target_binding import (
    TargetBindingError,
    validate_runtime_target,
)
from operator_audit.models import OperatorAuditEvent
from rehearsal.models import StagingResetIdentity
from rehearsal.reset import validate_baseline

CONFIRMATION_PHRASE = "restart Railway Staging validation operators"
_ROLES = ("managed", "limited", "emergency")
_MAX_AUDIT_ROWS = 10_000
# A Permission's display name omits its content-type model. The frozen role
# contract binds each authority to exactly one canonical content type.
_PERMISSION_MODELS = {
    "catches.delete_catch": "catch",
    "catches.view_catch": "catch",
    "conventions.revoke_catch_credential": "fursuitcatchcredential",
    "conventions.view_fursuitcatchcredential": "fursuitcatchcredential",
    "conventions.terminate_catch_session": "fursuitcatchsession",
    "conventions.view_fursuitcatchsession": "fursuitcatchsession",
    "conventions.deactivate_fursuit_activation": "fursuitactivation",
    "conventions.view_fursuitactivation": "fursuitactivation",
    "conventions.remove_convention_enrollment": "conventionenrollment",
    "conventions.view_conventionenrollment": "conventionenrollment",
    "conventions.set_convention_playability": "convention",
    "conventions.view_convention": "convention",
    "profiles.set_profile_enabled": "playerprofile",
    "profiles.view_playerprofile": "playerprofile",
    "fursuits.set_fursuit_enabled": "fursuit",
    "fursuits.view_fursuit": "fursuit",
}
_AUDIT_FIELDS = (
    "pk",
    "actor_id",
    "action",
    "actor_class",
    "affected_record_type",
    "affected_record_id",
    "outcome",
    "occurred_at",
)
_REGISTRY_FIELDS = (
    "pk",
    "owner_id",
    "catcher_id",
    "convention_id",
    "first_fursuit_id",
    "second_fursuit_id",
    "environment_id",
    "cluster_identifier",
    "database_name",
    "media_key",
)


def _hidden_input(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise CommandError("Hidden terminal input is unavailable.") from None


def _canonical_permission_ids(expected: set[str]) -> set[int]:
    if not expected or not expected <= _PERMISSION_MODELS.keys():
        raise CommandError("Operator permission state is unavailable.")
    canonical = {(*name.split(".", 1), _PERMISSION_MODELS[name]) for name in expected}
    matches = [
        permission.pk
        for permission in Permission.objects.select_related("content_type").filter(
            content_type__app_label__in={app for app, _, _ in canonical}
        )
        if (
            permission.content_type.app_label,  # pyright: ignore[reportUnknownMemberType]
            cast(str, permission.codename),  # pyright: ignore[reportUnknownMemberType]
            permission.content_type.model,  # pyright: ignore[reportUnknownMemberType]
        )
        in canonical
    ]
    if len(matches) != len(canonical):
        raise CommandError("Operator permission state is unavailable.")
    return set(matches)


def _exact_actor(group: Group, expected: set[str], *, lock: bool = False) -> User:
    candidates = User.objects.filter(groups=group)
    if lock:
        candidates = candidates.select_for_update()
    members = list(candidates[:2])
    if (
        len(members) != 1
        or set(group.permissions.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
        != _canonical_permission_ids(expected)
    ):
        raise CommandError("Operator state is unavailable.")
    actor = members[0]
    if (
        not actor.is_staff
        or cast(bool, actor.is_superuser)  # pyright: ignore[reportUnknownMemberType]
        or not actor.has_usable_password()
        or set(actor.groups.values_list("pk", flat=True)) != {group.pk}  # pyright: ignore[reportUnknownMemberType]
        or actor.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or _has_forbidden_attachment(actor)
    ):
        raise CommandError("Operator state is unavailable.")
    return actor


def _roles(*, lock: bool = False) -> tuple[dict[str, User], dict[str, Group]]:
    groups = Group.objects.select_for_update() if lock else Group.objects
    managed_group = groups.get(name=OPERATOR_GROUP_NAME)
    limited_group = groups.get(name=LIMITED_GROUP_NAME)
    managed = _exact_actor(managed_group, set(EXPECTED_PERMISSION_NAMES), lock=lock)
    limited = _exact_actor(limited_group, set(LIMITED_PERMISSION_NAMES), lock=lock)
    if inspect_emergency_state() != "READY":
        raise CommandError("Operator state is unavailable.")
    if User.objects.filter(clerk_user_id__startswith="staging_emergency_").count() != 1:
        raise CommandError("Operator state is unavailable.")
    emergency_query = User.objects.select_for_update() if lock else User.objects
    emergency = emergency_query.get(is_superuser=True)
    if (
        not emergency.is_staff
        or not emergency.has_usable_password()
        or emergency.groups.exists()  # pyright: ignore[reportUnknownMemberType]
        or emergency.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or _has_forbidden_attachment(emergency)
    ):
        raise CommandError("Operator state is unavailable.")
    actors = {"managed": managed, "limited": limited, "emergency": emergency}
    if len({actor.pk for actor in actors.values()}) != 3:
        raise CommandError("Operator state is unavailable.")
    if set(User.objects.filter(is_staff=True).values_list("pk", flat=True)) != {
        actor.pk for actor in actors.values()
    }:
        raise CommandError("Operator state is unavailable.")
    return actors, {"managed": managed_group, "limited": limited_group}


def _snapshot() -> tuple[object, ...]:
    registry = StagingResetIdentity.objects.get(pk=1)
    validate_baseline(registry)
    audit = tuple(
        OperatorAuditEvent.objects.order_by("pk").values_list(*_AUDIT_FIELDS)[
            : _MAX_AUDIT_ROWS + 1
        ]
    )
    if len(audit) > _MAX_AUDIT_ROWS:
        raise CommandError("Operator audit snapshot is unavailable.")
    baseline = tuple(StagingResetIdentity.objects.values_list(*_REGISTRY_FIELDS))
    preserved = tuple(
        (
            user.pk,
            user.clerk_user_id,
            user.is_staff,
            cast(bool, user.is_superuser),  # pyright: ignore[reportUnknownMemberType]
            cast(str, user.password),  # pyright: ignore[reportUnknownMemberType]
            tuple(user.groups.order_by("pk").values_list("pk", flat=True)),  # pyright: ignore[reportUnknownMemberType]
            tuple(
                user.user_permissions.order_by("pk").values_list("pk", flat=True)  # pyright: ignore[reportUnknownMemberType]
            ),
        )
        for user in User.objects.filter(
            pk__in=(registry.owner_id, registry.catcher_id)
        ).order_by("pk")
    )
    if len(preserved) != 2:
        raise CommandError("Preserved Staging identities are unavailable.")
    return audit, baseline, preserved


def _target(expected: object) -> None:
    if (
        os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
        or os.environ.get("RAILWAY_SERVICE_NAME") != "api"
    ):
        raise CommandError("Staging target is unavailable.")
    try:
        validate_runtime_target(os.environ)
        if (
            not isinstance(expected, dict)
            or set(cast(dict[str, object], expected))
            != {"source_sha", "deployment_id", "environment"}
            or get_identity() != expected
            or expected["environment"] != "staging"
        ):
            raise ValueError
    except (TargetBindingError, ValueError):
        raise CommandError("Staging target is unavailable.") from None


class Command(BaseCommand):
    """One guarded, nonrepeatable transfer of the three current roles."""

    def create_parser(
        self, prog_name: str, subcommand: str, **kwargs: object
    ) -> CommandParser:
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.error = self._parser_error
        return parser

    def _parser_error(self, message: str) -> NoReturn:
        del message
        text = "Invalid command arguments. Use the documented interactive command."
        if getattr(self, "_called_from_command_line", False):
            self.stderr.write(text)
            raise SystemExit(2)
        raise CommandError(text)

    def handle(self, *args: object, **options: object) -> None:
        _target(options.get("expected_identity"))
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
            _require_database_binding()
            before = _snapshot()
            actors, _ = _roles()
        except Exception as error:
            if isinstance(error, CommandError):
                raise
            raise CommandError("Operator restart precondition failed.") from None
        pinned = {
            role: (
                actor.pk,
                actor.clerk_user_id,
                cast(str, actor.password),  # pyright: ignore[reportUnknownMemberType]
            )
            for role, actor in actors.items()
        }
        if input("Confirmation: ") != CONFIRMATION_PHRASE:
            raise CommandError("Confirmation failed.")
        names = {
            role: f"staging_{'validation' if role == 'limited' else role}_{secrets.token_hex(8)}"
            for role in _ROLES
        }
        passwords: dict[str, str] = {}
        for role in _ROLES:
            password = _hidden_input(f"{role.title()} password: ")
            if password != _hidden_input(f"Confirm {role} password: "):
                raise CommandError("Passwords do not match.")
            candidate = User(
                clerk_user_id=names[role],
                is_staff=True,
                is_superuser=role == "emergency",
            )
            try:
                validate_password(password, candidate)
            except ValidationError:
                raise CommandError(
                    "Password does not meet operator requirements."
                ) from None
            passwords[role] = password
        if len(set(passwords.values())) != len(_ROLES):
            raise CommandError("Operator passwords must be distinct.")

        try:
            with transaction.atomic():
                ContentType.objects.select_for_update().get(
                    app_label="accounts", model="user"
                )
                _target(options.get("expected_identity"))
                _require_database_binding()
                if _snapshot() != before:
                    raise CommandError("Operator state changed before restart.")
                current, groups = _roles(lock=True)
                if {
                    role: (
                        actor.pk,
                        actor.clerk_user_id,
                        cast(str, actor.password),  # pyright: ignore[reportUnknownMemberType]
                    )
                    for role, actor in current.items()
                } != pinned:
                    raise CommandError("Operator state changed before restart.")
                if User.objects.filter(
                    clerk_user_id__in=tuple(names.values())
                ).exists():
                    raise CommandError("Generated operator identity is unavailable.")
                for actor in current.values():
                    actor.is_staff = False
                    actor.is_superuser = False
                    actor.set_unusable_password()
                    actor.save(update_fields={"is_staff", "is_superuser", "password"})
                    actor.groups.clear()  # pyright: ignore[reportUnknownMemberType]
                    actor.user_permissions.clear()  # pyright: ignore[reportUnknownMemberType]
                new: dict[str, User] = {}
                for role in _ROLES:
                    actor = User(
                        clerk_user_id=names[role],
                        is_staff=True,
                        is_superuser=role == "emergency",
                    )
                    actor.set_password(passwords[role])
                    actor.save(force_insert=True)
                    if role in groups:
                        actor.groups.add(groups[role])  # pyright: ignore[reportUnknownMemberType]
                    new[role] = actor
                if _snapshot() != before:
                    raise CommandError("Operator restart postcondition failed.")
        except CommandError:
            raise
        except Exception:  # noqa: BLE001
            raise CommandError("Operator restart failed.") from None

        # A new read-only transaction is required after commit; the marker is
        # withheld if any pinned predecessor, audit row, or baseline changed.
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                _target(options.get("expected_identity"))
                _require_database_binding()
                if _snapshot() != before:
                    raise ValueError
                for role, old_state in pinned.items():
                    old = User.objects.get(pk=old_state[0])
                    if (
                        old.clerk_user_id != old_state[1]
                        or old.is_staff
                        or cast(bool, old.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                        or old.has_usable_password()
                        or old.groups.exists()  # pyright: ignore[reportUnknownMemberType]
                        or old.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                    ):
                        raise ValueError
                for role, actor in new.items():
                    observed = User.objects.get(pk=actor.pk)
                    if (
                        observed.clerk_user_id != names[role]
                        or not observed.is_staff
                        or cast(bool, observed.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                        != (role == "emergency")
                        or not observed.has_usable_password()
                        or not check_password(
                            passwords[role],
                            cast(str, observed.password),  # pyright: ignore[reportUnknownMemberType]
                        )
                        or observed.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
                        or set(observed.groups.values_list("pk", flat=True))  # pyright: ignore[reportUnknownMemberType]
                        != ({groups[role].pk} if role in groups else set())
                    ):
                        raise ValueError
                for role, expected in (
                    ("managed", set(EXPECTED_PERMISSION_NAMES)),
                    ("limited", set(LIMITED_PERMISSION_NAMES)),
                ):
                    if _exact_actor(groups[role], expected).pk != new[role].pk:
                        raise ValueError
                if (
                    set(User.objects.filter(is_staff=True).values_list("pk", flat=True))
                    != {actor.pk for actor in new.values()}
                    or inspect_emergency_state() != "READY"
                    or _has_forbidden_attachment(new["emergency"])
                ):
                    raise ValueError
        except Exception:  # noqa: BLE001
            raise CommandError("Operator restart postcondition uncertain.") from None
        self.stdout.write("POSTCONDITION_PASS")
