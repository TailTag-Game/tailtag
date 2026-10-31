"""Run one #243 Staging operator command over `render ssh` (#410 AC9).

The local launcher starts this module with `python -m accounts.render_operator`
in an interactive `render ssh` session. Before any prompt, it binds the Render
Staging runtime and the image build to the expected source SHA. For the
lifecycle and managed commands, it then requires the read-only operator
inspector status that the Railway bootstrap required. For the emergency
commands, it binds the database to the pinned private values and keeps that
one physical connection for the whole command. The last line it prints is the
result. It names a command's failure message only when the message is in a
fixed allowlist, so the line can never carry a value.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Final, NoReturn, cast

if TYPE_CHECKING:
    from rehearsal.safety import ResetConfiguration

RESULT_PREFIX: Final = "TAILTAG-RENDER-OPERATOR "
# Each operation: its command, the command's options, and the operator
# inspector status it requires first, or None for a database binding instead.
_OPERATIONS: Final[dict[str, tuple[str, dict[str, str], str | None]]] = {
    "lifecycle-provision": (
        "staging_validation_operator",
        {"action": "provision"},
        "FAIL_LIMITED_OPERATOR_MISSING",
    ),
    "lifecycle-decommission": (
        "staging_validation_operator",
        {"action": "decommission"},
        "PASS",
    ),
    "lifecycle-rotate-password": (
        "staging_validation_operator",
        {"action": "rotate_password"},
        "PASS",
    ),
    "emergency-create": ("bootstrap_staging_emergency_operator", {}, None),
    "emergency-decommission": ("decommission_staging_emergency_operator", {}, None),
    "managed-password-rotate": ("rotate_staging_managed_password", {}, "PASS"),
    "managed-operator-replace": ("replace_staging_managed_operator", {}, "PASS"),
}
_IDENTITY_COMMANDS: Final = frozenset(
    {"rotate_staging_managed_password", "replace_staging_managed_operator"}
)
# Every fixed CommandError message of the five commands. A test fails when a
# command gains a message that this set does not hold.
COMMAND_MESSAGES: Final = frozenset(
    {
        "Audit prerequisite exceeds bounded inspection.",
        "Confirmation failed.",
        "Emergency operator bootstrap failed.",
        "Emergency operator decommission failed.",
        "Emergency operator state is unavailable.",
        "Existing account cannot be used as an emergency operator.",
        "Existing account cannot be used as an operator.",
        "Existing group cannot be used as an operator.",
        "Hidden terminal input is unavailable.",
        "Invalid command arguments.",
        "Invalid command arguments. Use the documented interactive command.",
        "Limited operator prerequisite failed.",
        "Managed operator postcondition failed.",
        "Managed operator replacement failed.",
        "Managed operator state changed.",
        "Managed password postcondition failed.",
        "Managed password rotation failed.",
        "Operator identifier is invalid.",
        "Operator identifier is unavailable.",
        "Password does not meet operator requirements.",
        "Passwords do not match.",
        "Query debugging must be disabled.",
        "Required operator permissions are unavailable.",
        "Staging database binding is unavailable.",
        "Staging prerequisite state changed.",
        "This command is unavailable for the current target.",
        "This command requires an interactive terminal.",
        "Validation operator action failed.",
        "Validation operator postcondition failed.",
    }
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


class _Failure(Exception):
    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def validate_database(configuration: ResetConfiguration) -> None:
    from rehearsal.safety import validate_database as implementation

    implementation(configuration)


def _arguments(argv: list[str] | None) -> tuple[str, str]:
    parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--operation", required=True, choices=tuple(_OPERATIONS))
    parser.add_argument("--source-sha", required=True)
    try:
        arguments = parser.parse_args(argv)
    except (SystemExit, ValueError):
        raise _Failure("arguments") from None
    return arguments.operation, arguments.source_sha


def _bind(source_sha: str) -> None:
    """Require a real terminal, Render Staging, and an image built from S."""
    from rehearsal import render_job

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise _Failure("terminal")
    try:
        render_job._bind_runtime(source_sha)  # pyright: ignore[reportPrivateUsage]
        render_job._setup()  # pyright: ignore[reportPrivateUsage]
    except render_job._Failure as failure:  # pyright: ignore[reportPrivateUsage]
        raise _Failure(failure.phase) from None


def _require_inspector(expected: str) -> None:
    from rehearsal import render_job

    status = render_job._read_only("inspect")  # pyright: ignore[reportPrivateUsage]
    if status.get("result") != expected:
        raise _Failure("precondition")


def _execute(name: str, options: dict[str, object]) -> None:
    import importlib

    from django.core.management import CommandError

    module = importlib.import_module(f"accounts.management.commands.{name}")
    try:
        module.Command().execute(
            force_color=False,
            no_color=False,
            skip_checks=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            **options,
        )
    except CommandError as error:
        message = str(error)
        raise _Failure(
            f"command: {message}" if message in COMMAND_MESSAGES else "command"
        ) from None


def _run_bound(name: str, options: dict[str, object]) -> None:
    """Bind the pinned database, and keep that one connection for the command."""
    from django.db import connection, transaction

    from rehearsal import render_job

    try:
        configuration = render_job._configuration()  # pyright: ignore[reportPrivateUsage]
    except render_job._Failure:  # pyright: ignore[reportPrivateUsage]
        raise _Failure("configuration") from None
    with transaction.atomic():
        try:
            validate_database(configuration)
        except Exception:  # noqa: BLE001 - never leak a database value
            raise _Failure("binding") from None
        physical = connection.connection
        _execute(name, options)
        if connection.connection is not physical:
            raise _Failure("binding")


def _run(argv: list[str] | None) -> tuple[int, str]:
    operation: str | None = None
    try:
        operation, source_sha = _arguments(argv)
        _bind(source_sha)
        name, arguments, inspector_status = _OPERATIONS[operation]
        options = cast(dict[str, object], dict(arguments))
        if name in _IDENTITY_COMMANDS:
            # Render sets no runtime deploy ID, so the expected one is None.
            options["expected_identity"] = {
                "environment": "staging",
                "source_sha": source_sha,
                "deployment_id": None,
            }
        if inspector_status is None:
            _run_bound(name, options)
        else:
            _require_inspector(inspector_status)
            _execute(name, options)
    except _Failure as failure:
        named = "" if operation is None else f" {operation}"
        return 1, f"FAIL{named} {failure.phase}"
    except BaseException as error:  # noqa: BLE001 - never success, always a line
        named = "" if operation is None else f" {operation}"
        phase = "interrupted" if isinstance(error, KeyboardInterrupt) else "unknown"
        return 1, f"FAIL{named} {phase}"
    return 0, f"PASS {operation}"


def main(argv: list[str] | None = None) -> int:
    status, result = _run(argv)
    print(RESULT_PREFIX + result, flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
