# Architecture

Status: accepted V0 direction; backend Phase 0 is about to begin.

## Current direction

TailTag is a monorepo for the community-led rebuild of a social convention game. The V0 backend direction is:

- Python
- Django and Django REST Framework
- PostgreSQL as the primary application database
- Clerk as the player authentication authority
- A TailTag-owned internal application user identity for domain relationships, separate from Clerk
- A modular monolith backend
- Railway for V0 backend hosting

The completed Django POC at `services/api-django-poc/` is historical evaluation evidence. It is not the V0 product or API specification; its POC-only authentication, session/CSRF behavior, fursuit fields, routes, deletion behavior, and other experimental choices must be reset or reconsidered during promotion.

## Backend phases

Phase 0 will promote and reset the POC into a clean `services/api` foundation and establish the local contributor environment. Phase 1 will establish CI/CD and the shared Railway development environment. Those implementation phases have not begun, so this document does not describe final developer commands, environment variables, deployment configuration, or application behavior.

## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Keep business and domain rules server-controlled.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Use a modular monolith for V0; do not introduce microservices without an approved need.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Current repository and open decisions

The repository currently contains documentation, repository checks, and the historical POC. Before adding client applications, shared packages, gameplay capabilities, or other runtime areas, an approved spec and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

Accepted backend choices do not settle every V0/V1 detail. Open decisions include the final domain model, API contracts, client architecture, Clerk integration boundary details, deployment configuration, environment variables, and operational policies. These must be resolved by current approved issues/specs before implementation.

## Verification architecture

`scripts/doctor.sh` validates the local Git/GitHub setup, repository location, remote, branch, and working-tree state. The Django POC workflow (`.github/workflows/api-django-poc.yml`) runs the locked Python 3.13 environment against PostgreSQL 17 and checks Ruff formatting and linting, strict mypy, pytest, Django checks, migration drift, drf-spectacular configuration validation, and Gunicorn configuration loading. The same commands are documented in `services/api-django-poc/README.md`.

The POC service uses PostgreSQL for runtime checks and does not provide a SQLite fallback. Keep its CI, Docker, and contributor commands aligned as the scaffold evolves; do not infer deployment behavior from this local/CI foundation.

## Decision log

The accepted backend decisions are recorded in:

- [0001 — Use Django and DRF for the backend](adrs/0001-use-django-and-drf-for-backend.md)
- [0002 — Use PostgreSQL as the primary database](adrs/0002-use-postgresql-as-primary-database.md)
- [0003 — Use Clerk for player authentication](adrs/0003-use-clerk-for-player-authentication.md)
- [0004 — Use Railway for V0 hosting](adrs/0004-use-railway-for-v0-hosting.md)
- [0005 — Use a modular monolith for V0](adrs/0005-use-modular-monolith-for-v0.md)

See [the ADR index](adrs/README.md) for the decision threshold and format.
