"""Guarded offline operator entry point for the fixed Staging rehearsal baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, Protocol, Self

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from scripts.api_staging_preflight import validate_target

from rehearsal.baseline import BASELINE_VERSION

if TYPE_CHECKING:
    from rehearsal.safety import ResetConfiguration


class _Maintenance(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
    def quiesce(self) -> None: ...
    def resume(self) -> None: ...


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


def DatabaseMaintenance(configuration: ResetConfiguration) -> _Maintenance:
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
    try:
        initial_identity = validate_target(_TARGET)
    except Exception:  # noqa: BLE001
        return _fail("preflight")
    try:
        _bootstrap()
    except Exception:  # noqa: BLE001
        return _fail("configuration")
    try:
        configuration = load_configuration(os.environ)
    except Exception:  # noqa: BLE001
        return _fail("configuration")
    if arguments.provision:
        try:
            provision_identity(configuration)
        except Exception:  # noqa: BLE001
            return _fail("provision")
        print("Staging reset identity provisioned.")
        return 0
    try:
        with DatabaseMaintenance(configuration) as maintenance:
            try:
                maintenance.quiesce()
            except BaseException:  # noqa: BLE001
                return _fail("maintenance unknown")
            try:
                counts = reset_baseline(configuration)
            except BaseException:  # noqa: BLE001
                return _fail("maintenance retained")
            try:
                maintenance.resume()
                final_identity = validate_target(_TARGET)
                if final_identity != initial_identity:
                    raise RuntimeError
            except BaseException:  # noqa: BLE001
                try:
                    maintenance.quiesce()
                except Exception:  # noqa: BLE001
                    return _fail("maintenance unknown")
                return _fail("committed maintenance retained")
    except BaseException:  # noqa: BLE001
        return _fail("maintenance unknown")
    print(
        json.dumps(
            {
                "identity": initial_identity,
                "baseline_version": BASELINE_VERSION,
                "counts": counts,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
