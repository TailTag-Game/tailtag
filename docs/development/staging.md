# Staging runbook

This is the maintainer runbook for TailTag's persistent Railway **Staging**
backend: a controlled production-rehearsal target for maintainers with the
needed Railway, Clerk, and Cloudflare access. The replacement generation became
canonical during the 2026-09-24 rebuild. It is separate from the mutable
contributor/integration [Development runbook](backend-delivery-operations.md).
It covers the controlled promotion procedure below. It is not a production SRE
guide or a source of credentials.
For common backend incidents, follow the
[Staging first-response procedures](../operations/staging-first-response.md)
and their [#208 evidence matrix](v0-backend-operational-readiness-matrix.md).

## Supported target and boundary

Use only the code-pinned replacement Railway target below. Its temporary
`TailTag Rebuild` display name was changed to `TailTag`. The retired project
also used the `TailTag` name, so verify the project ID against the code-owned
replacement pin; a display name alone cannot select the target. Historical
retired-project receipts do not establish replacement readiness.

| Item | Value |
| --- | --- |
| Workspace | `Finn the Panther's Projects` |
| Project / environment | Replacement project (currently displayed as `TailTag`) / `staging` |
| Services | `api`, `Postgres` |
| Canonical public API | `https://staging.tailtag.app` |

The sanitized [replacement canonical handoff receipt](staging-deployments/c34c45bb-6eb8-488d-8114-d1dd931cf25e.json)
records source `fc1376e9b4387cb46e37ef3f60191b2ce7f06c68`, deployment
`c34c45bb-6eb8-488d-8114-d1dd931cf25e`, and a successful public/exact-instance
join observed on 2026-09-25. It is a point-in-time target receipt, not proof of
the current active deployment or of the new database, #204 baseline, operator
roles, or restore state. The subsequent
[replacement prerequisite readback](staging-replacement-prerequisite-attempt-2026-09-25.md)
did not establish database facts; #204 sentinel, fixtures, operator inspection,
and #243 cases 1–9 remain unverified on this generation.

The later [single guarded promotion receipt](staging-deployments/2adc748c-ee54-4446-958c-f49a384925be.json)
records source `99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be` as `SUCCEEDED` and `ACTIVE` on
2026-09-25. Fresh canonical public and exact-instance readback matched that
tuple afterward. This receipt supersedes the handoff receipt for current
deployment identification; it does not establish #204 or #243 readiness.

**Command boundary:** use the #202 promotion command below only from a reviewed
repository revision that includes the [replacement target binding
contract](replacement-staging-promotion-contract.md). It loads the owner-only
replacement manifest and checks its code-owned pins before provider operations.
Older revisions with retired-project selectors are historical and must not be
used against the replacement project. Do not substitute a project ID or reuse old
private configuration to make an old command address the replacement.

Staging owns its Railway environment instances, PostgreSQL service and volume,
runtime configuration and secrets, and public API networking. The API reaches
its database through the environment-local `Postgres` reference; never copy or
record a rendered database URL. Its private R2 bucket is Staging-owned, with a
single-bucket Object Read & Write credential. The
R2 account endpoint may be shared platform infrastructure; the bucket and
credential must not be.

`TailTag Staging Replacement` is a separate Clerk application using its
dedicated Production instance, not Development's Clerk application or instance. The
current hosted Account Portal origin,
`https://accounts.staging.tailtag.app`, is authorized only for the bootstrap
authentication validation described here. It is deliberately replaceable when
real V0 client integration establishes its own semantics; it is not a permanent
mobile/client architecture decision. The
[#219 amendment](../specs/2026-10-02-synthetic-identity-pool.md) adds a second,
ordered authorized party, `https://simulator.staging.tailtag.app`, used only by
the simulator identity pool. Removing it disables simulator tokens without
affecting the portal origin.

Use only synthetic TailTag records, Clerk users, and media. Do not use personal
data, production data, or ordinary user accounts. Development remains the
mutable contributor/integration environment. TailTag has no Production
environment, deployment target, or production data.

## Retired-generation bootstrap and deployment history

The one-time bootstrap for the former `TailTag` project is complete. Staging
GitHub autodeploy is disabled while
the `main` source connection remains. Reviewed Staging configuration was
committed with deployment suppressed; after the Staging-only volume wipe, the
previously stopped PostgreSQL instance used its existing image path once, and
`staging/api` used the existing **Deploy the repo TailTag-Game/tailtag** entry
point once. The dated 2026-09-16 observation records bootstrap `main` commit
`4293d271ce1ab262b688c5b723a119aa02c232b7`; it is an observation only, not an
immutable-artifact guarantee or #201 build identity.

Do not repeat or generalize that bootstrap into a routine. Bootstrap itself
establishes neither #201 immutable build identity nor #202 repeatable promotion.
Use the separate identity and controlled-promotion procedures below. No reset/
reseed process, observability system, recovery drill or health behavior is added.

The original CLI duplication unexpectedly deployed inherited configuration
before review. Those deployments were stopped, configuration was replaced while
offline, and the Staging volume was wiped before the supported bootstrap. That
initial interval is not proof of isolation and is not asserted to be free of
prior exposure. The current reviewed isolated bootstrap and the evidence below
are the usable proof.

## Controlled Staging promotion (#202)

Retired on 2026-10-30. `staging.tailtag.app` serves Render Staging, so use the
[Render Staging promotion](#render-staging-promotion-409). Do not run the
Railway command below again. Railway Staging stays as a frozen rollback target
until #412.

The frozen [controlled promotion contract](../specs/2026-09-16-controlled-staging-promotion.md)
is authoritative. This is the only routine Staging promotion path. It uses
Railway `serviceInstanceDeployV2` with an explicit immutable candidate SHA and
captures the returned deployment ID. Staging GitHub autodeploy stays disabled.
Do not use `railway up`, Deploy Latest Commit, branch mutation or a deployment
branch. Development retains its existing independent delivery path.

### Before promotion

Coordinate a maintainer operation window: no concurrent Staging configuration
changes or unrelated pending staged changes. Review the canonical target and
current configuration in Railway without exporting variables. Stop on a mismatch;
do not repair configuration or authentication as part of promotion. Only an
operator authorized for the canonical Staging/API target may run this command.

Use a reviewed full commit SHA from accepted `TailTag-Game/tailtag` main history,
containing the #201 identity implementation. It may be an older ancestor: main
can advance after selection. It must resolve in the repository and have a
completed successful push run of `.github/workflows/api.yml` with exactly the
same head SHA. A successful PR run or workflow dispatch does not qualify.
The operator checks remote ancestry and exact push validation; it does not use
local branch state or duplicate backend relevance logic.

Verify approved Finn GitHub/Railway identities; the command repeats the required
checks. An identity mismatch, failed identity lookup, authentication/access
failure or failed authenticated operation ends the task. Do not switch accounts,
repair credentials, use another session or retry the failure.

Before invoking the command on the replacement generation, require the
reviewed replacement binding in the common baseline and the private
`~/.config/tailtag/staging-clean-rebuild-targets.json` manifest with its established file
ownership and mode. The command checks the replacement `staging` API selectors
against code-owned pins and fails closed when the manifest is unavailable or
mismatched. It does not accept target selectors from arguments or environment
variables. The retired-generation receipts below cannot authorize a new
replacement deployment.

The replacement API uses the guarded
`python -m config.replacement_migrate` Railway pre-deploy command established
by the [replacement launch contract](../specs/2026-09-24-replacement-api-launch.md).
The retired direct `manage.py migrate` command is not a valid replacement
pre-deploy setting. A mismatch stops promotion before submission.

From the repository root, with existing locked dependencies installed:

```bash
SOURCE_SHA='replace-with-reviewed-full-40-character-main-ancestor-SHA'
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_promote.py \
  --source-sha "$SOURCE_SHA" --confirm promote-tailtag-staging
```

The confirmation authorizes this one exact-SHA Staging submission, not recovery
or configuration changes. The command is opt-in and is never invoked by ordinary
CI, `task api-check`, application startup or a health check.

### Expected operation and evidence

After eligibility and target/configuration checks, the command submits S once
and immediately checkpoints returned D at
`docs/development/staging-deployments/<D>.json`. Every subsequent lifecycle/event
lookup is for D. It observes the existing pre-deploy migration, startup and
readiness gates, reads image identity on an explicitly selected RUNNING instance
of D, reuses #201's exact-deployment join, and checks image source equals S.
Then it runs the existing canonical credential-free HTTP smoke and checks the
Staging/API active-deployment set immediately before declaring success.

A zero exit is current-promotion success only when all required outcomes
succeeded and exact D was still active at declaration. The evidence includes
source SHA, D, Staging environment, exact Railway createdAt timestamp, accepted
main SHA, validation run/attempt, deployment/migration/startup/readiness/identity/
smoke outcomes, final active state and overall result. Only fixed outcome codes
and allowlisted public identities are retained; no raw CLI output, metadata,
event errors, environment values, private URLs or logs.

| Result | Operator action |
| --- | --- |
| Candidate/target/configuration rejected before submission | Stop; there is no returned D and no deployment was intentionally submitted. Correct the prerequisite through its normal owning process. |
| PENDING record with progressing deployment | The command observes successful exact-D reads every five seconds, for up to 20 minutes. Do not start a second promotion. |
| SUCCEEDED / ACTIVE | Review and retain the sanitized record. This is a point-in-time success claim; subsequent deployments may change current state. |
| SUPERSEDED | Keep valid historical D evidence; do not report successful current promotion. No automatic resubmission. |
| INACTIVE | D is not active and no replacement is observed. Ordinary promotion did not succeed. |
| FAILED | Stop ordinary promotion at the first failed gate. Inspect the safe exact-D owning surface before any separately approved next operation. |
| INDETERMINATE or interrupted PENDING | The command cannot establish complete evidence. Do not assume failure was clean, success occurred, or that submission did not happen. Preserve known S/D and inspect exact D. |
| OR7_HANDOFF | Ambiguous migration/database state requires OR-7's reviewed recovery decision. This procedure performs no recovery. |

A lost mutation response can mean Railway accepted a deployment although D was
not received. Stop; do not resubmit or discover a substitute through "latest."
If checkpoint persistence fails after D is returned, preserve only the emitted
safe S/D identifiers in the repository evidence location and stop. Review any
interrupted record before committing it; never convert it to success based on
a later shared-URL response alone.

### Safe first diagnostics and recovery boundary

Start with the captured D's status, target fields, instances and paginated
lifecycle events. PRE_DEPLOY_COMMAND is the Django migration gate;
MIGRATE_VOLUMES is not. A completed event alone is insufficient to prove success.
Error/skip/conflicting or missing evidence must not be treated as a passed gate.
NOT_REACHED requires affirmative evidence that the attempt stopped before the
step; absence alone is indeterminate.

For a failed gate, inspect only D's relevant Railway build/pre-deploy/deployment
surface. Do not export general metadata, variables, private URLs, screenshots
or indiscriminate logs. Record only sanitized fixed outcomes. A migration error
does not prove database state was unchanged; ambiguous/partial state hands off
to OR-7. This flow never automatically retries, reverses migrations, rolls back
application/database state, restores data or deliberately terminates services.

The smoke checks the shared public endpoint and does not attest the serving
image per response. Exact-instance SSH plus the #201 join establishes D's image
identity; final active membership bounds the current-serving claim. Detailed
readiness semantics belong to OR-4 and migration/recovery semantics to OR-7.

## Render Staging promotion (#409)

[ADR 0011](../adrs/0011-move-v0-hosting-from-railway-to-render.md) moves
Staging to Render. `scripts/api_staging_render_promote.py` is the only
routine path that deploys Render Staging. It keeps every gate of the
[#202 contract](../specs/2026-09-16-controlled-staging-promotion.md). The
[promotion contract](replacement-staging-promotion-contract.md#render-staging-identity-409)
says how Render proves the deploy identity. The Railway procedure above stays
until #412. After `staging.tailtag.app` moves to Render, the Railway
promotion command is retired, and nobody runs it again.

### Before a Render promotion

You need these items:

- A Render API key. Create it in the Render dashboard under
  **Account Settings > API Keys > Create API key**. If Render offers scoped
  keys, select the TailTag workspace and grant Services Read, and Deploys Read
  and Run. Keep the key only in your password manager. The command asks for
  it at a hidden prompt for each run.
- The key `render_staging_api_service_id` in the owner-only
  `~/.config/tailtag/staging-clean-rebuild-targets.json` manifest. Its value
  is the `srv-…` part of the `tailtag-api-staging` dashboard URL. The command
  accepts only the ID that matches the code-owned #407 pin. It never reads the
  target from an argument or an environment variable.
- A reviewed full commit SHA S. The #202 eligibility rules apply without
  change: S is an accepted `main` ancestor with a successful `api.yml` push
  run.
- The approved Finn GitHub identity. The command checks it.

Scoped keys are in early access. Without them, Render creates a classic key.
A classic key can do anything your account can do in every workspace. To
limit that exposure, you can revoke the key after each promotion session and
create a new one next time.

From the repository root, run:

```bash
SOURCE_SHA='replace-with-reviewed-full-40-character-main-ancestor-SHA'
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_render_promote.py \
  --source-sha "$SOURCE_SHA" --confirm promote-tailtag-render-staging
```

### What the Render command checks

Before submission, the command stops if one of these checks fails:

- The service settings from the Render API: the name `tailtag-api-staging`,
  this repository, branch `main`, auto-deploy `off`, a Docker web service that
  is not suspended, `/health/ready`, and the pre-deploy command
  `python -m config.replacement_migrate`.
- The workspace: among the workspaces that the key sees, exactly one owns the
  service, and it is a team workspace. A classic key can also see other
  workspaces.
- An idle service: no Staging deploy is in progress. Render runs one deploy at
  a time, and a queued deploy can be skipped.

Then the command submits S once with `commitId`. It saves the returned
`dep-…` ID D at `docs/development/staging-deployments/<D>.json` before it
watches the deploy. It reads D every 10 seconds, for up to 30 minutes.

| Render status of D | Receipt outcome |
| --- | --- |
| `live` with commit S | Deployment, migration, startup, and readiness SUCCEEDED. |
| `pre_deploy_failed` | Migration FAILED. The overall result is `OR7_HANDOFF`. |
| `build_failed`, `canceled`, or `deactivated` before `live` | Deployment FAILED. |
| `update_failed` | Readiness FAILED. Startup is INDETERMINATE. |
| Any other status, or a timeout | INDETERMINATE. |

After D is `live`, the command reads `/health/identity` and `/health/ready`
on the public Render Staging origin. The identity must show S, `staging`, and
`deployment_id: null`. Render keeps the old instance serving for a while after
a deploy goes live, so the identity can still show the old SHA. The command
reads again every 5 seconds, for up to 5 minutes. Then it runs `task api-smoke` against the same origin.
Last, D must still be `live`. If another deploy is `live`, the result is
SUPERSEDED. If no deploy is `live`, the result is INACTIVE.

The old instance can still run for about a minute after the promotion
passes. While it runs, Render lists two instances. The #410 job and
`render ssh` launchers need exactly one, so they stop at `FAIL ... target`
and change nothing. Wait a minute after a promotion before you run them.

The result table in [Expected operation and evidence](#expected-operation-and-evidence)
applies to the Render receipts too. A 202 response or a missing deploy ID
means that the command has no D. Stop, and do not submit again. Check the
Render dashboard for a deploy of S first.

A `FAIL_GUARD` pre-deploy failure means that a check failed before any
migration ran. The previous version keeps serving. The first Render Staging
promotion ran before the database pin landed and failed this way
(`dep-dbiedi6c6qcc73a9a120`, the AC3 proof of #409).

To read the pre-deploy result of a deploy, run `render logs` with the Staging
service ID and the deploy time window, then look for the `PASS`, `FAIL_GUARD`,
or `FAIL_MIGRATION` line:

```bash
render logs -r "$RENDER_SERVICE_ID" --start 2026-10-30T18:49:00Z \
  --end 2026-10-30T19:00:00Z --direction forward --limit 500 -o text
```

### Deploys outside the promotion

A Blueprint sync or a variable change that deploys Render Staging is an
uncontrolled deploy. A Blueprint sync deploys the latest `main` commit, even
with auto-deploy off. After such a deploy, promote the intended SHA with this
command before any Staging proof counts.

### Render Staging smoke checks

Run the credential-free preflight:

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_preflight.py --render-staging
```

Render has no command that copies service variables into a local process. So
the authenticated and media smokes run locally. Copy each value from the
`tailtag-api-staging` **Environment** page. Run each block in zsh, the default
macOS shell, like the other blocks on this page.

The smoke verifies the session token with the API's own verifier, which loads
the production settings. On Railway, `railway run` supplied every service
variable. Here the block sets the Clerk values and harmless placeholders for
the other required settings. The smoke does not connect to the database or to
media storage.

The Clerk JWT public key is not a secret, and it has several lines. Paste the
whole PEM block at the prompt. Make sure that the cursor is on an empty line
after `-----END PUBLIC KEY-----`, then press Ctrl-D once.

```zsh
read -rs 'CLERK_STAGING_SMOKE_USER_ID?Synthetic Clerk user ID: '
print
read -r 'RENDER_SERVICE_ID?Render Staging service ID: '
print 'Paste CLERK_JWT_KEY, then press Ctrl-D on an empty line:'
CLERK_JWT_KEY="$(cat)"
export CLERK_STAGING_SMOKE_USER_ID RENDER_SERVICE_ID CLERK_JWT_KEY
RENDER=true CLERK_AUTHENTICATION_ENABLED=true \
CLERK_AUTHORIZED_PARTIES=https://accounts.staging.tailtag.app \
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY=local-auth-smoke-placeholder \
DJANGO_ALLOWED_HOSTS=localhost DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
DATABASE_URL=postgresql://placeholder:placeholder@localhost:5432/placeholder \
MEDIA_STORAGE_ENDPOINT_URL=https://media.example.test \
MEDIA_STORAGE_BUCKET_NAME=placeholder MEDIA_STORAGE_REGION=auto \
MEDIA_STORAGE_ACCESS_KEY_ID=placeholder MEDIA_STORAGE_SECRET_ACCESS_KEY=placeholder \
TAILTAG_STAGING_AUTH_SMOKE_CONFIRM=run-clerk-render-staging-auth-smoke \
API_BASE_URL=https://staging.tailtag.app \
TAILTAG_STAGING_API_BASE_URL=https://staging.tailtag.app \
task api-staging-auth-smoke
unset CLERK_STAGING_SMOKE_USER_ID RENDER_SERVICE_ID CLERK_JWT_KEY
```

```zsh
read -rs 'MEDIA_STORAGE_ENDPOINT_URL?MEDIA_STORAGE_ENDPOINT_URL: '; print
read -rs 'MEDIA_STORAGE_BUCKET_NAME?MEDIA_STORAGE_BUCKET_NAME: '; print
read -rs 'MEDIA_STORAGE_ACCESS_KEY_ID?MEDIA_STORAGE_ACCESS_KEY_ID: '; print
read -rs 'MEDIA_STORAGE_SECRET_ACCESS_KEY?MEDIA_STORAGE_SECRET_ACCESS_KEY: '; print
read -r 'RENDER_SERVICE_ID?Render Staging service ID: '
export MEDIA_STORAGE_ENDPOINT_URL MEDIA_STORAGE_BUCKET_NAME \
  MEDIA_STORAGE_ACCESS_KEY_ID MEDIA_STORAGE_SECRET_ACCESS_KEY RENDER_SERVICE_ID
RENDER=true MEDIA_STORAGE_REGION=auto \
DJANGO_SECRET_KEY=local-media-smoke-placeholder \
DJANGO_ALLOWED_HOSTS=localhost DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost \
DATABASE_URL=postgresql://placeholder:placeholder@localhost:5432/placeholder \
TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-render-staging-media-storage-smoke \
task api-media-storage-smoke
unset MEDIA_STORAGE_ENDPOINT_URL MEDIA_STORAGE_BUCKET_NAME \
  MEDIA_STORAGE_ACCESS_KEY_ID MEDIA_STORAGE_SECRET_ACCESS_KEY RENDER_SERVICE_ID
```

Each smoke fails unless the service ID matches the pinned Render Staging
service and the confirmation names Render Staging. Since the 2026-10-30
switch, the public origin is `https://staging.tailtag.app`. Before the switch,
it was `https://tailtag-api-staging.onrender.com`.

### Move staging.tailtag.app to Render

The owner approved the switch on 2026-10-30, and #409 records the date. Run
the steps in this order:

1. Merge the cutover change. It sets the Render Staging phase to `canonical`.
2. On the `tailtag-api-staging` **Environment** page, set
   `DJANGO_ALLOWED_HOSTS` to
   `staging.tailtag.app,tailtag-api-staging.onrender.com`. Set
   `DJANGO_CSRF_TRUSTED_ORIGINS` to `https://staging.tailtag.app`. Choose
   **Save only**, so that no deploy starts with a half-changed profile.
3. Run the Blueprint sync. It deploys the latest `main` commit with the new
   phase. Do not promote yet. In the `canonical` phase, the promotion checks
   `https://staging.tailtag.app`, and that name still points to Railway.
4. Under **Settings > Custom Domains**, add `staging.tailtag.app`.
5. In Porkbun, point the `staging` CNAME record to
   `tailtag-api-staging.onrender.com`. Remove any AAAA record for the name.
6. In Render, verify the domain. Wait for the certificate.
7. Promote the intended SHA. The sync deploy in step 3 is uncontrolled, so
   this receipt is the first one that counts.
8. Run the preflight and the authenticated smoke against
   `https://staging.tailtag.app`.

Render health checks send the `onrender.com` host until the domain is
verified, and the custom domain after it. So in the `canonical` phase,
readiness on Render allows exactly these two hosts. Keep the Render subdomain
on.

After the switch, Railway Staging stays as the rollback target until #412.
Do not promote, reset, or run the simulator against Railway Staging. To roll
back, point the Porkbun `staging` CNAME back to its Railway target. Railway
still holds its custom domain and its `canonical` settings.

## Render Staging operations and recovery (#410)

This section covers the #204 reset, the #243 operator commands, database
recovery, and application rollback on Render Staging. The Railway procedures
in this runbook stay until #412. Do not run them against Render Staging.

### Which method each command uses

A one-off job is a short task that Render runs on its own instance from the
live image. A command that prompts needs a terminal, so it runs over
`render ssh` instead.

| Operation | Method | Launcher arguments |
| --- | --- | --- |
| Sentinel provision | Job | `api_staging_render_job.py provision --confirm provision-tailtag-staging-reset` |
| Reset, reseed, and baseline provision | Job | `api_staging_render_job.py reset --confirm reset-tailtag-staging` |
| Registry reconcile | Read-only job | `api_staging_render_job.py reconcile` |
| Operator inspect | Read-only job | `api_staging_render_job.py inspect` |
| Emergency operator state | Read-only job | `api_staging_render_job.py emergency-state` |
| Row counts for a PITR drill | Read-only job | `api_staging_render_job.py row-counts` |
| Managed operator create | `render ssh` | `api_staging_render_ssh.py managed-create` |
| Limited operator provision | `render ssh` | `api_staging_render_ssh.py lifecycle-provision` |
| Limited operator password rotation | `render ssh` | `api_staging_render_ssh.py lifecycle-rotate-password` |
| Limited operator decommission | `render ssh` | `api_staging_render_ssh.py lifecycle-decommission` |
| Managed operator password rotation | `render ssh` | `api_staging_render_ssh.py managed-password-rotate` |
| Managed operator replace | `render ssh` | `api_staging_render_ssh.py managed-operator-replace` |
| Emergency operator create | `render ssh` | `api_staging_render_ssh.py emergency-create` |
| Emergency operator decommission | `render ssh` | `api_staging_render_ssh.py emergency-decommission` |
| PITR restore count | `render ssh` | `api_staging_render_ssh.py restore-count --expected-counts <digest>` |

These tools have no Render version, and #412 deletes them: the #243 matrix,
restart, and managed-auth diagnosis tools, and the #207 logical-dump drill.

### Before a Render operation

You need these items:

- The Render API key and the manifest key `render_staging_api_service_id`
  from [Before a Render promotion](#before-a-render-promotion).
- A `SUCCEEDED` receipt for the live deploy in
  `docs/development/staging-deployments/` in your checkout. The promotion
  command writes it there.
- For `render ssh`: the Render CLI signed in as Finn the Panther. The
  launcher checks `render whoami` before and after its checks.

Wait one minute after a promotion, so that the old instance stops. Run every
launcher from the repository root in your own terminal, because each one asks
for the API key at a hidden prompt. While a launcher waits, it prints progress
lines that start with `...` on stderr. Make sure that nothing else changes
Staging while a launcher runs.

### One-off jobs

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_render_job.py inspect
```

Replace `inspect` with the operation from the table above. The reset and the
sentinel provision also need their exact `--confirm` value.

The launcher checks the workspace, the one live deploy and its receipt, the
public identity, and the one running instance. Then it starts exactly one job
of the live commit. It reads the one `TAILTAG-RENDER-JOB` result line from the
Render Logs API and prints it. After the job, it waits up to 5 minutes until
Staging serves the same deploy again. It exits 0 only for a `PASS` result. It
never retries or cancels a job, because a reset can stop between its gate and
its resume.

The read-only jobs run in a read-only database transaction. A reconcile
`MISMATCH` exits 1, which is stricter than the Railway command.

| Output | Meaning | Next step |
| --- | --- | --- |
| `FAIL render job confirmation` | The operation or its `--confirm` value is wrong. | Nothing ran. Fix the command. |
| `FAIL render job target` | A target check failed before the job. | Nothing ran. After a promotion, wait one minute and run it again. |
| `FAIL render job submission indeterminate` | The launcher cannot tell if Render started a job. | Look for a new job in the service logs before you run anything again. |
| `FAIL render job indeterminate <job>` | The job started, but its result is not proven. | For a reset, follow [Reset recovery on Render](#reset-recovery-on-render). Otherwise run `inspect`. |
| `FAIL render job target changed <job>` | The job ended, but Staging serves another deploy. | Run the preflight. Promote the intended SHA before more work. |
| A `TAILTAG-RENDER-JOB` line with `"outcome": "FAIL"` | The job ran and failed. | Read its `phase` or `result`. |

### The reset on Render

The reset closes the Staging database with `ALLOW_CONNECTIONS false`, resets
and reseeds it, then opens it again. While the database is closed, the web
service fails its health checks, and Render restarts it after 60 seconds. The
job runs on its own instance, so that restart does not stop the reset.

A deploy cannot go live while the database is closed. Its pre-deploy
migration needs the database. A dashboard rollback also runs the pre-deploy
command, so a rollback cannot go live either. Still, do not start a
promotion, rollback, Blueprint sync, or variable change during a reset.

The Render reset has one limit that the Railway reset does not. The Railway
reset reads the public identity again after it opens the database, and it
closes the database again if the identity changed. The Render job cannot do
this, because `scripts/` is not in the image. So if the target changed, the
launcher exits 1 with `target changed <job>`, and Staging stays open. The
owner accepted this limit on 2026-10-31.

### Reset recovery on Render

Use this procedure when a reset reports `maintenance unknown`,
`maintenance retained`, or `committed maintenance retained`. Also use it for
`indeterminate` after a reset. A retained gate is an intentional outage.

1. Do not run the reset again. Do not start a deploy.
2. In the Render dashboard, open `tailtag-api-staging`, then **Shell**.
3. Read the connection flag from the `postgres` database:

   ```bash
   python - <<'PY'
   import os
   import psycopg
   from psycopg.conninfo import conninfo_to_dict

   url = os.environ["DATABASE_URL"]
   target = conninfo_to_dict(url)["dbname"]
   with psycopg.connect(url, dbname="postgres", autocommit=True) as control:
       row = control.execute(
           "SELECT datallowconn FROM pg_database WHERE datname = %s", (target,)
       ).fetchone()
       print("allow_connections", row[0])
   PY
   ```

4. If it prints `allow_connections False`, open the database as its owner:

   ```bash
   python - <<'PY'
   import os
   import psycopg
   from psycopg import sql
   from psycopg.conninfo import conninfo_to_dict

   url = os.environ["DATABASE_URL"]
   target = conninfo_to_dict(url)["dbname"]
   with psycopg.connect(url, dbname="postgres", autocommit=True) as control:
       control.execute(
           sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS true").format(
               sql.Identifier(target)
           )
       )
       row = control.execute(
           "SELECT datallowconn FROM pg_database WHERE datname = %s", (target,)
       ).fetchone()
       print("allow_connections", row[0])
   PY
   ```

5. Make sure that it prints `allow_connections True`. Then run
   `api_staging_preflight.py --render-staging`, and the `inspect` and
   `reconcile` jobs.
6. A phase that starts with `committed` means that the reset changed the
   data. The other phases mean that the data did not change. Before the next
   rehearsal, make sure that `inspect` and `reconcile` pass.

The executor owns the Staging database and is not a superuser. The #410 AC3
probe showed that this role can connect to `postgres` and run the
`ALTER DATABASE` statement. If the Shell cannot open, or a statement fails,
stop and ask for a new plan. Do not restart the database or delete a service.

### Operator commands over render ssh

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_render_ssh.py managed-create
```

Replace `managed-create` with the operation from the table above. The
launcher checks the terminal and `render whoami`. Then it makes the same
target checks as a job, and it finds the exact instance ID. It runs the
read-only jobs that prove the state the command needs. It checks the target,
the instance, and `render whoami` again. Then it opens one session on that
instance:

```text
render ssh <instance> -o text -- -o UpdateHostKeys=no -t "<in-image command>"
```

In the session, `accounts.render_operator` binds the runtime and the build,
then runs the command. Each command asks for its own Render phrase:

| Operation | Phrase |
| --- | --- |
| `managed-create` | `bootstrap Render Staging operator` |
| `lifecycle-provision` | `provision Render Staging validation operator` |
| `lifecycle-rotate-password` | `rotate Render Staging validation operator password` |
| `lifecycle-decommission` | `Y` |
| `managed-password-rotate` | `rotate Render Staging managed operator password` |
| `managed-operator-replace` | `replace Render Staging managed operator` |
| `emergency-create` | `bootstrap Render Staging emergency operator` |
| `emergency-decommission` | `Y` at `Decommission the Render Staging emergency operator? [Y/N]:` |

The session ends with `TAILTAG-RENDER-OPERATOR PASS <operation>` or a `FAIL`
line. After the session, the launcher waits for the same deploy and runs the
read-only jobs again. The last line is `PASS render ssh <operation>` or
`FAIL render ssh <operation> <phase>`.

| Phase | Meaning | Next step |
| --- | --- | --- |
| `terminal` | The launcher has no terminal. | Run it in your own terminal. |
| `target` | A target check failed. | Nothing ran. After a promotion, wait one minute. |
| `precondition <job>` | Staging is not in the state that the command needs. | Nothing ran. Read the `inspect` and `reconcile` results. |
| `session uncertain` | The session did not exit 0. | The command can have committed. Run `inspect` before any retry. |
| `target changed` | Staging serves another deploy after the session. | Run the preflight and `inspect`. |
| `postcondition <job>` | The new state is not the expected one. | Run `inspect`. |

The Render CLI passes the exit status of the session on. A wrong phrase gave
`session uncertain` in the live #410 run, which proved this. No read-only job
can see a new password or a replaced login. So for
`lifecycle-rotate-password`, `managed-password-rotate`, and
`managed-operator-replace`, PASS rests on the session exit status. The jobs
after those sessions show only that the roles stay valid.

`lifecycle-decommission` cannot be undone on Staging. The inactive User and
group block a new provision, and `inspect` then reports
`FAIL_LIMITED_OPERATOR_STATE`. The live #410 run skipped it for this reason.

### Restore the database with PITR

The Render recovery path for the Staging database is a point-in-time recovery
(PITR) into a new database. The #207 logical-dump drill has no Render version.
Render starts a PITR only from the dashboard, so no job or command starts it.

Render facts, from the
[Render backup docs](https://render.com/docs/postgresql-backups):

- The restore starts from the database's **Recovery** page and makes a new
  database. The source database does not change.
- The dashboard does not accept a restore time within 10 minutes of now.
- The new database copies the IP allowlist of the source.
- **Customize Recovery** sets the plan, the project, and the environment.

Keep the new database in the Staging environment. Staging has network
isolation, so `tailtag-api-staging` reaches only databases in its own
environment by their internal URL.

To practice a restore and check it:

1. Start a quiet window. Make sure that nothing writes to Staging until the
   restore starts.
2. Run the `row-counts` job. Its result line holds the count of every
   `public` table, the `counts_sha256` digest, and `captured_at`, the time T
   in UTC.
3. At least 10 minutes later, open **Recovery** on `tailtag-postgres-staging`,
   then **Restore Database**. Choose the first time that the dashboard accepts
   at or after T. In **Customize Recovery**, choose the cheapest plan and the
   smallest size, the TailTag project, and the Staging environment.
4. When the new database is available, check its allowlist with
   `render pg get <name> -o json | jq -c '.data | {name, status, ipAllowList}'`.
   If the list is not `[]`, run `render pg update <name> --clear-ip-allow-list`.
5. Copy the internal URL of the new database from **Connect > Internal**.
6. Run `api_staging_render_ssh.py restore-count --expected-counts <counts_sha256>`.
   Paste the internal URL only at its `Recovery database URL:` prompt.

The counter accepts only a Render internal host that is not the live Staging
database. It counts the new database in a read-only transaction with the same
code as the job. It prints the counts and `same_system_identifier`, then
`TAILTAG-RENDER-RESTORE PASS restore-count` only when the digests are equal.
A PITR copies the database files, so `same_system_identifier` is `true`. The
counter records that value, but it does not gate on it.

After the check, delete the new database in its **Settings**, after owner
approval. It is a paid resource. Record its create time, delete time, and cost.

The practice drill on 2026-11-01 passed: all 25 tables matched. The #410 issue
holds the record. Moving Staging to a restored database is a different
operation. It changes the pinned database identity of the guards, so it needs
a reviewed plan first.

### Application rollback on Render

The [#206 compatibility gate](#fail-closed-compatibility-gate) still decides
whether a rollback is safe. Roll back only to an old application that is
proven compatible with the current schema and data.

Render facts, from the [Render rollback docs](https://render.com/docs/rollbacks)
and the #410 drill:

- A rollback makes a new deploy D from the build of the target deploy R. It
  does not rebuild.
- A rollback uses the environment variables of R. So a variable that changed
  after R goes back to its old value.
- A dashboard rollback turns auto-deploy off. Staging already has it off.
- The pre-deploy command runs during a rollback. The Render docs do not say
  this, and the #410 drill showed it.

Run the rollback in this order:

1. Start a quiet window. Make sure that no Staging variable changed after R
   went live.
2. Record the deploy list:

   ```zsh
   SERVICE_ID="$(jq -r .render_staging_api_service_id ~/.config/tailtag/staging-clean-rebuild-targets.json)"
   render deploys list "$SERVICE_ID" -o json | jq -c '[.. | objects | select(has("trigger") and has("status"))] | .[:8][] | {id, status, trigger, commit: .commit.id, createdAt, finishedAt}'
   unset SERVICE_ID
   ```

3. In the dashboard, open the `tailtag-api-staging` deploy list, find R, and
   click **Rollback**, then **Rollback to this deploy**. Do this only once. If
   it fails, do not retry.
4. In the log of D, record whether the pre-deploy step printed `PASS`.
5. Record the deploy list again. Make sure that it shows exactly one new
   deploy D, with trigger `rollback`, status `live`, and the commit of R.
6. Wait one minute. Run `api_staging_preflight.py --render-staging`, read
   `/health/ready`, and run the
   [authenticated smoke](#render-staging-smoke-checks).
7. Restore the current SHA with an exact-SHA
   [Render promotion](#render-staging-promotion-409). Never use a second
   rollback.

The drill on 2026-11-01 rolled back from `22a307f` to `43d12ae` and promoted
`22a307f` again. It proved the mechanics only, because no migration changed
between the two deploys.

### Database IP allowlists

Both Render databases must have an empty IP allowlist. An empty list blocks
every connection from outside Render. The Blueprint `render.yaml` declares
`ipAllowList: []` for both, so a Blueprint sync keeps them closed. To check a
database:

```bash
render pg get tailtag-postgres-staging -o json | jq -c '.data | {name, status, ipAllowList}'
```

If the list is not `[]`, run
`render pg update tailtag-postgres-staging --clear-ip-allow-list`, then check
again. On 2026-11-01, both `tailtag-postgres-staging` and
`tailtag-postgres-development` showed `[]`.

## Controlled promotion acceptance evidence (2026-09-16)

The owner-squashed [PR #233](https://github.com/TailTag-Game/tailtag/pull/233)
provided candidate `c09c0b441b35d070ed04c73f3a22e34f7f0f2803`.
Its exact completed successful push API validation was
[run 35185145714](https://github.com/TailTag-Game/tailtag/actions/runs/35185145714),
attempt 1. One supported operator invocation submitted that SHA and captured
returned D `d7e69108-a6d8-4355-b1ec-8b83057ca11b` before observation.

The [sanitized repository record](staging-deployments/d7e69108-a6d8-4355-b1ec-8b83057ca11b.json)
records deployment createdAt `2026-09-17T05:20:35.320Z`, every required gate
SUCCEEDED, final active state ACTIVE and overall SUCCEEDED. Exact-instance image
source matched the candidate through #201's unchanged join; canonical smoke
passed. The final exact-D active check was the last remote gate before success.

This validates #202's normal promotion path on the retired generation. It is a
point-in-time declaration and durable historical evidence, not a promise about
later serving state or replacement-project delivery.
Bootstrap and older #201 observations below remain separate historical evidence.
Staging autodeploy stayed disabled; no recovery or deliberate failure test ran.

## Migration and application-image recovery (#206)

The authoritative [#206 migration and application rollback
contract](../specs/2026-09-22-v0-migration-application-rollback.md) and its
[sanitized NO-GO record](staging-recovery/2026-09-22-issue-206-no-go.json)
govern this procedure. Application-image rollback restores application code,
not PostgreSQL schema or data. It is exceptional recovery, not a routine reverse
migration, database rollback, restore, or a substitute for a reviewed forward
fix.

### Expand, Compatible, Contract policy

Prefer **Expand**, **Compatible**, **Contract** schema evolution. Expand with
backward-compatible additions; keep application revisions compatible while old
and new schema/data states coexist; then contract only after a separately
reviewed destructive step proves safe. Destructive or contract migrations cross
the application rollback boundary by default.

Rollback is allowed only when the exact old application has been positively
shown compatible with the actual schema and persisted state that will remain.
The forward fix is the default when proof is missing, ambiguous, or uncertain:
the result is NO-GO. Schema shape or schema compatibility alone is insufficient;
newer persisted state and old application invariants can still be unsafe.

### Fail-closed compatibility gate

Before authorizing rollback from N to O while retaining schema/data S, record
the full old/current source SHAs and exact deployment identities, then review
the complete migration delta and reconcile actual migration history and schema
with that graph. Review O reads, inserts, updates, and deletes for every
affected domain, plus persisted state introduced or made valid by N.

Review added, renamed, and removed objects; nullability; Python defaults and a
database default; types; `NOT NULL`, `UNIQUE`, `CHECK`, foreign key, exclusion, index,
trigger, and generated-value behavior. Explicitly inspect every data migration,
`RunPython`, `RunSQL`, state/database split, non-atomic operation, and suspected
manual operation. Reject partial migration evidence, unreconciled actual state,
or suspected manual database changes.

Where practical, use disposable PostgreSQL proof: apply S with N first, then
run the immutable old application against that unchanged database without reverse
migration.
Require an empty O migration plan, Django checks, focused affected-domain
read/write coverage, retained new migration records/objects, negative constraint
coverage, and proof that O does not reinterpret or mutate newer valid state
unsafely. This is pair-specific maintainer review, not a generic analyzer.

### Retired-generation candidate conclusion: NO-GO

The preferred representative boundary was old
`04f8383fe750bec712ced27a1932b82b1eabb292`, retained as deployment
`57f17ef7-7b34-4c2f-9272-b8091b1eafad`, to new
`77b6c55130f1b69304a8fd748590b4bbad3bf721`. It contains only additive
`rehearsal.0001_initial`, but `77b6c55` was never deployed to Staging, so no
exact retained new image exists for that rehearsal.

The retained old-to-current boundary instead reaches active deployment
`cbe83780-0256-49c2-b026-34709ddb69b0`, source
`856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, and crosses the additional
account/operator/audit migrations recorded in the #206 evidence. The old image
is technically Railway rollback-capable, but it is not application-safe against
current Staging state. [PR #239](https://github.com/TailTag-Game/tailtag/pull/239)
change permits a staff/non-superuser to hold a usable local password and
authentication state, and that state is valid and current. When loaded and
saved by O, its usable password becomes unusable. O
also lacks the newer authorization/audit semantics. This affirmative result
means schema compatibility was insufficient for that old pair and establishes
**NO-GO for that live Staging application rollback**. It does not establish a current
replacement-generation rollback pair. The #206 policy remains authoritative;
the exact live compatible Railway rehearsal remains assigned to #241.

Deployment `3acf7fee-260b-472d-9b20-d1dd76efcb25`, source
`756f48e2d90bbb803060cd015e8bcf2d47ad4fbc`, to current has no migration delta.
It would validate Railway mechanics only, not representative schema/application
recovery. No live mutation was performed, authorized, or required; no artificial
migration pair will be created. The safe recovery is a reviewed forward fix.

### Verified Railway interface and future exact evidence

Read-only GraphQL inspection verified `Deployment.canRollback: Boolean!` and
`deploymentRollback(id: String!): Boolean!`. The mutation selects an exact
historical deployment and does not return the resulting deployment ID. Railway
documents stored-image reuse and historical variable-snapshot restoration without
a rebuild. PRE_DEPLOY_COMMAND remains **unverified** during rollback; observe
its lifecycle only for an exact future result deployment.

For a future qualifying pair:

1. Establish an exclusive Staging operation window and reverify approved
   identities and the canonical target.
2. Capture rollback target **R**, current active deployment **A**, their source
   SHAs, image digests, snapshot IDs, `canRollback`, canonical configuration,
   and the complete scoped pre-operation deployment set without variable values.
3. Invoke `deploymentRollback(id: R)` exactly once.
4. Derive exactly one new deployment **D** from scoped pre/post sets, after the
   invocation, and require D source/image identity to match R. Zero or multiple
   candidates, concurrency, or a lost response is **INDETERMINATE**: stop and
   do not retry blindly. Record the exact result deployment identity,
   source/image match, and lifecycle evidence before proceeding. The
   attribution target is exact D, never `latest`.
5. Inspect lifecycle events for exact D, including whether
   `PRE_DEPLOY_COMMAND` occurred; compare D/R variable snapshots without values;
   use #201 image-local identity and the exact-deployment join; and require D
   active.
6. Run canonical Staging HTTP smoke and focused affected-domain read/write proof.
   Shared-endpoint smoke is never image attribution.
7. Restore A's source through #202 exact-SHA promotion, never a second rollback,
   and verify that restoration as its own exact deployment.

### Windows operator setup

The Staging operator tasks run natively on Windows (#315). They read secrets and
bindings only from owner-only files, so set up the private location first.

- **Checkout.** Clone TailTag under `%USERPROFILE%` and keep `uv` and its cache
  in their default per-user locations. Do not use a folder under a drive root,
  such as `C:\src`, unless no other account can write to it: the tasks run
  Python from the checkout and its virtual environment. This is documented, not
  checked.
- **Configuration folder.** The equivalent of `mkdir -m 700` and `chmod 600`:

  ```powershell
  New-Item -ItemType Directory -Force "$HOME\.config\tailtag" | Out-Null
  icacls "$HOME\.config\tailtag" /reset
  icacls "$HOME\.config\tailtag" /setowner "$env:USERNAME"
  icacls "$HOME\.config\tailtag" /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
  icacls "$HOME\.config\tailtag"
  ```

  `/reset` drops any explicit grants a reused folder already carries, so the
  next line leaves exactly three entries. The `/setowner` line matters in an
  elevated shell, where new folders are owned by `Administrators`; it is
  harmless otherwise. The last line must list only your account,
  `NT AUTHORITY\SYSTEM`, and `BUILTIN\Administrators`; store configuration
  there only after it does. Files created in that folder afterwards inherit
  only those three entries.
- **Rule.** The owner must be you. The only access entries allowed are for you,
  `SYSTEM`, and `Administrators`; any other account or group (`Users`,
  `Authenticated Users`, `CREATOR OWNER`, and so on) is refused, even where it
  contains only you. A symlink, junction, or other reparse point on the file or
  its folder is refused, as is a file over the size limit.
- **Inspect and fix.** `icacls <file>` lists the access entries, and `Get-Acl
  <file> | Format-List Owner` shows the owner. A refused file gets the same
  short failure as on POSIX. If the owner is wrong, for example because the file
  was created from an elevated shell, run `icacls <file> /setowner
  "$env:USERNAME"`. Remove other entries with `icacls <file> /remove <name>` or
  repeat the `/inheritance:r /grant:r` command on the file.
- **Docker.** The restore drill accepts only `npipe:////./pipe/<name>` as the
  Docker endpoint on Windows; a remote pipe host is refused.
- **Evidence.** Files the tools create (restore-drill evidence, simulator
  reports and evaluations) get the same three-entry access list, with
  inheritance off.

Live Staging runs from Windows are not verified by CI.

## Opt-in verification procedures

These are maintainer-only live operations, separate from ordinary CI and
`task api-check`. First verify the Railway context and stop if it is not the
workspace, project, environment, and service listed above. Use explicit
selectors, not a guessed linked context.

### PostgreSQL backup restoration drill (#207)

This drill has no Render version. For Render Staging, use
[Restore the database with PITR](#restore-the-database-with-pitr).

The frozen [backup restoration contract](../specs/2026-09-22-v0-postgresql-backup-restore.md)
and [implementation plan](../specs/2026-09-22-v0-postgresql-backup-restore-implementation-plan.md)
govern this operation. Read-only discovery for the retired database found no
usable PITR recovery point, so the September 23 #207 GO used a real
custom-format `pg_dump` from the former `TailTag/staging` Postgres and
`pg_restore` into a disposable local PostgreSQL 18 target. That restore is
historical evidence for the retired database only. The #207 command now uses
the owner-only, code-pinned replacement `TailTag/staging` selectors and fails
closed if they are unavailable. Read-only replacement discovery at
2026-09-29 04:09 UTC found a ready Postgres volume, zero Railway API backups
and schedules, and a Railway Backups panel showing no backups. The panel
described backup creation and PITR as Pro features while this workspace was on
Hobby. These are point-in-time observations, not a claim about internal backup
state. The replacement drill uses a logical dump for isolated restore proof.
The procedure does not restore a Railway volume or change backup settings.

The [September 29 guarded replacement restore receipt](staging-recovery/20260929T063432Z-issue-207-restore-d4480275113242e7bba0b25387cdf6eb.json)
records `outcome=GO` for source `f16ff7527059e32d2cca15038e55ba406aa35381`
at recovery point `2026-09-29T06:34:40.582701Z`. A real custom-format dump
restored into isolated PostgreSQL 18; 36 of 43 named checks passed. Seven were
`NOT_EXERCISED`: Catch, session and credential representative reads plus the
session, credential and Catch relationship and Catch provenance checks, because
their source tables were empty. Matching-revision backend usability, active
Staging nonimpact and cleanup passed, with no listed limitations or follow-up.
This is isolated restore evidence; it is not an active Staging restore, PITR
proof or Production recovery proof.

Before the drill, verify the approved Finn identities, exact Railway project,
Staging environment, Postgres service/volume, active API deployment/revision,
and healthy fixed Staging origin. Use the local Docker daemon, the cached
`postgres:18` image, and PostgreSQL 18 client tools. Coordinate an exclusive
observation window with no concurrent Staging deployment or configuration
change. The operator command accepts no source URL or restore destination:

```bash
PYTHONPATH="$PWD:$PWD/services/api" \
uv run --project services/api --locked --no-sync \
  python -m scripts.api_staging_restore_drill \
  --confirm restore-tailtag-staging-backup
```

The command must hold one read-only exported source snapshot while capturing
sanitized expectations and streaming the dump through a Railway SSH tunnel.
Before restore it verifies the exact task-owned Docker container ID, image,
`--network none`, absence of published ports, tmpfs mounts, PostgreSQL major
version, and empty `tailtag_recovery` database. The artifact and restored data
remain on tmpfs; `pg_restore` has no configurable remote destination. A
command-only backend container may share only that isolated loopback for
read-only ORM proof, without a public port, Clerk/R2 credentials, or app server.

Successful evidence requires the dump and archive validation, completed
restore, matching migrations/schema/constraints, each named domain integrity
check, representative backend reads, unchanged active Staging deployment and
database relationship plus health, and verified cleanup. On any failure, the
command stops source reads and tunnel, removes only captured task-owned
containers, and records a sanitized NO-GO boundary. Never invoke #204 reset on
the recovered clone or point the active API at it. If automatic cleanup cannot
be verified, retain the opaque task resource handle for a focused manual
cleanup; do not declare #207 complete. The durable result belongs under
`docs/development/staging-recovery/` and contains no connection details or row
contents.

If matching-revision backend reads cannot be performed safely, preserve the
exact limitation and strongest safe database/schema evidence under AC-6. That
substitute explains the gap; it does not meet #207's GO requirement for backend
readability or authorize closing the issue.

### Synthetic baseline reset and reseed (#204)

The [frozen reset contract](../specs/2026-09-17-staging-synthetic-reset-reseed.md)
and [implementation handoff](../specs/2026-09-17-staging-synthetic-reset-reseed-implementation-plan.md)
define a small canonical baseline. Local implementation, independent review
and two-run live acceptance were completed for the retired generation. The
replacement normal-path result and its evidence boundary are recorded below.
The contract records sanitized local and live verification evidence, including
the initially missing fixtures and their separately authorized preparation.

Reset preserves all Users/admin permissions, reusable Clerk identities,
designated media, migration history/schema, and the reset sentinel. It restores
two registered profiles, one Convention, two registered Fursuits, two active
enrollments and two activations. Owned catches, sessions and credentials are zero.
An owner starts a fresh catch session through normal API behavior for catching
rehearsals. Fixtures are resolved through preserved explicit registry bindings,
never by name/prefix or because all Staging state is synthetic. Conflicting
unowned dependencies deny reset instead of enlarging its deletion scope.

#### One-time preparation for replacement Staging: completed

The former generation's provision/reset evidence and private
`staging-reset.env` are not reusable. The replacement database requires a new
independently generated sentinel identity, new owner-only expected configuration,
new fixture/root/media bindings and fresh registry/database reconciliation.
Keep the new expected configuration separately at
`~/.config/tailtag/staging-reset-replacement.env` (file mode `0600`, parent
directory mode `0700`); the replacement-bound launchers use only that default.
Do not copy the retired file or its sentinel values into this path.
The first database-fact prerequisite query for the replacement did not return
a classification. Subsequent guarded checks established the API/PostgreSQL
binding, reconciled the private expected database facts, provisioned the
replacement sentinel, and reseeded the baseline as recorded below. Future
operations still require fresh target and #204 safety checks.

The later [#243 replacement prerequisite record](staging-operator-validation-243-execution-attempts.md#replacement-ordinary-identity-preparation--2026-09-25)
establishes the two exact ordinary Clerk-bound User identities through one
normal authenticated API call and a separate read-only exact-instance
postcondition. The subsequent [designated media and private prerequisite
check](staging-operator-validation-243-execution-attempts.md#replacement-204-private-prerequisite-check--2026-09-25)
established an application-readable synthetic image, the actual connected
database binding, and the new owner-only replacement reset configuration.
That check made no Staging mutation. The later [guarded sentinel and baseline
receipt](staging-operator-validation-243-execution-attempts.md#replacement-204-sentinel-and-baseline--2026-09-25)
records one replacement-bound provision, a matching three-way reconciliation,
one guarded baseline reseed with the expected counts and cleanup, and a second
matching reconciliation. At that point, operator-role and #243 matrix evidence
remained separate from this #204 prerequisite.

Two later guarded replacement resets on September 29 returned the same
version-1 baseline counts and confirmed temporary-source cleanup. The last
reset occurred during the [completed #243 matrix](staging-operator-validation-243-execution-attempts.md#replacement-bounded-matrix-completed--2026-09-29);
its in-process readback passed the semantic baseline, retained registered
roots and audit rows, canonical readiness, and managed-role validity after
resumption. The [#208 OR-5 reconciliation](v0-backend-operational-readiness-matrix.md#replacement-or-5--204-reset-evidence-2026-09-29)
records the exact preservation and inherited-test boundary. These receipts
demonstrate the replacement normal path, while each future reset still needs
its own target, database, asset, identity and maintenance-window guards.

The replacement-target SSH reset path and its separately confirmed, sentinel-only
`api-staging-reset-provision-ssh` mode passed local tests and independent
security review on the #243 branch. They established the replacement sentinel
and baseline in the bounded receipt linked above. For any future reset, repeat
the independent identity, database, media, registry, target, and exclusive-window
guards; this point-in-time result is not a standing authorization. Any uncertain
provision result requires a fresh read-only reconciliation; do not retry it
blindly. The native `api-staging-reset-provision` command assumes
a reachable database and must not be substituted for the private-network SSH
path. Retired-generation commands and receipts do not authorize a replacement
mutation. Record fresh evidence without changing the historical receipts.

#### Retired-generation one-time preparation (historical)

Use the approved Railway/operator identity checks and verify the exact Staging
Postgres resource independently before establishing the pinned database endpoint,
port, name and PostgreSQL cluster system identifier. Select exactly two existing,
distinct non-admin synthetic Clerk identities with existing TailTag User bindings,
and one stable pre-provisioned synthetic image. Do not create/recreate Clerk
users or upload media through reset. The image must use the existing opaque-key
contract and be readable using configured Staging S3 storage.

Store Staging-only operator configuration privately; never commit rendered
values, database URLs, media keys or a sentinel identifier. Required configuration
is enumerated in the implementation handoff. Set explicit reset capability and
independently generate/configure a random v4 environment UUID. Ordinary migrations
create the empty registry schema, never an enabled sentinel. Provisioning requires
its separate exact confirmation and refuses to overwrite an existing sentinel.
Do not make Development/Production reset-capable or copy this configuration when
cloning a database.

After privately configuring the verified Staging values and deploying the empty
sentinel schema, invoke the separate provisioning operation from repository root:

```sh
task api-staging-reset-provision
```

For subsequent maintenance resets inside a verified native Staging environment, use:

```sh
task api-staging-reset
```

For the approved private-network Staging API, the maintained operator command is:

```sh
task api-staging-reset-ssh
```

Its native equivalent is `python -m scripts.api_staging_reset_ssh --confirm reset-tailtag-staging`,
with optional `--config PATH`. The default is the private file
`~/.config/tailtag/staging-reset.env`; the file must be owned by the current
operator with mode `0600`, in an owned non-symlink directory with mode `0700`.
It accepts exactly the nine reset assignments, with no shell evaluation or
credential/target overrides. This command resets an already-provisioned baseline;
it does not prepare schema, identities, the sentinel, or external assets.

These targets supply their distinct exact CLI confirmations. Native equivalents
are `python -m scripts.api_staging_reset --provision --confirm provision-tailtag-staging-reset`
and `python -m scripts.api_staging_reset --confirm reset-tailtag-staging`, using the
locked API environment, production settings and repository/API Python paths as
defined in the Taskfile. Do not pass credentials or private identity values as
arguments. Invocation is a deliberate maintenance action, not a scheduled task
installed by this work item.

The executor is a repository-owned native Python process using production Django
settings and positively verified Staging database/storage configuration. It needs
superuser database privileges and access to a separate `postgres` control database
on the same pinned cluster. Target database `postgres` is unsupported. A native
operator process cannot assume it can resolve Railway private DNS; use the
independently verified reachable Staging endpoint and compatible effective Django
configuration. No credential or private identity value should appear in command
arguments/output. `railway run` runs locally with selected variables; it does not
create an executor inside the private Railway network.

The approved Staging Postgres resource currently has no public TCP proxy.
`api-staging-reset-ssh` positively verifies the approved Railway account, captures
the canonical #203 public tuple, and joins that deployment to the exact approved
Staging resources and sole running instance. It compares selected API/Postgres
database configuration and independently verifies runtime selectors, immutable
build identity and the database URL fingerprint before invoking the native reset.
Its bounded code-only archive and complete per-file manifest are validated before
execution by the existing production interpreter in an exclusive private
`/tmp/tailtag-staging-reset-*` directory. Private reset configuration is transferred
through SSH stdin; database/storage credentials remain in the verified runtime.
The real #203 helper must match the pinned tuple at every internal preflight,
including after resume, preserving the native command's failure/re-gate behavior.
The served `/app` files are never replaced, and no deployment is submitted.
Successful output includes exact baseline counts, the public tuple, a bundle
fingerprint and confirmed removal of temporary source.

A timeout, disconnect or untrusted response after SSH starts reports maintenance
unknown. Do not retry or assume service resumed. Use the retained-gate recovery
procedure below. Handled failures and interruptions remove temporary source; a cleanup error or
process/container loss may prevent that cleanup and makes the command fail. After verifying the same approved
account and exact resource/instance join, inspect only directories matching
`/tmp/tailtag-staging-reset-*` on that instance. Confirm a directory is no longer
used by an active reset before removing that specific directory. Never delete
`/app`, unrelated temporary files, persistent fixture objects or a service/volume,
and never resume a retained database gate as an implicit cleanup step.

For the completed proof, Staging-only expected configuration is retained privately
at `~/.config/tailtag/staging-reset.env` (`0600`, parent directory `0700`). It
contains the capability, random expected sentinel identifier, approved database
pins and fixture references; database/storage credentials remain owned by the
verified Staging runtime. Keep that file private and preserve it independently
of the database; do not copy it to other environments. The sentinel, two reusable
Clerk/User identities and single designated media object survive every reset.
The maintained SSH command has passed two controlled resets with matching semantic
and protected-state observations, final readiness and no retained remote source
directories. Private command/snapshot receipts use the `staging-reset-ssh-proof-*`
filenames in that directory. This proves the controlled normal path; failure and
interruption cases are exercised offline, and ordinary resumed gameplay can
subsequently change the baseline.

#### Maintenance and expected result

The guarded entry point performs #203 preflight only at
`https://staging.tailtag.app`, verifies runtime/capability, actual connected
database/sentinel, registered identity bindings and read-only media availability.
It opens and retains the target executor and a separate control connection.
The control connection temporarily disables all new target-database connections,
terminates other target sessions and positively proves sole-executor quiescence
before destructive cleanup. PostgreSQL connection gating covers ordinary API,
admin and replacement-instance writes without application writers joining a lock.
Any prepared transaction, subscription, unresolved writer or identity uncertainty
denies reset. Plan for a Staging maintenance outage; coordinate rehearsal users
and privileged operators and do not run other database administration concurrently.

Scoped cleanup, baseline reconstruction and semantic validation occur in one
transaction. Root fursuit public UUIDs remain stable; database PKs/timestamps are
not semantic equivalence keys. Reset neither calls Django flush/truncate nor
mutates Clerk/R2. It reuses designated objects, and does not remove old uploaded
objects or unowned simulation data. Simulation media cleanup belongs to #199/#220.

On successful commit and validation, the procedure restores database connections
and proves canonical readiness and unchanged application identity. Only then is
success reported with allowlisted counts and source/deployment identity. The
baseline becomes authoritative after reset and normal service resumption; later
gameplay can change it. A second reset restores the same semantic baseline.

#### Failure and recovery

A transaction failure restores prior domain state. Failure after connection
gating retains maintenance rather than silently reopening writes. A committed
reset with failed resumption is reported separately; it is not a rollback or
successful rehearsal. Failure to prove re-gating is maintenance-unknown and needs
operator inspection. Never run an unguarded retry to bypass denial.

For interruption/executor loss or retained maintenance, an approved operator must
first reverify the exact Staging endpoint/resource, connected control-cluster
identity and target database name using privately stored expected configuration.
Inspect the reset phase and whether domain commit happened; stop if uncertain.
Use that verified separate control database to restore the target's originally
enabled `ALLOW_CONNECTIONS` flag, then run canonical #203 preflight and inspect
semantic baseline or prior-state evidence before resuming rehearsals. Recovery
does not delete any domain/external state, create a sentinel, or bypass identity
checks. Do not restart Postgres or delete a service/volume as cleanup.

The temporary database connection flag is restored on success; a retained gate
is an intentional outage requiring this recovery procedure. No test container or
network is retained by the live operator procedure. Reset is neither a Django
migration nor a backup/recovery substitute; OR-8 owns backup/restore.

### Immutable build and deployment identity (#201)

The 2026-09-16 bootstrap observation is historical only: it predates the #201
implementation and is excluded from its final acceptance evidence. Do not use
it to claim an immutable build identity, a current deployment, or a completed
deployment workflow. The frozen [build and deployment identity
specification](../specs/2026-09-16-backend-build-deployment-identity.md) defines
the authoritative contract.

`config.build_identity.get_identity()` is the shared application source for the
root-owned, image-local build artifact and the explicit runtime deployment ID
and environment. It has no Railway credentials or control-plane query. Its
operator entry point emits only those three fields.

Before any authorized #201 proof operation, confirm the repository author and
committer are both `Finn the Panther <finn@finnthepanther.com>`, and confirm
the authenticated Railway identity is Finn's approved name and email with
`railway whoami`. Confirm the authenticated GitHub CLI account is
`FinnThePanther` with `gh api user --jq '.login'`. Stop on any mismatch. Record
only the full source SHA, Railway deployment ID, environment name, and deployment
timestamp; do not record tokens, CLI diagnostics, deployment metadata, or
configuration values.

For a captured deployment ID `D`, query only that record and collect only its
ID, target fields, and deployment-instance IDs/statuses. The query below must
match the canonical project, Staging environment, and API service before an
instance is selected:

```bash
railway api 'query Deployment($id: String!) { deployment(id: $id) { id projectId serviceId environment { name } instances { id status } } }' \
  --raw-var "id=$DEPLOYMENT_ID"
```

Choose only a `RUNNING` instance returned for `D` and pass its actual
deployment-instance ID explicitly to SSH. Never allow `railway ssh` to select
its default active instance. The following pinned SSH pipeline belongs to the
**retired Railway project** and is unsupported for replacement Staging. Do not
execute it against the replacement or substitute a guessed project ID. Its
successful historical proof remains valid for the retired deployment only:

```bash
set -o pipefail
railway ssh --project 85324de4-be6a-49c3-a3f9-6cac13877849 \
  --service api --environment staging --deployment-instance "$DEPLOYMENT_INSTANCE_ID" -- \
  uv run --locked --no-sync python -m config.build_identity \
  | uv --directory services/api run --locked --no-sync python ../../scripts/api_deployment_identity.py
```

The join command accepts only the three-field backend JSON and queries exactly
`D`; it does not select the latest deployment. Its successful output preserves
Railway's `createdAt` as `deployment_timestamp`, which is deployment-record
creation time rather than a build, startup, restart, activation, or query time.
Immediately before resolving the returned `source_sha`, repeat the Finn GitHub
identity check, then resolve the exact commit with
`gh api "repos/TailTag-Game/tailtag/commits/$SOURCE_SHA" --jq .sha`.

The join command validates supplied stdin and Railway's target metadata, but
cannot attest where stdin originated. Final evidence must therefore retain the
actual backend command output from the selected exact instance, not a
hand-constructed tuple. Railway metadata is trusted platform evidence, not
cryptographic image attestation. Evidence for `D` remains valid historically
after later deployments, but it does not claim that `D` is currently serving;
make that claim only after a separate active-deployments comparison.

Final #201 acceptance passed for source
`84237fd2e8db35ecf06c33a8eb09d104858195ff`, deployment
`bd411e7e-cbc9-4c3e-b332-9f7e522b4b72`, environment `staging`, and Railway
`createdAt` `2026-09-17T01:04:22.773Z`. The specification retains the exact-instance
readback, exact-record join, GitHub resolution, and smoke evidence. This is
historical evidence for that deployment rather than an ongoing serving claim.

### HTTP, configuration, and media

#### Health and public Staging preflight (#203)

The [health and environment-safety contract](../specs/2026-09-16-backend-health-environment-safety.md)
defines the three public signals:

- `/health/live`: HTTP 200 with `{"status":"ok"}` means the process can answer.
  It does not depend on database, vendor availability, or identity validity.
- `/health/ready`: HTTP 200 with `{"status":"ok"}` means required effective local
  configuration is valid and the configured PostgreSQL database answers a small
  query. Invalid configuration or database failure returns sanitized HTTP 503
  with `{"status":"unavailable"}`. Clerk and storage are checked locally, without
  vendor requests. This is not proof of credential authorization or vendor uptime.
- `/health/identity`: returns only #201's image/runtime `source_sha`,
  `deployment_id`, and `environment`; invalid identity returns sanitized HTTP 503.
  It contains no deployment timestamp, resource identifiers, or configuration dump.

All health/identity responses use `Cache-Control: no-store`. Intended local
settings can retain disabled Clerk authentication and filesystem storage, but
cannot qualify as a Staging acceptance target. Deployed readiness requires valid
authentication/storage and safe deployed configuration; Staging additionally
requires its valid baked/runtime identity.

Before acceptance or simulation traffic, future tooling must call the reusable,
credential-free primitive `scripts.api_staging_preflight.validate_target()`.
To run the same guard from the repository root:

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_preflight.py https://staging.tailtag.app
```

The command rejects every origin except that exact literal before networking.
No trailing slash, explicit port, alternate host, path, credentials, HTTP,
Development, Production, or localhost override is accepted. It disables redirects
and ambient proxies, validates positive Staging identity, requires readiness, and
requires unchanged identity across the preflight observations. Timeout, malformed
or unexpected responses, missing identity, and any uncertainty deny traffic.
Failure is a fixed sanitized error with nonzero exit status; success prints only
the three-field observed identity JSON. The guard makes health/identity GETs only.

Future #199 reports must capture the observed source SHA and deployment ID.
This is protection against accidental/misconfigured targeting, not remote
attestation or a promise that a deployment cannot change afterward. It needs no
Railway credentials, deployment timestamp, or expected candidate SHA. Optional
operator correlation requires a separately reviewed replacement-bound
exact-instance procedure; the retired SSH invocation above cannot provide it.
That enrichment is separate from permission to send acceptance traffic.

Live #203 validation passed on 2026-09-17 after controlled promotion of merged
revision `04f8383fe750bec712ced27a1932b82b1eabb292`, validated by exact push
[run 35189808670](https://github.com/TailTag-Game/tailtag/actions/runs/35189808670).
The [sanitized promotion record](staging-deployments/57f17ef7-7b34-4c2f-9272-b8091b1eafad.json)
records every required #202 gate SUCCEEDED and final state ACTIVE for deployment
`57f17ef7-7b34-4c2f-9272-b8091b1eafad`.

Separate credential-free public checks confirmed `/health/live`, `/health/ready`,
and `/health/identity` each returned HTTP 200, exactly their approved JSON bodies,
`application/json`, and `Cache-Control: no-store`, with no redirects. The CLI and
reusable primitive both passed, capturing the SHA/deployment above and
`environment == "staging"`. Nine unsafe origin variants (including slash, HTTP,
localhost, Production/Development/unknown hosts, IP, explicit port, and malformed
input) were denied locally before transport. Unhealthy dependency/configuration
and malformed-response cases remain deterministic test evidence; no live chaos
was performed.

The promotion record's timestamp is optional operator correlation evidence;
public preflight neither obtains nor requires it. These are point-in-time
observations, not a promise about subsequent serving state.

Run the existing credential-free HTTP smoke only against the canonical public
URL. It checks the existing health, schema, and docs contract; it does not
deploy or change Staging or establish the #203 identity/target-safety contract.

```bash
API_BASE_URL=https://staging.tailtag.app task api-smoke
```

The following configuration-fingerprint, media-smoke, and Clerk-smoke
`railway run --project` invocations pin the **retired Railway project**. They
are historical examples, unsupported for replacement Staging. Do not execute
them for the replacement or substitute a guessed project ID. The retired
configuration-fingerprint command emitted only resource/configuration
fingerprints, never values:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM=run-tailtag-environment-fingerprint \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment staging -- \
uv run --project services/api --locked --no-sync python scripts/api_environment_fingerprint.py
```

The retired comparison used the corresponding Development command in the same
review window:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM=run-tailtag-environment-fingerprint \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment development -- \
uv run --project services/api --locked --no-sync python scripts/api_environment_fingerprint.py
```

The retired synthetic R2 upload/read/delete/absence check used that same
project. Its cleanup and final absence check were mandatory:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-staging-media-storage-smoke \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment staging -- \
task api-media-storage-smoke
```

Do not share object keys, bucket names, presigned URLs, signatures, response
material, or rendered variable values. A failed deletion or absence check is a
failure, not a warning.

### Clerk authenticated smoke

The command below is the retired-generation Production-Clerk smoke launcher
and is unsupported for replacement Staging. A replacement authenticated smoke
requires a separately reviewed, code-pinned launcher and owner-controlled
bounded validation; do not use the retired command below. The historical
procedure used a TTY and first required the operator to disable clipboard
history and synchronization before copying any Backend secret,
session ID, or JWT. Then sign in through `/sign-in`, open `/user`, and copy the
session ID in the browser console with `copy(Clerk.session.id)`. Only when the
command prompts, obtain a fresh ordinary token with
`copy(await Clerk.session.getToken({skipCache:true}))`. Paste each value
directly into the hidden prompt, clear the clipboard immediately afterwards,
and never place a secret, session ID, or JWT in an argument, environment,
shell history, log, file, chat, or URL.

The synthetic user ID is non-secret but must still be entered through a hidden
local read before it is supplied only to the command's child environment:

```zsh
read -rs 'CLERK_STAGING_SMOKE_USER_ID?Synthetic Clerk user ID: '
print
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_STAGING_AUTH_SMOKE_CONFIRM=run-clerk-staging-auth-smoke \
API_BASE_URL=https://staging.tailtag.app \
TAILTAG_STAGING_API_BASE_URL=https://staging.tailtag.app \
CLERK_STAGING_SMOKE_USER_ID="$CLERK_STAGING_SMOKE_USER_ID" \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment staging -- \
task api-staging-auth-smoke
unset CLERK_STAGING_SMOKE_USER_ID
```

The command accepts only the exact `staging`/`api` target and canonical public
API, confirms the dedicated Production instance and synthetic metadata, then
checks `/api/me/` using an unchanged cryptographic verifier. The named
60-second ordinary-token bound is Clerk provider-smoke safety, not a TailTag
domain or API contract. It never creates sessions, mints tokens, uses tickets
or templates, or introduces frontend/protocol behavior.

Before selection, sign out or revoke manually if setup fails. After the exact
selected session is accepted, revoke is mandatory in `finally`; cleanup failure
takes priority and requires manual remediation. A revoked session's already
issued token can remain acceptable until its short expiry, so do not claim
instant invalidation.

## Operator audit acceptance matrix (#205)

The [#208 evidence handoff](staging-operator-validation-205.md) records which
bounded live outcomes can currently be substantiated; the matrix below is the
approved test definition, not a result record.

Run this matrix only with separate explicit authorization, in isolated Staging,
using disposable synthetic records. It is a bounded field-beta proof, not a
general admin test suite. Follow the [operator authorization and audit
runbook](../operations/operator-authorization-audit.md) for the exact
provisioning and permission boundary.

| Case | Required proof |
| --- | --- |
| 1 | An ordinary player cannot browse or inspect sensitive admin records and cannot execute a sensitive admin mutation. |
| 2 | An `is_staff=True` user without the target sensitive permission is denied; exactly one sanitized `denied` audit row is retained and no mutation occurs. |
| 3 | An explicitly permitted non-superuser operator succeeds on one representative sensitive operation. |
| 4 | An operator permitted for one action cannot cross a different sensitive permission boundary. |
| 5 | An emergency superuser succeeds and the durable record has `actor_class=emergency_superuser`. |
| 6 | A successful action creates exactly one sanitized durable audit row containing action, actor class, target type/ID, `succeeded`, and time. |
| 7 | An unauthorized or denied mutation creates exactly one sanitized `denied` audit row. |
| 8 | A profile or fursuit disable cascade preserves transactional data-integrity behavior and creates exactly one top-level audit row. |
| 9 | Catch create/add, edit, bulk, and every alternate gameplay authority or award path remain unavailable. |

Use #204 to restore/reset disposable synthetic domain state where appropriate;
it does not delete retained audit evidence. Do not reset an audit row away as
part of this proof.

The protected durable database audit record contains the actor application/Django
user ID required by the audit contract. It is not a shareable evidence artifact.

### Sanitized evidence template

Record only: matrix case, action, actor class, target type/ID, outcome (for
example, `succeeded`), time, and a fixed pass/fail result. Sanitized evidence
must not record actor application/Django user ID. Do not record credentials,
provider identifiers, emails, tokens, QR payloads, private URLs, raw request
bodies, or raw logs.

## Safety and evidence handling

Keep `sk_live_` credentials, session IDs, and JWTs strictly hiddenTTY. Do not
put them in argv, environment, history, logs, files, chat, or URLs. Do not
record raw bucket names, private Railway URLs, screenshots, dumps, email
addresses, user IDs, credentials, tokens, or session IDs. Sanitize diagnostics
before sharing them.

The dated 2026-09-16 record reports only safe public identifiers, fixed stages,
and short one-way fingerprints. A resource fingerprint is a SHA-256 prefix of
a resource ID/name. A configuration fingerprint is an approved framed field
tuple; tuple inequality does **not** prove that every individual field differs.
Use the independent owned-resource identities, scope review, and successful
bounded checks as complementary evidence.

## 2026-09-28 replacement parity readback

This is a point-in-time, read-only comparison for the replacement `TailTag` /
`development` and `staging`. The repository-pinned replacement project selectors
and approved Railway identity passed before the existing
`api_environment_fingerprint.py` helper ran against each `api` configuration.
The helper emitted only short, one-way fingerprints. All five approved groups
were different:

| Effective configuration group | Development | Staging | Result |
| --- | --- | --- | --- |
| Database URL | `a70514d7f0d89fc4` | `8fd03c48623fd8f7` | DIFFER |
| Django secret | `0b1a74f19516074a` | `801e9055b74d381b` | DIFFER |
| Clerk verification key and authorized parties | `0810af6281c98c9d` | `b8faad750558e6d7` | DIFFER |
| Media bucket name | `a750eecf47ff92d9` | `b95c8d61f8b9386a` | DIFFER |
| Media credential pair | `2bd4737fdf60c2d8` | `7dbd16c08d745956` | DIFFER |

The canonical credential-free preflight also returned `environment=staging`,
source `99e6466e1bd5432025c085134e72c2c46eb92dbc`, and deployment
`2adc748c-ee54-4446-958c-f49a384925be`, matching the approved replacement
[promotion receipt](staging-deployments/2adc748c-ee54-4446-958c-f49a384925be.json).
That receipt retains the exact-instance image join and successful promotion
gates from September 25; the public preflight is a current shared-origin
observation, not a fresh image attestation.

The same read-only pass checked provider resource ownership. Railway returned
the project ID pinned by the replacement manifest and code, distinct from the
retired project's ID. Its current display name is `TailTag`, following the
temporary `TailTag Rebuild` name. The approved active deployment belongs to
the pinned replacement project, `staging` environment, and `api` service. Each
Development/Staging Railway resource below was distinct and attached to the
respective pinned environment and service; fingerprints are SHA-256 prefixes
of resource IDs, not configuration values:

| Railway resource | Development | Staging | Result |
| --- | --- | --- | --- |
| Environment | `f7023481cda2ea4a` | `774b263fa12467f7` | DIFFER / PASS |
| API service instance | `6b894823bb3276c2` | `ca975902ff3eb800` | DIFFER / PASS |
| PostgreSQL service instance | `9ad9c82f62db7440` | `4db28d59e8b726f9` | DIFFER / PASS |
| PostgreSQL volume instance | `c74dc72fab8fa311` | `264e3033b5ad5dee` | DIFFER / PASS |
| Underlying PostgreSQL volume | `2e214df95860c779` | `ae3eaaf53778396b` | DIFFER / PASS |

The Clerk provider inventory showed separate replacement Development and
Staging applications and instances (DIFFER / PASS); Staging's instance is the
Production instance of its dedicated application. The Cloudflare provider
inventory showed separate replacement Development and Staging R2 buckets and
separate active API tokens, each with Object Read & Write scope restricted to
its corresponding single bucket (DIFFER / PASS). These are point-in-time
ownership and scope observations, not credential or application smoke tests.

The configuration comparisons establish distinct effective database URLs,
Django secrets, and bucket names. Grouped Clerk and credential results do not
prove that every constituent field differs. A separate normalized Clerk
public-key readback returned no usable sanitized result, so no key-level
comparison is claimed. No authenticated Clerk or media smoke or Staging
mutation ran in this pass.

The maintained intentional-drift record for the replacement is:

| Concern | Development | Staging | Future Production |
| --- | --- | --- | --- |
| Purpose and data | Mutable contributor/integration work with synthetic data | Controlled rehearsal with synthetic data | No environment or data exists |
| Railway | Replacement `TailTag/development` with its own PostgreSQL environment and volume | Replacement `TailTag/staging` with its own PostgreSQL environment and volume | Not established |
| Delivery | Normal Development delivery path | Exact-SHA controlled promotion; automatic Staging delivery disabled | Not established |
| Authentication | Development Clerk application and authorized origins | Dedicated `TailTag Staging Replacement` application and Staging origins | Not established |
| Media | Development private R2 bucket and scoped credential | Distinct private Staging R2 bucket and scoped credential | Not established |
| Effective configuration | Development database, secret, Clerk, bucket, and credential groups above | Different values for all five groups above | Not established |
| Public origin | Development API origin | `https://staging.tailtag.app` | Not established |

The resource-ownership descriptions above have a fresh provider inventory as
of this readback. Reconcile any future configuration change against this record
without publishing values or private selectors.

## 2026-09-16 sanitized parity record

The following fingerprint and live-smoke evidence belongs to the retired
`TailTag` Railway generation. It remains historical and does not establish
resource isolation or smoke outcomes for the replacement project.

The observed target has successful `api` and `Postgres` deployments, a ready
5000 MB Staging PostgreSQL volume, disabled Staging autodeploy, canonical HTTPS
HTTP smoke success, and only `development` and `staging` Railway environments.
The following was the retired generation's intentional-parity record; it does
not disclose private addresses or secrets.

Porkbun is the authoritative DNS provider for `tailtag.app`; the approved
hostname-scoped Clerk and Railway records were added through verified
zone-editor access without a zone move, nameserver, root, or wildcard change.
The distinct active R2 token resources are named `TailTag Railway Development`
and `TailTag Railway Staging`; each has Object Read & Write scope only for its
respective single bucket. No token IDs or key material are retained.

Resource fingerprints are the first 16 lowercase hexadecimal characters of
SHA-256 over the relevant provider resource ID/name; they use no credentials.

| Resource | Development | Staging | Result |
| --- | --- | --- | --- |
| Railway environment | `db22c0f5eaba28c2` | `9c7e0f7f762c181e` | DIFFER / PASS |
| Railway api service instance | `ee781f506046aa80` | `e053d8c6c1c2b5dc` | DIFFER / PASS |
| Railway Postgres service instance | `6b458dfe6b7f6a32` | `37b163c50c85f451` | DIFFER / PASS |
| Railway PostgreSQL volume instance | `60b8e6c18a88ce0b` | `391189f2a6222233` | DIFFER / PASS |
| Clerk application | `04fd8c0acbac568a` | `ccf8c8de1e8c2010` | DIFFER / PASS |
| Clerk instance | `8544da8f1bdb2a37` | `eb6daf25d12b85eb` | DIFFER / PASS |
| R2 bucket name | `e2bc2123287283cd` | `ba4fcb660a2476a8` | DIFFER / PASS |

The guarded configuration comparison produced the following approved framed
tuple fingerprints. A `DIFFER` result is a tuple comparison, not proof that
every field inside that tuple differs.

| Group | Development | Staging | Result |
| --- | --- | --- | --- |
| database | `c10bd6425f263f5d` | `fe06faf3737839a6` | DIFFER / PASS |
| django-secret | `6be5a62437737cf3` | `f1d52a9daebfe9d9` | DIFFER / PASS |
| clerk-verification | `781eb17ff2c25999` | `f589d2beb0310251` | DIFFER / PASS |
| media-bucket | `f979eefe5c51f0ba` | `c19e2036ae29079a` | DIFFER / PASS |
| media-credential | `da8a14263699e150` | `8bdd61b51d4e82fd` | DIFFER / PASS |

The Clerk verification-key material was separately compared through a
read-only normalization: DER-SPKI SHA-256 prefix `7bf6fb343ed260c6` for
Development and `1c617efd974ee2d6` for Staging: DIFFER / PASS. No PEM was
retained, and this supplemental observation adds no tool or application
behavior.

Fixed sanitized live-stage evidence was also recorded:

| Check | Recorded result |
| --- | --- |
| Credential-free API smoke | `/health/live`, `/health/ready`, `/api/schema/`, and `/api/docs/`: HTTPS200 / PASS |
| Synthetic media smoke | target, upload, object exists, presigned GET bytes, delete, object absent, and media storage smoke: PASS |
| HiddenTTY Clerk smoke | target, baseline API smoke, Clerk Production instance, synthetic user, session token, authenticated API, cleanup, and Staging authenticated API smoke: PASS |

The media object was cleaned. The Clerk smoke used a fresh ordinary browser
token verified by the unchanged verifier and revoked its exact selected session;
no sensitive inputs or identifiers were retained in the evidence.

| Concern | Development | Staging | Future Production |
| --- | --- | --- | --- |
| Topology | Mutable contributor/integration environment | Persistent production-rehearsal environment | Does not exist |
| Source/build | `main`-connected Development API service | Same existing source, root, Dockerfile, migration and Gunicorn paths | Not defined by this runbook |
| Migrations/runtime/health | Existing production-settings image and readiness path | Same existing paths, explicitly Staging-targeted | Not defined |
| Database | Separate Railway Postgres and volume | Separate Railway Postgres and volume; resource identity differs | Does not exist |
| Clerk | Separate Development application/instance | `TailTag Staging` dedicated Production instance; identity differs | Does not exist |
| R2 | Private Development bucket and scoped credential | Private Staging bucket and separately scoped credential; identities differ | Does not exist |
| Domains | Development public API | `https://staging.tailtag.app`; current bootstrap portal origin is replaceable | Does not exist |
| Secrets/configuration | Development-owned values | Staging-owned values; approved configuration tuple fingerprints differ | Does not exist |
| Data | Synthetic mutable integration state | Synthetic-only TailTag, Clerk, and media state | No production data |
| Deploy trigger | Normal GitHub autodeploy for Development | Autodeploy disabled after one-time bootstrap | No trigger or environment |
| Sizing | Current 5000 MB PostgreSQL volume | Current 5000 MB PostgreSQL volume | No sizing decision |

The same source/build and platform shape are deliberate rehearsal parity. The
environment, dependency identities, Clerk application, R2 ownership,
configuration/secrets, data policy, deploy trigger, and operational purpose are
deliberately different. Drift ownership is with maintainers: before any Staging
configuration or platform change, re-check this runbook and record only
sanitized evidence; do not copy Development values or turn Staging into a
promotion lane without separately approved work.

For the authoritative acceptance constraints, see the frozen
[V0 Railway Staging environment specification](../specs/2026-09-15-v0-railway-staging-environment.md).
