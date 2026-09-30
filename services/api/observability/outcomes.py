"""Domain outcome telemetry: the bounded taxonomy and the one recorder.

Every domain outcome is one INFO log line and one Sentry count of 1, both named by
the signal and carrying only the bounded outcome and reason values below. Values are
add-only: dashboards and alerts depend on them. See
`docs/architecture/backend/observability.md`.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import sentry_sdk

_logger = logging.getLogger(__name__)


class Signal(StrEnum):
    CATCH_CONFIRMATION = "tailtag.catches.confirmation"
    CREDENTIAL_RESOLUTION = "tailtag.conventions.credential_resolution"
    CATCH_SESSION = "tailtag.conventions.catch_session"
    AUTHENTICATION_VERIFICATION = "tailtag.authentication.verification"


class Outcome(StrEnum):
    CREATED = "created"
    ALREADY_CAUGHT = "already_caught"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    STARTED = "started"
    START_REJECTED = "start_rejected"
    ENDED = "ended"


class Reason(StrEnum):
    # Catch confirmation and credential resolution.
    PAYLOAD_INVALID = "payload_invalid"
    CATCHER_INELIGIBLE = "catcher_ineligible"
    CONVENTION_MISMATCH = "convention_mismatch"
    SELF_CATCH = "self_catch"
    CALLER_INELIGIBLE = "caller_ineligible"
    CONVENTION_UNKNOWN = "convention_unknown"
    # Target reasons, in the order catch confirmation checks them.
    CREDENTIAL_UNKNOWN = "credential_unknown"
    CREDENTIAL_REVOKED = "credential_revoked"
    CONVENTION_NOT_PLAYABLE = "convention_not_playable"
    TARGET_INELIGIBLE = "target_ineligible"
    ACTIVATION_INACTIVE = "activation_inactive"
    SESSION_INACTIVE = "session_inactive"
    SESSION_EXPIRED = "session_expired"
    # Catch session start rejections.
    OWNER_INELIGIBLE = "owner_ineligible"
    NOT_ENROLLED = "not_enrolled"
    ACTIVATION_INELIGIBLE = "activation_ineligible"
    # Catch session end reasons (`FursuitCatchSessionEndReason` values).
    OWNER = "owner"
    OPERATOR = "operator"
    ELIGIBILITY_LOST = "eligibility_lost"
    EXPIRED = "expired"
    # Authentication.
    MALFORMED_HEADER = "malformed_header"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_NOT_YET_VALID = "token_not_yet_valid"
    TOKEN_INVALID = "token_invalid"
    CLAIMS_MISSING = "claims_missing"
    VERIFIER_MISCONFIGURED = "verifier_misconfigured"
    USER_RESOLUTION_UNAVAILABLE = "user_resolution_unavailable"
    OTHER = "other"


def record_outcome(
    signal: Signal, outcome: Outcome, reason: Reason | None = None
) -> None:
    """Write one outcome log line and count it once; the only domain outcome emitter."""
    extra: dict[str, object] = {"event": str(signal), "tailtag_outcome": str(outcome)}
    attributes = {"tailtag.outcome": str(outcome)}
    if reason is not None:
        extra["tailtag_reason"] = str(reason)
        attributes["tailtag.reason"] = str(reason)
    _logger.info("Domain outcome recorded", extra=extra)
    sentry_sdk.metrics.count(str(signal), 1, attributes=attributes)
