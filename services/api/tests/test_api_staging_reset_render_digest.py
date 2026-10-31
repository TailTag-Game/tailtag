"""The owner's Render reset digest comes only from a strict private file (#410 AC5)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_api_staging_reset_ssh import configuration, write_configuration


@pytest.fixture
def digest_tool() -> Any:
    return cast(Any, importlib.import_module("scripts.api_staging_reset_render_digest"))


def test_digest_tool_prints_only_the_pin_of_a_valid_private_file(
    digest_tool: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The printed digest is exactly what the Render loader compares against."""
    binding = importlib.import_module("config.replacement_target_binding")
    path = tmp_path / "operator" / "staging-reset-render.env"
    write_configuration(path, configuration())

    assert digest_tool.main(["--config", str(path)]) == 0

    output = capsys.readouterr()
    assert output.out == (
        binding.fingerprint_render_reset_configuration(configuration()) + "\n"
    )
    assert output.err == ""


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
