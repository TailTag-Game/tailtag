# Synthetic simulation identity pool

Issue: [#219](https://github.com/TailTag-Game/tailtag/issues/219) (SIM-2).
Parent: #199. Builds on the #218 harness
([spec](2026-10-02-headless-simulation-harness.md)). Amends, if approved, the
#200 Staging contract ([spec](2026-09-15-v0-railway-staging-environment.md)).
Later consumers: #220 (fixtures), #221 (journeys), #222 (reconciliation),
#223 (cleanup), #228 (execution host).

## Status and phase ledger

**APPROVED and frozen (2026-10-02).** The maintainer approved the design in
this order:

1. **Approved:** Staging Clerk stays synthetic-only, including through the
   field beta. The field beta gets its own environment and Clerk application.
2. **Approved for the D3 proof only:** D1 and D2, limited to one ticket for one
   existing synthetic user, verified locally, then revoked. No Staging
   configuration change.
3. **D3 passed (2026-10-02).** See the D3 results below.
4. **Approved:** the full #200 amendment (D1 and D2, with the cookie carrier
   named), the #218 amendment (D5), and the lease table (D7). The acceptance
   contract below is frozen.

Execution: STANDARD EXPANDED. Assurance: SECURITY (Staging authorized-party
boundary, Clerk secret handling, session material), DATA INTEGRITY (concurrent
allocation), RELIABILITY (broken-identity recovery).

Completed (2026-10-02): scope review, Clerk documentation research, repository
evidence review, a Development minting spike (below), and an independent
security challenge. Its verdict was ACCEPTABLE WITH CONDITIONS, holding only
while the Staging Clerk application contains synthetic users only. Its four
MEDIUM and three LOW findings are incorporated below.
The D3 Staging feasibility proof then passed, and the maintainer approved the
full amendments. Pending: independent test authorship, implementation, and
review. Changing Staging's live `CLERK_AUTHORIZED_PARTIES` is a separate
operational step that needs explicit maintainer go-ahead when implementation
reaches it.

**Precondition.** #200 requires that only clearly synthetic users exist in the
Staging Clerk application, and the maintainer confirmed this holds through the
field beta. If that ever changes, D1 and D2 must be re-reviewed and the tooling
origin removed before any real person signs in, because the Staging secret can
open a session for any user.

Implementation sequencing:
[implementation plan](2026-10-02-synthetic-identity-pool-implementation-plan.md).

## Objective

Provide a durable pool of synthetic Clerk/TailTag identities on Staging that a
run can allocate, use through the real public authentication boundary, and
release, without per-run account churn, operator token entry per identity, or
credential exposure.

## Evidence

All evidence is sanitized. No credential, Clerk user ID, session ID, or token
is retained.

- **Target is Staging only.** #199 states Development is not a load-test
  target and Production is not a synthetic-traffic target.
- **Backend minting cannot satisfy TailTag verification.** The #99 spike
  ([spec](2026-08-18-authentication-test-and-backend-developer-tooling.md))
  found that Backend API session creation yields tokens without `azp`. A
  2026-10-02 spike on the Clerk Development instance extended this: on a
  session created through the ticket and Frontend API flow (whose own token
  carried the tooling `azp`), Backend API `POST /v1/sessions/{id}/tokens`
  honored `expires_in_seconds` (600 requested, 600 observed; 60 by default) but
  the token had **no `azp`**, and the unchanged `ClerkSessionVerifier`
  rejected it. The Clerk SDK rejects a missing `azp` whenever authorized
  parties are configured.
- **The ticket and Frontend API flow works on Development.** A Backend API
  sign-in ticket redeemed through the Frontend API with an explicit `Origin`
  yields an ordinary 60-second session token whose `azp` equals that origin
  (`scripts/clerk_development_session.py`). Development authorizes the exact
  pair of that tooling origin and its pinned hosted portal origin
  ([amendment](2026-09-24-replacement-development-portal-auth.md)).
- **Staging forbids that flow today.** #200 forbids Backend token minting,
  tickets and redemption, a Frontend API client, undocumented cookie or origin
  protocols, and any weaker Clerk boundary. Its sole authorized party is the
  hosted portal origin, explicitly bootstrap-only and replaceable.
- **Clerk Production instances** do not offer Backend session creation.
  Sessions last 7 days by default. The Backend API allows 1000 requests per 10
  seconds and 10 user-data updates per user per 10 seconds. Clerk bills
  monthly retained users (users returning more than a day after sign-up);
  50,000 are included per application. Frontend API rate limits and whether a
  non-browser client can redeem tickets on a Production instance are
  undocumented.
- **No synthetic marker exists in TailTag.** `accounts.User` has only
  `clerk_user_id`, created on first authenticated request
  (`accounts/resolution.py`). There are no Clerk webhooks.
- **The rehearsal reset fails closed** if users outside its registered closure
  touch the baseline Convention or fursuits (`rehearsal/reset.py`).

## Decisions

### D1 Staging token acquisition — APPROVED (amends #200)

Options:

- A. Backend minting. Rejected: no `azp` (Evidence).
- B. Operator portal sign-in per identity. Rejected: does not scale beyond a
  handful of identities and needs a human per run.
- C. Weaken verification to accept a missing `azp`. Rejected: removes a
  verifier guarantee for every Staging token.
- D. Password sign-in per identity with passwords derived from a pool key.
  This keeps the Staging secret out of routine runs, but Production bot and
  new-device protection probably block it, and it adds a credential per user.
  Considered, not recommended.
- E. **Recommended.** Follow the shape of the Development mechanism: SETUP
  creates a short-lived single-use sign-in ticket per allocated identity
  through the Backend API and redeems it through the Staging Frontend API with
  a dedicated synthetic tooling origin. The resulting ordinary session token
  carries that origin as `azp`.

E is not a copy of Development. The Development flow relies on the
development-browser mechanism (`/v1/dev_browser`), which Production instances
do not offer. On Staging, client state needs a different carrier. That is the
"cookie protocol" #200 forbids, so the amendment names the one permitted
carrier. D3 established it: the Frontend API client cookie, held in an
in-memory cookie jar, with `Origin` set to the tooling origin. Native mode is
excluded because its tokens carry no `azp`.

E requires amending #200 to permit, only within the simulator's privileged
SETUP phase: Backend sign-in ticket creation, ticket redemption through the
Frontend API, the named client-state carrier, and the one pinned tooling
origin. Sending a tooling origin that TailTag owns is not the origin spoofing
#218 decision 1 forbids, which means presenting another party's origin, such
as the portal's. Custom JWT templates, Backend token minting, and verifier
changes remain forbidden.

Before creating any user or ticket, SETUP pins the Staging instance
fingerprint. Before each ticket, it re-reads the user and requires the existing
synthetic markers, the pool markers (D6), and the `external_id` pattern,
failing closed otherwise, as `scripts/api_staging_auth_smoke.py` does today. A
wrong user ID from a bug or a tampered lease therefore cannot open a session
for a smoke, rehearsal, or other non-pool identity.

### D2 Staging authorized parties — APPROVED (amends #200)

Staging `CLERK_AUTHORIZED_PARTIES` becomes the ordered exact pair of the hosted
portal origin and one synthetic tooling origin, both pinned as literals in the
canonical-phase Staging readiness check (`services/api/health/configuration.py`),
which already compares the portal origin as a literal. The `staging-next`
candidate phase is unchanged. No suffix,
wildcard, or caller-supplied value. Tokens still pass the unchanged verifier
first.

The tooling origin is an HTTPS hostname under `staging.tailtag.app` with no DNS
record and no wildcard record covering it. Proposed:
`https://simulator.staging.tailtag.app`. On 2026-10-02 it did not resolve.
`tailtag.app` has a wildcard record (`*.tailtag.app`, the registrar's parking
host), so names directly under `tailtag.app` are unsafe. Because
`staging.tailtag.app` exists, that wildcard does not cover names beneath it. A
wildcard under `staging.tailtag.app` must never be added. Script served from that origin could
use a signed-in browser's same-site Clerk cookie, so a dangling or wildcard
record must never exist. It differs from Development's origin as defense in
depth only, since separate instance signing keys already keep Development
tokens from verifying on Staging. The amendment states whether Clerk's
`allowed_origins` instance setting must change, as D3 will show.

Security consequence, confirmed by the challenge: the tooling origin opens no
new way to get a session. Minting any token needs the user's Clerk client
credential, which already gives full control of the session under the portal
`azp`, and any party holding the Staging Clerk secret can already create
tickets for any Staging user. `azp` is therefore a label, not proof of where a
token came from. It must never drive authorization, quotas, or telemetry trust.
The tooling origin's value is separation: removing it from authorized parties
is an independent kill switch for simulator tokens. D2 is a two-way door.

### D3 Staging feasibility proof before any build — PASSED

Before test authorship, run one bounded, maintainer-executed proof against
Staging with the existing synthetic smoke user, after pinning the instance and
checking the user's synthetic markers: ticket creation, Frontend API redemption
with the tooling origin, one ordinary token, then session revocation. The token
is checked with the unchanged `ClerkSessionVerifier` locally, using the Staging
JWT key and the tooling origin as the only authorized party. Staging's own
`CLERK_AUTHORIZED_PARTIES` is not changed for the proof, so `/api/me/`
acceptance is proven only after the full amendment. Output only booleans and
lifetimes, as in the Development spike.

The proof also establishes which client-state carrier Production redemption
uses (D1), and whether Clerk's `allowed_origins` must list the tooling origin.

Stop conditions: bot protection that requires a browser challenge, a Frontend
API that refuses non-browser clients or offers no documented client-state
carrier, or `azp` not equal to the tooling origin. On any stop condition, record on #219
that automated Staging tokens are not available through supported mechanisms,
and replan. Clerk testing tokens may be used only if Clerk documents them for
this case on Production instances.

**Results (2026-10-02, maintainer-run, sanitized).** A throwaway script ran
against Staging with the existing smoke user and was then deleted. Every
session it created was ended from the client side and revoked through the
Backend API. A final sweep found no new sessions left, and unused tickets were
revoked. Each variant used one 60-second ticket. Tokens were checked locally
with the unchanged `ClerkSessionVerifier`, with
`https://simulator.staging.tailtag.app` as the only authorized party.

| Variant | Outcome |
| --- | --- |
| Native mode (`_is_native=1`, client token in `Authorization`), no `Origin` | Redemption completed and tokens refreshed, but `azp` was absent; the verifier rejects it. |
| Native mode with `Origin` | Refused at sign-in: `origin_authorization_headers_conflict`. |
| Browser-style client cookie with `Origin` set to the tooling origin | Redemption completed. `azp` equaled the tooling origin; `sid`, `sub`, and the 60-second lifetime were correct; the verifier accepted it. After the first token expired, the same session issued a new accepted token. The client-side session end succeeded. |

Conclusions:

- **Carrier:** the Frontend API client cookie set by `POST /v1/client`, held in
  an in-memory cookie jar and sent with `Origin` set to the tooling origin and
  the `Clerk-API-Version: 2026-05-12` header. Sending the version as the
  `__clerk_api_version` query parameter as well was refused with
  `api_version_invalid`.
- **No `allowed_origins` change** was needed for the cookie flow. No bot
  challenge occurred.
- **Refresh works** after expiry from the same session, which supports D4.
- `/api/me/` acceptance remains unproven until Staging's authorized parties
  change under the full amendment.

Two incidental findings:

- The Staging Clerk instance fingerprint pinned in
  `scripts/api_staging_auth_smoke.py` (`eb6daf25d12b85eb`) belongs to the
  retired Staging generation. The current instance, identified by its single
  primary domain `staging.tailtag.app` and Frontend API
  `https://clerk.staging.tailtag.app`, has fingerprint `328b851879c17392`. Pool
  tooling pins that value and also checks the domain.
- The existing Staging smoke user lacked the #200 synthetic markers until the
  maintainer added them during the proof. Provisioning must set markers itself
  and never assume an existing user carries them.

### D4 Token lifetime and refresh

Ordinary tokens last 60 seconds and the Frontend API offers no lifetime input.
Each allocated identity keeps one Clerk session for the run and obtains a fresh
ordinary token from it before the current one expires. Sessions are revoked at
release. Backend minting of longer tokens is not used (Evidence).

### D5 Phase boundary and secret handling — APPROVED (amends #218)

- The Staging Clerk secret key is entered through the existing hidden TTY
  prompt in SETUP only, never stored in a file, environment variable, argument,
  log, or report, and is discarded when SETUP ends. #219 never stores it. #228
  may not store it on a run host without its own approved secret-handling
  decision: the key controls the whole Staging Clerk instance, and exposure
  forces a rotation that takes Staging authentication down. Persisting it is
  an unapproved one-way door.
- SETUP calls the Clerk Backend and Frontend APIs with httpx. The Clerk SDK
  stays excluded from the simulator environment (#218 A-10 unchanged).
- SIMULATION receives, per virtual user, an opaque token provider that returns
  only a current ordinary token. Refresh runs in a setup-owned component
  during SIMULATION.
- The client-state carrier is a refresh credential that lives as long as the
  session (7 days by default). Only the refresher holds it, in memory only. The
  Frontend API and TailTag API use separate httpx clients, and the API client
  has cookies disabled. The Frontend API host is pinned, with `trust_env=False`
  and no redirects. Provider HTTP loggers are suppressed. Exceptions use fixed
  stages and are raised `from None`. No credential appears in `repr`.
- Release ends sessions through the Frontend API with each user's own
  credential, so the secret is not needed after SETUP. As a backstop,
  allocation revokes all of an identity's active sessions in SETUP, closing
  any session a crashed run left open.
- The phase boundary is code discipline within one process. These controls
  prevent leakage; they are not process isolation.
- This amends #218 decision 7 (phases run strictly in sequence) and A-4
  (SIMULATION receives only a client bound to one origin and token): SIMULATION
  would receive token providers instead of a single token, and a setup-owned
  refresher would run concurrently with it.

### D6 Synthetic marking

Each pool identity carries the existing Staging synthetic markers in Clerk
`public_metadata` (`tailtag_synthetic: true`, `tailtag_environment:
"staging"`), checked exactly as the Staging smoke checks them, plus pool fields
`tailtag_pool: "<pool name>"` and `tailtag_pool_index`. It also has a stable
`external_id` such as `sim-pool-<pool>-<index>`, and a recognizable identifier
on a TailTag-controlled domain or a username, depending on the Staging
instance's enabled identifiers (open). No TailTag schema change. Users are
created with `skip_password_requirement`.

### D7 Allocation and lease store — APPROVED

Options:

- A. Clerk `private_metadata` leases. Rejected: no compare-and-set, and the
  per-user update limit is 10 per 10 seconds.
- B. A lock file on the operator's machine. Rejected: unsafe once runs come
  from more than one machine (#228).
- C. **Recommended.** A Postgres lease table in a simulation-only Django app,
  written only by privileged management commands that run inside the Staging
  API container through pinned `railway ssh`, as `api-staging-reset-ssh` does.
  Allocation uses `SELECT ... FOR UPDATE SKIP LOCKED`; each lease has a run ID,
  expiry, and heartbeat; expired leases are reclaimable. The commands refuse
  to run unless the #203 identity is `staging`. The simulator itself keeps no
  database driver.

`railway run` is not used: it runs locally with Staging variables, and Staging
Postgres has no public TCP proxy (`docs/development/staging.md`). Enabling a
public database proxy, or loading Staging variables such as `DATABASE_URL`, the
Django secret key, or storage keys into the simulator or its host, is
forbidden.

C adds a model and migration on Staging and a privileged channel from the run
host. How the #228 external host obtains that channel is open.

### D8 Profile initialization

At allocation, SETUP verifies each identity's profile against the V0 invariant
(handle, display name, and onboarding timestamp all set or all null). A
never-onboarded identity completes onboarding once through the public
`PUT /api/profile/` with its own token, using the pool handle `sp_<pool>_<index>`
(handles allow only lowercase letters, digits, and underscores).
Profiles then stay onboarded. Leftover run-specific state is reported and the
identity quarantined; deleting it belongs to #223.

### D9 Lifecycle and recovery

- **Provision or expand:** an idempotent privileged command brings the pool to
  a target size, creating only missing identities.
- **Insufficient pool:** fail before any allocation, reporting needed and
  available counts only.
- **Broken identity:** a Clerk user that is missing, banned, or locked, a
  failed ticket or redemption, a verifier rejection, or profile drift
  quarantines the identity and excludes it from allocation. Recovery is
  documented: inspect, repair or retire, re-admit.
- **Crashed run:** leases expire and become reclaimable. Their sessions are
  revoked when the identities are next allocated (D5), and otherwise expire
  under Clerk's session lifetime.

### D10 Pool size and cost

Pool size is a provisioning parameter, default 50, well inside Clerk's included
retained users. Before raising pool size beyond 1000, measure the Frontend API
refresh load (about one token request per identity per 50 seconds) against
Clerk limits.

### D11 Rehearsal baseline disjointness

Pool identities never enroll in the #204 baseline Convention or interact with
baseline fursuits, and are never registered as reset identities. Run state
lives only in #220 run Conventions.

## Uncertainty register

| Question | Impact if wrong | Resolution | Status |
| --- | --- | --- | --- |
| Can a non-browser client redeem a ticket on Staging's Production instance? | D1 fails; no automated Staging tokens | D3 proof | Resolved: yes, through the client cookie |
| Does Staging bot protection block headless redemption? | Same | D3 proof | Resolved: no challenge occurred |
| Which client-state carrier Production redemption uses, and whether it is documented | D1 amendment wording; possible stop | D3 proof and Clerk docs | Resolved: the client cookie from `POST /v1/client`, documented in the Frontend API spec |
| Must Clerk `allowed_origins` list the tooling origin? | Extra Staging configuration change | D3 proof | Resolved: not for the cookie flow |
| Will field-beta participants ever sign in to Staging Clerk? | D1 and D2 become unacceptable | Maintainer decision | Resolved: no, field beta gets its own environment |
| Does Clerk offer scoped Backend API keys? | A narrower secret than the full instance key | Clerk docs | Open |
| Frontend API refresh rate limits | Caps pool size | Measure before scaling past 1000 | Open |
| Staging instance's enabled identifiers | Changes D6 identifiers | Inspect Staging Clerk configuration | Open |
| How #228's external host reaches the privileged lease commands | D7 channel | #228 design | Deferred |

## Acceptance contract (frozen 2026-10-02)

- P-1 An idempotent privileged command provisions or expands a pool to a target
  size. Every identity carries the D6 markers and none are real users.
- P-2 A run allocates N identities only if N are available and unleased;
  otherwise it fails before allocation. Two concurrent allocations never
  receive the same identity.
- P-3 Release ends the run's sessions without the Clerk secret and ends its
  leases. Allocation revokes an identity's leftover sessions. A crashed run's
  leases become reclaimable after expiry.
- P-4 Each allocated identity authenticates at Staging `/api/me/` through the
  unchanged verifier with an ordinary token whose `azp` is the pinned tooling
  origin, obtained only through ticket redemption with the D1 cookie carrier,
  and stays authenticated for a run longer than one token lifetime. No Backend
  token minting, JWT template, or native-mode token is used.
- P-5 Profiles are initialized or verified only through public endpoints and
  satisfy the V0 profile invariant.
- P-6 Missing, banned, locked, failing, or drifted identities are quarantined
  and reported, and recovery is documented.
- P-7 No secret, token, ticket, session ID, Clerk user ID, or cookie appears in
  output, reports, files, environment variables, arguments, or exceptions.
- P-8 SIMULATION cannot reach the Clerk secret, ticket creation, lease
  commands, Backend API, or client-state carrier; the secret is discarded when
  SETUP ends.
- P-8a No user or ticket is created unless the instance is the Production
  instance with fingerprint `328b851879c17392` and single primary domain
  `staging.tailtag.app`, and no ticket is created for a user lacking the
  synthetic and pool markers and the `external_id` pattern.
- P-9 Pool identities never touch the #204 rehearsal baseline.
- P-10 The pool lifecycle is documented in `tools/simulator/README.md`.
- P-11 Staging readiness requires `CLERK_AUTHORIZED_PARTIES` to be exactly the
  ordered pair of the pinned portal origin and the literal
  `https://simulator.staging.tailtag.app`. A missing, reordered, extra, or
  different origin fails readiness. The verifier is unchanged.
- P-12 Lease commands run only inside the Staging API container through pinned
  `railway ssh` and refuse a non-`staging` #203 identity. No public database
  proxy is enabled and no Staging variable is loaded into the simulator.
- P-13 The #200 and #218 specs point to this spec as their approved
  amendment.

## Test surface contract

External Clerk and Railway boundaries are substituted at their HTTP or
subprocess seams; lease allocation runs against real PostgreSQL in the API test
environment. Failure modes to protect: concurrent double allocation (P-2), a
leaked credential (P-7), SIMULATION reaching privileged inputs (P-8), an
expired token used mid-run (P-4), an invariant-violating profile accepted
(P-5), a quarantined identity allocated (P-6), a ticket created for an
unmarked user or the wrong instance (P-8a), and a Staging readiness check
accepting a wrong authorized-party set (P-11). Live proof of P-4 is a
maintainer-run Staging check after the authorized-party change.

## Scope guard

Expected files: `tools/simulator/**`, a simulation-only app under
`services/api/`, the Staging authorized-party pin and readiness check, Semgrep
rules, `Makefile`, this spec, amendment pointers in the #200 and #218 specs,
and short pointers in existing docs.

Non-goals: run-specific Convention, catch, or fixture state (#220); journeys
(#221); reconciliation (#222); cleanup of run state (#223); the execution host
(#228); Development or Production targets; real-user identities; custom JWT
templates or verifier changes; public API or gameplay changes.

Reversibility: D1 and D2 change the Staging security contract and need
explicit approval, but are technically two-way: removing the tooling origin and
redeploying disables simulator tokens. D7 adds a migration and is additive.
Persisting the Staging Clerk secret on any host is a one-way door that this
proposal does not request. The rest is additive tooling.
