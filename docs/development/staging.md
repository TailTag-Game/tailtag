# Staging runbook

This is the maintainer runbook for TailTag's persistent Railway **Staging**
backend: a controlled production-rehearsal target for maintainers with the
needed Railway, Clerk, and Cloudflare access. It is separate from the mutable
contributor/integration [Development runbook](backend-delivery-operations.md).
It covers the controlled promotion procedure below. It is not a production SRE
guide or a source of credentials.

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
