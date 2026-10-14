"""TEMPORARY (#315 slice 1): reproduce the catalog test through task on Windows."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, "tests")
from report_support import literal_report, repository  # noqa: E402

NAME = "checkout space ' apostrophe $(touch SENTINEL-dollar) `touch SENTINEL-backtick`"
DESCRIPTOR = "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json"
checkout = Path("../..").resolve()
value = literal_report()["scenario"]
entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
root = repository(
    Path(tempfile.mkdtemp()).resolve() / NAME,
    {"Taskfile.yml": (checkout / "Taskfile.yml").read_text(), DESCRIPTOR: json.dumps(entry)},
)
adapter = root.parent / "adapter.py"
adapter.write_text(
    textwrap.dedent(
        """
        import os, subprocess, sys
        os.chdir(sys.argv[2])
        sys.stderr.write("argv=%r cwd=%r\\n" % (sys.argv[7:], os.getcwd()))
        body = "".join("    " + part + "\\n" for part in sys.argv[8].split("; "))
        wrapped = "import sys\\ntry:\\n" + body + "except BaseException as e:\\n    sys.stderr.write('context=%r\\\\n' % (e.__context__,))\\n    raise\\n"
        raise SystemExit(subprocess.call([sys.executable, "-c", wrapped, *sys.argv[9:]]))
        """
    )
)
uv = f"{Path(sys.executable).as_posix()} {adapter.as_posix()}"
env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
result = subprocess.run(
    ["task", "sim-catalog-check", f"UV={uv}"],
    cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
)
print("returncode:", result.returncode)
print(result.stdout[-1500:])
print(result.stderr[-2500:])
