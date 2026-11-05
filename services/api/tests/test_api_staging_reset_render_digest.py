"""The owner's Render reset digest comes only from a strict private file (#410 AC5)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from tests import windows_acl_support as acl

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
CONFIGURATION_NAMES = frozenset(
    {
        "TAILTAG_STAGING_RESET_ENABLED",
        "TAILTAG_STAGING_RESET_ID",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
        "TAILTAG_STAGING_DATABASE_HOST",
        "TAILTAG_STAGING_DATABASE_PORT",
        "TAILTAG_STAGING_DATABASE_NAME",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
        "TAILTAG_STAGING_RESET_MEDIA_KEY",
    }
)


def configuration(**overrides: str) -> dict[str, str]:
    """Return the nine private reset bindings, with fictitious values only."""
    return {
        "TAILTAG_STAGING_RESET_ENABLED": "true",
        "TAILTAG_STAGING_RESET_ID": "2b859e84-1d92-4a8a-a72b-d3567219288d",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID": "742391",
        "TAILTAG_STAGING_DATABASE_HOST": "postgres.internal",
        "TAILTAG_STAGING_DATABASE_PORT": "5432",
        "TAILTAG_STAGING_DATABASE_NAME": "tailtag",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID": "user_synthetic_owner",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_synthetic_catcher",
        "TAILTAG_STAGING_RESET_MEDIA_KEY": "images/0123456789abcdef0123456789abcdef.png",
        **overrides,
    }


def write_configuration(path: Path, values: Mapping[str, str]) -> None:
    """Create a private operator file with its required containing directory."""
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        "# synthetic test configuration\n\n"
        + "\n".join(f"{key}={value}" for key, value in values.items())
        + "\n"
    )
    path.chmod(0o600)
    if sys.platform == "win32":
        acl.protect_tree(path.parent, path)


def assert_denied(operation: Callable[[], object]) -> None:
    """Require a fail-closed helper outcome without selecting a new error API."""
    try:
        operation()
    except Exception:  # noqa: BLE001
        return
    pytest.fail("unsafe operator input must be denied")


def mutate_configuration(path: Path, mutation: str) -> None:
    """Apply one focused malformed-file mutation while preserving other bindings."""
    if mutation == "file-mode":
        path.chmod(0o644)
        if sys.platform == "win32":
            acl.make_owner_only(path, extra_aces="(A;;FR;;;BU)")
    elif mutation == "directory-mode":
        path.parent.chmod(0o755)
        if sys.platform == "win32":
            acl.make_owner_only(path.parent, container=True, extra_aces="(A;;FR;;;BU)")
    elif mutation == "evaluated-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ID="$(unsafe)"))
    elif mutation == "quoted-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ENABLED="'true'"))
    elif mutation == "shell-separator":
        write_configuration(
            path, configuration(TAILTAG_STAGING_RESET_ENABLED="true;unsafe")
        )
    elif mutation == "whitespace-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ENABLED=" true"))
    elif mutation == "unknown-key":
        path.write_text(path.read_text() + "UNKNOWN=value\n")
    elif mutation == "selector-override":
        path.write_text(path.read_text() + "RENDER_SERVICE_ID=unapproved-selector\n")
    elif mutation == "credential-field":
        path.write_text(path.read_text() + "DATABASE_URL=postgresql://unapproved\n")
    elif mutation == "nul-byte":
        path.write_bytes(path.read_bytes() + b"\x00")
    elif mutation == "duplicate":
        path.write_text(
            "\n".join(
                [f"{key}={value}" for key, value in configuration().items()]
                + ["TAILTAG_STAGING_RESET_ID=2b859e84-1d92-4a8a-a72b-d3567219288d"]
            )
        )
    else:
        raise AssertionError(f"unknown mutation: {mutation}")


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


def test_read_configuration_accepts_only_the_exact_nine_literal_assignments(
    digest_tool: Any, tmp_path: Path
) -> None:
    """SSH-2: comments and blank lines do not weaken the strict private-file grammar."""
    path = tmp_path / "operator" / "staging-reset.env"
    write_configuration(path, configuration())

    assert digest_tool._read_configuration(path) == configuration()
    assert set(digest_tool._read_configuration(path)) == CONFIGURATION_NAMES


@pytest.mark.parametrize(
    "mutation",
    (
        "file-mode",
        "directory-mode",
        "evaluated-value",
        "quoted-value",
        "shell-separator",
        "whitespace-value",
        "unknown-key",
        "selector-override",
        "credential-field",
        "nul-byte",
        "duplicate",
    ),
)
def test_read_configuration_fails_closed_for_unsafe_file_or_content(
    digest_tool: Any, tmp_path: Path, mutation: str
) -> None:
    """SSH-2/SECURITY: a private configuration is never shell input or a selector seam."""
    path = tmp_path / "operator" / "staging-reset.env"
    write_configuration(path, configuration())
    mutate_configuration(path, mutation)

    assert_denied(lambda: digest_tool._read_configuration(path))


@pytest.mark.parametrize("link_parent", (False, True), ids=("file", "directory"))
def test_read_configuration_rejects_symbolic_links(
    digest_tool: Any, tmp_path: Path, link_parent: bool
) -> None:
    """SSH-2: links cannot redirect an operator-owned configuration read."""
    if sys.platform == "win32":
        acl.require_symlinks(tmp_path)
    target = tmp_path / "target" / "staging-reset.env"
    write_configuration(target, configuration())
    path = tmp_path / "operator" / "staging-reset.env"
    if link_parent:
        path.parent.symlink_to(target.parent, target_is_directory=True)
    else:
        path.parent.mkdir(mode=0o700)
        path.symlink_to(target)

    assert_denied(lambda: digest_tool._read_configuration(path))
