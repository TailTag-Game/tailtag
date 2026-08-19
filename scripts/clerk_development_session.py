"""Guarded, development-only Clerk session creation for local smoke tooling.

This module deliberately keeps provider credentials and issued values in memory.
It is not an application authentication path.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, cast
from urllib.parse import quote, urlsplit

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.models import CreateSignInTokenRequestBody
from clerk_backend_api.utils import BackoffStrategy, RetryConfig
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
_MAX_DEVELOPMENT_BROWSER_ERROR_BODY_BYTES: Final = 4096
_FAPI_USER_AGENT: Final = "TailTag-Issue-99-Development-Smoke"
_FAPI_ACCEPT: Final = "application/json"
_PROVIDER_LOGGER_NAMES: Final = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
)
_http_client_factory = httpx.Client


class ClerkFlowStage(StrEnum):
    """Closed, non-sensitive failure stages for the tooling caller."""

    INSTANCE = "Clerk instance not validated as Development"
    USER = "configured smoke user unavailable"
    DEVELOPMENT_BROWSER = "provider development-browser flow unsuccessful"
    DEVELOPMENT_BROWSER_REQUEST_INVALID = "provider development-browser request invalid"
    DEVELOPMENT_BROWSER_REQUEST_UNAUTHENTICATED = (
        "provider development-browser request unauthenticated"
    )
    DEVELOPMENT_BROWSER_REQUEST_FORBIDDEN = (
        "provider development-browser request forbidden"
    )
    DEVELOPMENT_BROWSER_BROWSER_CHALLENGE_REQUIRED = (
        "provider development-browser browser challenge required"
    )
    DEVELOPMENT_BROWSER_ORIGIN_REJECTED = "provider development-browser origin rejected"
    DEVELOPMENT_BROWSER_HOSTNAME_REJECTED = (
        "provider development-browser hostname rejected"
    )
    DEVELOPMENT_BROWSER_REQUEST_REJECTED = (
        "provider development-browser request rejected"
    )
    DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE = (
        "provider development-browser transport unavailable"
    )
    DEVELOPMENT_BROWSER_RESPONSE_INVALID = (
        "provider development-browser response invalid"
    )
    CLIENT_INITIALIZATION = "provider client initialization unsuccessful"
    TICKET = "provider ticket flow unsuccessful"
    TICKET_CREDENTIAL = "provider sign-in-ticket credential unavailable"
    FAPI_AUTHORITY = "provider Frontend API authority unavailable"
    TOKEN = "provider session-token flow unsuccessful"
    TOKEN_REQUEST_INVALID = "provider session-token request invalid"
    TOKEN_REQUEST_UNAUTHENTICATED = "provider session-token request unauthenticated"
    TOKEN_REQUEST_FORBIDDEN = "provider session-token request forbidden"
    TOKEN_REQUEST_NOT_FOUND = "provider session-token request not found"
    TOKEN_REQUEST_REJECTED = "provider session-token request rejected"
    TOKEN_TRANSPORT_UNAVAILABLE = "provider session-token transport unavailable"
    TOKEN_RESPONSE_INVALID = "provider session-token response invalid"
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


@dataclass(frozen=True, slots=True)
class _AuthorizationRequest:
    headers: dict[str, str]


@contextmanager
def _suppress_provider_debug_logs() -> Generator[None]:
    """Temporarily disable the provider HTTP loggers around sensitive work."""
    loggers = [logging.getLogger(name) for name in _PROVIDER_LOGGER_NAMES]
    disabled = [logger.disabled for logger in loggers]
    for logger in loggers:
        logger.disabled = True
    try:
        yield
    finally:
        for logger, prior_disabled in zip(loggers, disabled, strict=True):
            logger.disabled = prior_disabled


def _development_browser_forbidden_stage(
    response: httpx.Response,
) -> ClerkFlowStage:
    if _has_mitigation_challenge_header(response.headers):
        return ClerkFlowStage.DEVELOPMENT_BROWSER_BROWSER_CHALLENGE_REQUIRED

    body_text = _development_browser_error_body_text(response)
    if body_text is None:
        return ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_FORBIDDEN
    if any(marker in body_text for marker in ("bot", "captcha", "challenge")):
        return ClerkFlowStage.DEVELOPMENT_BROWSER_BROWSER_CHALLENGE_REQUIRED
    if "origin" in body_text:
        return ClerkFlowStage.DEVELOPMENT_BROWSER_ORIGIN_REJECTED
    if "hostname" in body_text or "host" in body_text:
        return ClerkFlowStage.DEVELOPMENT_BROWSER_HOSTNAME_REJECTED
    return ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_FORBIDDEN


def _has_mitigation_challenge_header(headers: object) -> bool:
    try:
        items = cast(Any, headers).items()
        return any(
            isinstance(name, str)
            and isinstance(value, str)
            and ("mitigated" in name.casefold() or "challenge" in name.casefold())
            and "challenge" in value.casefold()
            for name, value in items
        )
    except Exception:  # noqa: BLE001 - diagnostic metadata is untrusted
        return False


def _development_browser_error_body_text(response: httpx.Response) -> str | None:
    try:
        response_body = response.content[:_MAX_DEVELOPMENT_BROWSER_ERROR_BODY_BYTES]
        payload: object = json.loads(response_body.decode("utf-8"))
    except Exception:  # noqa: BLE001 - malformed diagnostics fail closed
        return None
    if not isinstance(payload, dict):
        return None
    error_payload = cast(dict[str, object], payload)
    errors = error_payload.get("errors")
    if not isinstance(errors, list):
        return None
    messages: list[str] = []
    for error_entry in cast(list[object], errors):
        if not isinstance(error_entry, dict):
            continue
        error_details = cast(dict[str, object], error_entry)
        for name in ("message", "long_message"):
            value = error_details.get(name)
            if isinstance(value, str):
                messages.append(value)
    return " ".join(messages).casefold()


@dataclass(slots=True)
class ClerkDevelopmentSession:
    """A short-lived, verified development session and its supported cleanup."""

    _user_id: str = field(repr=False)
    _transport: Any = field(repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)
    _fapi_authority: str | None = field(default=None, repr=False)
    _fapi_client: httpx.Client | None = field(default=None, repr=False)
    _ticket_id: str | None = field(default=None, repr=False)
    _ticket_cleanup_uncertain: bool = False
    _ticket_consumed: bool = False
    _session_id: str | None = field(default=None, repr=False)
    _session_cleanup_uncertain: bool = False

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
        http_client = (
            None
            if transport is not None
            else _http_client_factory(trust_env=False, follow_redirects=False)
        )
        try:
            clerk: Any = (
                transport
                if transport is not None
                else Clerk(bearer_auth=secret, client=http_client)
            )
            instance: object = cast(object, clerk.instance_settings.get())
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            _close_client(http_client)
            raise ClerkFlowFailure(ClerkFlowStage.INSTANCE) from None

        if getattr(instance, "environment_type", None) != "development":
            _close_client(http_client)
            raise ClerkFlowFailure(ClerkFlowStage.INSTANCE)
        try:
            user: object = cast(object, clerk.users.get(user_id=user_id))
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            _close_client(http_client)
            raise ClerkFlowFailure(ClerkFlowStage.USER) from None
        if getattr(user, "id", None) != user_id:
            _close_client(http_client)
            raise ClerkFlowFailure(ClerkFlowStage.USER)
        try:
            fapi_authority = _primary_development_fapi_authority(clerk)
        except Exception:  # noqa: BLE001 - provider details remain private
            _close_client(http_client)
            raise ClerkFlowFailure(ClerkFlowStage.FAPI_AUTHORITY) from None
        return cls(
            _user_id=user_id,
            _transport=clerk,
            _http_client=http_client,
            _fapi_authority=fapi_authority,
        )

    def create_verified_token(self) -> str:
        """Issue a normal FAPI session token and verify it with the existing verifier."""
        ticket = self._create_ticket()
        ticket_value = _ticket_field(ticket, "token")
        ticket_id = _ticket_field(ticket, "id")
        if isinstance(ticket_id, str) and ticket_id:
            self._ticket_id = ticket_id
            self._ticket_cleanup_uncertain = False
        if not isinstance(ticket_id, str) or not ticket_id:
            raise ClerkFlowFailure(ClerkFlowStage.TICKET)
        if not isinstance(ticket_value, str) or not ticket_value:
            raise ClerkFlowFailure(ClerkFlowStage.TICKET_CREDENTIAL)

        try:
            sign_in, client, dev_browser_id = self._run_frontend_ticket_flow(
                ticket_value
            )
            self._ticket_consumed = True
            session_id = _completed_sign_in_created_session_id(sign_in)
            if session_id is None:
                raise ValueError
            self._session_id = session_id
            if not _is_owned_active_session(client, self._user_id, session_id):
                raise ValueError
            self._session_cleanup_uncertain = False
            token = self._request_session_token(dev_browser_id, session_id)
        except ClerkFlowFailure:
            raise
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TICKET) from None

        self._validate_claims_and_verifier(token)
        return token

    def cleanup(self) -> None:
        """Revoke only resources owned by this run, attempting all applicable work."""
        failed = False
        transport = self._transport
        try:
            if self._session_id is not None:
                try:
                    if transport is None:
                        raise TypeError
                    transport.sessions.revoke(session_id=self._session_id)
                except Exception:  # noqa: BLE001 - cleanup must attempt both resources
                    failed = True
            elif self._session_cleanup_uncertain:
                failed = True
            if self._ticket_id is not None and not self._ticket_consumed:
                try:
                    if transport is None:
                        raise TypeError
                    transport.sign_in_tokens.revoke(sign_in_token_id=self._ticket_id)
                except Exception:  # noqa: BLE001 - cleanup must attempt both resources
                    failed = True
            elif self._ticket_cleanup_uncertain:
                failed = True
            fapi_client = self._fapi_client
            self._fapi_client = None
            if not _close_client(fapi_client):
                failed = True
            http_client = self._http_client
            self._http_client = None
            if not _close_client(http_client):
                failed = True
        finally:
            self._clear_sensitive_state()
        if failed:
            raise ClerkFlowFailure(ClerkFlowStage.CLEANUP)

    def _clear_sensitive_state(self) -> None:
        self._user_id = None  # type: ignore[assignment]
        self._transport = None
        self._http_client = None
        self._fapi_authority = None
        self._fapi_client = None
        self._ticket_id = None
        self._ticket_cleanup_uncertain = False
        self._ticket_consumed = False
        self._session_id = None
        self._session_cleanup_uncertain = False

    def _create_ticket(self) -> object:
        self._ticket_cleanup_uncertain = True
        try:
            return cast(
                object,
                self._transport.sign_in_tokens.create(
                    request=CreateSignInTokenRequestBody(
                        user_id=self._user_id,
                        expires_in_seconds=SIGN_IN_TICKET_LIFETIME_SECONDS,
                    ),
                    retries=RetryConfig(
                        strategy="none",
                        backoff=BackoffStrategy(0, 0, 1, 0),
                        retry_connection_errors=False,
                    ),
                ),
            )
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TICKET) from None

    def _run_frontend_ticket_flow(
        self, ticket: str
    ) -> tuple[dict[str, object], dict[str, object], str]:
        dev_browser = self._frontend_request(
            "/v1/dev_browser",
            failure_stage=ClerkFlowStage.DEVELOPMENT_BROWSER,
            development_browser_diagnostics=True,
        )
        dev_browser_id = _field(dev_browser, "id")
        if not isinstance(dev_browser_id, str) or not dev_browser_id:
            raise ClerkFlowFailure(ClerkFlowStage.DEVELOPMENT_BROWSER_RESPONSE_INVALID)
        self._frontend_request(
            "/v1/client",
            query={"__dev_session": dev_browser_id},
            form={},
            failure_stage=ClerkFlowStage.CLIENT_INITIALIZATION,
        )
        self._session_cleanup_uncertain = True
        client_wrapped_sign_in = self._frontend_request(
            "/v1/client/sign_ins",
            query={"__dev_session": dev_browser_id},
            form={"strategy": "ticket", "ticket": ticket},
            unwrap_response=False,
        )
        sign_in = client_wrapped_sign_in.get("response")
        client = client_wrapped_sign_in.get("client")
        if not isinstance(sign_in, dict) or not isinstance(client, dict):
            raise ClerkFlowFailure(ClerkFlowStage.TICKET)
        return (
            cast(dict[str, object], sign_in),
            cast(dict[str, object], client),
            dev_browser_id,
        )

    def _request_session_token(
        self,
        dev_browser_id: str,
        session_id: str,
    ) -> str:
        try:
            response = self._frontend_request(
                f"/v1/client/sessions/{quote(session_id, safe='')}/tokens",
                query={"__dev_session": dev_browser_id},
                form={},
                failure_stage=ClerkFlowStage.TOKEN,
                unwrap_response=False,
                session_token_diagnostics=True,
            )
            token = _field(response, "jwt")
            if not isinstance(token, str) or not token:
                raise ClerkFlowFailure(ClerkFlowStage.TOKEN_RESPONSE_INVALID)
            return token
        except ClerkFlowFailure:
            raise
        except Exception:  # noqa: BLE001 - third-party errors are intentionally opaque
            raise ClerkFlowFailure(ClerkFlowStage.TOKEN) from None

    def _frontend_request(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        failure_stage: ClerkFlowStage = ClerkFlowStage.TICKET,
        unwrap_response: bool = True,
        development_browser_diagnostics: bool = False,
        session_token_diagnostics: bool = False,
    ) -> dict[str, object]:
        try:
            with _suppress_provider_debug_logs():
                response = self._fapi_http_client().post(
                    path,
                    params=query,
                    data=form,
                    headers=(
                        {"Content-Type": "application/x-www-form-urlencoded"}
                        if form is not None
                        else None
                    ),
                )
        except OSError:
            stage = (
                ClerkFlowStage.DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE
                if development_browser_diagnostics
                else (
                    ClerkFlowStage.TOKEN_TRANSPORT_UNAVAILABLE
                    if session_token_diagnostics
                    else failure_stage
                )
            )
            raise ClerkFlowFailure(stage) from None
        except httpx.DecodingError:
            if session_token_diagnostics:
                raise ClerkFlowFailure(ClerkFlowStage.TOKEN_RESPONSE_INVALID) from None
            raise
        except httpx.InvalidURL:
            if session_token_diagnostics:
                raise ClerkFlowFailure(ClerkFlowStage.TOKEN_REQUEST_INVALID) from None
            raise
        except httpx.TransportError:
            if development_browser_diagnostics:
                raise ClerkFlowFailure(
                    ClerkFlowStage.DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE
                ) from None
            if session_token_diagnostics:
                raise ClerkFlowFailure(
                    ClerkFlowStage.TOKEN_TRANSPORT_UNAVAILABLE
                ) from None
            raise
        except (httpx.RequestError, httpx.StreamError, httpx.CookieConflict):
            if session_token_diagnostics:
                raise ClerkFlowFailure(
                    ClerkFlowStage.TOKEN_TRANSPORT_UNAVAILABLE
                ) from None
            raise
        if response.status_code // 100 != 2:
            if development_browser_diagnostics:
                if response.status_code == 400:
                    stage = ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_INVALID
                elif response.status_code == 401:
                    stage = ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_UNAUTHENTICATED
                elif response.status_code == 403:
                    stage = _development_browser_forbidden_stage(response)
                else:
                    stage = ClerkFlowStage.DEVELOPMENT_BROWSER_REQUEST_REJECTED
                raise ClerkFlowFailure(stage) from None
            if session_token_diagnostics:
                if response.status_code == 400:
                    stage = ClerkFlowStage.TOKEN_REQUEST_INVALID
                elif response.status_code == 401:
                    stage = ClerkFlowStage.TOKEN_REQUEST_UNAUTHENTICATED
                elif response.status_code == 403:
                    stage = ClerkFlowStage.TOKEN_REQUEST_FORBIDDEN
                elif response.status_code == 404:
                    stage = ClerkFlowStage.TOKEN_REQUEST_NOT_FOUND
                else:
                    stage = ClerkFlowStage.TOKEN_REQUEST_REJECTED
                raise ClerkFlowFailure(stage) from None
            raise ClerkFlowFailure(failure_stage) from None
        try:
            payload: object = response.json()
        except (ValueError, json.JSONDecodeError):
            stage = (
                ClerkFlowStage.DEVELOPMENT_BROWSER_RESPONSE_INVALID
                if development_browser_diagnostics
                else (
                    ClerkFlowStage.TOKEN_RESPONSE_INVALID
                    if session_token_diagnostics
                    else failure_stage
                )
            )
            raise ClerkFlowFailure(stage) from None
        if not isinstance(payload, dict):
            stage = (
                ClerkFlowStage.DEVELOPMENT_BROWSER_RESPONSE_INVALID
                if development_browser_diagnostics
                else (
                    ClerkFlowStage.TOKEN_RESPONSE_INVALID
                    if session_token_diagnostics
                    else failure_stage
                )
            )
            raise ClerkFlowFailure(stage)
        response_payload = cast(dict[str, object], payload)
        nested = response_payload.get("response") if unwrap_response else None
        return (
            cast(dict[str, object], nested)
            if isinstance(nested, dict)
            else response_payload
        )

    def _fapi_http_client(self) -> httpx.Client:
        if self._fapi_client is not None:
            return self._fapi_client
        if self._fapi_authority is None:
            raise ClerkFlowFailure(
                ClerkFlowStage.DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE
            )
        try:
            client = _http_client_factory(
                base_url=self._fapi_authority,
                headers={
                    "Clerk-API-Version": _FAPI_API_VERSION,
                    "Origin": TOOLING_ORIGIN,
                    "User-Agent": _FAPI_USER_AGENT,
                    "Accept": _FAPI_ACCEPT,
                },
                trust_env=False,
                follow_redirects=False,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:  # noqa: BLE001 - provider construction details remain private
            raise ClerkFlowFailure(
                ClerkFlowStage.DEVELOPMENT_BROWSER_TRANSPORT_UNAVAILABLE
            ) from None
        self._fapi_client = client
        return client

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

        try:
            request = cast(
                HttpRequest,
                _AuthorizationRequest(headers={"Authorization": f"Bearer {token}"}),
            )
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
    if any(character.isspace() for character in value) or "?" in value or "#" in value:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname
    return (
        parsed.scheme == "https"
        and host is not None
        and parsed.netloc == host
        and host.endswith(_DEVELOPMENT_FAPI_HOST_SUFFIX)
        and host != _DEVELOPMENT_FAPI_HOST_SUFFIX[1:]
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
    )


def _primary_development_fapi_authority(clerk: Any) -> str:
    domains = clerk.domains.list()
    data = cast(object, getattr(domains, "data", None))
    if not isinstance(data, list):
        raise TypeError
    domain_data = cast(list[object], data)
    primaries = [
        domain
        for domain in domain_data
        if getattr(domain, "is_satellite", None) is False
    ]
    if len(primaries) != 1:
        raise ValueError
    authority = getattr(primaries[0], "frontend_api_url", None)
    if not isinstance(authority, str) or not authority:
        raise TypeError
    if not _is_development_fapi_url(authority):
        raise ValueError
    return authority


def _field(payload: dict[str, object], name: str) -> object:
    return payload.get(name)


def _ticket_field(ticket: object, name: str) -> object:
    values = getattr(ticket, "__dict__", None)
    if isinstance(values, dict) and name not in values:
        return None
    return getattr(ticket, name, None)


def _completed_sign_in_created_session_id(sign_in: dict[str, object]) -> str | None:
    created_session_id = sign_in.get("created_session_id")
    if (
        sign_in.get("status") != "complete"
        or not isinstance(created_session_id, str)
        or not created_session_id
    ):
        return None
    return created_session_id


def _is_owned_active_session(
    client: dict[str, object], user_id: str, created_session_id: str
) -> bool:
    sessions = client.get("sessions")
    if not isinstance(sessions, list):
        return False
    for session in cast(list[object], sessions):
        if not isinstance(session, dict):
            continue
        session_data = cast(dict[str, object], session)
        if (
            session_data.get("id") != created_session_id
            or session_data.get("status") != "active"
        ):
            continue
        user = session_data.get("user")
        if not isinstance(user, dict):
            continue
        session_user = cast(dict[str, object], user)
        if session_user.get("id") == user_id:
            return True
    return False


def _close_client(client: httpx.Client | None) -> bool:
    if client is None:
        return True
    try:
        client.close()
    except Exception:  # noqa: BLE001 - cleanup must remain bounded
        return False
    return True


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
