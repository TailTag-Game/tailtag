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
from contextlib import nullcontext
from pathlib import Path
from typing import cast

from tailtag_simulator.baselines import PromotionFailed, promote, trend
from tailtag_simulator.behavior_config import resolve_behavior_config
from tailtag_simulator.cleanup import run_cleanup, run_retained
from tailtag_simulator.client import open_client
from tailtag_simulator.convention import run_convention
from tailtag_simulator.evaluation import (
    EvaluationFailed,
    default_output,
    evaluate,
    summary,
    write_evaluation,
)
from tailtag_simulator.fixtures import FixtureLauncherChannel, run_fixture_smoke
from tailtag_simulator.host_protocol import (
    decode_document,
    manifest_target,
    validate_manifest,
)
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
from tailtag_simulator.provenance import SourceRejected, execution_mode, load_source
from tailtag_simulator.reconciliation import InspectionLauncherChannel
from tailtag_simulator.reports import ReportFailed, RunReport, load_report
from tailtag_simulator.safety import SafetyRuntime, resolve_safety_policy
from tailtag_simulator.scenarios import ScenarioRejected
from tailtag_simulator.smoke import run_smoke
from tailtag_simulator.targets import (
    Target,
    bind_target,
    bound_target,
    resolve_target,
    verify_target,
)
from tailtag_simulator.traffic_config import resolve_traffic_config

# `task -s` keeps launcher stdout to the child's JSON result alone.
LAUNCHER_COMMAND = ["task", "-s", "api-sim-pool-ssh"]
FIXTURE_LAUNCHER_COMMAND = ["task", "-s", "api-sim-fixture-ssh"]
INSPECTION_LAUNCHER_COMMAND = ["task", "-s", "api-sim-inspect-ssh"]
# The replica relays for host commands named with `--replica-session` (#359).
REPLICA_LAUNCHER_COMMAND = ["task", "-s", "api-sim-pool-replica"]
REPLICA_FIXTURE_LAUNCHER_COMMAND = ["task", "-s", "api-sim-fixture-replica"]


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


def _run_id(value: str) -> str:
    """A canonical lowercase UUID, as the ledger records it."""
    if str(uuid.UUID(value)) != value:
        raise ValueError("invalid run id")
    return value


def _replica_premise(
    args: argparse.Namespace,
) -> tuple[Target, dict[str, object]] | None:
    """The replica target and the newest promoted identity, or None for Staging (#359).

    Both flags or neither. The session host must be the pinned replica host, both
    relay files owner-only and naming that host, and the receipt the newest promoted
    one. The host operator holds those rules, so it is imported only here: it is host
    tooling, and native Windows runs only the Staging commands.
    """
    session = getattr(args, "replica_session", None)
    receipt = getattr(args, "receipt", None)
    if session is None and receipt is None:
        return None
    if session is None or receipt is None:
        raise ValueError
    from tailtag_simulator.host_operator import (
        latest_replica_identity,
        replica_files,
        replica_session_host,
    )

    target = resolve_target("replica", f"https://{replica_session_host(session)}")
    if replica_files(target) is None:
        raise ValueError
    return target, latest_replica_identity(receipt)


async def _served_identity(target: Target) -> dict[str, object]:
    """Two agreeing identity reads with readiness, from the replica only."""
    async with open_client(target.origin) as client:
        return (await verify_target(client, target)).identity()


async def _serves_receipt(target: Target, expected: dict[str, object]) -> bool:
    """True only when the replica serves the receipt identity; prints `FAIL target` otherwise."""
    try:
        identity = await _served_identity(target)
    except Exception:  # noqa: BLE001 - failures become a fixed line, never detail
        identity = None
    if identity != expected:
        _emit("FAIL target")
        return False
    return True


def _prompt_token() -> str:
    return _prompt_hidden("Session token:")


def _prompt_secret() -> str:
    return _prompt_hidden(f"Clerk {bound_target().name.capitalize()} secret:")


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
    journeys.add_argument("--host-manifest", type=Path)
    journeys.add_argument("--host-socket-dir", type=Path)
    journeys.add_argument("--stage-log", type=Path)
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
    retained = commands.add_parser("retained", help="list retained and unfinished runs")
    for each in (provision, status, readmit, fixture_smoke, cleanup, retained):
        each.add_argument("--replica-session", type=Path)
        each.add_argument("--receipt", type=Path)
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
    report_evaluate = report_commands.add_parser("evaluate")
    report_evaluate.add_argument("report", type=Path)
    report_evaluate.add_argument("--host-companion", type=Path)
    report_evaluate.add_argument("--context", type=Path)
    default_baselines = REPOSITORY_ROOT / "tools/simulator/baselines"
    report_evaluate.add_argument(
        "--baselines-dir", type=Path, default=default_baselines
    )
    report_evaluate.add_argument("--out", type=Path)
    report_trend = report_commands.add_parser("trend")
    report_trend.add_argument("directory", type=Path)
    report_trend.add_argument("--baselines-dir", type=Path, default=default_baselines)
    baseline_command = commands.add_parser(
        "baseline", help="promote a reviewed baseline offline"
    )
    baseline_commands = baseline_command.add_subparsers(
        dest="baseline_command", required=True
    )
    baseline_promote = baseline_commands.add_parser("promote")
    baseline_promote.add_argument("report", type=Path)
    baseline_promote.add_argument("--rationale", required=True)
    baseline_promote.add_argument("--host-companion", type=Path)
    baseline_promote.add_argument("--context", type=Path)
    baseline_promote.add_argument(
        "--baselines-dir", type=Path, default=default_baselines
    )
    baseline_promote.add_argument("--initial-thresholds", action="store_true")
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
    if args.command == "report" and args.report_command == "evaluate":
        try:
            artifact = evaluate(
                args.report,
                host_companion=args.host_companion,
                context=args.context,
                baselines_dir=args.baselines_dir,
            )
            write_evaluation(
                artifact, args.out or default_output(args.report, artifact)
            )
        except EvaluationFailed:
            _emit("FAIL evaluation")
            return 1
        _emit(f"PASS evaluation {artifact['verdict']}")
        for line in summary(artifact):
            _emit(line)
        return 0
    if args.command == "baseline":
        try:
            written = promote(
                args.report,
                rationale=args.rationale,
                baselines_dir=args.baselines_dir,
                host_companion=args.host_companion,
                context=args.context,
                initial_thresholds=args.initial_thresholds,
            )
        except PromotionFailed:
            _emit("FAIL promotion")
            return 1
        _emit(f"PASS promotion {written.name.removesuffix('.baseline.json')}")
        return 0
    if args.command == "report" and args.report_command == "trend":
        try:
            lines = trend(args.directory, baselines_dir=args.baselines_dir)
        except OSError:
            _emit("FAIL trend")
            return 1
        for line in lines:
            _emit(line)
        return 0
    if args.command == "report":
        try:
            load_report(args.path)
        except ReportFailed:
            _emit("FAIL report")
            return 1
        _emit("PASS report")
        return 0
    try:
        args.replica = _replica_premise(args)
    except Exception:  # noqa: BLE001 - a bad premise or receipt is a fixed line, never detail
        _emit("FAIL configuration")
        return 1
    try:
        if args.command in {"cleanup", "retained", "pool"}:
            return _host_command(args)
        return asyncio.run(_execute(args))
    except (OSError, ValueError):
        if args.command not in {"convention", "journeys"} or not (
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


def _host_command(args: argparse.Namespace) -> int:
    """Run one pool, cleanup or retained command on Staging, or on the replica (#359)."""
    pool_channel, fixture_channel = _launcher(), _fixture_launcher()
    with bind_target(args.replica[0]) if args.replica else nullcontext():
        if args.replica:
            target, identity = args.replica
            if not asyncio.run(_serves_receipt(target, identity)):
                return 1
            pool_channel = LauncherChannel(
                REPLICA_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT, identity=identity
            )
            fixture_channel = FixtureLauncherChannel(
                REPLICA_FIXTURE_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT, identity=identity
            )
        if args.command == "cleanup":
            return asyncio.run(
                run_cleanup(
                    str(args.pool),
                    str(args.run_id),
                    channel=fixture_channel,
                    emit=_emit,
                )
            )
        if args.command == "retained":
            return asyncio.run(run_retained(channel=fixture_channel, emit=_emit))
        if args.pool_command == "provision":
            return asyncio.run(
                run_provision(
                    str(args.pool),
                    int(args.size),
                    prompt_secret=_prompt_secret,
                    channel=pool_channel,
                    emit=_emit,
                )
            )
        if args.pool_command == "status":
            return asyncio.run(
                run_status(str(args.pool), channel=pool_channel, emit=_emit)
            )
        return asyncio.run(
            run_readmit(
                str(args.pool), int(args.index), channel=pool_channel, emit=_emit
            )
        )


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
                value.get("target", "staging") not in ("staging", "replica")
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
        if (
            args.command in {"convention", "journeys"}
            and args.host_manifest is not None
        ):
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
        # The manifest or the replica session names the run target. Bind it before
        # any network call (#359).
        target = (
            manifest_target(supplied_host)
            if supplied_host
            else args.replica[0]
            if args.replica
            else resolve_target("staging", None)
        )
    except (ScenarioRejected, ValueError):
        _emit("FAIL configuration")
        return 1
    with bind_target(target):
        if args.replica and not await _serves_receipt(target, args.replica[1]):
            return 1
        return await _execute_bound(args, supplied_host, policy)


async def _execute_bound(
    args: argparse.Namespace,
    supplied_host: dict[str, object] | None,
    policy: dict[str, object],
) -> int:
    """Run the command with its target bound."""
    report: RunReport | None = None
    config: dict[str, object] = {}
    if args.command in {
        "smoke",
        "pool-smoke",
        "fixture-smoke",
        "journeys",
        "convention",
    }:
        config = {"target": bound_target().name, "base_url": None}
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
        convention = args.command == "convention"
        if args.command in {"convention", "journeys"} and (
            args.host_manifest is not None
            or args.host_socket_dir is not None
            or args.stage_log is not None
        ):
            try:
                if (
                    args.host_manifest is None
                    or args.host_socket_dir is None
                    or args.scenario_version != (2 if convention else 1)
                    or not args.host_socket_dir.is_absolute()
                ):
                    raise ValueError
                host = supplied_host
                if host is None:
                    raise ValueError
                if (
                    host["configuration"]
                    != (config if convention else {"pool": args.pool})
                    or host["safety"] != policy
                    or host["seed"] != args.seed
                    or host["scenario_id"]
                    != ("convention-" + args.family if convention else "journeys")
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
        if args.command == "convention" and args.scenario_version == 2:
            report.record_execution_mode(execution_mode(REPOSITORY_ROOT))
        report.end("provenance", "passed")
        if report.write_failed:
            _emit("FAIL report")
            return report.finish(1)
    safety = SafetyRuntime(
        policy,
        observe=report.cache_safety if report else None,
        persist=report.record_safety if report else None,
    )
    if sys.platform == "win32":
        # The Linux host runner sends SIGUSR1 to abort on resource saturation;
        # Windows has neither that signal nor that runner.
        return await _dispatch(args, config, report, safety)
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

    if args.command == "convention":
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
            lease_channel=LauncherChannel(REPLICA_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT)
            if args.replica
            else _launcher(),
            fixture_channel=FixtureLauncherChannel(
                REPLICA_FIXTURE_LAUNCHER_COMMAND, cwd=REPOSITORY_ROOT
            )
            if args.replica
            else _fixture_launcher(),
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
            lease_channel=LauncherChannel(
                channel_command("pool", LAUNCHER_COMMAND), cwd=REPOSITORY_ROOT
            ),
            fixture_channel=FixtureLauncherChannel(
                channel_command("fixture", FIXTURE_LAUNCHER_COMMAND),
                cwd=REPOSITORY_ROOT,
            ),
            inspection_channel=InspectionLauncherChannel(
                channel_command("inspection", INSPECTION_LAUNCHER_COMMAND),
                cwd=REPOSITORY_ROOT,
            ),
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
