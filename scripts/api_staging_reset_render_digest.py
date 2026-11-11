"""Print the pin digest of the owner's private Render Staging reset file (#410).

The command reads the file with the strict #204 private-file rules: mode
`0600`, a `0700` directory, and exactly the nine reset assignments. It prints
only the digest, never a value. Pin the digest as
`_EXPECTED_RENDER_RESET_DIGEST` in `config/replacement_target_binding.py`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NoReturn

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config.owner_only import open_owner_only_file
from config.replacement_target_binding import fingerprint_render_reset_configuration

RENDER_RESET_CONFIG_PATH: Final = (
    Path.home() / ".config/tailtag/staging-reset-render.env"
)
_FAILURE: Final = "FAIL Render reset digest"
_CONFIGURATION_NAMES: Final = frozenset(
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
_CONFIGURATION_VALUE = re.compile(r"[A-Za-z0-9._:/@+-]+")


def _read_configuration(path: Path) -> dict[str, str]:
    try:
        values: dict[str, str] = {}
        with open_owner_only_file(path, max_bytes=16 * 1024) as stream:
            text = stream.read().decode("utf-8")
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            if line.count("=") != 1:
                raise ValueError
            key, value = line.split("=", 1)
            if (
                key not in _CONFIGURATION_NAMES
                or key in values
                or not value
                or _CONFIGURATION_VALUE.fullmatch(value) is None
            ):
                raise ValueError
            values[key] = value
        if frozenset(values) != _CONFIGURATION_NAMES:
            raise ValueError
        return values
    except (OSError, TypeError, UnicodeError, ValueError):
        raise ValueError("configuration invalid") from None


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


def main(argv: list[str] | None = None) -> int:
    """Print the digest, or one fixed failure line that names no value."""
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path, default=RENDER_RESET_CONFIG_PATH)
    try:
        arguments = parser.parse_args(argv)
        values = _read_configuration(arguments.config)
        digest = fingerprint_render_reset_configuration(values)
    except (SystemExit, ValueError):
        print(_FAILURE, file=sys.stderr)
        return 1
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
