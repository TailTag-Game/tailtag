"""Dependency-free constants for the V1 catch-credential payload protocol."""

from typing import Final

CATCH_CREDENTIAL_TOKEN_BYTES: Final = 32
CATCH_CREDENTIAL_TOKEN_LENGTH: Final = 43
CATCH_CREDENTIAL_PAYLOAD_PREFIX: Final = "tailtag:catch:v1:"
CATCH_CREDENTIAL_TOKEN_PATTERN: Final = (
    rf"[A-Za-z0-9_-]{{{CATCH_CREDENTIAL_TOKEN_LENGTH}}}"
)
CATCH_CREDENTIAL_PAYLOAD_PATTERN: Final = (
    rf"^{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{CATCH_CREDENTIAL_TOKEN_PATTERN}$"
)
