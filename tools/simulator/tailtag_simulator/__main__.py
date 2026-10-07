"""Command line entry point: `python -m tailtag_simulator smoke --target ...`."""

import argparse
import asyncio
import getpass
import json
import logging
import sys
import uuid
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from tailtag_simulator.behavior_config import resolve_behavior_config
from tailtag_simulator.cleanup import run_cleanup, run_retained
from tailtag_simulator.convention import run_convention
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
from tailtag_simulator.population_reconciliation import (
    PopulationInspectionLauncherChannel,
)
from tailtag_simulator.provenance import SourceRejected, load_source
from tailtag_simulator.reconciliation import InspectionLauncherChannel
from tailtag_simulator.reports import ReportFailed, RunReport, load_report
from tailtag_simulator.scenarios import ScenarioRejected
from tailtag_simulator.smoke import run_smoke

LAUNCHER_COMMAND = ["make", "-s", "--no-print-directory", "api-sim-pool-ssh"]
FIXTURE_LAUNCHER_COMMAND = [
    "make",
    "-s",
    "--no-print-directory",
    "api-sim-fixture-ssh",
]
INSPECTION_LAUNCHER_COMMAND = [
    "make",
    "-s",
    "--no-print-directory",
    "api-sim-inspect-ssh",
]


def _repository_root() -> Path:
    parents = Path(__file__).resolve().parents
    for parent in parents:
        if (parent / ".git").exists():
            return parent
    for parent in parents:
        if (parent / "source.json").is_file():
            return parent
    return Path("/app")


REPOSITORY_ROOT = _repository_root()
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


def _inspection_launcher() -> InspectionLauncherChannel:
    """The inspection launcher, from the repository root; only journeys reconciliation calls it."""
    return InspectionLauncherChannel(INSPECTION_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT)


def _run_id(value: str) -> str:
    """A canonical lowercase UUID, as the ledger records it."""
    if str(uuid.UUID(value)) != value:
        raise ValueError("invalid run id")
    return value


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
    convention = commands.add_parser(
        "convention", help="run a finite convention population on Staging"
    )
    convention.add_argument(
        "--family",
        required=True,
        choices=("baseline", "post-event", "hotspot", "retry", "soak"),
    )
    convention.add_argument("--config", type=Path)
    cleanup = commands.add_parser(
        "cleanup", help="clean one run's Staging state and readmit its identities"
    )
    cleanup.add_argument("--run-id", required=True, type=_run_id)
    commands.add_parser("retained", help="list retained and unfinished runs")
    for each in (
        provision,
        status,
        readmit,
        pool_smoke,
        fixture_smoke,
        journeys,
        convention,
        cleanup,
    ):
        each.add_argument("--pool", required=True, type=validate_pool_name)
    report_command = commands.add_parser("report", help="validate a report offline")
    report_commands = report_command.add_subparsers(
        dest="report_command", required=True
    )
    report_validate = report_commands.add_parser("validate")
    report_validate.add_argument("path", type=Path)
    for execution in (smoke, pool_smoke, fixture_smoke, journeys, convention):
        execution.add_argument("--scenario-version", type=int, default=1)
        execution.add_argument("--seed", type=int, default=0)
        execution.add_argument(
            "--report-dir",
            type=Path,
            default=(
                REPOSITORY_ROOT / "tools/simulator/reports"
                if (REPOSITORY_ROOT / ".git").exists()
                else Path("/reports")
            ),
        )
    args = parser.parse_args(argv)
    for name in ("httpx", "httpcore"):  # their INFO lines carry full request URLs
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).propagate = False
    if args.command == "report":
        try:
            load_report(args.path)
        except ReportFailed:
            _emit("FAIL report")
            return 1
        _emit("PASS report")
        return 0
    try:
        if args.command == "cleanup":
            return asyncio.run(
                run_cleanup(
                    str(args.pool),
                    str(args.run_id),
                    channel=_fixture_launcher(),
                    emit=_emit,
                )
            )
        if args.command == "retained":
            return asyncio.run(run_retained(channel=_fixture_launcher(), emit=_emit))
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
        return asyncio.run(_execute(args))
    except KeyboardInterrupt:
        _emit("FAIL interrupted")
        return 130


def _behavior_file(path: Path) -> dict[str, object]:
    """Bounded JSON with no duplicate keys or unapproved routing overrides."""

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ScenarioRejected
            result[key] = value
        return result

    try:
        with path.open("rb") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise ScenarioRejected
        value = json.loads(raw, object_pairs_hook=pairs)
        if not isinstance(value, dict) or set(cast(dict[str, object], value)) & {
            "pool",
            "target",
            "base_url",
            "family",
        }:
            raise ScenarioRejected
        return cast(dict[str, object], value)
    except (OSError, ValueError, RecursionError):
        raise ScenarioRejected from None


async def _execute(args: argparse.Namespace) -> int:
    """Create durable evidence and establish provenance before executing a command."""
    report: RunReport | None = None
    config: dict[str, object] = {}
    if args.command in {
        "smoke",
        "pool-smoke",
        "fixture-smoke",
        "journeys",
        "convention",
    }:
        config = {"target": "staging", "base_url": None}
        if args.command == "smoke":
            config.update(target=args.target, base_url=args.base_url)
        else:
            config["pool"] = args.pool
        if args.command == "pool-smoke":
            config["count"] = args.count
        elif args.command == "fixture-smoke":
            config.update(
                owners=args.owners, fursuits=args.fursuits, catchers=args.catchers
            )
        if args.command == "convention":
            try:
                config.update(
                    _behavior_file(args.config) if args.config is not None else {}
                )
                config["family"] = args.family
                config = resolve_behavior_config(config)
            except (ScenarioRejected, ValueError):
                _emit("FAIL configuration")
                return 1
        try:
            report = RunReport(
                args.report_dir,
                "convention-" + args.family
                if args.command == "convention"
                else args.command,
                scenario_version=args.scenario_version,
                seed=args.seed,
                config=config,
            )
        except (ReportFailed, ScenarioRejected):
            _emit("FAIL report")
            return 1
        report.begin("provenance")
        try:
            source = load_source(REPOSITORY_ROOT)
        except SourceRejected:
            report.end("provenance", "failed", "FAIL_PROVENANCE")
            _emit("FAIL provenance")
            return report.finish(1)
        except BaseException:
            report.end("provenance", "interrupted", "FAIL_INTERRUPTED")
            report.finish(130)
            raise
        report.record_source(source)
        report.end("provenance", "passed")
        if report.write_failed:
            _emit("FAIL report")
            return report.finish(1)
    if args.command == "convention":
        return await run_convention(
            str(args.pool),
            config=config,
            seed=args.seed,
            prompt_secret=_prompt_secret,
            lease_channel=_launcher(),
            fixture_channel=_fixture_launcher(),
            inspection_channel=PopulationInspectionLauncherChannel(
                INSPECTION_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT
            ),
            emit=_emit,
            report=report,
        )
    if args.command == "pool-smoke":
        return await run_pool_smoke(
            str(args.pool),
            int(args.count),
            prompt_secret=_prompt_secret,
            channel=_launcher(),
            emit=_emit,
            report=report,
        )
    if args.command == "fixture-smoke":
        return await run_fixture_smoke(
            str(args.pool),
            int(args.owners),
            int(args.fursuits),
            int(args.catchers),
            prompt_secret=_prompt_secret,
            lease_channel=_launcher(),
            fixture_channel=_fixture_launcher(),
            emit=_emit,
            report=report,
        )
    if args.command == "journeys":
        try:
            valid_a, valid_b = load_fixture_images(FIXTURE_IMAGES)
        except BaseException as failure:
            if report is not None:
                report.begin("setup")
                report.end(
                    "setup",
                    "failed" if isinstance(failure, Exception) else "interrupted",
                    "FAIL_SETUP"
                    if isinstance(failure, Exception)
                    else "FAIL_INTERRUPTED",
                )
                code = report.finish(1 if isinstance(failure, Exception) else 130)
            else:
                code = 1
            if not isinstance(failure, Exception):
                raise
            _emit("FAIL setup")
            return code
        return await run_journeys(
            str(args.pool),
            images=JourneyImages(valid_a=valid_a, valid_b=valid_b),
            prompt_secret=_prompt_secret,
            lease_channel=_launcher(),
            fixture_channel=_fixture_launcher(),
            inspection_channel=_inspection_launcher(),
            emit=_emit,
            report=report,
        )
    return await run_smoke(
        str(args.target),
        base_url=None if args.base_url is None else str(args.base_url),
        prompt_token=_prompt_token,
        emit=_emit,
        report=report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
