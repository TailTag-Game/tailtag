"""Resolve verified Clerk identities to TailTag application users."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import psycopg
from django.db import IntegrityError, OperationalError, transaction
from psycopg.pq import ConnStatus

from accounts.models import User

EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT: Final[str] = "accounts_user_clerk_user_id_key"


class ApplicationUserResolutionUnavailable(Exception):
    """A transient application-user persistence dependency failure."""


def resolve_application_user(clerk_user_id: str) -> User:
    """Return the application user linked to an exact Clerk subject."""
    try:
        return _resolve_application_user(clerk_user_id)
    except OperationalError as error:
        if _is_transient_availability_error(error):
            raise ApplicationUserResolutionUnavailable() from None
        raise


def _resolve_application_user(clerk_user_id: str) -> User:
    try:
        return User.objects.get(clerk_user_id=clerk_user_id)
    except User.DoesNotExist:
        pass

    try:
        with transaction.atomic():
            return User.objects.create_user(clerk_user_id=clerk_user_id)
    except IntegrityError as error:
        if not _is_expected_clerk_identity_conflict(error):
            raise

        try:
            return User.objects.get(clerk_user_id=clerk_user_id)
        except User.DoesNotExist:
            raise error


def _is_expected_clerk_identity_conflict(error: IntegrityError) -> bool:
    driver_error = _psycopg_error_in_chain(error)
    return (
        driver_error is not None
        and driver_error.sqlstate == "23505"
        and driver_error.diag.constraint_name
        == EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT
    )


def _is_transient_availability_error(error: OperationalError) -> bool:
    driver_error = _psycopg_error_in_chain(error)
    if driver_error is None:
        return False

    if sqlstate := driver_error.sqlstate:
        return sqlstate.startswith("08") or sqlstate in {"57P01", "57P02", "57P03"}

    return driver_error.pgconn is None or driver_error.pgconn.status is ConnStatus.BAD


def _psycopg_error_in_chain(error: BaseException) -> psycopg.Error | None:
    for cause in _cause_chain(error):
        if isinstance(cause, psycopg.Error):
            return cause
    return None


def _cause_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield the explicit exception causes without relying on error text."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__
