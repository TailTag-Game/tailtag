"""Profile-state acquisition and persistence seams."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import psycopg
from django.db import IntegrityError

from accounts.models import User
from profiles.models import PlayerProfile
from profiles.normalization import ProfileValueError

HANDLE_UNIQUE_CONSTRAINT: Final[str] = "profiles_player_profile_handle_unique"

__all__ = [
    "DuplicateHandleError",
    "ProfileDisabledError",
    "ProfileIncompleteError",
    "ProfileValueError",
    "get_or_create_profile",
    "patch_text_profile",
    "put_text_profile",
]


class DuplicateHandleError(Exception):
    """The requested normalized handle is already owned."""


class ProfileDisabledError(Exception):
    """The profile is disabled for product mutations."""


class ProfileIncompleteError(Exception):
    """The requested operation requires completed onboarding."""


def get_or_create_profile(user: User) -> PlayerProfile:
    """Idempotently materialize profile state for a profile-surface caller."""
    profile, _ = PlayerProfile.objects.get_or_create(user=user)
    return profile


def put_text_profile(user: User, *, handle: str, display_name: str) -> PlayerProfile:
    """Temporary Task 2 persistence seam; Task 3 owns lifecycle transitions."""
    profile = get_or_create_profile(user)
    profile.handle = handle
    profile.display_name = display_name
    try:
        profile.save(update_fields=("handle", "display_name"))
    except IntegrityError as error:
        if _is_handle_unique_violation(error):
            raise DuplicateHandleError() from None
        raise
    return profile


def patch_text_profile(
    user: User, *, handle: str | None = None, display_name: str | None = None
) -> PlayerProfile:
    """Temporary Task 2 persistence seam; Task 3 owns lifecycle transitions."""
    profile = get_or_create_profile(user)
    if handle is not None:
        profile.handle = handle
    if display_name is not None:
        profile.display_name = display_name
    try:
        profile.save(update_fields=("handle", "display_name"))
    except IntegrityError as error:
        if _is_handle_unique_violation(error):
            raise DuplicateHandleError() from None
        raise
    return profile


def _is_handle_unique_violation(error: IntegrityError) -> bool:
    """Recognize only the exact structured PostgreSQL handle conflict."""
    driver_error = _psycopg_error_in_chain(error)
    return (
        driver_error is not None
        and driver_error.diag.sqlstate == "23505"
        and driver_error.diag.constraint_name == HANDLE_UNIQUE_CONSTRAINT
    )


def _psycopg_error_in_chain(error: BaseException) -> psycopg.Error | None:
    for cause in _cause_chain(error):
        if isinstance(cause, psycopg.Error):
            return cause
    return None


def _cause_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield explicit exception causes without inspecting their messages."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__
