"""Contributor-facing container runtime contracts."""

from __future__ import annotations

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
    assert "RUN uv sync --locked --no-install-project" in development
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

    assert (
        "DJANGO_SECRET_KEY=replace-with-a-local-development-secret"
        in environment_template
    )
    assert (
        "DATABASE_URL=postgresql://tailtag:replace-with-a-local-password@localhost:5432/tailtag"
        in environment_template
    )
    assert "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1" in environment_template
    assert (
        "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000"
        in environment_template
    )
    assert "POSTGRES_PASSWORD=replace-with-a-local-password" in environment_template


def test_contributor_commands_and_ci_cover_the_api_foundation_contract() -> None:
    """Contributor guidance and CI retain every supported foundation check."""
    readme = (SERVICE_ROOT / "README.md").read_text()
    workflow = (REPOSITORY_ROOT / ".github/workflows/api.yml").read_text()

    contributor_commands = [
        "uv sync --all-groups --locked",
        "uv run python manage.py runserver",
        "docker compose up --build",
        "docker compose exec api python manage.py migrate",
        "uv run pytest -q",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy .",
        "uv run python manage.py check",
        "uv run python manage.py makemigrations --check --dry-run",
        "uv run python manage.py spectacular --validate",
        "uv run gunicorn config.wsgi:application --check-config",
        "/health/live",
        "/health/ready",
    ]
    for command in contributor_commands:
        assert command in readme
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
    for command in contributor_commands[4:12]:
        assert command in workflow
