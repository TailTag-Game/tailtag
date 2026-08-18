# TailTag API

`services/api` is TailTag's V0 Django API foundation. It provides Django
administration, PostgreSQL-backed liveness/readiness checks, and OpenAPI
schema/documentation infrastructure. It also defines TailTag's application-user
identity and Clerk request verification. It intentionally does not implement
Clerk-to-user request resolution, player profiles, or gameplay APIs.

The service uses Python 3.13, Django, Django REST Framework, PostgreSQL 17,
`uv`, Ruff, strict Pyright, pytest, drf-spectacular, Gunicorn, and Docker. This is
the detailed operating reference for API contributors; the concise fresh-clone
journey is in [Getting Started](../../docs/development/getting-started.md).

Maintainers operating or recovering the shared Railway development backend
should use the [backend development delivery operations guide](../../docs/development/backend-delivery-operations.md).

## Current foundation boundary

`accounts.User` is Django's configured user model and TailTag's canonical
application identity. The `fursuits` app remains a neutral shell with no models,
migrations, or public API behavior. Current TailTag product-domain
administration does not exist.

The POC application migrations were intentionally reset. On a clean database,
`make api-migrate` applies the initial `accounts.User` migration and Django
framework migrations; future TailTag domain migrations require approved feature
work. Historical Django POC documents remain evaluation evidence and are not
current setup instructions.

## Application identity contract

A TailTag application user and a Clerk user are related identities with
different responsibilities:

- `accounts.User.id` is the repository-standard `BigAutoField` primary key and
  canonical identity inside TailTag.
- `accounts.User.clerk_user_id` is the required, unique link to the external
  Clerk authentication-provider identity. It is opaque, case-sensitive, and is
  neither a TailTag primary key nor a domain foreign identity.
- `accounts.User.is_staff` and the inherited Django password, last-login,
  superuser, group, and permission fields support Django administration. They do
  not define TailTag product roles or account lifecycle behavior.
- Ordinary application-user creation rejects Django privilege flags and local
  Django passwords. The model rejects usable passwords for non-superusers and
  clears the local password when a superuser is demoted. Only the Django
  superuser bootstrap path accepts a local password for administration, and
  configured password validation compares that password with the administrative
  user's Clerk ID.
- No email address, username, display name, avatar, biography, profile state, or
  gameplay data is stored on the application-user model.

Issue #96 verifies Clerk requests but does not resolve a TailTag user. Issue
#97 alone resolves or provisions `accounts.User` and creates final DRF
authentication; only then will authenticated DRF code receive the resolved user
as `request.user`.

Model declarations must refer to the configured user model, never to a Clerk ID:

```python
from django.conf import settings
from django.db import models


class FutureDomainModel(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
```

Runtime code that needs the model class uses
`django.contrib.auth.get_user_model()`. Domain rows store the resulting TailTag
primary key in their foreign-key columns. Do not use `clerk_user_id` as a domain
foreign key, expose it as TailTag's canonical identity, or copy other fields from
Clerk into this model without a separately approved requirement.

### Existing development database prerequisite

The initial custom-user migration is the supported baseline for a fresh
PostgreSQL database. A database that already applied Django's admin migrations
while `AUTH_USER_MODEL` was `auth.User` has an incompatible applied migration
graph and admin-log foreign key; #95 intentionally does not rewrite that history
in place.

Do not deploy this user-model switch to an already-migrated development database
until maintainers have separately authorized and coordinated its reset or
transition. The normal `make api-migrate` and Railway pre-deploy migration command
do not perform that operation. This repository contains no production
environment, and #95 does not authorize any database or environment reset.

## Local configuration

Before using either supported workflow, create the ignored local environment
file from the repository root:

```bash
cp services/api/.env.example services/api/.env
```

The template contains safe local-only defaults and no real secrets. `.env` is
ignored by Git: never commit it, paste it into tickets, or share it as a log
attachment. Local Django settings load `services/api/.env`; production settings
do not load it implicitly.

| Setting | Required | Used by |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Django database connection. The native template uses `127.0.0.1:5432`. |
| `DJANGO_SECRET_KEY` | Yes | Django. The template value is safe only for local development. |
| `POSTGRES_DB` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `POSTGRES_USER` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `POSTGRES_PASSWORD` | Yes for Compose | PostgreSQL 17 bootstrap. |
| `DJANGO_ALLOWED_HOSTS` | No | Django; local settings have safe defaults when omitted. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | No | Django; local settings have safe defaults when omitted. |

Django reads its database connection only from `DATABASE_URL`; it does not read
`POSTGRES_*`. Compose uses `POSTGRES_*` to bootstrap PostgreSQL and gives
containerized Django a `db:5432` connection. Native Django uses the explicit
`DATABASE_URL` in `.env` and reaches the same published database at
`127.0.0.1:5432`. This hostname difference is expected: container and host
processes are in different network namespaces.

PostgreSQL 17 is the supported local major version. There is no SQLite fallback
and host-installed PostgreSQL is not a supported contributor workflow. If `.env`
is absent or `DATABASE_URL` is invalid, local Django stops with a sanitized
configuration error that does not print credentials.

## Clerk request-authentication configuration (#96)

Clerk request authentication is disabled by default. Set
`CLERK_AUTHENTICATION_ENABLED=true` only when the following complete
configuration is available:

| Setting | Required | Purpose |
| --- | --- | --- |
| `CLERK_AUTHENTICATION_ENABLED` | No; defaults to `false` | Enables Clerk bearer-token verification. |
| `CLERK_JWT_KEY` | Yes when enabled | Configured Clerk instance JWT public key used for verification. |
| `CLERK_AUTHORIZED_PARTIES` | Yes when enabled | Comma-separated list of authorized parties. |

Verification uses Clerk backend SDK 6.0.1 with the configured instance JWT
public key and does not make network requests. It does not require, read, or
document a Clerk secret key or publishable key. TailTag does not independently
validate or claim to validate `iss`.

TailTag accepts exactly one `Bearer` token68 credential in the `Authorization`
header; the scheme is case-insensitive. An absent header causes no verification
attempt. Every supplied malformed or invalid credential fails with the same
generic authentication failure.

The SDK is explicitly configured to accept a `session_token`. TailTag also
requires the verified claims to include nonempty `sid` as a session-bound
discriminator and nonempty `sub`. The resulting
`VerifiedClerkIdentity` is immutable and exposes only the subject; it never
exposes `sid` or raw claims downstream.

This issue deliberately stops at request verification. Issue #97 resolves or
provisions `accounts.User` and creates the final DRF authentication. Issue #98
owns protected-endpoint `401` proof, and issue #100 owns Railway development
enablement.

## Canonical backend commands

Run these commands from the repository root. They are the supported interface
for normal setup, Django operations, and validation; they avoid contributors
having to remember `uv`, Django, or individual quality-tool invocations.

| Command | Purpose | Required state |
| --- | --- | --- |
| `make help` | List canonical backend commands. | None. |
| `make api-setup` | Synchronize locked backend dependencies. | `uv` available; does not start services or change schema. |
| `make api-run` | Run Django on port 8000. | Dependencies, `services/api/.env`, and PostgreSQL available. |
| `make api-test` | Run PostgreSQL-backed backend tests. | Dependencies, `services/api/.env`, and PostgreSQL available. |
| `make api-check` | Run complete local pre-PR backend validation. | Dependencies, `services/api/.env`, and PostgreSQL available. |
| `make api-migrate` | **Apply existing Django migrations.** | Dependencies, `services/api/.env`, and PostgreSQL available; mutates schema. |
| `make api-migrations` | **Create Django migrations from model changes.** | Dependencies and `services/api/.env`; mutates migration state but does not apply migrations. |
| `make api-migrations-check` | Check for migration drift. | Dependencies, `services/api/.env`, and PostgreSQL available; does not create migrations. |
| `make api-shell` | Open the Django shell. | Dependencies, `services/api/.env`, and PostgreSQL available. |
| `make api-smoke` | HTTP-check an already-running API. | API already running; never starts services or applies migrations. |

`make api-check` runs formatting, linting, strict typing, PostgreSQL-backed
tests, Django system checks, migration-drift detection, OpenAPI validation, and
Gunicorn production-configuration loading. It neither creates nor applies
migrations.

## Railway development migrations

The shared Railway `development` API service applies Django migrations through
its service-level **Pre-Deploy Command**:

```text
python manage.py migrate --settings=config.settings.production --noinput
```

This is configured in Railway service settings, not in `railway.toml` or
`railway.json`. The Django `--settings` option explicitly selects the same
production settings as Gunicorn. Railway builds the candidate API image, runs
the command in its pre-deploy container using the API service's existing
`DATABASE_URL` reference, then starts Gunicorn only when the command exits
successfully. Railway readiness checks `/health/ready` after the candidate
application starts.

```text
build candidate image
-> run Django migrations in Railway pre-deploy
-> start candidate Gunicorn process
-> Railway readiness check
-> #77 post-deploy HTTP smoke verification
```

The pre-deploy command runs for each API deployment attempt. A manual redeploy
is a new attempt and can run it again; Django's migration table normally makes
already-applied migrations a no-op. This is deliberately not a global
exactly-once guarantee and does not require distributed locking for V0.

Migrations must remain absent from Docker CMD/entrypoint, Gunicorn and Django
startup, health/readiness endpoints, and normal local commands such as `make
api-run`. Local contributors continue to run `make api-migrate` explicitly.
The Railway pre-deploy container uses the same private Railway database
configuration as the API; do not add a second database URL, expose a public
PostgreSQL endpoint, or put database credentials in source or logs.

### Railway migration failures and recovery

A non-zero pre-deploy command fails the candidate deployment before it becomes
the active application deployment. Inspect the deployment's state and logs in
the Railway dashboard, or use the Railway CLI without printing service
variables:

```bash
railway deployment list --service api --environment development --json
railway logs <deployment-id> --deployment --lines 200
```

Do not blindly redeploy a failed migration. Inspect the migration or
configuration error, correct it in a reviewed change, run the normal CI checks,
then inspect and reconcile the database state before retrying deployment.
Django records a migration only after it completes, so a failed, unrecorded
migration is rerun from its first operation rather than resumed at the failed
operation. This is especially important after non-transactional operations,
which can leave state that requires direct inspection of the specific migration
and database; no automatic repair is provided.

Rolling back or redeploying an older application revision does **not** roll back
the PostgreSQL schema. Only redeploy an older revision when it remains compatible
with the current schema. Do not automatically run reverse Django migrations:
they can be destructive, irreversible, or data-losing. A schema reversal is a
reviewed operator action for the specific migration.

Prefer forward-compatible migrations during deployment transitions where
practical: add tables or columns before code requires them, use nullable columns
or safe defaults when appropriate, and defer destructive cleanup until older
revisions no longer use the old schema. This is guidance, not a claim that every
schema change is backward compatible or a mandate for a separate migration
framework.

The GitHub Actions post-deploy smoke workflow verifies a successful Railway
development deployment with the same `make api-smoke` contract. It does not
deploy, migrate, or start the API. The protected `main`-to-development
delivery chain owns those separate responsibilities.

Use the commands for distinct purposes:

- `./scripts/doctor.sh` diagnoses environment readiness; it does not repair or
  mutate the environment.
- `make api-test` is the normal feedback loop while developing.
- `make api-smoke` verifies an already-running API over HTTP.
- `make api-check` is the pre-pull-request validation suite.

## Recommended devcontainer workflow

The repository devcontainer is the primary supported backend workflow. Install
Git, Docker Desktop (or another Docker Engine with the Compose plugin), and use
a devcontainer-capable editor. Host Python, `uv`, and PostgreSQL are not
required.

After creating `services/api/.env`, open the repository root in the editor and
choose **Reopen in Container**. The devcontainer uses `services/api/compose.yaml`
with the `api` service as the repository-root workspace, forwards port 8000, and
starts the PostgreSQL service with its health check.

Its post-create hook synchronizes locked dependencies. It does not apply
migrations or make schema changes. Inside the devcontainer, run:

```bash
./scripts/doctor.sh
make api-migrate
make api-run
```

Leave `make api-run` running. In another terminal, run:

```bash
make api-smoke
```

Use `make api-test` while developing and `make api-check` before a pull request.
Migrations remain explicit after a new, reopened, or rebuilt devcontainer.

## Supported native workflow

The secondary supported path is intentionally narrow:

- Python 3.13 and `uv` installed on the host
- Docker Engine with the Compose plugin available on the host
- PostgreSQL 17 supplied by this repository's Compose `db` service
- Django run natively on the host with `services/api/.env`

From the repository root, start only the database infrastructure, then use the
same canonical commands:

```bash
docker compose -f services/api/compose.yaml up -d db
make api-setup
make api-migrate
make api-run
```

In a second terminal, use `make api-smoke`. The host connects to the
Compose-published database at `127.0.0.1:5432`, as configured by `.env`.

This support boundary excludes host-installed PostgreSQL, SQLite, Python versions
other than 3.13, arbitrary environment managers, and OS-specific setup variants.
Other arrangements may work, but they are not documented or supported contracts.

## PostgreSQL lifecycle

Compose stores local PostgreSQL data in the named `postgres_data` volume. Normal
service stop/start, image rebuilds, and devcontainer reopen/rebuild operations
preserve that volume and its data.

For infrastructure lifecycle operations, run Compose from the repository root:

```bash
docker compose -f services/api/compose.yaml ps
docker compose -f services/api/compose.yaml logs db
docker compose -f services/api/compose.yaml down
```

`down` stops services while preserving the volume. To intentionally erase local
database state, use the following **destructive** command:

```bash
docker compose -f services/api/compose.yaml down --volumes
```

This deletes local PostgreSQL data. Start the database again and run `make
api-migrate` explicitly; no workflow automatically recreates schema state.

## HTTP surfaces

With `make api-run` running, local development surfaces are:

| URL | Purpose |
| --- | --- |
| `http://127.0.0.1:8000/health/live` | Process/application liveness; does not query PostgreSQL. |
| `http://127.0.0.1:8000/health/ready` | Readiness, including a lightweight PostgreSQL dependency check. |
| `http://127.0.0.1:8000/api/schema/` | Generated OpenAPI schema. |
| `http://127.0.0.1:8000/api/docs/` | Interactive OpenAPI documentation. |
| `http://127.0.0.1:8000/admin/` | Django development/operational administration. |

`make api-smoke` is the normal HTTP verification path. It requires an already
running service and checks liveness, readiness, schema, and interactive docs for
HTTP 200. It defaults to `http://127.0.0.1:8000`; target another running
environment only when appropriate:

```bash
API_BASE_URL=https://example.internal make api-smoke
```

If `/health/ready` returns `503`, Django is reachable but PostgreSQL is not
ready. Diagnose the database before treating it as an API-route problem.

### Post-deploy development verification

`.github/workflows/post-deploy-smoke.yml` reacts to an observed successful
Railway `deployment_status` event only when the deployment environment is
`TailTag / development` and its creator is `railway-app[bot]`. It can also be
run manually without initiating a deployment. Both paths use the non-secret
repository Actions variable `TAILTAG_DEVELOPMENT_API_BASE_URL` and run the
canonical `API_BASE_URL=... make api-smoke` command.

The workflow logs the triggering deployment/status identifiers, ref, and public
target URL, then fails its GitHub Actions job if any smoke endpoint fails. It
does not print the raw GitHub event, use Railway credentials, provision a
database, migrate, roll back, redeploy, or stop the service. The deployment
event identifies what triggered verification; the resulting stable-URL requests
show that the shared development endpoint met the smoke contract after that
event, not that each response is provably served by that deployment's SHA.

### Protected main-to-development delivery

Normal contributor delivery is a composed GitHub and Railway control path:

1. A contributor opens a pull request. The active `Protect main` ruleset
   requires one approval, resolved review conversations, squash merge, and the
   stable `API foundation checks` status check.
2. The API workflow runs that one named job on every pull request. Relevant
   changes run `make api-check`; irrelevant changes take the explicit
   successful skip path.
3. A normal merge creates a `main` commit. The same workflow force-runs the
   canonical `make api-check` contract for that push.
4. Railway's development `api` service autodeploys only
   `TailTag-Game/tailtag` `main` commits and has Wait for CI enabled. It
   waits while GitHub workflows run, skips the candidate when a workflow fails,
   and proceeds only after they succeed.
5. Railway runs the existing pre-deploy migration command, checks
   `/health/ready`, then reports its deployment status. The #77 workflow
   performs the independent real-HTTP smoke verification after a successful
   Railway deployment.

Railway watches only `services/api/**` for this service. Its deployment
relevance is intentionally narrower than backend CI relevance: a change only to
the root `Makefile`, `scripts/api_smoke.py`, `.github/workflows/api.yml`,
documentation, or frontend code does not rebuild the running API unless an
approved runtime build change makes that path relevant.

The repository owner retains a pull-request-only bypass for exceptional,
auditable administrative or recovery use. It is not a normal development or
delivery shortcut and must not be used to validate this path. The guarantee is
for normal contributors, not an assertion that a privileged administrator can
never intentionally override repository protections.

Use the first failing boundary to diagnose delivery:

| Symptom | First place to inspect |
| --- | --- |
| PR cannot merge because backend CI failed | The GitHub `API foundation checks` job. |
| PR cannot merge because review is incomplete | GitHub ruleset and PR merge requirements. |
| Railway candidate waits or is skipped | GitHub Actions for the pushed `main` SHA, then the Railway deployment trigger state. |
| Candidate fails before app startup | Railway pre-deploy migration logs/status. |
| Candidate build, deploy, or readiness fails | Railway deployment state/logs. |
| Railway succeeds but API verification fails | The #77 post-deploy smoke workflow run. |

No automatic rollback occurs. A failed migration, deployment, readiness check,
or smoke run must be diagnosed through its owning surface before any deliberate
recovery action.

For revision evidence, match the merged `main` SHA to the push workflow SHA,
Railway Git-triggered deployment metadata, and the `deployment_status`
SHA/ref that #77 logs. That metadata proves what Railway deployed. A stable
development-domain smoke result proves the HTTP contract after that deployment,
not a cryptographic response-to-SHA binding; record a later superseding
deployment as a race limitation rather than adding an application version
endpoint.

## Django admin

`/admin/` exists for Django framework, development, and operational
administration. It provides read-oriented inspection of TailTag application-user
IDs and their Clerk identity links without rendering password material. User
creation and deletion are not available through the admin; just-in-time
application-user provisioning and account deletion remain outside #95.

A Django superuser is an `accounts.User` with Django's staff and superuser flags
and a local admin password. Those flags are Django administration infrastructure,
not TailTag product roles, and the local password does not implement Clerk player
authentication. Do not infer administration for profiles, fursuits, conventions,
or catches from this surface: those domain models and workflows do not yet exist.

Create a development-only Django superuser after PostgreSQL is available. There
is no canonical Make target for this one Django operation, so use this narrow
low-level command from the repository root:

```bash
uv --directory services/api run python manage.py createsuperuser
```

Supply a unique Clerk user ID for the administrative user when prompted, then
sign in at `http://127.0.0.1:8000/admin/` with that ID and the local admin
password.

## Direct Compose usage

Running the API service itself through plain Compose is lower-level reference
material for infrastructure debugging; it is not a third onboarding workflow.
To build and run the API and database services from the repository root:

```bash
docker compose -f services/api/compose.yaml up --build
```

Compose waits for database health before starting its dependent API service, but
migrations never run automatically. After the services are available, apply them
explicitly with this low-level command:

```bash
docker compose -f services/api/compose.yaml exec api python manage.py migrate
```

Use `docker compose -f services/api/compose.yaml down` to stop these services
while retaining database data. See [PostgreSQL lifecycle](#postgresql-lifecycle)
before resetting a volume.

## Troubleshooting

Use this compact pattern: identify the symptom, run a safe diagnostic, then
apply the recovery for the supported workflow.

| Symptom | Likely cause and diagnostic | Safe recovery |
| --- | --- | --- |
| `doctor.sh` reports Docker or Compose `FAIL` | Docker CLI is missing, daemon is stopped, or the Compose plugin is unavailable. Re-run `./scripts/doctor.sh` after checking Docker Desktop/Engine. | Install or start a compatible Docker Engine with Compose, then re-run doctor. A missing Dev Container CLI is only a `WARN` when a compatible editor is used. |
| Devcontainer cannot open or build | Docker/Compose is unhealthy, or `services/api/.env` is missing. Check host `./scripts/doctor.sh` and the editor's devcontainer build output. | Restore Docker/Compose, create `.env` from the template, then rebuild or reopen the container. |
| Devcontainer post-create dependency sync fails | Locked dependencies could not synchronize. Inside the container, run `./scripts/doctor.sh` to distinguish dependency and database readiness. | Resolve the reported environment problem, then run `make api-setup`; reopen or rebuild only if the editor environment itself is stale. |
| Django reports missing configuration or an invalid `DATABASE_URL` | `services/api/.env` is missing, incomplete, or malformed. | Recopy the template if appropriate and edit only local values. Do not paste `.env` contents into logs or commit the file. |
| Database is unreachable or unhealthy | The `db` service is not running or has failed its health check. Run `docker compose -f services/api/compose.yaml ps` and `docker compose -f services/api/compose.yaml logs db`. | Start it with `docker compose -f services/api/compose.yaml up -d db`, then retry the canonical command. |
| Port 5432 is already in use | Another host process is using the published PostgreSQL port. Check the host process or Compose output. | Stop or reconfigure the conflicting local process; do not substitute a host-installed PostgreSQL workflow. |
| Port 8000 is already in use | Another Django/API process is still listening. | Stop that process, then rerun `make api-run`; `make api-smoke` must target the API instance you intend to verify. |
| Migration errors or drift | Existing migrations have not been applied, or model changes need review. | Use `make api-migrate` for existing migrations. Use `make api-migrations-check` to inspect drift; create migrations only with `make api-migrations` when approved work changes models. |
| `/health/ready` is unavailable or `make api-smoke` fails | The service is not running, PostgreSQL is not ready, or the target URL/status is wrong. Run `make api-smoke` against the running service and inspect `db` status/logs. | Start or repair the intended service/database, then rerun smoke. Use `API_BASE_URL` only for another already-running target. |
| Local database state must be discarded | The named volume intentionally persists through normal stops and rebuilds. | Use the destructive `down --volumes` command in [PostgreSQL lifecycle](#postgresql-lifecycle), then explicitly run `make api-migrate`. |

`FAIL` from `doctor.sh` means a required condition for the environment it is
checking is absent. `WARN` is advisory and does not cause the command to fail.

## Validation boundary

These instructions document the implemented Phase 0 workflow. Independent
clean-environment onboarding validation is tracked separately and may result in
documentation corrections. Do not treat that validation as already complete.
