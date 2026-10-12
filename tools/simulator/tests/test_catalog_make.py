"""Run the real catalog Make recipe; replace only UV's environment launcher."""

import json
import os
import subprocess
import sys
from pathlib import Path

from report_support import literal_report, repository


def test_catalog_make_treats_quoted_checkout_root_as_data(tmp_path: Path) -> None:
    simulator = Path(__file__).parents[1]
    checkout = simulator.parents[1]
    value = literal_report()["scenario"]
    entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
    descriptor = "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json"
    root = repository(
        tmp_path
        / "checkout space ' apostrophe \" quote $(touch SENTINEL-dollar) `touch SENTINEL-backtick`",
        {
            "Makefile": (checkout / "Makefile").read_text(),
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
        return subprocess.run(
            ["make", "--no-print-directory", "sim-catalog-check", f"UV={adapter}"],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / "SENTINEL-dollar").exists()
    assert not (root / "SENTINEL-backtick").exists()
    # A recipe that loses the root and validates the installed catalog instead
    # must not pass: the selected checkout's current descriptor is now absent.
    (root / descriptor).unlink()
    assert run().returncode != 0


def test_convention_make_passes_bounded_config_and_report_paths_as_arguments(
    tmp_path: Path,
) -> None:
    checkout = Path(__file__).parents[3]
    adapter = tmp_path / "uv-adapter"
    output = tmp_path / "arguments.json"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['SIM_TEST_ARGUMENTS'], 'w') as stream:\n"
        "    json.dump(sys.argv[1:], stream)\n"
    )
    adapter.chmod(0o755)
    config = tmp_path / "config space.json"
    report_dir = tmp_path / "reports space"
    config.write_text('{"casual":2}')
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "sim-convention",
            f"UV={adapter}",
            "POOL=p1",
            "FAMILY=baseline",
            f"CONFIG={config}",
            "VERSION=1",
            "SEED=-42",
            f"REPORT_DIR={report_dir}",
        ],
        cwd=checkout,
        env={**os.environ, "SIM_TEST_ARGUMENTS": str(output)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
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
        "p1",
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
