"""Child-process environments and platform skips shared by subprocess tests."""

from __future__ import annotations

import os
import sys

import pytest


def minimal_environment() -> dict[str, str]:
    """Return the smallest environment a child Python can start with.

    Tests pass only PATH so settings cannot read the caller's configuration.
    Windows also needs SYSTEMROOT, or the child cannot initialize sockets
    (WinError 10106). It is OS plumbing, not application configuration.
    """
    environment = {"PATH": os.environ.get("PATH", "")}
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return environment


def skip_on_windows(reason: str) -> pytest.MarkDecorator:
    """Skip one POSIX-only test on native Windows; Linux CI still runs it."""
    return pytest.mark.skipif(sys.platform == "win32", reason=reason)
