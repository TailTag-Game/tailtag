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

Phase 0 established the clean `services/api` foundation and local contributor environment. Phase 1 now has authoritative backend CI and pre-merge GitHub validation through `make api-check`, its persistent Railway development environment, an explicit Railway pre-deploy migration step, post-deploy HTTP smoke verification, and an enforced normal-contributor delivery path from protected `main` to Railway development. This document does not define production deployment configuration or product application behavior.

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

The API service has normal GitHub autodeploy enabled for the
`TailTag-Game/tailtag` `main` branch. Its Railway trigger is configured with
Wait for CI (`checkSuites: true`), which Railway documents as holding a
candidate while the pushed-`main` GitHub workflows run, then skipping it on
failure. This is defense in depth after, not a replacement for, GitHub's
pre-merge protections. Configuration alone is not proof of that temporal
gate: a fresh normal reviewed merge must show Railway `WAITING` before the
push validation completes; see the main-to-Railway delivery review for the
observed verification boundary.

Railway evaluates API deployment relevance independently from the broader CI
relevance contract. Its only API watch path is `services/api/**`. Therefore,
changes only to the root `Makefile`, `scripts/api_smoke.py`,
`.github/workflows/api.yml`, documentation, or a future frontend do not
create an unnecessary API deployment unless a later approved runtime build
change makes one of those paths directly relevant.

For a Git-triggered `main` commit outside that watch path, the expected
no-delivery result is an exact-SHA metadata-only Railway evaluation record with
status `SKIPPED` and reason `No changes to watched files`. If that record is
absent after the defined observation window, the exercise is inconclusive.
Railway must not run an API build, pre-deploy migration, readiness check, or
application deployment, and it must not create the GitHub deployment that
would trigger the post-deploy smoke workflow.

For normal contributor delivery, the active `Protect main` GitHub ruleset
requires a pull request, one approval, resolved review conversations, squash
merge, and the stable `API foundation checks` status check. That check exists
on every pull request: relevant pull requests run the canonical
`make api-check`, while irrelevant ones complete through the explicit
successful skip path. The same workflow also runs for every push to `main`,
using the same job and canonical command, so Railway Wait for CI validates the
resulting `main` commit before deploying it.

The repository owner retains a pull-request-only ruleset bypass as an
exceptional, auditable administrative or recovery override. It is outside the
normal contributor delivery path and must not be used for routine development,
or delivery. Owner-operated #78/#80 validation changes may use the bypass when
the override is intentional and recorded, but those merges validate delivery
mechanics rather than the human-review path. The active ruleset remains the
evidence that normal contributors require review. This design does not claim
that a deliberately privileged administrator can never override GitHub
protections; it ensures that a normal contributor cannot cause Railway
development delivery while bypassing required pull-request CI and review.

The dedicated GitHub Actions post-deploy smoke workflow reacts only when the
observed Railway GitHub integration reports a `success` deployment status for
`TailTag / development` created by `railway-app[bot]`. It also supports a manual
rerun. Both paths use the non-secret repository Actions variable
`TAILTAG_DEVELOPMENT_API_BASE_URL` and invoke `make api-smoke` against the
already-running public API; they neither deploy, migrate, provision PostgreSQL,
nor control Railway. A smoke failure is a clear failed Actions run with
endpoint-level diagnostics, not an automatic rollback or redeploy.

Railway deployment metadata records the Git-triggered commit SHA, and the
GitHub `deployment_status` event supplies its deployment SHA/ref to the #77
verifier. Together with the matching `main` push workflow SHA, this provides
Stage 1 infrastructure-level revision attribution. The HTTP check separately
proves the shared development endpoint satisfied the smoke contract after the
successful deployment event; a stable-endpoint response is not cryptographically
bound to that SHA. If another deployment supersedes it before smoke runs, record
that race as evidence rather than adding an application version endpoint.
Railway's `/health/ready` platform health check remains distinct from this
broader external smoke verification. This environment contains no production
environment, preview environment, Redis, workers, cron service, or other
application infrastructure.

Delivery failures have distinct primary surfaces:

| Failure | Control and primary diagnostic surface |
| --- | --- |
| Pre-merge backend CI | GitHub `API foundation checks`; the PR cannot normally merge. |
| Missing approval or unresolved review | GitHub ruleset and PR merge requirements; the PR cannot normally merge. |
| Post-merge CI | GitHub Actions plus Railway's waiting/skipped candidate state; no candidate is promoted after a failed workflow. |
| Migration | Railway pre-deploy logs/status; the candidate fails before application promotion. |
| Build, deploy, or readiness | Railway deployment state and logs. |
| Post-deploy smoke | The #77 GitHub Actions verifier; Railway deployment succeeded but broader HTTP verification failed. |

#78 adds no automatic rollback behavior.

## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Keep business and domain rules server-controlled.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Use a modular monolith for V0; do not introduce microservices without an approved need.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Mobile V0 architecture contract

### Application identity and targets

The accepted mobile application is a future Flutter application at `apps/mobile/`. The canonical domain is `tailtag.app`; its Android application ID and namespace and iOS bundle identifier are all `app.tailtag`. There is no legacy-app, `finnthepanther`, signing, store-continuity, migration, or compatibility obligation. The V0 target is Android API 24+ and iOS 15.1+. Phones are primary, while tablets remain compatible without a V0-specific optimization. A physical-device requirement is not part of baseline validation.

Issue #131 will create and commit repository-owned `apps/mobile/.fvmrc` configuration pinning exact stable Flutter `3.47.1`; Dart comes from that Flutter SDK and is not independently pinned. Flutter must never follow a moving channel. Any upgrade requires an explicit reviewed pull request. The upstream Flutter tag is `6655482ec06e547f90abf8ae7590466f4415978d` (bundling Dart `3.13.1`).

### Structure, dependencies, routing, and state

Features own their Views, ViewModels, Repositories, and Services. A feature may use shared, explicitly owned infrastructure but must not depend on a sibling feature. Do not introduce a domain/use-case layer unless demonstrated complexity warrants it; do not add abstractions or framework machinery merely in anticipation of it.

`go_router` owns declarative application routing. Riverpod owns state and dependency composition, including test overrides; no second dependency-injection framework or foundation code generation is allowed. `package:http` is the HTTP transport and is composed through an injected `Client`, allowing repositories/services to be tested without network access.

### API contracts and generated code

The backend is authoritative for product/domain rules. The mobile client uses the current unversioned `/api/` namespace, with schema at `/api/schema/`, docs at `/api/docs/`, and authenticated `/api/me/` as the identity proof. It sends exactly one Clerk session token in `Authorization: Bearer`.

A generated, low-level OpenAPI client and DTO layer may model the wire API, but is isolated behind TailTag-owned repositories and services. Feature code must never import generated wire models. Issue #134 must pin the generator and its configuration; regeneration from the authoritative backend schema followed by a clean-diff check must deterministically detect drift.

### Runtime configuration and authentication

TailTag owns a typed `AppConfig` populated from compile-time Dart defines. Selecting a local versus Railway Development API is configuration rather than flavors or schemes. Compile-time values embedded in an application are not secrets. This does not repurpose the existing backend-smoke `TAILTAG_DEVELOPMENT_API_BASE_URL` variable or the fixed `http://localhost:3000` auth-tooling origin as the mobile configuration contract.

`clerk_flutter` is contained behind an injectable TailTag-owned auth/session interface. Clerk owns session persistence and token refresh; TailTag must not create a separate persistent bearer-token store, and product features receive no Clerk types. It is an initial beta SDK direction to be reassessed in #135, not a dependency pin here.

### Tests, simplicity, and review authority

Tests exercise feature behavior through the above owned boundaries: Riverpod overrides/providers and injected HTTP clients make isolated tests possible. Generated-client drift is verified by deterministic regeneration and a clean diff. The architecture deliberately remains feature-oriented and small; additional layers, DI systems, code generation, flavors, and token persistence need a demonstrated requirement and approved change.

`@TailTag-Game/core-maintainers` approves frontend architecture. Relevant mobile/frontend contributors should review changes.

### Child-issue ownership and scope boundary

Issue #131 owns the scaffold, identifiers/minimum-platform implementation, committed `apps/mobile/.fvmrc` exact Flutter `3.47.1` pin, and both platform builds/launches. Issue #132 owns root commands, `AppConfig` implementation, configuration inputs, and diagnostics. Issue #133 owns CI. Issue #134 owns generator/client implementation and proof. Issue #135 owns live Clerk proof. Issue #136 owns independent clean-environment validation.

Issue #130 establishes only this architecture contract and ADR. It adds no application secret, Flutter scaffold, dependency, platform project, screen, command implementation, diagnostic implementation, product behavior, or `apps/mobile/` directory.

## V0 player-profile flow

The dedicated profiles module adds product state without changing the existing
identity boundary:

```text
Clerk subject
  -> accounts.User.id (canonical identity)
  -> profiles.PlayerProfile (product state)
  -> authenticated + onboarding complete + enabled
  -> later domain-specific participation requirements
```

Profile-surface reads may lazily materialize the default incomplete profile
row. Participation eligibility is a separate fail-closed lookup: it never
creates, repairs, or infers profile state. Composed Railway validation for this
flow is owned by #120; #113 adds no Railway profile smoke command.

## Current repository and open decisions

The repository currently contains documentation, repository checks, the API
foundation, and the V0 player-profile module. Before adding client applications,
shared packages, gameplay capabilities, or other runtime areas, an approved spec
and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

Accepted backend and mobile architecture choices do not settle every V0/V1 detail. Open decisions include the final domain model, product API contracts, deployment configuration, environment variables, operational policies, and implementation details owned by the relevant child issues. These must be resolved by current approved issues/specs before implementation.

## Verification architecture

`scripts/doctor.sh` validates the local Git/GitHub setup, repository location, remote, branch, working-tree state, required backend/devcontainer artifacts, and host Docker/Compose readiness. Inside the TailTag devcontainer it additionally checks the selected Python version, `uv`, locked dependencies, canonical Make commands, and non-mutating PostgreSQL connectivity. The API workflow (`.github/workflows/api.yml`) runs on pull requests, pushes to `main`, and manual dispatches. On a pull request, its relevance classifier runs the canonical root `make api-check` validation contract only when the change can affect backend validation; otherwise the same stable job reports the explicit successful skip. On a push to `main`, it force-runs that same contract for Railway Wait for CI.

Setup in the Makefile, CI, and devcontainer synchronizes both locked projects:
the API and the separate non-package Semgrep CE project. CI then runs exactly
one validation command, `make api-check`; the no-sync contract performs Ruff
formatting and linting, strict Pyright, deterministic TailTag-owned Semgrep
rule-fixture analysis and local blocking scan, PostgreSQL-backed pytest, Django
checks, migration drift, drf-spectacular configuration validation, and Gunicorn
configuration loading. Semgrep's canonical scan validates rule/fixture metadata
before its fixture test, uses the root `.semgrepignore` policy, scans all
tracked API Python including tests plus the five approved root helpers, and
explicitly clears inherited baseline state. CI adds no Semgrep-specific action,
account, token, secret, Registry rule, remote configuration, or result upload.
The gate provides no SCA/dependency-vulnerability or secret scanning, SARIF
output, AppSec Platform integration, comprehensive security claim, or arbitrary
interfile analysis. Its raw-SQL checks are deliberately limited to supported
direct and same-lexical-block forms; arbitrary aliases, interprocedural flow,
and unsupported concatenation are outside that coverage boundary. The same
commands are documented in `services/api/README.md`.

The API service uses PostgreSQL for runtime checks and does not provide a SQLite fallback. Keep its CI, Docker, and contributor commands aligned as the foundation evolves; do not infer deployment behavior from this local/CI foundation.

## Decision log

The accepted architecture decisions are recorded in:

- [0001 — Use Django and DRF for the backend](adrs/0001-use-django-and-drf-for-backend.md)
- [0002 — Use PostgreSQL as the primary database](adrs/0002-use-postgresql-as-primary-database.md)
- [0003 — Use Clerk for player authentication](adrs/0003-use-clerk-for-player-authentication.md)
- [0004 — Use Railway for V0 hosting](adrs/0004-use-railway-for-v0-hosting.md)
- [0005 — Use a modular monolith for V0](adrs/0005-use-modular-monolith-for-v0.md)
- [0006 — Use Flutter for mobile V0](adrs/0006-use-flutter-for-mobile-v0.md)

See [the ADR index](adrs/README.md) for the decision threshold and format.
