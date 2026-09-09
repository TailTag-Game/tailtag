# V0 authoritative catch validation and creation

**Issue:** [#175 — Implement authoritative V0 catch validation and
creation](https://github.com/TailTag-Game/tailtag/issues/175)

**Parent:** [#173 — Establish V0 catch creation and persistent
collections](https://github.com/TailTag-Game/tailtag/issues/173)

**Status:** Approved design, Acceptance Contract, and Test Surface Contract;
frozen on 2026-09-08 before production implementation

## Goal

Implement one canonical catch-write service that accepts only an authenticated
TailTag application user and the original opaque Convention-scoped credential
payload. The service independently resolves authoritative context, recovers an
already-committed Catch when possible, otherwise revalidates all current V0
eligibility under PostgreSQL locks, and creates exactly one durable Catch.

Current state determines whether TailTag may create a new Catch. A previously
committed Catch is durable history and may be recovered through a historical
credential for the same activation after that credential or target state
becomes stale. Recovery grants no authority to create anything new.

## Domain boundary

Add the sole normal catch-write authority to `catches.services`:

```python
class CatchConfirmationStatus(StrEnum):
    CREATED = "created"
    ALREADY_CAUGHT = "already_caught"


@dataclass(frozen=True)
class CatchConfirmationResult:
    catch: Catch
    status: CatchConfirmationStatus


def confirm_catch(
    user: User,
    *,
    payload: str,
) -> CatchConfirmationResult:
    ...
```

The service accepts no Convention ID, fursuit ID, activation ID, session ID,
owner ID, user ID, Clerk ID, or other client-supplied internal identifier.

The API layer will establish the TailTag-owned application identity. The
service nevertheless rejects an anonymous, unauthenticated, unsaved,
non-persisted, or otherwise unresolvable caller. It never accepts or resolves a
Clerk identifier.

Keep `conventions.catch_credentials.resolve_catch_credential()` lock-free and
preview-only. A narrow credential-domain helper may own exact parsing and
historical credential discovery so credential protocol knowledge is not
duplicated. It must not become another general-purpose resolver or catch-write
authority.

The Catch service owns the outer transaction, lock acquisition, authoritative
re-read, cross-domain eligibility validation, active-Convention validation,
self-catch validation, duplicate recovery, creation, and uniqueness-race
recovery.

## Domain results and errors

`CatchConfirmationResult` is the only successful result shape.
`ALREADY_CAUGHT` is a success status, not an exception.

Use this narrow catch-domain error taxonomy:

```text
CatchAuthenticationError
CatchParticipationIneligibleError
CatchActiveConventionMismatchError
CatchTargetInvalidError
CatchSelfCatchError
```

Malformed credential grammar may remain the existing
`CatchCredentialPayloadInvalidError` or be translated to an equivalent
catch-layer protocol error. HTTP concepts and status codes do not belong in
this service.

`CatchTargetInvalidError` conceals all target-side and current-credential
failures, including:

- an unknown credential;
- a revoked credential when no durable Catch can be recovered;
- credential or activation inconsistency;
- target-owner participation ineligibility;
- missing target enrollment;
- a disabled target fursuit;
- a nonplayable Convention;
- an inactive or otherwise ineligible activation;
- a missing, stopped, or expired catch session; and
- any other target state that prevents a new Catch.

Catcher-side failures remain distinct because the caller is entitled to know
their own state. Error details and representations must not disclose target
moderation state, owner identity, internal relationship identity, provider
identity, or credential/token data.

## Validation precedence

Use this logical precedence:

```text
validate concrete authenticated/persisted application user
-> parse exact credential payload
-> historical credential discovery
-> durable duplicate-recovery check
-> authoritative locked current-state validation
-> self-catch validation
-> create Catch
-> narrow uniqueness-race recovery
```

Preliminary historical discovery is not authorization. It may only identify
the rows required for duplicate recovery and deterministic locking.

## Durable duplicate recovery

After authentication, exact parsing, and historical credential discovery,
look for an existing Catch belonging to the caller whose fursuit and Convention
match the historical credential's activation. If found, return the original
Catch with `ALREADY_CAUGHT` before current target eligibility validation.

Recovery must establish all of the following:

- the caller is a concrete authenticated and persisted TailTag application
  user;
- the submitted payload uses the exact credential grammar;
- the token identifies a real historical `FursuitCatchCredential`;
- the credential's activation identifies the same fursuit and Convention as
  the Catch; and
- the Catch belongs to the caller.

Recovery does not require the credential to remain current, the session to
remain live, the activation to remain active, or either actor or the target to
remain otherwise eligible. Always return the original Catch unchanged. Do not
rewrite its activation, catch session, `caught_at`, or other provenance.

If no matching durable Catch exists, a revoked or otherwise stale credential
cannot authorize creation and produces `CatchTargetInvalidError`.

## Authoritative new-Catch validation

When duplicate recovery does not find a Catch, the service must revalidate all
of the following under the frozen locks:

- the caller has an enabled, completed, participation-eligible profile;
- the caller is enrolled in the target Convention;
- that enrollment is the caller's selected active Convention;
- the target Convention is playable;
- the historical credential is still the current unrevoked credential for its
  activation and still contains the submitted token;
- the target owner's profile remains participation eligible;
- the target owner remains enrolled in the target Convention;
- the target fursuit remains enabled;
- the activation still joins that exact fursuit and Convention and is active;
- one session still joins that activation, is unended, and satisfies
  `now < expires_at`; and
- the target fursuit is not owned by the catcher.

Every client-independent relationship is resolved and compared server-side.
The service must not trust a preview response or any client assertion.

## PostgreSQL transaction and lock order

Use preliminary, non-authoritative historical credential discovery only to
learn the IDs required for deterministic locking. Then execute the new-Catch
path in one `transaction.atomic()` boundary with this relative order:

```text
1. PlayerProfile rows: catcher and target owner, ascending primary key
2. Convention: target Convention row
3. ConventionEnrollment rows: catcher and target owner for that Convention,
   ascending primary key
4. Fursuit
5. FursuitActivation
6. FursuitCatchCredential
7. FursuitCatchSession
8. Catch inspection and creation
```

An operation may deduplicate a shared actor or skip an unavailable later row,
but it may not acquire an earlier row type after a later one. Multiple rows of
one type lock in ascending primary-key order.

The two-profile order is mandatory. Reciprocal A-to-B and B-to-A confirmations
must acquire their shared actor locks identically and must not deadlock.

After every required authoritative lock is held, re-read and validate the
locked state. Do not rely on objects or eligibility conclusions from the
preliminary discovery query.

This contract extends the approved Wave 2 hierarchy. If it requires reversing
or changing an approved Wave 2 lifecycle invariant, stop and replan rather than
modifying that invariant.

## Time semantics

Do not capture `now` before waiting for authoritative locks. For a new Catch:

```text
acquire authoritative locks
-> capture one timezone.now()
-> use that value for every time-sensitive eligibility check
```

A session valid at that serialized instant is valid for this operation even if
wall-clock expiration occurs before commit.

`Catch.caught_at` remains server-owned by `auto_now_add` and may be slightly
later than the validation instant. Do not force it to equal the captured
eligibility time.

An unended session with `expires_at <= now` is ineligible. Catch confirmation
must reject without lazily finalizing or otherwise mutating the session.

## Catch creation and uniqueness recovery

Create the Catch with the caller, authoritative fursuit and Convention, and the
locked activation and live session as provenance. Persist no raw credential or
token.

Use this narrow PostgreSQL recovery sequence:

```text
check for existing Catch
-> attempt Catch insert inside nested transaction.atomic()
-> on IntegrityError inspect structured psycopg diagnostic constraint_name
-> if it is "catches_catcher_fursuit_convention_unique":
     allow only the nested savepoint to roll back
     read the winning canonical Catch
     return ALREADY_CAUGHT
-> otherwise re-raise unchanged
```

Do not inspect exception strings, swallow broad `IntegrityError`, retry
unrelated failures, retry the whole transaction unnecessarily, create a
replacement Catch, or rewrite the winner's provenance.

## Scope Guard

**Outcome:** One canonical, retry-safe, concurrency-safe service turns a
TailTag application user and opaque credential payload into exactly one durable
Catch or the matching existing Catch.

**Non-goals:** HTTP routes, serializers, views, HTTP error mapping, OpenAPI,
collection/history reads, Catch admin or correction, schema or migration
changes, generic idempotency infrastructure, preview authorization, QR/mobile
work, offline sync, alternative capture mechanisms, proximity proof,
progression, advanced anti-cheat, and unrelated cleanup.

**Expected production change surface:** A focused `catches.services` module and,
only where required, narrow credential/session internal primitives that do not
change their approved behavior. No model, migration, API, admin, or dependency
change is authorized.

**Expected test change surface:** Focused catch-service behavior, transaction,
security, and real PostgreSQL concurrency tests, plus the minimum shared test
support required to arrange existing-domain prerequisites.

**Proof:** Acceptance-first tests mapped to AC-01 through AC-16; real
PostgreSQL concurrency/integrity evidence; exact named-constraint recovery;
plausible-mutant analysis; repository deterministic validation including
Semgrep; independent specification, code-quality, test-adequacy, security,
data-integrity, and whole-change review; and parent authoritative verification.

## Acceptance Contract

- **AC-01 — Exact input boundary:** `confirm_catch(user, *, payload)` accepts
  only the TailTag application `User` and opaque payload, with no client-supplied
  internal or provider identifiers.
- **AC-02 — Defensive application authentication:** Anonymous,
  unauthenticated, unsaved, non-persisted, and unresolvable users are rejected
  with `CatchAuthenticationError`; Clerk identifiers are never accepted or
  resolved.
- **AC-03 — Exact protocol:** Malformed payloads fail exact existing grammar
  validation. Unknown well-formed tokens produce concealed target invalidity.
- **AC-04 — Historical recovery precedence:** A matching existing Catch is
  returned with `ALREADY_CAUGHT` before current target validation, including
  after credential rotation/revocation, session termination/expiration,
  activation deactivation, or later target ineligibility.
- **AC-05 — Bound recovery:** Historical recovery requires a real credential
  whose activation fursuit and Convention match a Catch owned by the caller.
  It cannot return another catcher's Catch or authorize a new write.
- **AC-06 — Catcher authority:** New creation requires an enabled, completed,
  eligible catcher profile, enrollment in the target Convention, and that
  enrollment as the catcher's selected active Convention.
- **AC-07 — Target concealment and authority:** New creation requires a
  current credential, eligible target owner, target enrollment, enabled
  fursuit, playable Convention, eligible active activation, and current live
  session. Every target-side failure collapses to `CatchTargetInvalidError`.
- **AC-08 — Self-catch:** A currently otherwise valid attempt against a
  catcher-owned fursuit fails with `CatchSelfCatchError` and persists nothing.
- **AC-09 — Frozen locks:** New creation preserves the exact relative lock
  hierarchy and ascending same-type ordering, including two actor profiles.
- **AC-10 — Serialized time:** One `now` captured after authoritative locks
  governs session validity. Expired sessions are rejected without mutation.
- **AC-11 — Exact result:** Creation returns the new Catch with `CREATED`;
  duplicates return the one canonical Catch with `ALREADY_CAUGHT`.
- **AC-12 — Server-owned record:** Creation uses server-owned `caught_at`,
  locked activation/session provenance, and stores no credential/token.
- **AC-13 — Durable provenance:** Duplicate recovery never rewrites the
  original Catch timestamp, activation, session, or other provenance.
- **AC-14 — Narrow database recovery:** Only the named Catch tuple uniqueness
  violation is translated after nested-savepoint rollback. Every unrelated
  database failure is re-raised unchanged.
- **AC-15 — Concurrency:** Lifecycle races produce a valid serial outcome,
  duplicate callers converge on one Catch, and reciprocal catches do not
  deadlock.
- **AC-16 — Sole authority and scope:** `catches.services` is the only normal
  Catch creation path; preview behavior and Wave 2 invariants remain unchanged,
  and no excluded interface or infrastructure is introduced.

## Test Surface Contract

Tests may use:

- the public `confirm_catch` service, result types, and domain errors;
- the existing credential protocol formatter/parser to create exact payloads;
- existing repository test factories/helpers and direct ORM setup for domain
  prerequisites;
- Django model and ORM reads to verify durable Catch and unchanged provenance;
- `unittest.mock.patch` only for the existing `timezone.now` call used to prove
  post-lock capture or for a bounded synchronization hook at an approved
  package-internal seam; and
- real PostgreSQL transactions, separate connections/threads, barriers,
  events, and bounded future timeouts for concurrency evidence.

Tests must not add a public production clock, lock, callback, HTTP endpoint, or
generic injection API. Package-internal helpers may be patched only when the
test also proves meaningful database state/interleaving rather than asserting
mock calls as the behavior.

The approved behavioral test groups are:

1. exact result type, signature, and sole-authority boundary;
2. authentication and catcher eligibility failures;
3. exact payload parsing and concealed unknown/target failures;
4. active-Convention and enrollment matching;
5. target profile, enrollment, fursuit, Convention, activation, credential,
   and session boundaries;
6. self-catch;
7. creation, server timestamp, and exact provenance;
8. repeat and post-staleness durable recovery;
9. unrelated `IntegrityError` propagation and actual named-constraint recovery;
10. transaction rollback and no expired-session mutation; and
11. the concurrency matrix below.

### Required PostgreSQL concurrency matrix

Use separate database connections, bounded synchronization barriers/timeouts,
and assertions proving the intended interleaving for:

- Catch versus credential rotation;
- Catch versus operator credential revocation;
- Catch versus session stop;
- Catch versus activation deactivation;
- Catch versus target profile disablement;
- Catch versus catcher profile disablement;
- Catch versus target enrollment removal;
- Catch versus catcher enrollment or active-Convention transition;
- Catch versus Convention becoming nonplayable;
- concurrent duplicate canonical service calls;
- Catch creation versus a deliberately competing raw duplicate insert; and
- reciprocal A-to-B and B-to-A catches.

For lifecycle races, require one valid serialized outcome:

```text
mutation wins first -> no new Catch
catch wins first -> exactly one durable Catch
```

For duplicate races, require:

```text
Catch count == 1
one caller may receive CREATED
all other successful duplicate callers receive ALREADY_CAUGHT
all successful callers resolve the same Catch primary key
caught_at is unchanged
activation/session provenance is unchanged
```

Tests must also prove that unrelated database failures remain unexpected rather
than being translated to duplicate success.

## Plausible-mutant requirements

The approved tests must reject at least these plausible incorrect
implementations:

- accepting a Convention or internal target ID from the caller;
- using Clerk/provider identity in the Catch relationship;
- authorizing from lock-free preview output;
- returning another catcher's row during historical recovery;
- requiring current target state before returning a matching durable Catch;
- recovering a stale credential into a new Catch when no Catch exists;
- locking reciprocal actor profiles in caller/target rather than primary-key
  order;
- evaluating eligibility only before locks or capturing time before lock wait;
- treating `ended_at IS NULL` as sufficient after expiration;
- lazily finalizing an expired session during confirmation;
- checking self-catch from client data or omitting it;
- rewriting an existing Catch's timestamp or provenance;
- catching every `IntegrityError` as a duplicate; and
- creating more than one Catch during duplicate or lifecycle races.

## Deferred work

- #176: HTTP confirmation endpoint, serializer, status mapping, and OpenAPI.
- #177: private player collection and catch-history APIs.
- #178: restricted Catch administration and correction/removal behavior.
- #179: composed Railway Development validation and durable Wave 3 evidence.
