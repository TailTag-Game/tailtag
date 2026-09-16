# Wave 3 catching and collection validation

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to execute this live validation step-by-step
> with explicit operator checkpoints. Do not execute live steps while producing
> or reviewing this plan.

**Goal:** Prove and document that the complete authenticated Wave 3 catch,
private collection/history, and operator-correction flow composes correctly in
Railway Development without exposing sensitive values.

**Architecture:** A reviewable one-off, process-local probe exercises the public
player APIs for User A and User B. Existing Django admin supplies the only
operator correction surface. Existing real-PostgreSQL tests supply the
authoritative simultaneous-concurrency proof; the live run supplies sequential
retry proof. Deployed OpenAPI, Railway metadata, and this document supply
contract, revision, and sanitized durable evidence.

**Tech stack:** Python and locked repository dependencies for temporary
orchestration, Clerk Development authentication, Django/DRF public APIs and
admin, PostgreSQL-backed Railway Development, and the repository's real-
PostgreSQL automated suite.

Issue: [#179 — Validate and document the complete V0 catching and collection
flow](https://github.com/TailTag-Game/tailtag/issues/179)

Status: Validation complete against the correlated Railway Development revision.

## Frozen validation contract

This document is the canonical approved plan, rerun procedure, evidence oracle,
and sanitized execution record for Issue #179. The contract freezes these
decisions:

- client uncertainty is simulated by issuing the first valid confirmation once,
  discarding its response in process memory, and issuing one identical retry;
- the existing real-PostgreSQL automated concurrency suite is authoritative for
  simultaneous duplicate convergence and lifecycle races;
- stable synthetic Development actors and fixtures are reconciled and reused;
- any pre-existing Catch for the exact primary tuple is removed only through the
  authorized Catch admin surface before the proof begins;
- all evidence for the original Catch is captured before its required operator
  deletion;
- practical composed negative cases run live, while exhaustive time, race,
  transaction, and constraint cases remain deterministic automated evidence;
- the probe remains temporary and process-local; and
- only small direct defects may be corrected here. Material findings become
  focused follow-up issues.

The ordered phases and matrix below are the frozen acceptance oracle. Changing a
public contract, persistence assumption, security boundary, operator surface,
or live-versus-automated split requires replanning Issue #179.

## Global constraints

- Use only the approved `TailTag / development / api` Railway target. Never
  access or claim readiness for production.
- Keep tokens, session values, credentials, QR payloads, presigned URLs, response
  bodies containing identifiers, and all personal or provider-account data
  process-local and absent from durable evidence.
- Use only User A, User B, Operator, Convention 1, Convention 2, and Fursuit A
  aliases in committed evidence.
- Reuse the established synthetic Development fixtures where practical. Never
  blindly retry non-idempotent fixture creation.
- If fixture identity is ambiguous, stop for operator reconciliation instead of
  guessing or creating a replacement.
- Use public player APIs and the existing Django admin. Do not write or delete
  live fixture data directly in PostgreSQL.
- Do not add a permanent Wave 3 smoke command, generalized multi-user test
  framework, cleanup API, observability endpoint, retry middleware, proxy,
  transport fault injector, or persistent operator script.
- Do not abort sockets mid-write or inject server failures. This run proves
  application retry semantics, not TCP behavior.
- Keep ordinary tests and `make api-check` network-independent.
- Do not add a Railway concurrent-write probe unless a concrete deployed-only
  discrepancy is discovered that the automated PostgreSQL tests cannot explain.

## Purpose and boundary

This validation begins at the already-approved explicit confirmation boundary.
It proves that credential resolution remains preview-only, the backend
independently revalidates catch eligibility, exactly one durable Catch is
created, duplicate and uncertain retries converge on that Catch, private
collection/history derives from Catch records, and authorized operator deletion
removes the Catch without rewriting participation history.

The run does not introduce product behavior. Flutter scanner screens, XP,
progression, achievements, leaderboards, rarity, public or social collections,
a changing caught denominator, offline sync, NFC/manual codes, dedicated
hardware, GPS/BLE/proximity proof, advanced anti-cheat, dedicated analytics,
production rollout, and generalized live-test infrastructure remain out of
scope.

## Scope Guard

- **Outcome:** Validate the complete Issue #179 Railway Development flow and
  retain only sanitized, durable evidence of the deployed behavior and the
  authoritative PostgreSQL concurrency tests.
- **Non-goals:** New catch behavior, client UX, new operator or cleanup surfaces,
  transport-failure testing, a live concurrency probe without a discovered
  discrepancy, generalized validation tooling, production access, or unrelated
  remediation.
- **Expected files:** This document plus links from
  `docs/development/backend-delivery-operations.md` and
  `services/api/README.md`, plus one focused credential-history preservation
  assertion in `services/api/tests/test_catch_admin.py`. Production files change
  only if the live run exposes a small direct defect that is separately
  diagnosed and reviewed against the approved contracts.
- **Proof:** The matrix below, sanitized Railway deployment correlation,
  deployed OpenAPI inspection, the existing real-PostgreSQL concurrency and
  lifecycle tests, `make api-check`, `./scripts/doctor.sh`, and
  `git diff --check`.
- **Assurance:** SECURITY, DATA INTEGRITY, RELIABILITY, and TEST ADEQUACY.

## Authoritative contracts

The run observes rather than reinterprets these approved contracts:

- [V0 catch domain](../specs/2026-09-08-v0-catch-domain.md)
- [Authoritative catch validation and creation](../specs/2026-09-08-v0-authoritative-catch-confirmation.md)
- [V0 catch confirmation API](../specs/2026-09-09-v0-catch-confirmation-api.md)
- [V0 player catch-history API](../specs/2026-09-10-v0-player-catch-history-api.md)
- [Catch administration and operator correction](../operations/catch-administration.md)
- [Convention-scoped catch credentials](../specs/2026-09-01-v0-fursuit-catch-credentials.md)
- [V0 fursuit catch sessions](../specs/2026-09-01-v0-fursuit-catch-sessions.md)
- [Per-Convention fursuit activation](../specs/2026-08-31-v0-fursuit-activation.md)
- [V0 Convention enrollment](../specs/2026-08-25-v0-convention-enrollment.md)
- [V0 player profile](../specs/2026-08-24-v0-player-profile.md)
- [Main-to-Railway Development delivery](../specs/2026-08-16-main-to-railway-development-delivery.md)
- [Wave 2 participation validation](wave-2-participation-validation.md)

If live evidence contradicts one of these contracts, stop dependent stages and
follow the failure procedure. Fix only a small direct defect through the normal
reviewed workflow. File a focused follow-up for a material redesign, generic
tool, unrelated problem, or changed product contract.

## Acceptance Contract

- A composed Railway Development run uses at least two distinct synthetic users
  to prove explicit confirmation of a valid QR-based catch, server-side
  revalidation, exactly-once persistence, and private collection/history
  reflection.
- The first confirmation is sent exactly once and its response is discarded.
  One identical retry with the same process-local credential returns
  `already_caught`; the read API then proves one Catch with its original
  server-owned `caught_at`.
- Live validation covers unauthenticated confirmation, self-catch, wrong
  Convention, stopped session, deactivated target, globally disabled fursuit,
  at least one broader player/participation eligibility failure, and valid
  duplicate/retry behavior.
- Existing deterministic tests remain authoritative for literal time expiry,
  exhaustive eligibility permutations, all lifecycle race orderings,
  simultaneous duplicate concurrency, raw uniqueness recovery, and low-level
  transaction/savepoint behavior.
- The real-PostgreSQL suite proves that simultaneous canonical confirmations
  yield exactly one `created` and one `already_caught`, resolve the same Catch,
  persist one row, and preserve provenance and the original `caught_at`.
- Before deletion, private reads prove own-player isolation, all-time and
  Convention-scoped history, count, server-owned time, approved fursuit and
  Convention context, deterministic ordering/pagination where meaningful, no
  changing denominator, and no other-player data.
- Existing authorized Django admin can inspect and delete the synthetic Catch;
  the Catch disappears from derived reads and unrelated activation, session,
  and credential history is unchanged.
- Deployed OpenAPI, repository documentation, checked revision, Railway target
  and deployment, and deterministic checks align with observed behavior.
- Durable evidence contains only the explicitly allowed sanitized fields and no
  sensitive or personal values.

## Test Surface Contract

Approved observation and control seams are:

- the deployed public HTTPS API for authentication and player behavior;
- the deployed `/api/schema/` OpenAPI document, parsed without retaining the
  full document;
- existing owner APIs for fixture reconciliation, activation, sessions, and
  credential fetch;
- existing authenticated private Catch collection/history reads;
- existing Django admin for authorized Catch inspection/deletion and approved
  fixture lifecycle controls;
- Railway's existing safe target and deployment metadata; and
- existing real-PostgreSQL tests and fixed stage-level probe output.

No direct live database read/write, production endpoint, test-only API,
build-information route, cleanup API, award API, test clock, new public seam, or
persistent script may be added. The live run does not inspect or create a
second mutable collection source of truth.

## Environment and execution prerequisites

Do not begin authenticated live stages until all of these are true:

- the intended checked revision has passed deterministic repository checks and
  is the successful Railway Development `api` deployment;
- the linked Railway target is exactly `TailTag / development / api`;
- the deployed OpenAPI contains the approved confirmation and private-history
  contracts;
- the credential-free deployed smoke passes;
- the existing Clerk Development secret is available only through an approved
  hidden, process-local boundary;
- two distinct persistent synthetic Clerk Development identities are available
  as User A and User B;
- the existing authorized Django-admin Operator path works with the required
  Catch and participation permissions;
- no maintainer is concurrently changing the selected fixtures or deployment;
  and
- the temporary probe source has been completely reviewed against the security
  contract below.

Use `railway status --json` only to confirm safe target identity. Never run a
Railway variables command for routine diagnosis. Deployment metadata and live
behavior provide revision evidence; do not add a build-information endpoint.

## Actors and stable fixtures

| Alias | Durable role |
| --- | --- |
| User A | Onboarded, enabled synthetic player and owner of Fursuit A. |
| User B | Distinct onboarded, enabled synthetic player and primary catcher. |
| Operator | Existing authorized Django-admin path used for fixture reconciliation, lifecycle controls where required, and Catch inspection/deletion. |
| Convention 1 | Stable synthetic active Convention used for the primary Catch. |
| Convention 2 | Stable synthetic Convention used only for the wrong-Convention boundary. |
| Fursuit A | Stable synthetic fursuit owned by User A and used as the catch target. |

Before the primary run, privately resolve the exact `(User B, Fursuit A,
Convention 1)` tuple. If its Catch already exists, Operator deletes only that
Catch through the approved admin correction surface. User B's private read must
then prove the Catch absent before the primary confirmation. Never retain any
resolved internal identifier.

Capture the selected fixtures' initial safe lifecycle state in memory so that
cleanup can restore eligibility and leave a benign state. Reconcile missing
fixtures only through their approved surfaces. Never replay an ambiguous
non-idempotent creation response. If lookup is missing or ambiguous, stop for
operator reconciliation.

## One-off probe security contract

The temporary probe may orchestrate public API requests and reuse the existing
Clerk Development session helper, but it is not committed as a supported
interface. Before execution, review its complete source and require that it:

- lives in a temporary directory that is removed after the run;
- accepts the Clerk Development secret only through a hidden interactive prompt
  or another already-approved process-local secret boundary;
- keeps provider secrets, session tokens, credentials, Catch IDs, internal
  fixture IDs, timestamps used for equality checks, presigned URLs, request
  headers, and sensitive response bodies in process memory only;
- validates the exact approved HTTPS Railway Development origin and never
  follows redirects for authenticated requests;
- never prints authorization headers, sensitive request bodies, raw or decoded
  credential values, full responses, or exception details that could contain
  request material;
- creates fresh short-lived sessions when necessary and revokes supported
  ephemeral Clerk sessions on success and failure;
- emits only fixed stage aliases, expected status/outcome classes,
  `PASS`/`FAIL`/`BLOCKED`, and sanitized recovery instructions;
- sends the first primary confirmation exactly once, consumes and deliberately
  discards its response without inspecting or logging body/status, and sends one
  identical retry with the same still-valid in-memory credential;
- does not abort sockets, use a proxy, inject a failure, alter clocks, or add
  retry middleware; and
- fails closed on an unexpected outcome, redirect, schema, fixture ambiguity,
  or uncertain provider cleanup result.

The probe may pause at explicit Operator checkpoints while sensitive values
remain in memory. It must not automate Django-admin login or accept a persistent
operator credential.

## Ordered validation procedure

Execute the phases in order. A prerequisite or assertion failure stops dependent
work, while provider cleanup and benign-state recovery must still be attempted
through approved surfaces.

### Phase 1 — deterministic repository, deployment, and OpenAPI preflight

1. Run `make api-check`, `./scripts/doctor.sh`, and `git diff --check` at the
   intended application revision.
2. Run the focused real-PostgreSQL concurrency/lifecycle set and retain only
   test names, aggregate results, and PASS/FAIL.
3. Confirm required GitHub checks passed for the intended revision.
4. Confirm the successful Railway deployment reports that revision and exact
   `TailTag / development / api` target.
5. Run the existing credential-free `make api-smoke` against the approved API
   root.
6. Parse deployed OpenAPI for the path set below, Bearer security, closed
   schemas, expected outcome/status classes, and current catch semantics.
7. Confirm privately that User A, User B, and Operator access are available and
   no concurrent fixture or deployment changes are underway.

### Phase 2 — actor and fixture reconciliation

1. Authenticate User A and User B separately and require `/api/me/` success
   without retaining either body.
2. Confirm both profiles and required Convention enrollments are eligible;
   reconcile only through approved player/admin surfaces.
3. Reconcile Convention 1 and Fursuit A by stable synthetic attributes without
   retaining their identifiers.
4. Read User B's private Convention-scoped history and determine in memory
   whether the exact primary tuple already has a Catch.
5. If it exists, pause for Operator to inspect and delete it through existing
   Catch admin. Then require User B's read API to show it absent and its count
   adjusted before continuing.
6. Retain no identifiers, credentials, or raw field values in durable output.
   The participation projection used to prove deletion isolation is captured
   immediately before deletion, after the planned lifecycle mutations are
   complete, so those intentional mutations cannot confound the comparison.

### Phase 3 — eligible target, session, and credential resolution

1. Ensure User A and User B are distinct, eligible, and enrolled in Convention
   1, with Convention 1 selected as required by the approved contracts.
2. Ensure Fursuit A is globally enabled and activated for Convention 1.
3. Start an active catch session for Fursuit A and fetch its current
   Convention-scoped credential through User A's owner API.
4. As User B, resolve the credential under Convention 1. Require only the
   approved safe preview projection; resolution must not create a Catch.
5. Re-read User B's history and require that the primary Catch is still absent.

### Phase 4 — primary confirmation, repeat, and uncertain-retry proof

1. Build one confirmation request from User B with the still-valid in-memory
   credential.
2. Send it exactly once. Read enough bytes to complete the client exchange, but
   deliberately discard and do not inspect or log the returned body or status.
3. Send the byte-identical confirmation once more with the same credential.
   Require the observable retry outcome `already_caught` and retain only that
   outcome class.
4. Treat this single retry as both the repeat/already-caught observation and the
   approved ambiguous-response retry. Do not issue a third write merely to
   manufacture a separate duplicate stage.
5. Read User B's private history and require exactly one matching Catch. Keep
   its `caught_at` only in memory for equality checks and require subsequent
   duplicate/read observations to preserve it.

### Phase 5 — collection/history proof before deletion

1. Read User B's all-time history and Convention 1 history. Require the primary
   Catch in both, correct counts, server-owned `caught_at`, and approved fursuit
   and Convention context.
2. Require the stable `-caught_at, -id` ordering contract and bounded pagination;
   exercise multiple entries/pages only when the reconciled fixture set makes
   the observation meaningful. Otherwise rely on the authoritative automated
   ordering/pagination coverage and record that split.
3. Require the response shape to contain no changing denominator, credential,
   ownership/provider data, or other-player records.
4. As User A, read private history and require User B's Catch to be absent,
   establishing own-player isolation without retaining either full body.
5. Require the in-memory `caught_at` to equal the original value from the first
   post-confirmation read.

### Phase 6 — non-destructive live negative cases

1. Use User A for authenticated negative confirmations in Phases 6 and 7.
   User A owns no Catch for the primary tuple, so durable duplicate-recovery
   precedence cannot hide the eligibility branch under test. User B must not be
   used for those negative confirmations after the primary Catch exists.
2. Submit confirmation without authentication and require the generic
   authentication failure class.
3. Select Convention 2 as User A's authoritative active Convention, present the
   Convention 1 credential, and require the approved wrong-Convention conflict
   without creating a Catch. Restore Convention 1 afterward.
4. With every other prerequisite valid, have User A attempt to catch User A's
   own Fursuit A. Require the approved self-catch conflict without creating a
   Catch.
5. Re-read User B's Catch and require one row-equivalent projection with the
   unchanged `caught_at`.

### Phase 7 — lifecycle mutations and remaining live negative cases

Perform one mutation at a time, verify the expected safe failure, and restore
the prerequisite for the next case without touching the existing Catch:

1. Use User A, who still has no Catch for the tuple, for every confirmation in
   this phase. Stop Fursuit A's session and require User A's attempt to return
   target unavailable.
2. Re-establish an active session as needed, deactivate the Convention 1 target,
   and require target unavailable.
3. Restore activation/session as needed, globally disable Fursuit A through the
   existing admin surface, and require target unavailable.
4. Re-enable Fursuit A and restore target participation. Exercise at least one
   broader User A caller-eligibility boundary by disabling User A's profile,
   and require the approved caller-ineligible outcome. Missing or inactive
   enrollment remains covered by deterministic tests because its public
   outcome differs from profile disablement.
5. Restore User A eligibility. Require User B's private history to continue
   exposing exactly the original Catch with unchanged `caught_at` throughout
   target/caller staleness.

Literal time expiration is live only if a naturally expired reusable synthetic
session exists and can be exercised safely. Never wait twelve hours, alter a
clock, or add a time seam for this run.

### Phase 8 — Operator inspection and Catch deletion

1. Restore User A, User B, Convention 1, and Fursuit A to the safe eligible state
   needed for inspection and cleanup.
2. Pause for Operator to open the existing Catch admin, find the exact synthetic
   Catch using safe aliases privately, and inspect only the approved safe fields.
3. Before deletion, ensure every Catch, retry, collection/history, and
   concurrency evidence item has been captured in sanitized form.
4. Operator deletes the Catch through the existing individual admin correction
   path. Do not use bulk actions, scripts, APIs, or direct database cleanup.
5. Through User B's all-time and Convention 1 reads, require the Catch absent and
   counts reduced by exactly one from the pre-deletion observation.
6. Require User A's read isolation to remain unchanged.
7. Compare the stored in-memory activation, session, and credential row counts
   and lifecycle projections with Operator's approved post-deletion inspection.
   Require exact preservation of unrelated participation history; retain only
   the sanitized unchanged outcome.

### Phase 9 — benign-state cleanup and final evidence

1. Stop any remaining active validation catch session.
2. Leave Fursuit A globally enabled and restore both users' eligible profile and
   required stable enrollment state.
3. Leave the validation activation in its approved benign reusable state and do
   not alter unrelated users, Conventions, fursuits, or participation history.
4. Revoke every supported ephemeral Clerk session, discard all process-local
   values, remove the temporary probe directory, and verify its absence.
5. Run final `make api-check`, `./scripts/doctor.sh`, and `git diff --check`.
6. Record the checked revision, correlated Railway deployment/target, fixed
   stage outcomes, PostgreSQL test names/results, Operator deletion outcome,
   cleanup state, and any focused follow-up links below.

## Validation matrix

The `Expected evidence` column is the frozen oracle. Exact field sets and error
shapes remain those of the authoritative specifications.

| ID | Requirement | Exercise | Expected evidence |
| --- | --- | --- | --- |
| PRE-01 | Deterministic baseline | Run `make api-check`, doctor, and diff check. | PASS, or an environmental limitation is recorded without concealing it. |
| PRE-02 | Revision/target correlation | Correlate checked revision, successful deployment, and `development/api`. | One revision and approved target; no new endpoint or secret rendering. |
| PRE-03 | Public deployed baseline | Run credential-free smoke. | Liveness, readiness, schema, and docs stages PASS. |
| API-01 | Deployed OpenAPI | Parse the approved path set and relevant components. | Methods, Bearer security, closed schemas, outcomes/statuses, and semantics match. |
| PG-01 | Simultaneous canonical confirmation | Run the real-PostgreSQL canonical concurrency test. | One `created`, one `already_caught`, same Catch, one row, unchanged provenance and `caught_at`. |
| PG-02 | Lifecycle race support | Run the real-PostgreSQL lifecycle-race matrix. | Every confirmation/lifecycle pair has a valid serial outcome. |
| PG-03 | Constraint recovery | Run named raw-winner and direct uniqueness tests. | Expected named-constraint recovery and exactly one persisted row. |
| FIX-01 | Actors and stable fixtures | Reconcile User A, User B, Operator, Convention 1, and Fursuit A. | Exact synthetic aliases are unambiguous and reused. |
| FIX-02 | Clean primary tuple | Inspect User B history and, if needed, delete only through Catch admin. | Primary tuple is absent before confirmation; no direct database mutation. |
| AUTH-01 | Real authentication | Authenticate both users and call `/api/me/`. | Both succeed; identities and bodies are discarded. |
| RES-01 | Preview-only resolution | Resolve the current credential as User B, then read history. | Safe preview succeeds and no Catch exists before confirmation. |
| CATCH-01 | Uncertain first confirmation | Send the first confirmation once and discard its response. | Exchange completes; body/status is neither relied on nor retained. |
| CATCH-02 | Retry/duplicate convergence | Send one identical retry with the same credential. | `already_caught`; no third write is required. |
| CATCH-03 | Durable exactly-once result | Read private history after retry. | Exactly one matching Catch with a stable server-owned `caught_at`. |
| HIST-01 | Own all-time history | Read User B all-time history. | Correct entry, count, approved context, and no changing denominator. |
| HIST-02 | Convention history | Read User B Convention 1 history. | Same Catch and correct Convention-scoped count/context. |
| HIST-03 | Isolation and safe shape | Compare User A/User B private reads. | No other-player data, credentials, ownership/provider data, or extra fields. |
| HIST-04 | Ordering and pagination | Observe when fixtures permit; otherwise cite deterministic tests. | Stable ordering, bounded pagination, and explicit evidence split. |
| NEG-01 | Unauthenticated confirmation | Confirm without authentication. | Generic authentication failure; no new Catch. |
| NEG-02 | Self-catch | User A, who has no Catch for the tuple, confirms against owned Fursuit A with every other prerequisite valid. | Approved self-catch conflict; no new Catch. |
| NEG-03 | Wrong Convention | User A selects Convention 2 and confirms with the Convention 1 credential. | Approved conflict; no new Catch. |
| NEG-04 | Stopped session | Stop session and confirm as uncaught User A. | Target unavailable; original User B Catch unchanged. |
| NEG-05 | Deactivated target | Deactivate and confirm as uncaught User A. | Target unavailable; original User B Catch unchanged. |
| NEG-06 | Globally disabled fursuit | Disable through admin and confirm as uncaught User A. | Target unavailable; original User B Catch unchanged. |
| NEG-07 | Broader player eligibility | Disable User A's profile, then confirm. | Caller-ineligible outcome; original User B Catch unchanged. |
| AUTO-01 | Literal expiry | Run existing exact-time expiration tests; live only if naturally available. | Expired session is rejected without clock changes or waiting. |
| AUTO-02 | Exhaustive lifecycle/eligibility | Run existing deterministic matrices. | Exhaustive variants and race orderings pass. |
| ADMIN-01 | Safe inspection | Operator inspects the exact Catch in existing admin. | Safe Catch and related context only; no credential/provider leakage. |
| ADMIN-02 | Authorized correction | Operator individually deletes the Catch. | Approved deletion succeeds; no award, cleanup, or player delete path. |
| ADMIN-03 | Derived read update | Read User B history after deletion. | Catch absent and all-time/Convention counts decrease by one. |
| ADMIN-04 | Participation preservation | Compare activation, session, and credential rows/projections before and after deletion; run the focused regression assertion. | Activation/session/credential history is not rewritten. |
| END-01 | Benign fixture state | Stop session and restore approved reusable eligibility state. | Fursuit enabled, actors eligible, no active validation session, unrelated state untouched. |
| END-02 | Temporary/provider cleanup | Revoke sessions, discard values, and remove probe directory. | Cleanup and local absence checks PASS. |
| SEC-01 | Sensitive-value containment | Review output, evidence, and diff. | No prohibited value or sensitive body is retained. |

## Authoritative PostgreSQL evidence

Retain the exact result of these existing real-PostgreSQL tests, without adding
a Railway concurrency probe solely for Issue #179:

```text
tests/test_catch_confirmation_concurrency.py::test_concurrent_canonical_confirmations_converge_on_one_unchanged_catch
tests/test_catch_confirmation_concurrency.py::test_confirm_catch_and_every_lifecycle_mutation_have_a_valid_serial_outcome
tests/test_catch_confirmation_concurrency.py::test_named_duplicate_constraint_recovers_the_raw_competing_winner
tests/test_catch_concurrency.py::test_postgresql_duplicate_catch_insert_persists_exactly_one_row
```

The complete deterministic suite additionally remains authoritative for exact
expiration, exhaustive eligibility permutations, lifecycle race orders,
transaction/savepoint behavior, history privacy, ordering/pagination, and admin
deletion effects. The Issue #179 addition to the existing admin-correction test
must snapshot and preserve credential history as well as activation/session
state. Do not introduce mutation tooling for this validation; the
approved tests already reject the relevant plausible mutants: two created
outcomes, two rows, divergent canonical Catch values, changed provenance,
replaced timestamps, stale-target rejection before duplicate recovery, and
Catch deletion that mutates activation or session history. The live Operator
comparison supplies the additional credential-history deletion proof.

## Deployed OpenAPI path set

Inspect at least these Wave 3 paths and the referenced closed components:

```text
POST   /api/conventions/{convention_id}/catch-credentials/resolve/
POST   /api/catches/confirm/
GET    /api/catches/
```

Also inspect the authentication, profile, Convention/enrollment, fursuit,
activation, session, and credential paths used to establish or mutate the live
preconditions. Require the confirmation request to accept only the opaque
credential, confirmation responses to distinguish `created` from
`already_caught`, and history to remain private and Catch-derived.

## Live versus automated evidence boundary

Live Railway evidence is required for the composed success path, sequential
duplicate/uncertain retry, private reads, unauthenticated/self/wrong-Convention
failures, stopped/deactivated/disabled target failures, at least one broader
caller-eligibility failure, Operator inspection/deletion, and post-deletion
reads.

Automated PostgreSQL evidence is authoritative for literal clock expiration
when no natural fixture exists, exhaustive eligibility variants, every
lifecycle race order, simultaneous confirmation, raw uniqueness recovery, and
low-level transaction/savepoint behavior. A passing live run must not be
described as simultaneous-concurrency evidence.

## Durable evidence allowlist and denylist

The committed record may contain only:

- sanitized actor and fixture aliases;
- tested repository revision;
- correlated Railway Development deployment and `development/api` target;
- deterministic command and aggregate test results;
- fixed validation-stage and PostgreSQL test names;
- expected and observed status or outcome classes;
- `PASS`, `FAIL`, or `BLOCKED`;
- Operator deletion outcome and benign cleanup state; and
- focused follow-up issue links when needed.

It must not contain tokens, Clerk IDs, internal database IDs, Catch IDs,
Convention/fursuit IDs, raw credentials or QR payloads, bearer/session values,
presigned URLs, personal Development-account data, secret or key material,
full sensitive response bodies, or private timestamps used to correlate
provider activity. Do not include even sanitized-looking hashes of prohibited
values.

## Failure handling and recovery

On any mismatch:

1. Emit only the fixed stage alias and sanitized failure category.
2. Do not print the unexpected response or exception when it may contain
   sensitive material.
3. Stop dependent validation steps.
4. Attempt provider-session cleanup and benign fixture recovery through the
   approved public/admin surfaces.
5. If a profile, enrollment, fursuit, activation, or session may remain in a
   disruptive state, require Operator/owner reconciliation of that exact
   synthetic fixture before ending.
6. Record `FAIL` or `BLOCKED`, the safe observed boundary, and recovery result.
7. Diagnose suspected application defects separately. Do not mutate contracts
   or stack workarounds inside the probe.

An ambiguous creation response is reconciled by private Catch history, never
blind replay. The first Catch confirmation response is intentionally uncertain
by contract and is reconciled only by the one identical retry plus private
history.

## Sanitized execution record

Execution status: `PASS`.

Validation executed on 2026-09-15 against application revision
`c51dda6b5a2beb7b7aefdc07e78306b6ed401fdf`, which Railway reported as the
successful deployment for the approved `development/api` target. Values used
for private comparisons stayed in probe memory and were discarded.

```text
execution date (UTC): 2026-09-15
validated application revision: c51dda6b5a2beb7b7aefdc07e78306b6ed401fdf
Railway target: TailTag / development / api
Railway deployment: successful correlated development/api deployment
deployment correlation: PASS
deterministic baseline: PASS (1,342 tests; Semgrep 0 findings)
final post-live deterministic verification: PASS (1,342 tests; Semgrep 0 findings)
PostgreSQL simultaneous confirmation: PASS
PostgreSQL lifecycle/constraint support: PASS (25 focused cases)
authentication/fixtures: PASS
credential resolution: PASS
first confirmation response discarded: PASS
retry outcome already_caught: PASS
exactly one durable Catch: PASS
private collection/history: PASS
live negative matrix: PASS
operator inspection/deletion: PASS
post-deletion read behavior: PASS
benign fixture state: PASS
provider/probe cleanup: PASS
deployed OpenAPI: PASS
sensitive-value review: PASS
overall: PASS
```

Record one row for every matrix ID after execution:

| ID | Result | Sanitized observation |
| --- | --- | --- |
| PRE-01 | PASS | The isolated PostgreSQL baseline passed. After live cleanup, a fresh final `make api-check` again passed: 1,342 tests, formatting, lint, strict typing, Semgrep with zero findings, Django checks, migration consistency, OpenAPI validation, and production server configuration. The final `./scripts/doctor.sh` and `git diff --check` also passed. Host `make` remained unavailable because the Xcode license is not accepted, so the authoritative runs used the supported Linux devcontainer toolchain. |
| PRE-02 | PASS | The checked application revision matched Railway's successful deployment for `TailTag / development / api`. |
| PRE-03 | PASS | Credential-free liveness, readiness, schema, and documentation smoke stages passed. |
| API-01 | PASS | Deployed confirmation, resolution, and history methods, Bearer security, closed schemas, outcome classes, and status classes matched. |
| PG-01 | PASS | The canonical simultaneous-confirmation test produced one `created`, one `already_caught`, one unchanged Catch, and one row with preserved provenance and `caught_at`. |
| PG-02 | PASS | The PostgreSQL confirmation/lifecycle race matrix passed every valid serial ordering. |
| PG-03 | PASS | Named raw-winner recovery and direct uniqueness coverage passed with exactly one persisted row. |
| FIX-01 | PASS | User A, User B, Operator, Convention 1, Convention 2, and Fursuit A resolved to the established unambiguous synthetic fixtures. |
| FIX-02 | PASS | The exact primary tuple was absent before confirmation; no correction was required. |
| AUTH-01 | PASS | Both synthetic players authenticated independently. |
| RES-01 | PASS | Credential resolution returned the safe preview and created no Catch. |
| CATCH-01 | PASS | The first confirmation completed exactly once and its body and status were deliberately discarded. |
| CATCH-02 | PASS | One identical retry with the same credential returned `already_caught`. |
| CATCH-03 | PASS | Private history exposed exactly one original Catch with unchanged server-owned `caught_at` through all pre-deletion observations. |
| HIST-01 | PASS | User B's all-time history contained the expected Catch, correct count, approved context, and no changing denominator. |
| HIST-02 | PASS | Convention 1 history contained the same Catch and correct scoped count. |
| HIST-03 | PASS | User A's private history did not expose User B's Catch or any other-player data. |
| HIST-04 | PASS | The reconciled live set did not permit a meaningful multi-entry ordering/pagination observation; authoritative deterministic ordering and pagination coverage passed. |
| NEG-01 | PASS | Unauthenticated confirmation returned the authentication-failure status class and created no Catch. |
| NEG-02 | PASS | Self-catch returned `self_catch_not_allowed` and created no Catch. |
| NEG-03 | PASS | Wrong-Convention confirmation returned `active_convention_mismatch` and created no Catch. |
| NEG-04 | PASS | A stopped session returned `catch_target_unavailable`; the original Catch remained unchanged. |
| NEG-05 | PASS | A deactivated target returned `catch_target_unavailable`; the original Catch remained unchanged. |
| NEG-06 | PASS | A globally disabled fursuit returned `catch_target_unavailable`; the fursuit was restored and the original Catch remained unchanged. |
| NEG-07 | PASS | A disabled User A profile returned `catcher_ineligible`; the profile was restored and no User A Catch was created. |
| AUTO-01 | PASS | Existing deterministic exact-time expiration coverage passed; no live clock manipulation or wait was used. |
| AUTO-02 | PASS | Existing exhaustive eligibility, lifecycle, transaction, and race coverage passed. |
| ADMIN-01 | PASS | Operator inspected the exact synthetic Catch and captured a private participation projection before deletion. |
| ADMIN-02 | PASS | Operator deleted only the exact Catch through the individual existing admin correction path. |
| ADMIN-03 | PASS | User B's all-time and Convention-scoped reads no longer contained the Catch and both counts decreased by one; User A isolation remained unchanged. |
| ADMIN-04 | PASS | The private before/after projection and focused PostgreSQL regression proved activation, session, and credential history unchanged by Catch deletion. |
| END-01 | PASS | Fursuit A and User A were restored, both users selected Convention 1, the activation was reusable, and no validation catch session remained active. |
| END-02 | PASS | Ephemeral Clerk sessions were revoked, process-local values were discarded, and the temporary probe and disposable PostgreSQL resources were removed. |
| SEC-01 | PASS | Output, evidence, and diff review found no prohibited identifier, credential, payload, token, URL, personal account data, or sensitive response body. |

For any non-PASS stage, add only a sanitized description, direct-defect or
external-prerequisite classification, fixture-recovery result, and focused
follow-up disposition.

## Completion gate

Issue #179 is ready to close only when every matrix row is accounted for, the
overall live result is `PASS`, the Catch has been removed through existing
authorized admin, derived reads reflect deletion, reusable fixtures are benign,
provider and temporary artifacts are cleaned up, PostgreSQL concurrency evidence
passes, deployed OpenAPI matches the contracts, final deterministic checks are
fresh, and this record contains the sanitized validated revision and outcomes.

Any direct code fix must pass normal independent tests, review, deterministic
gates, and a complete rerun against the corrected deployed revision before the
issue can complete.
