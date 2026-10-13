"""Run the real root Taskfile; replace only the UV launcher the Taskfile exposes."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from report_support import literal_report, repository

from tailtag_simulator.host_bridge import fixed_dispatch
from tailtag_simulator.host_protocol import encode_frame

CHECKOUT = Path(__file__).parents[3]


def run_task(
    *arguments: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["task", *arguments],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def recording_adapter(tmp_path: Path) -> Path:
    """An external UV launcher stand-in that records its argv and succeeds."""
    adapter = tmp_path / "uv-adapter"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['SIM_TEST_ARGUMENTS'], 'w') as stream:\n"
        "    json.dump(sys.argv[1:], stream)\n"
    )
    adapter.chmod(0o755)
    return adapter


def test_catalog_check_treats_quoted_checkout_root_as_data(tmp_path: Path) -> None:
    simulator = Path(__file__).parents[1]
    value = literal_report()["scenario"]
    entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
    descriptor = "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json"
    root = repository(
        tmp_path
        / "checkout space ' apostrophe \" quote $(touch SENTINEL-dollar) `touch SENTINEL-backtick`",
        {
            "Taskfile.yml": (CHECKOUT / "Taskfile.yml").read_text(),
            descriptor: json.dumps(entry),
        },
    )
    # UV is an external environment/launcher boundary. Forward its bounded
    # invocation to this test's interpreter, keeping the recipe and validator real.
    adapter = tmp_path / "uv-adapter"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "assert sys.argv[1:7] == ['--directory', 'tools/simulator', 'run', '--locked', '--no-sync', 'python']\n"
        "os.chdir(sys.argv[2])\n"
        "os.execv(sys.executable, [sys.executable, *sys.argv[7:]])\n"
    )
    adapter.chmod(0o755)
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
    adapter = tmp_path / "uv-adapter"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "request = sys.stdin.read()\n"
        "print(json.dumps({'result': 'PASS', 'data': {'argv': sys.argv[1:], 'stdin': request}}))\n"
    )
    adapter.chmod(0o755)
    monkeypatch.setenv("UV", str(adapter))
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
    assert f"{CHECKOUT}/.semgrep/simulator-rules" in output
