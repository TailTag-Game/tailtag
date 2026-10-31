"""Print the pin digest of the owner's private Render Staging reset file (#410).

The command reads the file with the strict #204 private-file rules: mode
`0600`, a `0700` directory, and exactly the nine reset assignments. It prints
only the digest, never a value. Pin the digest as
`_EXPECTED_RENDER_RESET_DIGEST` in `config/replacement_target_binding.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, NoReturn

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
for _path in (_REPOSITORY_ROOT, _REPOSITORY_ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.api_staging_reset_ssh import (
    _read_configuration,  # pyright: ignore[reportPrivateUsage]
)

from config.replacement_target_binding import fingerprint_render_reset_configuration

RENDER_RESET_CONFIG_PATH: Final = (
    Path.home() / ".config/tailtag/staging-reset-render.env"
)
_FAILURE: Final = "FAIL Render reset digest"


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
