"""Guarded offline operator entry point for the fixed Staging rehearsal baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from scripts.api_staging_preflight import validate_target

from rehearsal import procedure
from rehearsal.baseline import BASELINE_VERSION

if TYPE_CHECKING:
    from rehearsal.safety import ResetConfiguration


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


_TARGET = "https://staging.tailtag.app"


def _bootstrap() -> None:
    import django

    django.setup()


def load_configuration(environment: Mapping[str, str]) -> ResetConfiguration:
    from rehearsal.safety import load_configuration as implementation

    return implementation(environment)


def DatabaseMaintenance(configuration: ResetConfiguration) -> procedure.Maintenance:
    from rehearsal.safety import DatabaseMaintenance as implementation

    return implementation(configuration)


def reset_baseline(configuration: ResetConfiguration) -> dict[str, int]:
    from rehearsal.reset import reset_baseline as implementation

    return implementation(configuration)


def provision_identity(configuration: ResetConfiguration) -> None:
    from rehearsal.reset import provision_identity as implementation

    implementation(configuration)


def _arguments() -> argparse.Namespace | None:
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--confirm")
    try:
        return parser.parse_args()
    except (SystemExit, ValueError):
        return None


def _fail(phase: str) -> int:
    print(f"FAIL staging reset {phase}", file=sys.stderr)
    return 1


def main() -> int:
    """Run only the exact, confirmed provision or reset procedure."""
    arguments = _arguments()
    if arguments is None:
        return _fail("confirmation")
    expected = (
        "provision-tailtag-staging-reset"
        if arguments.provision
        else "reset-tailtag-staging"
    )
    if arguments.confirm != expected:
        return _fail("confirmation")
    outcome = procedure.run(
        provision=arguments.provision,
        preflight=lambda: validate_target(_TARGET),
        bootstrap=_bootstrap,
        load_configuration=lambda: load_configuration(os.environ),
        maintenance=DatabaseMaintenance,
        reset_baseline=reset_baseline,
        provision_identity=provision_identity,
    )
    if outcome.failure is not None:
        return _fail(outcome.failure)
    if arguments.provision:
        print("Staging reset identity provisioned.")
        return 0
    print(
        json.dumps(
            {
                "identity": outcome.identity,
                "baseline_version": BASELINE_VERSION,
                "counts": outcome.counts,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
