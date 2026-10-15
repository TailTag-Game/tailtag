"""The two Python projects vendor the same standard-library modules (S3-9)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API = REPOSITORY_ROOT / "services" / "api" / "config"
SIMULATOR = REPOSITORY_ROOT / "tools" / "simulator" / "tailtag_simulator"


@pytest.mark.parametrize("module", ("owner_only", "process_tree"))
def test_vendored_copies_are_byte_identical(module: str) -> None:
    """S3-9: a fix applied to one copy of a security-relevant module cannot drift."""
    api_copy = (API / f"{module}.py").read_bytes()
    simulator_copy = (SIMULATOR / f"{module}.py").read_bytes()

    assert api_copy == simulator_copy
