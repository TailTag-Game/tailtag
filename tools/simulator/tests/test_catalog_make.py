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
