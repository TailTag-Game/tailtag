"""Contributor-facing container runtime contracts."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

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


def docker_labels(stage: str) -> dict[str, str]:
    """Return key/value pairs from LABEL instructions in one Docker stage."""
    labels: dict[str, str] = {}
    lines = iter(stage.splitlines())

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("LABEL "):
            continue

        instruction = stripped.removeprefix("LABEL ")
        while instruction.endswith("\\"):
            instruction = instruction.removesuffix("\\").rstrip()
            instruction = f"{instruction} {next(lines).strip()}"

        for token in shlex.split(instruction):
            key, separator, value = token.partition("=")
            assert separator, f"LABEL entry must use key=value syntax: {token}"
            labels[key] = value

    return labels


def compose_service(compose_file: str, name: str) -> str:
    """Return one top-level Compose service section."""
    match = re.search(
        rf"^  {name}:\n(?P<contents>.*?)(?=^  \w+:\n|^volumes:|\Z)",
        compose_file,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Compose file must define a {name} service"
    return match.group("contents")


def yaml_mapping_contents(document: str, key: str, indentation: int) -> str:
    """Return one mapping's full indentation-delimited YAML content block."""
    header = re.compile(rf"^ {{{indentation}}}{re.escape(key)}:\s*(?:#.*)?$")
    lines = document.splitlines()

    for index, line in enumerate(lines):
        if not header.fullmatch(line):
            continue

        contents: list[str] = []
        for candidate in lines[index + 1 :]:
            if (
                candidate.strip()
                and len(candidate) - len(candidate.lstrip()) <= indentation
            ):
                break
            contents.append(candidate)
        return "\n".join(contents)

    raise AssertionError(f"YAML mapping not found: {' ' * indentation}{key}")


def assert_api_workflow_least_privilege(workflow: str) -> None:
    """Require one read-only workflow permission block with no job override."""
    top_level_permissions = yaml_mapping_contents(workflow, "permissions", 0)
    permission_entries = [
        line.strip()
        for line in top_level_permissions.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert permission_entries == ["contents: read"]

    jobs = yaml_mapping_contents(workflow, "jobs", 0)
    job_names = re.findall(
        r"""(?m)^  ("[^"]+"|'[^']+'|[A-Za-z0-9_-]+):\s*(?:#.*)?$""", jobs
    )
    assert job_names, "workflow must define at least one job"
    for job_name in job_names:
        job = yaml_mapping_contents(jobs, job_name, 2)
        assert not re.search(r"(?m)^    permissions:", job)


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
    assert "DJANGO_SETTINGS_MODULE=config.settings.local" in api
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


def test_production_image_records_oci_attribution() -> None:
    """The deployable image identifies its repository and runtime purpose."""
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text()
    production = docker_stage(dockerfile, "production")
    labels = docker_labels(production)

    assert labels["org.opencontainers.image.source"] == (
        "https://github.com/TailTag-Game/tailtag"
    )
    assert labels["org.opencontainers.image.title"] == "TailTag API"
    assert labels["org.opencontainers.image.description"] == "TailTag development API"
    assert labels["org.tailtag.delivery-probe"] == (
        "wait-for-ci-trigger-refresh-2026-08-16"
    )


def test_repository_devcontainer_reuses_the_api_compose_topology() -> None:
    """The editor workspace adapts the API Compose stack without duplicating it."""
    devcontainer_root = REPOSITORY_ROOT / ".devcontainer"
    devcontainer = json.loads((devcontainer_root / "devcontainer.json").read_text())
    override = (devcontainer_root / "compose.devcontainer.yaml").read_text()
    api = compose_service((SERVICE_ROOT / "compose.yaml").read_text(), "api")
    devcontainer_api = compose_service(override, "api")

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
        "uv --directory services/api sync --all-groups --locked && "
        "uv --directory .semgrep sync --locked"
    )
    assert devcontainer["forwardPorts"] == [8000]
    assert "migrate" not in devcontainer["postCreateCommand"]

    assert "services:" in override
    assert "api:" in override
    assert "command: sleep infinity" in override
    assert "- ../..:/workspaces/tailtag:cached" in devcontainer_api
    assert "target: development" in api
    assert "db:" not in override
    assert "postgres_data:" not in override
    assert "migrate" not in override


def test_contributor_commands_and_ci_share_the_api_foundation_contract() -> None:
    """Contributor guidance and CI use one backend validation contract."""
    readme = (SERVICE_ROOT / "README.md").read_text()
    workflow = (REPOSITORY_ROOT / ".github/workflows/api.yml").read_text()

    canonical_contributor_commands = [
        "make api-setup",
        "make api-run",
        "make api-test",
        "make api-semgrep-check",
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

    assert "name: API foundation checks" in workflow
    assert "run: make api-check" in workflow
    assert_api_workflow_least_privilege(workflow)
    for duplicated_command in (
        "uv run pytest -q",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run pyright",
        "semgrep scan",
        "api-semgrep-check",
        "uv run python manage.py check",
        "uv run python manage.py makemigrations --check --dry-run",
        "uv run python manage.py spectacular --validate",
        "uv run gunicorn config.wsgi:application --check-config",
    ):
        assert duplicated_command not in workflow

    for forbidden_semgrep_integration in (
        "SEMGREP_APP_TOKEN",
        "SEMGREP_API_TOKEN",
        "semgrep.dev",
        "semgrep-action",
    ):
        assert forbidden_semgrep_integration not in workflow

    semgrep_documentation = " ".join(readme.lower().split())
    assert re.search(r"(?:repository[- ]owned|local) rules", semgrep_documentation)
    assert re.search(r"(?:no|without) (?:scan-time )?network", semgrep_documentation)
    assert re.search(r"(?:no|without) (?:semgrep )?account", semgrep_documentation)
    assert re.search(
        r"(?:does not|doesn't|not) .{0,80}(?:dependency|sca).{0,80}(?:scan|cover)",
        semgrep_documentation,
    )
    assert re.search(
        r"(?:does not|doesn't|not) .{0,80}secret.{0,80}(?:scan|cover)",
        semgrep_documentation,
    )

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
    push_trigger = re.search(
        r"(?ms)^  push:\n(?P<configuration>.*?)(?=^  \w+:\n)",
        workflow,
    )
    assert push_trigger
    push_configuration = push_trigger.group("configuration")
    assert "    branches:\n      - main" in push_configuration
    assert "    paths:" not in push_configuration
    assert "    paths-ignore:" not in push_configuration
    assert "workflow_dispatch:" in workflow
    assert workflow.count("name: API foundation checks") == 1
    assert workflow.count("run: make api-check") == 1
    assert "scripts/backend_ci_relevance.py" in workflow
    assert "--force-run" in workflow
    assert (
        "No backend-relevant changes detected; backend validation skipped." in workflow
    )
    assert "git diff --name-only -z" in workflow
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
    api_job = yaml_mapping_contents(
        yaml_mapping_contents(workflow, "jobs", 0), "api", 2
    )
    validation_index = api_job.index("run: make api-check")
    for setup_command in (
        "uv --directory services/api sync --all-groups --locked",
        "uv --directory .semgrep sync --locked",
    ):
        assert api_job.count(setup_command) == 1
        assert api_job.index(setup_command) < validation_index


def test_api_workflow_permissions_reject_effective_escalation() -> None:
    """A write-capable top-level or API-job permission is never a valid contract."""
    workflow = (REPOSITORY_ROOT / ".github/workflows/api.yml").read_text()
    top_level_escalation = workflow.replace(
        "  contents: read", "  contents: read\n  pull-requests: write", 1
    )
    job_level_escalation = workflow.replace(
        "    runs-on:", "    permissions:\n      contents: write\n    runs-on:", 1
    )
    late_job_level_escalation = workflow.replace(
        "\n    env:\n", "\n    permissions:\n      contents: write\n    env:\n", 1
    )

    assert top_level_escalation != workflow
    assert job_level_escalation != workflow
    assert late_job_level_escalation != workflow
    with pytest.raises(AssertionError):
        assert_api_workflow_least_privilege(top_level_escalation)
    with pytest.raises(AssertionError):
        assert_api_workflow_least_privilege(job_level_escalation)
    with pytest.raises(AssertionError):
        assert_api_workflow_least_privilege(late_job_level_escalation)


def test_api_workflow_permissions_ignore_comments_and_reject_every_job_override() -> (
    None
):
    """Comments are inert, but a second job cannot escalate workflow permissions."""
    workflow = (REPOSITORY_ROOT / ".github/workflows/api.yml").read_text()
    commented_permissions = workflow.replace(
        "  contents: read", "  # contents: write\n  contents: read", 1
    )
    second_job_escalation = workflow.replace(
        "  api:\n",
        "  reporting:\n"
        "    permissions:\n"
        "      contents: write\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  api:\n",
        1,
    )
    quoted_job_escalation = workflow.replace(
        "  api:\n",
        '  "reporting":\n'
        "    permissions:\n"
        "      contents: write\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  api:\n",
        1,
    )

    assert commented_permissions != workflow
    assert second_job_escalation != workflow
    assert quoted_job_escalation != workflow
    assert_api_workflow_least_privilege(commented_permissions)
    with pytest.raises(AssertionError):
        assert_api_workflow_least_privilege(second_job_escalation)
    with pytest.raises(AssertionError):
        assert_api_workflow_least_privilege(quoted_job_escalation)
