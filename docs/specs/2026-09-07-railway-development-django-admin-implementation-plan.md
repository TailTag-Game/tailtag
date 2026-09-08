# Railway Development Django Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the existing Django admin correctly from Railway Development and
provide a secret-safe, interactive, rerunnable procedure for establishing its
dedicated operator.

**Architecture:** Collect immutable Django admin assets into the production
image and serve them through WhiteNoise under Gunicorn while preserving the
private media backend. Add one Railway Development-only Django management
command that creates a dedicated operator or rotates an existing full
operator's password and refuses every player-elevation path.

**Tech Stack:** Python 3.13, Django 6.0, WhiteNoise 6.x, PostgreSQL, pytest,
Docker, Gunicorn, Railway.

## Global Constraints

- The approved design and frozen contracts are in
  `docs/specs/2026-09-07-railway-development-django-admin.md`.
- The command must require exact Railway metadata
  `RAILWAY_ENVIRONMENT_NAME=development` and `RAILWAY_SERVICE_NAME=api`.
- Operator identifiers and passwords must not be accepted as arguments or
  environment variables and must never appear in output, logs, committed
  evidence, or command history.
- The command may create a new dedicated operator or reconcile an account that
  is already both staff and superuser. It must never elevate an ordinary or
  partially privileged account.
- Production static delivery must not alter `media.storage.S3MediaStorage`, add
  a `/media/` route, enable `DEBUG`, or expose private player media.
- Keep migrations, static collection, and operator provisioning out of
  Gunicorn, application startup, health endpoints, and Railway pre-deploy.
- Do not add an operator HTTP API, automatic bootstrap, Make target, stored
  bootstrap credential, custom admin UI, or unrelated Wave 2/Wave 3 behavior.
- No database migration is expected.
- Do not push, open or change a pull request, deploy, or perform a live Railway
  mutation without the applicable TailTag identity check and authorization.

---

### Task 1: Establish the environment-ready baseline

**Files:**

- Read: `services/api/pyproject.toml`
- Read: `services/api/uv.lock`
- Read: `Makefile`
- Create/modify: none

**Interfaces:**

- Consumes: the clean `fix/issue-170-django-admin` worktree based on
  `origin/main`.
- Produces: fresh evidence that the locked backend toolchain, PostgreSQL test
  service, complete backend gate, and Docker builder are usable before tests or
  implementation change.

- [ ] **Step 1: Verify worktree and Git identity state**

  Run:

  ```bash
  git status --short --branch
  git var GIT_AUTHOR_IDENT
  git var GIT_COMMITTER_IDENT
  ```

  Expected: only the committed design/plan history is present; both identities
  are exactly `Finn the Panther <finn@finnthepanther.com>`.

- [ ] **Step 2: Synchronize the current locked dependencies**

  Run:

  ```bash
  make api-setup
  ```

  Expected: the API and repository-owned Semgrep environments synchronize from
  their lockfiles without changing either lockfile.

- [ ] **Step 3: Run the complete pre-change backend gate**

  Run:

  ```bash
  make api-check
  ```

  Expected: formatting, linting, Pyright, Semgrep, PostgreSQL-backed tests,
  Django checks, migration drift, OpenAPI validation, and Gunicorn configuration
  all pass.

- [ ] **Step 4: Verify Docker is available**

  Run:

  ```bash
  docker version
  docker buildx version
  ```

  Expected: the daemon and builder are reachable. If either is unavailable,
  stop and resolve environment readiness before production-image verification.

### Task 2: Independently author and approve acceptance tests

**Files:**

- Create: `services/api/tests/test_static_delivery.py`
- Create: `services/api/tests/test_bootstrap_development_operator.py`
- Modify: `services/api/tests/test_production_settings.py`
- Modify: `services/api/tests/test_runtime_commands.py`

**Interfaces:**

- Consumes: only the frozen Acceptance Contract, Test Surface Contract, current
  repository behavior, and existing test helpers. The test author does not
  receive proposed production implementation code.
- Produces: failing acceptance tests mapped to contract items 1-8 and 11, plus
  preservation checks for private media and startup boundaries.

- [ ] **Step 1: Dispatch a fresh `test_author` context**

  Give it
  `docs/specs/2026-09-07-railway-development-django-admin.md`, the four approved
  test files, `accounts/models.py`, the settings modules, `config/urls.py`, and
  the production Docker stage. Require an item-by-item mapping from every new
  test to an Acceptance Contract item or the SECURITY, TEST ADEQUACY, or
  RELIABILITY assurance modifier.

- [ ] **Step 2: Require the production-settings contract tests**

  Extend subprocess inspection so tests prove these exact values after a
  successful production import:

  ```python
  assert settings.DEBUG is False
  assert settings.MIDDLEWARE[1] == "whitenoise.middleware.WhiteNoiseMiddleware"
  assert settings.STORAGES["staticfiles"]["BACKEND"] == (
      "whitenoise.storage.CompressedManifestStaticFilesStorage"
  )
  assert settings.STORAGES["default"]["BACKEND"] == "media.storage.S3MediaStorage"
  ```

  The test must use the existing sanitized production environment fixture and
  must not print media configuration values.

- [ ] **Step 3: Require an observable static-response test**

  In `test_static_delivery.py`, use a temporary `STATIC_ROOT`, the approved
  WhiteNoise static backend, and Django's real `collectstatic` command. Construct
  a fresh Django test client only after collection and request:

  ```python
  response = client.get("/static/admin/css/base.css")
  assert response.status_code == 200
  assert response.headers["Content-Type"].startswith("text/css")
  assert b"html" in b"".join(response.streaming_content)
  assert client.get("/media/private-sentinel.jpg").status_code == 404
  ```

  The test must run with `DEBUG=False`, the approved middleware ordering, and
  the real static storage implementation. It must not add URL patterns or mock
  WhiteNoise/static storage.

- [ ] **Step 4: Require production-image source-contract tests**

  Extend `test_runtime_commands.py` to assert the production stage includes this
  build action after the application copy and before Gunicorn:

  ```dockerfile
  RUN python manage.py collectstatic --settings=config.settings.build --noinput
  ```

  Preserve the existing assertions that both stages run as `tailtag`, Gunicorn
  is the production `CMD`, and migrations are absent from Docker/Compose startup.

- [ ] **Step 5: Require the operator-command matrix**

  `test_bootstrap_development_operator.py` must use real PostgreSQL-backed
  `accounts.User` rows and `call_command`. It may patch terminal detection,
  `input`, and the module-local private-input function. Cover:

  - exact Development/api/TTY/confirmation acceptance;
  - new full-operator creation with a usable validated password;
  - existing full-operator password rotation with the same primary key and one
    logical row;
  - refusal and no mutation for ordinary, staff-only, and superuser-only rows;
  - wrong/missing Railway environment and service values;
  - non-TTY stdin and non-TTY stdout;
  - confirmation mismatch, empty identifier, password mismatch, and Django
    password-validation failure;
  - an unrelated account remaining byte-for-byte unchanged; and
  - captured stdout/stderr excluding identifier, password, and password hash in
    success and failure cases.

- [ ] **Step 6: Run the focused tests and confirm expected failures**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_static_delivery.py \
    tests/test_bootstrap_development_operator.py \
    tests/test_production_settings.py \
    tests/test_runtime_commands.py
  ```

  Expected before implementation: failures identify the missing WhiteNoise
  dependency/settings, build collection command, and management command. Existing
  preservation assertions must continue to pass.

- [ ] **Step 7: Parent-review test adequacy and scope**

  Approve only tests mapped to the frozen contract and approved seams. Reject
  tests that expose a new API, mock the user manager/transaction/static backend,
  require external network access, persist sensitive values, or test unrelated
  behavior.

- [ ] **Step 8: Commit the approved failing tests**

  Run the TailTag Git identity check immediately before committing, then:

  ```bash
  git add services/api/tests/test_static_delivery.py \
    services/api/tests/test_bootstrap_development_operator.py \
    services/api/tests/test_production_settings.py \
    services/api/tests/test_runtime_commands.py
  git commit -m "test(api): define Railway admin operations contract"
  ```

### Task 3: Implement production static delivery

**Files:**

- Modify: `services/api/pyproject.toml`
- Modify: `services/api/uv.lock`
- Modify: `services/api/config/settings/base.py`
- Create: `services/api/config/settings/build.py`
- Modify: `services/api/config/settings/production.py`
- Modify: `services/api/Dockerfile`
- Test: `services/api/tests/test_static_delivery.py`
- Test: `services/api/tests/test_production_settings.py`
- Test: `services/api/tests/test_runtime_commands.py`

**Interfaces:**

- Consumes: Django's existing `STATIC_URL`, `STATIC_ROOT`, `STORAGES` aliases,
  production Gunicorn command, and approved failing tests.
- Produces: build settings importable without secrets or network, collected
  admin assets in `/app/staticfiles`, and WhiteNoise-served `/static/` responses.

- [ ] **Step 1: Add and lock WhiteNoise**

  Run:

  ```bash
  uv --directory services/api add "whitenoise>=6.12,<7"
  ```

  Confirm `pyproject.toml` contains the bounded runtime dependency and `uv.lock`
  resolves WhiteNoise without unrelated manual dependency edits.

- [ ] **Step 2: Configure the middleware and production static backend**

  Insert this entry immediately after Django's security middleware in
  `config/settings/base.py`:

  ```python
  "whitenoise.middleware.WhiteNoiseMiddleware",
  ```

  In `config/settings/production.py`, preserve the current S3 `default` alias
  and add:

  ```python
  "staticfiles": {
      "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
  },
  ```

- [ ] **Step 3: Add isolated build settings**

  Create `config/settings/build.py` importing the shared base settings and
  defining only inert build-time values:

  ```python
  from .base import *
  from .base import STORAGES

  DEBUG = False
  SECRET_KEY = "tailtag-static-build-only-not-a-runtime-secret"
  ALLOWED_HOSTS: list[str] = []
  CSRF_TRUSTED_ORIGINS: list[str] = []
  DATABASES = {
      "default": {
          "ENGINE": "django.db.backends.sqlite3",
          "NAME": ":memory:",
      }
  }
  STORAGES = {
      **STORAGES,
      "staticfiles": {
          "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
      },
  }
  ```

  The module must not load `.env`, production media configuration, Clerk
  configuration, Railway variables, or any external service.

- [ ] **Step 4: Collect assets in the production image**

  After `COPY --chown=tailtag:tailtag . ./` in the production stage, add:

  ```dockerfile
  RUN python manage.py collectstatic --settings=config.settings.build --noinput
  ```

  Do not change the development stage or production `CMD`.

- [ ] **Step 5: Run the focused static contract**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_static_delivery.py \
    tests/test_production_settings.py \
    tests/test_runtime_commands.py
  ```

  Expected: all focused static/settings/runtime tests pass.

- [ ] **Step 6: Commit static delivery**

  Run the TailTag Git identity check immediately before committing, then:

  ```bash
  git add services/api/pyproject.toml services/api/uv.lock \
    services/api/config/settings/base.py \
    services/api/config/settings/build.py \
    services/api/config/settings/production.py \
    services/api/Dockerfile
  git commit -m "fix(api): serve collected admin static assets"
  ```

### Task 4: Implement the guarded Development operator command

**Files:**

- Create: `services/api/accounts/management/__init__.py`
- Create: `services/api/accounts/management/commands/__init__.py`
- Create: `services/api/accounts/management/commands/bootstrap_development_operator.py`
- Test: `services/api/tests/test_bootstrap_development_operator.py`

**Interfaces:**

- Consumes: `accounts.User`, `User.objects.create_superuser`, Django password
  validators, Railway system metadata, terminal input, and the approved failing
  tests.
- Produces: `python manage.py bootstrap_development_operator` with no credential
  arguments. The module exposes only `Command`; helper constants/functions stay
  package-internal.

- [ ] **Step 1: Define fail-closed target and input guards**

  In the command module, define these fixed values:

  ```python
  REQUIRED_ENVIRONMENT = "development"
  REQUIRED_SERVICE = "api"
  CONFIRMATION_PHRASE = "bootstrap Railway Development operator"
  ```

  `Command.handle(*args: object, **options: object) -> None` must check exact
  Railway environment/service values, `sys.stdin.isatty()`, and
  `sys.stdout.isatty()` before prompting or querying. It then uses `input()` for
  the fixed confirmation phrase and `getpass.getpass()` for the operator
  identifier and both password entries.

- [ ] **Step 2: Validate all inputs before mutation**

  Reject empty/whitespace-only identifiers and mismatched passwords with generic
  `CommandError` messages. Do not normalize or print the opaque identifier.
  Inside the database transaction, pass the password and the exact candidate or
  locked user to:

  ```python
  django.contrib.auth.password_validation.validate_password(password, user)
  ```

  Convert `ValidationError` to a generic `CommandError` without including the
  validator messages or sensitive inputs.

- [ ] **Step 3: Implement the atomic create-or-reconcile state machine**

  Use `transaction.atomic()` and query the matching row with
  `select_for_update().filter(clerk_user_id=operator_id).first()`.

  - Missing row: validate against an unsaved full-operator `User`, then call
    `User.objects.create_superuser(operator_id, password=password)`.
  - Existing row with both flags true: validate, call `set_password(password)`,
    and save only `password`.
  - Any other existing row: raise a generic `CommandError` before changing flags
    or password.

  Emit exactly one generic success line distinguishing `created` from
  `reconciled`; never interpolate account or password data.

- [ ] **Step 4: Run the focused command contract**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_bootstrap_development_operator.py \
    tests/test_accounts.py
  ```

  Expected: the complete command matrix and existing account invariants pass.

- [ ] **Step 5: Perform plausible-mutant analysis**

  Confirm the tests reject at least these incorrect implementations:

  - accepting `production` or an unset Railway environment;
  - accepting the wrong Railway service;
  - allowing non-interactive invocation;
  - echoing a private input in success or error output;
  - promoting an ordinary or one-flag account;
  - creating a duplicate instead of reconciling;
  - changing the password before validation completes; and
  - changing an unrelated account.

  Classify any surviving mutant as equivalent/irrelevant or add only the missing
  contract-mapped test before proceeding.

- [ ] **Step 6: Commit the management command**

  Run the TailTag Git identity check immediately before committing, then:

  ```bash
  git add services/api/accounts/management
  git commit -m "feat(api): guard Development operator bootstrap"
  ```

### Task 5: Document the maintained Railway procedure

**Files:**

- Modify: `services/api/README.md`
- Modify: `docs/development/backend-delivery-operations.md`
- Modify: `services/api/tests/test_runtime_commands.py`

**Interfaces:**

- Consumes: the final management command name, confirmation phrase, Railway SSH
  target, static build/runtime behavior, and evidence-sanitization contract.
- Produces: one canonical operator runbook and synchronized API reference text;
  no supported Make target or script.

- [ ] **Step 1: Replace the local-only admin guidance with an environment split**

  Preserve the existing local `createsuperuser` instructions. Add a clearly
  separate Railway Development procedure that tells the maintainer to copy the
  exact SSH command from the Railway dashboard or run:

  ```text
  railway ssh --service api --environment development
  python manage.py bootstrap_development_operator --settings=config.settings.production
  ```

  Document creation, safe reconciliation, player-elevation refusal, and the
  generic failure/recovery paths.

- [ ] **Step 2: Document secret and evidence handling**

  State explicitly that the operator identifier and password are entered only
  through hidden interactive prompts; neither belongs in command arguments,
  environment variables, shell history, logs, issues, pull requests, or
  committed evidence. State that no Clerk secret is required.

- [ ] **Step 3: Document static build and troubleshooting behavior**

  Explain that the production image collects admin static assets and WhiteNoise
  serves `/static/` through Gunicorn while private media stays on S3/R2. Add a
  troubleshooting entry distinguishing build-time `collectstatic` failure from
  runtime asset `404` and operator-command target/TTY rejection.

- [ ] **Step 4: Keep documentation assertions synchronized**

  Update the existing runtime documentation assertions so they require the
  canonical command and forbid recommendations to use credentials in arguments,
  `DJANGO_SUPERUSER_PASSWORD`, Railway variables, or automatic startup.

- [ ] **Step 5: Run documentation and focused runtime checks**

  Run:

  ```bash
  ./scripts/doctor.sh
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_runtime_commands.py
  git diff --check
  ```

  Expected: required doctor checks pass, with only an existing optional Dev
  Container CLI warning permitted; runtime documentation tests pass; no
  whitespace errors are reported.

- [ ] **Step 6: Commit the runbook**

  Run the TailTag Git identity check immediately before committing, then:

  ```bash
  git add services/api/README.md \
    docs/development/backend-delivery-operations.md \
    services/api/tests/test_runtime_commands.py
  git commit -m "docs(api): add Railway operator runbook"
  ```

### Task 6: Run deterministic, image, and independent review gates

**Files:**

- Read: all changes relative to `origin/main`
- Create/modify: none unless a required finding maps directly to the frozen
  contract

**Interfaces:**

- Consumes: committed implementation and documentation.
- Produces: deterministic evidence, production-image evidence, one fresh
  STANDARD COMPACT reviewer verdict, and parent authoritative verification.

- [ ] **Step 1: Run the complete deterministic backend gate**

  Run:

  ```bash
  make api-check
  git diff --check origin/main...HEAD
  ```

  Expected: every repository-owned backend gate passes, including Semgrep, and
  the complete branch diff has no whitespace errors.

- [ ] **Step 2: Build the production image**

  Run:

  ```bash
  docker build --target production \
    --tag tailtag-api:issue-170 services/api
  docker run --rm --entrypoint test tailtag-api:issue-170 \
    -f /app/staticfiles/admin/css/base.css
  ```

  Expected: the image builds successfully and contains the collected Django
  admin stylesheet. This local tag is disposable and is not published.

- [ ] **Step 3: Run the focused production-style HTTP test again**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_static_delivery.py \
    tests/test_bootstrap_development_operator.py \
    tests/test_production_settings.py \
    tests/test_runtime_commands.py
  ```

  Expected: all acceptance tests pass with no network access.

- [ ] **Step 4: Dispatch one fresh STANDARD COMPACT reviewer**

  Give the reviewer the frozen design, plan, full `origin/main...HEAD` diff, and
  verification output. Require one combined verdict for specification
  compliance, correctness, security/privacy, transaction safety, test adequacy,
  code quality, dependency/supply-chain impact, and scope discipline.

- [ ] **Step 5: Resolve findings under severity policy**

  Resolve every Acceptance Contract violation and every BLOCKER/HIGH finding.
  The parent decides whether MEDIUM findings are contract-required; LOW/NIT
  findings do not automatically expand scope. Re-run the narrowest affected test
  and then the complete deterministic gate after any change.

- [ ] **Step 6: Parent authoritative verification**

  Account for every Acceptance Contract item, touched file, new test, dependency
  change, review finding, and deferred limitation. Confirm `git status` is clean
  and no debug/scratch/generated static files or sensitive values appear in the
  diff.

### Task 7: Handoff, deploy to Railway Development, and verify live behavior

**Files:**

- Modify after live verification if needed:
  `docs/development/backend-delivery-operations.md`
- Read: Railway deployment metadata and deployed admin responses

**Interfaces:**

- Consumes: reviewed branch, explicit authorization for GitHub writes and
  deployment workflow, merged `main` revision, Railway Development access, and
  interactive operator inputs supplied by the maintainer.
- Produces: pull-request handoff and sanitized live acceptance evidence for
  Issue #170; resumes Issue #120 only after #170 is satisfied.

- [ ] **Step 1: Perform the TailTag PR handoff**

  After verifying the acting GitHub identity is exactly `FinnThePanther`, push
  the focused branch and open/update a pull request that links `Closes #170`,
  lists deterministic/image evidence, identifies WhiteNoise as the new bounded
  dependency, and states that no schema/API/media contract changed.

- [ ] **Step 2: Complete normal review and merge controls**

  Wait for required checks and human authorization before merge. Do not bypass
  branch protection or use an alternate identity. Correlate the merged `main`
  SHA with the Railway Development deployment metadata.

- [ ] **Step 3: Verify live unauthenticated static behavior**

  Fetch Railway Development `/admin/login/`, parse only built-in admin CSS and
  JavaScript references, and verify every referenced `/static/admin/...` URL
  returns `200` with an appropriate CSS or JavaScript content type. Do not record
  cookies, CSRF values, response bodies, or unrelated URLs as evidence.

- [ ] **Step 4: Establish the dedicated Development operator interactively**

  Use Railway SSH and the documented management command. The maintainer supplies
  the hidden identifier/password inputs. Do not automate or capture them. Record
  only the sanitized created/reconciled outcome.

- [ ] **Step 5: Verify operator and ordinary-player boundaries**

  Confirm the operator can sign in and access the existing approved Convention,
  fursuit-enablement, activation/session, and credential inspection controls.
  Confirm an ordinary player cannot access Django admin. Do not create a catch or
  change unrelated Convention/fursuit state during this issue's verification.

- [ ] **Step 6: Verify private-media preservation**

  Confirm the deployed settings/observed fursuit-photo behavior still uses the
  configured private media path. Do not expose or commit a presigned URL, object
  key, credential, or response payload.

- [ ] **Step 7: Record sanitized completion evidence**

  Record the merged revision/deployment identity, static response matrix,
  generic operator outcome, approved admin-access result, ordinary-player
  denial, private-media preservation, and any direct defect/disposition. Never
  record operator identifiers, passwords, cookies, CSRF/session values, Clerk
  IDs, media URLs, request signatures, or private object data.
