"""Run one guarded #204 reset or sentinel provision as a Render Staging job (#410).

The local launcher `scripts/api_staging_render_job.py` starts this module with
`python -m rehearsal.render_job`. The job binds its own image build and Render
runtime before any database work. It then prints exactly one line, which the
launcher reads back from the Render Logs API. All other process output is
suppressed, so no domain or setup message can leak a private value.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn

from rehearsal.baseline import BASELINE_VERSION

if TYPE_CHECKING:
    from rehearsal.safety import DatabaseMaintenance as _Maintenance
    from rehearsal.safety import ResetConfiguration

RESULT_PREFIX: Final = "TAILTAG-RENDER-JOB "
_BUILD_IDENTITY_PATH: Path = Path("/opt/tailtag/build-identity.json")
_CONFIRMATIONS: Final = {
    "reset": "reset-tailtag-staging",
    "provision": "provision-tailtag-staging-reset",
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


class _Failure(Exception):
    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def DatabaseMaintenance(configuration: ResetConfiguration) -> _Maintenance:
    from rehearsal.safety import DatabaseMaintenance as implementation

    return implementation(configuration)


def reset_baseline(configuration: ResetConfiguration) -> dict[str, int]:
    from rehearsal.reset import reset_baseline as implementation

    return implementation(configuration)


def provision_identity(configuration: ResetConfiguration) -> None:
    from rehearsal.reset import provision_identity as implementation

    implementation(configuration)


def validate_identity(configuration: ResetConfiguration) -> None:
    from rehearsal.safety import validate_identity as implementation

    implementation(configuration)


def _arguments(argv: list[str] | None) -> tuple[str, str]:
    parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--confirm", required=True)
    try:
        arguments = parser.parse_args(argv)
    except (SystemExit, ValueError):
        raise _Failure("confirmation") from None
    operation = arguments.operation
    if (
        operation not in _CONFIRMATIONS
        or arguments.confirm != _CONFIRMATIONS[operation]
    ):
        raise _Failure("confirmation")
    return operation, arguments.source_sha


def _bind_runtime(source_sha: str) -> None:
    """Require Render Staging, production settings, and an image built from S."""
    from config import build_identity, replacement_target_binding

    try:
        if (
            os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.production"
            or replacement_target_binding.runtime_host(os.environ) != "render"
            or replacement_target_binding.validate_runtime_target(os.environ)
            != "staging"
        ):
            raise _Failure("target")
        identity = build_identity._load_identity(  # pyright: ignore[reportPrivateUsage]
            _BUILD_IDENTITY_PATH, os.environ
        )
    except (ValueError, replacement_target_binding.TargetBindingError):
        raise _Failure("target") from None
    if identity["source_sha"] != source_sha or identity["environment"] != "staging":
        raise _Failure("target")


def _configuration() -> ResetConfiguration:
    import django

    try:
        django.setup()
        from rehearsal.safety import load_configuration

        return load_configuration(os.environ)
    except Exception:  # noqa: BLE001 - never leak a configuration value
        raise _Failure("configuration") from None


def _reset(configuration: ResetConfiguration) -> dict[str, int]:
    """Gate, reset, and reopen with the #204 retained-gate failure rules."""
    try:
        with DatabaseMaintenance(configuration) as maintenance:
            try:
                maintenance.quiesce()
            except BaseException:  # noqa: BLE001
                raise _Failure("maintenance unknown") from None
            try:
                counts = reset_baseline(configuration)
            except BaseException:  # noqa: BLE001
                raise _Failure("maintenance retained") from None
            try:
                maintenance.resume()
            except BaseException:  # noqa: BLE001
                try:
                    maintenance.quiesce()
                except BaseException:  # noqa: BLE001
                    raise _Failure("maintenance unknown") from None
                raise _Failure("committed maintenance retained") from None
    except _Failure:
        raise
    except BaseException:  # noqa: BLE001
        raise _Failure("maintenance unknown") from None
    return counts


def _provision(configuration: ResetConfiguration) -> None:
    try:
        provision_identity(configuration)
    except BaseException:  # noqa: BLE001
        raise _Failure("provision") from None
    try:
        validate_identity(configuration)
    except BaseException:  # noqa: BLE001
        raise _Failure("provision") from None


def _run(argv: list[str] | None) -> tuple[int, dict[str, object]]:
    operation: str | None = None
    try:
        operation, source_sha = _arguments(argv)
        _bind_runtime(source_sha)
        configuration = _configuration()
        result: dict[str, object] = {
            "operation": operation,
            "outcome": "PASS",
            "source_sha": source_sha,
        }
        if operation == "reset":
            result["baseline_version"] = BASELINE_VERSION
            result["counts"] = _reset(configuration)
        else:
            _provision(configuration)
            result["provision_postcondition"] = "PASS"
    except _Failure as failure:
        if failure.phase == "confirmation":
            return 1, {"outcome": "FAIL", "phase": "confirmation"}
        return 1, {"operation": operation, "outcome": "FAIL", "phase": failure.phase}
    except BaseException:  # noqa: BLE001 - an unknown failure is never success
        if operation is None:
            return 1, {"outcome": "FAIL", "phase": "confirmation"}
        phase = "maintenance unknown" if operation == "reset" else "provision"
        return 1, {"operation": operation, "outcome": "FAIL", "phase": phase}
    return 0, result


def _interrupted(*_: object) -> NoReturn:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    """Suppress all process output, then print the one result line."""
    # Render cancels a job with SIGTERM. Turn it into an interrupt so the
    # maintenance context still exits and the job still reports a phase.
    previous = signal.signal(signal.SIGTERM, _interrupted)
    saved = (os.dup(1), os.dup(2))
    try:
        with open(os.devnull, "wb", buffering=0) as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                status, result = _run(argv)
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        signal.signal(signal.SIGTERM, previous)
    line = RESULT_PREFIX + json.dumps(result, sort_keys=True, separators=(",", ":"))
    os.write(1, (line + "\n").encode("ascii"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
