"""The in-image Render SSH entry point for the #243 operator commands (#410 AC9)."""

from __future__ import annotations

import getpass
import importlib
import json
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest

from accounts.models import User
from tests import test_staging_emergency_operator as emergency
from tests import test_staging_managed_operator_recovery as recovery
from tests import test_staging_validation_operator as lifecycle
from tests.test_render_job import SOURCE_SHA, pin_render_staging

PREFIX = "TAILTAG-RENDER-OPERATOR "


class Terminal(StringIO):
    def isatty(self) -> bool:
        return True


class Pipe(StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture
def operator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """Pinned Render Staging, an image built from SOURCE_SHA, and a terminal."""
    pin_render_staging(monkeypatch, tmp_path)
    module = importlib.import_module("accounts.render_operator")
    from config import build_identity

    monkeypatch.setattr(
        build_identity,
        "get_identity",
        lambda: {
            "environment": "staging",
            "source_sha": SOURCE_SHA,
            "deployment_id": None,
        },
    )
    return module


def inspector(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    module = importlib.import_module("rehearsal.operator_inspect")
    monkeypatch.setattr(module, "_inspect_orm_preconditions", lambda: status)


def answers(monkeypatch: pytest.MonkeyPatch, confirmation: str, *hidden: str) -> None:
    values = iter(hidden)
    monkeypatch.setattr("builtins.input", lambda _prompt="": confirmation)

    def read_hidden(_prompt: str = "", **_: object) -> str:
        return next(values)

    monkeypatch.setattr(getpass, "getpass", read_hidden)


def forbid_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_prompt: str = "", **_: object) -> NoReturn:
        raise AssertionError("a refused operation must not prompt")

    monkeypatch.setattr("builtins.input", forbidden)
    monkeypatch.setattr(getpass, "getpass", forbidden)


def run(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    source_sha: str = SOURCE_SHA,
    *,
    stdin: StringIO | None = None,
) -> tuple[int, str, str]:
    """Run in a fake terminal, and return the status, all output, and the result."""
    terminal = Terminal()
    monkeypatch.setattr(sys, "stdin", stdin or terminal)
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.setattr(sys, "stderr", Terminal())
    status = module.main(["--operation", operation, "--source-sha", source_sha])
    output = terminal.getvalue()
    return status, output, output.splitlines()[-1]


@pytest.mark.django_db
def test_rotate_runs_the_real_command_after_the_read_only_inspector_passes(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Render identity has no deploy ID, and the command proves its result."""
    recovery.seed_roles()
    inspector(monkeypatch, "PASS")
    answers(
        monkeypatch,
        "rotate Render Staging managed operator password",
        recovery.NEW_PASSWORD,
        recovery.NEW_PASSWORD,
    )

    status, output, result = run(operator, monkeypatch, "managed-password-rotate")

    assert status == 0
    assert "POSTCONDITION_PASS" in output
    assert result == PREFIX + "PASS managed-password-rotate"
    managed = User.objects.get(clerk_user_id=recovery.OLD_IDENTIFIER)
    assert managed.check_password(recovery.NEW_PASSWORD)


@pytest.mark.django_db
def test_emergency_create_binds_the_pinned_database_then_runs_the_command(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The AC5 pinned values bind the database before the first prompt."""
    emergency._install_registry()  # pyright: ignore[reportPrivateUsage]
    bound: list[object] = []
    # The entry point and the command each check the pinned database.
    safety = importlib.import_module("rehearsal.safety")
    monkeypatch.setattr(safety, "validate_database", bound.append)
    answers(
        monkeypatch,
        "bootstrap Render Staging emergency operator",
        emergency.IDENTIFIER,
        emergency.PASSWORD,
        emergency.PASSWORD,
    )

    status, _, result = run(operator, monkeypatch, "emergency-create")

    assert status == 0
    assert [getattr(item, "platform", None) for item in bound] == ["render", "render"]
    assert result == PREFIX + "PASS emergency-create"
    assert User.objects.filter(
        clerk_user_id=emergency.IDENTIFIER, is_superuser=True
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("operation", "status"),
    [
        # A new limited operator needs its absence first, the others need PASS.
        ("lifecycle-provision", "PASS"),
        ("lifecycle-rotate-password", "FAIL_LIMITED_OPERATOR_MISSING"),
    ],
)
def test_an_unexpected_inspector_status_refuses_before_any_prompt(
    operator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    status: str,
) -> None:
    inspector(monkeypatch, status)
    forbid_prompts(monkeypatch)

    assert run(operator, monkeypatch, operation)[::2] == (
        1,
        PREFIX + f"FAIL {operation} precondition",
    )


@pytest.mark.django_db
def test_a_database_that_does_not_match_the_pin_refuses_before_any_prompt(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = importlib.import_module("rehearsal.safety")

    def mismatch(_configuration: object) -> NoReturn:
        raise safety.ResetSafetyError

    monkeypatch.setattr(operator, "validate_database", mismatch)
    forbid_prompts(monkeypatch)

    assert run(operator, monkeypatch, "emergency-decommission")[::2] == (
        1,
        PREFIX + "FAIL emergency-decommission binding",
    )


@pytest.mark.parametrize(
    ("case", "phase"),
    [
        ("unknown-operation", "arguments"),
        ("not-a-terminal", "terminal"),
        ("other-build", "target"),
    ],
)
def test_entry_point_refuses_before_django_work(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch, case: str, phase: str
) -> None:
    forbid_prompts(monkeypatch)
    operation, source_sha, stdin = "lifecycle-provision", SOURCE_SHA, None
    if case == "unknown-operation":
        operation = "matrix"
    elif case == "not-a-terminal":
        stdin = Pipe()
    else:
        source_sha = "a" * 40

    status, _, result = run(operator, monkeypatch, operation, source_sha, stdin=stdin)

    named = "" if phase == "arguments" else f" {operation}"
    assert (status, result) == (1, PREFIX + f"FAIL{named} {phase}")


@pytest.mark.django_db
def test_a_command_failure_reports_its_fixed_message(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commands raise only fixed messages, so the operator sees the reason."""
    recovery.seed_roles()
    inspector(monkeypatch, "PASS")
    answers(monkeypatch, "rotate Railway Staging managed operator password")

    assert run(operator, monkeypatch, "managed-password-rotate")[::2] == (
        1,
        PREFIX + "FAIL managed-password-rotate command: Confirmation failed.",
    )
    managed = User.objects.get(clerk_user_id=recovery.OLD_IDENTIFIER)
    assert managed.check_password(recovery.OLD_PASSWORD)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("bound", "state"),
    [(True, "ABSENT"), (True, "MISMATCH"), (False, "FAIL_BINDING")],
)
def test_emergency_state_job_reads_the_state_after_the_database_binding(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bound: bool,
    state: str,
) -> None:
    """The PR 2 launcher reads this before and after an emergency command."""
    pin_render_staging(monkeypatch, tmp_path)
    job = importlib.import_module("rehearsal.render_job")
    safety = importlib.import_module("rehearsal.safety")

    def binding(_configuration: object) -> None:
        if not bound:
            raise safety.ResetSafetyError

    monkeypatch.setattr(job, "validate_database", binding)
    if state == "MISMATCH":
        emergency_module = importlib.import_module(emergency.COMMAND_MODULE)
        monkeypatch.setattr(emergency_module, "inspect_emergency_state", lambda: state)

    status = job.main(["--operation", "emergency-state", "--source-sha", SOURCE_SHA])

    line = capfd.readouterr().out.strip()
    assert line.startswith("TAILTAG-RENDER-JOB ")
    assert (status, json.loads(line.removeprefix("TAILTAG-RENDER-JOB "))) == (
        0 if state == "ABSENT" else 1,
        {
            "operation": "emergency-state",
            "outcome": "PASS" if state == "ABSENT" else "FAIL",
            "source_sha": SOURCE_SHA,
            "result": state,
        },
    )


@pytest.mark.django_db
def test_lifecycle_provision_runs_its_action_after_the_operator_is_absent(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provision needs the limited operator missing, and runs the provision action."""
    inspector(monkeypatch, "FAIL_LIMITED_OPERATOR_MISSING")
    answers(
        monkeypatch,
        "provision Render Staging validation operator",
        lifecycle.OPERATOR_IDENTIFIER,
        lifecycle.INITIAL_PASSWORD,
        lifecycle.INITIAL_PASSWORD,
    )

    status, _, result = run(operator, monkeypatch, "lifecycle-provision")

    assert (status, result) == (0, PREFIX + "PASS lifecycle-provision")
    lifecycle.assert_exact_active_limited_role(
        User.objects.get(clerk_user_id=lifecycle.OPERATOR_IDENTIFIER),
        lifecycle.INITIAL_PASSWORD,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["unlisted-message", "interrupt"])
def test_an_unlisted_message_or_an_interrupt_still_ends_with_a_fixed_line(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A future message with a value never reaches the line, and Ctrl-C reports."""
    from django.core.management import CommandError

    recovery.seed_roles()
    inspector(monkeypatch, "PASS")

    def confirm(_prompt: str = "") -> NoReturn:
        if failure == "interrupt":
            raise KeyboardInterrupt
        raise CommandError("operator staging_managed_secret_value is unavailable")

    monkeypatch.setattr("builtins.input", confirm)

    status, output, result = run(operator, monkeypatch, "managed-password-rotate")

    phase = "interrupted" if failure == "interrupt" else "command"
    assert (status, result) == (1, PREFIX + f"FAIL managed-password-rotate {phase}")
    assert "secret_value" not in output


@pytest.mark.django_db(transaction=True)
def test_emergency_command_fails_when_its_physical_connection_changes(
    operator: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned binding holds only for the one connection it checked."""
    from django.db import connection

    def bound(_configuration: object) -> None:
        return None

    monkeypatch.setattr(operator, "validate_database", bound)
    connection.ensure_connection()
    original = connection.connection
    replacement = connection.get_new_connection(connection.get_connection_params())

    def swap(_name: str, _options: object) -> None:
        connection.connection = replacement

    monkeypatch.setattr(operator, "_execute", swap)
    try:
        status, _, result = run(operator, monkeypatch, "emergency-create")
    finally:
        # The atomic block began on the original handle and ended on the
        # replacement, so end the original transaction for the next test.
        connection.connection = original
        original.rollback()
        original.autocommit = True
        replacement.close()

    assert (status, result) == (1, PREFIX + "FAIL emergency-create binding")


def test_every_fixed_command_message_is_in_the_allowlist() -> None:
    """A new literal message must be added on purpose before the line names it."""
    import ast

    from accounts import render_operator

    root = Path(render_operator.__file__).parent / "management" / "commands"
    operations = render_operator._OPERATIONS  # pyright: ignore[reportPrivateUsage]
    messages: set[str] = set()
    for name in {spec[0] for spec in operations.values()}:
        tree = ast.parse((root / f"{name}.py").read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "CommandError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                messages.add(cast(str, node.args[0].value))
    assert len(messages) > 20
    assert messages <= render_operator.COMMAND_MESSAGES
