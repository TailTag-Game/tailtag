# Django API POC scaffold

**Issue:** [#18 — Scaffold the Django API POC](https://github.com/TailTag-Game/tailtag/issues/18)  
**Status:** Approved for implementation

## Goal

Create a reproducible, production-shaped foundation for the Django API proof of concept. Contributors must be able to install, run, test, type-check, lint, inspect health, and build the service with PostgreSQL before account or fursuit behavior exists.

## Scope

The scaffold lives in `services/api-django-poc/` as an independent `uv` project. It uses Python 3.13, the current compatible Django 6.0 release line, Django REST Framework, PostgreSQL 17, Ruff, strict mypy with Django and DRF stubs, pytest, pytest-django, drf-spectacular, Gunicorn, Docker, and GitHub Actions.

The scaffold includes:

- `config` with base, local, and production settings plus WSGI and ASGI entry points;
- a secret-free environment template and explicit configuration validation;
- Docker development and production targets plus Compose services for the API and PostgreSQL;
- PostgreSQL-backed health behavior, with a database-independent liveness endpoint and a database-checked readiness endpoint;
- local commands, CI checks, and service documentation for dependency synchronization, quality gates, tests, migrations, Docker, and production-server configuration;
- an update of the Django POC design document from Draft to Approved.

## Boundaries

Issue #18 does not create Django applications, domain models, migrations, account behavior, authentication, fursuit CRUD, Django-admin behavior, public OpenAPI schema or documentation routes, Railway configuration, or deployment behavior. Those belong to issues #19 and #20.

drf-spectacular is configured and checked as a future API-contract dependency, but no public schema route is published before #19 defines endpoint behavior.

## Runtime and configuration

`pyproject.toml` constrains Python to `>=3.13,<3.14` and Django to the current supported 6.0 series. `uv.lock` records exact dependency versions.

Local settings are the default for `manage.py`. Production settings require `DJANGO_SECRET_KEY`, `DATABASE_URL`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`; missing values stop startup. Real secret values are never committed.

The Docker API image is based on `python:3.13-slim-bookworm`; `uv` is copied from a version-pinned official uv image. Compose uses PostgreSQL 17 and exposes a persistent named volume. Migrations are always an explicit command rather than a web-process startup side effect.

## Health contract

`GET /health/live` returns `200` with `{"status":"ok"}` without accessing PostgreSQL.

`GET /health/ready` returns `200` with `{"status":"ok"}` only when PostgreSQL is reachable. When it is not reachable, it returns `503` with `{"status":"unavailable"}`. Both responses set `Cache-Control: no-store` and never expose exception text, hostnames, connection strings, or credentials.

## Quality and verification

The API CI job installs the locked environment with Python 3.13 and PostgreSQL, then runs Ruff formatting and linting, strict mypy with Django and DRF plugins, PostgreSQL-backed pytest, Django system checks, migration-drift checks, applicable OpenAPI configuration validation, and a production-server configuration smoke check.

The service README is the source of truth for supported commands. The root development guide receives only a short pointer to the service guide if needed.
