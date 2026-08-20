override REPOSITORY_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
override API_DIRECTORY := services/api
override SEMGREP_DIRECTORY := .semgrep
UV ?= uv
override API_UV := $(UV) --directory $(API_DIRECTORY)
override SEMGREP_UV := $(UV) --directory $(SEMGREP_DIRECTORY)
override SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_smoke.py
override AUTH_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_auth_smoke.py
override MEDIA_STORAGE_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_media_storage_smoke.py
override CLERK_DEVELOPMENT_SESSION_SCRIPT := $(REPOSITORY_ROOT)/scripts/clerk_development_session.py
override CI_RELEVANCE_SCRIPT := $(REPOSITORY_ROOT)/scripts/backend_ci_relevance.py
override SEMGREP_VALIDATOR := $(REPOSITORY_ROOT)/scripts/validate_semgrep_contract.py
override SEMGREP_RULES := $(REPOSITORY_ROOT)/.semgrep/rules
override SEMGREP_TESTS := $(REPOSITORY_ROOT)/.semgrep/tests
override SEMGREP_TARGETS := $(REPOSITORY_ROOT)/services/api \
	$(SMOKE_SCRIPT) \
	$(AUTH_SMOKE_SCRIPT) \
	$(MEDIA_STORAGE_SMOKE_SCRIPT) \
	$(CLERK_DEVELOPMENT_SESSION_SCRIPT) \
	$(CI_RELEVANCE_SCRIPT) \
	$(SEMGREP_VALIDATOR)
override SEMGREP := $(SEMGREP_UV) run --locked --no-sync semgrep

define run_django_command
if [ "$${TAILTAG_DEVCONTAINER:-}" = "1" ]; then \
	DATABASE_URL="$$($(API_UV) run --locked --no-sync python -m config.compose_database_url)" \
	DJANGO_SETTINGS_MODULE=config.settings.local \
	$(API_UV) run --locked --no-sync $(1); \
else \
	$(API_UV) run --locked --no-sync $(1); \
fi
endef

.DEFAULT_GOAL := help
.NOTPARALLEL: api-check

.PHONY: help \
	api-setup api-run api-semgrep-check api-test api-check api-migrate api-migrations \
	api-migrations-check api-shell api-smoke api-auth-smoke api-media-storage-smoke \
	api-format-check api-lint-check api-type-check api-django-check \
	api-schema-check api-gunicorn-check

help: ## List the canonical backend developer commands.
	@awk 'BEGIN { print "TailTag backend commands:" } /^[a-zA-Z0-9_-]+:.*##/ { target = $$1; sub(/:.*/, "", target); if (target != "help") { description = $$0; sub(/^.*##[[:space:]]*/, "", description); printf "  make %-20s %s\n", target, description } }' $(MAKEFILE_LIST)

api-setup: ## Sync locked backend dependencies.
	@printf '%s\n' 'Synchronizing locked backend dependencies...'
	$(API_UV) sync --all-groups --locked
	$(SEMGREP_UV) sync --locked

api-run: ## Run Django locally on port 8000; requires configured PostgreSQL.
	@printf '%s\n' 'Starting Django development server on port 8000...'
	@$(call run_django_command,python manage.py runserver 0.0.0.0:8000)

api-semgrep-check: ## Run deterministic TailTag Semgrep security analysis.
	@printf '%s\n' 'Testing TailTag Semgrep rules...'
	$(API_UV) run --locked --no-sync python $(SEMGREP_VALIDATOR) --rules $(SEMGREP_RULES) --fixtures $(SEMGREP_TESTS)
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_BASELINE_COMMIT= SEMGREP_APP_TOKEN= SEMGREP_RULES= \
		$(SEMGREP) scan --test \
		--config $(SEMGREP_RULES) \
		--baseline-commit '' \
		--metrics=off \
		--disable-version-check \
		$(SEMGREP_TESTS)
	@printf '%s\n' 'Running TailTag Semgrep security analysis...'
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_BASELINE_COMMIT= SEMGREP_APP_TOKEN= SEMGREP_RULES= \
		$(SEMGREP) scan \
		--config $(SEMGREP_RULES) \
		--baseline-commit '' \
		--error \
		--metrics=off \
		--disable-version-check \
		$(SEMGREP_TARGETS)

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
	$(API_UV) run python $(SMOKE_SCRIPT)

api-auth-smoke: ## Authenticated smoke test with an interactive Clerk Development secret.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_auth_smoke

api-media-storage-smoke: ## Run guarded live media storage verification against Railway Development.
	DJANGO_SETTINGS_MODULE=config.settings.production \
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" \
	$(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_media_storage_smoke

api-check: api-format-check api-lint-check api-type-check api-semgrep-check api-test api-django-check api-migrations-check api-schema-check api-gunicorn-check ## Run the complete local pre-PR backend validation suite.
	@printf '%s\n' 'Backend pre-PR validation completed.'

api-format-check:
	@printf '%s\n' 'Checking Ruff formatting...'
	$(API_UV) run --locked --no-sync ruff format --check . $(SMOKE_SCRIPT) $(AUTH_SMOKE_SCRIPT) $(MEDIA_STORAGE_SMOKE_SCRIPT) $(CLERK_DEVELOPMENT_SESSION_SCRIPT) $(CI_RELEVANCE_SCRIPT) $(SEMGREP_VALIDATOR)

api-lint-check:
	@printf '%s\n' 'Running Ruff lint...'
	$(API_UV) run --locked --no-sync ruff check . $(SMOKE_SCRIPT) $(AUTH_SMOKE_SCRIPT) $(MEDIA_STORAGE_SMOKE_SCRIPT) $(CLERK_DEVELOPMENT_SESSION_SCRIPT) $(CI_RELEVANCE_SCRIPT) $(SEMGREP_VALIDATOR)

api-type-check:
	@printf '%s\n' 'Running strict Pyright...'
	$(API_UV) run --locked --no-sync pyright

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
	MEDIA_STORAGE_ENDPOINT_URL=https://media.example.test \
	MEDIA_STORAGE_BUCKET_NAME=ci-media-bucket \
	MEDIA_STORAGE_REGION=auto \
	MEDIA_STORAGE_ACCESS_KEY_ID=ci-not-a-real-access-key \
	MEDIA_STORAGE_SECRET_ACCESS_KEY=ci-not-a-real-secret-key \
	$(API_UV) run --locked --no-sync gunicorn config.wsgi:application --check-config
