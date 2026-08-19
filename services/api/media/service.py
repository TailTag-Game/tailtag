"""Storage-agnostic media operations and database-reference lifecycle ordering."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal, cast

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage

from .images import NormalizedImage, normalize_image
from .keys import create_image_key, validate_image_key

_LOGGER = logging.getLogger(__name__)
_REPLACEMENT_CLEANUP_WARNING = "Media cleanup failed after replacement commit."
_REMOVAL_CLEANUP_WARNING = "Media cleanup failed after removal commit."


class _CanonicalContentFile(ContentFile):  # type: ignore[type-arg]
    """A normalized payload with the MIME metadata needed by S3 storage."""

    content_type: Literal["image/jpeg", "image/png", "image/webp"]


def _storage_or_default(storage: Storage | None) -> Storage:
    return default_storage if storage is None else storage


def _normalized_image(upload: object) -> NormalizedImage:
    if not isinstance(upload, File):
        raise TypeError("upload must be a Django File")
    return normalize_image(cast("File[bytes]", upload))


def _compensate_failed_commit(storage: Storage, key: str) -> None:
    """Attempt cleanup without allowing a secondary failure to hide the commit one."""
    try:
        storage.delete(key)
    except BaseException:  # noqa: BLE001 - cleanup failure must be deliberately ignored.
        return


def store_image(upload: File[bytes], *, storage: Storage | None = None) -> str:
    """Normalize and store an image, returning only its opaque object key."""
    normalized = _normalized_image(upload)
    requested_key = create_image_key(normalized.extension)
    content = _CanonicalContentFile(normalized.content, name=requested_key)
    content.content_type = normalized.content_type
    stored_key = _storage_or_default(storage).save(requested_key, content)
    return validate_image_key(stored_key)


def read_image_url(key: str, *, storage: Storage | None = None) -> str:
    """Generate an ephemeral backend read URL without recording it."""
    return _storage_or_default(storage).url(validate_image_key(key))


def replace_image(
    upload: File[bytes],
    *,
    old_key: str | None,
    commit_reference: Callable[[str], None],
    storage: Storage | None = None,
) -> str:
    """Store, commit, then best-effort remove a replaced image object."""
    if old_key is not None:
        validate_image_key(old_key)

    backend = _storage_or_default(storage)
    new_key = store_image(upload, storage=backend)
    try:
        commit_reference(new_key)
    except BaseException:
        _compensate_failed_commit(backend, new_key)
        raise

    if old_key is not None:
        try:
            backend.delete(old_key)
        except Exception:  # noqa: BLE001 - committed reference remains authoritative.
            _LOGGER.warning(_REPLACEMENT_CLEANUP_WARNING)
    return new_key


def remove_optional_image(
    *,
    old_key: str | None,
    commit_removal: Callable[[], None],
    storage: Storage | None = None,
) -> None:
    """Commit an absent reference, then best-effort remove its old object."""
    if old_key is not None:
        validate_image_key(old_key)

    commit_removal()
    if old_key is None:
        return
    try:
        _storage_or_default(storage).delete(old_key)
    except Exception:  # noqa: BLE001 - committed absence remains authoritative.
        _LOGGER.warning(_REMOVAL_CLEANUP_WARNING)
