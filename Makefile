API_DIRECTORY := services/api
UV := uv --directory $(API_DIRECTORY)
SMOKE_SCRIPT := $(CURDIR)/scripts/api_smoke.py
CI_RELEVANCE_SCRIPT := $(CURDIR)/scripts/backend_ci_relevance.py

define run_django_command
if [ "$${TAILTAG_DEVCONTAINER:-}" = "1" ]; then \
	DATABASE_URL="$$($(UV) run --locked --no-sync python -m config.compose_database_url)" \
	DJANGO_SETTINGS_MODULE=config.settings.production \
	$(UV) run $(1); \
else \
	$(UV) run $(1); \
fi
endef

.DEFAULT_GOAL := help
.NOTPARALLEL: api-check

.PHONY: help \
	api-setup api-run api-test api-check api-migrate api-migrations \
	api-migrations-check api-shell api-smoke \
	api-format-check api-lint-check api-type-check api-django-check \
	api-schema-check api-gunicorn-check

help: ## List the canonical backend developer commands.
	@awk 'BEGIN { print "TailTag backend commands:" } /^[a-zA-Z0-9_-]+:.*##/ { target = $$1; sub(/:.*/, "", target); if (target != "help") { description = $$0; sub(/^.*##[[:space:]]*/, "", description); printf "  make %-20s %s\n", target, description } }' $(MAKEFILE_LIST)

api-setup: ## Sync locked backend dependencies.
	@printf '%s\n' 'Synchronizing locked backend dependencies...'
	$(UV) sync --all-groups --locked

api-run: ## Run Django locally on port 8000; requires configured PostgreSQL.
	@printf '%s\n' 'Starting Django development server on port 8000...'
	@$(call run_django_command,python manage.py runserver 0.0.0.0:8000)

api-test: ## Run PostgreSQL-backed backend tests.
	@printf '%s\n' 'Running backend tests...'
	@$(call run_django_command,pytest -q)

api-migrate: ## Apply existing Django migrations (mutates schema).
	@printf '%s\n' 'Applying existing Django migrations...'
	@$(call run_django_command,python manage.py migrate)

api-migrations: ## Create Django migrations (mutates migration state).
	@printf '%s\n' 'Creating Django migrations from model changes...'
	@$(call run_django_command,python manage.py makemigrations)

api-migrations-check: ## Check for migration drift without creating migrations.
	@printf '%s\n' 'Checking for Django migration drift...'
	@$(call run_django_command,python manage.py makemigrations --check --dry-run)

api-shell: ## Open the Django shell; requires configured PostgreSQL.
	@printf '%s\n' 'Opening the Django shell...'
	@$(call run_django_command,python manage.py shell)

api-smoke: ## HTTP-check a running API (API_BASE_URL defaults to 127.0.0.1:8000).
	@printf '%s\n' 'Smoke-testing the already-running API...'
	$(UV) run python $(SMOKE_SCRIPT)

api-check: api-format-check api-lint-check api-type-check api-test api-django-check api-migrations-check api-schema-check api-gunicorn-check ## Run the complete local pre-PR backend validation suite.
	@printf '%s\n' 'Backend pre-PR validation completed.'

api-format-check:
	@printf '%s\n' 'Checking Ruff formatting...'
	$(UV) run ruff format --check . $(SMOKE_SCRIPT) $(CI_RELEVANCE_SCRIPT)

api-lint-check:
	@printf '%s\n' 'Running Ruff lint...'
	$(UV) run ruff check . $(SMOKE_SCRIPT) $(CI_RELEVANCE_SCRIPT)

api-type-check:
	@printf '%s\n' 'Running strict Pyright...'
	$(UV) run pyright

api-django-check:
	@printf '%s\n' 'Running Django system checks...'
	@$(call run_django_command,python manage.py check)

api-schema-check:
	@printf '%s\n' 'Validating the OpenAPI schema configuration...'
	@$(call run_django_command,python manage.py spectacular --validate --file /dev/null)

api-gunicorn-check:
	@printf '%s\n' 'Checking the production Gunicorn configuration...'
	DJANGO_SETTINGS_MODULE=config.settings.production \
	DJANGO_SECRET_KEY=not-a-real-secret \
	DATABASE_URL=postgresql://tailtag:tailtag@localhost:5432/tailtag \
	DJANGO_ALLOWED_HOSTS=localhost \
	DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
	$(UV) run gunicorn config.wsgi:application --check-config
