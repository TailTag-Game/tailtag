"""Narrow, offline Clerk session-token verification boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, NoReturn, Protocol

from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request
from clerk_backend_api.security.types import (
    AuthErrorReason,
    TokenVerificationErrorReason,
)
from django.http import HttpRequest
from rest_framework.exceptions import AuthenticationFailed

from observability.outcomes import Outcome, Reason, Signal, record_outcome

_BEARER_CREDENTIAL = re.compile(r"(?i:Bearer) +([A-Za-z0-9\-._~+/]+=*)", flags=re.ASCII)

# Every reason the SDK can return for a signed-out request. A reason the SDK adds
# later has no entry and is reported as `other` until it is classified here.
CLERK_FAILURE_REASONS: Final[
    dict[AuthErrorReason | TokenVerificationErrorReason, Reason]
] = {
    AuthErrorReason.SESSION_TOKEN_MISSING: Reason.MALFORMED_HEADER,
    AuthErrorReason.SECRET_KEY_MISSING: Reason.VERIFIER_MISCONFIGURED,
    AuthErrorReason.TOKEN_TYPE_NOT_SUPPORTED: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.TOKEN_EXPIRED: Reason.TOKEN_EXPIRED,
    TokenVerificationErrorReason.TOKEN_IAT_IN_THE_FUTURE: Reason.TOKEN_NOT_YET_VALID,
    TokenVerificationErrorReason.TOKEN_NOT_ACTIVE_YET: Reason.TOKEN_NOT_YET_VALID,
    TokenVerificationErrorReason.TOKEN_INVALID: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.TOKEN_INVALID_SIGNATURE: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.TOKEN_INVALID_AUTHORIZED_PARTIES: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.TOKEN_INVALID_AUDIENCE: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.JWK_KID_MISMATCH: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.INVALID_TOKEN_TYPE: Reason.TOKEN_INVALID,
    TokenVerificationErrorReason.SECRET_KEY_MISSING: Reason.VERIFIER_MISCONFIGURED,
    TokenVerificationErrorReason.JWK_FAILED_TO_LOAD: Reason.VERIFIER_MISCONFIGURED,
    TokenVerificationErrorReason.JWK_REMOTE_INVALID: Reason.VERIFIER_MISCONFIGURED,
    TokenVerificationErrorReason.JWK_FAILED_TO_RESOLVE: Reason.VERIFIER_MISCONFIGURED,
    TokenVerificationErrorReason.SERVER_ERROR: Reason.VERIFIER_MISCONFIGURED,
}


@dataclass(frozen=True, slots=True)
class ClerkVerificationConfiguration:
    """Offline trust material and allowed parties for Clerk session verification."""

    jwt_key: str = field(repr=False)
    authorized_parties: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifiedClerkIdentity:
    """The TailTag-safe identity yielded by a verified Clerk session."""

    subject: str


class ClerkIdentityVerifier(Protocol):
    """Verifies a request into a minimal external identity, when present."""

    def verify(self, request: HttpRequest) -> VerifiedClerkIdentity | None: ...


@dataclass(frozen=True, slots=True)
class _AuthorizationOnlyRequest:
    """Clerk request surface with no cookie fallback."""

    headers: dict[str, str]


class ClerkSessionVerifier:
    """Verifies only canonical Bearer Clerk session tokens, offline."""

    def __init__(self, configuration: ClerkVerificationConfiguration) -> None:
        self._configuration = configuration

    def verify(self, request: HttpRequest) -> VerifiedClerkIdentity | None:
        authorization = request.headers.get("Authorization")
        if authorization is None:
            return None

        credential = _BEARER_CREDENTIAL.fullmatch(authorization)
        if credential is None:
            _reject(Reason.MALFORMED_HEADER)

        options = AuthenticateRequestOptions(
            jwt_key=self._configuration.jwt_key,
            authorized_parties=list(self._configuration.authorized_parties),
            accepts_token=["session_token"],
        )
        try:
            state = authenticate_request(
                _AuthorizationOnlyRequest(
                    headers={"Authorization": f"Bearer {credential.group(1)}"}
                ),
                options,
            )
        except (AttributeError, TypeError):
            _reject(Reason.OTHER)
        if not state.is_signed_in:
            _reject(
                Reason.OTHER
                if state.reason is None
                else CLERK_FAILURE_REASONS.get(state.reason, Reason.OTHER)
            )
        if state.payload is None:
            _reject(Reason.CLAIMS_MISSING)

        session_id = state.payload.get("sid")
        subject = state.payload.get("sub")
        if not isinstance(session_id, str) or not session_id.strip():
            _reject(Reason.CLAIMS_MISSING)
        if not isinstance(subject, str) or not subject.strip():
            _reject(Reason.CLAIMS_MISSING)

        return VerifiedClerkIdentity(subject=subject)


def _reject(reason: Reason) -> NoReturn:
    record_outcome(Signal.AUTHENTICATION_VERIFICATION, Outcome.REJECTED, reason)
    raise AuthenticationFailed()
