# Staging runbook

This is the maintainer runbook for TailTag's persistent Railway **Staging**
backend: a controlled production-rehearsal target for maintainers with the
needed Railway, Clerk, and Cloudflare access. It is separate from the mutable
contributor/integration [Development runbook](backend-delivery-operations.md).
It is not a production SRE guide, a deployment-promotion procedure, or a
source of credentials.

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

Do not repeat or generalize that bootstrap into a routine. In particular, this
runbook establishes neither #201 immutable build identity nor #202 repeatable
promotion behavior. It adds no reset/reseed process, observability system,
recovery drill, health behavior, or new deployment mechanism.

The original CLI duplication unexpectedly deployed inherited configuration
before review. Those deployments were stopped, configuration was replaced while
offline, and the Staging volume was wiped before the supported bootstrap. That
initial interval is not proof of isolation and is not asserted to be free of
prior exposure. The current reviewed isolated bootstrap and the evidence below
are the usable proof.

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

### HTTP, configuration, and media

Run the existing credential-free HTTP smoke only against the canonical public
URL. It checks the existing health, schema, and docs contract; it does not
deploy or change Staging.

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
