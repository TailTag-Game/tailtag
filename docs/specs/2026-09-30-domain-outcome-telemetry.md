# Domain outcome telemetry

Issue: [#213](https://github.com/TailTag-Game/tailtag/issues/213) (OB-5).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #210 ([structured logging and request correlation](2026-09-29-structured-logging-request-correlation.md)), #211 ([telemetry privacy policy](../architecture/backend/telemetry-privacy.md)), #212 ([HTTP and backend runtime telemetry](2026-09-29-http-runtime-telemetry.md)).
Domain contracts: [catch confirmation](2026-09-09-v0-catch-confirmation-api.md), [catch credentials](2026-09-01-v0-fursuit-catch-credentials.md), [catch sessions](2026-09-01-v0-fursuit-catch-sessions.md).
Consumers: #216 (dashboard and alerts), #199 (simulations).

## Status and phase ledger

Execution: STANDARD EXPANDED. Assurance: SECURITY (telemetry privacy, public
response concealment), TEST ADEQUACY.
Completed: scope review, uncertainty review, maintainer approval of the four
design decisions (2026-09-30), repository reconnaissance, maintainer approval
of the frozen taxonomy and parent refinements 5 to 7 (2026-09-30).
Completed additionally: independent acceptance tests with parent approval, red
only for the missing `observability.outcomes` seam; clean baseline on a
disposable PostgreSQL container.
Completed additionally: independent implementation; documentation; full gate
(3,439 tests, format, lint, strict Pyright, Semgrep 0 findings,
`./scripts/doctor.sh`, `git diff --check`).
Completed additionally: independent review. SPEC, SCOPE, and SECURITY passed;
QUALITY, TEST, and TEST ADEQUACY passed with LOW findings only. Remediated by
the parent:

- F1 (LOW): the operations guide now says credential resolution checks in its
  own order and reports a non-playable Convention as `target_ineligible`; the
  `Reason` comment matches the check order.
- F2 (LOW): a malformed-JSON row covers the resolution view's parse and
  media-type branch.
- F3 (LOW): resolution read the unended session twice on rejection. It now
  reads it once after its own activation checks, so no query exists only to
  choose a reason.
- F4 (LOW): the taxonomy test requires every `FursuitCatchSessionEndReason`
  value to be a `Reason`, because ending a session converts it inside the
  transaction.

Remediation verification: the outcome, catch-confirmation, credential, and
session-lifecycle suites (203 tests), format, lint, and strict Pyright passed.
Completed additionally: independent test sweep and minimization (maintainer
request, 2026-09-30). Removed six cases whose code path another case already
covers, strengthened the revoked-first ordering case to stack every later
fault, and replaced the private `_insert_catch` patch with the public
`catches.views.confirm_catch` seam. The outcome module went from 62 to 56
cases. The outcome and catch-confirmation API tests (84), format, lint, strict
Pyright, and Semgrep passed.
Completed additionally: PR review (#266). CI lint failed on import order that a
cached local Ruff run had hidden; fixed and verified with an uncached
`make api-check` (3,434 tests). CodeRabbit found that credential resolution
recorded `resolved` before building the response, so a projection failure
counted a success on a 500. `resolved` is now recorded after the response is
built, matching catch confirmation; the unexpected-failure test failed before
the fix and passes after it. CodeRabbit's two proposed hardenings (a
best-effort recorder and runtime value checks) were not adopted: logging
handlers and the Sentry SDK do not raise into callers, and the enumerations
are enforced by strict Pyright and the metric privacy filter.
Pending: Development evidence after merge, recorded in a follow-up
documentation change as for #212.

## Problem

The generic request metric (#212) shows that `POST /api/v1/catches/` returned
404 or 200, but not why. A technically healthy API returning legitimate
already-caught results, one returning stale-credential failures, and one
returning expired-session failures all look the same. The catch, credential,
and session code already decides these outcomes, but it collapses most target
failures into one exception, as the public contracts require, and the Clerk
authenticator discards the provider's failure reason.

## Decisions

Approved by the maintainer on 2026-09-30.

1. **Target failures carry an internal reason.** `CatchTargetInvalidError` and
   `CatchCredentialNotFoundError` gain a required, closed `reason`. The
   combined target check in `confirm_catch` becomes ordered checks over the
   same conditions, and each failing check raises the same exception with its
   reason. Public responses do not change: catch-confirmation AC-10 and
   credentials AC-11 govern the public response only, and a test proves every
   reason still produces the identical response.
2. **Expiry is observed, not swept.** Expiry is recorded where the code already
   determines it: in target rejections (`session_expired`) and in
   `_terminate_locked_session`, which already gives expiry precedence. No
   background expiry sweeper is added. Lifecycle transitions are emitted on
   transaction commit, so a rolled-back transition is never counted.
3. **Authentication failures use Clerk's reason.** The authenticator maps
   `RequestState.reason` to a small TailTag set through an explicit table. A
   test iterates every member of Clerk's two reason enumerations so an SDK
   upgrade that adds a reason fails CI. A missing `Authorization` header is not
   an authentication outcome.
4. **The taxonomy below is the contract.** Values are add-only. Renaming or
   removing a value needs a maintainer decision and a documented migration for
   dashboards.

Parent refinements within the approved decisions, made while freezing the
contract:

5. Authentication reasons that describe the token carry a `token_` prefix
   (`token_expired`, `token_not_yet_valid`, `token_invalid`), because reason
   values share one namespace and the catch-session `ended` reason is already
   `expired`.
6. Credential resolution adds `convention_unknown` for a route whose Convention
   does not exist, so every resolution request that reaches the domain has an
   outcome.
7. Session-start rejections use `owner_ineligible`, `not_enrolled`, and
   `activation_ineligible`, the three existing eligibility errors.

## Taxonomy

The metric name and the log `event` are the same string.

| Signal | Outcome | Reasons |
| --- | --- | --- |
| `tailtag.catches.confirmation` | `created`, `already_caught` | none |
| | `rejected` | `payload_invalid`, `catcher_ineligible`, `convention_mismatch`, `self_catch`, and the target reasons |
| `tailtag.conventions.credential_resolution` | `resolved` | none |
| | `rejected` | `payload_invalid`, `caller_ineligible`, `convention_unknown`, and the target reasons |
| `tailtag.conventions.catch_session` | `started` | none |
| | `start_rejected` | `owner_ineligible`, `not_enrolled`, `activation_ineligible` |
| | `ended` | `owner`, `operator`, `eligibility_lost`, `expired` (the `FursuitCatchSessionEndReason` values) |
| `tailtag.authentication.verification` | `rejected` | `malformed_header`, `token_expired`, `token_not_yet_valid`, `token_invalid`, `claims_missing`, `verifier_misconfigured`, `user_resolution_unavailable`, `other` |

Target reasons, checked in this order (first failing check wins):

| Reason | Conditions |
| --- | --- |
| `credential_unknown` | No credential has the token (in resolution, also a token from another Convention), or the locked credential no longer matches the discovered one |
| `credential_revoked` | The credential exists but is revoked or rotated |
| `convention_not_playable` | The Convention is missing or not playable |
| `target_ineligible` | The target owner's profile is ineligible, the owner is not enrolled, or the fursuit is missing, disabled, or owned by someone else |
| `activation_inactive` | The activation is missing, mismatched, or inactive |
| `session_inactive` | The activation has no unended session |
| `session_expired` | The activation's unended session has reached `expires_at` |

Credential resolution applies the same meanings to its existing checks:
`activation_inactive` for an inactive activation, `target_ineligible` for an
ineligible activation, and `session_expired` or `session_inactive` when there is
no effective session.

Clerk reason mapping:

| TailTag reason | Clerk reasons |
| --- | --- |
| `malformed_header` | Header fails the bearer grammar; `SESSION_TOKEN_MISSING` |
| `token_expired` | `TOKEN_EXPIRED` |
| `token_not_yet_valid` | `TOKEN_IAT_IN_THE_FUTURE`, `TOKEN_NOT_ACTIVE_YET` |
| `token_invalid` | `TOKEN_INVALID`, `TOKEN_INVALID_SIGNATURE`, `TOKEN_INVALID_AUTHORIZED_PARTIES`, `TOKEN_INVALID_AUDIENCE`, `JWK_KID_MISMATCH`, `INVALID_TOKEN_TYPE`, `TOKEN_TYPE_NOT_SUPPORTED` |
| `claims_missing` | Signed in, but no usable `sid` or `sub` claim, or no payload |
| `verifier_misconfigured` | `SECRET_KEY_MISSING` (both enumerations), `JWK_FAILED_TO_LOAD`, `JWK_REMOTE_INVALID`, `JWK_FAILED_TO_RESOLVE`, `SERVER_ERROR` |
| `user_resolution_unavailable` | The existing 503 from `ApplicationUserResolutionUnavailable` |
| `other` | No reason, or the SDK raised `AttributeError` or `TypeError` |

## Scope

### In scope

- A shared `observability/outcomes.py` module owning the signal, outcome, and
  reason enumerations and the one function that records an outcome.
- Privacy allow-list values derived from those enumerations, and the two log
  keys.
- Internal reasons on the two target exceptions, with ordered checks.
- Emission at the catch-confirmation, credential-resolution, and catch-session
  views, in `_terminate_locked_session` and session creation (on commit), and
  in the authenticator.
- Tests for the Acceptance Contract; updates to existing tests only where an
  exception now requires a reason.
- Maintainer and contributor documentation.

### Out of scope

- Generic HTTP and runtime telemetry (#212), dependency health (#214),
  dashboards and alerts (#216), retention (#215).
- Any change to a public response, status code, header, OpenAPI schema, or
  gameplay semantic, including the 401 returned for `verifier_misconfigured`.
- A background expiry sweeper or any new persistence.
- Activation transitions as their own signal. Deactivation already appears as a
  catch session `ended` with `eligibility_lost`, and activation toggling has no
  operator question behind it yet.
- Outcomes for unauthenticated requests, unexpected failures (5xx is the request
  metric's job), credential issue and rotation, and operator catch removal.
- Entity IDs in outcome log lines or metrics. `request_id` already links an
  outcome to its request, build, and environment.
- Product analytics.

## Acceptance Contract

**AC-1 One shared recorder.** `observability.outcomes.record_outcome(signal,
outcome, reason=None)` is the only code that emits a domain outcome. Each call
writes one INFO log line with `event` set to the signal, `tailtag_outcome`, and
`tailtag_reason` when a reason is given, plus the existing correlation and build
fields. It also emits one Sentry count of 1 named by the signal with
`tailtag.outcome` and, when given, `tailtag.reason`. Feature code never calls
`sentry_sdk.metrics` directly.

**AC-2 Bounded values.** The privacy policy's outcome and reason sets equal the
enumeration values, so every recorded outcome keeps its attributes through
`scrub_metric` without a rejection warning. The log keys `tailtag_outcome` and
`tailtag_reason` are allow-listed. No outcome log line or metric carries an ID,
token, payload, Clerk identifier, or free text.

**AC-3 Catch confirmation.** An authenticated request that reaches the
catch-confirmation view records exactly one `tailtag.catches.confirmation`
outcome:

- `created` for a 201, `already_caught` for a 200;
- `rejected` with `payload_invalid` for a malformed body or payload;
- `rejected` with `catcher_ineligible`, `convention_mismatch`, or `self_catch`
  for those errors;
- `rejected` with the target reason from the ordered checks for a 404.

An unexpected failure records no domain outcome.

**AC-4 Credential resolution.** An authenticated request that reaches the
resolution view records exactly one `tailtag.conventions.credential_resolution`
outcome: `resolved`, or `rejected` with `payload_invalid`, `caller_ineligible`,
`convention_unknown`, or a target reason. A revoked credential yields
`credential_revoked`, not `credential_unknown`.

**AC-5 Public responses unchanged.** For every target reason, the catch
confirmation response is exactly the frozen 404 `catch_target_unavailable`
response, and the resolution response is exactly the frozen 404 `Catch
credential not found.` response. No other status, body, header, or OpenAPI
schema changes. Existing domain tests pass without changes to their assertions
about behavior.

**AC-6 Same conditions.** The ordered checks accept and reject exactly the same
states as before. Only the reason differs between rejected states. No new query
decides an outcome.

**AC-7 Catch session lifecycle.**

- Creating a new session records `started` after commit. Returning an existing
  unexpired session records nothing.
- Every session ended through `_terminate_locked_session` records `ended` after
  commit, with the session's `end_reason` as the reason. That includes starting
  over an expired session, which records `ended` with `expired` and then
  `started`.
- A start rejected by an eligibility error records `start_rejected` with its
  reason.
- A rolled-back transaction records nothing.

**AC-8 Authentication.** Every `AuthenticationFailed` raised by the Clerk
authenticator, and the 503 for unavailable user resolution, records exactly one
`tailtag.authentication.verification` `rejected` outcome with the mapped
reason. A request without an `Authorization` header records none. Every member
of Clerk's `TokenVerificationErrorReason` and `AuthErrorReason` has an explicit
mapping.

**AC-9 Diagnosis.** From outcome metrics and the request metric alone, a
maintainer can tell apart:

- a stale-credential failure (`credential_revoked`);
- an expired or stopped session (`session_expired`, `session_inactive`);
- a legitimate already-caught result (`already_caught`);
- a generic server error (5xx in `tailtag.http.server.requests`, no domain
  outcome).

**AC-10 Documentation.** Maintainer documentation explains each signal, outcome,
and reason, how to read them in Sentry and Railway, and the known limits.
Contributor documentation explains how to add a new outcome or reason. The
observability architecture, telemetry privacy policy, and logging guide are
updated to match.

## Design

- `observability/outcomes.py`
  - `Signal`, `Outcome`, and `Reason` are `StrEnum`s holding the taxonomy.
  - `record_outcome(signal, outcome, reason=None)` logs through a module logger
    and calls `sentry_sdk.metrics.count`.
  - It imports nothing from feature modules.
- `observability/privacy.py` derives `_OUTCOMES` and `_REASONS` from `Outcome`
  and `Reason`, so the two cannot drift.
- `observability/logging.py` adds `tailtag_outcome` and `tailtag_reason` to
  `ALLOWED_EXTRA_FIELDS`.
- `catches/services.py`
  - `CatchTargetInvalidError(reason: Reason)`.
  - The target block in `confirm_catch` becomes ordered checks in the order of
    the target-reason table. An unknown token at discovery raises
    `credential_unknown`. The self-catch check stays after the target checks.
- `conventions/catch_credentials.py`
  - `CatchCredentialNotFoundError(reason: Reason)`.
  - `resolve_catch_credential` looks the token up within the Convention without
    the `revoked_at` filter, then rejects a revoked row with
    `credential_revoked`. The token is unique, so the accepted set is unchanged.
  - The session check tells an expired unended session from no unended session
    by reading the activation's one unended session. At most one exists
    (`conventions_catch_session_one_unended_per_activation`).
    `get_effective_fursuit_catch_session_for_activation` shares that read so
    there is still one definition of an effective session.
- Views
  - `CatchConfirmationView` and `FursuitCatchCredentialResolutionView` record
    one outcome per authenticated request, from their existing exception
    mapping.
  - `FursuitCatchSessionDetailView` records `start_rejected` in its existing
    mapping of the three eligibility errors.
- `conventions/catch_sessions.py`
  - `_terminate_locked_session` registers `ended` with
    `transaction.on_commit` when it ends a session.
  - Session creation registers `started` the same way.
- `authentication/clerk.py` and `authentication/drf.py` record `rejected` with
  the mapped reason immediately before raising, using a module-level mapping
  from Clerk reasons.

## Test surface

Seams the tests use, which production code must provide:

- `observability.outcomes.Signal`, `Outcome`, `Reason` with the values above,
  and `record_outcome(signal: Signal, outcome: Outcome, reason: Reason | None = None) -> None`.
- `catches.services.CatchTargetInvalidError(reason)` and
  `conventions.catch_credentials.CatchCredentialNotFoundError(reason)`, each
  exposing `.reason`.
- `authentication.clerk.CLERK_FAILURE_REASONS`: a mapping from every Clerk
  `TokenVerificationErrorReason` and `AuthErrorReason` member to a `Reason`.

Rules:

- Domain tests build real database states with the existing test-support
  modules and drive the real views through Django's test client. Outcomes are
  observed through the captured stdout JSON lines and the capturing Sentry
  transport from `tests/observability_test_support.py`.
- Clerk verification tests substitute only the provider boundary: the
  `authenticate_request` result (`RequestState`). The authenticator and DRF
  composition stay real.
- Target-reason and response-equality cases are parameterized, not repeated.
- Negative tests use synthetic sentinel values, never real credentials.
- Extend existing test modules and support helpers rather than adding parallel
  ones.

## Risks

- **Ordered checks change which reason a multi-fault state gets.** Only the
  reason; the accept/reject set is fixed by AC-6 and existing tests.
- **Resolution refactor touches the effective-session query.** Existing
  lifecycle, concurrency, and integrity tests for resolution and sessions guard
  it.
- **Taxonomy is consumed by #216.** Add-only rule (Decision 4).

## Known limitations

- A session that expired and was later ended by an owner stop, eligibility
  loss, or a new start records `ended` with `expired` only when that happens.
  A session nobody touches after expiry records no `ended` at all.
- Once an expired session has been ended, later target rejections report
  `session_inactive`, not `session_expired`.
- `verifier_misconfigured` failures still return 401 to the client. Changing
  that response is a separate decision.
- Outcome counts can differ slightly from the request metric: unauthenticated
  requests and unexpected failures have no domain outcome.
