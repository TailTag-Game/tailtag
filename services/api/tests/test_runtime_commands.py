"""Contributor-facing container runtime contracts."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import cast

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
    production_copy_index = production.index("COPY --chown=tailtag:tailtag . ./")
    static_collection = (
        "RUN python manage.py collectstatic --settings=config.settings.build --noinput"
    )
    assert production.count(static_collection) == 1
    assert production_copy_index < production.index(static_collection)
    assert 'CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in development
    gunicorn_command = (
        'CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]'
    )
    assert gunicorn_command in production
    assert production.index(static_collection) < production.index(gunicorn_command)
    assert "migrate" not in development
    assert "migrate" not in production
    assert "collectstatic" not in development
    assert "bootstrap_development_operator" not in development
    assert "bootstrap_development_operator" not in production

    assert "api:" in compose_file
    assert "db:" in compose_file
    assert 'command: ["python", "manage.py", "runserver", "0.0.0.0:8000"]' in api
    assert "DJANGO_SETTINGS_MODULE=config.settings.local" in api
    assert "postgres:17" in compose_file
    assert "healthcheck:" in compose_file
    assert "pg_isready" in compose_file
    assert "service_healthy" in compose_file
    assert "migrate" not in compose_file
    assert "collectstatic" not in compose_file
    assert "bootstrap_development_operator" not in compose_file
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


OPERATOR_COMMAND = (
    "python manage.py bootstrap_development_operator "
    "--settings=config.settings.production"
)
OPERATOR_PROCEDURE = (
    f"railway ssh --service api --environment development\n{OPERATOR_COMMAND}"
)
OPERATOR_AUTOMATION_PROHIBITIONS = (
    (
        "Do not add a Make target or script, set a `DJANGO_SUPERUSER_PASSWORD`, "
        "configure Railway credential variables, or run the command automatically "
        "during build, pre-deploy, startup, health checks, or Gunicorn."
    ),
    (
        "Do not set `DJANGO_SUPERUSER_PASSWORD`, add Railway credential variables, "
        "create a Make target or script, or run this command automatically in build, "
        "pre-deploy, startup, health checks, or Gunicorn."
    ),
)


def operator_runbook(document: str, start: str, end: str) -> str:
    """Return one maintained operator-procedure section."""
    return document[document.index(start) : document.index(end)]


def assert_safe_operator_runbook(runbook: str) -> None:
    """Require the canonical interactive operator procedure and no unsafe variant."""
    normalized_runbook = " ".join(runbook.split())
    command_lines = [
        line
        for line in runbook.splitlines()
        if "bootstrap_development_operator" in line
    ]
    assert command_lines == [OPERATOR_COMMAND]
    command_blocks = re.findall(
        r"(?ms)^(?P<delimiter>`{3}|~{3})[^\n]*\n"
        r"(?P<body>.*?)^(?P=delimiter)[ \t]*$",
        runbook,
    )
    command_block_bodies = [body for _, body in command_blocks]
    operator_command_blocks = [
        block.strip()
        for block in command_block_bodies
        if "bootstrap_development_operator" in block
    ]
    assert operator_command_blocks == [OPERATOR_PROCEDURE]
    assert not any(
        credential in block
        for block in command_block_bodies
        for credential in (
            "DJANGO_SUPERUSER_PASSWORD",
            "RAILWAY_TOKEN",
            "RAILWAY_API_TOKEN",
        )
    )
    assert "RAILWAY_TOKEN" not in runbook
    assert "RAILWAY_API_TOKEN" not in runbook
    assert runbook.count("DJANGO_SUPERUSER_PASSWORD") == 1
    assert any(
        prohibition in normalized_runbook
        for prohibition in OPERATOR_AUTOMATION_PROHIBITIONS
    )

    assert "bootstrap Railway Development operator" in normalized_runbook
    for prohibition in OPERATOR_AUTOMATION_PROHIBITIONS:
        normalized_runbook = normalized_runbook.replace(prohibition, "")
    assert "automatically" not in normalized_runbook


def test_railway_operator_documentation_preserves_the_interactive_boundary() -> None:
    """The documented Railway operator path is canonical and credential-safe."""
    readme = (SERVICE_ROOT / "README.md").read_text()
    operations = (
        REPOSITORY_ROOT / "docs/development/backend-delivery-operations.md"
    ).read_text()
    readme_runbook = operator_runbook(
        readme, "### Railway Development operator", "## Direct Compose usage"
    )
    operations_runbook = operator_runbook(
        operations,
        "## Django admin and Development operator",
        "## Find state and logs",
    )

    assert_safe_operator_runbook(readme_runbook)
    assert_safe_operator_runbook(operations_runbook)
    documentation = f"{readme}\n{operations}"
    normalized_documentation = " ".join(documentation.split())

    assert OPERATOR_PROCEDURE in readme
    assert OPERATOR_PROCEDURE in operations
    for required_guidance in (
        "copy the exact SSH command from the Railway dashboard",
        "hidden interactive prompts",
        "visible confirmation prompt",
        "bootstrap Railway Development operator",
        "No Clerk secret is required.",
        "shell history, logs, issues, pull requests, or committed evidence",
        "ordinary, staff-only, or superuser-only player account",
        "collects Django admin static assets during its image build",
        "WhiteNoise",
        "private media remains in the configured S3/R2 backend",
        "Image build fails at `collectstatic`",
        "runtime static-delivery failure",
    ):
        assert required_guidance in normalized_documentation

    assert "Do not set `DJANGO_SUPERUSER_PASSWORD`" in normalized_documentation
    assert "Railway credential variables" in normalized_documentation
    assert "run the command automatically" in normalized_documentation


def test_railway_operator_runbook_rejects_plausible_unsafe_mutants() -> None:
    """Unsafe credential, fence, and automation guidance must fail the contract."""
    readme = (SERVICE_ROOT / "README.md").read_text()
    runbook = operator_runbook(
        readme, "### Railway Development operator", "## Direct Compose usage"
    )
    unsafe_mutants = (
        runbook.replace(
            "No Clerk secret is required.",
            "No Clerk secret is required. Add a RAILWAY_TOKEN variable in the "
            "Railway dashboard.",
        ),
        f"{runbook}\n```shell\nRAILWAY_TOKEN\n```\n",
        f"{runbook}\n```\nRAILWAY_API_TOKEN\n```\n",
        f"{runbook}\n~~~shell\nRAILWAY_TOKEN\n~~~\n",
        f"{runbook}\nRun it automatically during pre-deploy.\n",
    )

    for mutant in unsafe_mutants:
        with pytest.raises(AssertionError):
            assert_safe_operator_runbook(mutant)


STAGING_OPERATOR_COMMAND = (
    "python manage.py bootstrap_staging_operator --settings=config.settings.production"
)
STAGING_OPERATOR_PROCEDURE = (
    "railway ssh --project 85324de4-be6a-49c3-a3f9-6cac13877849 "
    f"--service api --environment staging\n{STAGING_OPERATOR_COMMAND}"
)
STAGING_OPERATOR_CONFIRMATION = "bootstrap Railway Staging operator"
OPERATOR_AUDIT_RUNBOOK = (
    REPOSITORY_ROOT / "docs/operations/operator-authorization-audit.md"
)
SENSITIVE_OPERATOR_ACTION_MATRIX = (
    ("remove_catch", "catches.catch", "catches.delete_catch", "view_catch"),
    (
        "revoke_catch_credential",
        "conventions.fursuitcatchcredential",
        "conventions.revoke_catch_credential",
        "view_fursuitcatchcredential",
    ),
    (
        "terminate_catch_session",
        "conventions.fursuitcatchsession",
        "conventions.terminate_catch_session",
        "view_fursuitcatchsession",
    ),
    (
        "deactivate_fursuit_activation",
        "conventions.fursuitactivation",
        "conventions.deactivate_fursuit_activation",
        "view_fursuitactivation",
    ),
    (
        "remove_convention_enrollment",
        "conventions.conventionenrollment",
        "conventions.remove_convention_enrollment",
        "view_conventionenrollment",
    ),
    (
        "set_profile_enabled",
        "profiles.playerprofile",
        "profiles.set_profile_enabled",
        "view_playerprofile",
    ),
    (
        "set_fursuit_enabled",
        "fursuits.fursuit",
        "fursuits.set_fursuit_enabled",
        "view_fursuit",
    ),
    (
        "set_convention_playability",
        "conventions.convention",
        "conventions.set_convention_playability",
        "view_convention",
    ),
)

SENSITIVE_INSPECTION_ALTERNATIVE_ACTIONS = frozenset(
    {
        "remove_catch",
        "revoke_catch_credential",
        "terminate_catch_session",
        "deactivate_fursuit_activation",
    }
)

GENERIC_PERMISSION_CODENAMES_BY_ACTION = {
    "remove_catch": ("catches.change_catch", "catches.view_catch"),
    "revoke_catch_credential": (
        "conventions.change_fursuitcatchcredential",
        "conventions.delete_fursuitcatchcredential",
        "conventions.view_fursuitcatchcredential",
    ),
    "terminate_catch_session": (
        "conventions.change_fursuitcatchsession",
        "conventions.delete_fursuitcatchsession",
        "conventions.view_fursuitcatchsession",
    ),
    "deactivate_fursuit_activation": (
        "conventions.change_fursuitactivation",
        "conventions.delete_fursuitactivation",
        "conventions.view_fursuitactivation",
    ),
    "remove_convention_enrollment": (
        "conventions.change_conventionenrollment",
        "conventions.delete_conventionenrollment",
        "conventions.view_conventionenrollment",
    ),
    "set_profile_enabled": (
        "profiles.change_playerprofile",
        "profiles.delete_playerprofile",
        "profiles.view_playerprofile",
    ),
    "set_fursuit_enabled": (
        "fursuits.change_fursuit",
        "fursuits.delete_fursuit",
        "fursuits.view_fursuit",
    ),
    "set_convention_playability": (
        "conventions.change_convention",
        "conventions.delete_convention",
        "conventions.view_convention",
    ),
}

GENERIC_PERMISSION_CODENAMES = tuple(
    generic_permission
    for generic_permissions in GENERIC_PERMISSION_CODENAMES_BY_ACTION.values()
    for generic_permission in generic_permissions
)

AUDIT_PRIVACY_EXCLUSIONS = (
    ("secrets", r"secrets"),
    ("credentials", r"credentials"),
    ("tokens", r"tokens"),
    ("Clerk identifiers", r"Clerk.{0,40}identif"),
    ("provider identifiers", r"provider identifiers"),
    ("emails", r"emails"),
    ("QR payloads", r"QR.{0,40}payload"),
    ("private URLs", r"private URLs"),
    ("raw request bodies", r"raw request bodies"),
    ("broad object snapshots", r"broad.{0,80}object.{0,80}snapshot"),
    ("broad permission snapshots", r"broad.{0,80}permission.{0,80}snapshot"),
    ("broad group snapshots", r"broad.{0,80}group.{0,80}snapshot"),
    ("exception detail", r"exception detail"),
)


def assert_no_concrete_generic_permission_prerequisites(runbook: str) -> None:
    """Reject generic-permission prerequisites for each sensitive action."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(runbook.split()))
    explicit_negation = (
        r"\b(?:not required|never required|does not require|doesn't require|"
        r"need not|not needed|never needed)\b"
    )
    prerequisite_language = (
        r"\b(?:authorize|grant|substitute|requires?|needs?|(?:is )?required|"
        r"(?:additional )?prerequisite|"
        r"must hold|must have|has to have|only available after|"
        r"before (?:invoking|executing))\b"
    )

    for action, _, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX:
        generic_permissions = GENERIC_PERMISSION_CODENAMES_BY_ACTION[action]
        for sentence in sentences:
            if operation_permission not in sentence and not re.search(
                r"(?i)sensitive (?:action|operation)", sentence
            ):
                continue
            if re.search(rf"(?i){explicit_negation}", sentence):
                continue
            for generic_permission in generic_permissions:
                if generic_permission in sentence:
                    assert not re.search(rf"(?i){prerequisite_language}", sentence)


def assert_no_ordinary_sensitive_inspection_grants(runbook: str) -> None:
    """Keep ordinary-record inspection on its explicit Django view permission."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(runbook.split()))
    inspection_grant = (
        r"\b(?:grant|allow|permit|authorize)s?.{0,160}"
        r"\b(?:inspect(?:ion)?|brows(?:e|ing)|read|view)"
    )
    negation = r"\b(?:does not|do not|never|not)\b"

    for (
        action,
        _,
        operation_permission,
        read_permission,
    ) in SENSITIVE_OPERATOR_ACTION_MATRIX:
        if action in SENSITIVE_INSPECTION_ALTERNATIVE_ACTIONS:
            continue
        for sentence in sentences:
            if operation_permission not in sentence:
                continue
            if re.search(rf"(?i){negation}", sentence):
                continue
            if re.search(rf"(?i){inspection_grant}", sentence):
                assert read_permission in sentence


def assert_staging_operator_authority_boundary(runbook: str) -> None:
    """Require operation authority, rather than staff/group/model-permission authority."""
    normalized_runbook = " ".join(runbook.split())

    assert re.search(
        r"(?i)is_staff(?:=True)?.{0,180}(?:never|does not|not).{0,120}"
        r"(?:authorize|grant).{0,120}sensitive operations",
        normalized_runbook,
    )
    assert not re.search(
        r"(?i)is_staff(?:=True)?(?:(?!\b(?:never|does not|not)\b).){0,180}"
        r"(?:authorize|grant).{0,120}sensitive operations",
        normalized_runbook,
    )
    for generic_permission in ("change_*", "delete_*", "view_*"):
        assert generic_permission in runbook
    assert re.search(
        r"(?i)generic.{0,160}(?:never|does not|not).{0,120}"
        r"(?:substitute|authorize).{0,120}sensitive",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)generic.{0,160}neither.{0,100}(?:substitute|authorize).{0,100}"
        r"nor.{0,100}(?:additional )?prerequisite.{0,120}sensitive",
        normalized_runbook,
    )
    assert not re.search(
        r"(?i)generic.{0,160}(?:change_\*|delete_\*|view_\*).{0,120}"
        r"(?:authorize|grant).{0,120}sensitive",
        normalized_runbook,
    )
    assert not re.search(
        r"(?i)generic.{0,160}(?:change_\*|delete_\*|view_\*)"
        r"(?:(?!\b(?:neither|never|does not|not)\b).){0,120}"
        r"(?:additional )?prerequisite.{0,120}sensitive",
        normalized_runbook,
    )
    for generic_permission in GENERIC_PERMISSION_CODENAMES:
        assert generic_permission in runbook
    assert_no_concrete_generic_permission_prerequisites(runbook)
    assert re.search(
        r"catches\.delete_catch.{0,180}(?i:explicit).{0,120}"
        r"(?i:correction|action) authority",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)catches\.delete_catch.{0,160}"
        r"(?:built-in|Django).{0,80}model permission",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)catches\.delete_catch.{0,180}(?:only|solely|limited).{0,120}"
        r"Catch correction",
        normalized_runbook,
    )
    assert not re.search(
        r"(?i)catches\.delete_catch(?:(?!\b(?:does not|never|not)\b).){0,180}"
        r"generic substitution",
        normalized_runbook,
    )

    assert re.search(
        r"(?i)normal Staging operator.{0,180}is_staff=True",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)normal Staging operator.{0,180}is_superuser=False",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)normal Staging operator.{0,180}exact explicit permissions",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)group.{0,160}assignment convenience.{0,160}"
        r"(?:exact )?explicit permissions",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)provision(?:ing|ed)?.{0,180}(?:does not|never).{0,120}"
        r"(?:create|make).{0,120}(?:normal )?operator.{0,120}superuser",
        normalized_runbook,
    )
    assert not re.search(
        r"(?i)(?:normal )?Staging operator.{0,120}is_superuser=True",
        normalized_runbook,
    )


def assert_safe_staging_operator_runbook(runbook: str) -> None:
    """Require the one guarded, interactive Staging provisioning procedure."""
    normalized_runbook = " ".join(runbook.split())
    command_lines = [
        line for line in runbook.splitlines() if "bootstrap_staging_operator" in line
    ]
    assert command_lines == [STAGING_OPERATOR_COMMAND]
    command_blocks = re.findall(
        r"(?ms)^(?P<delimiter>`{3}|~{3})[^\n]*\n"
        r"(?P<body>.*?)^(?P=delimiter)[ \t]*$",
        runbook,
    )
    operator_command_blocks = [
        body.strip()
        for _, body in command_blocks
        if "bootstrap_staging_operator" in body
    ]
    assert operator_command_blocks == [STAGING_OPERATOR_PROCEDURE]

    for credential_name in (
        "RAILWAY_TOKEN",
        "RAILWAY_API_TOKEN",
        "DJANGO_SUPERUSER_PASSWORD",
    ):
        assert credential_name not in runbook
    assert not re.search(
        r"(?mi)(?:^|\s)(?:export\s+)?[A-Z][A-Z0-9_]*"
        r"(?:TOKEN|PASSWORD|SECRET|CREDENTIAL)[A-Z0-9_]*=",
        runbook,
    )
    assert not re.search(r"(?i)--(?:password|credential|token)(?:=|\s)", runbook)

    assert "RAILWAY_ENVIRONMENT_NAME=staging" in runbook
    assert "RAILWAY_SERVICE_NAME=api" in runbook
    assert re.search(
        r"(?i)(?:hidden|not echoed).{0,100}(?:input|prompt)", normalized_runbook
    )
    assert "identifier" in normalized_runbook
    assert "password" in normalized_runbook
    assert STAGING_OPERATOR_CONFIRMATION in runbook
    assert re.search(
        r"(?i)(?:never|do not).{0,120}(?:credential|identifier|password).{0,120}"
        r"(?:command argument|environment variable)",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)(?:reject|fail).{0,160}(?:wrong|different|non-staging|outside|not)"
        r".{0,160}(?:target|environment|service|staging|api)",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)(?:do not|never).{0,120}automatically.{0,120}"
        r"(?:build|pre-deploy|startup|health check|gunicorn)",
        normalized_runbook,
    )
    assert_staging_operator_authority_boundary(runbook)


def assert_documented_operator_action_matrix(runbook: str) -> None:
    """Require one readable action/target/operation/read-permission matrix."""
    assert "| Audit action |" in runbook
    normalized_runbook = " ".join(runbook.split())
    assert_no_ordinary_sensitive_inspection_grants(runbook)
    for (
        action,
        target,
        operation_permission,
        read_permission,
    ) in SENSITIVE_OPERATOR_ACTION_MATRIX:
        matrix_rows = [
            line
            for line in runbook.splitlines()
            if action in line and target in line and operation_permission in line
        ]
        assert len(matrix_rows) == 1
        matrix_row = matrix_rows[0].replace("`", "").replace("*", "")
        assert read_permission in matrix_row
        assert operation_permission in matrix_row
        assert re.search(
            rf"{re.escape(operation_permission)}.{{0,180}}"
            r"(?:independently|on its own).{0,80}sufficient.{0,120}"
            r"(?:action|operation)",
            matrix_row,
        )
        read_alternative_patterns = (
            rf"{re.escape(read_permission)}\s+(?:or|OR)\s+{re.escape(operation_permission)}",
            rf"{re.escape(operation_permission)}\s+(?:or|OR)\s+{re.escape(read_permission)}",
        )
        if action in SENSITIVE_INSPECTION_ALTERNATIVE_ACTIONS:
            assert any(
                re.search(pattern, matrix_row) for pattern in read_alternative_patterns
            )
        else:
            assert re.search(
                rf"{re.escape(read_permission)}.{{0,120}}"
                r"(?:normal|explicit|required)",
                matrix_row,
            )
            assert not any(
                re.search(pattern, matrix_row) for pattern in read_alternative_patterns
            )
        assert not re.search(
            rf"{re.escape(operation_permission)}"
            r"(?:(?!\b(?:does not|never|not)\b).){0,180}"
            r"(?:requires|prerequisite).{0,120}generic.{0,80}"
            r"(?:change_\*|delete_\*|view_\*)",
            normalized_runbook,
        )


def test_staging_operator_documentation_defines_the_guarded_provisioning_path() -> None:
    """AC-11: Staging provisioning is exact, interactive, and target-bound."""
    runbook = OPERATOR_AUDIT_RUNBOOK.read_text()

    assert_safe_staging_operator_runbook(runbook)
    normalized_runbook = " ".join(runbook.split())
    assert "TailTag Field Beta Operators" in runbook
    assert_documented_operator_action_matrix(runbook)
    assert re.search(
        r"(?i)TailTag Field Beta Operators.{0,180}convenience",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)(?:authorization|admin checks).{0,180}explicit.{0,80}permission",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)normal operator.{0,180}explicit.{0,80}permission",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)superuser.{0,180}emergency-only",
        normalized_runbook,
    )


def assert_negated_audit_privacy_exclusions(runbook: str) -> None:
    """Require every privacy exclusion to be negative in an audit-record context."""
    paragraphs = tuple(
        " ".join(paragraph.split())
        for paragraph in re.split(r"\n\s*\n", runbook)
        if paragraph.strip()
    )
    audit_context = r"(?:audit (?:record|row|event|evidence)s?|OperatorAuditEvent)"
    negation = r"(?:must not|do not|never|exclude)"

    for excluded_value, excluded_pattern in AUDIT_PRIVACY_EXCLUSIONS:
        matching_paragraphs = [
            paragraph
            for paragraph in paragraphs
            if re.search(rf"(?i){audit_context}", paragraph)
            and any(
                re.search(rf"(?i){negation}.{{0,480}}{excluded_pattern}", sentence)
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            )
        ]
        assert matching_paragraphs, excluded_value
        assert not any(
            re.search(rf"(?i){audit_context}", paragraph)
            and any(
                re.search(
                    rf"(?i)^(?:(?!\b(?:must not|do not|never|exclude)\b).)*"
                    rf"(?:include|store|contain|record).{{0,360}}{excluded_pattern}",
                    sentence,
                )
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            )
            for paragraph in paragraphs
        ), excluded_value


def test_operator_audit_documentation_defines_safe_durable_evidence() -> None:
    """AC-11: evidence uses the durable audit record, not framework/log history."""
    runbook = OPERATOR_AUDIT_RUNBOOK.read_text()
    normalized_runbook = " ".join(runbook.split())

    assert "OperatorAuditEvent" in runbook
    assert re.search(r"(?i)durable.{0,100}database", normalized_runbook)
    minimum_schema = re.search(
        r"(?i)(?:minimum|closed).{0,100}"
        r"(?:audit (?:record|event)|OperatorAuditEvent).{0,120}"
        r"(?:schema|fields?)"
        r"(?P<fields>.{0,1800})",
        normalized_runbook,
    )
    assert minimum_schema
    for field_pattern in (
        r"stable.{0,80}event ID",
        r"\baction\b",
        r"actor.{0,80}(?:application|Django).{0,80}user ID",
        r"actor class",
        r"affected record type",
        r"affected record ID",
        r"\boutcome\b",
        r"\btimestamp\b",
    ):
        assert re.search(field_pattern, minimum_schema.group("fields"), re.IGNORECASE)
    assert re.search(
        r"(?i)LogEntry.{0,180}(?:not|neither).{0,80}authoritative",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)(?:structured|application|Railway).{0,80}logs?.{0,180}"
        r"(?:not|neither).{0,80}authoritative",
        normalized_runbook,
    )
    assert re.search(r"(?i)no.{0,80}audit.{0,80}viewer", normalized_runbook)
    assert re.search(
        r"(?i)audit rows?.{0,180}only.{0,120}approved.{0,120}"
        r"(?:database|operator) procedures?",
        normalized_runbook,
    )
    outcome_definitions = {
        "succeeded": r"`succeeded`.{0,180}(?:requested )?(?:state )?transition"
        r".{0,120}commit",
        "denied": r"`denied`.{0,180}(?:authenticated|staff).{0,180}"
        r"(?:lack|without).{0,80}(?:permission|authority)",
        "rejected": r"`rejected`.{0,180}(?:authorized|permission).{0,180}"
        r"(?:invalid|current state|domain contract)",
        "failed": r"`failed`.{0,180}(?:unexpected|failure).{0,180}"
        r"(?:did not|does not).{0,120}commit",
    }
    for outcome, definition in outcome_definitions.items():
        assert f"`{outcome}`" in runbook
        assert re.search(definition, normalized_runbook)
    assert_negated_audit_privacy_exclusions(runbook)
    assert "#204" in runbook
    assert re.search(
        r"(?i)(?:retain|retention).{0,180}(?:no automatic|not automatically)",
        normalized_runbook,
    )
    assert re.search(
        r"(?i)(?:retain|retention).{0,180}until.{0,180}"
        r"future documented.{0,80}policy",
        normalized_runbook,
    )
    assert "catastrophic database failure" in normalized_runbook


def assert_current_catch_operator_documentation(catch_documentation: str) -> None:
    """Keep Catch inspection and durable audit evidence on their frozen boundaries."""
    normalized_documentation = " ".join(catch_documentation.split())
    inspection_alternatives = (
        (
            r"catches\.view_catch.{0,120}\b(?:or|OR)\b.{0,120}"
            r"catches\.delete_catch"
        ),
        (
            r"catches\.delete_catch.{0,120}\b(?:or|OR)\b.{0,120}"
            r"catches\.view_catch"
        ),
    )
    assert any(
        re.search(pattern, normalized_documentation)
        for pattern in inspection_alternatives
    )
    assert "OperatorAuditEvent" in catch_documentation

    sentences = re.split(r"(?<=[.!?])\s+", normalized_documentation)
    for sentence in sentences:
        if (
            "catches.view_catch" in sentence
            and re.search(r"(?i)\b(?:only|alone)\b", sentence)
            and re.search(r"(?i)\b(?:den(?:y|ied)|bar|block|refuse)", sentence)
        ):
            assert re.search(
                r"(?i)\b(?:not|never)\s+(?:deny|denied|bar|block|refuse)", sentence
            )
        if re.search(
            r"(?i)(?:transaction\.on_commit\(\)|(?:structured )?application logs?)",
            sentence,
        ) and re.search(r"(?i)\bauthoritative\b", sentence):
            assert re.search(
                r"(?i)\b(?:not|never|neither)\b.{0,80}\bauthoritative\b", sentence
            )


def assert_api_readme_allows_normal_operator_password(readme: str) -> None:
    """Do not leave usable local passwords exclusive to a superuser bootstrap path."""
    normalized_readme = " ".join(readme.split())
    assert re.search(
        r"(?i)(?:is_staff(?:=True)?|staff|operator).{0,160}"
        r"(?:usable )?(?:local|Django) password",
        normalized_readme,
    )
    assert not re.search(
        r"(?i)\bonly\b.{0,160}(?:superuser.{0,80}bootstrap|"
        r"bootstrap.{0,80}superuser).{0,160}(?:accept|allow).{0,160}"
        r"(?:usable )?(?:local|Django) password",
        normalized_readme,
    )


def test_operator_audit_documentation_rejects_contradictory_privacy_mutants() -> None:
    """AC-11: a positive inclusion claim cannot coexist with an exclusion list."""
    runbook = OPERATOR_AUDIT_RUNBOOK.read_text()

    for excluded_value, _ in AUDIT_PRIVACY_EXCLUSIONS:
        mutant = f"{runbook}\nAudit evidence includes {excluded_value}.\n"
        with pytest.raises(AssertionError):
            assert_negated_audit_privacy_exclusions(mutant)


def test_audit_privacy_helper_accepts_scoped_allowed_and_excluded_fields() -> None:
    """An allowed-field sentence may precede explicit exclusions in one paragraph."""
    excluded_values = ", ".join(
        excluded_value for excluded_value, _ in AUDIT_PRIVACY_EXCLUSIONS
    )
    compliant = (
        "OperatorAuditEvent audit records contain only the closed allowed fields. "
        f"They never include {excluded_values}."
    )

    assert_negated_audit_privacy_exclusions(compliant)

    contradictory = f"{compliant} Audit evidence includes Clerk identifiers."
    with pytest.raises(AssertionError):
        assert_negated_audit_privacy_exclusions(contradictory)


def test_stale_operator_documentation_helpers_reject_retained_claims() -> None:
    """Frozen inspection, audit, and password boundaries reject stale guidance."""
    compliant_catch_documentation = (
        "Catch inspection requires `catches.view_catch` or "
        "`catches.delete_catch`. "
        "`OperatorAuditEvent` is the durable audit record. "
        "Structured application logs are not authoritative."
    )
    assert_current_catch_operator_documentation(compliant_catch_documentation)

    for stale_catch_claim in (
        "Users with only `catches.view_catch` are denied Catch inspection.",
        (
            "Structured application logs emitted with transaction.on_commit() are "
            "authoritative audit evidence."
        ),
    ):
        with pytest.raises(AssertionError):
            assert_current_catch_operator_documentation(
                f"{compliant_catch_documentation} {stale_catch_claim}"
            )

    compliant_readme = (
        "A normal `is_staff=True` operator can use a usable local password for "
        "Django administration."
    )
    assert_api_readme_allows_normal_operator_password(compliant_readme)
    with pytest.raises(AssertionError):
        assert_api_readme_allows_normal_operator_password(
            f"{compliant_readme} Only the superuser bootstrap path accepts a "
            "usable local password."
        )


def test_concrete_permission_helper_allows_explicit_non_prerequisites() -> None:
    """Concrete view/change/delete guidance may explicitly reject prerequisites."""
    compliant = "\n".join(
        f"`{generic_permission}` is not required before executing "
        f"`{operation_permission}`."
        for action, _, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX
        for generic_permission in GENERIC_PERMISSION_CODENAMES_BY_ACTION[action]
    )

    assert_no_concrete_generic_permission_prerequisites(compliant)


def test_concrete_permission_helper_rejects_action_bound_prerequisites() -> None:
    """Each real sensitive action rejects its relevant model-permission gates."""
    prerequisite_mutants = (
        "`{generic_permission}` is required before `{operation_permission}`.",
        "`{generic_permission}` must hold before `{operation_permission}`.",
        (
            "A user must have `{generic_permission}` before executing "
            "`{operation_permission}`."
        ),
        (
            "A user has to have `{generic_permission}` before invoking "
            "`{operation_permission}`."
        ),
        (
            "`{operation_permission}` is only available after "
            "`{generic_permission}` is granted."
        ),
        "`{operation_permission}` requires `{generic_permission}`.",
    )

    for action, _, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX:
        for generic_permission in GENERIC_PERMISSION_CODENAMES_BY_ACTION[action]:
            for prerequisite_mutant in prerequisite_mutants:
                with pytest.raises(AssertionError):
                    assert_no_concrete_generic_permission_prerequisites(
                        prerequisite_mutant.format(
                            generic_permission=generic_permission,
                            operation_permission=operation_permission,
                        )
                    )


def test_ordinary_inspection_helper_rejects_sensitive_permission_grants() -> None:
    """Ordinary records cannot turn mutation permission into read authority."""
    for action, target, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX:
        if action in SENSITIVE_INSPECTION_ALTERNATIVE_ACTIONS:
            continue
        for inspection_grant in (
            f"`{operation_permission}` grants inspection of `{target}`.",
            f"`{operation_permission}` allows browsing `{target}`.",
        ):
            with pytest.raises(AssertionError):
                assert_no_ordinary_sensitive_inspection_grants(inspection_grant)


def markdown_section(document: str, heading_pattern: str) -> str:
    """Return a level-two documentation section identified by its semantic heading."""
    heading = re.search(heading_pattern, document)
    assert heading
    next_heading = re.search(r"(?m)^##\s+", document[heading.end() :])
    end = heading.end() + next_heading.start() if next_heading else len(document)
    return document[heading.start() : end]


STAGING_OPERATOR_PROOF_CASES = (
    (
        1,
        (
            r"(?i)ordinary player",
            r"(?i)(?:cannot|denied).{0,120}(?:browse|inspect).{0,120}sensitive admin",
            r"(?i)(?:cannot|denied).{0,120}(?:execute|mutation).{0,120}sensitive admin",
        ),
    ),
    (
        2,
        (
            r"is_staff=True",
            r"(?i)(?:without|lacking).{0,80}target sensitive permission",
            r"(?i)denied",
            r"(?i)exactly one.{0,80}sanitized.{0,80}`denied`.{0,80}audit row",
            r"(?i)no mutation",
        ),
    ),
    (3, (r"(?i)explicitly permitted", r"(?i)non-superuser operator", r"(?i)succeeds")),
    (
        4,
        (
            r"(?i)permitted.{0,80}one action",
            r"(?i)(?:cannot|denied)",
            r"(?i)(?:different|another).{0,80}sensitive permission boundary",
        ),
    ),
    (
        5,
        (
            r"(?i)superuser",
            r"(?i)succeeds",
            r"actor_class=emergency_superuser",
        ),
    ),
    (
        6,
        (
            r"(?i)exactly one.{0,80}sanitized.{0,80}durable.{0,80}audit row",
            r"(?i)action",
            r"(?i)actor class",
            r"(?i)target type/ID",
            r"`succeeded`",
            r"(?i)time",
        ),
    ),
    (
        7,
        (
            r"(?i)(?:unauthorized|denied) mutation",
            r"(?i)exactly one.{0,80}sanitized.{0,80}`denied`.{0,80}audit row",
        ),
    ),
    (
        8,
        (
            r"(?i)(?:profile|fursuit).{0,80}disable",
            r"(?i)cascade",
            r"(?i)(?:transactional|data-integrity|integrity)",
            r"(?i)exactly one.{0,80}top-level (?:audit row|event)",
        ),
    ),
    (
        9,
        (
            r"(?i)Catch",
            r"(?i)(?:create|add)",
            r"(?i)edit",
            r"(?i)bulk",
            r"(?i)alternate.{0,80}(?:authority|award)",
            r"(?i)(?:unavailable|remain unavailable)",
        ),
    ),
)


def assert_staging_operator_acceptance_matrix(staging: str) -> None:
    """Require all nine proof cases as individual semantic matrix rows."""
    normalized_staging = " ".join(staging.split())
    proof_matrix = markdown_section(
        staging,
        r"(?mi)^## (?=[^\n]*operator)(?=[^\n]*audit)(?=[^\n]*acceptance).*\n",
    )
    normalized_proof_matrix = " ".join(proof_matrix.split())
    assert re.search(
        r"(?i)(?:execute|execution|run).{0,160}separate explicit authorization",
        normalized_proof_matrix,
    )
    assert re.search(
        r"(?i)(?:isolated.{0,80}Staging|Staging.{0,80}isolated)", proof_matrix
    )
    assert re.search(r"(?i)disposable.{0,80}synthetic records", proof_matrix)
    matrix_rows = [
        line
        for line in proof_matrix.splitlines()
        if re.fullmatch(r"\|\s*\d+\s*\|.*\|", line)
    ]
    assert len(matrix_rows) == len(STAGING_OPERATOR_PROOF_CASES)
    for case_number, required_patterns in STAGING_OPERATOR_PROOF_CASES:
        case_rows = [
            row
            for row in matrix_rows
            if re.fullmatch(rf"\|\s*{case_number}\s*\|.*\|", row)
        ]
        assert len(case_rows) == 1
        for required_pattern in required_patterns:
            assert re.search(required_pattern, case_rows[0])

    template_heading = re.search(r"(?mi)^#+\s+sanitized evidence template\s*$", staging)
    assert template_heading
    next_heading = re.search(r"(?m)^#+\s+", staging[template_heading.end() :])
    template_end = (
        template_heading.end() + next_heading.start() if next_heading else len(staging)
    )
    evidence_template = staging[template_heading.start() : template_end]
    for evidence_field in (
        "action",
        "actor class",
        "target type/ID",
        "`succeeded`",
        "time",
    ):
        assert evidence_field in evidence_template
    assert re.search(
        r"(?i)(?:must not|does not|never|exclude).{0,120}actor.{0,80}"
        r"(?:application|Django|user).{0,80}ID",
        evidence_template,
    )
    assert re.search(
        r"(?i)(?:protected|durable).{0,120}(?:database|audit)"
        r".{0,160}actor.{0,80}(?:application|Django).{0,80}user ID",
        normalized_staging,
    )
    assert "#204" in staging
    assert re.search(
        r"(?i)#204.{0,220}(?:restore|reset).{0,120}disposable.{0,160}"
        r"(?:do not|does not).{0,80}delete.{0,80}audit",
        normalized_staging,
    )


def test_existing_operator_docs_link_the_staging_procedure_and_matrix() -> None:
    """AC-11: Catch, API, and Staging docs retain the shared operational boundary."""
    catch_administration = (
        REPOSITORY_ROOT / "docs/operations/catch-administration.md"
    ).read_text()
    readme = (SERVICE_ROOT / "README.md").read_text()
    staging = (REPOSITORY_ROOT / "docs/development/staging.md").read_text()

    assert_current_catch_operator_documentation(catch_administration)
    assert_api_readme_allows_normal_operator_password(readme)
    assert "operator-authorization-audit.md" in readme
    assert "operator-authorization-audit.md" in staging
    assert_staging_operator_acceptance_matrix(staging)


def test_staging_operator_runbook_rejects_unsafe_documentation_mutants() -> None:
    """AC-11: docs must reject wrong target, noninteractive, and unsafe procedures."""
    runbook = OPERATOR_AUDIT_RUNBOOK.read_text()
    unsafe_prerequisite_mutants = tuple(
        f"{runbook}\n`{operation_permission}` requires generic `change_*` as an "
        "additional prerequisite for its sensitive operation.\n"
        for _, _, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX
    )
    unsafe_concrete_prerequisite_mutants = tuple(
        f"{runbook}\n`{generic_permission}` is an additional prerequisite for "
        "sensitive operations.\n"
        for generic_permission in GENERIC_PERMISSION_CODENAMES
    )
    unsafe_reversed_concrete_prerequisite_mutants = tuple(
        mutant
        for generic_permission in GENERIC_PERMISSION_CODENAMES
        for mutant in (
            f"{runbook}\nThe sensitive operation requires `{generic_permission}`.\n",
            f"{runbook}\n`{generic_permission}` is required before the sensitive operation.\n",
            f"{runbook}\nA user needs `{generic_permission}` for the sensitive operation.\n",
        )
    )
    unsafe_modal_concrete_prerequisite_mutants = tuple(
        mutant
        for generic_permission in GENERIC_PERMISSION_CODENAMES
        for mutant in (
            f"{runbook}\n`{generic_permission}` must hold for the sensitive operation.\n",
            f"{runbook}\nA user must have `{generic_permission}` for the sensitive operation.\n",
            f"{runbook}\nA user has to have `{generic_permission}` for the sensitive operation.\n",
            f"{runbook}\nThe sensitive action is only available after `{generic_permission}` is granted.\n",
            f"{runbook}\n`{generic_permission}` must be granted before invoking the sensitive operation.\n",
            f"{runbook}\n`{generic_permission}` must be granted before executing the sensitive operation.\n",
        )
    )
    unsafe_action_bound_concrete_prerequisite_mutants = tuple(
        f"{runbook}\n`{generic_permission}` must be granted before executing "
        f"`{operation_permission}`.\n"
        for action, _, operation_permission, _ in SENSITIVE_OPERATOR_ACTION_MATRIX
        for generic_permission in GENERIC_PERMISSION_CODENAMES_BY_ACTION[action]
    )
    unsafe_mutants = (
        runbook.replace("--environment staging", "--environment development", 1),
        runbook.replace(
            "RAILWAY_ENVIRONMENT_NAME=staging",
            "RAILWAY_ENVIRONMENT_NAME=development",
            1,
        ),
        runbook.replace(STAGING_OPERATOR_CONFIRMATION, "confirm operator", 1),
        runbook.replace(
            STAGING_OPERATOR_COMMAND,
            f"{STAGING_OPERATOR_COMMAND} --password=not-allowed",
            1,
        ),
        f"{runbook}\n```shell\nRAILWAY_TOKEN=not-allowed\n```\n",
        f"{runbook}\n```shell\nRAILWAY_API_TOKEN=not-allowed\n```\n",
        f"{runbook}\n```shell\nDJANGO_SUPERUSER_PASSWORD=not-allowed\n```\n",
        f"{runbook}\n```shell\nOPERATOR_CREDENTIAL=not-allowed\n```\n",
        f"{runbook}\n`is_staff=True` authorizes sensitive operations.\n",
        f"{runbook}\nGeneric `change_*` permissions authorize sensitive operations.\n",
        f"{runbook}\nGeneric `view_*` is an additional prerequisite for sensitive operations.\n",
        f"{runbook}\n`catches.delete_catch` is a generic substitution.\n",
        f"{runbook}\nThe normal Staging operator is_superuser=True.\n",
        *unsafe_prerequisite_mutants,
        *unsafe_concrete_prerequisite_mutants,
        *unsafe_reversed_concrete_prerequisite_mutants,
        *unsafe_modal_concrete_prerequisite_mutants,
        *unsafe_action_bound_concrete_prerequisite_mutants,
    )

    for mutant in unsafe_mutants:
        assert mutant != runbook
        with pytest.raises(AssertionError):
            assert_safe_staging_operator_runbook(mutant)


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


ISSUE_206_SPEC = (
    REPOSITORY_ROOT / "docs/specs/2026-09-22-v0-migration-application-rollback.md"
)
ISSUE_206_PLAN = (
    REPOSITORY_ROOT
    / "docs/specs/2026-09-22-v0-migration-application-rollback-implementation-plan.md"
)
ISSUE_206_SPEC_INDEX = REPOSITORY_ROOT / "docs/specs/README.md"
ISSUE_206_DELIVERY_RUNBOOK = (
    REPOSITORY_ROOT / "docs/development/backend-delivery-operations.md"
)
ISSUE_206_STAGING_RUNBOOK = REPOSITORY_ROOT / "docs/development/staging.md"
ISSUE_206_EVIDENCE = (
    REPOSITORY_ROOT
    / "docs/development/staging-recovery/2026-09-22-issue-206-no-go.json"
)

ISSUE_206_EVIDENCE_TOP_LEVEL_KEYS = frozenset(
    {
        "issue",
        "decision",
        "live_mutation",
        "safe_recovery",
        "retained_deployments",
        "migration_analysis",
        "schema_reconciliation",
        "compatibility_proof",
        "operator_state_incompatibility",
        "railway_rollback_api",
        "pre_deploy_command",
        "future_rehearsal",
        "cleanup",
        "limitations",
    }
)
ISSUE_206_EVIDENCE_ALLOWED_NESTED_KEYS = frozenset(
    {
        "old",
        "current",
        "non_representative",
        "deployment_id",
        "source_sha",
        "can_rollback",
        "active",
        "preferred_boundary",
        "retained_to_current",
        "old_source_sha",
        "new_source_sha",
        "migrations",
        "staging_deployed",
        "applied_migrations_reconciled",
        "schema_matches_reviewed_graph",
        "partial_migration_evidence",
        "manual_database_changes_suspected",
        "disposable_postgresql",
        "old_migration_plan_empty",
        "django_checks_passed",
        "focused_domain_read_write_passed",
        "reverse_migrations_run",
        "rehearsal_table_and_record_preserved",
        "rehearsal_fk_rejects_unaware_deletion",
        "current_limited_operator_has_usable_local_auth",
        "old_save_invalidates_local_auth",
        "rollback_application_safe",
        "can_rollback_signature",
        "rollback_mutation_signature",
        "result_deployment_id_returned",
        "stored_image_reused_without_rebuild",
        "historical_variable_snapshot_restored",
        "status",
        "rollback_target_symbol",
        "active_deployment_symbol",
        "result_deployment_symbol",
        "exact_target_api_call",
        "new_deployment_derivation",
        "ambiguous_outcome",
        "exact_instance_attribution",
        "restoration",
        "task_owned_postgresql_containers_removed",
        "temporary_source_trees_removed",
    }
)
ISSUE_206_SENSITIVE_EVIDENCE_KEY = re.compile(
    r"(?i)(?:password|credential|token|secret|variable[_-]?values?|"
    r"private[_-]?(?:url|resource|identifier)|database[_-]?(?:contents?|rows?|dump)|"
    r"(?:user|account|clerk|person|actor)[_-]?id)"
)


def read_required_issue_206_document(path: Path) -> str:
    """Read one approved #206 document, reporting a missing implementation clearly."""
    assert path.is_file(), (
        f"#206 required document is missing: {path.relative_to(REPOSITORY_ROOT)}"
    )
    return path.read_text()


def assert_issue_206_policy_and_compatibility(
    delivery_runbook: str, staging_runbook: str
) -> None:
    """Require both runbooks to retain the fail-closed application/schema policy."""
    for runbook in (delivery_runbook, staging_runbook):
        normalized = " ".join(runbook.split())
        assert "2026-09-22-v0-migration-application-rollback.md" in runbook
        for policy_term in ("Expand", "Compatible", "Contract", "forward fix"):
            assert re.search(rf"(?i)\b{re.escape(policy_term)}\b", normalized)
        assert re.search(
            r"(?i)(?:not|never).{0,100}routine.{0,80}reverse migration", normalized
        )
        assert re.search(
            r"(?i)old application.{0,120}actual schema.{0,120}persisted state",
            normalized,
        )
        assert re.search(
            r"(?i)(?:missing|ambiguous|uncertain).{0,120}(?:NO-GO|forward fix)",
            normalized,
        )

    normalized_staging = " ".join(staging_runbook.split())
    for migration_review_term in (
        "RunPython",
        "RunSQL",
        "state/database split",
        "non-atomic",
        "foreign key",
        "nullability",
        "database default",
        "renamed",
        "removed",
    ):
        assert migration_review_term in staging_runbook
    assert re.search(
        r"(?i)disposable PostgreSQL.{0,160}old.{0,80}application", normalized_staging
    )
    assert re.search(
        r"(?i)(?:do not|without).{0,80}reverse migration", normalized_staging
    )
    assert re.search(r"(?i)focused.{0,80}read.{0,80}write", normalized_staging)


def assert_issue_206_no_go_boundaries(staging_runbook: str) -> None:
    """Require the investigated boundaries and affirmative unsafe-state finding."""
    normalized = " ".join(staging_runbook.split())
    recovery_section = issue_206_staging_recovery_section(staging_runbook)
    for identifier in (
        "04f8383fe750bec712ced27a1932b82b1eabb292",
        "57f17ef7-7b34-4c2f-9272-b8091b1eafad",
        "77b6c55130f1b69304a8fd748590b4bbad3bf721",
        "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a",
        "cbe83780-0256-49c2-b026-34709ddb69b0",
        "756f48e2d90bbb803060cd015e8bcf2d47ad4fbc",
        "3acf7fee-260b-472d-9b20-d1dd76efcb25",
    ):
        assert identifier in staging_runbook
    assert re.search(r"(?i)77b6c55.{0,180}never deployed.{0,80}Staging", normalized)
    assert re.search(r"(?i)no migration delta.{0,160}mechanics only", normalized)
    assert re.search(
        r"(?i)NO-GO.{0,160}live Staging.{0,160}(?:rollback|application)", normalized
    )
    assert re.search(
        r"(?i)no live mutation.{0,160}(?:performed|authorized|required)", normalized
    )
    assert re.search(
        r"(?i)staff/non-superuser.{0,160}usable local password", normalized
    )
    assert re.search(
        r"(?is)(?:#239.{0,400}staff/non-superuser.{0,200}usable local password|"
        r"staff/non-superuser.{0,400}usable local password.{0,400}#239)",
        recovery_section,
    )
    assert re.search(
        r"(?i)(?:old|O).{0,100}save.{0,160}usable password.{0,100}unusable", normalized
    )
    assert re.search(
        r"(?i)(?:schema shape|schema compatibility).{0,120}insufficient", normalized
    )


def issue_206_staging_recovery_section(staging_runbook: str) -> str:
    """Return the #206 recovery section without constraining adjacent runbooks."""
    return markdown_section(
        staging_runbook,
        r"(?mi)^## Migration and application-image recovery \(#206\)\s*$",
    )


def assert_issue_206_railway_rehearsal_procedure(staging_runbook: str) -> None:
    """Require exact-ID rollback evidence, rather than a latest-deployment claim."""
    normalized = " ".join(staging_runbook.split())
    assert "Deployment.canRollback: Boolean!" in staging_runbook
    assert "deploymentRollback(id: String!): Boolean!" in staging_runbook
    assert re.search(
        r"(?i)does not return.{0,80}(?:resulting )?deployment ID", normalized
    )
    assert re.search(r"(?i)PRE_DEPLOY_COMMAND.{0,100}unverified", normalized)
    assert not re.search(
        r"(?i)PRE_DEPLOY_COMMAND.{0,80}(?:runs|reruns|is skipped)", normalized
    )
    for required_step in (
        "exclusive Staging operation window",
        "rollback target **R**",
        "current active deployment **A**",
        "new deployment **D**",
        "deploymentRollback(id: R)",
        "exactly one new deployment **D**",
        "do not retry blindly",
        "#201 image-local identity",
        "canonical Staging HTTP smoke",
        "affected-domain read/write proof",
        "#202 exact-SHA promotion",
        "never a second rollback",
    ):
        assert required_step in staging_runbook
    assert re.search(
        r"(?i)(?:zero|multiple).{0,100}(?:INDETERMINATE|indeterminate)", normalized
    )
    recovery_section = issue_206_staging_recovery_section(staging_runbook)
    assert re.search(r"(?i)(?:never|not).{0,80}`?latest`?", recovery_section)


def assert_issue_206_evidence_keys(value: object) -> None:
    """Reject unallowlisted or secret-bearing keys at every evidence nesting level."""
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        for key, nested_value in mapping.items():
            assert isinstance(key, str)
            assert key in (
                ISSUE_206_EVIDENCE_TOP_LEVEL_KEYS
                | ISSUE_206_EVIDENCE_ALLOWED_NESTED_KEYS
            )
            assert not ISSUE_206_SENSITIVE_EVIDENCE_KEY.search(key)
            assert_issue_206_evidence_keys(nested_value)
    elif isinstance(value, list):
        sequence = cast(list[object], value)
        for item in sequence:
            assert_issue_206_evidence_keys(item)


def assert_exact_json_value(actual: object, expected: object) -> None:
    """Require JSON-compatible values to match in both type and structure."""
    assert type(actual) is type(expected)
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        actual_mapping = cast(dict[object, object], actual)
        expected_mapping = cast(dict[object, object], expected)
        assert set(actual_mapping) == set(expected_mapping)
        for key, expected_value in expected_mapping.items():
            assert_exact_json_value(actual_mapping[key], expected_value)
    elif isinstance(expected, list):
        assert isinstance(actual, list)
        actual_sequence = cast(list[object], actual)
        expected_sequence = cast(list[object], expected)
        assert len(actual_sequence) == len(expected_sequence)
        for actual_value, expected_value in zip(actual_sequence, expected_sequence):
            assert_exact_json_value(actual_value, expected_value)
    else:
        assert actual == expected


def test_issue_206_documentation_is_discoverable_and_defines_policy() -> None:
    """AC-1/2/3: runbooks link #206 and retain the reviewed compatibility gate."""
    spec_index = read_required_issue_206_document(ISSUE_206_SPEC_INDEX)
    delivery_runbook = read_required_issue_206_document(ISSUE_206_DELIVERY_RUNBOOK)
    staging_runbook = read_required_issue_206_document(ISSUE_206_STAGING_RUNBOOK)

    assert ISSUE_206_SPEC.name in spec_index
    assert ISSUE_206_PLAN.name in spec_index
    assert_issue_206_policy_and_compatibility(delivery_runbook, staging_runbook)


def test_issue_206_staging_runbook_records_the_final_no_go() -> None:
    """AC-4/5/8: Staging records the unsafe retained pair and no mutation path."""
    staging_runbook = read_required_issue_206_document(ISSUE_206_STAGING_RUNBOOK)

    assert_issue_206_no_go_boundaries(staging_runbook)


def test_issue_206_staging_runbook_preserves_exact_rollback_evidence_rules() -> None:
    """AC-6/7: future rehearsal is exact-ID, exact-D, and never blind retry."""
    staging_runbook = read_required_issue_206_document(ISSUE_206_STAGING_RUNBOOK)

    assert_issue_206_railway_rehearsal_procedure(staging_runbook)


def test_issue_206_spec_keeps_pre_deploy_as_an_observation() -> None:
    """AC-6: a skipped pre-deploy hook is observed, not predeclared a failure."""
    spec = read_required_issue_206_document(ISSUE_206_SPEC)
    future_procedure = markdown_section(
        spec, r"(?mi)^## Future exact evidence procedure\s*$"
    )
    normalized_future_procedure = " ".join(future_procedure.split())

    assert re.search(r"(?i)PRE_DEPLOY_COMMAND.{0,100}unverified", spec)
    assert re.search(
        r"(?i)record whether `PRE_DEPLOY_COMMAND`.{0,100}occurred",
        normalized_future_procedure,
    )
    assert not re.search(
        r"(?i)(?:skipped|not executed|non-execution).{0,160}"
        r"(?:fails? closed|NO-GO|failure)",
        normalized_future_procedure,
    )


def test_issue_206_staging_runbook_rejects_unsafe_rehearsal_mutants() -> None:
    """AC-6/7: misleading pre-deploy, latest, or second-rollback claims fail."""
    staging_runbook = read_required_issue_206_document(ISSUE_206_STAGING_RUNBOOK)
    recovery_section = issue_206_staging_recovery_section(staging_runbook)
    unsafe_mutants = (
        recovery_section.replace(
            "PRE_DEPLOY_COMMAND remains **unverified**",
            "PRE_DEPLOY_COMMAND runs during rollback",
            1,
        ),
        recovery_section.replace("do not retry blindly", "retry until it succeeds", 1),
        recovery_section.replace("never `latest`", "use `latest`", 1),
        recovery_section.replace(
            "never a second rollback", "use a second rollback for restoration", 1
        ),
    )

    for mutant in unsafe_mutants:
        assert mutant != recovery_section
        with pytest.raises(AssertionError):
            assert_issue_206_railway_rehearsal_procedure(
                staging_runbook.replace(recovery_section, mutant, 1)
            )

    unrelated_latest = (
        f"{staging_runbook}\n## Unrelated historical promotion note\n"
        "A separate historical procedure may use `latest`.\n"
    )
    assert_issue_206_railway_rehearsal_procedure(unrelated_latest)


def test_issue_206_evidence_has_the_sanitized_no_go_shape() -> None:
    """AC-5/9: durable evidence is fixed, complete, and free of sensitive keys."""
    evidence_text = read_required_issue_206_document(ISSUE_206_EVIDENCE)
    loaded_evidence: object = json.loads(evidence_text)

    assert isinstance(loaded_evidence, dict)
    evidence = cast(dict[str, object], loaded_evidence)
    assert set(evidence) == ISSUE_206_EVIDENCE_TOP_LEVEL_KEYS
    assert_exact_json_value(evidence["issue"], "#206")
    assert_exact_json_value(evidence["decision"], "NO_GO")
    assert_exact_json_value(evidence["live_mutation"], False)
    assert_exact_json_value(evidence["safe_recovery"], "FORWARD_FIX")

    retained_deployments = evidence["retained_deployments"]
    assert_exact_json_value(
        retained_deployments,
        {
            "old": {
                "deployment_id": "57f17ef7-7b34-4c2f-9272-b8091b1eafad",
                "source_sha": "04f8383fe750bec712ced27a1932b82b1eabb292",
                "can_rollback": True,
            },
            "current": {
                "deployment_id": "cbe83780-0256-49c2-b026-34709ddb69b0",
                "source_sha": "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a",
                "active": True,
            },
            "non_representative": {
                "deployment_id": "3acf7fee-260b-472d-9b20-d1dd76efcb25",
                "source_sha": "756f48e2d90bbb803060cd015e8bcf2d47ad4fbc",
            },
        },
    )
    assert_exact_json_value(
        evidence["migration_analysis"],
        {
            "preferred_boundary": {
                "old_source_sha": "04f8383fe750bec712ced27a1932b82b1eabb292",
                "new_source_sha": "77b6c55130f1b69304a8fd748590b4bbad3bf721",
                "migrations": ["rehearsal.0001_initial"],
                "staging_deployed": False,
            },
            "retained_to_current": {
                "migrations": [
                    "accounts.0002_staff_local_password",
                    "conventions.0006_operator_permissions",
                    "fursuits.0003_fursuit_operator_permission",
                    "profiles.0002_playerprofile_operator_permission",
                    "operator_audit.0001_initial",
                    "rehearsal.0001_initial",
                ]
            },
            "non_representative": {
                "old_source_sha": "756f48e2d90bbb803060cd015e8bcf2d47ad4fbc",
                "new_source_sha": "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a",
                "migrations": [],
            },
        },
    )
    assert_exact_json_value(
        evidence["schema_reconciliation"],
        {
            "applied_migrations_reconciled": True,
            "schema_matches_reviewed_graph": True,
            "partial_migration_evidence": False,
            "manual_database_changes_suspected": False,
        },
    )
    assert_exact_json_value(
        evidence["compatibility_proof"],
        {
            "disposable_postgresql": True,
            "old_migration_plan_empty": True,
            "django_checks_passed": True,
            "focused_domain_read_write_passed": True,
            "reverse_migrations_run": False,
            "rehearsal_table_and_record_preserved": True,
            "rehearsal_fk_rejects_unaware_deletion": True,
        },
    )
    assert_exact_json_value(
        evidence["operator_state_incompatibility"],
        {
            "current_limited_operator_has_usable_local_auth": True,
            "old_save_invalidates_local_auth": True,
            "rollback_application_safe": False,
        },
    )
    assert_exact_json_value(
        evidence["railway_rollback_api"],
        {
            "can_rollback_signature": "Deployment.canRollback: Boolean!",
            "rollback_mutation_signature": "deploymentRollback(id: String!): Boolean!",
            "result_deployment_id_returned": False,
            "stored_image_reused_without_rebuild": True,
            "historical_variable_snapshot_restored": True,
        },
    )
    assert_exact_json_value(evidence["pre_deploy_command"], {"status": "UNVERIFIED"})
    assert_exact_json_value(
        evidence["future_rehearsal"],
        {
            "rollback_target_symbol": "R",
            "active_deployment_symbol": "A",
            "result_deployment_symbol": "D",
            "exact_target_api_call": "deploymentRollback(id: R)",
            "new_deployment_derivation": "EXACTLY_ONE_POST_OPERATION_DEPLOYMENT",
            "ambiguous_outcome": "INDETERMINATE_NO_RETRY",
            "exact_instance_attribution": "#201",
            "restoration": "#202_EXACT_SHA_PROMOTION",
        },
    )
    assert_exact_json_value(
        evidence["cleanup"],
        {
            "task_owned_postgresql_containers_removed": True,
            "temporary_source_trees_removed": True,
        },
    )
    assert_exact_json_value(
        evidence["limitations"], {"status": "LIVE_ROLLBACK_UNVERIFIED"}
    )

    assert_issue_206_evidence_keys(evidence)

    for numeric_mutant, expected_value in (
        ({"disposable_postgresql": 1}, {"disposable_postgresql": True}),
        ({"reverse_migrations_run": 0}, {"reverse_migrations_run": False}),
    ):
        with pytest.raises(AssertionError):
            assert_exact_json_value(numeric_mutant, expected_value)
