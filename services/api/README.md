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

## Local configuration

The V0 backend supports PostgreSQL 17 only. Before using either supported local
workflow, create an ignored local environment file from the template:

```bash
cp .env.example .env
```

The template contains safe local-only defaults and no real secrets. Keep `.env`
private: it is ignored by Git and must never be committed. Native local settings
load this file automatically; production settings never load it implicitly.

The configuration uses one shared vocabulary with separate ownership:

| Setting | Required | Used by |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Django. The native template uses `127.0.0.1:5432`. |
| `DJANGO_SECRET_KEY` | Yes | Django. The template value is safe only for local development. |
| `POSTGRES_DB` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `POSTGRES_USER` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `POSTGRES_PASSWORD` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `DJANGO_ALLOWED_HOSTS` | No | Django; local settings use safe defaults if it is omitted. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | No | Django; local settings use safe defaults if it is omitted. |

Django reads database configuration only through `DATABASE_URL`; it does not
read `POSTGRES_*` settings. Compose uses `POSTGRES_*` to configure PostgreSQL
and supplies Django with a container-network URL using `db:5432`. Native Django
uses the explicit `DATABASE_URL` in `.env` and reaches the same published
database at `127.0.0.1:5432`. The host difference is expected because native
and container execution use different network namespaces, not different
configuration contracts.

If `.env` is absent, native Django fails at startup with a sanitized message
naming the missing required setting. Invalid `DATABASE_URL` values also fail at
startup without printing credentials. Do not substitute SQLite.

## Canonical backend commands

Run these commands from the repository root. They wrap the existing `uv`,
Django, and validation tooling so contributors do not need to remember service
paths or individual tool invocations.

| Command | Purpose | Required state |
| --- | --- | --- |
| `make help` | List the supported backend commands. | None. |
| `make api-setup` | Synchronize locked backend dependencies. | `uv` available; does not start services or change schema. |
| `make api-run` | Run Django on port 8000. | Dependencies, `services/api/.env`, and PostgreSQL already available. |
| `make api-test` | Run PostgreSQL-backed backend tests. | Dependencies, `services/api/.env`, and PostgreSQL already available. |
| `make api-check` | Run the complete local pre-PR backend validation suite. | Dependencies, `services/api/.env`, and PostgreSQL already available. |
| `make api-migrate` | **Apply existing Django migrations.** | Dependencies, `services/api/.env`, and PostgreSQL already available; mutates schema. |
| `make api-migrations` | **Create Django migrations from model changes.** | Dependencies and `services/api/.env`; mutates migration state but does not apply migrations. |
| `make api-migrations-check` | Check for migration drift. | Dependencies, `services/api/.env`, and PostgreSQL already available; does not create migrations. |
| `make api-shell` | Open the Django shell. | Dependencies, `services/api/.env`, and PostgreSQL already available. |
| `make api-smoke` | HTTP-check an already-running API. | API already running; it never starts services or applies migrations. |

`api-check` includes Ruff formatting and linting, strict mypy, pytest, Django
system checks, migration-drift detection, OpenAPI validation, and Gunicorn
production-configuration loading. It does not create or apply migrations.

`api-smoke` checks `/health/live`, `/health/ready`, `/api/schema/`, and
`/api/docs/`, expecting HTTP 200 from each. It defaults to
`http://127.0.0.1:8000`; target another already-running environment by setting
`API_BASE_URL`, for example:

```bash
API_BASE_URL=https://example.internal make api-smoke
```

The canonical commands do not manage Docker or Compose lifecycle. Start the
environment you intend to use first, then invoke the command that consumes it.

## Prerequisites

### Devcontainer

For the supported container workflow, install Git, Docker Desktop (or another
Docker Engine with the Compose plugin), and a devcontainer-capable editor. Open
the repository root in that editor and choose its **Reopen in Container**
action. Create `services/api/.env` from the template first. Host Python and
PostgreSQL are not required.

The devcontainer reuses `services/api/compose.yaml`: PostgreSQL starts with its
existing health check and named `postgres_data` volume, while the `api` service
is the editor workspace. The post-create hook runs
`uv sync --all-groups --locked` from `services/api`; it does not run migrations
or make any schema changes.

The editor workspace is the repository root, so `services/api/`, `docs/`, and
`scripts/` remain available. Apply migrations explicitly before starting Django:

```bash
cd services/api
uv run python manage.py migrate
```

Then start Django when needed:

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

Start PostgreSQL 17 through Compose. Compose waits for its `pg_isready` health
check before starting dependent containers, and publishes the database only at
`127.0.0.1:5432` for native Django:

```bash
docker compose up -d db
```

With `.env` in place, apply migrations and create a Django admin account:

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

For the plain Compose workflow, migrations never run automatically. Run them
explicitly after the services are available:

```bash
docker compose exec api python manage.py migrate
```

Stop the services when finished while preserving the named local database volume:

```bash
docker compose down
```

The `postgres_data` named volume preserves database data across normal
stop/start, image rebuild, and devcontainer reopen/rebuild operations. Reset
local database state only intentionally by stopping the Compose services and
removing that named volume:

```bash
docker compose down --volumes
```

This destructive command removes local PostgreSQL data only; migrations remain
an explicit contributor action afterward.

## Validate the service

With PostgreSQL available at `127.0.0.1:5432` and `.env` present, run the same
quality gates as CI:

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
