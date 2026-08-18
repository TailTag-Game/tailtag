"""Guarded, development-only Clerk session creation for local smoke tooling.

This module deliberately keeps provider credentials and issued values in memory.
It is not an application authentication path.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from http.cookiejar import CookieJar
from typing import Any, Final, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from clerk_backend_api import Clerk
from clerk_backend_api.models import CreateSignInTokenRequestBody
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import HttpRequest

from authentication.clerk import ClerkSessionVerifier, ClerkVerificationConfiguration

TOOLING_ORIGIN: Final = "http://localhost:3000"
MAX_SESSION_TOKEN_LIFETIME_SECONDS: Final = 60
SIGN_IN_TICKET_LIFETIME_SECONDS: Final = 60
_REQUEST_TIMEOUT_SECONDS: Final = 10
_FAPI_API_VERSION: Final = "2026-05-12"
_DEVELOPMENT_FAPI_HOST_SUFFIX: Final = ".clerk.accounts.dev"


class ClerkFlowStage(StrEnum):
    """Closed, non-sensitive failure stages for the tooling caller."""

    INSTANCE = "Clerk instance not validated as Development"
    USER = "configured smoke user unavailable"
    TICKET = "provider ticket flow unsuccessful"
    TOKEN = "provider session-token flow unsuccessful"
    CLAIMS = "token claims or lifetime invalid"
    VERIFIER = "TailTag verifier rejected the token"
    CLEANUP = "cleanup incomplete"


class ClerkFlowFailure(Exception):
    """A provider failure that intentionally reveals only its fixed stage."""

    def __init__(self, stage: ClerkFlowStage) -> None:
        self.stage = stage
        super().__init__(stage.value)


class ClerkCredentialFailure(Exception):
    """Reject an unsafe credential form before opening a provider boundary."""

    def __init__(self) -> None:
        super().__init__("credential form invalid")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


@dataclass(slots=True)
class ClerkDevelopmentSession:
    """A short-lived, verified development session and its supported cleanup."""

    _secret: str = field(repr=False)
    _user_id: str = field(repr=False)
    _transport: Any = field(repr=False)
    _fapi_authority: str | None = field(default=None, repr=False)
    _ticket_id: str | None = field(default=None, repr=False)
    _ticket_consumed: bool = False
    _session_id: str | None = field(default=None, repr=False)
    _token: str | None = field(default=None, repr=False)

    @classmethod
    def validate(
        cls,
        *,
        secret: str,
        user_id: str,
        transport: Any | None = None,
    ) -> ClerkDevelopmentSession:
        """Validate the fixed Development instance and its already-provisioned user."""
        if not secret.startswith("sk_test_"):
            raise ClerkCredentialFailure()
        try:
            clerk: Any = transport if transport is not None else Clerk(bearer_auth=secret)
            instance: object = cast(object, clerk.instance_settings.get())
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.INSTANCE) from None

        if getattr(instance, "environment_type", None) != "development":
            raise ClerkFlowFailure(ClerkFlowStage.INSTANCE)
        try:
            user: object = cast(object, clerk.users.get(user_id=user_id))
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.USER) from None
        if getattr(user, "id", None) != user_id:
            raise ClerkFlowFailure(ClerkFlowStage.USER)
        return cls(
            _secret=secret,
            _user_id=user_id,
            _transport=clerk,
        )

    def create_verified_token(self) -> str:
        """Issue a normal FAPI session token and verify it with the existing verifier."""
        ticket = self._create_ticket()
        ticket_value = getattr(ticket, "token", None)
        ticket_id = getattr(ticket, "id", None)
        ticket_url = getattr(ticket, "url", None)
        if (
            not isinstance(ticket_value, str)
            or not ticket_value
            or not isinstance(ticket_id, str)
            or not ticket_id
            or not isinstance(ticket_url, str)
            or not _is_development_fapi_url(ticket_url)
        ):
            raise ClerkFlowFailure(ClerkFlowStage.TICKET)
        self._ticket_id = ticket_id
        self._fapi_authority = ticket_url

        try:
            client, opener, dev_token = self._run_frontend_ticket_flow(ticket_value)
            session_id = _active_session_id(client, self._user_id)
            if session_id is None:
                raise ValueError
            self._session_id = session_id
            self._ticket_consumed = True
            token = self._request_session_token(opener, dev_token, session_id)
        except ClerkFlowFailure:
            raise
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TICKET) from None

        self._token = token
        self._validate_claims_and_verifier(token)
        return token

    def cleanup(self) -> None:
        """Revoke only resources owned by this run, attempting all applicable work."""
        failed = False
        if self._session_id is not None:
            try:
                self._transport.sessions.revoke(session_id=self._session_id)
            except Exception:  # noqa: BLE001 - cleanup must attempt both resources
                failed = True
        if self._ticket_id is not None and not self._ticket_consumed:
            try:
                self._transport.sign_in_tokens.revoke(
                    sign_in_token_id=self._ticket_id
                )
            except Exception:  # noqa: BLE001 - cleanup must attempt both resources
                failed = True
        if failed:
            raise ClerkFlowFailure(ClerkFlowStage.CLEANUP)

    def _create_ticket(self) -> object:
        try:
            return cast(object, self._transport.sign_in_tokens.create(
                request=CreateSignInTokenRequestBody(
                    user_id=self._user_id,
                    expires_in_seconds=SIGN_IN_TICKET_LIFETIME_SECONDS,
                )
            ))
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TICKET) from None

    def _run_frontend_ticket_flow(
        self, ticket: str
    ) -> tuple[dict[str, object], urllib.request.OpenerDirector, str]:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()), _NoRedirect()
        )
        dev_browser = self._frontend_request(opener, "/v1/dev_browser")
        dev_token = _field(dev_browser, "token")
        if not isinstance(dev_token, str):
            raise ClerkFlowFailure(ClerkFlowStage.TICKET)
        self._frontend_request(
            opener, "/v1/client", query={"__dev_session": dev_token}
        )
        signed_in_client = self._frontend_request(
            opener,
            "/v1/client/sign_ins",
            query={"__dev_session": dev_token},
            form={"strategy": "ticket", "ticket": ticket},
        )
        return signed_in_client, opener, dev_token

    def _request_session_token(
        self,
        opener: urllib.request.OpenerDirector,
        dev_token: str,
        session_id: str,
    ) -> str:
        try:
            response = self._frontend_request(
                opener,
                f"/v1/client/sessions/{urllib.parse.quote(session_id, safe='')}/tokens",
                query={"__dev_session": dev_token},
                failure_stage=ClerkFlowStage.TOKEN,
            )
            token = _field(response, "jwt")
            if not isinstance(token, str):
                raise TypeError
            return token
        except ClerkFlowFailure:
            raise
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TOKEN) from None

    def _frontend_request(
        self,
        opener: urllib.request.OpenerDirector,
        path: str,
        *,
        query: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        failure_stage: ClerkFlowStage = ClerkFlowStage.TICKET,
    ) -> dict[str, object]:
        url = _fapi_url(self._fapi_authority, path, query)
        data = None if form is None else urllib.parse.urlencode(form).encode("ascii")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Clerk-API-Version": _FAPI_API_VERSION,
                "Origin": TOOLING_ORIGIN,
            },
            method="POST",
        )
        try:
            with opener.open(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                if response.getcode() // 100 != 2 or response.geturl() != url:
                    raise ValueError
                payload: object = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            raise ClerkFlowFailure(failure_stage) from None
        if not isinstance(payload, dict):
            raise ClerkFlowFailure(failure_stage)
        response_payload = cast(dict[str, object], payload)
        nested = response_payload.get("response")
        return cast(dict[str, object], nested) if isinstance(nested, dict) else response_payload

    def _validate_claims_and_verifier(self, token: str) -> None:
        try:
            header, claims = _unverified_jwt_parts(token)
            kid = header.get("kid")
            if not isinstance(kid, str):
                raise TypeError
            public_key_pem = self._matching_jwk_pem(kid)
            sid, sub, azp = claims.get("sid"), claims.get("sub"), claims.get("azp")
            iat, exp = claims.get("iat"), claims.get("exp")
            lifetime = exp - iat if type(iat) is int and type(exp) is int else 0
            if (
                sid != self._session_id
                or sub != self._user_id
                or azp != TOOLING_ORIGIN
                or type(iat) is not int
                or type(exp) is not int
                or not 0 < lifetime <= MAX_SESSION_TOKEN_LIFETIME_SECONDS
                or exp <= int(time.time())
            ):
                raise ClerkFlowFailure(ClerkFlowStage.CLAIMS)
        except ClerkFlowFailure:
            raise
        except Exception:  # noqa: BLE001 - claims and crypto errors remain opaque
            raise ClerkFlowFailure(ClerkFlowStage.CLAIMS) from None

        request = HttpRequest()
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        try:
            identity = ClerkSessionVerifier(
                ClerkVerificationConfiguration(
                    jwt_key=public_key_pem,
                    authorized_parties=(TOOLING_ORIGIN,),
                )
            ).verify(request)
        except Exception:  # noqa: BLE001 - verifier errors remain opaque
            raise ClerkFlowFailure(ClerkFlowStage.VERIFIER) from None
        if identity is None or identity.subject != self._user_id:
            raise ClerkFlowFailure(ClerkFlowStage.VERIFIER)

    def _matching_jwk_pem(self, kid: str) -> str:
        jwks: object = cast(object, self._transport.jwks.get_jwks())
        for key in getattr(jwks, "keys", []):
            if getattr(key, "kid", None) == kid:
                if getattr(key, "kty", None) != "RSA":
                    break
                modulus = _base64url_int(getattr(key, "n", None))
                exponent = _base64url_int(getattr(key, "e", None))
                return (
                    rsa.RSAPublicNumbers(exponent, modulus)
                    .public_key()
                    .public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    .decode("ascii")
                )
        raise TypeError


def _is_development_fapi_url(value: str) -> bool:
    parsed = urlsplit(value)
    host = parsed.hostname
    return (
        parsed.scheme == "https"
        and host is not None
        and host.endswith(_DEVELOPMENT_FAPI_HOST_SUFFIX)
        and host != _DEVELOPMENT_FAPI_HOST_SUFFIX[1:]
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
    )


def _fapi_url(base_url: str | None, path: str, query: dict[str, str] | None) -> str:
    if base_url is None:
        raise ValueError
    parsed = urlsplit(base_url)
    return urlunsplit(
        SplitResult(
            scheme=parsed.scheme,
            netloc=parsed.netloc,
            path=path,
            query=urllib.parse.urlencode(query or {}),
            fragment="",
        )
    )


def _field(payload: dict[str, object], name: str) -> object:
    return payload.get(name)


def _active_session_id(client: dict[str, object], user_id: str) -> str | None:
    sessions = client.get("sessions")
    if not isinstance(sessions, list):
        return None
    for session in cast(list[object], sessions):
        if not isinstance(session, dict):
            continue
        session_data = cast(dict[str, object], session)
        if session_data.get("status") != "active":
            continue
        if session_data.get("user_id") != user_id:
            continue
        session_id = session_data.get("id")
        if isinstance(session_id, str):
            return session_id
    return None


def _unverified_jwt_parts(token: str) -> tuple[dict[str, object], dict[str, object]]:
    encoded_header, encoded_claims, _signature = token.split(".")
    header: object = json.loads(_base64url_decode(encoded_header))
    claims: object = json.loads(_base64url_decode(encoded_claims))
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise TypeError
    return cast(dict[str, object], header), cast(dict[str, object], claims)


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _base64url_int(value: object) -> int:
    if not isinstance(value, str):
        raise TypeError
    decoded = _base64url_decode(value)
    if not decoded:
        raise ValueError
    return int.from_bytes(decoded, "big")
