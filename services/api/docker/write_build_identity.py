"""Write the immutable build identity artifact for the production image."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
# Each host passes the commit under its own build argument name.
_ARGUMENTS = ("RAILWAY_GIT_COMMIT_SHA", "RENDER_GIT_COMMIT")


def main(argv: list[str]) -> int:
    """Write {"source_sha": ...} to argv[1], or fail without writing."""
    if len(argv) != 2:
        print("usage: write_build_identity.py OUTPUT_PATH", file=sys.stderr)
        return 2
    values = {os.environ.get(name, "") for name in _ARGUMENTS} - {""}
    if len(values) > 1 or not all(_SOURCE_SHA.fullmatch(value) for value in values):
        print("conflicting or malformed build source SHA", file=sys.stderr)
        return 1
    path = Path(argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source_sha": next(iter(values), None)}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
