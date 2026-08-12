"""Repository-root backend developer command contracts."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep test output focused on command behavior."""


class UnreadySmokeHandler(SmokeHandler):
    """Serve an unavailable readiness endpoint for smoke failure coverage."""

    def do_GET(self) -> None:
        if self.path == "/health/ready":
            self.send_response(503)
            self.end_headers()
            return
        super().do_GET()


@contextmanager
def smoke_server(handler: type[BaseHTTPRequestHandler] = SmokeHandler) -> Iterator[str]:
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
    for target in (
        "api-setup",
        "api-run",
        "api-test",
        "api-check",
        "api-migrate",
        "api-migrations",
        "api-migrations-check",
        "api-shell",
        "api-smoke",
    ):
        assert target in completed.stdout


def test_check_composes_every_required_backend_validation() -> None:
    """The full check runs CI-equivalent validation without schema mutation."""
    completed = run_make("-n", "api-check")

    assert completed.returncode == 0, completed.stderr
    for command in (
        "ruff format --check .",
        "ruff check .",
        "mypy .",
        "pytest -q",
        "python manage.py check",
        "python manage.py makemigrations --check --dry-run",
        "python manage.py spectacular --validate --file /tmp/openapi.yml",
        "gunicorn config.wsgi:application --check-config",
    ):
        assert command in completed.stdout
    assert "docker compose" not in completed.stdout
    assert "python manage.py migrate" not in completed.stdout
    assert "python manage.py makemigrations" in completed.stdout


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
