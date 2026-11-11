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
- Render for V0 backend hosting ([ADR 0011](adrs/0011-move-v0-hosting-from-railway-to-render.md)). Staging and Production use the Virginia region, and Development uses Oregon ([ADR 0012](adrs/0012-run-staging-and-production-in-render-virginia.md)). Development and Staging both run on Render. Railway Development and Staging are frozen, and #412 retires them.

The historical Django POC has been promoted and reset at `services/api/`. Its POC-only authentication, session/CSRF behavior, fursuit fields, routes, deletion behavior, and other experimental choices were evaluation evidence, not V0 requirements.

## Staging boundary

TailTag has one persistent Staging environment on Render in the Virginia
region. It has an isolated `tailtag-api-stg` service, a `tailtag-postgres-stg`
database, runtime configuration and secrets, a Clerk Production application,
private R2 ownership, and public API `https://staging.tailtag.app`. It is a
synthetic-data production-rehearsal backend, while Render Development remains
the mutable contributor/integration environment. TailTag has no Production
environment. Render auto-deploy is off for Staging. Each Staging deploy runs
through the promotion script `scripts/api_staging_render_promote.py`. The
boundary does not define immutable builds (#201) or repeatable promotion
behavior (#202). See the maintained [Staging runbook](development/staging.md).

## Backend phases

Phase 0 established the clean `services/api` foundation and local contributor environment. Phase 1 now has authoritative backend CI and pre-merge GitHub validation through `task api-check`, its persistent Render Development environment, an explicit Render pre-deploy migration step, post-deploy HTTP smoke verification, and an enforced normal-contributor delivery path from protected `main` to Render Development. This document does not define production deployment configuration or product application behavior.

## Render development environment

The V0 development environment is a single, explicitly non-production Render
environment. The Blueprint `render.yaml` defines it, and Render hosts it in
the Oregon region ([ADR 0011](adrs/0011-move-v0-hosting-from-railway-to-render.md),
[ADR 0012](adrs/0012-run-staging-and-production-in-render-virginia.md)).

| Item | Established configuration |
| --- | --- |
| Blueprint | `render.yaml`, project `tailtag`, environment `development` |
| API service | `tailtag-api-dev`, a Docker web service that builds `main` from `TailTag-Game/tailtag` |
| Docker context | `services/api`, using `services/api/Dockerfile` |
| Runtime | The existing production image and its Gunicorn CMD on port 8000. The Blueprint sets `PORT=8000`. |
| PostgreSQL | Render Postgres `tailtag-postgres-dev` (PostgreSQL 18). The API reads it through `DATABASE_URL`. The Blueprint sets an empty IP allow list. |
| Public API endpoint | `https://tailtag-api-development.onrender.com` |
| Platform health check | `/health/ready` |

The Blueprint names the development variables without recording secret values.
Render generates `DJANGO_SECRET_KEY`. `DATABASE_URL` comes from the
`tailtag-postgres-dev` database. The Blueprint sets
`DJANGO_SETTINGS_MODULE=config.settings.production` and `PGSSLMODE=require`.
Secret and host values use `sync: false`, so they live only in Render. `PORT=8000`
is platform runtime configuration that matches the Gunicorn binding. It is not a
Django application variable. No SQLite fallback exists.

Render runs the pre-deploy command `python -m config.replacement_migrate` for
each deploy attempt. It runs after the candidate image is built and before the
new version takes traffic. It uses the same production settings and
`DATABASE_URL` as the API process. A redeploy is a new attempt and can run the
command again. Django records applied migrations, so a current schema normally
makes the next run a no-op.

The Docker CMD, Gunicorn process, Django startup, health endpoints, and local
`task api-run` command do not run migrations. If the pre-deploy command fails,
the deploy fails and the previous version keeps serving. The deploy state and
deploy log are the diagnostic record. See the maintained
[backend development delivery operations](development/backend-delivery-operations.md)
guide for recovery and rollback boundaries.

Render auto-deploy is off (`autoDeployTrigger: "off"`). The
`Render Development deploy` GitHub Actions workflow starts each deploy through
a Render deploy hook (#408). It runs for a merge to `main` that changes
`services/api/**`. It waits for the other workflows on the commit. If one of
them failed, it does not deploy. After the deploy, it waits until
`/health/identity` shows the commit and then runs `task api-smoke` against the
public API. The workflow does not provision PostgreSQL or change Render
settings. A smoke failure is a failed Actions run with endpoint-level
diagnostics, not an automatic rollback or redeploy.

For normal contributor delivery, the active `Protect main` GitHub ruleset
requires a pull request, one approval, resolved review conversations, squash
merge, and the stable `API foundation checks` status check. That check exists
on every pull request: relevant pull requests run the canonical
`task api-check`, while irrelevant ones complete through the explicit
successful skip path. The same workflow also runs for every push to `main`,
using the same job and canonical command. The deploy workflow waits for that
run before it deploys the resulting `main` commit.

The repository owner retains a pull-request-only ruleset bypass as an
exceptional, auditable administrative or recovery override. It is outside the
normal contributor delivery path and must not be used for routine development
or delivery. The active ruleset remains the evidence that normal contributors
require review. This design does not claim that a deliberately privileged
administrator can never override GitHub protections. It ensures that a normal
contributor cannot cause a Render Development deploy while bypassing required
pull-request CI and review.

This environment contains no production environment, preview environment
(`previews.generation` is `off`), Redis, workers, or other application
infrastructure. Its one cron job, `tailtag-cleanup-dev`, deletes catch request
history after each review deadline ([ADR 0013](adrs/0013-run-catch-request-cleanup-as-render-cron-jobs.md)).

Delivery failures have distinct primary surfaces:

| Failure | Control and primary diagnostic surface |
| --- | --- |
| Pre-merge backend CI | GitHub `API foundation checks`; the PR cannot normally merge. |
| Missing approval or unresolved review | GitHub ruleset and PR merge requirements; the PR cannot normally merge. |
| Post-merge CI | GitHub Actions. The deploy workflow does not deploy after a failed workflow. |
| Migration | Render pre-deploy command result in the deploy log. The previous version keeps serving. |
| Build, deploy, or readiness | Render deploy state and logs. |
| Post-deploy smoke | The `Render Development deploy` run. The deploy succeeded, but broader HTTP verification failed. |

The delivery path adds no automatic rollback behavior.

Staging uses the same Blueprint with its own services and its own promotion
path. See the [Staging runbook](development/staging.md).

Railway history: Development and Staging ran on Railway before ADR 0011. The
Railway environments are frozen, and #412 retires them. The Railway delivery
design (#77, #78, #80) remains in git history and in the historical records.


## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Keep business and domain rules server-controlled.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Use a modular monolith for V0; do not introduce microservices without an approved need.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Mobile V0 architecture contract

### Application identity and targets

The TailTag V0 Flutter application scaffold is at `apps/mobile/`. The canonical domain is `tailtag.app`; its Android application ID and namespace and iOS bundle identifier are all `app.tailtag`. There is no legacy-app, `finnthepanther`, signing, store-continuity, migration, or compatibility obligation. The V0 target is Android API 26+ and iOS 17+ (raised from 15.1 by [ADR 0009](adrs/0009-use-native-clerk-sdks-for-mobile-auth.md)). Phones are primary, while tablets remain compatible without a V0-specific optimization. A physical-device requirement is not part of baseline validation.

Issue #131 supplies the scaffold, repository-owned `apps/mobile/.fvmrc` exact stable Flutter pin, native identifiers and minimum-platform floors, and initial Android and iOS platform proof. The pin is Flutter `3.47.2`: #131 committed `3.47.1`, and #154 upgraded it through a reviewed pull request. Dart comes from that Flutter SDK and is not independently pinned. Flutter must never follow a moving channel. Any upgrade requires an explicit reviewed pull request. The upstream Flutter tag is `d3b14c876900e553bc736ca19295fc09e3853e8e` (bundling Dart `3.13.2`).

### Structure, dependencies, routing, and state

Features own their Views, ViewModels, Repositories, and Services. A feature may use shared, explicitly owned infrastructure but must not depend on a sibling feature. Do not introduce a domain/use-case layer unless demonstrated complexity warrants it; do not add abstractions or framework machinery merely in anticipation of it.

`go_router` owns declarative application routing. Riverpod owns state and dependency composition, including test overrides; no second dependency-injection framework or foundation code generation is allowed. `package:http` is the HTTP transport and is composed through an injected `Client`, allowing repositories/services to be tested without network access.

### API contracts and generated code

The backend is authoritative for product/domain rules. The mobile client uses the current unversioned `/api/` namespace, with schema at `/api/schema/`, docs at `/api/docs/`, and authenticated `/api/me/` as the identity proof. For an authenticated request, it sends exactly one Clerk session token in `Authorization: Bearer`, and only to an HTTPS URL within the configured TailTag API origin. It omits the header over HTTP, so a cleartext Local configuration cannot exercise authenticated endpoints. Authenticated requests must not follow redirects automatically; following one requires validating that its target remains HTTPS and within the configured API origin before issuing a new request with the header.

A generated, low-level OpenAPI client and DTO layer may model the wire API, but is isolated behind TailTag-owned repositories and services. Feature code must never import generated wire models. Issue #134 must pin the generator and its configuration; regeneration from the authoritative backend schema followed by a clean-diff check must deterministically detect drift.

### Runtime configuration and authentication

TailTag owns a typed `AppConfig` populated from compile-time Dart defines. Selecting a local versus Render Development API is configuration rather than flavors or schemes. Compile-time values embedded in an application are not secrets. This does not repurpose the existing backend-smoke `TAILTAG_DEVELOPMENT_API_BASE_URL` variable or the fixed `http://localhost:3000` auth-tooling origin as the mobile configuration contract.

The approved Local API root is `http://127.0.0.1:8000` on the contributor host. Android emulators and USB-connected Android devices reach it through `adb reverse`, which `task mobile-run` applies, so the app keeps the same root. Dart-owned sockets are not governed by Android network security configuration or iOS App Transport Security, so no cleartext policy is configured; a future platform-owned HTTP client must add a debug-only, host-scoped policy and must not enable cleartext release-wide. See [the mobile contributor guide](development/mobile.md). Authenticated Local testing requires HTTPS termination or the HTTPS Render Development API.

The official Clerk iOS and Android SDKs are contained behind the TailTag-owned `AuthSession` boundary in `lib/core/auth/` ([ADR 0009](adrs/0009-use-native-clerk-sdks-for-mobile-auth.md)). Clerk owns session persistence and token refresh. TailTag must not create a separate persistent bearer-token store, and product features receive no Clerk types.

### Tests, simplicity, and review authority

Tests exercise feature behavior through the above owned boundaries: Riverpod overrides/providers and injected HTTP clients make isolated tests possible. Generated-client drift is verified by deterministic regeneration and a clean diff. The architecture deliberately remains feature-oriented and small; additional layers, DI systems, code generation, flavors, and token persistence need a demonstrated requirement and approved change.

`@TailTag-Game/core-maintainers` approves frontend architecture. Relevant mobile/frontend contributors should review changes.

### Child-issue ownership and scope boundary

Issue #131 owns the scaffold, identifiers/minimum-platform implementation, committed `apps/mobile/.fvmrc` exact Flutter pin, and both platform builds/launches. Issue #132 owns root commands, `AppConfig` implementation, configuration inputs, Android emulator host mapping and API 28+ Local HTTP coverage, and diagnostics. Issue #133 owns CI. Issue #134 owns generator/client implementation and proof. Issue #135 owns live Clerk proof. Issue #136 owns independent clean-environment validation.

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
creates, repairs, or infers profile state. Composed hosted validation for this
flow is owned by #120; #113 adds no hosted profile smoke command.

## Current repository and open decisions

The repository currently contains documentation, repository checks, the API
foundation, the V0 player-profile module, and the mobile application scaffold.
Before adding shared packages, gameplay capabilities, or other runtime areas,
an approved spec and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

Accepted backend and mobile architecture choices do not settle every V0/V1 detail. Open decisions include the final domain model, product API contracts, deployment configuration, environment variables, operational policies, and implementation details owned by the relevant child issues. These must be resolved by current approved issues/specs before implementation.

## Verification architecture

`task doctor` (the Python `scripts/doctor.py`; `scripts/doctor.sh` is a POSIX wrapper for it) validates the local Git/GitHub setup, repository location, remote, branch, working-tree state, required backend/devcontainer artifacts, and host Docker/Compose readiness. Inside the TailTag devcontainer it additionally checks the selected Python version, `uv`, locked dependencies, canonical task commands, and non-mutating PostgreSQL connectivity. The API workflow (`.github/workflows/api.yml`) runs on pull requests, pushes to `main`, and manual dispatches. On a pull request, its relevance classifier runs the canonical root `task api-check` validation contract only when the change can affect backend validation; otherwise the same stable job reports the explicit successful skip. On a push to `main`, it force-runs that same contract, and the `Render Development deploy` workflow waits for it.

Setup in the Taskfile, CI, and devcontainer synchronizes both locked projects:
the API and the separate non-package Semgrep CE project. CI then runs exactly
one validation command, `task api-check`; the no-sync contract performs Ruff
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

Architecture decisions are recorded in:

- [0001 — Use Django and DRF for the backend](adrs/0001-use-django-and-drf-for-backend.md)
- [0002 — Use PostgreSQL as the primary database](adrs/0002-use-postgresql-as-primary-database.md)
- [0003 — Use Clerk for player authentication](adrs/0003-use-clerk-for-player-authentication.md)
- [0004 — Use Railway for V0 hosting](adrs/0004-use-railway-for-v0-hosting.md) (superseded by 0011)
- [0005 — Use a modular monolith for V0](adrs/0005-use-modular-monolith-for-v0.md)
- [0006 — Use Flutter for mobile V0](adrs/0006-use-flutter-for-mobile-v0.md)
- [0007 — Use Render and Sentry for V0 observability](adrs/0007-v0-observability-backend.md) (proposed)
- [0008 — Use asyncio and httpx for headless simulation](adrs/0008-use-asyncio-httpx-for-headless-simulation.md)
- [0010 — Keep Railway for V0 hosting after the GCP evaluation](adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) (superseded by 0011)
- [0011 — Move V0 hosting from Railway to Render](adrs/0011-move-v0-hosting-from-railway-to-render.md) (region clause superseded by 0012)
- [0012 — Run Staging and Production in the Render Virginia region](adrs/0012-run-staging-and-production-in-render-virginia.md)

See [the ADR index](adrs/README.md) for the decision threshold and format.
