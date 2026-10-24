"""Run the hybrid replica reset, provision and registry jobs (#355).

The nine private reset values come from an owner-only file and travel inside the
job request. They are never printed. A wrong confirm string or an unsafe file
stops the run before `gcloud` or any request, and the shared runner in
`scripts/api_replica_job.py` does the rest.

Run it with `task replica-reset -- --project <gcp-project-id> --source-sha <40 hex>
--operation reset|provision|registry [--confirm <string>] [--config <path>]`.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, Final

from scripts import api_replica_job as _job
from scripts import api_staging_reset_ssh as _reset_ssh

_read_configuration = _reset_ssh._read_configuration  # pyright: ignore[reportPrivateUsage]

DEFAULT_CONFIG_PATH: Final = Path.home() / ".config/tailtag/replica-reset.env"
_RESET_JOB: Final = "tailtag-replica-reset"
_REGISTRY_JOB: Final = "tailtag-replica-registry-reconcile"
_CONFIRMATIONS: Final = {
    "reset": "reset-tailtag-replica",
    "provision": "provision-tailtag-replica-reset",
}


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None) -> int:
    """Check the confirm string and the private file, then run the pinned job.

    `stdin` is accepted for the shared runner shape and is not read.
    """
    del stdin
    try:
        parser = _job.Parser(add_help=False)
        parser.add_argument("--project", required=True)
        parser.add_argument("--source-sha", required=True)
        parser.add_argument(
            "--operation", required=True, choices=("reset", "provision", "registry")
        )
        parser.add_argument("--confirm")
        parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
        arguments = parser.parse_args(argv)
        _job.valid_target(arguments.project, arguments.source_sha)
        operation: str = arguments.operation
        if operation != "registry" and arguments.confirm != _CONFIRMATIONS[operation]:
            raise ValueError
        configuration = _read_configuration(arguments.config)
    except Exception:  # noqa: BLE001
        print(_job.FAILURE)
        return 1
    if operation == "registry":
        job, body = _REGISTRY_JOB, {"configuration": configuration}
    else:
        job = _RESET_JOB
        body = {
            "operation": operation,
            "confirm": arguments.confirm,
            "configuration": configuration,
        }
    return _job.submit(arguments.project, arguments.source_sha, job, body)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
