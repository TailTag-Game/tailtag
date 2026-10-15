"""Run the real root Taskfile; replace only the UV launcher the Taskfile exposes."""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from report_support import literal_report, repository

from tailtag_simulator.__main__ import (
    FIXTURE_LAUNCHER_COMMAND,
    INSPECTION_LAUNCHER_COMMAND,
    LAUNCHER_COMMAND,
)
from tailtag_simulator.host_bridge import fixed_dispatch
from tailtag_simulator.host_protocol import encode_frame

CHECKOUT = Path(__file__).parents[3]


def run_task(
    *arguments: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["task", *arguments],
        cwd=cwd,
        # GitHub Actions makes go-task add colors and `::error` annotations.
        env={
            **{k: v for k, v in env.items() if k != "GITHUB_ACTIONS"},
            "NO_COLOR": "1",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def write_adapter(path: Path, body: str) -> str:
    """Write a UV launcher stand-in; return the UV value that runs it here.

    Windows cannot execute a shebang script, so there UV names the interpreter
    and the script; the Taskfile splits the unquoted value into those words.
    """
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o755)
    if sys.platform == "win32":
        return f"{Path(sys.executable).as_posix()} {path.as_posix()}"
    return str(path)


def recording_adapter(tmp_path: Path) -> str:
    """An external UV launcher stand-in that records its argv and succeeds."""
    return write_adapter(
        tmp_path / "uv-adapter",
        "import json, os, sys\n"
        "with open(os.environ['SIM_TEST_ARGUMENTS'], 'w') as stream:\n"
        "    json.dump(sys.argv[1:], stream)\n",
    )


def test_catalog_check_treats_quoted_checkout_root_as_data(tmp_path: Path) -> None:
    simulator = Path(__file__).parents[1]
    value = literal_report()["scenario"]
    entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
    descriptor = "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json"
    root = repository(
        tmp_path
        / (
            "checkout space ' apostrophe"
            # A double quote cannot appear in a Windows file name.
            + ("" if sys.platform == "win32" else ' " quote')
            + " $(touch SENTINEL-dollar) `touch SENTINEL-backtick`"
        ),
        {
            "Taskfile.yml": (CHECKOUT / "Taskfile.yml").read_text(),
            descriptor: json.dumps(entry),
        },
    )
    # UV is an external environment/launcher boundary. Forward its bounded
    # invocation to this test's interpreter, keeping the recipe and validator real.
    # A child process, not os.execv: on Windows execv starts a new process and
    # the adapter would exit before the validator finishes.
    adapter = write_adapter(
        tmp_path / "uv-adapter",
        "import os, subprocess, sys\n"
        "assert sys.argv[1:7] == ['--directory', 'tools/simulator', 'run', '--locked', '--no-sync', 'python']\n"
        "os.chdir(sys.argv[2])\n"
        "raise SystemExit(subprocess.call([sys.executable, *sys.argv[7:]]))\n",
    )
    env = {**os.environ, "PYTHONPATH": str(simulator)}

    def run() -> subprocess.CompletedProcess[str]:
        return run_task("sim-catalog-check", f"UV={adapter}", cwd=root, env=env)

    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / "SENTINEL-dollar").exists()
    assert not (root / "SENTINEL-backtick").exists()
    # A recipe that loses the root and validates the installed catalog instead
    # must not pass: the selected checkout's current descriptor is now absent.
    (root / descriptor).unlink()
    assert run().returncode != 0


@pytest.mark.parametrize("uv_channel", ["environment", "command_line"])
def test_convention_passes_awkward_values_as_arguments_and_honors_uv_override(
    tmp_path: Path, uv_channel: str
) -> None:
    """AC13 (UV by environment and by argument) and AC17 (spaces and quotes)."""
    adapter = recording_adapter(tmp_path)
    output = tmp_path / "arguments.json"
    config = tmp_path / "config space's.json"
    report_dir = tmp_path / "reports space's"
    config.write_text('{"casual":2}')
    environment = {**os.environ, "SIM_TEST_ARGUMENTS": str(output)}
    environment.pop("UV", None)
    arguments = [
        "sim-convention",
        "POOL=pool one's",
        "FAMILY=baseline",
        f"CONFIG={config}",
        "VERSION=1",
        "SEED=-42",
        f"REPORT_DIR={report_dir}",
    ]
    if uv_channel == "environment":
        environment["UV"] = str(adapter)
    else:
        arguments.append(f"UV={adapter}")

    result = run_task(*arguments, cwd=CHECKOUT, env=environment)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output.read_text()) == [
        "--directory",
        "tools/simulator",
        "run",
        "--locked",
        "--no-sync",
        "python",
        "-m",
        "tailtag_simulator",
        "convention",
        "--pool",
        "pool one's",
        "--family",
        "baseline",
        "--config",
        str(config),
        "--scenario-version",
        "1",
        "--seed",
        "-42",
        "--report-dir",
        str(report_dir),
    ]


@pytest.mark.parametrize(
    ("task", "names"),
    [
        ("sim-smoke", ["TARGET", "BASE_URL", "VERSION", "SEED", "REPORT_DIR"]),
        ("sim-pool-provision", ["POOL", "SIZE"]),
        ("sim-pool-status", ["POOL"]),
        ("sim-pool-readmit", ["POOL", "INDEX"]),
        ("sim-pool-smoke", ["POOL", "COUNT", "VERSION", "SEED", "REPORT_DIR"]),
        (
            "sim-fixture-smoke",
            ["POOL", "OWNERS", "FURSUITS", "CATCHERS", "VERSION", "SEED", "REPORT_DIR"],
        ),
        ("sim-journeys", ["POOL", "VERSION", "SEED", "REPORT_DIR"]),
        ("sim-cleanup", ["POOL", "RUN_ID"]),
        ("sim-report-validate", ["REPORT"]),
    ],
)
def test_operator_values_with_single_quotes_reach_the_launcher_intact(
    tmp_path: Path, task: str, names: list[str]
) -> None:
    """A quote in any operator value stays one argument instead of ending the word."""
    adapter = recording_adapter(tmp_path)
    output = tmp_path / "arguments.json"
    environment = {**os.environ, "UV": str(adapter), "SIM_TEST_ARGUMENTS": str(output)}
    values = {name: f"{name.lower()} o'clock" for name in names}

    result = run_task(
        task,
        *(f"{name}={value}" for name, value in values.items()),
        cwd=CHECKOUT,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = json.loads(output.read_text())
    for value in values.values():
        assert value in recorded


@pytest.mark.parametrize(
    ("task", "arguments", "message"),
    [
        ("sim-smoke", [], "TARGET is required: local or staging."),
        ("sim-pool-status", [], "POOL is required."),
        # An empty value must fail: go-task's `requires:` would accept it.
        ("sim-pool-status", ["POOL="], "POOL is required."),
        ("sim-pool-provision", ["POOL=p1"], "POOL and SIZE are required."),
        ("sim-cleanup", ["RUN_ID=r1"], "POOL and RUN_ID are required."),
        ("sim-baseline-promote", ["REPORT=r.json"], "RATIONALE is required."),
    ],
)
def test_missing_or_empty_required_variable_fails_before_running_anything(
    tmp_path: Path, task: str, arguments: list[str], message: str
) -> None:
    adapter = recording_adapter(tmp_path)
    output = tmp_path / "arguments.json"
    environment = {**os.environ, "UV": str(adapter), "SIM_TEST_ARGUMENTS": str(output)}
    for name in ("POOL", "SIZE", "RUN_ID", "TARGET", "REPORT", "RATIONALE"):
        environment.pop(name, None)

    result = run_task(task, *arguments, cwd=CHECKOUT, env=environment)

    assert result.returncode != 0
    assert message in result.stderr.splitlines()
    assert not output.exists(), "the guard must stop the task before UV runs"


@pytest.mark.parametrize(
    ("channel", "module"),
    [
        ("pool", "scripts.api_sim_pool_ssh"),
        ("fixture", "scripts.api_sim_fixture_ssh"),
        ("inspection", "scripts.api_sim_inspect_ssh"),
    ],
)
def test_host_bridge_dispatch_runs_silent_task_with_stdin_and_exact_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, channel: str, module: str
) -> None:
    """AC9: `task -s <target>` leaves stdout as exactly the launcher's JSON."""
    adapter = write_adapter(
        tmp_path / "uv-adapter",
        "import json, sys\n"
        "request = sys.stdin.read()\n"
        "print(json.dumps({'result': 'PASS', 'data': {'argv': sys.argv[1:], 'stdin': request}}))\n",
    )
    monkeypatch.setenv("UV", adapter)
    envelope: dict[str, object] = {"channel": channel, "request": {"operation": "x"}}

    result, data = asyncio.run(fixed_dispatch(channel, envelope))

    assert result == "PASS"
    assert data == {
        "argv": [
            "run",
            "--project",
            "services/api",
            "--locked",
            "--no-sync",
            "python",
            "-m",
            module,
        ],
        "stdin": encode_frame(envelope).decode(),
    }


def test_baseline_promote_takes_the_rationale_verbatim_from_the_environment(
    tmp_path: Path,
) -> None:
    """go-task re-renders CLI values as templates; the environment is verbatim."""
    adapter = recording_adapter(tmp_path)
    output = tmp_path / "arguments.json"
    rationale = 'it\'s "quoted" $HOME {{.X}}'
    environment = {
        **os.environ,
        "UV": str(adapter),
        "SIM_TEST_ARGUMENTS": str(output),
        "RATIONALE": rationale,
    }

    result = run_task(
        "sim-baseline-promote", "REPORT=r.json", cwd=CHECKOUT, env=environment
    )

    assert result.returncode == 0, result.stdout + result.stderr
    arguments = json.loads(output.read_text())
    assert [a for a in arguments if "--rationale" in a or a == rationale] in (
        [f"--rationale={rationale}"],
        ["--rationale", rationale],
    )


def test_baseline_promote_rejects_a_rationale_given_as_an_argument(
    tmp_path: Path,
) -> None:
    adapter = recording_adapter(tmp_path)
    output = tmp_path / "arguments.json"
    environment = {**os.environ, "UV": str(adapter), "SIM_TEST_ARGUMENTS": str(output)}
    environment.pop("RATIONALE", None)

    result = run_task(
        "sim-baseline-promote",
        "REPORT=r.json",
        "RATIONALE=some-text",
        cwd=CHECKOUT,
        env=environment,
    )

    assert result.returncode != 0
    assert (
        "RATIONALE must be set in the environment, not as an argument."
        in result.stderr.splitlines()
    )
    assert not output.exists(), "the guard must stop the task before UV runs"


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("REPOSITORY_ROOT", "/tmp/evil-repository-root"),
        ("SIM_SEMGREP_TARGETS", "/tmp/evil-simulator-target.py"),
        ("ROOT_DIR", "/tmp/evil-root-dir"),
        ("TASKFILE_DIR", "/tmp/evil-taskfile-dir"),
    ],
)
def test_simulator_semgrep_check_ignores_command_line_overrides_of_its_scope(
    variable: str, replacement: str
) -> None:
    """AC19: `NAME=value` cannot redirect the simulator Semgrep rules or targets."""
    result = run_task(
        "--dry",
        "--verbose",
        "sim-semgrep-check",
        f"{variable}={replacement}",
        cwd=CHECKOUT,
        env=dict(os.environ),
    )

    # go-task writes the dry-run echo to stderr.
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert replacement not in output
    assert f"{CHECKOUT.as_posix()}/.semgrep/simulator-rules" in output


@pytest.mark.parametrize(
    "command",
    [LAUNCHER_COMMAND, FIXTURE_LAUNCHER_COMMAND, INSPECTION_LAUNCHER_COMMAND],
    ids=["pool", "fixture", "inspection"],
)
def test_launchers_run_a_silent_task_the_taskfile_defines(command: list[str]) -> None:
    """Launcher stdout must be the JSON result alone, from a task that exists."""
    listing = run_task("--list-all", "--json", cwd=CHECKOUT, env=dict(os.environ))
    assert listing.returncode == 0, listing.stderr
    defined = {task["name"] for task in json.loads(listing.stdout)["tasks"]}

    assert command[:2] == ["task", "-s"]
    assert len(command) == 3
    assert command[2] in defined


HOST_FAIL_LINE = (
    "FAIL  The simulation host workflow needs macOS or Linux (WSL works); "
    "see docs/operations/simulation-host.md."
)
HOST_TASKS = [
    "sim-host-prepare",
    "sim-host-run",
    "sim-host-collect",
    "sim-host-release-export",
    "sim-host-release-load",
]


@pytest.mark.parametrize("task", HOST_TASKS)
def test_host_tasks_fail_fast_on_windows_and_are_unchanged_elsewhere(task: str) -> None:
    """D1, S3-8: no faithful Windows equivalent exists, so say so and exit 1.

    On Windows the real task runs with no arguments: it must stop with the exact
    line and exit 1 (not the missing-argument exit 2, and not a crash inside
    fcntl or directory-descriptor code). Elsewhere a dry run must still show the
    real launcher command and not the Windows message.
    Catches: a missing platforms split, a wrong exit code, or a changed message.
    """
    environment = {k: v for k, v in os.environ.items() if k != "UV"}
    if sys.platform == "win32":
        result = run_task(task, cwd=CHECKOUT, env=environment)
        assert result.returncode == 1, result.stdout + result.stderr
        assert HOST_FAIL_LINE in (result.stdout + result.stderr).splitlines()
        return

    dry = run_task("--dry", task, cwd=CHECKOUT, env=environment)
    assert dry.returncode == 0, dry.stderr
    assert HOST_FAIL_LINE not in dry.stdout + dry.stderr
    assert "tailtag_simulator.host_" in dry.stdout + dry.stderr
    block = re.search(
        rf"^  {task}:\n(.*?)(?=^  \S|\Z)",
        (CHECKOUT / "Taskfile.yml").read_text(),
        re.MULTILINE | re.DOTALL,
    )
    assert block is not None
    assert "platforms: [windows]" in block.group(1)
    assert "needs macOS or Linux (WSL works)" in block.group(1)
