"""Guarded live verification of the private Development media bucket."""

from __future__ import annotations

import os
import re
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final, Protocol, Self
from urllib.parse import urlsplit

import django
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from PIL import Image

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_API_DIRECTORY = _REPOSITORY_ROOT / "services" / "api"
if str(_API_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_API_DIRECTORY))

from media.images import normalize_image
from media.keys import create_image_key
from media.storage import S3MediaStorage

_EXPECTED_ENVIRONMENT: Final = "development"
_EXPECTED_SERVICE: Final = "api"
_CONFIRMATION_VALUE: Final = "run-r2-development-media-storage-smoke"
_PRESIGN_EXPIRY_SECONDS: Final = 600
_FETCH_TIMEOUT_SECONDS: Final = 10
_DNS_HOST_PATTERN: Final = re.compile(
    r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z"
)


class SmokeFailure(Exception):
    """A bounded failure whose stage is safe to display."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward bearer URLs to a redirect destination."""

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
    """The live boundary, replaceable by deterministic test fakes."""

    def create_key(self) -> str: ...

    def canonical_content(self) -> bytes: ...

    def upload(self, *, key: str, content: bytes) -> None: ...

    def exists(self, *, key: str) -> bool: ...

    def presign_get(self, *, key: str, expires_in: int) -> str: ...

    def fetch(self, *, url: str) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SmokeOutcome:
    """Only fixed, sanitized operation state crosses the command boundary."""

    primary_stage: str | None = None
    cleanup_stage: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.primary_stage is None and self.cleanup_stage is None


class DefaultSmokeRuntime:
    """Use Django's configured production S3 storage for the real operation."""

    def __init__(self, *, opener: _Opener | None = None) -> None:
        storage = storages["default"]
        if not isinstance(storage, S3MediaStorage):
            raise SmokeFailure("storage runtime")
        self._storage = storage
        self._opener = (
            opener
            if opener is not None
            else urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _NoRedirect()
            )
        )

    def create_key(self) -> str:
        return create_image_key("png")

    def canonical_content(self) -> bytes:
        source = BytesIO()
        Image.new("RGB", (1, 1), color=(0, 0, 0)).save(source, format="PNG")
        normalized = normalize_image(File(BytesIO(source.getvalue()), name="smoke.png"))
        return normalized.content

    def upload(self, *, key: str, content: bytes) -> None:
        self._storage.save(key, ContentFile(content, name=key))

    def exists(self, *, key: str) -> bool:
        return self._storage.exists(key)

    def presign_get(self, *, key: str, expires_in: int) -> str:
        if expires_in != _PRESIGN_EXPIRY_SECONDS:
            raise SmokeFailure("presigned GET bytes")
        return self._storage.url(key)

    def fetch(self, *, url: str) -> bytes:
        try:
            parsed_url = urlsplit(url)
            hostname = parsed_url.hostname
            if (
                parsed_url.scheme != "https"
                or hostname is None
                or _DNS_HOST_PATTERN.fullmatch(hostname) is None
            ):
                raise SmokeFailure("presigned GET bytes")
            _ = parsed_url.port
        except SmokeFailure:
            raise
        except ValueError as error:
            raise SmokeFailure("presigned GET bytes") from error

        request = urllib.request.Request(  # noqa: S310, RUF100 - URL is constrained to HTTPS.
            url, method="GET"
        )
        try:
            with self._opener.open(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
                if response.getcode() != 200:
                    raise SmokeFailure("presigned GET bytes")
                return response.read()
        except SmokeFailure:
            raise
        except Exception as error:
            raise SmokeFailure("presigned GET bytes") from error

    def delete(self, *, key: str) -> None:
        self._storage.delete(key)


def valid_target(environment: Mapping[str, str]) -> bool:
    """Require the exact, non-interactive Railway Development target."""
    return (
        environment.get("RAILWAY_ENVIRONMENT_NAME") == _EXPECTED_ENVIRONMENT
        and environment.get("RAILWAY_SERVICE_NAME") == _EXPECTED_SERVICE
        and environment.get("TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM")
        == _CONFIRMATION_VALUE
    )


def run(environment: Mapping[str, str], runtime: SmokeRuntime) -> SmokeOutcome:
    """Run the bounded storage sequence and mandatory delete/absence cleanup."""
    if not valid_target(environment):
        return SmokeOutcome(primary_stage="target configuration invalid")

    key: str | None = None
    primary_stage: str | None = None
    try:
        key = runtime.create_key()
    except Exception:  # noqa: BLE001 - synthetic preparation failures are sanitized.
        primary_stage = "prepare synthetic image"
    else:
        try:
            content = runtime.canonical_content()
        except Exception:  # noqa: BLE001 - synthetic preparation failures are sanitized.
            primary_stage = "prepare synthetic image"
        else:
            try:
                runtime.upload(key=key, content=content)
            except Exception:  # noqa: BLE001 - external storage failures are sanitized.
                primary_stage = "upload"
            else:
                try:
                    present = runtime.exists(key=key)
                except Exception:  # noqa: BLE001 - external storage failures are sanitized.
                    primary_stage = "object exists"
                else:
                    if not present:
                        primary_stage = "object exists"
                    else:
                        try:
                            url = runtime.presign_get(
                                key=key, expires_in=_PRESIGN_EXPIRY_SECONDS
                            )
                            fetched = runtime.fetch(url=url)
                            if fetched != content:
                                primary_stage = "presigned GET bytes"
                        except Exception:  # noqa: BLE001 - external storage failures are sanitized.
                            primary_stage = "presigned GET bytes"
    finally:
        cleanup_stage: str | None = None
        if key is not None:
            try:
                runtime.delete(key=key)
            except Exception:  # noqa: BLE001 - cleanup failures are sanitized.
                cleanup_stage = "delete"
            try:
                if runtime.exists(key=key):
                    cleanup_stage = cleanup_stage or "object absent"
            except Exception:  # noqa: BLE001 - cleanup failures are sanitized.
                cleanup_stage = cleanup_stage or "object absent"
        else:
            cleanup_stage = None

    return SmokeOutcome(primary_stage=primary_stage, cleanup_stage=cleanup_stage)


def _print_failure(stage: str) -> None:
    print(f"FAIL {stage}", file=sys.stderr)


def main() -> int:
    """Run the explicit command without accepting unsafe CLI configuration."""
    if len(sys.argv) != 1:
        _print_failure("media storage smoke arguments invalid")
        return 1
    if not valid_target(os.environ):
        _print_failure("target configuration invalid")
        return 1

    try:
        django.setup()
        runtime = DefaultSmokeRuntime()
    except Exception:  # noqa: BLE001 - initialization failures are sanitized.
        _print_failure("storage runtime")
        _print_failure("media storage smoke")
        return 1

    outcome = run(os.environ, runtime)
    if not outcome.succeeded:
        if outcome.primary_stage is not None:
            _print_failure(outcome.primary_stage)
        if outcome.cleanup_stage is not None:
            _print_failure(outcome.cleanup_stage)
        _print_failure("media storage smoke")
        return 1

    for stage in (
        "target development/api",
        "upload",
        "object exists",
        "presigned GET bytes",
        "delete",
        "object absent",
        "media storage smoke",
    ):
        print(f"PASS {stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
