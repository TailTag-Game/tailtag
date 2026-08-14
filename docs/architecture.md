# Architecture

Status: accepted V0 direction; the initial backend Phase 0 foundation is present.

## Current direction

TailTag is a monorepo for the community-led rebuild of a social convention game. The V0 backend direction is:

- Python
- Django and Django REST Framework
- PostgreSQL as the primary application database
- Clerk as the player authentication authority
- A TailTag-owned internal application user identity for domain relationships, separate from Clerk
- A modular monolith backend
- Railway for V0 backend hosting

The historical Django POC has been promoted and reset at `services/api/`. Its POC-only authentication, session/CSRF behavior, fursuit fields, routes, deletion behavior, and other experimental choices were evaluation evidence, not V0 requirements.

## Backend phases

Phase 0 established the clean `services/api` foundation and local contributor environment. Phase 1 now has authoritative backend pull-request CI and pre-merge GitHub validation through `make api-check`, its persistent Railway development environment, and an explicit Railway pre-deploy migration step. Post-deploy verification and the formal merge-to-development delivery policy remain separate Stage 1 work. This document does not define production deployment configuration or product application behavior.

## Shared Railway development environment

The V0 development environment is a single, explicitly non-production Railway
project and environment:

| Item | Established configuration |
| --- | --- |
| Workspace | `Finn the Panther's Projects` |
| Project / environment | `TailTag` / `development` |
| API service | `api`, sourced from `TailTag-Game/tailtag` on `main` |
| API service root | `/services/api` |
| Runtime | The existing `services/api/Dockerfile` production image and its Gunicorn CMD on port 8000. Railway supplies `PORT=8000` to the container as platform runtime configuration for networking and health checking. |
| PostgreSQL service | Railway-managed `Postgres` service, reachable only through the API's Railway reference variable. |
| Public API endpoint | `https://api-development-8fa7.up.railway.app` |
| Platform health check | `/health/ready` |

The API service owns these development variable names without recording their
rendered values: `DATABASE_URL` references `${{Postgres.DATABASE_URL}}`,
`DJANGO_SECRET_KEY` is generated and managed in Railway, and
`DJANGO_ALLOWED_HOSTS` plus `DJANGO_CSRF_TRUSTED_ORIGINS` derive from the
Railway development domain. `PORT=8000` is Railway platform runtime
configuration, supplied to the container to match the existing Gunicorn
binding; it is not a Django application variable. `healthcheck.railway.app` is
an allowed host so Railway can evaluate deployment readiness. No SQLite fallback
or public database endpoint is configured.

The `api` service's Railway service settings configure the pre-deploy command
`python manage.py migrate --settings=config.settings.production --noinput`.
Railway runs it for each API deployment attempt after the candidate image is
built and before the candidate Gunicorn process starts. It uses the same
production settings and `DATABASE_URL` reference as the API process; no
migration-specific database configuration exists. This is an explicit deployment
migration step, not a global exactly-once guarantee: a redeploy is a new attempt
and may run the command again. Django records applied migrations, so an
already-current schema normally makes a subsequent invocation a no-op.

The Docker CMD, Gunicorn process, Django startup, health endpoints, and local
`make api-run` command do not run migrations. A non-zero pre-deploy command
fails the candidate deployment before it becomes active; deployment state and
deployment logs provide the diagnostic record. See the [Railway development
environment review](reviews/2026-08-13-railway-development-environment.md) for
the observed recovery and rollback boundaries.

Connecting the API service to the repository establishes the build source but
does not complete the delivery policy. Railway created its normal GitHub
`main` trigger (`checkSuites: false`) with that source connection; this observed
platform default permits the foundation to build, but is not the reviewed
delivery and failure-surfacing contract. Issue #77 owns post-deploy HTTP smoke
verification, and #78 owns the delivery policy. This environment contains no
production environment, preview environment, Redis, workers, cron service, or
other application infrastructure.

## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Keep business and domain rules server-controlled.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Use a modular monolith for V0; do not introduce microservices without an approved need.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Current repository and open decisions

The repository currently contains documentation, repository checks, and the minimal API foundation. Before adding client applications, shared packages, gameplay capabilities, or other runtime areas, an approved spec and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

Accepted backend choices do not settle every V0/V1 detail. Open decisions include the final domain model, API contracts, client architecture, Clerk integration boundary details, deployment configuration, environment variables, and operational policies. These must be resolved by current approved issues/specs before implementation.

## Verification architecture

`scripts/doctor.sh` validates the local Git/GitHub setup, repository location, remote, branch, working-tree state, required backend/devcontainer artifacts, and host Docker/Compose readiness. Inside the TailTag devcontainer it additionally checks the selected Python version, `uv`, locked dependencies, canonical Make commands, and non-mutating PostgreSQL connectivity. For backend-relevant pull-request changes and manual workflow dispatches, the API workflow (`.github/workflows/api.yml`) synchronizes locked Python 3.13 dependencies and invokes the same root `make api-check` validation contract used locally against PostgreSQL 17: Ruff formatting and linting, strict Pyright, pytest, Django checks, migration drift, drf-spectacular configuration validation, and Gunicorn configuration loading. Unrelated pull-request changes retain the same check but report that backend validation was skipped. The same commands are documented in `services/api/README.md`.

The API service uses PostgreSQL for runtime checks and does not provide a SQLite fallback. Keep its CI, Docker, and contributor commands aligned as the foundation evolves; do not infer deployment behavior from this local/CI foundation.

## Decision log

The accepted backend decisions are recorded in:

- [0001 — Use Django and DRF for the backend](adrs/0001-use-django-and-drf-for-backend.md)
- [0002 — Use PostgreSQL as the primary database](adrs/0002-use-postgresql-as-primary-database.md)
- [0003 — Use Clerk for player authentication](adrs/0003-use-clerk-for-player-authentication.md)
- [0004 — Use Railway for V0 hosting](adrs/0004-use-railway-for-v0-hosting.md)
- [0005 — Use a modular monolith for V0](adrs/0005-use-modular-monolith-for-v0.md)

See [the ADR index](adrs/README.md) for the decision threshold and format.
