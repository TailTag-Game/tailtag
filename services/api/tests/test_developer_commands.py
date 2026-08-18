"""Repository-root backend developer command contracts."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_smoke.py"
AUTH_SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_auth_smoke.py"
CI_RELEVANCE_SCRIPT = REPOSITORY_ROOT / "scripts" / "backend_ci_relevance.py"


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


def test_help_lists_the_canonical_backend_commands() -> None:
    """The root interface exposes every required backend command."""
    completed = run_make("help")

    assert completed.returncode == 0, completed.stderr
    expected_commands = {
        "api-setup": "Sync locked backend dependencies.",
        "api-run": "Run Django locally on port 8000; requires configured PostgreSQL.",
        "api-test": "Run PostgreSQL-backed backend tests.",
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
    assert "docker compose" not in completed.stdout
    assert "python manage.py migrate" not in completed.stdout
    assert "python manage.py makemigrations" in completed.stdout
    assert "api-auth-smoke" not in completed.stdout
    assert "Clerk Development secret:" not in completed.stdout
    assert "CLERK_SECRET" not in completed.stdout


def test_strict_type_check_includes_the_ci_relevance_helper() -> None:
    """The repo-owned CI classifier receives the same strict type coverage as scripts."""
    pyproject = (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()

    assert '"../../scripts/backend_ci_relevance.py"' in pyproject


def test_lifecycle_and_schema_changes_remain_explicit() -> None:
    """Only named migration targets can change migration or schema state."""
    non_mutating_targets = (
        "api-setup",
        "api-run",
        "api-test",
        "api-shell",
        "api-smoke",
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


def test_ci_and_ordinary_smoke_remain_noninteractive_and_credential_free() -> None:
    """CI must not gain a secret, prompt, or live authenticated smoke dependency."""
    ordinary = run_make("-n", "api-smoke").stdout
    api_check = run_make("-n", "api-check").stdout
    workflow_text = "\n".join(
        path.read_text()
        for suffix in ("*.yml", "*.yaml")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob(suffix)
    )

    for text in (ordinary, api_check, workflow_text):
        assert "api-auth-smoke" not in text
        assert "Clerk Development secret:" not in text
        assert "CLERK_SMOKE_USER_ID" not in text
        assert "sk_test_" not in text


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
