"""Command line entry point: `python -m tailtag_simulator smoke --target ...`."""

import argparse
import asyncio
import getpass
import logging
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path

from tailtag_simulator.fixtures import FixtureLauncherChannel, run_fixture_smoke
from tailtag_simulator.images import load_fixture_images
from tailtag_simulator.journeys import JourneyImages, run_journeys
from tailtag_simulator.pool import (
    LauncherChannel,
    run_pool_smoke,
    run_provision,
    run_readmit,
    run_status,
    validate_pool_name,
)
from tailtag_simulator.smoke import run_smoke

LAUNCHER_COMMAND = ["make", "-s", "--no-print-directory", "api-sim-pool-ssh"]
FIXTURE_LAUNCHER_COMMAND = [
    "make",
    "-s",
    "--no-print-directory",
    "api-sim-fixture-ssh",
]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_IMAGES = REPOSITORY_ROOT / "services/api/simulation_fixtures/images"


def _prompt_hidden(prompt: str) -> str:
    """Read a credential without echo from a TTY; refuse to read it any other way."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt, stream=sys.stderr)


def _launcher() -> LauncherChannel:
    """The pool launcher, from the repository root; only host-side pool commands call it."""
    return LauncherChannel(LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT)


def _fixture_launcher() -> FixtureLauncherChannel:
    """The fixture launcher, from the repository root; only the host-side fixture run calls it."""
    return FixtureLauncherChannel(FIXTURE_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT)


def _prompt_token() -> str:
    return _prompt_hidden("Session token:")


def _prompt_secret() -> str:
    return _prompt_hidden("Clerk Staging secret:")


def _emit(line: str) -> None:
    print(line, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tailtag_simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="run the authenticated smoke")
    smoke.add_argument("--target", required=True, help="local or staging")
    smoke.add_argument("--base-url", help="local target only; fixed allowlist")
    pool = commands.add_parser("pool", help="manage the synthetic identity pool")
    pool_commands = pool.add_subparsers(dest="pool_command", required=True)
    provision = pool_commands.add_parser("provision", help="create or expand a pool")
    provision.add_argument("--size", required=True, type=int)
    status = pool_commands.add_parser("status", help="show pool counts")
    readmit = pool_commands.add_parser("readmit", help="re-admit a quarantined slot")
    readmit.add_argument("--index", required=True, type=int)
    pool_smoke = commands.add_parser("pool-smoke", help="run the pool smoke on Staging")
    pool_smoke.add_argument("--count", required=True, type=int)
    fixture_smoke = commands.add_parser(
        "fixture-smoke", help="run the fixture smoke on Staging"
    )
    fixture_smoke.add_argument("--owners", type=int, default=2)
    fixture_smoke.add_argument("--fursuits", type=int, default=1)
    fixture_smoke.add_argument("--catchers", type=int, default=2)
    journeys = commands.add_parser(
        "journeys", help="run the acceptance journeys on Staging"
    )
    for each in (provision, status, readmit, pool_smoke, fixture_smoke, journeys):
        each.add_argument("--pool", required=True, type=validate_pool_name)
    args = parser.parse_args(argv)
    for name in ("httpx", "httpcore"):  # their INFO lines carry full request URLs
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).propagate = False
    try:
        if args.command == "pool-smoke":
            return asyncio.run(
                run_pool_smoke(
                    str(args.pool),
                    int(args.count),
                    prompt_secret=_prompt_secret,
                    channel=_launcher(),
                    emit=_emit,
                )
            )
        if args.command == "fixture-smoke":
            return asyncio.run(
                run_fixture_smoke(
                    str(args.pool),
                    int(args.owners),
                    int(args.fursuits),
                    int(args.catchers),
                    prompt_secret=_prompt_secret,
                    lease_channel=_launcher(),
                    fixture_channel=_fixture_launcher(),
                    emit=_emit,
                )
            )
        if args.command == "journeys":
            valid_a, valid_b = load_fixture_images(FIXTURE_IMAGES)
            return asyncio.run(
                run_journeys(
                    str(args.pool),
                    images=JourneyImages(valid_a=valid_a, valid_b=valid_b),
                    prompt_secret=_prompt_secret,
                    lease_channel=_launcher(),
                    fixture_channel=_fixture_launcher(),
                    emit=_emit,
                )
            )
        if args.command == "pool":
            if args.pool_command == "provision":
                return asyncio.run(
                    run_provision(
                        str(args.pool),
                        int(args.size),
                        prompt_secret=_prompt_secret,
                        channel=_launcher(),
                        emit=_emit,
                    )
                )
            if args.pool_command == "status":
                return asyncio.run(
                    run_status(str(args.pool), channel=_launcher(), emit=_emit)
                )
            return asyncio.run(
                run_readmit(
                    str(args.pool), int(args.index), channel=_launcher(), emit=_emit
                )
            )
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
