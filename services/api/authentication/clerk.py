"""Narrow, offline Clerk session-token verification boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request
from django.http import HttpRequest
from rest_framework.exceptions import AuthenticationFailed

_BEARER_CREDENTIAL = re.compile(r"(?i:Bearer) +([A-Za-z0-9\-._~+/]+=*)", flags=re.ASCII)


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
            raise AuthenticationFailed()

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
            raise AuthenticationFailed() from None
        if not state.is_signed_in or state.payload is None:
            raise AuthenticationFailed()

        session_id = state.payload.get("sid")
        subject = state.payload.get("sub")
        if not isinstance(session_id, str) or not session_id.strip():
            raise AuthenticationFailed()
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationFailed()

        return VerifiedClerkIdentity(subject=subject)
