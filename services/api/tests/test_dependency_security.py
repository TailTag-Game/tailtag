"""Security patch-level requirements for locked runtime dependencies."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.version import Version

_API_DIRECTORY = Path(__file__).parents[1]


def test_locked_runtime_dependencies_meet_security_patch_floors() -> None:
    """Keep declared and resolved security-sensitive dependencies patched."""
    project = tomllib.loads((_API_DIRECTORY / "pyproject.toml").read_text())
    lock = tomllib.loads((_API_DIRECTORY / "uv.lock").read_text())
    dependencies = project["project"]["dependencies"]
    versions = {
        package["name"]: Version(package["version"]) for package in lock["package"]
    }

    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert "Django>=6.0,<6.1" in dependencies
    assert "clerk-backend-api==7.0.0" in dependencies
    assert "cryptography>=50.0.0,<51" in dependencies
    assert versions["clerk-backend-api"] == Version("7.0.0")
    assert versions["django"] >= Version("6.0")
    assert versions["django"] < Version("6.1")
    assert versions["cryptography"] >= Version("50.0.0")
    assert versions["sqlparse"] >= Version("0.6.0")
