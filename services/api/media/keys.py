"""Opaque, server-owned object key helpers for normalized images."""

from __future__ import annotations

import re
from uuid import uuid4

_IMAGE_KEY_PATTERN = re.compile(r"images/[0-9a-f]{32}\.(?:jpg|png|webp)\Z")
_CANONICAL_EXTENSIONS = frozenset({"jpg", "png", "webp"})
_INVALID_KEY_MESSAGE = "Invalid image key."


def create_image_key(extension: str) -> str:
    """Create an opaque image key for one canonical normalized extension."""
    if extension not in _CANONICAL_EXTENSIONS:
        raise ValueError(_INVALID_KEY_MESSAGE)
    return f"images/{uuid4().hex}.{extension}"


def validate_image_key(key: str) -> str:
    """Return a conforming key, rejecting every unsafe key identically."""
    if _IMAGE_KEY_PATTERN.fullmatch(key) is None:
        raise ValueError(_INVALID_KEY_MESSAGE)
    return key
