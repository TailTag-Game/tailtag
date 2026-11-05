# Backend development delivery operations

This guide is the current maintainer runbook for the shared Render backend
development environment. It explains how to classify delivery failures, find
sanitized diagnostics, and choose between redeploying, forward-fixing, and
considering an application-code rollback. It is not a production SRE runbook,
an incident-management process, or a production data-recovery plan.

Its scope is the mutable contributor/integration **Development** environment.
For the separate persistent production-rehearsal target, use the maintained
[Staging runbook](staging.md); do not apply Development delivery or recovery
procedures to Staging.

Backend contributor setup and commands remain in the
[API README](../../services/api/README.md). Durable design and ownership live
in [architecture.md](../architecture.md). The maintained composed integration
procedures and sanitized evidence records live in the
[Wave 2 participation validation](wave-2-participation-validation.md) and
[Wave 3 catching and collection validation](wave-3-catching-validation.md).

## Render Development

Development runs on Render in Oregon, under
[ADR 0011](../adrs/0011-move-v0-hosting-from-railway-to-render.md). The old
Railway Development environment is frozen. Do not use it. #412 retires it.

| Item | Target |
| --- | --- |
| Blueprint | `render.yaml`, project `tailtag`, environment `development` |
| API service | `tailtag-api-dev` |
| Database | `tailtag-postgres-dev` |
| Region | Oregon |
| Public API | `https://tailtag-api-development.onrender.com` (the host keeps the original service name) |

### Delivery

Render auto-deploy is off. The `Render Development deploy` workflow starts each
deploy. It runs for a merge to `main` that changes `services/api/**`. It works
in these steps:

1. It waits until every other workflow on the commit finishes. It expects
   each workflow that the commit's changed files start, including path-filtered
   ones. The `TailTag post-deploy smoke` runs for Railway do not count. A few
   failed GitHub requests in a row count as waiting.
2. If a workflow failed, it does not deploy. Its run stays green with a
   notice, because the failed workflow is already red. If CI is still running
   after 75 minutes, the run turns red, because CI can still pass later.
3. If a newer backend commit is on `main`, it does not deploy. A newer push
   also cancels an older run.
4. It calls the Render deploy hook for that commit. The hook URL is the
   `RENDER_DEVELOPMENT_DEPLOY_HOOK_URL` secret of the `render-development`
   GitHub environment. Only `main` can use that environment.
5. It waits until `/health/identity` shows the commit, then runs
   `task api-smoke`. A timeout or a failed smoke turns the run red.

If a flaky check blocks a deploy, rerun the check. When the rerun passes, run
the workflow with **Run workflow** and enter the full 40-character commit SHA.
The workflow runs the same checks before it deploys. Enter only the latest
backend commit on `main`. A manual run cancels any running deploy run, so the
workflow turns red for an older commit. Do not deploy from the Render
dashboard, because that skips the CI gate.

If the hook URL leaks, regenerate it in the Render service settings. Then
store the new URL in the secret again.

Before the new version takes traffic, Render runs the pre-deploy command
`python -m config.replacement_migrate`. The command prints one word:

- `PASS`: the guarded migration finished.
- `FAIL_GUARD`: a check before the migration failed. Examples are a pin
  mismatch, invalid settings, or a database connection error. No migration
  ran.
- `FAIL_MIGRATION`: a migration failed. Treat the database as partly migrated,
  as [Handle migration failures](#handle-migration-failures) describes.

If the pre-deploy command fails, the deploy fails. The previous version keeps
serving.

The command hides the migration traceback, so the deploy log shows only the
word. After a `FAIL_MIGRATION`, do these steps:

1. Do not start the deploy again. A retry can apply more of a partial
   migration.
2. Open the Shell tab of `tailtag-api-dev`. The shell runs the
   previous version, which still serves traffic.
3. Run
   `python manage.py showmigrations --settings=config.settings.production`.
   Compare the applied migrations with the migrations in the failed commit.
4. Find the failed migration. Reproduce it on a local database from the same
   commit to see the error.
5. Merge a forward fix. Follow
   [Handle migration failures](#handle-migration-failures) for a partial
   migration. Do not run reverse migrations.

### Smoke checks

The `Render Development deploy` workflow runs `task api-smoke` after each
deploy. To check the current deploy by hand, run that workflow with
**Run workflow** and leave the SHA empty.

Run the authenticated smoke from a repository checkout:

```bash
TAILTAG_DEVELOPMENT_API_BASE_URL=https://tailtag-api-development.onrender.com \
API_BASE_URL=https://tailtag-api-development.onrender.com \
CLERK_SMOKE_USER_ID=<opaque-development-user-id> \
task api-auth-smoke
```

Render has no command that copies service variables into a local process. So
the media smoke runs locally with values that you enter at hidden prompts.
Copy each value from the `tailtag-api-dev` Environment page. The
service ID is the `srv-…` part of the dashboard URL.

Run this block in bash. In zsh, `read -p` reads from a coprocess and does not
show a prompt, so start `bash --noprofile --norc` first. Type `exit` when the
block finishes.

```bash
read -rs -p "MEDIA_STORAGE_ENDPOINT_URL: " MEDIA_STORAGE_ENDPOINT_URL; echo
read -rs -p "MEDIA_STORAGE_BUCKET_NAME: " MEDIA_STORAGE_BUCKET_NAME; echo
read -rs -p "MEDIA_STORAGE_ACCESS_KEY_ID: " MEDIA_STORAGE_ACCESS_KEY_ID; echo
read -rs -p "MEDIA_STORAGE_SECRET_ACCESS_KEY: " MEDIA_STORAGE_SECRET_ACCESS_KEY; echo
read -r -p "Render Development service ID: " RENDER_SERVICE_ID
export MEDIA_STORAGE_ENDPOINT_URL MEDIA_STORAGE_BUCKET_NAME \
  MEDIA_STORAGE_ACCESS_KEY_ID MEDIA_STORAGE_SECRET_ACCESS_KEY RENDER_SERVICE_ID
RENDER=true MEDIA_STORAGE_REGION=auto \
DJANGO_SECRET_KEY=local-media-smoke-placeholder \
DJANGO_ALLOWED_HOSTS=localhost DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
DATABASE_URL=postgresql://placeholder:placeholder@localhost:5432/placeholder \
TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-render-development-media-storage-smoke \
task api-media-storage-smoke
unset MEDIA_STORAGE_ENDPOINT_URL MEDIA_STORAGE_BUCKET_NAME \
  MEDIA_STORAGE_ACCESS_KEY_ID MEDIA_STORAGE_SECRET_ACCESS_KEY RENDER_SERVICE_ID
```

The placeholder values hold no secret. The smoke does not connect to the
database. The command fails unless the service ID matches the pinned Render
Development service.

## Environment boundary and access

Use only the Render targets in the [Render Development](#render-development)
table.

The shared environment is disposable, non-production infrastructure. It is
available for integration testing, verification of merged backend behavior,
appropriate shared frontend/backend work, and controlled delivery validation.
It is not:

- production or a performance/SLA benchmark;
- guaranteed to remain continuously available;
- guaranteed to retain test records;
- a place for destructive experiments without coordination; or
- a store for real credentials, personal information, or other
  production-sensitive data.

Use synthetic test data only. Schema or data resets may occur during
development, and no retention guarantee exists. Coordinate disruptive database
resets and destructive load or testing experiments with maintainers before
running them. Never treat this environment as backup storage or as production
evidence.

Render workspace access controls what a person can do. Only maintainers with
access to the Render workspace can open the service Shell or change
development variables. Other contributors must propose configuration changes
through normal project coordination. They must not receive copied secret
values.

## Django admin and Development operator

The production image collects Django admin static assets during its image build.
Gunicorn serves the resulting `/static/` files through WhiteNoise. This is
separate from private media: private media remains in the configured S3/R2
backend and this procedure does not add a public `/media/` route.

For the dedicated Django admin operator, use Render Development only. Open the
Shell tab of `tailtag-api-dev` in the Render dashboard and run:

```text
python manage.py bootstrap_development_operator --settings=config.settings.production
```

The command creates a dedicated operator for an unused identifier. Re-running
it reconciles only an existing account that is already both staff and
superuser, rotating that account's local password without creating a duplicate.
It refuses ordinary, staff-only, and superuser-only player accounts without
changing them. Do not use the command to elevate a player; investigate the
account state and choose a separate dedicated identifier instead.

The identifier and password are hidden interactive inputs only. At the visible
confirmation prompt, type the exact non-secret phrase
`bootstrap Render Development operator`. Never supply either credential as a
command argument or environment variable, or record it in shell history, logs,
issues, pull requests, or committed evidence. No Clerk secret is required. Do
not set `DJANGO_SUPERUSER_PASSWORD`, add credential
variables, create a task or script, or run this command automatically in
build, pre-deploy, startup, health checks, or Gunicorn.

If the command rejects the target, stop and make sure that the Shell belongs
to `tailtag-api-dev` before you run it again. If it rejects stdin or stdout as
non-interactive, use the dashboard Shell tab rather than a redirected
command. If confirmation, empty input, password mismatch, or password
validation fails, correct the hidden input and run it again. For database or
unexpected failures, do not manually alter accounts; retain only sanitized
failure details and investigate before retrying.

### Static and operator troubleshooting

| Symptom | Boundary and recovery |
| --- | --- |
| Image build fails at `collectstatic` | This is a build-time failure. Inspect the failed deploy's log in the Render dashboard, fix the static configuration or asset error, and deploy a reviewed fix. The candidate image was not promoted. |
| `/admin/` loads but a `/static/admin/...` asset is `404` | This is a runtime static-delivery failure. Confirm the deployed revision contains the production collection step and that Gunicorn/WhiteNoise is serving `/static/`; inspect deployment/runtime logs and use normal reviewed recovery. Do not expose private media to work around it. |
| Operator command rejects its target or TTY | Open the Shell tab of `tailtag-api-dev` in the Render dashboard and run the command there. Do not pipe input, pass credentials, or use a non-interactive command. |

## Find state and logs

Start in the Render dashboard. Open the `development` environment of the
`tailtag` project, then open `tailtag-api-dev`.

- Deploy history: open the service's deploy list. Select one deploy to see
  its state and its log. The log shows the pre-deploy result (`PASS`,
  `FAIL_GUARD`, or `FAIL_MIGRATION`) and the application start.
- Service logs: Render keeps application logs and HTTP request logs for 14
  days on Pro. Search is text and RE2 regular expressions only, with no filter
  on custom JSON keys. To follow one request, search its `request_id` or its
  `edge_request_id`, as
  [backend logging and request correlation](../operations/backend-logging.md)
  describes.
- CLI: `render logs` reads the same logs from a terminal. Pass the service
  ID and a time window. The service ID is the `srv-…` part of the dashboard URL.

```bash
render logs -r <service-id> --start <start> --end <end> \
  --direction forward --limit 500 -o text
```

Before any CLI diagnostic, make sure that the service ID belongs to
`tailtag-api-dev`, not to Staging (`tailtag-api-stg`). A bounded `--limit`
query is easier to review and sanitize before sharing. Do not copy an entire
log indiscriminately. Share only the lines needed to explain the failure, after
applying the secret-safety rules below.

## Classify a failure

Symptoms identify the first place to inspect, not a guaranteed root cause.

| Symptom | First place to inspect | Common possibilities |
| --- | --- | --- |
| PR `API foundation checks` fails | The PR's GitHub Actions run | Formatting, lint, type, test, Django, schema, migration-drift, or Gunicorn validation |
| The `Render Development deploy` run keeps waiting | The other workflows on the same commit | CI on the commit is still running. The run waits for every workflow and does not deploy after a failed one |
| Render build fails | The failed deploy's log in Render | Docker build, dependency resolution, or source/build configuration |
| Pre-deploy fails | The failed deploy's log, for the `FAIL_GUARD` or `FAIL_MIGRATION` word | Pin mismatch, runtime configuration, database connectivity, or a Django migration |
| Application deploy fails or crashes | The failed deploy's log, then the service logs | Gunicorn/Django startup, runtime configuration, or application failure |
| `/health/ready` fails | The service logs, then the `tailtag-postgres-dev` status in Render | Database connectivity, configuration, startup, or readiness failure |
| Render deploys but the smoke step fails | The `Render Development deploy` run | Public routing or the liveness, readiness, schema, or docs HTTP contract |
| A merge starts no deploy | The merge's changed files | Expected path filter. The workflow runs only for changes under `services/api/**`, so no API delivery follows |

Keep the boundaries distinct:

- GitHub `API foundation checks` owns pre-merge validation and the same-SHA
  post-merge checks that the `Render Development deploy` workflow waits for.
- Render owns image build, pre-deploy migration execution, application
  startup, and its `/health/ready` health check.
- The `Render Development deploy` workflow owns the wait for CI, the deploy
  hook call, the identity check, and `task api-smoke` against the public API.
  It does not migrate or roll back the service.

## Redeploy the current revision

Redeploy is the default recovery action when the current code is still correct
and the service needs a fresh deploy. It deploys the same code again. It is not
a database rollback.

Before redeploying:

1. Confirm the commit is the latest backend commit on `main` and is the
   intended revision.
2. Confirm the problem is not an unsafe or partially applied migration.
3. Review any variable change on the service and its expected effect.
4. Coordinate the action so another maintainer or delivery is not changing the
   same environment concurrently.

Redeploy through the `Render Development deploy` workflow. Run it with Run
workflow and enter the full 40-character SHA of the latest backend commit on
`main`, as in [Delivery](#delivery). Do not deploy from the Render dashboard,
because that skips the CI gate.

A redeploy is a new deploy attempt. Inspect the deploy and its log, make sure
that the pre-deploy step prints `PASS`, make sure that `/health/ready` passes,
and make sure that the workflow's smoke step passes. Do not treat the workflow
start as proof that delivery completed.

## Decide whether application-code rollback is a candidate

The authoritative V0 policy and Staging findings are the [#206 migration and
application rollback contract](../specs/2026-09-22-v0-migration-application-rollback.md).
This Development summary does not authorize a live action by itself.

Use an **Expand**, **Compatible**, **Contract** evolution: expand with
backward-compatible additions, operate through a compatible transition, then
contract only after the obsolete shape is no longer needed by a supported
application rollback. Prefer a reviewed forward fix. An application-image
rollback is exceptional, never a routine reverse migration or PostgreSQL
rollback.

Authorize an old application only after positive proof that the exact old
application works with the actual schema and persisted state left by the newer
application. Bind the old/current full source SHAs and exact deployment
identities; review the complete migration delta, actual schema and migration
history, new persisted state, and old reads/writes. Where practical, prove the
specific pair on disposable PostgreSQL: migrate current schema first, then run
the immutable old application against it without reverse migration. Missing,
ambiguous, or uncertain evidence is a NO-GO and requires a forward fix.

Do not assume an additive object is harmless, or that a Django default lets an
old write omit a new database requirement. Review constraints, nullability,
defaults, types, foreign keys, renames/removals, data migrations, `RunPython`,
`RunSQL`, state/database splits, and non-atomic or manual operations. Review
application invariants and persisted values as well as schema shape.

A Render rollback makes a new deploy from the build of an earlier deploy, and it
uses the variables of that earlier deploy. The pre-deploy command runs during a
rollback. The facts and the #410 drill are in
[Application rollback on Render](staging.md#application-rollback-on-render).
That drill ran on Staging. A rollback must name the exact earlier deploy and
must not assume that the latest deploy is the target. A future rehearsal must
follow the exact-deployment evidence procedure in the #206 contract.

## Handle migration failures

Render runs the guarded pre-deploy command `python -m config.replacement_migrate`
after it builds the new version and before the version takes traffic.
[Delivery](#delivery) lists its results.

A `FAIL_GUARD` or `FAIL_MIGRATION` result fails that deploy before the new
version takes traffic. The previous version keeps serving.

For a clean pre-deploy migration failure:

1. Inspect the failed deploy's log.
2. Identify the migration, configuration, or connectivity error.
3. Do not repeatedly deploy the same failure.
4. Correct it through the normal pull-request and CI path.
5. Let the `Render Development deploy` workflow deploy the corrected commit
   after the merge, and verify the complete delivery result.

If logs or database inspection suggest that a migration partially mutated
database state—especially through non-transactional operations—stop routine
retries. Inspect the specific migration and current database state, do not
automatically run reverse migrations, and escalate to the backend maintainer
and project owner. Decide explicitly whether a forward repair migration or a
carefully reviewed manual correction is safer. Django and Render do not
provide a universal recovery recipe for this case.

Application redeploy and rollback never imply PostgreSQL rollback. Reverse
migrations may be destructive, irreversible, or data-losing and require a
separate, migration-specific review.

## Runtime variables and secret safety

The `tailtag-api-dev` service's Environment page and the `render.yaml`
Blueprint are the authoritative runtime configuration. The Blueprint declares
each variable name. Secret values use `sync: false`, so they never live in the
file. Record names, references, and ownership, not rendered values. Private
media stays on Cloudflare R2.

### V0 private media storage rollout

This section is a historical record from Railway, before the Render move. It is not a current procedure. For the current media smoke, see [Smoke checks](#smoke-checks).

This repository does not create, change, rotate, or delete Cloudflare R2
buckets, credentials, or Railway variables. Those are explicit maintainer
operations at the established Cloudflare and Railway secret boundaries; do not
attempt them from repository startup, tests, CI, or local contributor setup.

Before merging the fail-closed media-storage change, an authorized maintainer
must complete this order for Railway `development`:

1. Create one dedicated **private** R2 development bucket. Do not use it as
   backup storage, a public asset origin, or a production bucket.
2. Create a bucket-scoped **Object Read & Write** credential restricted to that
   bucket. Do not grant account-wide, bucket-management, public-access, or
   unrelated-bucket scope.
3. In Railway `development` → `api` → **Variables**, stage all five values as
   secrets: `MEDIA_STORAGE_ENDPOINT_URL`, `MEDIA_STORAGE_BUCKET_NAME`,
   `MEDIA_STORAGE_REGION`, `MEDIA_STORAGE_ACCESS_KEY_ID`, and
   `MEDIA_STORAGE_SECRET_ACCESS_KEY`. Do not record rendered values in source,
   logs, tickets, reviews, screenshots, shell history, or chat.
4. Review and apply the staged variable names and intended ownership to Railway
   Development. Production settings fail closed when any required value is
   absent or an endpoint is not an HTTPS root URL; do not merge first and add
   these variables later.
5. Before merging, run the repository-owned live boundary check from the
   checked-out pull-request branch through Railway Development's `api` variable
   context:

   ```bash
   TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-development-media-storage-smoke \
   railway run --service api --environment development -- task api-media-storage-smoke
   ```

   This opt-in command is entirely separate from `task api-check` and ordinary
   CI. It fails closed unless the Railway identity is exactly
   `development`/`api`, the fixed confirmation value is present,
   `DJANGO_SETTINGS_MODULE=config.settings.production` is in use, and the
   configured storage is `S3MediaStorage`. It rejects a target identified as
   production. It uses only synthetic, in-memory canonical image bytes; no user
   data or repository fixture data is involved.

   The command uploads the synthetic object, confirms its existence, creates a
   600-second presigned GET, fetches and compares the canonical bytes, then
   deletes the object in a `finally` path and confirms its absence. A deletion
   error, absence-check error, or surviving object is a command failure, not a
   warning. The command itself never prints the object key, storage identifiers,
   bearer URL, credentials, request signatures, response material, or external
   error details.

   Record only this sanitized evidence after a successful run; do not include
   rendered variable values or other storage details:

   ```text
   command: task api-media-storage-smoke
   target: development/api
   branch/revision: <checked-out-branch> / <revision>
   stages: upload PASS; existence PASS; presigned-byte PASS; delete PASS
   cleanup/absence: PASS
   overall: PASS
   ```

   Record this successful result before retaining an automatic issue-close
   link on the pull request. If an external constraint makes pre-merge
   verification impossible, remove that link, merge the implementation, run
   the same smoke against the deployed revision, record the sanitized result,
   and close the issue manually afterward.

   The composed authenticated media-flow proof is now owned by the
   [Wave 2 participation validation](wave-2-participation-validation.md). Its
   live Railway Development execution completed successfully on 2026-09-08;
   the linked canonical record contains the sanitized evidence and rerun
   procedure.

The production storage backend creates only 600-second presigned `GET` URLs;
they are bearer credentials and must never be persisted or logged. There are
no presigned `PUT` URLs, direct-to-R2 uploads, public bucket URLs, or
repository-managed R2 provisioning.

### Media lifecycle and recovery boundary

For a replacement, the media boundary uploads the new object, commits the new
database reference, and then best-effort deletes the old object. If that commit
fails, it attempts compensating deletion of the new object but preserves the
original commit error. For optional removal, it commits the absent reference
before best-effort deletion of the old object. A failed post-commit deletion
may leave an orphan; do not restore a stale reference merely because cleanup
failed.

V0 intentionally has no scheduled garbage collection, bucket inventory
reconciliation, account/fursuit deletion workflow, or generalized asset
lifecycle service. Treat any orphan investigation or cleanup beyond the
best-effort boundary as separately approved work. An application-code
rollback does not restore or delete R2 objects, just as it does not restore
PostgreSQL state; assess references and objects independently before a rollback
or forward-recovery decision.

### Runtime variables

| Variable | Authority and handling |
| --- | --- |
| `DATABASE_URL` | The Blueprint supplies it from `tailtag-postgres-dev` (`fromDatabase`). Do not replace it with copied credentials or expose PostgreSQL publicly. The database allows no outside connections. |
| `DJANGO_SECRET_KEY` | Render generates it for the development API. Never copy it into source, documentation, or tickets. |
| `DJANGO_ALLOWED_HOSTS` | Development `api` requires exactly `tailtag-api-development.onrender.com`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Development `api` requires exactly `https://tailtag-api-development.onrender.com`. |
| `CLERK_AUTHENTICATION_ENABLED` | TailTag-owned Development authentication switch. The Blueprint sets exactly `true`. Do not enable it without the two complete verification inputs below. |
| `CLERK_JWT_KEY` | Clerk Development instance RSA JWKS Public Key used for offline verification. It is not a Clerk secret key, but manage it on the Environment page and do not copy its contents into source, issues, reviews, logs, or chat. |
| `CLERK_AUTHORIZED_PARTIES` | Development requires the ordered pair of the synthetic backend-tooling origin `http://localhost:3000` and its separately code-pinned hosted Clerk Account Portal origin, as defined by the [replacement amendment](../specs/2026-09-24-replacement-development-portal-auth.md). Never add the Render API destination or an unpinned origin. |
| `MEDIA_STORAGE_ENDPOINT_URL` | Private R2 S3-compatible HTTPS root endpoint for the Development bucket. Set it on the Environment page and never copy its rendered value into repository artifacts. |
| `MEDIA_STORAGE_BUCKET_NAME` | Dedicated private R2 Development bucket name. Set it on the Environment page and do not reuse a production or unrelated bucket. |
| `MEDIA_STORAGE_REGION` | S3-compatible region for the private Development bucket. The Blueprint sets `auto`. |
| `MEDIA_STORAGE_ACCESS_KEY_ID` | Minimum-scope private-bucket object credential identifier. Manage it only on the Environment page. |
| `MEDIA_STORAGE_SECRET_ACCESS_KEY` | Matching minimum-scope private-bucket object credential secret. Never display or record it. |
| `SENTRY_DSN` | Optional Sentry ingest credential for the Development and Staging Sentry project. When unset, the API runs without error reporting. Set it on the Environment page and never copy its value into repository artifacts, issues, or chat. See [backend logging and request correlation](../operations/backend-logging.md). |
| `SENTRY_TRACES_SAMPLE_RATE` | Optional Sentry tracing sample rate from `0` to `1`. When unset or empty, no transactions are sent. Any other value stops API startup. Development and Staging use `1.0` while traffic is low. It is configuration, not a secret. See [backend service signals](../operations/backend-service-signals.md). |
| `PORT` | The Blueprint sets `8000` for the container. Do not duplicate it as a TailTag-owned Django setting. |
| Other Render platform variables | Render owns them. Do not duplicate them by hand unless an approved design explicitly requires it. |

After the paired replacement Development deployment passes identity and readiness
checks, run `task api-replacement-auth-smoke` from the repository root with fresh
ordinary Clerk sessions for the replacement Development and Staging apps. The
command uses the locked backend environment and hidden token prompts. Require
both same-environment `/api/me/` checks and both cross-environment denials
before calling the replacement Development API usable. Never record the tokens.

`CLERK_SMOKE_USER_ID` and `TAILTAG_DEVELOPMENT_API_BASE_URL` are local
operator/tooling inputs, not Render runtime configuration. The Clerk
Development `sk_test_` credential is entered through the authenticated smoke
workflow's hidden interactive prompt and likewise must never be stored as a
Render variable. Configure all three runtime Clerk variables together so a
deployment cannot start with authentication enabled but incomplete verification
inputs.

Use Render references for service-to-service configuration, as the Blueprint
does for `DATABASE_URL`, so values are not copied between services.

For all operational work:

- never commit variable values;
- never paste `DATABASE_URL`, secret keys, tokens, credentials, or rendered
  secret values into GitHub issues, pull requests, documentation, or chat;
- redact secrets and personal data from screenshots and log excerpts;
- inspect the smallest diagnostic surface needed.

If a secret may have been exposed, stop sharing the material, notify the
project owner through the approved private channel, and rotate the affected
credential before resuming normal work.

## Related validation and design

- [Wave 2 participation validation](wave-2-participation-validation.md)
- [Wave 3 catching and collection validation](wave-3-catching-validation.md)
- [Main-to-Railway Development delivery specification (historical, Railway)](../specs/2026-08-16-main-to-railway-development-delivery.md)
- [Post-deploy HTTP smoke verification specification](../specs/2026-08-15-post-deploy-http-smoke-verification.md)
- [V0 media storage specification](../specs/2026-08-19-v0-media-storage.md)
