"""Command line entry point: `python -m tailtag_simulator smoke --target ...`."""

import argparse
import asyncio
import getpass
import json
import logging
import os
import signal
import stat
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
from tailtag_simulator.host_protocol import decode_document, validate_manifest
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
from tailtag_simulator.safety import SafetyRuntime, resolve_safety_policy
from tailtag_simulator.scenarios import ScenarioRejected
from tailtag_simulator.smoke import run_smoke
from tailtag_simulator.traffic_config import resolve_traffic_config

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


_stage_fd: int | None = None
_stage_bytes = 0


def _emit(line: str) -> None:
    global _stage_bytes
    if _stage_fd is not None:
        payload = (line + "\n").encode("utf-8")
        if _stage_bytes + len(payload) > 1_048_576:
            raise ValueError("stage_limit")
        if os.write(_stage_fd, payload) != len(payload):
            raise OSError("stage_write")
        _stage_bytes += len(payload)
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
    convention.add_argument("--unattended", action="store_true")
    convention.add_argument("--host-manifest", type=Path)
    convention.add_argument("--host-socket-dir", type=Path)
    convention.add_argument("--stage-log", type=Path)
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
        execution.add_argument("--safety-config", type=Path)
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
    except (OSError, ValueError):
        if args.command != "convention" or not (
            args.host_manifest or args.host_socket_dir or args.stage_log
        ):
            raise
        print("FAIL host", flush=True)
        return 1
    except KeyboardInterrupt:
        _emit("FAIL interrupted")
        return 130
    finally:
        global _stage_fd
        if _stage_fd is not None:
            os.close(_stage_fd)
            _stage_fd = None


def _behavior_file(path: Path, *, host: bool = False) -> dict[str, object]:
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
        if not isinstance(value, dict):
            raise ScenarioRejected
        value = cast(dict[str, object], value)
        if set(value) & {"pool", "family"}:
            raise ScenarioRejected
        if host:
            if (
                value.get("target", "staging") != "staging"
                or value.get("base_url") is not None
            ):
                raise ScenarioRejected
        elif set(value) & {"target", "base_url"}:
            raise ScenarioRejected
        return value
    except (OSError, ValueError, RecursionError):
        raise ScenarioRejected from None


async def _execute(args: argparse.Namespace) -> int:
    """Create durable evidence and establish provenance before executing a command."""
    supplied_host: dict[str, object] | None = None
    try:
        if args.command == "convention" and args.host_manifest is not None:
            with args.host_manifest.open("rb") as stream:
                supplied_host = validate_manifest(decode_document(stream.read(65537)))
        if args.command == "convention" and args.unattended:
            raise ValueError
        policy = resolve_safety_policy(
            _behavior_file(args.safety_config)
            if args.safety_config is not None
            else cast(dict[str, object], supplied_host["safety"])
            if supplied_host
            else {}
        )
    except (ScenarioRejected, ValueError):
        _emit("FAIL configuration")
        return 1
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
                    _behavior_file(args.config, host=supplied_host is not None)
                    if args.config is not None
                    else cast(dict[str, object], supplied_host["configuration"])
                    if supplied_host
                    else {}
                )
                config["pool"] = args.pool
                config["family"] = args.family
                config = (
                    resolve_traffic_config
                    if args.scenario_version == 2
                    else resolve_behavior_config
                )(config)
            except (ScenarioRejected, ValueError):
                _emit("FAIL configuration")
                return 1
        host: dict[str, object] | None = None
        if args.command == "convention" and (
            args.host_manifest is not None
            or args.host_socket_dir is not None
            or args.stage_log is not None
        ):
            try:
                if (
                    args.host_manifest is None
                    or args.host_socket_dir is None
                    or args.scenario_version != 2
                    or not args.host_socket_dir.is_absolute()
                ):
                    raise ValueError
                host = supplied_host
                if host is None:
                    raise ValueError
                if (
                    host["configuration"] != config
                    or host["safety"] != policy
                    or host["seed"] != args.seed
                    or host["scenario_id"] != "convention-" + args.family
                ):
                    raise ValueError
                source = load_source(REPOSITORY_ROOT)
                release = cast(dict[str, object], host["release"])
                runtime = cast(dict[str, object], source["runtime"])
                if (
                    cast(dict[str, object], source["simulator_sha"])["value"]
                    != release["simulator_sha"]
                    or cast(dict[str, object], runtime["dependency_lock_sha256"])[
                        "value"
                    ]
                    != release["dependency_lock_sha256"]
                ):
                    raise ValueError
                if args.stage_log is not None:
                    global _stage_fd, _stage_bytes
                    if any(
                        parent.is_symlink()
                        for parent in (args.stage_log, *args.stage_log.parents)
                    ):
                        raise ValueError
                    _stage_fd = os.open(
                        args.stage_log,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    )
                    info = os.fstat(_stage_fd)
                    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                        raise ValueError
                    _stage_bytes = 0
            except (OSError, ValueError, SourceRejected):
                print("FAIL host", flush=True)
                return 1
        args.bound_host = host
        try:
            report = RunReport(
                args.report_dir,
                "convention-" + args.family
                if args.command == "convention"
                else args.command,
                scenario_version=args.scenario_version,
                seed=args.seed,
                config=config,
                safety_policy=policy,
                run_id=cast(str, host["run_id"]) if host else None,
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
    safety = SafetyRuntime(
        policy,
        observe=report.cache_safety if report else None,
        persist=report.record_safety if report else None,
    )
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGUSR1)

    def stop() -> None:
        try:
            safety.abort("resource_saturation")
        except Exception:  # noqa: BLE001, S110 - report failure remains latched
            pass

    loop.add_signal_handler(signal.SIGUSR1, stop)
    try:
        return await _dispatch(args, config, report, safety)
    finally:
        loop.remove_signal_handler(signal.SIGUSR1)
        signal.signal(signal.SIGUSR1, previous)


async def _dispatch(
    args: argparse.Namespace,
    config: dict[str, object],
    report: RunReport | None,
    safety: SafetyRuntime,
) -> int:
    if args.command == "convention":

        def channel_command(channel: str, ordinary: list[str]) -> list[str]:
            return (
                [
                    sys.executable,
                    "-m",
                    "tailtag_simulator.host_channel",
                    "--channel",
                    channel,
                    "--socket-dir",
                    str(args.host_socket_dir),
                ]
                if args.bound_host
                else ordinary
            )

        return await run_convention(
            str(args.pool),
            config=config,
            seed=args.seed,
            scenario_version=args.scenario_version,
            prompt_secret=_prompt_secret,
            lease_channel=LauncherChannel(
                channel_command("pool", LAUNCHER_COMMAND), cwd=REPOSITORY_ROOT
            )
            if args.bound_host
            else _launcher(),
            fixture_channel=FixtureLauncherChannel(
                channel_command("fixture", FIXTURE_LAUNCHER_COMMAND),
                cwd=REPOSITORY_ROOT,
            )
            if args.bound_host
            else _fixture_launcher(),
            inspection_channel=PopulationInspectionLauncherChannel(
                channel_command("inspection", INSPECTION_LAUNCHER_COMMAND),
                cwd=REPOSITORY_ROOT,
            ),
            emit=_emit,
            report=report,
            safety=safety,
        )
    if args.command == "pool-smoke":
        return await run_pool_smoke(
            str(args.pool),
            int(args.count),
            prompt_secret=_prompt_secret,
            channel=_launcher(),
            emit=_emit,
            report=report,
            safety=safety,
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
            safety=safety,
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
            safety=safety,
        )
    return await run_smoke(
        str(args.target),
        base_url=None if args.base_url is None else str(args.base_url),
        prompt_token=_prompt_token,
        emit=_emit,
        report=report,
        safety=safety,
    )


if __name__ == "__main__":
    raise SystemExit(main())
