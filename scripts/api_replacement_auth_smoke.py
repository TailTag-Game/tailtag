"""Bounded candidate API authentication check with interactive Clerk session tokens."""

from __future__ import annotations

import getpass
import json
import sys
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from scripts import api_staging_preflight

_API_PATH = "/api/me/"
_MAX_BODY = 4096


class SmokeFailure(Exception):
    """A failure whose detail must never be derived from an external response."""


@dataclass(frozen=True)
class SmokeOutcome:
    succeeded: bool
    failure_stage: str | None = None


class SmokeRuntime(Protocol):
    def load_origins(self) -> dict[str, str]: ...

    def preflight(self, *, environment: str, origin: str) -> dict[str, str]: ...

    def prompt_token(self, *, environment: str) -> str: ...

    def request_me(self, *, origin: str, token: str) -> tuple[int, bytes, str]: ...


class DefaultSmokeRuntime:
    """Use the code-pinned candidate targets and direct, bounded HTTP requests."""

    def load_origins(self) -> dict[str, str]:
        api_directory = Path(__file__).resolve().parents[1] / "services/api"
        if str(api_directory) not in sys.path:
            sys.path.insert(0, str(api_directory))
        from config import replacement_target_binding

        return {
            "development": replacement_target_binding.load_development_candidate_origin(),
            "staging": replacement_target_binding.load_candidate_origin(),
        }

    def preflight(self, *, environment: str, origin: str) -> dict[str, str]:
        first = api_staging_preflight._validate_identity(
            api_staging_preflight._fetch_json(f"{origin}/health/identity"),
            expected_environment=environment,
        )
        if api_staging_preflight._fetch_json(f"{origin}/health/ready") != {
            "status": "ok"
        }:
            raise SmokeFailure
        second = api_staging_preflight._validate_identity(
            api_staging_preflight._fetch_json(f"{origin}/health/identity"),
            expected_environment=environment,
        )
        if second != first:
            raise SmokeFailure
        return dict(first)

    def prompt_token(self, *, environment: str) -> str:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise SmokeFailure
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass(
                f"{environment.capitalize()} ordinary Clerk session token: ",
                stream=sys.stderr,
            )
        if not token or token != token.strip():
            raise SmokeFailure
        return token

    def request_me(self, *, origin: str, token: str) -> tuple[int, bytes, str]:
        url = f"{origin}{_API_PATH}"
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}, method="GET"
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), api_staging_preflight._NoRedirect()
        )
        try:
            with opener.open(request, timeout=5) as response:
                return (
                    response.getcode(),
                    response.read(_MAX_BODY + 1),
                    response.geturl(),
                )
        except urllib.error.HTTPError as error:
            try:
                return error.code, error.read(_MAX_BODY + 1), error.geturl()
            finally:
                error.close()


def _valid_origin(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.netloc == parsed.hostname
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and value == f"https://{parsed.hostname}"
    )


def _valid_identity(value: object, environment: str) -> bool:
    try:
        api_staging_preflight._validate_identity(
            value, expected_environment=environment
        )
    except Exception:  # noqa: BLE001 - keep external identity details private
        return False
    return True


def _own_response(result: tuple[int, bytes, str], origin: str) -> bool:
    status, body, final_url = result
    if status != 200 or final_url != f"{origin}{_API_PATH}" or len(body) > _MAX_BODY:
        return False
    try:
        parsed = json.loads(
            body, object_pairs_hook=api_staging_preflight._reject_duplicate_keys
        )
    except (ValueError, UnicodeError, RecursionError):
        return False
    return type(parsed) is dict and set(parsed) == {"id"} and type(parsed["id"]) is int


def _cross_response(result: tuple[int, bytes, str], origin: str) -> bool:
    status, body, final_url = result
    return (
        status == 401 and final_url == f"{origin}{_API_PATH}" and len(body) <= _MAX_BODY
    )


def run(runtime: SmokeRuntime) -> SmokeOutcome:
    """Fail closed, with only fixed stage labels exposed to callers."""
    try:
        origins = runtime.load_origins()
        if (
            type(origins) is not dict
            or set(origins) != {"development", "staging"}
            or not all(_valid_origin(origin) for origin in origins.values())
            or origins["development"] == origins["staging"]
        ):
            raise SmokeFailure
        for environment in ("development", "staging"):
            if not _valid_identity(
                runtime.preflight(environment=environment, origin=origins[environment]),
                environment,
            ):
                raise SmokeFailure
    except Exception:  # noqa: BLE001 - keep target/configuration details private
        return SmokeOutcome(False, "target")

    for source, target in (
        ("development", "staging"),
        ("staging", "development"),
    ):
        try:
            token = runtime.prompt_token(environment=source)
            if not isinstance(token, str) or not token:
                raise SmokeFailure
        except Exception:  # noqa: BLE001 - keep hidden input details private
            return SmokeOutcome(False, "hidden input")
        try:
            own = runtime.request_me(origin=origins[source], token=token)
            if not _own_response(own, origins[source]):
                raise SmokeFailure
            cross = runtime.request_me(origin=origins[target], token=token)
            if not _cross_response(cross, origins[target]):
                raise SmokeFailure
        except Exception:  # noqa: BLE001 - keep external response details private
            return SmokeOutcome(False, "authenticated API")
        finally:
            del token
    return SmokeOutcome(True)


def main() -> int:
    outcome = run(DefaultSmokeRuntime())
    if outcome.succeeded:
        print("PASS replacement candidate authentication")
        return 0
    print(
        f"FAIL replacement candidate authentication: {outcome.failure_stage}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
