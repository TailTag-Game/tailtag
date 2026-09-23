# Staging runbook

This is the maintainer runbook for TailTag's persistent Railway **Staging**
backend: a controlled production-rehearsal target for maintainers with the
needed Railway, Clerk, and Cloudflare access. It is separate from the mutable
contributor/integration [Development runbook](backend-delivery-operations.md).
It covers the controlled promotion procedure below. It is not a production SRE
guide or a source of credentials.
For common backend incidents, follow the
[Staging first-response procedures](../operations/staging-first-response.md)
and their [#208 evidence matrix](v0-backend-operational-readiness-matrix.md).

## Supported target and boundary

Use only this observed Railway target:

| Item | Value |
| --- | --- |
| Workspace | `Finn the Panther's Projects` |
| Project / environment | `TailTag` / `staging` |
| Services | `api`, `Postgres` |
| Canonical public API | `https://staging.tailtag.app` |

Staging owns its Railway environment instances, PostgreSQL service and volume,
runtime configuration and secrets, and public API networking. The API reaches
its database through the environment-local `Postgres` reference; never copy or
record a rendered database URL. Its private R2 bucket is Staging-owned, with a
single-bucket `TailTag Railway Staging` Object Read & Write credential. The
R2 account endpoint may be shared platform infrastructure; the bucket and
credential must not be.

`TailTag Staging` is a separate Clerk application using its dedicated
Production instance, not Development's Clerk application or instance. The
current hosted Account Portal origin,
`https://accounts.staging.tailtag.app`, is authorized only for the bootstrap
authentication validation described here. It is deliberately replaceable when
real V0 client integration establishes its own semantics; it is not a permanent
mobile/client architecture decision.

Use only synthetic TailTag records, Clerk users, and media. Do not use personal
data, production data, or ordinary user accounts. Development remains the
mutable contributor/integration environment. TailTag has no Production
environment, deployment target, or production data.

## Bootstrap status and deployment boundary

The one-time bootstrap is complete. Staging GitHub autodeploy is disabled while
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

From the repository root, with existing locked dependencies installed:

```bash
SOURCE_SHA='replace-with-reviewed-full-40-character-main-ancestor-SHA'
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_promote.py \
  --source-sha "$SOURCE_SHA" --confirm promote-tailtag-staging
```

The confirmation authorizes this one exact-SHA Staging submission, not recovery
or configuration changes. The command is opt-in and is never invoked by ordinary
CI, `make api-check`, application startup or a health check.

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

This validates #202's normal promotion path. It is a point-in-time declaration
and durable historical evidence, not a promise about later serving state.
Bootstrap and older #201 observations below remain separate historical evidence.
Staging autodeploy stayed disabled; no recovery or deliberate failure test ran.

## Opt-in verification procedures

These are maintainer-only live operations, separate from ordinary CI and
`make api-check`. First verify the Railway context and stop if it is not the
workspace, project, environment, and service listed above. Use explicit
selectors, not a guessed linked context.

### PostgreSQL backup restoration drill (#207)

The frozen [backup restoration contract](../specs/2026-09-22-v0-postgresql-backup-restore.md)
and [implementation plan](../specs/2026-09-22-v0-postgresql-backup-restore-implementation-plan.md)
govern this operation. Read-only discovery found no usable PITR recovery point,
so #207 uses a real custom-format `pg_dump` from canonical `TailTag/staging`
Postgres and `pg_restore` into a disposable local PostgreSQL 18 target. It does
not restore a Railway volume or change backup settings.

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
define a small canonical baseline. Local implementation, independent review and
authorized two-run live Staging acceptance are complete. The contract records
sanitized local and live verification evidence, including the initially missing
fixtures and their separately authorized preparation.

Reset preserves all Users/admin permissions, reusable Clerk identities,
designated media, migration history/schema, and the reset sentinel. It restores
two registered profiles, one Convention, two registered Fursuits, two active
enrollments and two activations. Owned catches, sessions and credentials are zero.
An owner starts a fresh catch session through normal API behavior for catching
rehearsals. Fixtures are resolved through preserved explicit registry bindings,
never by name/prefix or because all Staging state is synthetic. Conflicting
unowned dependencies deny reset instead of enlarging its deletion scope.

#### One-time preparation

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
make api-staging-reset-provision
```

For subsequent maintenance resets inside a verified native Staging environment, use:

```sh
make api-staging-reset
```

For the approved private-network Staging API, the maintained operator command is:

```sh
make api-staging-reset-ssh
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
defined in the Makefile. Do not pass credentials or private identity values as
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
its default active instance. From the repository root, use a pipefail pipeline:

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
operator correlation of captured deployment ID through the #201 exact-deployment
procedure above can add `deployment_timestamp` and stronger Railway evidence;
that enrichment is separate from permission to send acceptance traffic.

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
API_BASE_URL=https://staging.tailtag.app make api-smoke
```

For the guarded configuration fingerprint rerun, use the exact target and
confirmation. It emits only resource/configuration fingerprints, never values:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM=run-tailtag-environment-fingerprint \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment staging -- \
uv run --project services/api --locked --no-sync python scripts/api_environment_fingerprint.py
```

Run the corresponding Development command in the same review window before
comparing the labeled outputs:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM=run-tailtag-environment-fingerprint \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment development -- \
uv run --project services/api --locked --no-sync python scripts/api_environment_fingerprint.py
```

For the synthetic R2 upload/read/delete/absence check, use the same explicit
target. Its cleanup and final absence check are mandatory:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-staging-media-storage-smoke \
railway run --project 85324de4-be6a-49c3-a3f9-6cac13877849 --no-local --service api --environment staging -- \
make api-media-storage-smoke
```

Do not share object keys, bucket names, presigned URLs, signatures, response
material, or rendered variable values. A failed deletion or absence check is a
failure, not a warning.

### Clerk authenticated smoke

This is the only Staging Production-Clerk live entry point. From a TTY, first
disable clipboard history and synchronization before copying any Backend secret,
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
make api-staging-auth-smoke
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

## 2026-09-16 sanitized parity record

The observed target has successful `api` and `Postgres` deployments, a ready
5000 MB Staging PostgreSQL volume, disabled Staging autodeploy, canonical HTTPS
HTTP smoke success, and only `development` and `staging` Railway environments.
The following is the maintained intentional-parity record; it does not disclose
private addresses or secrets.

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
