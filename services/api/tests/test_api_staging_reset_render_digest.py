"""The owner's Render reset digest comes only from a strict private file (#410 AC5)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_api_staging_reset_ssh import configuration, write_configuration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def digest_tool() -> Any:
    return cast(Any, importlib.import_module("scripts.api_staging_reset_render_digest"))


def test_digest_tool_prints_only_the_pin_of_a_valid_private_file(
    tmp_path: Path,
) -> None:
    """A direct run prints exactly what the Render loader compares against."""
    binding = importlib.import_module("config.replacement_target_binding")
    path = tmp_path / "operator" / "staging-reset-render.env"
    write_configuration(path, configuration())

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(REPOSITORY_ROOT / "scripts" / "api_staging_reset_render_digest.py"),
            "--config",
            str(path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0
    assert result.stdout == (
        binding.fingerprint_render_reset_configuration(configuration()) + "\n"
    )
    assert result.stderr == ""


def test_digest_tool_names_no_value_when_the_file_is_invalid(
    digest_tool: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file without all nine values fails with one fixed line."""
    path = tmp_path / "operator" / "staging-reset-render.env"
    partial = configuration()
    del partial["TAILTAG_STAGING_RESET_MEDIA_KEY"]
    write_configuration(path, partial)

    assert digest_tool.main(["--config", str(path)]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "FAIL Render reset digest\n"
