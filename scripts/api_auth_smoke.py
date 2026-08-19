"""Guarded authenticated smoke checks for a local or approved Development API."""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, Self, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .clerk_development_session import (
    ClerkCredentialFailure,
    ClerkDevelopmentSession,
    ClerkFlowFailure,
    _suppress_provider_debug_logs,  # pyright: ignore[reportPrivateUsage]
)

DEFAULT_API_BASE_URL: Final = "http://127.0.0.1:8000"
_API_ME_PATH: Final = "/api/me/"
_REQUEST_TIMEOUT_SECONDS: Final = 10
_BASELINE_TIMEOUT_SECONDS: Final = 30
_BASELINE_ENVIRONMENT_ALLOWLIST: Final = (
    "PATH",
    "SystemRoot",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)
_TARGET_FAILURE: Final = "target configuration invalid"
_BASELINE_FAILURE: Final = "baseline smoke unsuccessful"
_PROMPT_FAILURE: Final = "interactive terminal unavailable"
_VALIDATION_FAILURE: Final = "Clerk instance not validated as Development"
_TOKEN_FAILURE: Final = "provider session-token flow unsuccessful"
_API_FAILURE: Final = "authenticated API response invalid"
_CLEANUP_FAILURE: Final = "cleanup incomplete"


class SmokeFailure(Exception):
    """A closed, bounded orchestration failure."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Leave redirect responses available for strict status validation."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _Opener(Protocol):
    def open(self, request: urllib.request.Request, **kwargs: object) -> _Response: ...


class _Response(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(self, *_args: object) -> None: ...

    def getcode(self) -> int: ...

    def read(self) -> bytes: ...


class SmokeRuntime(Protocol):
    """The three externally observable smoke-operation boundaries."""

    def run_baseline(self, *, base_url: str) -> bool: ...

    def prompt_secret(self) -> str: ...

    def validate_clerk(
        self, *, secret: str, user_id: str
    ) -> ClerkDevelopmentSession: ...

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SmokeOutcome:
    """Only bounded, non-sensitive state is returned to the command boundary."""

    primary_stage: str | None = None
    cleanup_incomplete: bool = False

    @property
    def succeeded(self) -> bool:
        return self.primary_stage is None and not self.cleanup_incomplete


class DefaultSmokeRuntime:
    """Concrete subprocess, prompt, Clerk, and HTTP operations for the command."""

    def __init__(self, *, opener: _Opener | None = None) -> None:
        self._opener = (
            opener
            if opener is not None
            else urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _NoRedirect()
            )
        )

    def run_baseline(self, *, base_url: str) -> bool:
        environment = {
            name: value
            for name in _BASELINE_ENVIRONMENT_ALLOWLIST
            if (value := os.environ.get(name)) is not None
        }
        environment["API_BASE_URL"] = base_url
        try:
            result = subprocess.run(
                [sys.executable, _baseline_script_path()],
                check=False,
                env=environment,
                timeout=_BASELINE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False
        return result.returncode == 0

    def prompt_secret(self) -> str:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise SmokeFailure(_PROMPT_FAILURE)
        return getpass.getpass("Clerk Development secret:", stream=sys.stderr)

    def validate_clerk(self, *, secret: str, user_id: str) -> ClerkDevelopmentSession:
        return ClerkDevelopmentSession.validate(secret=secret, user_id=user_id)

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        url = urlunsplit(urlsplit(base_url)._replace(path=_API_ME_PATH))
        request = urllib.request.Request(
            url,
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
        except Exception:  # noqa: BLE001 - external response details remain private
            raise SmokeFailure(_API_FAILURE) from None
        if type(payload) is not dict:
            raise SmokeFailure(_API_FAILURE)
        body = cast(dict[str, object], payload)
        if set(body) != {"id"} or type(body["id"]) is not int:
            raise SmokeFailure(_API_FAILURE)


def _baseline_script_path() -> str:
    return str(os.path.join(os.path.dirname(__file__), "api_smoke.py"))


def _remove_root_trailing_slash(value: str) -> str:
    return value.removesuffix("/")


def _validate_root_url(value: str) -> str:
    parsed = _root_url_parts(value)
    if parsed.scheme == "http":
        if (
            parsed.netloc != "127.0.0.1:8000"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8000
        ):
            raise SmokeFailure(_TARGET_FAILURE)
    elif parsed.scheme != "https":
        raise SmokeFailure(_TARGET_FAILURE)
    return value


def _validate_https_root_url(value: str) -> str:
    parsed = _root_url_parts(value)
    if parsed.scheme != "https" or parsed.hostname is None:
        raise SmokeFailure(_TARGET_FAILURE)
    return value


def _root_url_parts(value: str) -> SplitResult:
    if not value or any(character.isspace() for character in value) or "\\" in value:
        raise SmokeFailure(_TARGET_FAILURE)
    raw_scheme, separator, _remainder = value.partition(":")
    if separator != ":" or raw_scheme not in {"http", "https"}:
        raise SmokeFailure(_TARGET_FAILURE)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise SmokeFailure(_TARGET_FAILURE) from None
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or value.endswith(("?", "#"))
        or "%" in parsed.netloc
        or parsed.netloc.endswith(":")
        or (port is None and parsed.scheme == "http")
    ):
        raise SmokeFailure(_TARGET_FAILURE)
    return parsed


def validate_api_target(environment: Mapping[str, str]) -> str:
    """Return the one allowed local target or exact configured Development target."""
    configured = environment.get("API_BASE_URL")
    if configured is None:
        target = DEFAULT_API_BASE_URL
    elif configured == "":
        raise SmokeFailure(_TARGET_FAILURE)
    else:
        target = _validate_root_url(configured)

    target = _remove_root_trailing_slash(target)
    development = environment.get("TAILTAG_DEVELOPMENT_API_BASE_URL")
    validated_development = (
        _validate_https_root_url(development) if development is not None else None
    )
    if target != DEFAULT_API_BASE_URL and (
        validated_development is None
        or target != _remove_root_trailing_slash(validated_development)
    ):
        raise SmokeFailure(_TARGET_FAILURE)
    return target


def _stage_for(error: BaseException, fallback: str) -> str:
    if isinstance(error, (SmokeFailure, ClerkFlowFailure)):
        return error.stage.value if isinstance(error, ClerkFlowFailure) else error.stage
    if isinstance(error, ClerkCredentialFailure):
        return str(error)
    return fallback


def _discard_error_details(error: BaseException) -> None:
    """Remove untrusted strings before a caller could accidentally render them."""
    try:
        error.args = ()
    except Exception:  # noqa: BLE001 - not every third-party exception is mutable
        return


def run(environment: Mapping[str, str], runtime: SmokeRuntime) -> SmokeOutcome:
    """Run the ordered credential-free baseline and ephemeral authenticated check."""
    try:
        base_url = validate_api_target(environment)
    except Exception:  # noqa: BLE001 - malformed input remains private
        return SmokeOutcome(primary_stage=_TARGET_FAILURE)

    try:
        if not runtime.run_baseline(base_url=base_url):
            return SmokeOutcome(primary_stage=_BASELINE_FAILURE)
    except Exception as error:  # noqa: BLE001 - subprocess failures remain private
        _discard_error_details(error)
        return SmokeOutcome(primary_stage=_BASELINE_FAILURE)

    try:
        secret: str | None = runtime.prompt_secret()
    except Exception as error:  # noqa: BLE001 - terminal details remain private
        _discard_error_details(error)
        return SmokeOutcome(primary_stage=_PROMPT_FAILURE)

    user_id = environment.get("CLERK_SMOKE_USER_ID", "")
    with _suppress_provider_debug_logs():
        try:
            try:
                session = runtime.validate_clerk(secret=secret, user_id=user_id)
            except Exception as error:  # noqa: BLE001 - provider details remain private
                stage = _stage_for(error, _VALIDATION_FAILURE)
                _discard_error_details(error)
                return SmokeOutcome(primary_stage=stage)
            finally:
                secret = None

            primary_stage: str | None = None
            cleanup_incomplete = False
            token: str | None = None
            try:
                try:
                    token = session.create_verified_token()
                except Exception as error:  # noqa: BLE001 - token details remain private
                    primary_stage = _stage_for(error, _TOKEN_FAILURE)
                    _discard_error_details(error)
                else:
                    try:
                        runtime.request_current_user(
                            base_url=base_url, bearer_token=token
                        )
                    except Exception as error:  # noqa: BLE001 - API details remain private
                        primary_stage = _stage_for(error, _API_FAILURE)
                        _discard_error_details(error)
            finally:
                token = None
                try:
                    session.cleanup()
                except Exception as error:  # noqa: BLE001 - cleanup details remain private
                    _discard_error_details(error)
                    cleanup_incomplete = True
            return SmokeOutcome(
                primary_stage=primary_stage,
                cleanup_incomplete=cleanup_incomplete,
            )
        finally:
            secret = None


def main() -> int:
    """Run the non-configurable command entry point without accepting CLI secrets."""
    if len(sys.argv) != 1:
        print("FAIL authenticated API smoke arguments invalid", file=sys.stderr)
        return 1

    try:
        outcome = run(os.environ, DefaultSmokeRuntime())
    except SmokeFailure as error:
        outcome = SmokeOutcome(primary_stage=error.stage)
    if outcome.succeeded:
        print("PASS authenticated API smoke")
        return 0
    if outcome.primary_stage is not None:
        print(f"FAIL {outcome.primary_stage}", file=sys.stderr)
    if outcome.cleanup_incomplete:
        print(f"FAIL {_CLEANUP_FAILURE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
