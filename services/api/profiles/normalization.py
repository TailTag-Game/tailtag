"""Pure normalization for player-profile text fields."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

RESERVED_HANDLES = frozenset(
    {"admin", "api", "me", "moderator", "staff", "support", "system", "tailtag"}
)
HANDLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{1,31}$", flags=re.ASCII)


class ProfileValueError(Exception):
    """A safe, field-specific profile value validation failure."""

    def __init__(
        self,
        field: Literal["handle", "display_name"],
        code: str,
        safe_message: str,
    ) -> None:
        super().__init__(safe_message)
        self.field = field
        self.code = code
        self.safe_message = safe_message


def normalize_handle(value: str) -> str:
    """Return a valid canonical handle or a safe validation failure."""
    normalized = value.lower()
    if HANDLE_PATTERN.fullmatch(normalized) is None:
        raise ProfileValueError("handle", "invalid", "Enter a valid handle.")
    if normalized in RESERVED_HANDLES:
        raise ProfileValueError("handle", "reserved", "This handle is reserved.")
    return normalized


def normalize_display_name(value: str) -> str:
    """Return a normalized single-line display name or a safe failure."""
    normalized = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char) in {"Cc", "Zl", "Zp"} for char in normalized):
        raise ProfileValueError(
            "display_name", "invalid", "Enter a single-line display name."
        )
    collapsed = " ".join(normalized.strip().split())
    if not 1 <= len(collapsed) <= 50:
        raise ProfileValueError(
            "display_name",
            "invalid_length",
            "Enter a display name of 1–50 characters.",
        )
    return collapsed
