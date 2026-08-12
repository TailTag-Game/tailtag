# TailTag API

`services/api` is TailTag's V0 Django API foundation. It currently provides
Django administration, PostgreSQL-backed liveness/readiness checks, and OpenAPI
schema/documentation infrastructure. It intentionally does not implement player
authentication, a TailTag application identity, or gameplay APIs.

The service uses Python 3.13, Django, Django REST Framework, PostgreSQL, `uv`,
Ruff, strict mypy, pytest, drf-spectacular, Gunicorn, and Docker.

## Current foundation boundary

Django's built-in `auth.User` remains only so `/admin/` is operational. It is
not the future Clerk-backed TailTag application identity. The neutral `accounts`
and `fursuits` app shells contain no models, migrations, or public API behavior.

The POC application migrations were intentionally reset. On a clean database,
`migrate` applies Django's framework migrations only; future TailTag domain
migrations will be introduced by approved feature work.

## Prerequisites

### Devcontainer

For the supported container workflow, install Git, Docker Desktop (or another
Docker Engine with the Compose plugin), and a devcontainer-capable editor. Open
the repository root in that editor and choose its **Reopen in Container**
action. Host Python and PostgreSQL are not required.

The devcontainer reuses `services/api/compose.yaml`: PostgreSQL starts with its
existing health check and named `postgres_data` volume, while the `api` service
is the editor workspace. The post-create hook runs
`uv sync --all-groups --locked` from `services/api`; it does not run migrations
or make any schema changes.

The editor workspace is the repository root, so `services/api/`, `docs/`, and
`scripts/` remain available. Start Django explicitly when needed:

```bash
cd services/api
uv run python manage.py runserver 0.0.0.0:8000
```

Port 8000 is forwarded by the devcontainer for the Django API. The named
PostgreSQL volume is retained during normal container reopen and rebuild
operations. To intentionally reset the local database, close the devcontainer
services and run this destructive command from the repository root on the host:

```bash
docker compose -f services/api/compose.yaml -f .devcontainer/compose.devcontainer.yaml down --volumes
```

This removes the named local PostgreSQL volume and its data. Migrations remain
an explicit contributor action after the environment is running.

### Native API workflow

Install Python 3.13, [uv](https://docs.astral.sh/uv/), and Docker Desktop (or another Docker Engine with the Compose plugin). PostgreSQL 17 is required for local tests and runtime checks; this API foundation intentionally has no SQLite fallback.

Run all commands below from this directory:

```bash
cd services/api
```

## Install dependencies

Create the locked development environment:

```bash
uv sync --all-groups --locked
```

## Run locally

With PostgreSQL 17 available on `localhost:5432` for the local `tailtag` database, apply migrations and create a Django admin account:

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Then start Django:

```bash
uv run python manage.py runserver
```

The liveness endpoint is [http://localhost:8000/health/live](http://localhost:8000/health/live). The database-backed readiness endpoint is [http://localhost:8000/health/ready](http://localhost:8000/health/ready).

The API schema is available at [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/), interactive documentation at [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/), and Django admin at [http://localhost:8000/admin/](http://localhost:8000/admin/).

## Run with Docker

Build and start the API and PostgreSQL services:

```bash
docker compose up --build
```

Migrations never run automatically. Run them explicitly after the services are available:

```bash
docker compose exec api python manage.py migrate
```

Stop the services when finished while preserving the named local database volume:

```bash
docker compose down
```

## Validate the service

With PostgreSQL available at `localhost:5432`, run the same quality gates as CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest -q
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py spectacular --validate --file /tmp/openapi.yml
```

The OpenAPI command validates the published schema configuration.

Validate that the production Gunicorn configuration loads without starting a persistent server:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY=not-a-real-secret \
DATABASE_URL=postgresql://tailtag:tailtag@localhost:5432/tailtag \
DJANGO_ALLOWED_HOSTS=localhost \
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
uv run gunicorn config.wsgi:application --check-config
```

## Docker troubleshooting

If Docker or the Compose plugin is unavailable, install and start Docker Desktop (or a compatible Docker Engine) before using the containerized workflow. Do not substitute SQLite: PostgreSQL is part of the API foundation contract. After Docker is available, use `docker compose up --build` for the containerized API.

If `/health/ready` reports `{"status": "unavailable"}`, confirm the database is running with `docker compose ps`, then check its logs with `docker compose logs db`.
