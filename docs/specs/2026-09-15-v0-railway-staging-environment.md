# V0 Railway Staging environment

**Issue:** [#200 — Establish the V0 Railway Staging environment](https://github.com/TailTag-Game/tailtag/issues/200)

**Parent:** [#197 — V0 Backend Operational Readiness](https://github.com/TailTag-Game/tailtag/issues/197)

**Status:** Approved and frozen for implementation

## Goal

Establish one persistent Railway environment named `staging` as TailTag's
canonical production-rehearsal backend target. Staging must use isolated
PostgreSQL, Clerk, R2, runtime configuration, secrets, public networking, and
synthetic state while Development remains the mutable contributor/integration
environment and no TailTag Production environment exists.

## Approved design

### Clerk isolation

Staging uses a separate Clerk application named `TailTag Staging`. It must not
share the Development Clerk application or instance, users, credentials, JWT
verification material, backend keys, or mutable Clerk configuration.

The dedicated Staging Clerk application's Production instance is the approved
instance. This exercises Clerk's production-style session and authentication
behavior and does not create or launch a TailTag Production environment. Only
clearly synthetic users may exist in the Staging Clerk application.

Clerk requires a domain for a Production instance. The approved canonical
Staging hostname is `staging.tailtag.app`. Before provisioning the Clerk
Production instance or completing Railway public-domain configuration, discover
the authoritative nameservers for `tailtag.app`, identify their DNS provider and
owning account, and verify access to create Staging records. Record only the
provider and sanitized ownership/boundary information. Do not move the zone or
change nameservers as part of #200 without a separate explicit decision.
Required DNS records must be created exactly as Clerk supplies them. If
maintainers cannot inspect and modify authoritative DNS for the approved
Staging domain, implementation stops; it must not fall back to a Clerk
Development instance or reuse the existing TailTag Development Clerk application.

### Bootstrap authentication proof

Clerk Production instances do not support Backend `sessions.create`. That flow
is removed, not retained as a fallback. A maintainer instead signs a new,
smoke-only synthetic session into the dedicated application's hosted Production
Account Portal. The opt-in repository command validates that selected session
and a freshly issued ordinary browser session JWT, exercises the existing
Staging `/api/me/` contract, and revokes only the selected session.

Before final replacement test authorship or implementation, complete dedicated
Clerk Production provisioning and authoritative DNS verification, establish the
canonical instance-ID fingerprint, and prove the hosted portal can safely yield
a fresh ordinary JWT through `getToken({skipCache:true})`, without a template.
If safe supported token retrieval is unavailable, stop at that concrete
provider limitation and replan. Do not add a TailTag frontend, Backend token
minting, tickets/redemption client, undocumented cookie/origin protocol, custom
JWT template, new Frontend API client, or weaker Clerk boundary.

The exact confirmed hosted Staging Account Portal origin is the current
**bootstrap Staging authentication validation origin**. For #200 it is the sole
permitted authorized party. A token must first pass cryptographic verification
through the unchanged `ClerkSessionVerifier`; only then may its genuine `azp`
be checked for exact equality with that confirmed portal origin. Development,
missing, and arbitrary origins fail closed. This does not freeze TailTag's
permanent V0/mobile client-origin architecture: the canonical client-origin and
authorized-party configuration may be deliberately replaced when real V0 client
integration establishes its production semantics. Document that distinction;
do not add application behavior or bypass the verifier to make the token pass.

The smoke-tool maximum ordinary token lifetime is a named provider-safety
constant, initially 60 seconds, with a source comment referencing Clerk's
documented ordinary-token behavior. Require valid integer `iat`/`exp`,
`exp > iat`, a currently unexpired token, exact verified selected `sid`, exact
synthetic `sub`, and ordinary session-token form. This bound may be deliberately
updated if provider behavior changes without changing TailTag's domain/API
authentication contract. Fresh issuance via `getToken({skipCache:true})` remains
an operator requirement, not Backend token minting.

Confirmed bootstrap target identities from dedicated Production provisioning:

- `STAGING_CLERK_INSTANCE_FINGERPRINT`: `eb6daf25d12b85eb` (SHA-256 of the
  confirmed dedicated Production instance ID, first 16 lowercase hex characters).
- `STAGING_CLERK_PORTAL_ORIGIN`: `https://accounts.staging.tailtag.app`.

Clerk's supported Secondary application domain mode preserves the
`staging.tailtag.app` boundary, including `clerk.staging.tailtag.app` and
`accounts.staging.tailtag.app`, instead of reserving root-level authentication
hostnames. This origin remains bootstrap-only as described above; neither
identity accepts runtime overrides.

### Railway boundary

Create a persistent environment named `staging` in the existing `TailTag`
Railway project. It owns isolated environment instances and configuration for:

- `api`;
- PostgreSQL and its volume;
- runtime variables and secrets;
- public backend networking; and
- every other mutable dependency scoped to the Railway environment.

Duplicating `development` is permitted only to stage the existing service
topology and configuration for review. No duplicated service may deploy until
every copied variable and dependency has been reviewed and every
Development-owned resource or credential has been replaced with a
Staging-owned equivalent.

Approved bootstrap recovery: CLI 5.57.2 duplication unexpectedly deployed both
services before review. Both deployments were removed after operator approval;
the initial interval is not evidence of isolation. Retain `staging`, do not
duplicate again, and verify no-deploy controls before changing copied
configuration. Disable Staging GitHub autodeploy and reconcile queued deployments.
Every configuration operation must use a verified staged/no-deploy path.
Replace and review all copied credentials/configuration while both services
remain offline, using verified no-deploy controls. Then explicitly wipe only
the current Staging PostgreSQL volume instance as its dependency bootstrap:
the supported dashboard wipe clears its data/backups. If the previously stopped
PostgreSQL instance remains stopped, deploy its existing configured image once.
Independently generated Staging PostgreSQL credentials must already be configured
before this action. Obtain destructive confirmation at action time. Do not use
unverified detach/add patch semantics, delete the shared/project-level volume
definition, or touch Development's instance. Verify the existing source/root/
Dockerfile path rather than assuming CLI duplication preserved it. Preserve
sanitized premature-deployment/containment evidence. Development credential
rotation or other Development mutations require a separate explicit decision.

Development remains the mutable contributor/integration environment. No
Railway environment named `production` may be created.

### Bootstrap deployment boundary

Issue #200 may perform the minimum one-time deployment needed to establish and
validate Staging. It uses the existing GitHub source, Dockerfile build,
pre-deploy migration, Gunicorn start, and readiness path, explicitly targeting
`staging`.

Staging GitHub autodeploy is disabled before the bootstrap deployment. The
bootstrap commits reviewed staged configuration with deployment suppressed,
establishes the isolated PostgreSQL dependency through its existing image path,
then uses the existing **Deploy the repo TailTag-Game/tailtag** entry point once
against connected `main`, explicitly in `staging/api`. It leaves the source
connection in place without defining the repeatable promotion workflow owned
by #202. No second long-term deployment mechanism is introduced.

Issue #200 does not implement immutable build identity (#201), repeatable
controlled Staging promotion (#202), or expanded health/target-safety behavior
(later operational-readiness work).

### Public identity

The canonical Staging API base URL is `https://staging.tailtag.app`. Configure
that custom public domain on `staging/api` only after authoritative DNS access
is established. Document it as the supported Staging target and require
validation and automation to select it explicitly.

The URL is public, not secret. Private Railway domains and internal URLs must
not be recorded. No endpoint, response header, environment dump, or
version/metadata API is added for #200.

### PostgreSQL

Staging uses the duplicated environment's isolated Railway-managed PostgreSQL
service instance and volume. The `api` service uses the environment-local
reference `${{Postgres.DATABASE_URL}}`; no rendered database URL is copied or
recorded.

### R2 media

Staging uses one new private R2 bucket whose name begins
`tailtag-staging-media-` and one new account API token named
`TailTag Railway Staging`. The token has only **Object Read & Write** permission
and applies only to the Staging bucket.

The Development bucket and credential, public bucket access, unrelated R2
credentials, and account-wide access are prohibited. Railway Staging receives
the existing five `MEDIA_STORAGE_*` variables with Staging-owned values.

### Runtime configuration

Staging must define and review this application-variable allowlist before its
first deployment:

- `DATABASE_URL`, as the Staging `Postgres` reference;
- `DJANGO_SECRET_KEY`, generated independently for Staging;
- `DJANGO_ALLOWED_HOSTS`, derived from the Staging public hostname and Railway
  health-check host;
- `DJANGO_CSRF_TRUSTED_ORIGINS`, derived from the Staging public HTTPS origin;
- `CLERK_AUTHENTICATION_ENABLED=true`;
- `CLERK_JWT_KEY`, from the `TailTag Staging` Production instance;
- `CLERK_AUTHORIZED_PARTIES`, containing only the approved Staging Clerk
  hosted Account Portal origin for current bootstrap validation, not a permanent
  V0/mobile architecture decision, API destination, or Development tooling origin;
- `MEDIA_STORAGE_ENDPOINT_URL`;
- `MEDIA_STORAGE_BUCKET_NAME`;
- `MEDIA_STORAGE_REGION`;
- `MEDIA_STORAGE_ACCESS_KEY_ID`; and
- `MEDIA_STORAGE_SECRET_ACCESS_KEY`.

Railway-provided `RAILWAY_*` variables and `PORT` remain platform-owned. Any
other copied application variable is a stop-and-review condition before
deployment.

### Documentation

The maintained Staging runbook is `docs/development/staging.md`.
`docs/development/backend-delivery-operations.md` remains focused on the
mutable Development environment and links to the Staging runbook. Architecture
documentation records the new boundary without defining #201 or #202.

### Isolation evidence

Evidence must demonstrate dependency inequality and successful Staging use
without disclosing credentials or private data. It may contain only safe
environment/resource types, the expected `staging` identity, fixed PASS/FAIL
stages, safe public identifiers, or short one-way fingerprints.

Evidence must never contain secret values, access keys, Clerk secret keys,
JWTs, session tokens, database URLs or passwords, private/internal URLs, full
environment dumps, personal users, or non-synthetic domain data.

## Acceptance Contract

1. A persistent Railway `staging` environment exists in the existing TailTag
   project with isolated `api`, PostgreSQL, volume, variables, secrets,
   deployment, and public networking instances.
2. The canonical Staging API URL is stable, public, distinct from Development,
   documented, and satisfies the existing HTTP smoke contract after the
   one-time bootstrap deployment.
3. The deployed Staging backend reaches its Staging PostgreSQL through the
   environment-local reference; safe Railway resource identity evidence and a
   successful readiness query prove that it is not Development PostgreSQL.
4. `TailTag Staging` exists as a separate Clerk application, its Production
   instance is configured through verified Staging-domain DNS, it contains only
   synthetic users, and a bounded live synthetic session authenticates to the
   Staging `/api/me/` path through the unchanged TailTag verifier.
5. A dedicated private Staging R2 bucket and bucket-scoped Object Read & Write
   account token exist, their safe identities differ from Development, and the
   repository-owned synthetic upload/read/delete/absence check passes against
   Staging.
6. Safe fingerprints and platform resource identities show that Staging does
   not inherit Development database, Django secret, Clerk verification
   material, R2 bucket, or R2 credential values. Shared non-secret platform
   facts such as the R2 account endpoint may match when ownership remains
   isolated.
7. Staging contains only synthetic TailTag, Clerk, and media state. Development
   remains the mutable contributor/integration environment. No TailTag
   Production environment or production data is created.
8. `docs/development/staging.md` records the supported target, dependency
   boundaries, bootstrap entry point, safety limits, parity expectations, and
   every intentional Development/Staging/future-Production difference without
   secrets or private URLs.
9. Staging autodeploy is disabled after bootstrap; #200 adds no promotion
   workflow, deployment workflow, runtime metadata surface, expanded health
   behavior, reset/reseed mechanism, observability system, recovery drill, or
   unrelated application behavior.

## Test Surface Contract

- Ordinary tests remain offline. External calls are represented by narrow
  injected runtimes/fakes and tests fail if unexpected network access occurs.
- `scripts/api_media_storage_smoke.py` may be narrowed from Development-only to
  exactly two permitted targets: `development/api` with its existing explicit
  confirmation and `staging/api` with a distinct explicit confirmation.
  `production` and every other target remain rejected before Django or storage
  initialization.
- A new `scripts/api_staging_auth_smoke.py` is the only Staging production-Clerk
  live entry point. Secret, session ID, and token inputs are hidden TTY-only;
  none is accepted through arguments, environment, config, stdin pipe, or
  credential storage. Exact prompts are `Clerk Staging Production secret:`,
  `Clerk Staging smoke-only session ID:`, and `Clerk Staging session token:`.
  Require `sk_live_`, authoritative `environment_type=production`, and exact
  canonical instance binding before synthetic-user lookup or session selection.
  Emit fixed sanitized stages only; perform no Backend session/token creation.
- The public operator target constant `STAGING_CLERK_INSTANCE_FINGERPRINT` is
  the 16-character lowercase SHA-256 prefix of the dedicated Production
  `instance.id`, derived after dashboard ownership verification. Missing,
  malformed, or different instance IDs fail before session selection or any
  revocation. No arguments or environment values may override that binding.
- After explicit smoke-only session-ID selection, authoritative
  `sessions.get(session_id=...)` must return the exact ID, selected synthetic
  `user_id`, status `active`, and no impersonation actor. Accept only null or
  the installed SDK's genuine `Unset` sentinel type (including copied defaults)
  as no actor; reject unrelated falsy values and actual actors. Do not enumerate
  sessions or perform any provider mutation before successful selection. Only
  then take cleanup ownership; every subsequent failure, including token
  prompting/verification failure, attempts that session's revocation in
  `finally`. Require the revoke response's exact ID and status `revoked`.
  Cleanup failure takes diagnostic priority even alongside a primary failure.
- Cryptographically verify the unchanged browser token first, then check its
  genuine `sid`/`sub`/`azp` and the named provider-safety lifetime bound. The
  confirmed portal-origin operator guard permits exactly the current bootstrap
  origin, not a configurable arbitrary origin or multiple-party allowlist.
  Make one no-redirect canonical `/api/me/` Bearer request. Untrusted claims
  never establish session ownership or cause a provider mutation.
- Disable automatic retries, use bounded provider timeouts, disable provider
  HTTP debug logs/proxies/redirects, close HTTP clients, and drop credential,
  token, selected-session and user references on terminal paths. Do not print
  or retain those inputs in logs, evidence, URLs, storage, or shell history.
  Direct transient clipboard-to-TTY transfer must not print the JWT or use
  clipboard history/synchronization; clear the clipboard after pasting.
- Before authoritative session selection, operator sign-out/revocation remains
  necessary if setup or selection fails. After selection, command cleanup is
  mandatory. A failed revoke requires explicit manual remediation. Offline
  verification can still accept an issued JWT until its short expiry; do not
  claim immediate token invalidation after revocation or change application
  authentication behavior for #200.
- The Staging-auth command requires both explicit API target inputs to be
  exactly `https://staging.tailtag.app`, without a trailing slash. It takes the
  synthetic user ID from `CLERK_STAGING_SMOKE_USER_ID` and checks that user's
  public metadata includes `tailtag_environment=staging` and
  `tailtag_synthetic=true` (the exact boolean). These are operator markers, not
  TailTag product-schema changes. The concrete command runtime may inject a
  narrow Clerk factory, the existing verifier, and a no-redirect HTTP opener
  for offline tests. Tests may monkeypatch public canonical instance/origin
  target constants to their synthetic provider values, but no production
  constructor/config override is added. No application API or verifier seam
  is added. Final replacement tests/implementation remain gated on live portal
  feasibility; prior unsupported-flow draft tests are not the new contract.
- A new `scripts/api_environment_fingerprint.py` may emit only labeled,
  truncated SHA-256 fingerprints for the approved isolation fields after exact
  Railway environment/service/confirmation guards. It never emits source
  values, accepts `production`, or enumerates the environment.
- The existing credential-free `scripts/api_smoke.py`, production settings,
  application endpoints, database schema, Clerk verifier, and media-storage
  implementation are unchanged.
- Live checks are opt-in maintainer operations and are not added to ordinary CI,
  application startup, health checks, or deployment hooks.

## Scope Guard

**Outcome:** One isolated, documented, and evidenced Railway Staging boundary
that later operational work can trust.

**Non-goals:** #201 build identity, #202 promotion automation, expanded health
contracts, reset/reseed, backup/restore, observability, load simulation,
Production, frontend work, or product behavior.

**Expected repository files:** the three approved operator scripts and their
focused tests, root Makefile/tooling registration, the dedicated Staging
runbook, and small architecture/Development-runbook cross-links.

**Proof:** offline acceptance tests; repository deterministic gates; sanitized
Railway, Clerk, PostgreSQL, R2, configuration-fingerprint, HTTP, authenticated,
and storage evidence; independent specification/code review; final diff review.

## Live discovery baseline

Read-only discovery on 2026-09-15 found:

- Railway project `TailTag` has only `development`, with `api` and `Postgres`;
- the inspected TailTag Clerk organization has only the existing `TailTag`
  Development application/instance and no Production instance;
- Cloudflare R2 has only the dedicated TailTag Development media bucket and
  its active bucket-scoped Object Read & Write account token; and
- the accessible Cloudflare account has no managed DNS zones, so authoritative
  access to `tailtag.app` remains an execution blocker until verified.

These observations contain no secret values and are not substitutes for fresh
pre-mutation discovery during implementation.

Initial DNS discovery on 2026-09-16 returned `NXDOMAIN` and registry RDAP HTTP
404. After the maintainer registered `tailtag.app`, fresh authoritative `.app`
DNS and public resolver `1.1.1.1` confirmed delegation to
`curitiba.ns.porkbun.com`, `fortaleza.ns.porkbun.com`,
`maceio.ns.porkbun.com`, and `salvador.ns.porkbun.com`.

DNS ownership/access check: PASS. The maintainer's authenticated Porkbun account
lists `tailtag.app` and exposes DNS management and an editable Add Record form
with a submit control. The empty form was canceled; no DNS mutation was made.
The DNS-management provider is Porkbun, whose UI labels the underlying service
"DNS Powered by Cloudflare". This does not establish zone access in the separate
Cloudflare account inspected earlier. The DNS gate is cleared; no zone move or
nameserver change is required or authorized. Recheck account/target access at
mutation time. Account identifiers, credentials, and session data are omitted.

Browser tooling previously surfaced Cloudflare login-session material. Treat
that session as compromised: invalidate it and authenticate cleanly before any
live Cloudflare mutation. Do not retain the material in evidence or artifacts.
On 2026-09-16 the maintainer confirmed revocation of the old session and clean
authentication. A sanitized browser check confirmed an authenticated dashboard
with the expected `Finn the Panther` account selected. This clears the session
safety gate; it does not independently prove token revocation or absence of
prior misuse. Recheck account and resource boundaries before mutation.

## Primary platform references

- [Clerk Production session-creation restriction](https://github.com/clerk/clerk-sdk-python/blob/main/docs/sdks/sessions/README.md#create)
- [Hosted Account Portal](https://clerk.com/docs/guides/account-portal/overview)
- [Normal browser session tokens](https://clerk.com/docs/js-frontend/reference/objects/session)
- [Fresh token retrieval](https://clerk.com/docs/guides/sessions/force-token-refresh)
- [Ordinary token claims and origin](https://clerk.com/docs/guides/sessions/session-tokens)
- [Clerk environments and separate staging applications](https://clerk.com/docs/guides/development/managing-environments)
- [Clerk testing and normal session-token flow](https://clerk.com/docs/guides/development/testing/overview)
- [Railway isolated environments and staged duplication](https://docs.railway.com/environments)
- [Railway staged changes and dependency ordering](https://docs.railway.com/deployments/deployment-actions)
- [Railway disabling GitHub autodeploy](https://docs.railway.com/deployments/github-autodeploys)
