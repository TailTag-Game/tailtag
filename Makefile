override REPOSITORY_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
override API_DIRECTORY := services/api
override SEMGREP_DIRECTORY := .semgrep
UV ?= uv
override API_UV := $(UV) --directory $(API_DIRECTORY)
override SEMGREP_UV := $(UV) --directory $(SEMGREP_DIRECTORY)
override SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_smoke.py
override AUTH_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_auth_smoke.py
override REPLACEMENT_AUTH_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_replacement_auth_smoke.py
override STAGING_AUTH_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_auth_smoke.py
override ENVIRONMENT_FINGERPRINT_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_environment_fingerprint.py
override MEDIA_STORAGE_SMOKE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_media_storage_smoke.py
override DEPLOYMENT_IDENTITY_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_deployment_identity.py
override STAGING_PROMOTION_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_promote.py
override STAGING_PREFLIGHT_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_preflight.py
override STAGING_OPERATOR_INSPECTOR_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_inspect.py
override STAGING_OPERATOR_MATRIX_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_matrix.py
override STAGING_OPERATOR_MATRIX_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_matrix_ssh.py
override STAGING_FIXTURE_DIAGNOSE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_fixture_diagnose.py
override STAGING_MANAGED_AUTH_DIAGNOSE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_managed_auth_diagnose.py
override STAGING_MANAGED_AUTH_DIAGNOSE_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_managed_auth_diagnose_ssh.py
override STAGING_MANAGED_OPERATOR_REPLACE_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_managed_operator_replace_ssh.py
override STAGING_MANAGED_PASSWORD_ROTATE_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_managed_password_rotate_ssh.py
override STAGING_OPERATOR_INSPECT_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_inspect_ssh.py
override STAGING_OPERATOR_LIFECYCLE_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_lifecycle_ssh.py
override STAGING_OPERATOR_RESTART_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_operator_restart_ssh.py
override STAGING_REGISTRY_RECONCILE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_registry_reconcile.py
override STAGING_REGISTRY_RECONCILE_REMOTE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_registry_reconcile_remote.py
override STAGING_EMERGENCY_OPERATOR_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_emergency_operator_ssh.py
override STAGING_EMERGENCY_DECOMMISSION_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_emergency_operator_decommission_ssh.py
override DEVELOPMENT_DELIVERY_EVENT_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_development_delivery_event.py
override SIM_POOL_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_sim_pool_ssh.py
override SIM_FIXTURE_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_sim_fixture_ssh.py
override SIM_INSPECT_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_sim_inspect_ssh.py
override STAGING_RESET_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_reset.py
override STAGING_RESET_SSH_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_reset_ssh.py
override STAGING_RESTORE_SCRIPT := $(REPOSITORY_ROOT)/scripts/api_staging_restore_drill.py
override STAGING_RESTORE_INTEGRITY_SCRIPT := $(REPOSITORY_ROOT)/scripts/staging_restore_integrity.py
override CLERK_DEVELOPMENT_SESSION_SCRIPT := $(REPOSITORY_ROOT)/scripts/clerk_development_session.py
override CI_RELEVANCE_SCRIPT := $(REPOSITORY_ROOT)/scripts/backend_ci_relevance.py
override SEMGREP_VALIDATOR := $(REPOSITORY_ROOT)/scripts/validate_semgrep_contract.py
override SEMGREP_RULES := $(REPOSITORY_ROOT)/.semgrep/rules
override SEMGREP_TESTS := $(REPOSITORY_ROOT)/.semgrep/tests
override SEMGREP_TARGETS := $(REPOSITORY_ROOT)/services/api \
	$(SMOKE_SCRIPT) \
	$(AUTH_SMOKE_SCRIPT) \
	$(REPLACEMENT_AUTH_SMOKE_SCRIPT) \
	$(STAGING_AUTH_SMOKE_SCRIPT) \
	$(ENVIRONMENT_FINGERPRINT_SCRIPT) \
	$(MEDIA_STORAGE_SMOKE_SCRIPT) \
	$(DEPLOYMENT_IDENTITY_SCRIPT) \
	$(STAGING_PROMOTION_SCRIPT) \
	$(STAGING_PREFLIGHT_SCRIPT) \
	$(STAGING_OPERATOR_INSPECTOR_SCRIPT) \
	$(STAGING_OPERATOR_MATRIX_SCRIPT) \
	$(STAGING_OPERATOR_MATRIX_SSH_SCRIPT) \
	$(STAGING_FIXTURE_DIAGNOSE_SCRIPT) \
	$(STAGING_MANAGED_AUTH_DIAGNOSE_SCRIPT) \
	$(STAGING_MANAGED_AUTH_DIAGNOSE_SSH_SCRIPT) \
	$(STAGING_MANAGED_OPERATOR_REPLACE_SSH_SCRIPT) \
	$(STAGING_MANAGED_PASSWORD_ROTATE_SSH_SCRIPT) \
	$(STAGING_OPERATOR_INSPECT_SSH_SCRIPT) \
	$(STAGING_OPERATOR_LIFECYCLE_SSH_SCRIPT) \
	$(STAGING_OPERATOR_RESTART_SSH_SCRIPT) \
	$(STAGING_REGISTRY_RECONCILE_SCRIPT) \
	$(STAGING_REGISTRY_RECONCILE_REMOTE_SCRIPT) \
	$(STAGING_EMERGENCY_OPERATOR_SSH_SCRIPT) \
	$(STAGING_EMERGENCY_DECOMMISSION_SSH_SCRIPT) \
	$(DEVELOPMENT_DELIVERY_EVENT_SCRIPT) \
	$(SIM_POOL_SSH_SCRIPT) \
	$(SIM_FIXTURE_SSH_SCRIPT) \
	$(SIM_INSPECT_SSH_SCRIPT) \
	$(STAGING_RESET_SCRIPT) \
	$(STAGING_RESET_SSH_SCRIPT) \
	$(STAGING_RESTORE_SCRIPT) \
	$(STAGING_RESTORE_INTEGRITY_SCRIPT) \
	$(CLERK_DEVELOPMENT_SESSION_SCRIPT) \
	$(CI_RELEVANCE_SCRIPT) \
	$(SEMGREP_VALIDATOR)
override SEMGREP := $(SEMGREP_UV) run --locked --no-sync semgrep
override SIMULATOR_DIRECTORY := tools/simulator
override SIM_UV := $(UV) --directory $(SIMULATOR_DIRECTORY)
override SIM_SEMGREP_RULES := $(REPOSITORY_ROOT)/.semgrep/simulator-rules
override SIM_SEMGREP_TESTS := $(REPOSITORY_ROOT)/.semgrep/simulator-tests
# Explicit files, not a directory, so untracked new modules are still scanned.
override SIM_SEMGREP_TARGETS := $(sort $(wildcard $(REPOSITORY_ROOT)/$(SIMULATOR_DIRECTORY)/tailtag_simulator/*.py))
override SIM_IMAGE := tailtag-simulator:local

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
.NOTPARALLEL: api-check sim-check

.PHONY: help \
	api-setup api-run api-semgrep-check api-test api-check api-migrate api-migrations \
	api-migrations-check api-shell api-smoke api-auth-smoke api-staging-auth-smoke api-replacement-auth-smoke api-media-storage-smoke api-staging-reset api-staging-reset-ssh api-staging-reset-provision api-staging-reset-provision-ssh \
	api-staging-restore-drill \
	api-format-check api-lint-check api-type-check api-django-check \
	api-schema-check api-gunicorn-check \
	sim-setup sim-check sim-smoke sim-pool-provision sim-pool-status sim-pool-readmit sim-pool-smoke sim-fixture-smoke sim-journeys sim-convention sim-cleanup sim-retained sim-image sim-catalog-check sim-report-validate sim-format-check sim-lint-check sim-type-check sim-test sim-semgrep-check

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

api-staging-auth-smoke: ## Run the explicit live Clerk Staging authenticated API smoke.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_auth_smoke

api-replacement-auth-smoke: ## Run the interactive replacement Development/Staging authenticated API smoke.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_replacement_auth_smoke

api-staging-reset: ## Run the explicitly confirmed guarded Staging rehearsal reset.
	DJANGO_SETTINGS_MODULE=config.settings.production PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_reset --confirm reset-tailtag-staging

api-staging-reset-ssh: ## Run the confirmed guarded Staging reset through its pinned Railway SSH instance.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_reset_ssh --confirm reset-tailtag-staging

api-staging-reset-provision: ## Provision the Staging reset sentinel after explicit confirmation.
	DJANGO_SETTINGS_MODULE=config.settings.production PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_reset --provision --confirm provision-tailtag-staging-reset

api-staging-reset-provision-ssh: ## Provision the replacement Staging reset sentinel on the pinned Railway instance.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_reset_ssh --provision --confirm provision-tailtag-staging-reset

api-sim-pool-ssh: ## Run one synthetic identity pool request (JSON on stdin) through the pinned Staging instance.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_sim_pool_ssh

api-sim-fixture-ssh: ## Run one simulation fixture request (JSON on stdin) through the pinned Staging instance.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_sim_fixture_ssh

api-sim-inspect-ssh: ## Run one read-only simulation inspection request (JSON on stdin) through the pinned Staging instance.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_sim_inspect_ssh

api-staging-restore-drill: ## Run the confirmed isolated Staging PostgreSQL backup restore drill.
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" $(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_staging_restore_drill --confirm restore-tailtag-staging-backup

api-media-storage-smoke: ## Run guarded live media storage verification against Railway Development or Staging.
	@DJANGO_SETTINGS_MODULE=config.settings.production \
	PYTHONPATH="$(REPOSITORY_ROOT):$(REPOSITORY_ROOT)/$(API_DIRECTORY)" \
	$(UV) run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_media_storage_smoke

api-check: api-format-check api-lint-check api-type-check api-semgrep-check api-test api-django-check api-migrations-check api-schema-check api-gunicorn-check ## Run the complete local pre-PR backend validation suite.
	@printf '%s\n' 'Backend pre-PR validation completed.'

api-format-check:
	@printf '%s\n' 'Checking Ruff formatting...'
	$(API_UV) run --locked --no-sync ruff format --check . $(SMOKE_SCRIPT) $(AUTH_SMOKE_SCRIPT) $(REPLACEMENT_AUTH_SMOKE_SCRIPT) $(STAGING_AUTH_SMOKE_SCRIPT) $(ENVIRONMENT_FINGERPRINT_SCRIPT) $(MEDIA_STORAGE_SMOKE_SCRIPT) $(DEPLOYMENT_IDENTITY_SCRIPT) $(STAGING_PROMOTION_SCRIPT) $(STAGING_PREFLIGHT_SCRIPT) $(STAGING_OPERATOR_INSPECTOR_SCRIPT) $(STAGING_OPERATOR_MATRIX_SCRIPT) $(STAGING_OPERATOR_MATRIX_SSH_SCRIPT) $(STAGING_FIXTURE_DIAGNOSE_SCRIPT) $(STAGING_MANAGED_AUTH_DIAGNOSE_SCRIPT) $(STAGING_MANAGED_AUTH_DIAGNOSE_SSH_SCRIPT) $(STAGING_MANAGED_OPERATOR_REPLACE_SSH_SCRIPT) $(STAGING_MANAGED_PASSWORD_ROTATE_SSH_SCRIPT) $(STAGING_OPERATOR_INSPECT_SSH_SCRIPT) $(STAGING_OPERATOR_LIFECYCLE_SSH_SCRIPT) $(STAGING_OPERATOR_RESTART_SSH_SCRIPT) $(STAGING_REGISTRY_RECONCILE_SCRIPT) $(STAGING_REGISTRY_RECONCILE_REMOTE_SCRIPT) $(STAGING_EMERGENCY_OPERATOR_SSH_SCRIPT) $(STAGING_EMERGENCY_DECOMMISSION_SSH_SCRIPT) $(DEVELOPMENT_DELIVERY_EVENT_SCRIPT) $(SIM_POOL_SSH_SCRIPT) $(SIM_FIXTURE_SSH_SCRIPT) $(SIM_INSPECT_SSH_SCRIPT) $(STAGING_RESET_SCRIPT) $(STAGING_RESET_SSH_SCRIPT) $(STAGING_RESTORE_SCRIPT) $(STAGING_RESTORE_INTEGRITY_SCRIPT) $(CLERK_DEVELOPMENT_SESSION_SCRIPT) $(CI_RELEVANCE_SCRIPT) $(SEMGREP_VALIDATOR)

api-lint-check:
	@printf '%s\n' 'Running Ruff lint...'
	$(API_UV) run --locked --no-sync ruff check . $(SMOKE_SCRIPT) $(AUTH_SMOKE_SCRIPT) $(REPLACEMENT_AUTH_SMOKE_SCRIPT) $(STAGING_AUTH_SMOKE_SCRIPT) $(ENVIRONMENT_FINGERPRINT_SCRIPT) $(MEDIA_STORAGE_SMOKE_SCRIPT) $(DEPLOYMENT_IDENTITY_SCRIPT) $(STAGING_PROMOTION_SCRIPT) $(STAGING_PREFLIGHT_SCRIPT) $(STAGING_OPERATOR_INSPECTOR_SCRIPT) $(STAGING_OPERATOR_MATRIX_SCRIPT) $(STAGING_OPERATOR_MATRIX_SSH_SCRIPT) $(STAGING_FIXTURE_DIAGNOSE_SCRIPT) $(STAGING_MANAGED_AUTH_DIAGNOSE_SCRIPT) $(STAGING_MANAGED_AUTH_DIAGNOSE_SSH_SCRIPT) $(STAGING_MANAGED_OPERATOR_REPLACE_SSH_SCRIPT) $(STAGING_MANAGED_PASSWORD_ROTATE_SSH_SCRIPT) $(STAGING_OPERATOR_INSPECT_SSH_SCRIPT) $(STAGING_OPERATOR_LIFECYCLE_SSH_SCRIPT) $(STAGING_OPERATOR_RESTART_SSH_SCRIPT) $(STAGING_REGISTRY_RECONCILE_SCRIPT) $(STAGING_REGISTRY_RECONCILE_REMOTE_SCRIPT) $(STAGING_EMERGENCY_OPERATOR_SSH_SCRIPT) $(STAGING_EMERGENCY_DECOMMISSION_SSH_SCRIPT) $(DEVELOPMENT_DELIVERY_EVENT_SCRIPT) $(SIM_POOL_SSH_SCRIPT) $(SIM_FIXTURE_SSH_SCRIPT) $(SIM_INSPECT_SSH_SCRIPT) $(STAGING_RESET_SCRIPT) $(STAGING_RESET_SSH_SCRIPT) $(STAGING_RESTORE_SCRIPT) $(STAGING_RESTORE_INTEGRITY_SCRIPT) $(CLERK_DEVELOPMENT_SESSION_SCRIPT) $(CI_RELEVANCE_SCRIPT) $(SEMGREP_VALIDATOR)

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

sim-setup: ## Sync locked simulator dependencies.
	@printf '%s\n' 'Synchronizing locked simulator dependencies...'
	$(SIM_UV) sync --all-groups --locked
	$(SEMGREP_UV) sync --locked

sim-check: sim-catalog-check sim-format-check sim-lint-check sim-type-check sim-test sim-semgrep-check ## Run the complete local simulator validation suite.
	@printf '%s\n' 'Simulator validation completed.'

sim-smoke: ## Run the manual authenticated smoke: TARGET=local|staging [BASE_URL=...].
	@test -n "$(TARGET)" || { printf '%s\n' 'TARGET is required: local or staging.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator smoke --target '$(TARGET)' $(if $(BASE_URL),--base-url '$(BASE_URL)') $(if $(VERSION),--scenario-version '$(VERSION)') $(if $(SEED),--seed '$(SEED)') $(if $(REPORT_DIR),--report-dir '$(REPORT_DIR)')

sim-pool-provision: ## Provision or expand the Staging identity pool: POOL=name SIZE=n (host only).
	@test -n "$(POOL)" -a -n "$(SIZE)" || { printf '%s\n' 'POOL and SIZE are required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator pool provision --pool '$(POOL)' --size '$(SIZE)'

sim-pool-status: ## Show Staging identity pool counts: POOL=name (host only).
	@test -n "$(POOL)" || { printf '%s\n' 'POOL is required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator pool status --pool '$(POOL)'

sim-pool-readmit: ## Re-admit a repaired quarantined identity: POOL=name INDEX=n (host only).
	@test -n "$(POOL)" -a -n "$(INDEX)" || { printf '%s\n' 'POOL and INDEX are required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator pool readmit --pool '$(POOL)' --index '$(INDEX)'

sim-pool-smoke: ## Run the Staging identity pool smoke: POOL=name COUNT=n (host only).
	@test -n "$(POOL)" -a -n "$(COUNT)" || { printf '%s\n' 'POOL and COUNT are required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator pool-smoke --pool '$(POOL)' --count '$(COUNT)' $(if $(VERSION),--scenario-version '$(VERSION)') $(if $(SEED),--seed '$(SEED)') $(if $(REPORT_DIR),--report-dir '$(REPORT_DIR)')

sim-fixture-smoke: ## Run the Staging fixture smoke: POOL=name [OWNERS=n FURSUITS=k CATCHERS=m] (host only).
	@test -n "$(POOL)" || { printf '%s\n' 'POOL is required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator fixture-smoke --pool '$(POOL)' $(if $(OWNERS),--owners '$(OWNERS)') $(if $(FURSUITS),--fursuits '$(FURSUITS)') $(if $(CATCHERS),--catchers '$(CATCHERS)') $(if $(VERSION),--scenario-version '$(VERSION)') $(if $(SEED),--seed '$(SEED)') $(if $(REPORT_DIR),--report-dir '$(REPORT_DIR)')

sim-journeys: ## Run the Staging acceptance journeys: POOL=name (host only; leases 7 identities).
	@test -n "$(POOL)" || { printf '%s\n' 'POOL is required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator journeys --pool '$(POOL)' $(if $(VERSION),--scenario-version '$(VERSION)') $(if $(SEED),--seed '$(SEED)') $(if $(REPORT_DIR),--report-dir '$(REPORT_DIR)')

sim-convention: ## Run convention workloads: POOL=name FAMILY=baseline [CONFIG=path VERSION=1|2 SEED=0 REPORT_DIR=path].
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator convention --pool '$(subst ','"'"',$(POOL))' --family '$(subst ','"'"',$(FAMILY))' $(if $(CONFIG),--config '$(subst ','"'"',$(CONFIG))') $(if $(VERSION),--scenario-version '$(subst ','"'"',$(VERSION))') $(if $(SEED),--seed '$(subst ','"'"',$(SEED))') $(if $(REPORT_DIR),--report-dir '$(subst ','"'"',$(REPORT_DIR))')

sim-cleanup: ## Clean one Staging simulation run and readmit its identities: POOL=name RUN_ID=id (host only).
	@test -n "$(POOL)" -a -n "$(RUN_ID)" || { printf '%s\n' 'POOL and RUN_ID are required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator cleanup --pool '$(POOL)' --run-id '$(RUN_ID)'

sim-retained: ## List retained and unfinished Staging simulation runs (host only).
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator retained

sim-image: ## Build the simulator container image from verified clean source.
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator.provenance build --root '$(CURDIR)' --tag '$(SIM_IMAGE)'

sim-catalog-check: ## Validate scenario descriptors and their Git history.
	$(SIM_UV) run --locked --no-sync python -c 'import sys; from pathlib import Path; from tailtag_simulator.scenarios import validate_catalog; validate_catalog(Path(sys.argv[1]))' '$(subst ','"'"',$(CURDIR))'

sim-report-validate: ## Validate an existing report offline: REPORT=path.
	@test -n "$(REPORT)" || { printf '%s\n' 'REPORT is required.' >&2; exit 2; }
	$(SIM_UV) run --locked --no-sync python -m tailtag_simulator report validate '$(REPORT)'

sim-format-check:
	@printf '%s\n' 'Checking simulator Ruff formatting...'
	$(SIM_UV) run --locked --no-sync ruff format --no-cache --check .

sim-lint-check:
	@printf '%s\n' 'Running simulator Ruff lint...'
	$(SIM_UV) run --locked --no-sync ruff check --no-cache .

sim-type-check:
	@printf '%s\n' 'Running simulator strict Pyright...'
	$(SIM_UV) run --locked --no-sync pyright

sim-test:
	@printf '%s\n' 'Running simulator tests...'
	$(SIM_UV) run --locked --no-sync pytest -q -p no:cacheprovider

sim-semgrep-check:
	@printf '%s\n' 'Testing simulator Semgrep rules...'
	$(SIM_UV) run --locked --no-sync python $(SEMGREP_VALIDATOR) --rules $(SIM_SEMGREP_RULES) --fixtures $(SIM_SEMGREP_TESTS)
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_BASELINE_COMMIT= SEMGREP_APP_TOKEN= SEMGREP_RULES= \
		$(SEMGREP) scan --test \
		--config $(SIM_SEMGREP_RULES) \
		--baseline-commit '' \
		--metrics=off \
		--disable-version-check \
		$(SIM_SEMGREP_TESTS)
	@printf '%s\n' 'Running simulator Semgrep boundary analysis...'
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_BASELINE_COMMIT= SEMGREP_APP_TOKEN= SEMGREP_RULES= \
		$(SEMGREP) scan \
		--config $(SEMGREP_RULES) \
		--config $(SIM_SEMGREP_RULES) \
		--baseline-commit '' \
		--error \
		--metrics=off \
		--disable-version-check \
		$(SIM_SEMGREP_TARGETS)
