# V0 Authoritative Catch Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the sole authoritative, retry-safe, PostgreSQL-serialized V0
Catch confirmation service approved in issue #175.

**Architecture:** `catches.services.confirm_catch()` accepts only a TailTag
application `User` and exact opaque payload. It performs non-authoritative
historical discovery for durable duplicate recovery, then locks both actor
graphs in the approved Wave 2 order before authorizing a new Catch. The existing
credential preview stays lock-free and unchanged; the Catch model and schema
stay unchanged.

**Tech Stack:** Python 3.13, Django 6.0, PostgreSQL 17, psycopg 3, pytest-django,
Ruff, Pyright, Semgrep

## Global Constraints

- The frozen source of truth is
  `docs/specs/2026-09-08-v0-authoritative-catch-confirmation.md`.
- The exact public service is
  `confirm_catch(user: User, *, payload: str) -> CatchConfirmationResult`.
- Successful status values are exactly `created` and `already_caught` through
  `CatchConfirmationStatus(StrEnum)`.
- HTTP, serializers, views, OpenAPI, admin, models, migrations, dependencies,
  and generic idempotency infrastructure are out of scope.
- `resolve_catch_credential()` remains preview-only and unchanged.
- Duplicate recovery precedes current target validation and never rewrites the
  original Catch.
- New writes lock profiles, Convention, enrollments, fursuit, activation,
  credential, session, then inspect/create Catch.
- Both actor profiles and both enrollments lock in ascending primary-key order.
- Capture one `timezone.now()` only after authoritative locks.
- Expired sessions are rejected without mutation.
- Only `catches_catcher_fursuit_convention_unique` is recovered through
  structured psycopg diagnostics after nested-savepoint rollback.
- No raw payload/token, Clerk identity, target owner, or moderation/lifecycle
  detail may be exposed through errors, logs, or Catch persistence.
- Add or replace no dependency.

---

## File Map

- Modify `services/api/tests/catch_test_support.py`: create complete, reusable
  Catch-confirmation prerequisites without adding production seams.
- Create `services/api/tests/test_catch_confirmation.py`: acceptance-first
  result, authentication, validation, recovery, provenance, time, and failure
  tests.
- Create `services/api/tests/test_catch_confirmation_concurrency.py`: real
  PostgreSQL lifecycle, duplicate, raw-insert, and reciprocal race evidence.
- Create `services/api/catches/services.py`: sole catch-write service, frozen
  result/error types, lock orchestration, validation, creation, and narrow
  constraint recovery.
- Do not modify `conventions.catch_credentials` unless RED test evidence proves
  that reusing its public exact parser is insufficient. Such evidence requires
  parent review before widening the production surface.

## Environment Contract

The supported native environment uses the repository PostgreSQL container and
safe values from `services/api/.env.example` without creating or committing a
local secrets file:

```bash
docker compose --env-file services/api/.env.example \
  -f services/api/compose.yaml up -d db
export DATABASE_URL='postgresql://tailtag:tailtag-local-password@127.0.0.1:5432/tailtag_issue175'
export DJANGO_SECRET_KEY='tailtag-local-development-secret'
```

Baseline evidence already established on 2026-09-08:

- `./scripts/doctor.sh`: required checks passed; optional Dev Container CLI
  warning only.
- clean dedicated database migration: passed.
- `make api-check`: passed with 1,141 tests; 0 Ruff, Pyright, or Semgrep
  findings; no migration drift; Django/OpenAPI/Gunicorn checks passed.

### Task 1: Author the complete independent acceptance-test surface

**Ownership:** Independent test-author context owns only
`services/api/tests/catch_test_support.py`,
`services/api/tests/test_catch_confirmation.py`, and
`services/api/tests/test_catch_confirmation_concurrency.py`. It must not create
or edit production code.

**Files:**

- Modify: `services/api/tests/catch_test_support.py`
- Create: `services/api/tests/test_catch_confirmation.py`
- Create: `services/api/tests/test_catch_confirmation_concurrency.py`

**Interfaces:**

- Consumes existing models and test helpers from `accounts`, `profiles`,
  `fursuits`, `conventions`, and `catches`.
- Consumes the wished-for production API and exact types/errors from the frozen
  specification.
- Produces a complete RED acceptance surface for AC-01 through AC-16 before any
  production implementation.

- [ ] **Step 1: Extend focused test support with a valid confirmation graph**

Add a frozen `CatchConfirmationScenario` containing concrete typed references:

```python
@dataclass(frozen=True)
class CatchConfirmationScenario:
    catcher_user: User
    catcher_profile: PlayerProfile
    catcher_enrollment: ConventionEnrollment
    target_user: User
    target_profile: PlayerProfile
    fursuit: Fursuit
    convention: Convention
    target_enrollment: ConventionEnrollment
    activation: FursuitActivation
    credential: FursuitCatchCredential
    catch_session: FursuitCatchSession
    payload: str
```

Implement:

```python
def create_catch_confirmation_scenario(
    *,
    catcher_clerk_user_id: str = "catch_confirmation_catcher",
    target_owner_clerk_user_id: str = "catch_confirmation_target",
    token: str = TOKEN_A,
    self_catch: bool = False,
) -> CatchConfirmationScenario:
```

The helper must create one active Convention, complete enabled profiles,
enroll both users, set only the catcher enrollment `is_active=True`, create an
enabled target fursuit, active activation, current credential, and unended
12-hour session. For `self_catch=True`, reuse the target user/profile/enrollment
as catcher and set that enrollment active. Format `payload` through
`format_catch_credential_payload(token)` rather than reimplementing grammar.

- [ ] **Step 2: Write exact public-contract and happy-path tests**

In `test_catch_confirmation.py`, import the wished-for public names directly:

```python
from catches.services import (
    CatchActiveConventionMismatchError,
    CatchAuthenticationError,
    CatchConfirmationResult,
    CatchConfirmationStatus,
    CatchParticipationIneligibleError,
    CatchSelfCatchError,
    CatchTargetInvalidError,
    confirm_catch,
)
```

Add tests that require:

```python
result = confirm_catch(scenario.catcher_user, payload=scenario.payload)
assert result == CatchConfirmationResult(
    catch=result.catch,
    status=CatchConfirmationStatus.CREATED,
)
assert result.status.value == "created"
assert result.catch.catcher_user_id == scenario.catcher_user.pk
assert result.catch.fursuit_id == scenario.fursuit.pk
assert result.catch.convention_id == scenario.convention.pk
assert result.catch.activation_id == scenario.activation.pk
assert result.catch.catch_session_id == scenario.catch_session.pk
assert result.catch.caught_at is not None
```

Also inspect `inspect.signature(confirm_catch)` so positional/keyword structure
is exactly `(user, *, payload)` and assert the result dataclass is frozen and
the enum contains exactly `CREATED` and `ALREADY_CAUGHT`.

- [ ] **Step 3: Write defensive authentication tests**

Parametrize runtime-invalid callers: `AnonymousUser()`, an unsaved `User`, a
persisted then deleted `User` instance, and a non-User object cast only at the
test boundary. Each must raise `CatchAuthenticationError` before credential
discovery and persist no Catch. A real persisted user with no profile must
instead reach `CatchParticipationIneligibleError` after exact discovery.

- [ ] **Step 4: Write exact payload and concealed-target tests**

Require the existing `CatchCredentialPayloadInvalidError` for malformed exact
grammar examples: bare token, whitespace, wrong version, wrong length,
padding, non-ASCII, and invalid alphabet. Require `CatchTargetInvalidError` for
a well-formed unknown token and assert exception text/repr does not contain the
payload, token, target owner, or lifecycle details.

- [ ] **Step 5: Write catcher-state tests**

Parametrize incomplete onboarding fields, disabled catcher profile, and missing
catcher enrollment to require `CatchParticipationIneligibleError`. Separately
set the target enrollment inactive or select a different active Convention for
the catcher and require `CatchActiveConventionMismatchError`. Every failure
must leave Catch count zero.

- [ ] **Step 6: Write current target-state concealment tests**

For a graph with no existing Catch, independently arrange each state below and
require the same `CatchTargetInvalidError` with zero Catch rows:

```text
revoked credential
revoked credential with current replacement
credential/activation mismatch on authoritative re-read
disabled/incomplete target profile
missing target enrollment
disabled target fursuit
nonplayable Convention
inactive activation
missing session
stopped session
expired-but-unended session
```

The expired case must snapshot the session row before and after and require no
change to `ended_at`, `end_reason`, or `updated_at`.

- [ ] **Step 7: Write self-catch and rollback tests**

An otherwise valid self-catch must raise `CatchSelfCatchError` and persist
nothing. Patch the package-private Catch insert helper to raise an unrelated
`IntegrityError` with no matching diagnostic constraint and require the same
exception object to escape with zero Catch rows and no upstream mutation.

- [ ] **Step 8: Write durable duplicate-recovery tests**

First confirm a valid Catch, snapshot its complete database row, then require a
repeat to return:

```python
assert repeated.status is CatchConfirmationStatus.ALREADY_CAUGHT
assert repeated.catch.pk == first.catch.pk
assert model.objects.values().get(pk=first.catch.pk) == original_row
```

Parametrize post-commit staleness over credential rotation, operator
revocation, session stop, session expiration, activation deactivation, target
profile disablement, target enrollment removal, fursuit disablement, and
Convention nonplayable. Each historical retry must return the same unchanged
Catch. Add negative binding tests proving the token cannot recover another
catcher's Catch or a Catch for another fursuit/Convention.

- [ ] **Step 9: Write serialized-time and exact provenance tests**

Use a bounded package-private lock gate plus a patched `catches.services.timezone.now`
to prove the clock is not called until all required row locks have been
acquired. Arrange `expires_at == captured_now` and require rejection; arrange
`expires_at > captured_now` and require creation. Assert `caught_at >=
captured_now` without requiring equality and verify the locked activation and
session are the exact stored provenance.

- [ ] **Step 10: Build real PostgreSQL concurrency helpers**

In `test_catch_confirmation_concurrency.py`, adapt the repository pattern using
`ThreadPoolExecutor`, separate Django connections, `Queue[int]`,
`pg_backend_pid()`, `pg_blocking_pids()`, `Event`, and bounded timeouts. Use:

```python
lock_timeout = "18000ms"
statement_timeout = "20000ms"
future_timeout = 25.0
```

The helper must prove the waiter is blocked behind the intended holder before
release; a sleep alone is not acceptable winner selection. Always close worker
connections in `finally`.

- [ ] **Step 11: Write the lifecycle race matrix**

For each operation, run both forced serial orders—Catch first and mutation
first—using the earliest shared row lock and the real repository service:

```text
rotate_owner_catch_credential
revoke_catch_credential_as_operator
set_fursuit_catch_session_state(..., is_active=False)
set_fursuit_activation_state(..., is_active=False)
set_profile_enabled(target, False)
set_profile_enabled(catcher, False)
set_fursuit_enabled(..., False)
remove_convention_enrollment(target)
remove_convention_enrollment(catcher)
set_active_convention(catcher, other_convention) or clear_active_convention
set_convention_admin_state(..., status=PAUSED)
```

Mutation-first must produce no new Catch. Catch-first must leave exactly one
durable Catch even though the mutation may subsequently make state stale. No
worker may leak a deadlock, `IntegrityError`, or unexpected exception.

- [ ] **Step 12: Write duplicate and reciprocal races**

Require concurrent canonical confirmations to converge on one Catch PK with
one possible `CREATED` and every other success `ALREADY_CAUGHT`. Snapshot and
compare `caught_at`, activation, and session provenance.

Gate the package-private insert helper after the service's existing-Catch
inspection, commit a raw competing Catch on another connection, then resume the
real service insert. Require the real named PostgreSQL uniqueness violation to
be translated to `ALREADY_CAUGHT`; do not mock `IntegrityError` for this test.

Create two fully eligible actors at the same active Convention, each with a
catchable fursuit. Run A-to-B and B-to-A concurrently and require two `CREATED`
results, two durable rows, and no deadlock, proving ascending two-profile lock
order.

- [ ] **Step 13: Verify the focused RED state**

Run:

```bash
uv run --project services/api --locked --no-sync pytest -q \
  services/api/tests/test_catch_confirmation.py \
  services/api/tests/test_catch_confirmation_concurrency.py
```

Expected: collection fails only because `catches.services` and its approved
public names do not exist. Fix malformed setup until the RED reason is exactly
the missing production feature; do not weaken expected behavior.

- [ ] **Step 14: Produce the test traceability report**

Map every new test to AC-01 through AC-16 and the SECURITY, DATA INTEGRITY,
TEST ADEQUACY, or RELIABILITY modifier. Identify which plausible mutants each
test rejects. Remove or defer every unmapped test before implementation.

### Task 2: Approve the independent RED tests

**Ownership:** Parent/reviewer is read-only for test adequacy and scope. The
test author fixes only test defects; no production implementation starts until
approval.

**Files:**

- Review: `services/api/tests/catch_test_support.py`
- Review: `services/api/tests/test_catch_confirmation.py`
- Review: `services/api/tests/test_catch_confirmation_concurrency.py`

**Interfaces:**

- Consumes Task 1 RED tests and traceability report.
- Produces explicit approval that tests are behavior-observable, reject
  plausible incorrect implementations, and introduce no unapproved production
  seam.

- [ ] **Step 1: Check contract coverage and scope**

Require at least one mapped rejection for each AC and each plausible mutant in
the frozen specification. Reject tests of HTTP behavior, model/schema changes,
credential-preview changes, or unrelated lifecycle behavior.

- [ ] **Step 2: Check concurrency evidence quality**

Confirm every race uses real PostgreSQL, separate connections, bounded waits,
and lock observation or an explicit gate proving the interleaving. Confirm the
raw duplicate test obtains a real named-constraint violation.

- [ ] **Step 3: Re-run RED authoritatively**

Run the two focused files and require failure for the missing service only.
Record approval before dispatching production implementation.

### Task 3: Implement the sole authoritative Catch service

**Ownership:** Independent implementer owns only
`services/api/catches/services.py`. It may request replanning but must not edit
approved acceptance tests, models, migrations, APIs, admin, dependencies, or
Wave 2 lifecycle modules.

**Files:**

- Create: `services/api/catches/services.py`
- Test: `services/api/tests/test_catch_confirmation.py`
- Test: `services/api/tests/test_catch_confirmation_concurrency.py`

**Interfaces:**

- Consumes exact parser `parse_catch_credential_payload`, existing models, and
  the frozen tests/contracts.
- Produces `CatchConfirmationStatus`, `CatchConfirmationResult`, the five exact
  catch-domain errors, and `confirm_catch(user, *, payload)`.

- [ ] **Step 1: Define exact immutable results and silent domain errors**

Create:

```python
class CatchConfirmationStatus(enum.StrEnum):
    CREATED = "created"
    ALREADY_CAUGHT = "already_caught"


@dataclass(frozen=True)
class CatchConfirmationResult:
    catch: Catch
    status: CatchConfirmationStatus


class CatchAuthenticationError(Exception): ...
class CatchParticipationIneligibleError(Exception): ...
class CatchActiveConventionMismatchError(Exception): ...
class CatchTargetInvalidError(Exception): ...
class CatchSelfCatchError(Exception): ...
```

Do not put payloads, IDs, owner data, moderation state, or HTTP values in error
messages or attributes.

- [ ] **Step 2: Implement defensive user validation and historical discovery**

`_require_persisted_user(user)` must require an actual authenticated `User`
with a non-null primary key that still resolves in `accounts.User`. Parse via
`parse_catch_credential_payload(payload)`. Discover the historical credential
by exact token and project only credential, activation, fursuit, Convention,
and target-owner IDs needed for recovery and locks. Translate a well-formed
unknown token to `CatchTargetInvalidError` without echoing it.

- [ ] **Step 3: Implement bound lock-free durable recovery**

Query Catch by caller, discovered fursuit, and discovered Convention. Return
the original row with `ALREADY_CAUGHT` only after comparing those exact
identities. Do not filter on credential currentness or any present eligibility.

- [ ] **Step 4: Lock the authoritative graph without joined lock traversal**

Inside one outer `transaction.atomic()`, lock and materialize:

```python
profiles = PlayerProfile.objects.select_for_update().filter(
    user_id__in=sorted({catcher_id, target_owner_id})
).order_by("pk")
convention = Convention.objects.select_for_update().filter(pk=...).first()
enrollments = ConventionEnrollment.objects.select_for_update().filter(
    user_id__in=sorted({catcher_id, target_owner_id}),
    convention_id=...,
).order_by("pk")
fursuit = Fursuit.objects.select_for_update().filter(pk=...).first()
activation = FursuitActivation.objects.select_for_update().filter(pk=...).first()
credential = FursuitCatchCredential.objects.select_for_update().filter(pk=...).first()
session = FursuitCatchSession.objects.select_for_update().filter(
    activation_id=..., ended_at__isnull=True
).order_by("pk").first()
```

Do not use a joined `select_for_update()` that implicitly locks an earlier row
class. Validate identity links explicitly from locked foreign-key IDs.

- [ ] **Step 5: Recheck durable recovery after all locks**

Inspect Catch after the final session lock and before evaluating current
eligibility. This closes the concurrent-commit window while preserving durable
recovery precedence. If found, return it unchanged with `ALREADY_CAUGHT`.

- [ ] **Step 6: Capture time and validate catcher then target**

Call `timezone.now()` once after locks. Validate the locked catcher profile,
catcher enrollment existence and `is_active`, then locked target profile,
target enrollment, Convention, fursuit, activation, current credential/token,
and session with `ended_at is None and now < expires_at`. Use direct locked
field inspection rather than helpers that perform unlocked reads or capture a
different clock. Map catcher and target failures to the exact frozen errors.
Check self-catch only after current eligibility succeeds.

- [ ] **Step 7: Create with nested-savepoint recovery**

Attempt the exact provenance insert inside nested `transaction.atomic()`. On
`IntegrityError`, read `error.__cause__.diag.constraint_name`; re-raise unless
it equals `catches_catcher_fursuit_convention_unique`. After the nested block
has rolled back, read the canonical winner by caller/fursuit/Convention and
return it unchanged with `ALREADY_CAUGHT`. If no winner exists, re-raise the
original error.

- [ ] **Step 8: Reach GREEN incrementally**

Run the narrow behavior file after each logical slice, then the concurrency
file. Fix production code only; do not weaken approved tests.

```bash
uv run --project services/api --locked --no-sync pytest -q \
  services/api/tests/test_catch_confirmation.py
uv run --project services/api --locked --no-sync pytest -q \
  services/api/tests/test_catch_confirmation_concurrency.py
```

### Task 4: Deterministic and assurance gates

**Ownership:** Parent runs and evaluates authoritative verification. Production
or test owners fix only findings mapped to the frozen contract.

**Files:** All touched files and the complete branch diff.

**Interfaces:**

- Consumes completed tests and implementation.
- Produces deterministic, security, data-integrity, reliability, and
test-adequacy evidence before independent review.

- [ ] **Step 1: Format only touched Python files**

```bash
uv --directory services/api run --locked --no-sync ruff format \
  catches/services.py tests/catch_test_support.py \
  tests/test_catch_confirmation.py \
  tests/test_catch_confirmation_concurrency.py
```

- [ ] **Step 2: Run focused behavior and concurrency tests**

Run both new files together under the dedicated PostgreSQL database and record
the test count and runtime.

- [ ] **Step 3: Run adjacent regression tests**

```bash
uv run --project services/api --locked --no-sync pytest -q \
  services/api/tests/test_catch_integrity.py \
  services/api/tests/test_catch_concurrency.py \
  services/api/tests/test_fursuit_catch_credential_resolution.py \
  services/api/tests/test_fursuit_catch_credential_concurrency.py \
  services/api/tests/test_fursuit_catch_session_lifecycle.py \
  services/api/tests/test_fursuit_catch_session_concurrency.py
```

- [ ] **Step 4: Run authoritative repository validation**

```bash
make api-check
git diff --check
```

Require Ruff, Pyright, Semgrep, all PostgreSQL tests, Django checks, migration
drift, OpenAPI validation, and Gunicorn configuration to pass.

- [ ] **Step 5: Perform plausible-mutant analysis**

Walk every mutant listed in the frozen spec and name the exact test that would
fail. Any meaningful survivor requires a focused test-first correction; do not
introduce mutation tooling.

- [ ] **Step 6: Review security and data integrity**

Inspect errors, reprs, query projections, logs, and test failure output for raw
credential or target-state disclosure. Confirm every Catch write uses the sole
service and exact locked provenance, every normal race has a legal serial
outcome, and unrelated database errors propagate.

### Task 5: Independent reviews and final verification

**Ownership:** Fresh spec reviewer, fresh code reviewer, and fresh integration
reviewer are read-only. Parent arbitrates findings. Implementer fixes approved
BLOCKER/HIGH findings without editing acceptance tests.

**Files:** Complete branch diff against `main`.

**Interfaces:**

- Consumes frozen spec, approved tests, production implementation, and
  deterministic evidence.
- Produces independent specification, code-quality, test-adequacy, security,
  data-integrity, reliability, scope, and integration verdicts.

- [ ] **Step 1: Run fresh specification review**

Require explicit AC-01 through AC-16 accounting and classification of findings
as BLOCKER, HIGH, MEDIUM, LOW, or NIT.

- [ ] **Step 2: Run fresh code/security/data review**

Review transaction boundaries, exact row-lock order, same-type ordering,
stale-object use, structured constraint recovery, secret/privacy exposure,
failure rollback, and test determinism.

- [ ] **Step 3: Run whole-change integration review**

Confirm preview remains lock-free, no Wave 2 invariant or public behavior
changed, no second Catch authority exists, and every touched file is required
by the Scope Guard.

- [ ] **Step 4: Resolve required findings**

Resolve every Acceptance Contract violation and every BLOCKER/HIGH finding.
Parent decides whether MEDIUM findings are required, adjacent authorized fixes,
or deferred. LOW/NIT findings do not expand scope.

- [ ] **Step 5: Parent authoritative verification**

Re-run focused tests, `make api-check`, and `git diff --check` after the final
fix. Inspect `git diff main...HEAD` plus uncommitted changes for debug, scratch,
dead, duplicate, unrelated, migration, API, admin, or dependency scope.

- [ ] **Step 6: Commit only after identity verification**

Immediately before each commit, require both effective identities to be exactly:

```text
Finn the Panther <finn@finnthepanther.com>
```

Do not perform any authenticated remote operation unless
`gh api user --jq .login` immediately beforehand returns exactly
`FinnThePanther`. Pushing or opening a pull request is not authorized by this
implementation plan unless the user requests it.
