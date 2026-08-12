#!/usr/bin/env python3
"""HTTP smoke checks for an already-running TailTag API."""

from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
SMOKE_PATHS = ("/health/live", "/health/ready", "/api/schema/", "/api/docs/")


def check_endpoint(base_url: str, path: str) -> bool:
    """Return whether one endpoint responds successfully without exposing its URL."""
    request = Request(f"{base_url.rstrip('/')}{path}", method="GET")
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310
            status = response.status
    except HTTPError as error:
        print(f"FAIL {path}: expected HTTP 200, received HTTP {error.code}", file=sys.stderr)
        return False
    except URLError as error:
        print(f"FAIL {path}: unable to reach the running API ({error.reason})", file=sys.stderr)
        return False

    if status != 200:
        print(f"FAIL {path}: expected HTTP 200, received HTTP {status}", file=sys.stderr)
        return False

    print(f"PASS {path}: HTTP 200")
    return True


def main() -> int:
    """Check the required API endpoints using the configured base URL."""
    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)
    if not base_url:
        print("FAIL API_BASE_URL: a non-empty URL is required", file=sys.stderr)
        return 1

    for path in SMOKE_PATHS:
        if not check_endpoint(base_url, path):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
