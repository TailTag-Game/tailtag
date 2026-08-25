"""Owner-safe writes for durable fursuit records.

The media module owns object validation, storage and compensating cleanup.  This
module owns the database reference and the lock ordering needed to keep it
authoritative.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from django.core.files import File
from django.db import connection, transaction

from accounts.models import User
from fursuits.models import Fursuit
from fursuits.normalization import normalize_fursuit_name
from media import service as media_service
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile

__all__ = [
    "FursuitWriteIneligibleError",
    "create_fursuit",
    "fursuit_advisory_lock_key",
    "get_owned_fursuit",
    "replace_fursuit_photo",
    "require_fursuit_write_eligible",
    "update_fursuit_name",
]


class FursuitWriteIneligibleError(Exception):
    """The owner cannot currently perform a fursuit write."""


def require_fursuit_write_eligible(user: User) -> None:
    """Perform the inexpensive, non-creating eligibility pre-check."""
    if not is_participation_eligible(user):
        raise FursuitWriteIneligibleError()


def get_owned_fursuit(user: User, fursuit_id: int) -> Fursuit:
    """Return only a fursuit owned by ``user`` (including 404 concealment)."""
    return Fursuit.objects.get(pk=fursuit_id, owner=user)


def create_fursuit(user: User, *, name: str, upload: File[bytes]) -> Fursuit:
    """Store a required photo then atomically make its new reference durable."""
    require_fursuit_write_eligible(user)
    normalized_name = normalize_fursuit_name(name)
    created: Fursuit | None = None

    def commit_reference(new_key: str) -> None:
        nonlocal created
        created = _commit_created_fursuit(user, normalized_name, new_key)

    media_service.replace_image(
        upload,
        old_key=None,
        commit_reference=commit_reference,
    )
    assert created is not None
    return created


def update_fursuit_name(
    user: User, fursuit: Fursuit | int, *, name: str
) -> Fursuit:
    """Update an owned fursuit name, preserving a normalized no-op exactly."""
    require_fursuit_write_eligible(user)
    normalized_name = normalize_fursuit_name(name)
    fursuit_id = _fursuit_id(fursuit)
    with transaction.atomic():
        _locked_eligible_profile(user)
        owned = _locked_owned_fursuit(user, fursuit_id)
        if owned.name == normalized_name:
            # Preserve the caller's already-current object on the no-write path.
            return fursuit if isinstance(fursuit, Fursuit) else owned
        owned.name = normalized_name
        owned.save(update_fields={"name", "updated_at"})
        return owned


def replace_fursuit_photo(
    user: User, fursuit: Fursuit | int, *, upload: File[bytes]
) -> str:
    """Serialize a full same-fursuit media lifecycle with an advisory lock."""
    require_fursuit_write_eligible(user)
    fursuit_id = _fursuit_id(fursuit)
    with _fursuit_photo_operation_lock(fursuit_id):
        current = get_owned_fursuit(user, fursuit_id)
        return media_service.replace_image(
            upload,
            old_key=current.photo_key,
            commit_reference=lambda new_key: _commit_replaced_fursuit_photo(
                user, fursuit_id, new_key
            ),
        )


def fursuit_advisory_lock_key(fursuit_id: int) -> int:
    """Map a positive fursuit identity into the avatar-disjoint negative range."""
    if fursuit_id <= 0:
        raise ValueError("fursuit_id must be positive")
    return -fursuit_id


@contextmanager
def _fursuit_photo_operation_lock(fursuit_id: int) -> Generator[None]:
    """Hold a PostgreSQL advisory lock across upload, commit and cleanup."""
    key = fursuit_advisory_lock_key(fursuit_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [key])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def _commit_created_fursuit(user: User, name: str, photo_key: str) -> Fursuit:
    """Commit creation only after the authoritative locked eligibility check."""
    with transaction.atomic():
        _locked_eligible_profile(user)
        return Fursuit.objects.create(owner=user, name=name, photo_key=photo_key)


def _commit_replaced_fursuit_photo(
    user: User, fursuit_id: int, photo_key: str
) -> None:
    """Commit a replacement reference after locking profile before fursuit."""
    with transaction.atomic():
        _locked_eligible_profile(user)
        fursuit = _locked_owned_fursuit(user, fursuit_id)
        fursuit.photo_key = photo_key
        fursuit.save(update_fields={"photo_key", "updated_at"})


def _locked_eligible_profile(user: User) -> PlayerProfile:
    """Lock an already-complete enabled profile, without creating or repairing it."""
    profile = (
        PlayerProfile.objects.select_for_update()
        .filter(
            user=user,
            onboarding_completed_at__isnull=False,
            handle__isnull=False,
            display_name__isnull=False,
            is_enabled=True,
        )
        .exclude(display_name="")
        .first()
    )
    if profile is None:
        raise FursuitWriteIneligibleError()
    return profile


def _locked_owned_fursuit(user: User, fursuit_id: int) -> Fursuit:
    """Acquire the second row lock only after the profile lock."""
    return Fursuit.objects.select_for_update().get(pk=fursuit_id, owner=user)


def _fursuit_id(fursuit: Fursuit | int) -> int:
    """Support the frozen service test seam while retaining ID-based callers."""
    return fursuit.id if isinstance(fursuit, Fursuit) else fursuit
