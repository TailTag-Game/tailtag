"""Dependency-free constants for the reusable TailTag payload format.

The printed payload is a one-way door (#502 G7). Badges carry it after printing.
"""

from typing import Final

TAG_TOKEN_BYTES: Final = 32
TAG_TOKEN_LENGTH: Final = 43
TAG_PAYLOAD_PREFIX: Final = "https://tailtag.app/t#"
TAG_TOKEN_PATTERN: Final = rf"[A-Za-z0-9_-]{{{TAG_TOKEN_LENGTH}}}"
