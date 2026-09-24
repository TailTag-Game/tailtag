"""One-shot, read-only local credential diagnosis for the #243 managed operator."""

from __future__ import annotations

import datetime as dt
import getpass
import logging
import sys
import warnings
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from scripts import api_staging_operator_inspect as _inspector

if TYPE_CHECKING:
    from accounts.models import User

_CLASSIFICATIONS = frozenset(
    {
        "CREDENTIAL_ACCEPTED",
        "CREDENTIAL_REJECTED",
        "IDENTITY_MISMATCH",
        "IDENTITY_AMBIGUOUS",
        "PASSWORD_UNUSABLE",
        "TARGET_OR_ROLE_FAILURE",
        "AUTH_PROTOCOL_FAILURE",
        "EXECUTION_FAILURE",
    }
)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _managed_member() -> tuple[str | None, User | None]:
    """Check the exact role while preserving unusable-hash classification."""
    from django.contrib.auth.models import Group

    from accounts.management.commands.bootstrap_staging_operator import (
        EXPECTED_PERMISSION_NAMES,
        OPERATOR_GROUP_NAME,
    )
    from accounts.models import User

    try:
        group = Group.objects.get(name=OPERATOR_GROUP_NAME)
    except Group.DoesNotExist:
        return "TARGET_OR_ROLE_FAILURE", None
    except Group.MultipleObjectsReturned:
        return "IDENTITY_AMBIGUOUS", None
    members = list(User.objects.filter(groups=group))
    if len(members) != 1:
        return ("IDENTITY_AMBIGUOUS" if members else "TARGET_OR_ROLE_FAILURE"), None
    operator = members[0]
    if (
        not operator.is_staff
        or cast(bool, operator.is_superuser)  # pyright: ignore[reportUnknownMemberType]
        or list(operator.groups.values_list("pk", flat=True)) != [group.pk]  # pyright: ignore[reportUnknownMemberType]
        or operator.user_permissions.exists()  # pyright: ignore[reportUnknownMemberType]
        or _inspector._permission_names(group.permissions) != EXPECTED_PERMISSION_NAMES  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType, reportUnknownArgumentType]
    ):
        return "TARGET_OR_ROLE_FAILURE", operator
    return None, operator


def _preconditions() -> tuple[str | None, User | None]:
    if _inspector._validate_fixture() is not None:  # pyright: ignore[reportPrivateUsage]
        return "TARGET_OR_ROLE_FAILURE", None
    status, operator = _managed_member()
    if status is not None:
        return status, operator
    if _inspector._validate_limited_operator() is not None:  # pyright: ignore[reportPrivateUsage]
        return "TARGET_OR_ROLE_FAILURE", None
    return None, operator


def _classify(
    identifier: str, password: str, status: str | None, operator: User | None
) -> str:
    from django.contrib.auth.hashers import check_password

    from accounts.models import User

    if status is not None:
        return status
    if operator is None:
        return "EXECUTION_FAILURE"
    selected = list(User.objects.filter(clerk_user_id=identifier))
    if len(selected) > 1:
        return "IDENTITY_AMBIGUOUS"
    if len(selected) != 1 or selected[0].pk != operator.pk:
        return "IDENTITY_MISMATCH"
    if not operator.has_usable_password():
        return "PASSWORD_UNUSABLE"
    try:
        matches = check_password(password, cast(str, operator.password))  # pyright: ignore[reportUnknownMemberType]
    except Exception:  # noqa: BLE001
        return "AUTH_PROTOCOL_FAILURE"
    if type(matches) is not bool:
        return "AUTH_PROTOCOL_FAILURE"
    return "CREDENTIAL_ACCEPTED" if matches else "CREDENTIAL_REJECTED"


def diagnose_local(identifier: str, password: str) -> str:
    """Classify one exact local credential without writing or invoking a setter."""
    try:
        status, operator = _preconditions()
        return _classify(identifier, password, status, operator)
    except Exception:  # noqa: BLE001
        return "EXECUTION_FAILURE"


def _result(classification: str, identity: object, started: str) -> dict[str, object]:
    if classification not in _CLASSIFICATIONS:
        classification = "EXECUTION_FAILURE"
    return {
        "classification": classification,
        "identity": identity,
        "window_utc": [started, _now()],
    }


def run(expected_identity: object) -> dict[str, object]:
    """Verify target and roles before acquiring two hidden terminal values."""
    from django.conf import settings
    from django.db import connection, transaction

    started = _now()
    identity: object = None
    try:
        if not isinstance(expected_identity, Mapping):
            return _result("TARGET_OR_ROLE_FAILURE", None, started)
        expected = cast(Mapping[str, object], expected_identity)
        source_sha = expected.get("source_sha")
        deployment_id = expected.get("deployment_id")
        if (
            set(expected) != {"source_sha", "deployment_id", "environment"}
            or expected.get("environment") != "staging"
            or not isinstance(source_sha, str)
            or not isinstance(deployment_id, str)
            or not _inspector._valid_expected_identity(source_sha, deployment_id)  # pyright: ignore[reportPrivateUsage]
            or not _inspector._target_identity_matches(source_sha, deployment_id)  # pyright: ignore[reportPrivateUsage]
        ):
            return _result("TARGET_OR_ROLE_FAILURE", None, started)
        identity = cast(dict[str, str], dict(expected))
        if (
            settings.DEBUG
            or connection.force_debug_cursor
            or connection.execute_wrappers
            or logging.getLogger("django.db.backends").isEnabledFor(logging.DEBUG)
        ):
            return _result("AUTH_PROTOCOL_FAILURE", identity, started)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            status, operator = _preconditions()
            if status is not None:
                return _result(status, identity, started)
            if operator is None:
                return _result("EXECUTION_FAILURE", identity, started)
            if not operator.has_usable_password():
                return _result("PASSWORD_UNUSABLE", identity, started)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return _result("AUTH_PROTOCOL_FAILURE", identity, started)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                identifier = getpass.getpass("Operator identifier: ")
                password = getpass.getpass("Password: ")
        except (EOFError, OSError, KeyboardInterrupt, getpass.GetPassWarning):
            return _result("AUTH_PROTOCOL_FAILURE", identity, started)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            return _result(diagnose_local(identifier, password), identity, started)
    except Exception:  # noqa: BLE001
        return _result("EXECUTION_FAILURE", identity, started)
