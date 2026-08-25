"""Fursuit-specific boundary for established human-name normalization."""

from __future__ import annotations

from profiles.normalization import ProfileValueError, normalize_display_name


class FursuitNameError(ValueError):
    """A safe fursuit-name validation failure."""

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


def normalize_fursuit_name(value: str) -> str:
    """Return a normalized fursuit name or a fursuit-named safe failure."""
    try:
        return normalize_display_name(value)
    except ProfileValueError as error:
        safe_messages = {
            "invalid": "Enter a single-line name.",
            "invalid_length": "Enter a name of 1–50 characters.",
        }
        raise FursuitNameError(error.code, safe_messages[error.code]) from None
