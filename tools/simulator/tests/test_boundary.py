"""A-10: the simulator environment must not be able to reach backend internals."""

import importlib.util

import pytest

FORBIDDEN_MODULES = [
    "django",
    "rest_framework",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "sqlalchemy",
    "clerk_backend_api",
]


@pytest.mark.parametrize("module", FORBIDDEN_MODULES)
def test_forbidden_library_is_not_importable(module: str) -> None:
    assert importlib.util.find_spec(module) is None
