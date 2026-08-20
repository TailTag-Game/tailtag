"""Repository-root backend developer command contracts."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import tomllib
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.semgrep_support import FROZEN_ROOT_HELPERS, dry_run_commands

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_smoke.py"
AUTH_SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_auth_smoke.py"
CI_RELEVANCE_SCRIPT = REPOSITORY_ROOT / "scripts" / "backend_ci_relevance.py"
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


def make_prerequisites(target: str) -> list[str]:
    """Return the explicitly declared prerequisites for a root Make target."""
    completed = run_make("-prRn", target)

    assert completed.returncode == 0, completed.stderr
    target_rule = re.search(
        rf"(?m)^{re.escape(target)}:\s*(?P<rules>[^\n]*)$", completed.stdout
    )
    assert target_rule, f"Makefile must define {target}"
    return target_rule.group("rules").split()


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


def is_authenticated_smoke_helper_operand(operand: str) -> bool:
    """Recognize every path spelling that resolves to the auth smoke helper."""
    return resolve_repository_operand(operand) == AUTH_SMOKE_SCRIPT.resolve()


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
        lowered = command.lower()
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


def test_semgrep_scan_tokens_allows_only_the_empty_trusted_app_token_prefix() -> None:
    """The canonical credential-clearing prefix is not mistaken for token access."""
    command = (
        "SEMGREP_APP_TOKEN= uv --directory .semgrep run --locked --no-sync "
        "semgrep scan --config .semgrep/rules .semgrep/tests"
    )

    assert semgrep_scan_tokens(command) == [shlex.split(command)]
    with pytest.raises(AssertionError):
        semgrep_scan_tokens(
            command.replace("SEMGREP_APP_TOKEN=", "SEMGREP_APP_TOKEN=secret")
        )


def test_api_check_uv_run_contract_rejects_implicit_project_sync() -> None:
    """Project-selected canonical commands cannot evade the no-sync requirement."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            "uv --directory services/api run --locked --no-sync pytest -q\n"
            "uv run --project services/api pytest -q"
        )


def test_api_check_uv_run_contract_allows_reordered_approved_options() -> None:
    """The approved locked/no-sync/offline options remain order-independent."""
    assert_api_check_uv_runs_are_locked_and_no_sync(
        "uv --directory services/api run --offline --no-sync --locked pytest -q"
    )


def test_api_check_uv_run_contract_rejects_reordered_project_without_no_sync() -> None:
    """A project option cannot hide a missing no-sync run option."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            "uv run --locked --project services/api pytest -q"
        )


def test_api_check_uv_run_contract_rejects_flags_after_the_child_command() -> None:
    """Child arguments cannot satisfy uv's locked/no-sync command contract."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            "uv --directory services/api run pytest -q --locked --no-sync"
        )


def test_api_check_uv_run_contract_rejects_unknown_child_executable() -> None:
    """Every canonical uv run must expose a recognized validation child."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            "uv run --locked --no-sync custom-validator"
        )


@pytest.mark.parametrize(
    "non_run_invocation",
    ["uv pip install injected-package", "uv --directory services/api sync --locked"],
)
def test_api_check_uv_run_contract_rejects_non_run_invocations(
    non_run_invocation: str,
) -> None:
    """No auxiliary uv command may mutate the validation environment."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            f"{non_run_invocation}; uv run --locked --no-sync pytest -q"
        )


@pytest.mark.parametrize(
    "shaping_option",
    ["--with injected-package", "--python 3.13", "--env-file path"],
)
def test_api_check_uv_run_contract_rejects_shaping_options(
    shaping_option: str,
) -> None:
    """Canonical validation must not alter its dependencies or interpreter."""
    with pytest.raises(AssertionError):
        assert_api_check_uv_runs_are_locked_and_no_sync(
            f"uv run --locked --no-sync {shaping_option} pytest -q"
        )


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


def run_make(
    *targets: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a root Make target with optional environment overrides."""
    return subprocess.run(
        ["make", *targets],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, **(environment or {})},
        capture_output=True,
        text=True,
        check=False,
    )


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


def test_dry_run_commands_ignores_recursive_make_directory_diagnostics() -> None:
    """GNU Make directory tracing is diagnostic output, not an executed command."""
    dry_run = """\
make[1]: Entering directory '/workspace/tailtag'
uv --directory services/api run --locked --no-sync pytest -q
make[1]: Leaving directory '/workspace/tailtag'
"""

    assert dry_run_commands(dry_run) == [
        "uv --directory services/api run --locked --no-sync pytest -q"
    ]


def test_semgrep_scan_tokens_rejects_an_incomplete_launcher_prefix() -> None:
    """A malformed Semgrep command fails before fixed-offset token parsing."""
    with pytest.raises(AssertionError, match="at least six launcher-prefix tokens"):
        semgrep_scan_tokens("semgrep scan --config .semgrep/rules .semgrep/tests")


def test_help_lists_the_canonical_backend_commands() -> None:
    """The root interface exposes every required backend command."""
    completed = run_make("help")

    assert completed.returncode == 0, completed.stderr
    expected_commands = {
        "api-setup": "Sync locked backend dependencies.",
        "api-run": "Run Django locally on port 8000; requires configured PostgreSQL.",
        "api-test": "Run PostgreSQL-backed backend tests.",
        "api-semgrep-check": "Run deterministic TailTag Semgrep security analysis.",
        "api-check": "Run the complete local pre-PR backend validation suite.",
        "api-migrate": "Apply existing Django migrations (mutates schema).",
        "api-migrations": "Create Django migrations (mutates migration state).",
        "api-migrations-check": "Check for migration drift without creating migrations.",
        "api-shell": "Open the Django shell; requires configured PostgreSQL.",
        "api-smoke": "HTTP-check a running API (API_BASE_URL defaults to 127.0.0.1:8000).",
        "api-auth-smoke": "Authenticated smoke test with an interactive Clerk Development secret.",
    }
    for target, description in expected_commands.items():
        assert f"make {target}" in completed.stdout
        assert description in completed.stdout


def test_check_composes_every_required_backend_validation() -> None:
    """The full check runs CI-equivalent validation without schema mutation."""
    completed = run_make("-n", "api-check")
    prerequisites = make_prerequisites("api-check")

    assert completed.returncode == 0, completed.stderr
    for command in (
        "ruff format --check .",
        "ruff check .",
        "pyright",
        "pytest -q",
        "python manage.py check",
        "python manage.py makemigrations --check --dry-run",
        "python manage.py spectacular --validate --file /dev/null",
        "gunicorn config.wsgi:application --check-config",
    ):
        assert command in completed.stdout
    assert f"ruff format --check . {SMOKE_SCRIPT}" in completed.stdout
    assert f"ruff check . {SMOKE_SCRIPT}" in completed.stdout
    assert str(CI_RELEVANCE_SCRIPT) in completed.stdout
    assert "api-semgrep-check" in prerequisites
    assert prerequisites.index("api-semgrep-check") < prerequisites.index("api-test")
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)
    assert_api_check_uv_runs_are_locked_and_no_sync(completed.stdout)
    assert completed.stdout.index("semgrep scan --test") < completed.stdout.index(
        "pytest -q"
    )
    assert " sync " not in completed.stdout
    assert "docker compose" not in completed.stdout
    assert "python manage.py migrate" not in completed.stdout
    assert "python manage.py makemigrations" in completed.stdout
    assert "api-auth-smoke" not in completed.stdout
    assert "Clerk Development secret:" not in completed.stdout
    assert "CLERK_SECRET" not in completed.stdout


def test_semgrep_check_is_local_locked_noninteractive_and_credential_free() -> None:
    """The static security gate scans local sources without external Semgrep services."""
    completed = run_make("-n", "api-semgrep-check")

    assert completed.returncode == 0, completed.stderr
    execution_lines = [
        line
        for line in dry_run_commands(completed.stdout)
        if line.strip() and not line.lstrip().startswith(("echo ", "printf "))
    ]
    assert len(execution_lines) == 3
    assert str(SEMGREP_VALIDATOR) in execution_lines[0]
    assert all("semgrep scan" in line for line in execution_lines[1:])
    assert ".env" not in completed.stdout
    assert "docker" not in completed.stdout.lower()
    assert "migrate" not in completed.stdout.lower()
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)
    assert completed.stdout.count(str(AUTH_SMOKE_SCRIPT)) == 1


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("SEMGREP_RULES", "/tmp/untrusted-semgrep-rules"),
        ("SEMGREP_TESTS", "/tmp/untrusted-semgrep-fixtures"),
        ("SEMGREP_TARGETS", "/tmp/untrusted-semgrep-target"),
        ("SEMGREP", "untrusted-semgrep-launcher"),
        ("SEMGREP_DIRECTORY", "/tmp/untrusted-semgrep-directory"),
        ("SEMGREP_UV", "untrusted-semgrep-uv"),
        ("API_UV", "untrusted-api-uv"),
        ("API_DIRECTORY", "/tmp/untrusted-api-directory"),
        ("SEMGREP_VALIDATOR", "/tmp/untrusted-semgrep-validator.py"),
        ("SMOKE_SCRIPT", "/tmp/untrusted-api-smoke.py"),
        ("AUTH_SMOKE_SCRIPT", "/tmp/untrusted-api-auth-smoke.py"),
        (
            "CLERK_DEVELOPMENT_SESSION_SCRIPT",
            "/tmp/untrusted-clerk-development-session.py",
        ),
        ("CI_RELEVANCE_SCRIPT", "/tmp/untrusted-backend-ci-relevance.py"),
    ],
)
@pytest.mark.parametrize(
    "override_source",
    ["environment", "command_line", "makeflags", "environment_overrides"],
)
def test_semgrep_check_ignores_make_overrides_of_its_security_inputs(
    variable: str, replacement: str, override_source: str
) -> None:
    """Only the repository can select the canonical Semgrep executable and scope."""
    if override_source == "environment":
        completed = run_make(
            "-n", "api-semgrep-check", environment={variable: replacement}
        )
    elif override_source == "command_line":
        completed = run_make("-n", "api-semgrep-check", f"{variable}={replacement}")
    elif override_source == "environment_overrides":
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": "-e", variable: replacement},
        )
    else:
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": f"{variable}={replacement}"},
        )

    assert completed.returncode == 0, completed.stderr
    assert replacement not in completed.stdout
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)


@pytest.mark.parametrize(
    ("variable", "replacement"),
    [
        ("SEMGREP_BASELINE_COMMIT", "HEAD"),
        ("SEMGREP_APP_TOKEN", "untrusted-token"),
        ("SEMGREP_RULES", "/tmp/untrusted-semgrep-rules"),
    ],
)
@pytest.mark.parametrize(
    "override_source",
    ["environment", "command_line", "makeflags", "environment_overrides"],
)
def test_semgrep_check_clears_inherited_semgrep_execution_settings(
    variable: str, replacement: str, override_source: str
) -> None:
    """Inherited Semgrep settings cannot alter the canonical local scan process."""
    if override_source == "environment":
        completed = run_make(
            "-n", "api-semgrep-check", environment={variable: replacement}
        )
    elif override_source == "command_line":
        completed = run_make("-n", "api-semgrep-check", f"{variable}={replacement}")
    elif override_source == "environment_overrides":
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": "-e", variable: replacement},
        )
    else:
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": f"{variable}={replacement}"},
        )

    assert completed.returncode == 0, completed.stderr
    assert replacement not in completed.stdout
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)


@pytest.mark.parametrize(
    "override_source", ["command_line", "makeflags", "environment_overrides"]
)
def test_semgrep_check_ignores_curdir_override_channels(override_source: str) -> None:
    """GNU Make's inherited assignment channels cannot redirect the security scope."""
    replacement = "/tmp/tailtag-fake"
    if override_source == "command_line":
        completed = run_make("-n", "api-semgrep-check", f"CURDIR={replacement}")
    elif override_source == "environment_overrides":
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": "-e", "CURDIR": replacement},
        )
    else:
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": f"CURDIR={replacement}"},
        )

    assert completed.returncode == 0, completed.stderr
    assert replacement not in completed.stdout
    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)


@pytest.mark.parametrize(
    "override_source", ["environment", "command_line", "environment_overrides"]
)
def test_semgrep_check_honors_the_uv_override_seam(
    tmp_path: Path, override_source: str
) -> None:
    """The one intentional launcher seam cannot alter Semgrep's fixed contract."""
    custom_uv = tmp_path / "uv"
    custom_uv.write_text("#!/bin/sh\nexit 0\n")
    custom_uv.chmod(0o755)

    if override_source == "environment":
        completed = run_make(
            "-n", "api-semgrep-check", environment={"UV": str(custom_uv)}
        )
    elif override_source == "command_line":
        completed = run_make("-n", "api-semgrep-check", f"UV={custom_uv}")
    else:
        completed = run_make(
            "-n",
            "api-semgrep-check",
            environment={"MAKEFLAGS": "-e", "UV": str(custom_uv)},
        )

    assert completed.returncode == 0, completed.stderr
    commands = [shlex.split(command) for command in dry_run_commands(completed.stdout)]
    validator_command = next(
        command for command in commands if str(SEMGREP_VALIDATOR) in command
    )
    assert validator_command[0] == str(custom_uv)
    for command in semgrep_scan_tokens(completed.stdout):
        semgrep_index = command.index("semgrep")
        assert command[semgrep_index - 6] == str(custom_uv)

    assert_semgrep_check_contract(completed.stdout)
    assert_semgrep_validator_precedes_fixture_scan(completed.stdout)


def test_semgrep_validator_preflight_rejects_a_second_python_execution() -> None:
    """A scan target mention is allowed, but a second validator execution is not."""
    completed = run_make("-n", "api-semgrep-check")
    commands = dry_run_commands(completed.stdout)
    validator = next(
        command
        for command in commands
        if shlex.split(command)[7:8] == [str(SEMGREP_VALIDATOR)]
    )

    with pytest.raises(AssertionError):
        assert_semgrep_validator_precedes_fixture_scan(
            f"{completed.stdout}\n{validator}"
        )


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


def test_setup_synchronizes_both_locked_projects_before_no_sync_checks() -> None:
    """Setup prepares both projects while the regular validation target never syncs."""
    setup = run_make("-n", "api-setup")
    check = run_make("-n", "api-check")

    assert setup.returncode == 0, setup.stderr
    assert "uv --directory services/api sync --all-groups --locked" in setup.stdout
    assert "uv --directory .semgrep sync --locked" in setup.stdout
    assert check.returncode == 0, check.stderr
    assert " sync " not in check.stdout


def test_strict_type_check_includes_the_ci_relevance_helper() -> None:
    """The repo-owned CI classifier receives the same strict type coverage as scripts."""
    pyproject = (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()

    assert '"../../scripts/backend_ci_relevance.py"' in pyproject


def test_static_checks_include_the_semgrep_contract_validator() -> None:
    """The root Semgrep metadata validator receives the ordinary static checks."""
    completed = run_make("-n", "api-format-check", "api-lint-check")
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()
    )

    assert completed.returncode == 0, completed.stderr
    ruff_commands = [
        shlex.split(command)
        for command in dry_run_commands(completed.stdout)
        if "ruff" in shlex.split(command)
    ]
    assert len(ruff_commands) == 2
    for command in ruff_commands:
        ruff_index = command.index("ruff")
        assert command[ruff_index + 1] in {"format", "check"}
        assert str(SEMGREP_VALIDATOR) in command[ruff_index + 1 :]

    pyright = pyproject["tool"]["pyright"]
    assert pyright["typeCheckingMode"] == "strict"
    assert "../../scripts/validate_semgrep_contract.py" in pyright["include"]


def test_static_checks_include_all_authenticated_smoke_helpers() -> None:
    """Live-tool scripts receive the same static checks as existing root helpers."""
    completed = run_make("-n", "api-format-check", "api-lint-check")
    pyproject = (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()

    assert completed.returncode == 0, completed.stderr
    for script in (
        AUTH_SMOKE_SCRIPT,
        REPOSITORY_ROOT / "scripts" / "clerk_development_session.py",
    ):
        assert str(script) in completed.stdout
        assert f'"../../scripts/{script.name}"' in pyproject


def test_lifecycle_and_schema_changes_remain_explicit() -> None:
    """Only named migration targets can change migration or schema state."""
    non_mutating_targets = (
        "api-setup",
        "api-run",
        "api-test",
        "api-shell",
        "api-smoke",
        "api-auth-smoke",
    )

    for target in non_mutating_targets:
        completed = run_make("-n", target)

        assert completed.returncode == 0, completed.stderr
        assert "docker compose" not in completed.stdout
        assert "python manage.py migrate" not in completed.stdout
        assert "python manage.py makemigrations" not in completed.stdout

    assert "python manage.py migrate" in run_make("-n", "api-migrate").stdout
    assert "python manage.py makemigrations" in run_make("-n", "api-migrations").stdout


def test_authenticated_smoke_is_a_separate_locked_atomic_command() -> None:
    """The only live Clerk path is explicit and never piggybacks on ordinary work."""
    completed = run_make("-n", "api-auth-smoke")

    assert completed.returncode == 0, completed.stderr
    assert (
        "uv run --project services/api --locked --no-sync python -m scripts.api_auth_smoke"
        in completed.stdout
    )
    assert str(AUTH_SMOKE_SCRIPT) not in run_make("-n", "api-smoke").stdout


def test_authenticated_smoke_honors_uv_override(tmp_path: Path) -> None:
    """The manual live command respects the repository's UV override seam."""
    overridden_uv = tmp_path / "overridden-uv"
    overridden_uv.write_text("#!/bin/sh\nexit 0\n")
    overridden_uv.chmod(0o755)

    completed = run_make("-n", "api-auth-smoke", f"UV={overridden_uv}")

    assert completed.returncode == 0, completed.stderr
    assert f"{overridden_uv} run " in completed.stdout
    assert "python -m scripts.api_auth_smoke" in completed.stdout


def assert_ci_and_ordinary_smoke_are_noninteractive_and_credential_free(
    ordinary: str, api_check: str, workflow_text: str
) -> None:
    """Assert that only explicit manual work can invoke authenticated smoke checks."""

    for text in (ordinary, api_check, workflow_text):
        assert "api-auth-smoke" not in text
        assert "scripts.api_auth_smoke" not in text
        assert "Clerk Development secret:" not in text
        assert "sk_test_" not in text
        for forbidden_name in (
            "CLERK_SECRET",
            "CLERK_SECRET_KEY",
            "CLERK_API_KEY",
            "CLERK_BACKEND_API_KEY",
        ):
            assert forbidden_name not in text

    # Static analysis may inspect the helper source in api-check, but it must
    # never execute it. The Semgrep helper proves the exact blocking target
    # set; Pyright coverage is asserted separately from pyproject.
    assert_semgrep_check_contract(api_check)
    assert_api_check_uv_runs_are_locked_and_no_sync(api_check)
    api_check_script_commands = [
        (line, shlex.split(line))
        for line in dry_run_commands(api_check)
        if any(
            is_authenticated_smoke_helper_operand(token) for token in shlex.split(line)
        )
    ]
    assert api_check_script_commands
    for line, tokens in api_check_script_commands:
        assert not any(
            operator in line
            for operator in ("&&", "||", ";", "|", "`", "$(", "${", ">", "<")
        ), line

        assert not any(
            token
            in {"python", "-m", "api-auth-smoke", "sh", "bash", "zsh", "xargs", "exec"}
            for token in tokens
        ), line

        if any(
            tokens[index : index + 2] == ["semgrep", "scan"]
            for index in range(len(tokens))
        ):
            # assert_semgrep_check_contract above structurally validates this
            # command and requires the helper as a blocking-scan source target.
            continue

        ruff_index = tokens.index("ruff")
        assert tokens[ruff_index + 1] in {"format", "check"}, line
        assert any(
            is_authenticated_smoke_helper_operand(token)
            for token in tokens[ruff_index + 1 :]
        ), line

    # Ordinary smoke and CI must not reference the helper at all.
    for text in (ordinary, workflow_text):
        assert "scripts/api_auth_smoke.py" not in text

    assert not any(
        is_authenticated_smoke_helper_operand(token)
        for line in dry_run_commands(ordinary)
        for token in shlex.split(line)
    )


def test_ci_and_ordinary_smoke_remain_noninteractive_and_credential_free() -> None:
    """CI must not gain a secret, prompt, or live authenticated smoke dependency."""
    ordinary = run_make("-n", "api-smoke").stdout
    api_check = run_make("-n", "api-check").stdout
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    assert_ci_and_ordinary_smoke_are_noninteractive_and_credential_free(
        ordinary, api_check, workflow_text
    )


def test_api_check_rejects_normalized_authenticated_smoke_helper_execution() -> None:
    """Equivalent helper paths cannot bypass api-check's execution prohibition."""
    ordinary = run_make("-n", "api-smoke").stdout
    api_check = run_make("-n", "api-check").stdout
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    with pytest.raises(AssertionError):
        assert_ci_and_ordinary_smoke_are_noninteractive_and_credential_free(
            ordinary,
            f"{api_check}\nuv --directory services/api run --locked --no-sync python scripts/./api_auth_smoke.py",
            workflow_text,
        )


def test_api_check_accepts_normalized_authenticated_smoke_helper_static_analysis() -> (
    None
):
    """Ruff may inspect the helper through an equivalent path spelling."""
    ordinary = run_make("-n", "api-smoke").stdout
    api_check = run_make("-n", "api-check").stdout
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    assert_ci_and_ordinary_smoke_are_noninteractive_and_credential_free(
        ordinary,
        f"{api_check}\nuv --directory services/api run --locked --no-sync ruff check scripts/./api_auth_smoke.py",
        workflow_text,
    )


def test_devcontainer_django_commands_derive_the_compose_database_url() -> None:
    """The generated devcontainer migration recipe configures Compose PostgreSQL."""
    completed = run_make("-n", "api-migrate", environment={"TAILTAG_DEVCONTAINER": "1"})

    assert completed.returncode == 0, completed.stderr
    assert "config.compose_database_url" in completed.stdout
    assert "DJANGO_SETTINGS_MODULE=config.settings.production" in completed.stdout
    assert "python manage.py migrate" in completed.stdout


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

    completed = run_make(
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
    assert "DJANGO_SETTINGS_MODULE=config.settings.production" in completed.stdout


def test_smoke_checks_an_already_running_http_service() -> None:
    """The smoke target requests every health and documentation endpoint."""
    with smoke_server() as base_url:
        completed = run_make("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode == 0, completed.stderr
    for path in ("/health/live", "/health/ready", "/api/schema/", "/api/docs/"):
        assert path in completed.stdout


def test_smoke_fails_clearly_when_the_api_is_unavailable() -> None:
    """The smoke target reports a connection failure without hiding it."""
    completed = run_make(
        "api-smoke", environment={"API_BASE_URL": "http://127.0.0.1:1"}
    )

    assert completed.returncode != 0
    assert "/health/live" in completed.stderr


def test_smoke_fails_clearly_when_an_endpoint_returns_an_unexpected_status() -> None:
    """The smoke target identifies the reachable endpoint with a bad response."""
    with smoke_server(UnreadySmokeHandler) as base_url:
        completed = run_make("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode != 0
    assert (
        "FAIL /health/ready: expected HTTP 200, received HTTP 503" in completed.stderr
    )


def test_smoke_rejects_redirects_from_required_endpoints() -> None:
    """The smoke target does not treat a redirected response as HTTP 200."""
    with smoke_server(RedirectingSmokeHandler) as base_url:
        completed = run_make("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode != 0
    assert "FAIL /health/live: expected HTTP 200, received HTTP 302" in completed.stderr


def test_smoke_rejects_a_malformed_base_url_without_a_traceback() -> None:
    """The smoke target reports invalid input without exposing a Python traceback."""
    completed = run_make("api-smoke", environment={"API_BASE_URL": "not a URL"})

    assert completed.returncode != 0
    assert (
        "FAIL API_BASE_URL: an absolute http or https URL is required"
        in completed.stderr
    )
    assert "Traceback" not in completed.stderr


def test_smoke_reports_every_failing_required_endpoint() -> None:
    """The smoke target continues checking after an endpoint fails."""
    with smoke_server(FailingSmokeHandler) as base_url:
        completed = run_make("api-smoke", environment={"API_BASE_URL": base_url})

    assert completed.returncode != 0
    assert "FAIL /health/live: expected HTTP 200, received HTTP 503" in completed.stderr
    assert (
        "FAIL /health/ready: expected HTTP 200, received HTTP 503" in completed.stderr
    )
