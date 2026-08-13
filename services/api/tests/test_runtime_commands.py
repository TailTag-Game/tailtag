"""Contributor-facing container runtime contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]


def docker_stage(dockerfile: str, name: str) -> str:
    """Return one named multi-stage Dockerfile section."""
    match = re.search(
        rf"^FROM .+ AS {name}\n(?P<contents>.*?)(?=^FROM |\Z)",
        dockerfile,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Dockerfile must define a {name} stage"
    return match.group("contents")


def compose_service(compose_file: str, name: str) -> str:
    """Return one top-level Compose service section."""
    match = re.search(
        rf"^  {name}:\n(?P<contents>.*?)(?=^  \w+:\n|^volumes:|\Z)",
        compose_file,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Compose file must define a {name} service"
    return match.group("contents")


def test_runtime_files_define_development_and_production_contracts() -> None:
    """Container tooling offers a development server and production Gunicorn entrypoint."""
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text()
    compose_file = (SERVICE_ROOT / "compose.yaml").read_text()
    environment_template = (SERVICE_ROOT / ".env.example").read_text()

    development = docker_stage(dockerfile, "development")
    production = docker_stage(dockerfile, "production")
    database = compose_service(compose_file, "db")
    api = compose_service(compose_file, "api")

    assert "FROM python:3.13-slim-bookworm AS development" in dockerfile
    assert "FROM python:3.13-slim-bookworm AS production" in dockerfile
    uv_copy = r"COPY --from=ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ /uv /uvx /bin/"
    assert re.search(uv_copy, development)
    assert re.search(uv_copy, production)
    for stage in (development, production):
        assert "groupadd --system tailtag" in stage
        assert "useradd --system --gid tailtag --create-home tailtag" in stage
        assert "chown tailtag:tailtag /app" in stage
        assert "COPY --chown=tailtag:tailtag pyproject.toml uv.lock ./" in stage
        assert "COPY --chown=tailtag:tailtag . ./" in stage
        assert "USER tailtag" in stage
    assert "RUN uv sync --locked --no-install-project" in development
    assert "apt-get install --no-install-recommends -y git make" in development
    assert "RUN uv sync --locked --no-dev --no-install-project" in production
    assert 'CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in development
    assert (
        'CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]'
        in production
    )
    assert "migrate" not in development
    assert "migrate" not in production

    assert "api:" in compose_file
    assert "db:" in compose_file
    assert 'command: ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in api
    assert "postgres:17" in compose_file
    assert "healthcheck:" in compose_file
    assert "pg_isready" in compose_file
    assert "service_healthy" in compose_file
    assert "migrate" not in compose_file
    assert "- postgres_data:/var/lib/postgresql/data" in database
    assert "postgres_data:/var/lib/postgresql/data" not in api
    database_ports = re.findall(r'^\s+- "([^"]+)"$', database, re.MULTILINE)
    assert database_ports == ["127.0.0.1:5432:5432"]
    assert re.search(r"^volumes:\n  postgres_data:\n", compose_file, re.MULTILINE)

    assert "DJANGO_SECRET_KEY=tailtag-local-development-secret" in environment_template
    assert (
        "DATABASE_URL=postgresql://tailtag:tailtag-local-password@127.0.0.1:5432/tailtag"
        in environment_template
    )
    assert "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver" in environment_template
    assert (
        "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000"
        in environment_template
    )
    assert "POSTGRES_PASSWORD=tailtag-local-password" in environment_template


def test_repository_devcontainer_reuses_the_api_compose_topology() -> None:
    """The editor workspace adapts the API Compose stack without duplicating it."""
    devcontainer_root = REPOSITORY_ROOT / ".devcontainer"
    devcontainer = json.loads((devcontainer_root / "devcontainer.json").read_text())
    override = (devcontainer_root / "compose.devcontainer.yaml").read_text()
    api = compose_service((SERVICE_ROOT / "compose.yaml").read_text(), "api")

    assert devcontainer["dockerComposeFile"] == [
        "../services/api/compose.yaml",
        "compose.devcontainer.yaml",
    ]
    assert devcontainer["service"] == "api"
    assert devcontainer["workspaceFolder"] == "/workspaces/tailtag"
    assert devcontainer["remoteUser"] == "tailtag"
    assert devcontainer["updateRemoteUserUID"] is True
    assert "workspaceMount" not in devcontainer
    assert devcontainer["postCreateCommand"] == (
        "cd services/api && uv sync --all-groups --locked"
    )
    assert devcontainer["forwardPorts"] == [8000]
    assert "migrate" not in devcontainer["postCreateCommand"]

    assert "services:" in override
    assert "api:" in override
    assert "command: sleep infinity" in override
    assert "- ../..:/workspaces/tailtag:cached" in override
    assert "target: development" in api
    assert "db:" not in override
    assert "postgres_data:" not in override
    assert "migrate" not in override


def test_contributor_commands_and_ci_cover_the_api_foundation_contract() -> None:
    """Contributor guidance and CI retain every supported foundation check."""
    readme = (SERVICE_ROOT / "README.md").read_text()
    workflow = (REPOSITORY_ROOT / ".github/workflows/api.yml").read_text()

    canonical_contributor_commands = [
        "make api-setup",
        "make api-run",
        "make api-test",
        "make api-check",
        "make api-migrate",
        "make api-migrations",
        "make api-migrations-check",
        "make api-shell",
        "make api-smoke",
    ]
    for command in canonical_contributor_commands:
        assert command in readme

    assert "uv sync --all-groups --locked" not in readme
    assert "uv run python manage.py runserver" not in readme
    assert "docker compose -f services/api/compose.yaml up --build" in readme
    assert (
        "docker compose -f services/api/compose.yaml exec api python manage.py migrate"
        in readme
    )
    assert "uv --directory services/api run python manage.py createsuperuser" in readme

    ci_commands = [
        "uv run pytest -q",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy .",
        "uv run python manage.py check",
        "uv run python manage.py makemigrations --check --dry-run",
        "uv run python manage.py spectacular --validate",
        "uv run gunicorn config.wsgi:application --check-config",
    ]
    for command in ci_commands:
        assert command in workflow

    supported_surfaces = [
        "/health/live",
        "/health/ready",
        "/api/schema/",
        "/api/docs/",
        "/admin/",
    ]
    for surface in supported_surfaces:
        assert surface in readme

    assert "Docker" in readme
    assert "unavailable" in readme

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    pull_request_trigger = re.search(
        r"(?ms)^  pull_request:\n(?P<configuration>.*?)(?=^  \w+:\n)",
        workflow,
    )
    assert pull_request_trigger
    pull_request_configuration = pull_request_trigger.group("configuration")
    assert "    paths:" not in pull_request_configuration
    assert "    paths-ignore:" not in pull_request_configuration
    assert 'python-version: "3.13"' in workflow
    assert "postgres:17" in workflow
    assert "uv sync --all-groups --locked" in workflow
