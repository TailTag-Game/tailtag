"""Command line entry point: `python -m tailtag_simulator smoke --target ...`."""

import argparse
import asyncio
import getpass
import sys
import warnings
from collections.abc import Sequence

from tailtag_simulator.smoke import run_smoke


def _prompt_token() -> str:
    """Read the token without echo from a TTY; refuse to read it any other way."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass("Session token:", stream=sys.stderr)


def _emit(line: str) -> None:
    print(line, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tailtag_simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="run the authenticated smoke")
    smoke.add_argument("--target", required=True, help="local or staging")
    smoke.add_argument("--base-url", help="local target only; fixed allowlist")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(
            run_smoke(
                str(args.target),
                base_url=None if args.base_url is None else str(args.base_url),
                prompt_token=_prompt_token,
                emit=_emit,
            )
        )
    except KeyboardInterrupt:
        _emit("FAIL interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
