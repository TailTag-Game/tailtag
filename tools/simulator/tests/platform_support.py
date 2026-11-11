"""Platform skips shared by simulator tests."""

import sys

import pytest


def skip_on_windows(reason: str) -> pytest.MarkDecorator:
    """Skip one POSIX-only test on native Windows; Linux CI still runs it."""
    return pytest.mark.skipif(sys.platform == "win32", reason=reason)
