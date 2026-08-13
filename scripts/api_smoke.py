"""HTTP smoke checks for an already-running TailTag API."""

from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
SMOKE_PATHS = ("/health/live", "/health/ready", "/api/schema/", "/api/docs/")


class NoRedirectHandler(HTTPRedirectHandler):
    """Treat redirects as failed endpoint responses instead of following them."""

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """Leave the original response status available to the smoke check."""
        return


def valid_base_url(value: str) -> bool:
    """Return whether a base URL is absolute HTTP(S) without reporting its value."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def check_endpoint(base_url: str, path: str) -> bool:
    """Return whether one endpoint responds successfully without exposing its URL."""
    request = Request(f"{base_url.rstrip('/')}{path}", method="GET")
    try:
        with build_opener(NoRedirectHandler).open(request, timeout=5) as response:
            status = response.status
    except HTTPError as error:
        print(
            f"FAIL {path}: expected HTTP 200, received HTTP {error.code}",
            file=sys.stderr,
        )
        return False
    except URLError as error:
        print(
            f"FAIL {path}: unable to reach the running API ({error.reason})",
            file=sys.stderr,
        )
        return False

    if status != 200:
        print(
            f"FAIL {path}: expected HTTP 200, received HTTP {status}", file=sys.stderr
        )
        return False

    print(f"PASS {path}: HTTP 200")
    return True


def main() -> int:
    """Check the required API endpoints using the configured base URL."""
    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)
    if not valid_base_url(base_url):
        print(
            "FAIL API_BASE_URL: an absolute http or https URL is required",
            file=sys.stderr,
        )
        return 1

    failed = False
    for path in SMOKE_PATHS:
        if not check_endpoint(base_url, path):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
