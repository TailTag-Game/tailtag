# Architecture

Status: foundational; the Django API proof-of-concept scaffold is approved, but no final application runtime stack has been selected.

## Current repository

The repository contains contributor documentation, GitHub policy files, shell-based repository checks, and an independent Django API proof-of-concept scaffold at `services/api-django-poc/`. The scaffold is a Python 3.13 `uv` project with Django, PostgreSQL 17 configuration, Docker Compose development tooling, health endpoints, quality tooling, and a dedicated GitHub Actions workflow.

The scaffold deliberately does not add domain models, migrations, authentication, CRUD, Django-admin behavior, public OpenAPI schema or documentation routes, Railway configuration, or deployment behavior. It evaluates a backend foundation; it does not select TailTag's final backend architecture. The candidate top-level areas in `README.md` remain directions for discussion rather than approved architecture.

## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Keep domain language in `CONTEXT.md`; keep hard-to-reverse decisions in `docs/adrs/`.
- Avoid final framework, database, hosting, and monorepo commitments until the relevant requirements and alternatives are documented. The approved Django POC is an evaluation boundary, not a production-runtime decision.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Candidate areas, not decisions

The README anticipates player and administrative applications, backend capabilities, shared packages, database changes, infrastructure, and tests. Before creating those areas, an approved spec and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

## Verification architecture

`scripts/doctor.sh` validates the local Git/GitHub setup, repository location, remote, branch, and working-tree state. The Django POC workflow (`.github/workflows/api-django-poc.yml`) runs the locked Python 3.13 environment against PostgreSQL 17 and checks Ruff formatting and linting, strict mypy, pytest, Django checks, migration drift, drf-spectacular configuration validation, and Gunicorn configuration loading. The same commands are documented in `services/api-django-poc/README.md`.

The POC service uses PostgreSQL for runtime checks and does not provide a SQLite fallback. Keep its CI, Docker, and contributor commands aligned as the scaffold evolves; do not infer deployment behavior from this local/CI foundation.

## Decision log

No technical ADRs have been accepted yet. See `docs/adrs/README.md` for the decision threshold and format.
