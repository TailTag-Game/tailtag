# Backend development delivery operations

This guide is the current maintainer runbook for the shared Railway backend
development environment. It explains how to classify delivery failures, find
sanitized diagnostics, and choose between redeploying, forward-fixing, and
considering an application-code rollback. It is not a production SRE runbook,
an incident-management process, or a production data-recovery plan.

Backend contributor setup and commands remain in the
[API README](../../services/api/README.md). Durable design and ownership live
in [architecture.md](../architecture.md), while historical validation evidence
remains in [`docs/reviews/`](../reviews/README.md).

## Environment boundary and access

Use these exact Railway targets:

| Item | Target |
| --- | --- |
| Workspace | `Finn the Panther's Projects` |
| Project | `TailTag` |
| Environment | `development` |
| API service | `api` |
| Database service | `Postgres` |
| Public API | `https://api-development-8fa7.up.railway.app` |

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

Railway project membership controls what a person may do. Railway defines
`Owner` as full project administration, `Editor` as able to deploy and change
project settings without destructive project/service deletion, and `Viewer` as
read-only without access to environment variables. Only maintainers with
authorized Railway edit access may change development runtime variables or
initiate recovery deployments. Other contributors should propose configuration
changes through normal project coordination; they should not receive copied
secret values. See Railway's current
[project-member roles](https://docs.railway.com/projects/project-members) for
the platform permission boundary.

Live, non-mutating Railway API inspection shows that the currently linked
maintainer account inherits workspace-level `ADMIN` access; Railway returns no
project-specific member assignments for `TailTag`. The same session can read
`api` deployment metadata and logs, and Railway reports that the latest
deployment can be redeployed. This is the observed access model, not a new
TailTag organizational role. Re-check current membership before relying on it
for a future operation.

## Find state and logs

Start in the Railway `TailTag` project, select the `development` environment,
then open the `api` service.

- **Deployment history:** open the service's **Deployments** tab. Select one
  deployment to see its state and deployment-specific output. Its **Build
  Logs** show image/build work; its deployment logs include the pre-deploy
  container and application startup/runtime output.
- **Observability:** the current `development` environment shows the
  unconfigured **Observe this environment** dashboard with options to add a
  block or start a dashboard. It does not currently show a configured dashboard
  or visible Log Explorer. Do not add Observability blocks solely for routine
  diagnosis; use deployment-specific logs or the CLI instead.
- **CLI:** use explicit service and environment selectors to avoid reading the
  wrong target. A deployment ID is optional for the latest applicable
  deployment and useful when correlating one failed attempt.

Before any CLI diagnostic or recovery command, verify the linked context:

```bash
railway status --json
```

Confirm that it reports workspace `Finn the Panther's Projects`, project
`TailTag`, environment `development`, and service `api`. Stop if any target
differs or is missing. The service and environment selectors in the commands
below only narrow the target within a project; they do not make a stale linked
project safe. Resolve the project link with a maintainer before continuing
rather than guessing a project ID or name.

```bash
railway deployment list --service api --environment development --json
railway logs --service api --environment development --build --lines 100 <deployment-id>
railway logs --service api --environment development --deployment --lines 100 <deployment-id>
railway logs --service api --environment development --lines 100 <deployment-id>
```

`railway logs` streams by default. A bounded `--lines` query is easier to
review and sanitize before sharing. Use `--latest` when the newest attempt
failed before becoming the most recent successful deployment.

Railway supports dashboard, Log Explorer, and CLI log access generally, as
described in its [logs reference](https://docs.railway.com/observability/logs),
but this guide records the interfaces currently available in TailTag. Adding an
Observability dashboard or log view is outside #79. Do not copy an entire log
indiscriminately. Share only the lines needed to explain the failure, after
applying the secret-safety rules below.

## Classify a failure

Symptoms identify the first place to inspect, not a guaranteed root cause.

| Symptom | First place to inspect | Common possibilities |
| --- | --- | --- |
| PR `API foundation checks` fails | The PR's GitHub Actions run | Formatting, lint, type, test, Django, schema, migration-drift, or Gunicorn validation |
| Railway remains `WAITING` | The same-SHA GitHub push workflow | Push CI is still running or failed; Railway is waiting on its check suite |
| Railway build fails | Selected deployment's Build Logs | Docker build, dependency resolution, or source/build configuration |
| Pre-deploy fails | Selected deployment's deployment logs, especially the pre-deploy container | Django migration, runtime configuration, or database connectivity |
| Application deployment fails or crashes | Selected deployment's deployment/runtime logs | Gunicorn/Django startup, runtime configuration, or application failure |
| `/health/ready` fails | `api` deployment logs, then `Postgres` service state and targeted CLI logs | Database connectivity, configuration, startup, or readiness failure |
| Railway succeeds but post-deploy smoke fails | The qualifying `Post-deploy development smoke` GitHub Actions run | Public routing or the liveness, readiness, schema, or docs HTTP contract |
| An irrelevant merge is `SKIPPED` with `No changes to watched files` | Exact-SHA Railway deployment record | Expected `services/api/**` watch-path behavior; no executable API delivery should follow |

Keep the boundaries distinct:

- GitHub `API foundation checks` owns pre-merge validation and the same-SHA
  post-merge check used by Railway Wait for CI.
- Railway owns image build, pre-deploy migration execution, application
  startup, and its `/health/ready` platform health check.
- The GitHub `Post-deploy development smoke` workflow observes a successful
  Railway deployment event and runs `make api-smoke` against the public API. It
  does not deploy, migrate, redeploy, or roll back the service.

## Redeploy the current revision

Redeploy is the default recovery action when the current code is still correct
and the service needs a fresh deployment, or when an authorized configuration
correction has been staged, reviewed, and applied. It deploys the same code
again. It is not a database rollback.

Before redeploying:

1. Confirm the selected deployment is the intended current revision.
2. Confirm the problem is not an unsafe or partially applied migration.
3. Review any Railway configuration changes and their expected effect. Do not
   assume redeploy commits an unreviewed staged change.
4. Coordinate the action so another maintainer or delivery is not changing the
   same environment concurrently.

In Railway, open `api` **→ Deployments**, find the intended deployment, open
its three-dot action menu, and choose **Redeploy**. For the latest deployment,
the CLI equivalent is below. Repeat the linked-context preflight immediately
before running it.

```bash
railway redeploy --service api --environment development
```

Keep the confirmation prompt; do not add `--yes` for routine interactive
recovery. The verified Railway CLI describes this command as redeploying the
latest deployment without uploading new code. Railway also documents
[redeploy](https://docs.railway.com/cli/redeploy) and the dashboard's
[deployment actions](https://docs.railway.com/deployments/deployment-actions).

A redeploy is a new deployment attempt. Inspect its deployment record and
logs, confirm the pre-deploy step completes, confirm `/health/ready`, and then
confirm the qualifying post-deploy smoke run. Do not treat the command's
successful submission as proof that delivery completed.

## Decide whether application-code rollback is a candidate

Railway rollback redeploys a previous successful application's image and its
custom variables. It does **not** restore PostgreSQL schema or data. The
existence of a **Rollback** control is not evidence that using it is safe.

Prefer a reviewed forward fix when any of these conditions apply:

- the failed or current release ran a migration that may not be compatible
  with the older application revision;
- old-code/current-schema compatibility is uncertain;
- the failure involves data transformation or a destructive migration;
- recovery would require reversing database state; or
- maintainers cannot confidently establish the compatibility boundary.

Application-code rollback may be considered only when all of these conditions
hold:

- the target previous application revision is known to work with the database
  schema as it exists now;
- no unsafe schema reversal is required;
- the problem is clearly in application code or runtime rather than database
  state;
- the relevant previous successful Railway deployment remains available; and
- maintainers are prepared to inspect the new attempt's pre-deploy lifecycle.

Railway exposes rollback from `api` **→ Deployments** through the three-dot
menu on an eligible previous deployment. Confirm the target revision and its
custom-variable snapshot before approving the action. The currently verified
Railway CLI has a latest-deployment `redeploy` command but no corresponding
rollback subcommand, so this guide does not prescribe a CLI rollback path.

Treat rollback as a new deployment attempt and inspect its pre-deploy logs.
TailTag has not intentionally exercised an application rollback solely for
this guide, so do not assume from documentation alone whether a particular
historical image's migration hook will be a no-op. Railway's
[deployment actions](https://docs.railway.com/deployments/deployment-actions)
describe image/custom-variable restoration, while its
[pre-deploy documentation](https://docs.railway.com/deployments/pre-deploy-command)
defines that hook as part of the deployment lifecycle before application
startup.

## Handle migration failures

The `api` service runs this Railway pre-deploy command after building the
candidate image and before promoting the application:

```text
python manage.py migrate --settings=config.settings.production --noinput
```

A non-zero exit fails that attempt before application promotion. Railway does
not automatically retry a failed pre-deploy command.

For a clean pre-deploy migration failure:

1. Inspect the failed attempt's deployment/pre-deploy logs.
2. Identify the migration, configuration, or connectivity error.
3. Do not repeatedly redeploy the same failure.
4. Correct it through the normal pull-request and CI path.
5. Redeploy the corrected revision and verify the complete delivery result.

If logs or database inspection suggest that a migration partially mutated
database state—especially through non-transactional operations—stop routine
retries. Inspect the specific migration and current database state, do not
automatically run reverse migrations, and escalate to the backend maintainer
and project owner. Decide explicitly whether a forward repair migration or a
carefully reviewed manual correction is safer. Django and Railway do not
provide a universal recovery recipe for this case.

Application redeploy and rollback never imply PostgreSQL rollback. Reverse
migrations may be destructive, irreversible, or data-losing and require a
separate, migration-specific review.

## Runtime variables and secret safety

Railway's `development` environment and `api` service configuration are the
authoritative runtime configuration. The service's **Variables** tab is the
management surface; edits are staged for review and deployment. Record names,
references, and ownership—not rendered values.

### V0 private media storage rollout

This repository does not create, change, rotate, or delete Cloudflare R2
buckets, credentials, or Railway variables. Those are explicit maintainer
operations at the established Cloudflare and Railway secret boundaries; do not
attempt them from repository startup, tests, CI, or local contributor setup.

Before merging the fail-closed media-storage change, an authorized maintainer
must complete this order for Railway `development`:

1. Create one dedicated **private** R2 development bucket. Do not use it as
   backup storage, a public asset origin, or a production bucket.
2. Create a bucket/object credential restricted to that bucket and only the
   object operations the API needs: write, read, and delete. Do not grant
   account-wide, bucket-management, public-access, or unrelated-bucket scope.
3. In Railway `development` → `api` → **Variables**, stage all five values as
   secrets: `MEDIA_STORAGE_ENDPOINT_URL`, `MEDIA_STORAGE_BUCKET_NAME`,
   `MEDIA_STORAGE_REGION`, `MEDIA_STORAGE_ACCESS_KEY_ID`, and
   `MEDIA_STORAGE_SECRET_ACCESS_KEY`. Do not record rendered values in source,
   logs, tickets, reviews, screenshots, shell history, or chat.
4. Review the staged variable names and intended ownership, then merge and
   deliver through the normal protected-`main` path. Production settings fail
   closed when any required value is absent or an endpoint is not an HTTPS root
   URL; do not merge first and add these variables later.
5. After the normal deployment and readiness verification, perform one
   authorized controlled write/read/delete exercise through the application
   media boundary against Railway Development. Confirm the created object can
   be written, read through the authorized application flow, and deleted. Do
   not preserve or share a credential, object key associated with a person, or
   presigned URL as evidence; record only sanitized pass/fail results and the
   deployment revision.

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
best-effort boundary as separately approved work. Railway application-code
rollback does not restore or delete R2 objects, just as it does not restore
PostgreSQL state; assess references and objects independently before a rollback
or forward-recovery decision.

| Variable | Authority and handling |
| --- | --- |
| `DATABASE_URL` | `api` uses a Railway reference to `Postgres.DATABASE_URL`. Do not replace it with copied credentials or expose PostgreSQL publicly. |
| `DJANGO_SECRET_KEY` | Railway-managed secret for the development API. Never copy it into source, documentation, or tickets. |
| `DJANGO_ALLOWED_HOSTS` | Railway `api` development configuration derived from the Railway development domain and required health-check host. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Railway `api` development configuration derived from the public development origin. |
| `CLERK_AUTHENTICATION_ENABLED` | TailTag-owned Development authentication switch. The validated Railway Development value is exactly `true`; do not enable it without the two complete verification inputs below. |
| `CLERK_JWT_KEY` | Clerk Development instance RSA JWKS Public Key used for offline verification. It is not a Clerk secret key, but manage it through Railway's staged variable boundary and do not copy its contents into source, issues, reviews, logs, or chat. |
| `CLERK_AUTHORIZED_PARTIES` | The validated Development contract is exactly `http://localhost:3000`, the synthetic backend-tooling origin. Do not add the Railway API destination or broaden this list without a separately approved authentication requirement. |
| `MEDIA_STORAGE_ENDPOINT_URL` | Private R2 S3-compatible HTTPS root endpoint for the Development bucket; stage as a Railway secret and never copy its rendered value into repository artifacts. |
| `MEDIA_STORAGE_BUCKET_NAME` | Dedicated private R2 Development bucket name; stage as a Railway secret and do not reuse a production or unrelated bucket. |
| `MEDIA_STORAGE_REGION` | S3-compatible region for the private Development bucket; stage it with the complete media configuration. |
| `MEDIA_STORAGE_ACCESS_KEY_ID` | Minimum-scope private-bucket object credential identifier; manage only through Railway's secret boundary. |
| `MEDIA_STORAGE_SECRET_ACCESS_KEY` | Matching minimum-scope private-bucket object credential secret; never display or record it. |
| `PORT` | Railway platform runtime configuration for the container; do not duplicate it as a TailTag-owned Django setting. |
| Other `RAILWAY_*` values | Platform-owned variables; do not manually duplicate them unless an approved design explicitly requires a user-configured Railway behavior variable. |

`CLERK_SMOKE_USER_ID` and `TAILTAG_DEVELOPMENT_API_BASE_URL` are local
operator/tooling inputs, not Railway API runtime configuration. The Clerk
Development `sk_test_` credential is entered through the authenticated smoke
workflow's hidden interactive prompt and likewise must never be stored as a
Railway variable. Configure all three runtime Clerk variables together so a
deployment cannot start with authentication enabled but incomplete verification
inputs.

Use Railway reference variables for service-to-service configuration so values
are not copied between services. Railway's
[variables documentation](https://docs.railway.com/variables) explains the
Variables tab, staged changes, and reference syntax.

For all operational work:

- never commit Railway variable values;
- never paste `DATABASE_URL`, secret keys, tokens, credentials, or rendered
  secret values into GitHub issues, pull requests, documentation, or chat;
- redact secrets and personal data from screenshots and log excerpts;
- inspect the smallest diagnostic surface needed; and
- do not run `railway variables` commands merely for routine diagnosis because
  they can print rendered secret values.

If a secret may have been exposed, stop sharing the material, notify the
project owner through the approved private channel, and rotate the affected
credential before resuming normal work.

## Related evidence and design

Use these records to understand why the current controls exist; keep detailed
historical evidence there rather than copying it into this runbook:

- [Railway development environment review](../reviews/2026-08-13-railway-development-environment.md)
- [Post-deploy HTTP smoke verification review](../reviews/2026-08-15-post-deploy-http-smoke-verification.md)
- [Main-to-Railway development delivery review](../reviews/2026-08-16-main-to-railway-development-delivery.md)
- [Railway Development authentication validation](../reviews/2026-08-18-railway-development-authentication-validation.md)
