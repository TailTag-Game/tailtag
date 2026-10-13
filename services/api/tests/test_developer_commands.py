"""Repository-root backend developer command contracts (go-task)."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
import tomllib
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.semgrep_support import (
    FROZEN_ROOT_HELPERS,
    dry_run_commands,
    run_task,
    task_dry_run,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTH_SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_auth_smoke.py"
STAGING_AUTH_SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_auth_smoke.py"
MEDIA_STORAGE_SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_media_storage_smoke.py"
LIVE_SMOKE_HELPERS = (
    AUTH_SMOKE_SCRIPT,
    STAGING_AUTH_SMOKE_SCRIPT,
    MEDIA_STORAGE_SMOKE_SCRIPT,
)
SEMGREP_VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_semgrep_contract.py"
SEMGREP_RULES_DIRECTORY = REPOSITORY_ROOT / ".semgrep" / "rules"
SEMGREP_FIXTURES_DIRECTORY = REPOSITORY_ROOT / ".semgrep" / "tests"
FROZEN_SEMGREP_SOURCE_TARGETS = {
    REPOSITORY_ROOT / "services" / "api",
    *(REPOSITORY_ROOT / helper for helper in FROZEN_ROOT_HELPERS),
}
CANONICAL_UV_RUN_CHILD_EXECUTABLES = frozenset(
    {"ruff", "pyright", "pytest", "python", "semgrep", "gunicorn"}
)
CANONICAL_UV_RUN_OPTIONS = frozenset({"--locked", "--no-sync", "--offline"})
# go-task's silent-failure footer is the only line a failed silent task adds.
MEDIA_STORAGE_SMOKE_TASK_FAILURE_FOOTER = re.compile(
    r'task: Failed to run task "api-media-storage-smoke": exit status [1-9]\d*'
)


def as_dry_run(*commands: str) -> str:
    """Render raw commands in go-task's dry-run format for checker self-tests."""
    return "\n".join(f"task: [injected] {command}" for command in commands)


def workflow_text() -> str:
    """Return every checked-in workflow as one searchable document."""
    return "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )


def assert_live_helpers_are_only_statically_analyzed(dry_run: str) -> None:
    """Allow live-smoke helpers in api-check only as Ruff or Semgrep operands."""
    modules = {f"scripts.{helper.stem}": helper for helper in LIVE_SMOKE_HELPERS}
    referenced: set[Path] = set()
    for command in dry_run_commands(dry_run):
        tokens = shlex.split(command)
        mentioned = {
            modules.get(token, resolve_repository_operand(token)) for token in tokens
        } & set(LIVE_SMOKE_HELPERS)
        if not mentioned:
            continue
        referenced |= mentioned
        assert "-m" not in tokens and "python" not in tokens, command
        if "semgrep" in tokens:
            assert len(semgrep_scan_tokens(as_dry_run(command))) == 1, command
        else:
            assert "ruff" in tokens, command
            assert tokens[tokens.index("ruff") + 1] in {"format", "check"}, command
    assert referenced == set(LIVE_SMOKE_HELPERS), "api-check must analyze each helper"


def assert_api_check_uv_runs_are_locked_and_no_sync(dry_run: str) -> None:
    """Require every executable uv invocation to use the approved run grammar."""
    invocation = re.compile(r"(?<![\w./-])(?:\S*/)?uv\b(?P<body>[^;|&()\n]*)")
    option_regions = [
        (command, uv_run_option_region(match.group("body")))
        for command in dry_run_commands(dry_run)
        for match in invocation.finditer(command)
    ]
    assert option_regions, "api-check must execute uv run commands"
    for command, option_region in option_regions:
        assert "--locked" in option_region, command
        assert "--no-sync" in option_region, command


def uv_run_option_region(arguments: str) -> list[str]:
    """Parse the approved uv invocation grammar through its child executable."""
    tokens = shlex.split(arguments)
    assert "run" in tokens, arguments
    run_index = tokens.index("run")
    global_options = tokens[:run_index]
    assert not global_options or (
        len(global_options) == 2
        and global_options[0] == "--directory"
        and not global_options[1].startswith("-")
    ), arguments

    child_index = next(
        (
            index
            for index in range(run_index + 1, len(tokens))
            if tokens[index] in CANONICAL_UV_RUN_CHILD_EXECUTABLES
        ),
        None,
    )

    assert child_index is not None, arguments
    run_options = tokens[run_index + 1 : child_index]
    assert set(run_options) <= CANONICAL_UV_RUN_OPTIONS, arguments
    assert len(run_options) == len(set(run_options)), arguments
    return run_options


def resolve_repository_operand(operand: str) -> Path:
    """Resolve a Make command operand from the repository root."""
    path = Path(operand)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    return path.resolve()


def semgrep_scan_tokens(dry_run: str) -> list[list[str]]:
    """Parse Semgrep scan commands emitted by a Make dry run."""
    commands = [line for line in dry_run_commands(dry_run) if "semgrep scan" in line]
    assert commands, "Semgrep validation must execute scan commands"

    tokens_by_command: list[list[str]] = []
    for command in commands:
        assert not any(
            operator in command
            for operator in ("&&", "||", ";", "|", "`", "$(", "${", ">", "<")
        ), command
        tokens = shlex.split(command)
        reviewed_registry_targets = {
            str(REPOSITORY_ROOT / helper)
            for helper in (
                "scripts/api_staging_registry_reconcile.py",
                "scripts/api_staging_registry_reconcile_remote.py",
            )
            if helper in FROZEN_ROOT_HELPERS
        }
        target_operands = semgrep_target_operands(tokens)
        lowered = " ".join(
            token
            for token in tokens
            if token not in reviewed_registry_targets or token not in target_operands
        ).lower()
        assert not any(
            forbidden in lowered
            for forbidden in (
                "http://",
                "https://",
                "registry",
                "login",
                "account",
                "prompt",
                "upload",
                "publish",
                ".env",
                "docker",
                "migrate",
            )
        ), command
        assert all(
            "token" not in token.lower() or token == "SEMGREP_APP_TOKEN="
            for token in tokens
        ), command

        semgrep_index = tokens.index("semgrep")
        assert semgrep_index >= 6, (
            "Semgrep command requires at least six launcher-prefix tokens"
        )
        assert tokens[semgrep_index : semgrep_index + 2] == ["semgrep", "scan"]
        assert tokens[semgrep_index - 5 : semgrep_index] == [
            "--directory",
            ".semgrep",
            "run",
            "--locked",
            "--no-sync",
        ]
        launcher = tokens[semgrep_index - 6]
        assert Path(launcher).name == "uv"
        assert all("=" in token for token in tokens[: semgrep_index - 6])
        tokens_by_command.append(tokens)

    return tokens_by_command


def semgrep_config_operands(tokens: list[str]) -> list[str]:
    """Return explicit Semgrep configuration operands from a scan command."""
    operands: list[str] = []
    for index, token in enumerate(tokens):
        if token == "--config":
            operands.append(tokens[index + 1])
        elif token.startswith("--config="):
            operands.append(token.removeprefix("--config="))
    return operands


def semgrep_target_operands(tokens: list[str]) -> set[str]:
    """Return positional operands after `semgrep scan` from a parsed command."""
    scan_index = tokens.index("scan")
    operands: set[str] = set()
    skip_next = False
    for token in tokens[scan_index + 1 :]:
        if skip_next:
            skip_next = False
        elif token in {"--config", "--baseline-commit"}:
            skip_next = True
        elif token in {
            "--test",
            "--error",
            "--metrics=off",
            "--disable-version-check",
        } or token.startswith("--config="):
            continue
        elif token.startswith("-"):
            raise AssertionError(f"unexpected Semgrep option: {token}")
        else:
            operands.add(token)
    return operands


def assert_semgrep_check_contract(dry_run: str) -> None:
    """Require separate local fixture and blocking Semgrep scans with frozen scopes."""
    commands = semgrep_scan_tokens(dry_run)
    assert len(commands) == 2

    fixture_commands = [command for command in commands if "--test" in command]
    blocking_commands = [command for command in commands if "--test" not in command]
    assert len(fixture_commands) == 1
    assert len(blocking_commands) == 1

    for command in commands:
        assert semgrep_config_operands(command) == [str(SEMGREP_RULES_DIRECTORY)]
        assert "--metrics=off" in command
        assert "--disable-version-check" in command
        baseline_index = command.index("--baseline-commit")
        assert command[baseline_index + 1] == ""
        environment = {
            name: value
            for name, value in (
                token.split("=", maxsplit=1)
                for token in command[: command.index("semgrep") - 6]
            )
        }
        assert environment["SEMGREP_SEND_METRICS"] == "off"
        assert environment["SEMGREP_ENABLE_VERSION_CHECK"] == "0"
        assert environment["SEMGREP_BASELINE_COMMIT"] == ""
        assert environment["SEMGREP_APP_TOKEN"] == ""
        assert environment["SEMGREP_RULES"] == ""

    fixture_command = fixture_commands[0]
    assert "--error" not in fixture_command
    assert semgrep_target_operands(fixture_command) == {str(SEMGREP_FIXTURES_DIRECTORY)}

    blocking_command = blocking_commands[0]
    assert "--error" in blocking_command
    assert {
        resolve_repository_operand(operand)
        for operand in semgrep_target_operands(blocking_command)
    } == {target.resolve() for target in FROZEN_SEMGREP_SOURCE_TARGETS}


def assert_semgrep_validator_precedes_fixture_scan(dry_run: str) -> None:
    """Require the locked API validator immediately before Semgrep fixture testing."""
    commands = dry_run_commands(dry_run)
    tokenized_commands = [shlex.split(command) for command in commands]
    validator_indexes = [
        index
        for index, tokens in enumerate(tokenized_commands)
        if len(tokens) >= 8
        and Path(tokens[0]).name == "uv"
        and tokens[1:7]
        == [
            "--directory",
            "services/api",
            "run",
            "--locked",
            "--no-sync",
            "python",
        ]
        and tokens[7] == str(SEMGREP_VALIDATOR)
    ]
    assert len(validator_indexes) == 1
    validator_tokens = tokenized_commands[validator_indexes[0]]
    assert Path(validator_tokens[0]).name == "uv"
    assert validator_tokens[1:7] == [
        "--directory",
        "services/api",
        "run",
        "--locked",
        "--no-sync",
        "python",
    ]
    assert validator_tokens[7:] == [
        str(SEMGREP_VALIDATOR),
        "--rules",
        str(SEMGREP_RULES_DIRECTORY),
        "--fixtures",
        str(SEMGREP_FIXTURES_DIRECTORY),
    ]

    fixture_indexes = [
        index
        for index, command in enumerate(commands)
        if "semgrep scan --test" in command
    ]
    assert fixture_indexes == [validator_indexes[0] + 1]


class SmokeHandler(BaseHTTPRequestHandler):
    """Serve the API routes expected by the smoke command."""

    def do_GET(self) -> None:
        if self.path in {"/health/live", "/health/ready", "/api/schema/", "/api/docs/"}:
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *_args: object) -> None:
        """Keep test output focused on command behavior."""


class UnreadySmokeHandler(SmokeHandler):
    """Serve an unavailable readiness endpoint for smoke failure coverage."""

    def do_GET(self) -> None:
        if self.path == "/health/ready":
            self.send_response(503)
            self.end_headers()
            return
        super().do_GET()


class RedirectingSmokeHandler(SmokeHandler):
    """Redirect liveness to ensure smoke checks inspect the original status."""

    def do_GET(self) -> None:
        if self.path == "/health/live":
            self.send_response(302)
            self.send_header("Location", "/api/docs/")
            self.end_headers()
            return
        super().do_GET()


class FailingSmokeHandler(SmokeHandler):
    """Return failures from more than one required endpoint."""

    def do_GET(self) -> None:
        if self.path in {"/health/live", "/health/ready"}:
            self.send_response(503)
            self.end_headers()
            return
        super().do_GET()


@contextmanager
def smoke_server(
    handler: type[BaseHTTPRequestHandler] = SmokeHandler,
) -> Generator[str]:
    """Provide a local HTTP server with the expected smoke routes."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_bare_task_lists_commands_and_exits_zero() -> None:
    """AC16: running `task` with no arguments is a listing, not an error."""
    completed = run_task()

    assert completed.returncode == 0, completed.stderr
    assert "api-check" in completed.stdout


def test_uv_grammar_checker_accepts_approved_options_in_any_order() -> None:
    assert_api_check_uv_runs_are_locked_and_no_sync(
        as_dry_run(
            "uv --directory services/api run --offline --no-sync --locked pytest -q"
        )
    )


@pytest.mark.parametrize(
    "command",
    [
        "uv run --project services/api pytest -q",
        "uv run --locked --project services/api pytest -q",
        "uv --directory services/api run pytest -q --locked --no-sync",
        "uv run --locked --no-sync custom-validator",
        "uv pip install injected-package",
        "uv --directory services/api sync --locked",
        "uv run --locked --no-sync --with injected-package pytest -q",
        "uv run --locked --no-sync --python 3.13 pytest -q",
        "uv run --locked --no-sync --env-file path pytest -q",
    ],
)
def test_uv_grammar_checker_rejects_unlocked_or_environment_shaping_calls(
    command: str,
) -> None:
    """Invariant: every executable uv call is the locked, no-sync run form."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            as_dry_run(
                "uv --directory services/api run --locked --no-sync pytest -q",
                command,
            )
        )


def test_semgrep_checker_allows_only_the_trusted_prefix_and_reviewed_targets() -> None:
    command = (
        "SEMGREP_APP_TOKEN= uv --directory .semgrep run --locked --no-sync "
        "semgrep scan --config .semgrep/rules"
    )
    reviewed = [
        str(REPOSITORY_ROOT / "scripts/api_staging_registry_reconcile.py"),
        str(REPOSITORY_ROOT / "scripts/api_staging_registry_reconcile_remote.py"),
    ]
    accepted = " ".join((command, ".semgrep/tests", *reviewed))

    assert semgrep_scan_tokens(as_dry_run(accepted)) == [shlex.split(accepted)]
    for rejected in (
        command.replace("SEMGREP_APP_TOKEN=", "SEMGREP_APP_TOKEN=secret"),
        f"{accepted} {REPOSITORY_ROOT / 'scripts/api_staging_registry_unreviewed.py'}",
        f"{accepted} --registry=untrusted",
        "semgrep scan --config .semgrep/rules .semgrep/tests",
    ):
        with pytest.raises(AssertionError):
            semgrep_scan_tokens(as_dry_run(rejected))


def test_semgrep_validator_preflight_rejects_a_second_python_execution() -> None:
    """A scan target mention is allowed, but a second validator execution is not."""
    dry_run = task_dry_run("api-semgrep-check").stdout
    validator = next(
        command
        for command in dry_run_commands(dry_run)
        if shlex.split(command)[7:8] == [str(SEMGREP_VALIDATOR)]
    )

    with pytest.raises(AssertionError):
        assert_semgrep_validator_precedes_fixture_scan(
            f"{dry_run}\n{as_dry_run(validator)}"
        )


def test_check_composes_every_required_backend_validation() -> None:
    """The full check runs CI-equivalent validation in order without mutation."""
    dry_run = task_dry_run("api-check").stdout
    executed = [
        command
        for command in dry_run_commands(dry_run)
        if not command.startswith(("printf ", "echo "))
    ]

    ordered_steps = (
        "ruff format --check .",
        "ruff check .",
        "pyright",
        "semgrep scan --test",
        "pytest -q",
        "manage.py check",
        "makemigrations --check --dry-run",
        "spectacular --validate",
        "gunicorn config.wsgi:application --check-config",
    )
    positions = [
        next(index for index, command in enumerate(executed) if step in command)
        for step in ordered_steps
    ]
    assert positions == sorted(set(positions)), "steps must exist in this order"

    joined = "\n".join(executed)
    for forbidden in (
        " sync ",
        "docker compose",
        "manage.py migrate",
        "Clerk Development secret:",
        "CLERK_SECRET",
    ):
        assert forbidden not in joined
    assert_semgrep_check_contract(dry_run)
    assert_semgrep_validator_precedes_fixture_scan(dry_run)
    assert_api_check_uv_runs_are_locked_and_no_sync(dry_run)
    assert_live_helpers_are_only_statically_analyzed(dry_run)


def test_semgrep_check_is_local_locked_noninteractive_and_credential_free() -> None:
    """The static security gate scans local sources without external Semgrep services."""
    dry_run = task_dry_run("api-semgrep-check").stdout

    execution_lines = [
        line
        for line in dry_run_commands(dry_run)
        if line.strip() and not line.lstrip().startswith(("echo ", "printf "))
    ]
    assert len(execution_lines) == 3
    assert str(SEMGREP_VALIDATOR) in execution_lines[0]
    assert all("semgrep scan" in line for line in execution_lines[1:])
    for forbidden in (".env", "docker", "migrate"):
        assert forbidden not in dry_run.lower()
    assert_semgrep_check_contract(dry_run)
    assert_semgrep_validator_precedes_fixture_scan(dry_run)


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("SEMGREP_RULES", "/tmp/untrusted-semgrep-rules"),
        ("SEMGREP_TESTS", "/tmp/untrusted-semgrep-fixtures"),
        ("SEMGREP_TARGETS", "/tmp/untrusted-semgrep-target"),
        ("SEMGREP", "untrusted-semgrep-launcher"),
        ("SEMGREP_DIRECTORY", "/tmp/untrusted-semgrep-directory"),
        ("API_DIRECTORY", "/tmp/untrusted-api-directory"),
        ("SEMGREP_VALIDATOR", "/tmp/untrusted-semgrep-validator.py"),
        ("SEMGREP_BASELINE_COMMIT", "untrusted-baseline-commit"),
        ("SEMGREP_APP_TOKEN", "untrusted-token"),
    ],
)
def test_semgrep_check_ignores_inherited_environment_for_its_security_inputs(
    variable: str, replacement: str
) -> None:
    """Only the task definition selects the Semgrep executable, scope, and settings."""
    dry_run = task_dry_run(
        "api-semgrep-check", environment={variable: replacement}
    ).stdout

    assert replacement not in dry_run
    assert_semgrep_check_contract(dry_run)
    assert_semgrep_validator_precedes_fixture_scan(dry_run)


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("REPOSITORY_ROOT", "/tmp/evil-repository-root"),
        ("API_HELPERS", "/tmp/evil-api-helper.py"),
        ("ROOT_DIR", "/tmp/evil-root-dir"),
        ("TASKFILE_DIR", "/tmp/evil-taskfile-dir"),
    ],
)
def test_semgrep_check_ignores_command_line_overrides_of_its_security_inputs(
    variable: str, replacement: str
) -> None:
    """AC19: Make's `override` blocked `NAME=value`; go-task must block it too."""
    dry_run = task_dry_run("api-semgrep-check", f"{variable}={replacement}").stdout

    assert replacement not in dry_run
    assert_semgrep_check_contract(dry_run)
    assert_semgrep_validator_precedes_fixture_scan(dry_run)


@pytest.mark.parametrize("uv_channel", ["environment", "command_line"])
def test_uv_override_selects_the_launcher_without_altering_the_semgrep_contract(
    tmp_path: Path, uv_channel: str
) -> None:
    """AC13: UV is overridable by environment and argument; nothing else moves."""
    custom_uv = tmp_path / "uv"
    custom_uv.write_text("#!/bin/sh\nexit 0\n")
    custom_uv.chmod(0o755)

    if uv_channel == "environment":
        completed = task_dry_run(
            "api-semgrep-check", environment={"UV": str(custom_uv)}
        )
    else:
        completed = task_dry_run("api-semgrep-check", f"UV={custom_uv}")

    commands = [shlex.split(command) for command in dry_run_commands(completed.stdout)]
    validator_command = next(
        command for command in commands if str(SEMGREP_VALIDATOR) in command
    )
    assert validator_command[0] == str(custom_uv)
    for command in semgrep_scan_tokens(completed.stdout):
        assert command[command.index("semgrep") - 6] == str(custom_uv)
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)


def test_setup_synchronizes_both_locked_projects() -> None:
    """Setup prepares both projects; api-check never syncs (see composition test)."""
    joined = "\n".join(dry_run_commands(task_dry_run("api-setup").stdout))

    assert "uv --directory services/api sync --all-groups --locked" in joined
    assert "uv --directory .semgrep sync --locked" in joined


def test_strict_type_check_includes_the_root_helpers() -> None:
    """Root helpers and the CI classifier receive strict Pyright coverage."""
    pyright = tomllib.loads(
        (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()
    )["tool"]["pyright"]

    assert pyright["typeCheckingMode"] == "strict"
    for script in (
        "backend_ci_relevance.py",
        "validate_semgrep_contract.py",
        "api_auth_smoke.py",
        "api_staging_auth_smoke.py",
        "api_media_storage_smoke.py",
        "api_environment_fingerprint.py",
        "clerk_development_session.py",
    ):
        assert f"../../scripts/{script}" in pyright["include"]


def test_only_named_migration_tasks_change_migration_or_schema_state() -> None:
    non_mutating = (
        "api-setup",
        "api-run",
        "api-test",
        "api-shell",
        "api-smoke",
        "api-auth-smoke",
        "api-staging-auth-smoke",
        "api-media-storage-smoke",
    )
    for task in non_mutating:
        dry_run = task_dry_run(task).stdout
        for forbidden in (
            "docker compose",
            "python manage.py migrate",
            "python manage.py makemigrations",
        ):
            assert forbidden not in dry_run, task

    assert "python manage.py migrate" in task_dry_run("api-migrate").stdout
    assert "python manage.py makemigrations" in task_dry_run("api-migrations").stdout


@pytest.mark.parametrize(
    ("task", "module", "settings_module"),
    [
        ("api-auth-smoke", "scripts.api_auth_smoke", None),
        ("api-staging-auth-smoke", "scripts.api_staging_auth_smoke", None),
        (
            "api-media-storage-smoke",
            "scripts.api_media_storage_smoke",
            "config.settings.production",
        ),
    ],
)
def test_live_smoke_tasks_are_explicit_locked_module_runs(
    task: str, module: str, settings_module: str | None
) -> None:
    commands = [
        command
        for command in dry_run_commands(task_dry_run(task).stdout)
        if not command.startswith(("printf ", "echo "))
    ]

    assert len(commands) == 1
    assert (
        f"run --project services/api --locked --no-sync python -m {module}"
        in commands[0]
    )
    if settings_module:
        assert f"DJANGO_SETTINGS_MODULE={settings_module}" in commands[0]


@pytest.mark.parametrize(
    "execution",
    [
        "uv --directory services/api run --locked --no-sync python scripts/./api_media_storage_smoke.py",
        "uv --directory services/api run --locked --no-sync python -m scripts.api_auth_smoke",
        "bash scripts/api_staging_auth_smoke.py",
        "env /usr/bin/python scripts/api_media_storage_smoke.py",
    ],
)
def test_api_check_rejects_every_live_smoke_helper_execution(execution: str) -> None:
    """Static analysis of the helpers is allowed; executing any of them is not."""
    api_check = task_dry_run("api-check").stdout

    with pytest.raises(AssertionError):
        assert_live_helpers_are_only_statically_analyzed(
            f"{api_check}\n{as_dry_run(execution)}"
        )


def test_api_check_accepts_normalized_static_analysis_of_a_live_smoke_helper() -> None:
    api_check = task_dry_run("api-check").stdout
    static = (
        "uv --directory services/api run --locked --no-sync "
        "ruff check scripts/./api_auth_smoke.py"
    )

    assert_live_helpers_are_only_statically_analyzed(
        f"{api_check}\n{as_dry_run(static)}"
    )


def test_ordinary_smoke_and_ci_remain_noninteractive_and_credential_free() -> None:
    """CI and the ordinary smoke must not gain a secret, prompt, or live Clerk path."""
    ordinary = task_dry_run("api-smoke").stdout

    for text in (ordinary, workflow_text()):
        assert "api-auth-smoke" not in text
        assert "scripts.api_auth_smoke" not in text
        assert "scripts/api_auth_smoke.py" not in text
        assert "Clerk Development secret:" not in text
        assert "sk_test_" not in text
        for forbidden_name in (
            "CLERK_SECRET",
            "CLERK_SECRET_KEY",
            "CLERK_API_KEY",
            "CLERK_BACKEND_API_KEY",
        ):
            assert forbidden_name not in text


def test_media_storage_smoke_failure_emits_only_sanitized_output(
    tmp_path: Path,
) -> None:
    """AC10: a silent task leaks no command text, settings, path, or launcher."""
    launcher = tmp_path / "uv"
    launcher.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        '[ "$1" = run ]\n'
        "shift\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in\n'
        "    --project) shift 2 ;;\n"
        "    --locked|--no-sync) shift ;;\n"
        '    python) shift; exec "$PYTHON_FOR_MEDIA_SMOKE" "$@" ;;\n'
        "    *) exit 99 ;;\n"
        "  esac\n"
        "done\n"
        "exit 99\n"
    )
    launcher.chmod(0o755)

    completed = run_task(
        "api-media-storage-smoke",
        environment={
            "UV": str(launcher),
            "PYTHON_FOR_MEDIA_SMOKE": sys.executable,
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "RAILWAY_SERVICE_NAME": "api",
            "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": (
                "run-r2-development-media-storage-smoke"
            ),
        },
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    stderr_lines = completed.stderr.splitlines()
    assert stderr_lines[0] == "FAIL target configuration invalid"
    assert len(stderr_lines[1:]) <= 1
    assert all(
        MEDIA_STORAGE_SMOKE_TASK_FAILURE_FOOTER.fullmatch(line)
        for line in stderr_lines[1:]
    )
    rendered = completed.stdout + completed.stderr
    for forbidden in (
        "DJANGO_SETTINGS_MODULE",
        "PYTHONPATH",
        "config.settings.production",
        "python -m scripts.api_media_storage_smoke",
        str(launcher),
        str(REPOSITORY_ROOT),
    ):
        assert forbidden not in rendered


def test_devcontainer_migrate_executes_with_the_compose_database_url(
    tmp_path: Path,
) -> None:
    """The devcontainer migration recipe passes its Compose database URL to Django."""
    uv = tmp_path / "uv"
    uv.write_text(
        """#!/bin/sh
case "$*" in
  *"config.compose_database_url")
    printf '%s\\n' 'postgresql://tailtag:local@db:5432/tailtag'
    ;;
  *"python manage.py migrate")
    printf 'DATABASE_URL=%s\\n' "$DATABASE_URL"
    printf 'DJANGO_SETTINGS_MODULE=%s\\n' "$DJANGO_SETTINGS_MODULE"
    ;;
  *)
    exit 1
    ;;
esac
"""
    )
    uv.chmod(0o755)

    completed = run_task(
        "api-migrate",
        environment={
            "DATABASE_URL": "postgresql://inherited:sentinel@localhost:5432/sentinel",
            "DJANGO_SETTINGS_MODULE": "sentinel.settings",
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "TAILTAG_DEVCONTAINER": "1",
            "UV": "uv",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "DATABASE_URL=postgresql://tailtag:local@db:5432/tailtag" in completed.stdout
    assert "DJANGO_SETTINGS_MODULE=config.settings.local" in completed.stdout


def test_smoke_checks_an_already_running_http_service() -> None:
    """The task passes API_BASE_URL through and requests every endpoint."""
    with smoke_server() as base_url:
        completed = run_task("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode == 0, completed.stderr
    for path in ("/health/live", "/health/ready", "/api/schema/", "/api/docs/"):
        assert path in completed.stdout


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (
            UnreadySmokeHandler,
            ["FAIL /health/ready: expected HTTP 200, received HTTP 503"],
        ),
        (
            RedirectingSmokeHandler,
            ["FAIL /health/live: expected HTTP 200, received HTTP 302"],
        ),
        (
            FailingSmokeHandler,
            [
                "FAIL /health/live: expected HTTP 200, received HTTP 503",
                "FAIL /health/ready: expected HTTP 200, received HTTP 503",
            ],
        ),
    ],
)
def test_smoke_reports_every_endpoint_with_a_bad_response(
    handler: type[BaseHTTPRequestHandler], expected: list[str]
) -> None:
    with smoke_server(handler) as base_url:
        completed = run_task("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode != 0
    for line in expected:
        assert line in completed.stderr


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:1", "/health/live"),
        ("not a URL", "FAIL API_BASE_URL: an absolute http or https URL is required"),
    ],
)
def test_smoke_fails_clearly_without_a_traceback(base_url: str, expected: str) -> None:
    completed = run_task("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode != 0
    assert expected in completed.stderr
    assert "Traceback" not in completed.stderr


def test_semgrep_is_isolated_from_the_api_dependency_resolution() -> None:
    """Semgrep lives only in its own locked project and never reaches the API image."""
    api_pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()
    )
    api_lockfile = (REPOSITORY_ROOT / "services" / "api" / "uv.lock").read_text()
    semgrep_pyproject = tomllib.loads(
        (REPOSITORY_ROOT / ".semgrep" / "pyproject.toml").read_text()
    )
    semgrep_lockfile = (REPOSITORY_ROOT / ".semgrep" / "uv.lock").read_text()
    dockerfile = (REPOSITORY_ROOT / "services" / "api" / "Dockerfile").read_text()

    assert semgrep_pyproject["project"]["dependencies"] == ["semgrep==1.173.0"]
    assert semgrep_pyproject["tool"]["uv"]["package"] is False
    assert 'name = "semgrep"' in semgrep_lockfile
    api_dependencies = [
        *api_pyproject["project"]["dependencies"],
        *(
            dependency
            for group in api_pyproject["dependency-groups"].values()
            for dependency in group
        ),
    ]
    assert not any(
        re.match(r"semgrep(?:\s|[\[<>=!~;@]|$)", dependency, flags=re.IGNORECASE)
        for dependency in api_dependencies
    )
    assert 'name = "semgrep"' not in api_lockfile
    assert "uv sync --locked --no-dev --no-install-project" in dockerfile

    root_ignore = REPOSITORY_ROOT / ".semgrepignore"
    tracked_ignore = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".semgrepignore"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert root_ignore.is_file()
    assert tracked_ignore.returncode == 0, tracked_ignore.stderr
    ignored_venv = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", ".semgrep/.venv/probe"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored_venv.returncode == 0

    exported = run_api_no_dev_dependency_export()
    assert exported.returncode == 0, exported.stderr
    assert "semgrep" not in exported.stdout.lower()


def run_api_no_dev_dependency_export() -> subprocess.CompletedProcess[str]:
    """Export the API's production dependency set through the UV launcher seam."""
    return subprocess.run(
        [
            os.environ.get("UV", "uv"),
            "--directory",
            "services/api",
            "export",
            "--locked",
            "--no-dev",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_api_dependency_export_honors_the_uv_launcher_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export probe cannot silently bypass a configured UV launcher."""
    invocation = tmp_path / "uv-invocation"
    launcher = tmp_path / "uv"
    launcher.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$UV_EXPORT_INVOCATION"\n'
        "printf '%s\\n' 'Django==5.2.10'\n"
    )
    launcher.chmod(0o755)
    monkeypatch.setenv("UV", str(launcher))
    monkeypatch.setenv("UV_EXPORT_INVOCATION", str(invocation))

    exported = run_api_no_dev_dependency_export()

    assert exported.returncode == 0, exported.stderr
    assert "semgrep" not in exported.stdout.lower()
    assert invocation.read_text().splitlines() == [
        "--directory",
        "services/api",
        "export",
        "--locked",
        "--no-dev",
    ]


def test_media_storage_smoke_has_no_unsafe_url_open_finding() -> None:
    """The guarded helper must carry effective, narrow S310 treatment at its URL sink."""
    completed = subprocess.run(
        [
            os.environ.get("UV", "uv"),
            "--directory",
            "services/api",
            "run",
            "--locked",
            "--no-sync",
            "ruff",
            "check",
            "--select",
            "S310",
            str(MEDIA_STORAGE_SMOKE_SCRIPT),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_staging_authenticated_smoke_is_never_an_ordinary_ci_workflow_step() -> None:
    """AC-4/9: Production-Clerk smoke remains an explicit maintainer operation."""
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    assert "api-staging-auth-smoke" not in workflow_text
    assert "scripts.api_staging_auth_smoke" not in workflow_text


def test_media_storage_smoke_is_never_an_ordinary_ci_workflow_step() -> None:
    """The real R2 operation is intentionally absent from all checked-in workflows."""
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    assert "api-media-storage-smoke" not in workflow_text
    assert "scripts.api_media_storage_smoke" not in workflow_text
