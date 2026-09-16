"""Guarded bootstrap-only authentication smoke check for TailTag Staging."""
# ruff: noqa: BLE001, S110

from __future__ import annotations

import asyncio
import base64
import getpass
import hashlib
import json
import os as _stdlib_os
import subprocess
import sys
import time
import urllib.request
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Final, Protocol, Self, cast

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.types import UNSET
from clerk_backend_api.utils import BackoffStrategy, RetryConfig
from django.http import HttpRequest
from scripts.clerk_development_session import (
    _suppress_provider_debug_logs,  # pyright: ignore[reportPrivateUsage]
)

from authentication.clerk import ClerkSessionVerifier, ClerkVerificationConfiguration

os = SimpleNamespace(environ=_stdlib_os.environ, path=_stdlib_os.path)

STAGING_CLERK_INSTANCE_FINGERPRINT: Final = "eb6daf25d12b85eb"
STAGING_CLERK_PORTAL_ORIGIN: Final = "https://accounts.staging.tailtag.app"
# Clerk documents ordinary session tokens as short-lived (60 seconds):
# https://clerk.com/docs/guides/development/testing/postman-or-insomnia
# Smoke/provider safety bound; not a TailTag application auth contract.
MAX_PROVIDER_SESSION_TOKEN_LIFETIME_SECONDS = 60

_STAGING_URL: Final = "https://staging.tailtag.app"
_CONFIRMATION: Final = "run-clerk-staging-auth-smoke"
_API_ME_PATH: Final = "/api/me/"
_REQUEST_TIMEOUT_SECONDS: Final = 10
_BASELINE_TIMEOUT_SECONDS: Final = 30
_PROVIDER_TIMEOUT_MILLISECONDS: Final = 10_000
_TARGET_FAILURE: Final = "target staging/api"
_BASELINE_FAILURE: Final = "baseline API smoke"
_PROMPT_FAILURE: Final = "hidden input"
_INSTANCE_FAILURE: Final = "Clerk Production instance"
_USER_FAILURE: Final = "synthetic user"
_SELECTION_FAILURE: Final = "smoke-only session"
_TOKEN_FAILURE: Final = "session token"
_API_FAILURE: Final = "authenticated API"
_CLEANUP_FAILURE: Final = "cleanup"


class SmokeFailure(Exception):
    """A fixed, safe failure stage for this operator command."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _Response(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, *_args: object) -> None: ...
    def getcode(self) -> int: ...
    def read(self) -> bytes: ...


class _Opener(Protocol):
    def open(self, request: urllib.request.Request, **kwargs: object) -> _Response: ...


class SmokeRuntime(Protocol):
    def run_baseline(self, *, base_url: str) -> bool: ...
    def prompt_secret(self) -> str: ...
    def validate_production_instance(self, *, secret: str) -> None: ...
    def validate_synthetic_user(self, *, secret: str, user_id: str) -> None: ...
    def prompt_session_id(self) -> str: ...
    def get_selected_session(
        self, *, secret: str, session_id: str, user_id: str
    ) -> None: ...
    def prompt_session_token(self) -> str: ...
    def verify_session_token(
        self, *, token: str, session_id: str, user_id: str
    ) -> None: ...
    def request_current_user(self, *, base_url: str, bearer_token: str) -> None: ...
    def revoke_selected_session(self, *, secret: str, session_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SmokeOutcome:
    primary_stage: str | None = None
    cleanup_failed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.primary_stage is None and not self.cleanup_failed


def _no_retries() -> RetryConfig:
    return RetryConfig("none", BackoffStrategy(0, 0, 1.0, 0), False)


class DefaultSmokeRuntime:
    """Concrete Clerk and no-redirect HTTP boundaries for the opt-in command."""

    def __init__(
        self,
        *,
        clerk_factory: Callable[[str], Any] | None = None,
        verifier: ClerkSessionVerifier | None = None,
        opener: _Opener | None = None,
    ) -> None:
        self._http_client: httpx.Client | None = None
        self._async_http_client: httpx.AsyncClient | None = None
        self._clerk: Any | None = None
        self._clerk_factory = clerk_factory or self._create_clerk
        self._verifier = verifier
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def _create_clerk(self, secret: str) -> Clerk:
        self._http_client = httpx.Client(trust_env=False, follow_redirects=False)
        self._async_http_client = httpx.AsyncClient(
            trust_env=False, follow_redirects=False
        )
        return Clerk(
            bearer_auth=secret,
            client=self._http_client,
            async_client=self._async_http_client,
            retry_config=_no_retries(),
            timeout_ms=_PROVIDER_TIMEOUT_MILLISECONDS,
        )

    def _provider(self, secret: str) -> Any:
        if self._clerk is None:
            self._clerk = self._clerk_factory(secret)
        return self._clerk

    def run_baseline(self, *, base_url: str) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, _baseline_script_path()],
                check=False,
                capture_output=True,
                text=True,
                env={"API_BASE_URL": base_url},
                timeout=_BASELINE_TIMEOUT_SECONDS,
            )
        except Exception:
            return False
        return result.returncode == 0

    @staticmethod
    def _hidden_prompt(label: str) -> str:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise SmokeFailure(_PROMPT_FAILURE)
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                return getpass.getpass(label, stream=sys.stderr)
            except getpass.GetPassWarning:
                raise SmokeFailure(_PROMPT_FAILURE) from None

    def prompt_secret(self) -> str:
        return self._hidden_prompt("Clerk Staging Production secret:")

    def prompt_session_id(self) -> str:
        return self._hidden_prompt("Clerk Staging smoke-only session ID:")

    def prompt_session_token(self) -> str:
        return self._hidden_prompt("Clerk Staging session token:")

    def validate_production_instance(self, *, secret: str) -> None:
        try:
            instance = self._provider(secret).instance_settings.get()
            instance_id = getattr(instance, "id", None)
        except Exception:
            raise SmokeFailure(_INSTANCE_FAILURE) from None
        if (
            getattr(instance, "environment_type", None) != "production"
            or not isinstance(instance_id, str)
            or hashlib.sha256(instance_id.encode()).hexdigest()[:16]
            != STAGING_CLERK_INSTANCE_FINGERPRINT
        ):
            raise SmokeFailure(_INSTANCE_FAILURE)

    def validate_synthetic_user(self, *, secret: str, user_id: str) -> None:
        try:
            user = self._provider(secret).users.get(user_id=user_id)
        except Exception:
            raise SmokeFailure(_USER_FAILURE) from None
        metadata = cast(object, getattr(user, "public_metadata", None))
        if (
            getattr(user, "id", None) != user_id
            or not isinstance(metadata, Mapping)
            or cast(Mapping[str, object], metadata).get("tailtag_environment")
            != "staging"
            or cast(Mapping[str, object], metadata).get("tailtag_synthetic") is not True
        ):
            raise SmokeFailure(_USER_FAILURE)

    def get_selected_session(
        self, *, secret: str, session_id: str, user_id: str
    ) -> None:
        try:
            session = self._provider(secret).sessions.get(session_id=session_id)
        except Exception:
            raise SmokeFailure(_SELECTION_FAILURE) from None
        actor = getattr(session, "actor", object())
        if (
            getattr(session, "id", None) != session_id
            or getattr(session, "user_id", None) != user_id
            or getattr(session, "status", None) != "active"
            or (actor is not None and type(actor) is not type(UNSET))
        ):
            raise SmokeFailure(_SELECTION_FAILURE)

    def verify_session_token(
        self, *, token: str, session_id: str, user_id: str
    ) -> None:
        try:
            verifier = self._verifier or _staging_verifier()
            request = HttpRequest()
            request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
            identity = verifier.verify(request)
            if identity is None or identity.subject != user_id:
                raise ValueError
            claims = _genuine_claims(token)
            iat, exp = claims.get("iat"), claims.get("exp")
            if (
                claims.get("sid") != session_id
                or claims.get("sub") != user_id
                or claims.get("azp") != STAGING_CLERK_PORTAL_ORIGIN
                or type(iat) is not int
                or type(exp) is not int
                or exp <= iat
                or exp <= int(time.time())
                or exp - iat > MAX_PROVIDER_SESSION_TOKEN_LIFETIME_SECONDS
            ):
                raise ValueError
        except Exception:
            raise SmokeFailure(_TOKEN_FAILURE) from None

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        request = urllib.request.Request(
            f"{base_url}{_API_ME_PATH}",
            headers={"Authorization": f"Bearer {bearer_token}"},
            method="GET",
        )
        try:
            with self._opener.open(
                request, timeout=_REQUEST_TIMEOUT_SECONDS
            ) as response:
                if response.getcode() != 200:
                    raise ValueError
                payload: object = json.loads(response.read().decode("utf-8"))
            if type(payload) is not dict:
                raise ValueError
            body = cast(dict[str, object], payload)
            if set(body) != {"id"} or type(body["id"]) is not int:
                raise ValueError
        except Exception:
            raise SmokeFailure(_API_FAILURE) from None

    def revoke_selected_session(self, *, secret: str, session_id: str) -> None:
        try:
            session = self._provider(secret).sessions.revoke(session_id=session_id)
        except Exception:
            raise SmokeFailure(_CLEANUP_FAILURE) from None
        if (
            getattr(session, "id", None) != session_id
            or getattr(session, "status", None) != "revoked"
        ):
            raise SmokeFailure(_CLEANUP_FAILURE)

    def close(self) -> None:
        self._clerk = None
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None
        if self._async_http_client is not None:
            try:
                asyncio.run(self._async_http_client.aclose())
            except Exception:
                pass
            self._async_http_client = None


def _baseline_script_path() -> str:
    return os.path.join(os.path.dirname(__file__), "api_smoke.py")


def _genuine_claims(token: str) -> dict[str, object]:
    _header, encoded_claims, _signature = token.split(".")
    padded = encoded_claims + "=" * (-len(encoded_claims) % 4)
    claims: object = json.loads(base64.urlsafe_b64decode(padded))
    if not isinstance(claims, dict):
        raise TypeError
    return cast(dict[str, object], claims)


def _staging_verifier() -> ClerkSessionVerifier:
    jwt_key = os.environ.get("CLERK_JWT_KEY", "")
    parties = tuple(
        value.strip()
        for value in os.environ.get("CLERK_AUTHORIZED_PARTIES", "").split(",")
        if value.strip()
    )
    if not jwt_key or parties != (STAGING_CLERK_PORTAL_ORIGIN,):
        raise SmokeFailure(_TOKEN_FAILURE)
    return ClerkSessionVerifier(
        ClerkVerificationConfiguration(jwt_key=jwt_key, authorized_parties=parties)
    )


def _valid_target(environment: Mapping[str, str]) -> tuple[str, str] | None:
    user_id = environment.get("CLERK_STAGING_SMOKE_USER_ID", "")
    if (
        environment.get("RAILWAY_ENVIRONMENT_NAME") != "staging"
        or environment.get("RAILWAY_SERVICE_NAME") != "api"
        or environment.get("TAILTAG_STAGING_AUTH_SMOKE_CONFIRM") != _CONFIRMATION
        or environment.get("API_BASE_URL") != _STAGING_URL
        or environment.get("TAILTAG_STAGING_API_BASE_URL") != _STAGING_URL
        or not user_id
    ):
        return None
    return _STAGING_URL, user_id


def _close_runtime(runtime: SmokeRuntime) -> None:
    close = getattr(runtime, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def run(environment: Mapping[str, str], runtime: SmokeRuntime) -> SmokeOutcome:
    """Run selected-session validation and revocation without alternate provider flows."""
    target = _valid_target(environment)
    if target is None:
        return SmokeOutcome(primary_stage=_TARGET_FAILURE)
    base_url, user_id = target
    target = None
    try:
        if not runtime.run_baseline(base_url=base_url):
            return SmokeOutcome(primary_stage=_BASELINE_FAILURE)
    except BaseException:
        return SmokeOutcome(primary_stage=_BASELINE_FAILURE)
    try:
        secret: str | None = runtime.prompt_secret()
    except BaseException:
        return SmokeOutcome(primary_stage=_PROMPT_FAILURE)
    if not secret.startswith("sk_live_") or secret == "sk_live_":
        return SmokeOutcome(primary_stage=_PROMPT_FAILURE)

    session_id: str | None = None
    token: str | None = None
    selected = False
    primary_stage: str | None = None
    cleanup_failed = False
    with _suppress_provider_debug_logs():
        try:
            try:
                runtime.validate_production_instance(secret=secret)
            except BaseException:
                primary_stage = _INSTANCE_FAILURE
            if primary_stage is None:
                try:
                    runtime.validate_synthetic_user(secret=secret, user_id=user_id)
                except BaseException:
                    primary_stage = _USER_FAILURE
            if primary_stage is None:
                try:
                    session_id = runtime.prompt_session_id()
                    if not session_id:
                        raise ValueError
                    runtime.get_selected_session(
                        secret=secret, session_id=session_id, user_id=user_id
                    )
                    selected = True
                except BaseException:
                    primary_stage = _SELECTION_FAILURE
            if primary_stage is None:
                try:
                    assert session_id is not None
                    token = runtime.prompt_session_token()
                    runtime.verify_session_token(
                        token=token, session_id=session_id, user_id=user_id
                    )
                except BaseException:
                    primary_stage = _TOKEN_FAILURE
                finally:
                    user_id = ""
            if primary_stage is None:
                try:
                    assert token is not None
                    runtime.request_current_user(base_url=base_url, bearer_token=token)
                except BaseException:
                    primary_stage = _API_FAILURE
        finally:
            token = None
            if selected and session_id is not None:
                try:
                    runtime.revoke_selected_session(
                        secret=secret, session_id=session_id
                    )
                except BaseException:
                    cleanup_failed = True
            session_id = None
            secret = None
            user_id = ""
            _close_runtime(runtime)
    return SmokeOutcome(primary_stage=primary_stage, cleanup_failed=cleanup_failed)


def main() -> int:
    if len(sys.argv) != 1:
        print("FAIL target staging/api", file=sys.stderr)
        return 1
    try:
        outcome = run(os.environ, DefaultSmokeRuntime())
    except BaseException:
        outcome = SmokeOutcome(primary_stage=_TARGET_FAILURE)
    if outcome.succeeded:
        for stage in (
            "target staging/api",
            "baseline API smoke",
            "Clerk Production instance",
            "synthetic user",
            "session token",
            "authenticated API",
            "cleanup",
            "Staging authenticated API smoke",
        ):
            print(f"PASS {stage}")
        return 0
    print(
        f"FAIL {_CLEANUP_FAILURE if outcome.cleanup_failed else outcome.primary_stage}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
