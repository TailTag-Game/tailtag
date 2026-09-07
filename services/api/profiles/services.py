"""Profile-state acquisition and persistence seams."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Final

import psycopg
from django.core.files import File
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.models import User
from media import service as media_service
from profiles.models import PlayerProfile
from profiles.normalization import (
    ProfileValueError,
    normalize_display_name,
    normalize_handle,
)

HANDLE_UNIQUE_CONSTRAINT: Final[str] = "profiles_player_profile_handle_unique"

__all__ = [
    "DuplicateHandleError",
    "ProfileDisabledError",
    "ProfileIncompleteError",
    "ProfileValueError",
    "get_or_create_profile",
    "patch_text_profile",
    "put_text_profile",
    "remove_profile_avatar",
    "replace_profile_avatar",
    "set_profile_enabled",
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


def set_profile_enabled(*, profile_id: int, is_enabled: bool) -> PlayerProfile:
    """Set operator-controlled eligibility and end live sessions on disable."""
    with transaction.atomic():
        profile = PlayerProfile.objects.select_for_update().get(pk=profile_id)
        if profile.is_enabled == is_enabled:
            return profile
        now = timezone.now()
        if not is_enabled:
            # The profile lock is the first member of the shared lifecycle order.
            from conventions.catch_credentials import revoke_for_profile_disable
            from conventions.catch_sessions import terminate_for_locked_activations

            activations = revoke_for_profile_disable(profile, now=now)
            terminate_for_locked_activations(activations, now=now)
        profile.is_enabled = is_enabled
        profile.save(update_fields=["is_enabled"])
        return profile


def put_text_profile(user: User, *, handle: str, display_name: str) -> PlayerProfile:
    """Create or fully replace the enabled user's normalized text profile."""
    normalized_handle = normalize_handle(handle)
    normalized_display_name = normalize_display_name(display_name)

    with transaction.atomic():
        profile = _locked_profile(user)
        _require_enabled(profile)
        _raise_if_handle_taken(user, normalized_handle)

        profile.handle = normalized_handle
        profile.display_name = normalized_display_name
        update_fields: list[str] = ["handle", "display_name"]
        if profile.onboarding_completed_at is None:
            profile.onboarding_completed_at = timezone.now()
            update_fields.append("onboarding_completed_at")
        _save_text_profile(profile, update_fields)
    return profile


def patch_text_profile(
    user: User, *, handle: str | None = None, display_name: str | None = None
) -> PlayerProfile:
    """Partially update a completed enabled user's normalized text profile."""
    if handle is None and display_name is None:
        raise ProfileValueError("handle", "required", "Provide a profile field.")

    with transaction.atomic():
        profile = _locked_profile(user)
        _require_enabled(profile)
        if (
            profile.onboarding_completed_at is None
            or profile.handle is None
            or profile.display_name is None
        ):
            raise ProfileIncompleteError()

        normalized_handle = normalize_handle(
            profile.handle if handle is None else handle
        )
        normalized_display_name = normalize_display_name(
            profile.display_name if display_name is None else display_name
        )
        if handle is not None:
            _raise_if_handle_taken(user, normalized_handle)

        update_fields: list[str] = []
        if profile.handle != normalized_handle:
            profile.handle = normalized_handle
            update_fields.append("handle")
        if profile.display_name != normalized_display_name:
            profile.display_name = normalized_display_name
            update_fields.append("display_name")
        if update_fields:
            _save_text_profile(profile, update_fields)
    return profile


def replace_profile_avatar(user: User, *, upload: File[bytes]) -> PlayerProfile:
    """Replace the enabled user's optional avatar using the media lifecycle seam."""
    with _avatar_operation_lock(user) as profile:
        _require_enabled(profile)
        media_service.replace_image(
            upload,
            old_key=profile.avatar_key,
            commit_reference=lambda new_key: _commit_avatar_reference(user, new_key),
        )
        profile.refresh_from_db()
        return profile


def remove_profile_avatar(user: User) -> None:
    """Remove the enabled user's optional avatar using the media lifecycle seam."""
    with _avatar_operation_lock(user) as profile:
        _require_enabled(profile)
        media_service.remove_optional_image(
            old_key=profile.avatar_key,
            commit_removal=lambda: _commit_avatar_removal(user),
        )


@contextmanager
def _avatar_operation_lock(user: User) -> Generator[PlayerProfile]:
    """Serialize one player's media lifecycle across PostgreSQL processes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [user.pk])
    try:
        yield get_or_create_profile(user)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [user.pk])


def _commit_avatar_reference(user: User, new_key: str) -> None:
    """Durably save an avatar key after checking enabled state under a row lock."""
    with transaction.atomic():
        profile = PlayerProfile.objects.select_for_update().get(user=user)
        _require_enabled(profile)
        profile.avatar_key = new_key
        profile.save(update_fields={"avatar_key"})


def _commit_avatar_removal(user: User) -> None:
    """Durably clear an avatar key after checking enabled state under a row lock."""
    with transaction.atomic():
        profile = PlayerProfile.objects.select_for_update().get(user=user)
        _require_enabled(profile)
        profile.avatar_key = None
        profile.save(update_fields={"avatar_key"})


def _locked_profile(user: User) -> PlayerProfile:
    get_or_create_profile(user)
    return PlayerProfile.objects.select_for_update().get(user=user)


def _require_enabled(profile: PlayerProfile) -> None:
    if not profile.is_enabled:
        raise ProfileDisabledError()


def _raise_if_handle_taken(user: User, handle: str) -> None:
    if PlayerProfile.objects.exclude(user=user).filter(handle=handle).exists():
        raise DuplicateHandleError()


def _save_text_profile(profile: PlayerProfile, update_fields: list[str]) -> None:
    try:
        with transaction.atomic():
            profile.save(update_fields=update_fields)
    except IntegrityError as error:
        if _is_handle_unique_violation(error):
            raise DuplicateHandleError() from None
        raise


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
