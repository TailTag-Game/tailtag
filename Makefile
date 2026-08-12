API_DIRECTORY := services/api
UV := uv --directory $(API_DIRECTORY)

.DEFAULT_GOAL := help

.PHONY: help \
	api-setup api-run api-test api-check api-migrate api-migrations \
	api-migrations-check api-shell api-smoke \
	api-format-check api-lint-check api-type-check api-django-check \
	api-schema-check api-gunicorn-check

help: ## List the canonical backend developer commands.
	@printf '%s\n' 'TailTag backend commands:' \
		'  make api-setup            Sync locked backend dependencies.' \
		'  make api-run              Run Django locally on port 8000; requires configured PostgreSQL.' \
		'  make api-test             Run PostgreSQL-backed backend tests.' \
		'  make api-check            Run the complete local pre-PR backend validation suite.' \
		'  make api-migrate          Apply existing Django migrations (mutates schema).' \
		'  make api-migrations       Create Django migrations (mutates migration state).' \
		'  make api-migrations-check Check for migration drift without creating migrations.' \
		'  make api-shell            Open the Django shell; requires configured PostgreSQL.' \
		'  make api-smoke            HTTP-check a running API (API_BASE_URL defaults to 127.0.0.1:8000).'

api-setup: ## Synchronize locked backend dependencies without changing services or schema.
	@printf '%s\n' 'Synchronizing locked backend dependencies...'
	$(UV) sync --all-groups --locked

api-run: ## Run Django locally without starting services or applying migrations.
	@printf '%s\n' 'Starting Django development server on port 8000...'
	$(UV) run python manage.py runserver 0.0.0.0:8000

api-test: ## Run the PostgreSQL-backed backend test suite.
	@printf '%s\n' 'Running backend tests...'
	$(UV) run pytest -q

api-migrate: ## Apply existing Django migrations (mutates schema).
	@printf '%s\n' 'Applying existing Django migrations...'
	$(UV) run python manage.py migrate

api-migrations: ## Create Django migrations (mutates migration state).
	@printf '%s\n' 'Creating Django migrations from model changes...'
	$(UV) run python manage.py makemigrations

api-migrations-check: ## Check migration drift without creating migrations.
	@printf '%s\n' 'Checking for Django migration drift...'
	$(UV) run python manage.py makemigrations --check --dry-run

api-shell: ## Open the Django shell without starting services or applying migrations.
	@printf '%s\n' 'Opening the Django shell...'
	$(UV) run python manage.py shell

api-smoke: ## HTTP-check an already-running API.
	@printf '%s\n' 'Smoke-testing the already-running API...'
	$(UV) run python ../../scripts/api_smoke.py

api-check: api-format-check api-lint-check api-type-check api-test api-django-check api-migrations-check api-schema-check api-gunicorn-check ## Run the complete local pre-PR backend validation suite.
	@printf '%s\n' 'Backend pre-PR validation completed.'

api-format-check:
	@printf '%s\n' 'Checking Ruff formatting...'
	$(UV) run ruff format --check .

api-lint-check:
	@printf '%s\n' 'Running Ruff lint...'
	$(UV) run ruff check .

api-type-check:
	@printf '%s\n' 'Running strict mypy...'
	$(UV) run mypy .

api-django-check:
	@printf '%s\n' 'Running Django system checks...'
	$(UV) run python manage.py check

api-schema-check:
	@printf '%s\n' 'Validating the OpenAPI schema configuration...'
	$(UV) run python manage.py spectacular --validate --file /tmp/openapi.yml

api-gunicorn-check:
	@printf '%s\n' 'Checking the production Gunicorn configuration...'
	DJANGO_SETTINGS_MODULE=config.settings.production \
	DJANGO_SECRET_KEY=not-a-real-secret \
	DATABASE_URL=postgresql://tailtag:tailtag@localhost:5432/tailtag \
	DJANGO_ALLOWED_HOSTS=localhost \
	DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
	$(UV) run gunicorn config.wsgi:application --check-config
