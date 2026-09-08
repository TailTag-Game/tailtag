# Wave 2 participation validation

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to execute this live validation step-by-step
> with explicit operator checkpoints. Do not execute live steps while producing
> or reviewing this plan.

**Goal:** Prove and document that the complete authenticated Wave 2
participation path composes correctly in Railway Development without recording
a catch or exposing sensitive values.

**Architecture:** A reviewable one-off, process-local probe exercises public
player APIs for User A and User B. Existing Django admin supplies the only
operator controls, deployed OpenAPI and Railway metadata supply contract and
revision evidence, and this document retains only sanitized results.

**Tech stack:** Python and locked repository dependencies for temporary
orchestration, Clerk Development authentication, Django/DRF public APIs and
admin, PostgreSQL-backed Railway Development, and private configured media
storage.

Issue: [#120 — Validate and document the complete Wave 2 participation
flow](https://github.com/TailTag-Game/tailtag/issues/120)

Status: Railway Development service recovery succeeded after the workspace plan
was restored. The resumed deployment preflight stopped on a direct OpenAPI
schema defect; no authentication or fixture mutation started.

## Global constraints

- Do not add a permanent Wave 2 smoke command or broaden `api-auth-smoke`.
- Keep all secrets, tokens, credential payloads, media URLs, signatures, and
  private identifiers process-local and absent from committed evidence.
- Use only User A, User B, and Operator aliases in durable documentation.
- Reuse stable synthetic fixtures and never blindly retry fursuit creation.
- Use only existing public player APIs, Django admin, and Railway metadata;
  never add an operator, cleanup, build-info, or catch API.
- Keep ordinary tests and `make api-check` network-independent.
- Leave mutable fixtures benign and record no catch.

## Purpose and boundary

This document is the canonical plan, rerun procedure, and sanitized evidence
record for the final Wave 2 integration validation. It proves that the
implemented authentication, profile, Convention, enrollment, fursuit, media,
activation, catch-session, and Convention-scoped catch-credential contracts
compose correctly in the shared Railway Development environment.

The validation stops at safe credential resolution. It never creates or
persists a catch and makes no production-readiness, performance, availability,
or physical-proximity claim.

The live run is a reviewable one-off exercise. It does not add a permanent
`api-wave2-smoke` command, broaden `api-auth-smoke`, create an operator API, or
establish a generalized multi-user validation framework. A permanent command
requires a separately demonstrated recurring maintenance need and approved
scope.

## Scope Guard

- **Outcome:** Prove the complete Issue #120 happy path, ownership and
  enrollment boundaries, retry safety, Convention scoping, global-disablement
  cascade, deployed OpenAPI accuracy, and real configured media behavior
  against Railway Development, then record only sanitized evidence.
- **Non-goals:** Catch creation, Wave 3 behavior, production access, new
  operator or cleanup interfaces, credential rotation testing, blind fursuit
  creation retries, generalized live-test infrastructure, and unrelated
  remediation.
- **Expected files:** This document plus links from
  `docs/development/backend-delivery-operations.md` and
  `services/api/README.md`, with the remaining deleted-review reference in
  `docs/architecture.md` redirected to maintained operating guidance.
  Production or test files change only if the live run exposes a small direct
  Wave 2 defect and that correction is separately reviewed against the
  approved contracts.
- **Proof:** The matrix below, fixed stage-level outcomes, sanitized Railway
  deployment correlation, deployed OpenAPI inspection, `make api-check`,
  `./scripts/doctor.sh`, and `git diff --check`.
- **Assurance:** SECURITY, DATA INTEGRITY, RELIABILITY, and TEST ADEQUACY.

## Authoritative contracts

The validation must not reinterpret the existing domain contracts:

- [V0 player profile](../specs/2026-08-24-v0-player-profile.md)
- [V0 Convention enrollment](../specs/2026-08-25-v0-convention-enrollment.md)
- [V0 fursuit domain](../specs/2026-08-24-v0-fursuit-domain.md)
- [Per-Convention fursuit activation](../specs/2026-08-31-v0-fursuit-activation.md)
- [V0 fursuit catch sessions](../specs/2026-09-01-v0-fursuit-catch-sessions.md)
- [Convention-scoped catch credentials](../specs/2026-09-01-v0-fursuit-catch-credentials.md)
- [V0 media storage](../specs/2026-08-19-v0-media-storage.md)
- [Main-to-Railway Development delivery](../specs/2026-08-16-main-to-railway-development-delivery.md)

If live evidence contradicts one of these contracts, stop the run. Fix only a
small, direct Wave 2 defect through the normal reviewed development workflow.
File a focused follow-up for a material redesign, generalized tool, unrelated
problem, or changed product contract.

### Direct defect acceptance contract

The initial deployed OpenAPI preflight found that the current-user
authentication error and several profile and Convention request/response
components did not declare `additionalProperties: false`. Correct this as a
schema-only Wave 2 defect before resuming the live run:

- close the `/api/me/` `401` response object and the relevant profile and
  Convention request/response object schemas through their deployed component
  references;
- preserve runtime request parsing, response status, and state behavior,
  including the existing profile handling of unrecognized fields;
- preserve the existing fields, methods, status codes, Bearer security, and
  unrelated APIs; and
- do not add a generalized schema framework, dependency, endpoint, or other
  production surface.

The approved test surface is the locally generated OpenAPI document exercised
by the existing current-user, profile, and Convention enrollment schema tests.
No production test seam or network-dependent automated test may be added.

## Environment and execution prerequisites

The run is blocked, without changing this design, until all of these are true:

- an intended `main` revision containing Issues #112 through #119 has passed
  required GitHub checks and is the successful Railway Development `api`
  deployment;
- the operator has authorized Railway Development access and confirms the
  linked target is `TailTag` / `development` / `api`;
- the existing Clerk Development secret is available through its approved
  hidden, process-local boundary;
- the configured Railway Development media-storage endpoint origin is
  privately available through the same kind of process-local operator boundary;
- two dedicated persistent Clerk Development identities are privately
  available as User A and User B;
- the existing Django-admin/operator login and required model permissions work;
- no maintainer is concurrently changing the validation fixtures or relevant
  Railway deployment; and
- the repository environment can run `make api-check`,
  `./scripts/doctor.sh`, and the one-off probe from locked dependencies.

Run `railway status --json` only to confirm the safe target identity. Do not
run commands that render Railway variables for routine diagnosis. Deployment
metadata plus observed live behavior is sufficient revision evidence; do not
add a build-information endpoint.

## Actors and stable fixtures

Committed evidence uses only these aliases:

| Alias | Durable role |
| --- | --- |
| User A | Onboarded, enabled ordinary player; owns Fursuit A and Fursuit B. |
| User B | Onboarded, enabled ordinary player; resolves User A's Convention 1 credential and remains unenrolled in Convention 2. |
| Operator | Existing Django staff/superuser path used only for Convention preparation and Fursuit A enablement changes. |
| Convention 1 | Stable synthetic `Issue 120 Validation Convention 1`, independently playable and used for the primary flow. |
| Convention 2 | Stable synthetic `Issue 120 Validation Convention 2`, independently playable and used for Convention-scope and non-enrollment proof. |
| Fursuit A | Stable enabled synthetic `Issue 120 Validation Fursuit A`, owned by User A and used as the primary activated/catchable target. |
| Fursuit B | Stable enabled synthetic `Issue 120 Validation Fursuit B`, owned by User A and kept without a Convention 1 activation. |

Reuse these fixtures on reruns. Resolve them privately through owner-visible
API results or Django admin and never record Clerk identifiers, internal user
IDs, fursuit IDs, Convention IDs, handles, or operator identity in durable
evidence. If a fixture lookup is missing, create the minimum missing fixture.
If it is ambiguous, stop for operator reconciliation rather than guessing or
creating another duplicate.

Fursuit creation is intentionally non-idempotent. Never retry it after an
ambiguous response. Reconcile with `GET /api/fursuits/` before deciding whether
creation is still required. On a rerun with existing fursuits, replace their
photos through the supported owner API when a fresh real-storage write is
needed; do not create replacement fursuit rows merely to exercise media.

Historical sessions and credentials are legitimate synthetic Development
history and may remain. Do not add deletion APIs, use direct database deletion,
or perform administrative deletion merely to make the fixtures look pristine.

## One-off probe security contract

The reviewable temporary probe may orchestrate public API requests and reuse
the existing Clerk Development session helper, but it is not committed as a
supported interface. Before execution, review its complete source against
these rules:

- create it in a temporary directory and remove that directory after the run;
- accept the Clerk Development secret only through a hidden interactive prompt
  or another already-approved process-local secret boundary;
- keep the secret, session tokens, credential payloads, presigned media URLs,
  request signatures, response bodies containing identifiers, and Clerk
  identifiers in process memory only;
- validate the exact approved HTTPS Railway Development origin and never
  follow redirects for authenticated API requests;
- validate the configured HTTPS media-storage origin privately and reject any
  returned media URL whose exact origin differs before fetching it; never
  follow media redirects or print either origin;
- never print or serialize authorization headers, sensitive request bodies,
  full response bodies, exception details that may contain request material,
  or fixture identifiers;
- issue fresh short-lived User A or User B tokens when necessary and revoke
  supported ephemeral Clerk sessions on success and failure;
- use synthetic, non-personal image bytes for fursuit-photo operations;
- emit only fixed stage aliases, expected status classes, `PASS` or `FAIL`, and
  sanitized recovery instructions; and
- fail closed on an unexpected status, schema, redirect, duplicate fixture,
  or uncertain provider cleanup result.

The probe may pause at explicit operator checkpoints while values remain in
memory. It must not automate Django-admin login or accept a persistent operator
credential. Ordinary automated tests and `make api-check` remain network
independent.

## Test Surface Contract

Approved observation and control seams are:

- the deployed public HTTPS API for authentication and all player behavior;
- the deployed `/api/schema/` OpenAPI document, parsed without recording the
  full document;
- the existing Django admin for Convention creation/status, fursuit
  enablement, and read-only per-fixture inspection of activation, session, and
  credential row counts, current/terminal state, and terminal reasons;
- Railway's existing deployment metadata and safe target identity; and
- fixed stage-level output from the one-off probe.

No direct database read or write is required. Do not add a production endpoint,
test-only production API, build-info route, operator script, token-export seam,
or storage-inspection interface. Public API behavior establishes owner and
resolver outcomes; Django admin is used only where terminal reasons are not
publicly represented.

## Ordered validation procedure

Execute the matrix in order. A prerequisite or assertion failure stops forward
progress, except for the benign-state recovery steps, which must still be
attempted through approved public APIs or Django admin.

### Phase 1 — deterministic and deployment preflight

1. Run `make api-check` at the intended application revision.
2. Run `./scripts/doctor.sh` and `git diff --check`.
3. Confirm required GitHub checks passed for the intended `main` revision.
4. Confirm the successful Railway Development deployment reports that revision
   and the exact `development` / `api` target.
5. Run the existing credential-free `make api-smoke` against the approved API
   root.
6. Confirm privately that User A, User B, and operator access are available.

### Phase 2 — fixture reconciliation and media

1. Authenticate both users through separate short-lived sessions and verify
   `/api/me/` succeeds without recording either response.
2. Read each user's profile. Complete it through the supported profile `PUT`
   only if necessary, using private stable synthetic values.
3. Through Django admin, create or reconcile Convention 1 and Convention 2 and
   leave both in the independently playable `active` state.
4. Through User A's owner API, reconcile Fursuit A and Fursuit B. Create only a
   missing, unambiguous fixture; otherwise reuse it.
5. Upload or replace each fursuit's synthetic photo through the actual owner
   API. Before fetching the returned short-lived read URL, require its exact
   origin to match the privately supplied configured media-storage origin.
   Fetch without redirecting, require a successful response with an image
   media type and nonempty body, then discard the URL and bytes without logging
   either.
6. Ensure Fursuit A and Fursuit B are globally enabled. Ensure Fursuit B has no
   Convention 1 activation by inspecting User A's activation list. If a durable
   relationship already exists, mark the run `BLOCKED` for approved fixture
   reconciliation; deactivation or deletion cannot recreate the required
   missing-activation precondition.
7. For any existing Fursuit A activation, use the owner desired-state API to
   stop a current session. Leave the Convention 1 activation available for the
   primary flow and converge the Convention 2 activation inactive. Through
   private read-only admin inspection, capture baseline per-fixture activation,
   session, and credential counts and lifecycle fields for later delta checks;
   retain no identifiers or values in durable output.

### Phase 3 — primary flow, ownership, and retry safety

1. Enroll User A in Convention 1 with active selection, repeat the retry-safe
   enrollment request, select Convention 1 active twice, and verify one logical
   enrollment and one active selection.
2. Attempt to start a Convention 1 session for Fursuit B. Require owner-safe
   `404` because no activation exists, and verify no activation or session was
   synthesized.
3. Activate Fursuit A for Convention 1 twice with the same desired state.
   Require one activation and unchanged transition timestamps on retry.
4. Start Fursuit A's Convention 1 catch session twice. Require one live session
   with unchanged `started_at` and `expires_at` on retry.
5. Fetch Fursuit A's Convention 1 current credential twice. Require the same
   process-local payload, `Cache-Control: no-store`, and one current credential.
6. Enroll User B in Convention 1. User B resolves the payload and receives only
   Convention 1 plus Fursuit A's safe `tailtag_id`, name, and temporary photo
   URL. Require the same exact configured media-origin match before fetching
   without redirecting, then require a successful image media type plus
   nonempty body; do not log the URL or bytes.
7. After successful resolution, User B attempts applicable owner operations
   against Fursuit A: fursuit detail/name update/photo replacement, activation
   mutation, catch-session mutation, and owner credential fetch. Require the
   contractually concealed `404` behavior, with photo rejection occurring
   before media processing. Confirm through User A's before/after
   representations that no owner-controlled state changed. Also require User
   B's fursuit list and Convention 1 activation list to exclude User A's rows.
8. Stop the Convention 1 session twice. Require one owner-ended historical
   session transition and no additional history or timestamp change on retry,
   measured against the private baseline. Retain the original Convention 1
   credential payload in process memory.
9. User B retries resolution with the still-existing payload. Require the exact
   generic `404` non-resolution shape. The probe invokes no catch/write
   operation; it does not claim database-level proof that resolution has no
   internal write.

### Phase 4 — Convention scope and non-enrollment

1. Verify from User B's enrollment list that Convention 2 is absent. If a
   durable enrollment already exists, mark the run `BLOCKED` for approved
   fixture reconciliation; do not delete it or continue with a false
   non-enrollment premise. Enroll User A, but not User B, in Convention 2
   without changing User A's active selection from Convention 1.
2. Restart Fursuit A's Convention 1 session and fetch its current Convention 1
   credential. Require it to equal the original Phase 3 payload byte-for-byte,
   proving that routine session stop did not revoke or replace the credential.
   Require User B to resolve that same original payload successfully again.
3. Activate Fursuit A in Convention 2, start its Convention 2 session, and fetch
   its current Convention 2 credential. Require the two payloads to differ in
   memory without recording either.
4. As enrolled User A, resolve the Convention 1 payload under Convention 2 and
   the Convention 2 payload under Convention 1. Both requests must return the
   same generic credential-not-found `404` used for target non-resolution.
5. As User B, attempt to resolve the otherwise current Convention 2 payload
   under Convention 2. Require the caller-authorization `403` because User B is
   not enrolled there. This is the stable rerunnable non-enrolled-player case.
6. Stop Fursuit A's Convention 2 session, retry the stop, and fetch the current
   credential again. Require the payload to remain byte-for-byte equal to the
   original Convention 2 payload, proving that session stop did not revoke it.
   Deactivate the Convention 2 activation and retry deactivation. Through
   read-only Django-admin inspection, require the exact current Convention 2
   credential to become terminal with
   `revocation_reason=eligibility_lost`; no credential rotation is used.

### Phase 5 — global-disablement cascade

1. Confirm Fursuit A remains activated and has a live Convention 1 session and
   current Convention 1 credential. User B resolves it successfully immediately
   before the operator transition.
2. Through the existing Fursuit Django admin, globally disable Fursuit A.
3. Verify synchronously that:
   - the Convention 1 activation remains stored active but computes ineligible;
   - the live Convention 1 session is terminal with
     `end_reason=eligibility_lost`;
   - the current Convention 1 credential is terminal with
     `revocation_reason=eligibility_lost`;
   - the previously successful payload now produces the generic resolver
     `404`; and
   - normal owner attempts to start a session or fetch a credential fail under
     the established eligibility contract.
4. Through the same Django admin, re-enable Fursuit A.
5. Without starting a session or fetching a credential, verify that:
   - the activation is eligible again but the terminated session remains
     terminal;
   - no credential was resurrected;
   - the old payload still returns the generic resolver `404`; and
   - only a later explicit owner action could create new current session or
     credential state.

### Phase 6 — deployed contract and benign final state

1. Parse deployed OpenAPI and validate the Wave 2 paths and methods listed in
   the matrix below, Bearer security, closed request/response schemas, relevant
   status responses, and the distinction between preview resolution and catch
   authorization. Inspect credential rotation in schema only; do not invoke it.
2. Confirm the correlated Wave 2 revision has no catch model or catch-write
   route and that the probe's fixed invocation set contains no catch write.
   Therefore this validation cannot and did not record a catch; it does not
   claim that unrelated future or pre-existing data was inspected.
3. Stop any remaining Issue #120 catch session through the owner API.
4. Leave Fursuit A and Fursuit B globally enabled. Leave Fursuit B without a
   Convention 1 activation and the Convention 2 activation inactive. Do not
   alter unrelated Conventions or users.
5. Revoke every ephemeral Clerk session created by the probe, discard all
   sensitive in-memory values, remove the temporary probe directory, and
   verify locally that the directory is absent.
6. Record the sanitized execution result in this document. Do not record
   identifiers, payloads, URLs, full bodies, timestamps that identify provider
   activity, or secret-bearing diagnostics.

## Validation matrix

The `Expected evidence` column is the frozen acceptance oracle. Exact response
field sets and error shapes remain those of the authoritative specifications.

| ID | Requirement | Exercise | Expected evidence |
| --- | --- | --- | --- |
| PRE-01 | Deterministic baseline | Run `make api-check`. | PASS; no live network dependency is added to ordinary tests. |
| PRE-02 | Contributor/document baseline | Run `./scripts/doctor.sh` and `git diff --check`. | PASS, or an environmental limitation is recorded without concealing it. |
| PRE-03 | Revision correlation | Correlate checked `main` SHA, successful Railway deployment, and `development/api`. | One intended revision and safe target are recorded; no new version endpoint exists. |
| PRE-04 | Public baseline | Run the existing credential-free API smoke. | Existing liveness, readiness, schema, and docs stages PASS. |
| AUTH-01 | Real authentication | Authenticate User A and User B and call `/api/me/`. | Both return `200`; identities and bodies are not recorded. |
| PROF-01 | Participation eligibility | Read and, only if needed, complete both profiles. | Both aliases are onboarded and enabled; private profile values are not recorded. |
| FIX-01 | Stable Conventions | Reconcile Convention 1 and Convention 2 in Django admin. | Exactly two intended synthetic fixtures are independently playable. |
| MEDIA-01 | Real configured media path | Create or update both fursuit photos, require each returned read URL to match the private configured storage origin, then fetch without redirects. | Owner operations succeed; exact origins match and responses have successful status, image media type, and nonempty body without logging URLs, keys, endpoints, or bytes. |
| FUR-01 | Stable fursuits | Reconcile Fursuit A and Fursuit B through User A's API. | Exactly the designated owner fixtures are used; ambiguous creation is never replayed. |
| FIX-02 | Missing-activation precondition | Inspect A's Convention 1 activation list for Fursuit B. | No relationship exists; an existing durable row blocks rather than weakens NEG-01. |
| FIX-03 | Non-enrollment precondition | Inspect B's enrollment list for Convention 2. | No enrollment exists; an existing durable row blocks rather than weakens ENR-03. |
| ENR-01 | Enrollment retry safety | Repeat User A's Convention 1 enrollment request. | Initial missing enrollment may return `201`; existing/retried enrollment returns `200`; list shows one relationship. |
| ENR-02 | Active-selection retry safety | Select Convention 1 active twice. | Both return `200`; active selection remains Convention 1 with no duplicate enrollment. |
| NEG-01 | Non-activated fursuit | Start Fursuit B's Convention 1 catch session without an activation. | Concealed `404`; no activation or session is created. |
| ACT-01 | Activation retry safety | Set Fursuit A active in Convention 1 twice. | Both return `200`; one row remains active and retry preserves transition timestamps. |
| SES-01 | Session-start retry safety | Set Fursuit A's Convention 1 session active twice. | Both return `200`; one live session and unchanged start/expiry values. |
| CRED-01 | Credential-fetch retry safety | Fetch the current Convention 1 credential twice. | Both return `200` and `no-store`; payload is unchanged in memory and only one credential is current. |
| RES-01 | Cross-player discovery | Enroll User B in Convention 1 and resolve Fursuit A's payload. | `200` with only safe Convention/fursuit preview fields and no owner or lifecycle data. The probe invokes no catch/write operation; absence of an internal resolution write is not claimed as a database-level live assertion. |
| OWN-01 | Cross-owner fursuit access | User B retrieves, patches, and attempts photo replacement on Fursuit A. | All return concealed `404`; photo rejection precedes media work and User A's representation remains unchanged. |
| OWN-02 | Cross-owner participation access | User B mutates A's activation/session and fetches A's owner credential. | Each applicable request returns concealed `404`; successful resolution has granted no owner authority. |
| OWN-03 | Cross-owner list isolation | User B lists fursuits and Convention 1 activations. | Neither list contains User A's fursuits or activation. |
| SES-02 | Session-stop retry safety | Set the Convention 1 session inactive twice. | Both return `200`; one owner-ended session remains and retry adds no history or timestamp change. |
| RES-02 | Stopped-session non-resolution | User B resolves the unchanged Convention 1 payload after stop. | Exact generic credential-not-found `404`; credential existence alone is insufficient. |
| CRED-02 | Session/credential independence | Restart Convention 1 session, refetch credential, and resolve it as User B. | Fetch returns the byte-identical original Phase 3 payload and User B again receives `200`; routine stop did not revoke or replace it. |
| SCOPE-01 | Independent Convention relationship | Enroll A and activate Fursuit A in Convention 2; start session and fetch credential. | Convention 2 has its own activation, session, and distinct process-local credential. |
| SCOPE-02 | Bidirectional Convention scoping | As A, resolve each Convention's payload under the other Convention path. | Both return the same generic credential-not-found `404`. |
| ENR-03 | Non-enrolled caller | User B resolves the valid Convention 2 payload under Convention 2 while not enrolled there. | Sanitized caller-authorization `403`; target details are not disclosed. |
| SCOPE-03 | Convention 2 stop independence | Stop the Convention 2 session twice and refetch its credential. | Desired session state converges with no duplicate history; credential remains current and byte-identical while stopped. |
| SCOPE-04 | Convention 2 deactivation cascade | Deactivate the Convention 2 activation twice and inspect credential history in admin. | Activation converges inactive; the exact current credential becomes terminal once with `eligibility_lost`. |
| LIFE-01 | Pre-disable catchability | With A active/session-current in Convention 1, B resolves the current payload. | `200` immediately before the operator transition. |
| LIFE-02 | Global-disable cascade | Operator disables Fursuit A through Django admin. | Activation computes ineligible; session and credential terminate synchronously with `eligibility_lost`. |
| LIFE-03 | Disabled non-participation | Retry old resolution and normal owner session/credential operations while disabled. | Resolver returns generic `404`; owner participation operations fail safely under approved `400`/eligibility behavior. |
| LIFE-04 | No resurrection | Operator re-enables Fursuit A without an owner start/fetch action. | Eligibility returns, but the ended session and revoked credential remain terminal and old payload stays `404`. |
| API-01 | Deployed OpenAPI | Parse the deployed schema for profile, Convention, enrollment, fursuit, activation, session, credential fetch/rotation, and resolution paths. | Exact supported methods, Bearer security, closed schemas, statuses, and preview-not-authorization language match implemented contracts. |
| API-02 | No catch behavior | Review the probe invocation set and correlated deployed Wave 2 source/OpenAPI. | No catch model or catch-write route exists and no catch-write operation is invoked; therefore this validation records no catch, without claiming a database-wide absence check. |
| END-01 | Benign fixture state | Run approved final-state actions even after a failure. | No active Issue #120 session, both fursuits enabled, Convention 2 activation inactive, no unrelated state change. |
| END-02 | Temporary-artifact cleanup | Remove the one-off probe directory and check its path. | Local absence check passes; no probe, token, payload, URL, or generated artifact remains. |
| SEC-01 | Sensitive-value containment | Review probe output, committed diff, and recorded evidence. | No token, payload, URL, signature, Clerk ID, account data, operator identity, secret, or rendered Railway variable is present. |

### Deployed OpenAPI path set

Inspect at least these paths because the procedure uses or depends on them:

```text
GET    /api/me/
GET    /api/profile/
PUT    /api/profile/
GET    /api/conventions/
GET    /api/conventions/{id}/
GET    /api/conventions/enrollments/
POST   /api/conventions/enrollments/
GET    /api/conventions/active/
PUT    /api/conventions/active/
GET    /api/fursuits/
POST   /api/fursuits/
GET    /api/fursuits/{id}/
PATCH  /api/fursuits/{id}/
PUT    /api/fursuits/{id}/photo/
GET    /api/conventions/{convention_id}/fursuit-activations/
PUT    /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/
PUT    /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-session/
GET    /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/
POST   /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/rotate/
POST   /api/conventions/{convention_id}/catch-credentials/resolve/
```

Rotation is inspected only as deployed contract. It is intentionally
state-changing and is not part of the retry matrix.

## Acceptance traceability

| Issue #120 acceptance requirement | Matrix evidence |
| --- | --- |
| Complete authenticated flow succeeds in Railway Development. | PRE-03, PRE-04, AUTH-01, PROF-01, FIX-01, MEDIA-01, FUR-01, ENR-01, ENR-02, ACT-01, SES-01, CRED-01, RES-01, SES-02, RES-02 |
| Ownership, enrollment, activation, enabled-state, session, and Convention-scope failures are safe. | FIX-02, FIX-03, NEG-01, OWN-01 through OWN-03, ENR-03, SCOPE-01 through SCOPE-04, LIFE-01 through LIFE-04 |
| Stopping a session removes current catchability despite an existing credential. | SES-02, RES-02, CRED-02, SCOPE-03 |
| Repeats preserve state integrity. | ENR-01, ENR-02, ACT-01, SES-01, SES-02, CRED-01, CRED-02, SCOPE-03, SCOPE-04 |
| Deployed OpenAPI, media configuration, deterministic checks, and documentation match behavior. | PRE-01 through PRE-04, MEDIA-01, API-01, SEC-01 |
| No catch is recorded. | API-02 |

## Failure handling and recovery

On any mismatch:

1. Emit only the failing stage alias and a fixed sanitized failure category.
2. Do not print the unexpected response or exception if it may contain sensitive
   material.
3. Stop dependent validation steps.
4. Attempt provider-session cleanup and the benign fixture state through the
   approved surfaces.
5. If Fursuit A may remain disabled, require the operator to inspect and
   re-enable that exact synthetic fixture before ending the run.
6. Record the criterion as `FAIL` or `BLOCKED`, the sanitized observed boundary,
   and whether fixture recovery succeeded.
7. Diagnose a suspected application defect separately. Do not patch production
   code or mutate contracts inside the live probe.

An ambiguous fursuit-creation response is reconciled by owner list, never blind
replay. An uncertain credential or session transition is reconciled through
the safe public projection or Django-admin history, never by direct database
mutation.

## Sanitized execution record

The first live attempt stopped at the approved deployment prerequisite because
the Railway workspace trial had expired. After the workspace owner restored an
active plan, the existing PostgreSQL service and volume returned healthy and
the intended Wave 2 application revision deployed successfully to the approved
`development/api` target. The canonical credential-free smoke then passed for
liveness, readiness, schema, and documentation, and the Django-admin route was
reachable.

The resumed run stopped before authentication when the fail-closed deployed
OpenAPI check found that the current-user authentication error and seven
existing profile/Convention components did not declare
`additionalProperties: false`. This is a small direct Wave 2 schema defect. Its
schema-only correction and focused regression tests pass the complete local
backend gate with 1,106 tests, zero Semgrep findings, strict type checking,
Django and migration checks, OpenAPI validation, and the production server
configuration check. Independent review found no material issue. The live run
remains blocked until that correction is merged and the correlated revision is
successfully deployed.

No Clerk session was created, no Django-admin operation ran, no application
fixture changed, and no catch operation was available or attempted. Rerun this
procedure from Phase 1 after the reviewed schema correction is deployed.
Fixture final state was not inspected, so it remains blocked rather than
verified; no recovery action was required for this attempt because fixture
mutation never started.

Record only this shape:

```text
execution date (UTC): 2026-09-08
validated application revision: 3347be9d8e4b2b42014e57e518f773ebe0c36156
Railway target: TailTag / development / api
deployment correlation: PASS
deterministic baseline: PASS
authentication/profile: BLOCKED
fixtures/media: BLOCKED
primary flow: BLOCKED
ownership/enrollment negatives: BLOCKED
retry/idempotency: BLOCKED
Convention scope: BLOCKED
global-disable cascade: BLOCKED
deployed OpenAPI: FAIL — direct schema defect, correction pending deployment
benign final state: BLOCKED
provider cleanup: PASS
no catch recorded: PASS
overall: BLOCKED
```

For any non-PASS stage, add only a sanitized description, direct Wave 2 defect
or external prerequisite classification, fixture-recovery result, and linked
follow-up disposition. Never include raw request/response material or private
identifiers.

## Completion gate

Issue #120 is ready to close only when every matrix row is accounted for, the
overall live result is `PASS`, both fursuits and all sessions are left benign,
provider cleanup is confirmed, deployed OpenAPI and media behavior match the
contracts, `make api-check` is fresh, no catch was recorded, and this canonical
record contains the sanitized validated revision and outcomes. Any direct code
fix must also pass the normal independent review and deterministic gates before
the live scenario is rerun against its deployed revision.
