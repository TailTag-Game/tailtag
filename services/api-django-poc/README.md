# TailTag Django API POC

This service is the Django API proof of concept for TailTag. It provides same-origin, session-authenticated account access and owner-scoped fursuit management; it remains a framework evaluation rather than TailTag's final backend architecture.

## Prerequisites

Install Python 3.13, [uv](https://docs.astral.sh/uv/), and Docker Desktop (or another Docker Engine with the Compose plugin). PostgreSQL 17 is required for local tests and runtime checks; this POC intentionally has no SQLite fallback.

Run all commands below from this directory:

```bash
cd services/api-django-poc
```

## Install dependencies

Create the locked development environment:

```bash
uv sync --all-groups --locked
```

For Docker Compose, create the local environment file from the placeholder template:

```bash
cp .env.example .env
```

`.env` is read by Docker Compose and must remain local-only. The host-based `uv run`
commands use the same development defaults automatically; export variables from `.env`
only when you need to override those defaults.

## Run locally

With PostgreSQL 17 available on `localhost:5432` for the local `tailtag` database, apply migrations and create an admin account:

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Then start Django from the local environment:

```bash
uv run python manage.py runserver
```

The liveness endpoint is [http://localhost:8000/health/live](http://localhost:8000/health/live). The database-backed readiness endpoint is [http://localhost:8000/health/ready](http://localhost:8000/health/ready).

The API schema is available at [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/) and interactive documentation at [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/). Django admin is at [http://localhost:8000/admin/](http://localhost:8000/admin/).

The host-based workflow uses `config.settings.local`, PostgreSQL at `localhost`, and
HTTP-safe development cookies. It does not use production settings or production
secrets.

Browser clients first request `GET /api/auth/csrf`, then send the `csrftoken` cookie as `X-CSRFToken` with `credentials: "include"` for signup, login, logout, and every fursuit write. The POC is same-origin; CORS is intentionally unsupported.

## Run with Docker

Build and start the API and PostgreSQL services:

```bash
docker compose up --build
```

Compose runs the API with `config.settings.local` against the `db` service, so browser
authentication works over local HTTP. Migrations never run automatically. Run them
explicitly after the services are available:

```bash
docker compose exec api python manage.py migrate
```

Create a local admin account when needed:

```bash
docker compose exec api python manage.py createsuperuser
```

Stop the services when finished while preserving the named local database volume:

```bash
docker compose down
```

To remove the local PostgreSQL data volume as well, use `docker compose down -v` only
when intentionally resetting the local database.

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

The OpenAPI command validates configuration only. It does not publish a schema or documentation route.

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

If Docker or the Compose plugin is unavailable, install and start Docker Desktop (or a compatible Docker Engine) before using the containerized workflow. Do not substitute SQLite: PostgreSQL is part of the POC contract. After Docker is available, use `docker compose up --build` for the containerized API.

If `/health/ready` reports `{"status": "unavailable"}`, confirm the database is running with `docker compose ps`, then check its logs with `docker compose logs db`.

## Railway deployment adapter

The Railway service should use `/services/api-django-poc` as its root directory.
Configure the Railway config file path as `/services/api-django-poc/railway.toml`.
That file runs migrations as a pre-deploy command and uses `/health/ready` as the
deployment healthcheck. Railway provides the `PORT` environment variable; the
production Gunicorn command consumes it and falls back to port `8000` locally.

The production image collects Django admin static assets during the image build and
serves them through WhiteNoise. Do not run `collectstatic` as a pre-deploy command:
Railway pre-deploy containers do not persist filesystem changes to the web container.
