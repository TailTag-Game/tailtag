# Deterministic Convention Concurrency Regression Design

## Objective

Strengthen the Convention enrollment concurrency suite so it deterministically
exercises the previously reproduced profile-eligibility TOCTOU, Convention
lifecycle-locking, and same-user active-mutation races against real PostgreSQL
transactions.

Issue 142 is the Acceptance Contract for this change. The production locking
implementation is expected to remain unchanged unless the tests expose a new
defect.

## Scope

The change is confined to
`services/api/tests/test_convention_concurrency.py`. It preserves the existing
API behavior, persistence model, lock order, and production service interfaces.

The strengthened tests must:

- use separate PostgreSQL connections for concurrent actors;
- use events or barriers to establish transaction ordering;
- positively observe PostgreSQL lock contention where serialization is the
  behavior under test;
- reject the former missing-revalidation and missing-lock implementations;
- avoid sleeps as the mechanism that establishes correctness; and
- pass the repository's `make api-check` completion gate.

## Synchronization Design

### Profile disablement after preflight

The test wraps `require_convention_participation_eligible` with a test-only
function that first calls the real preflight. After the preflight succeeds, the
wrapper signals an event and waits for a release event.

The enrollment request runs in a worker with its own database connection. Once
the main test observes the successful preflight, a separate connection disables
the profile inside an explicit transaction and commits. The test then releases
the request. The production transaction performs its locked eligibility query
against the newly committed state and returns 403. No enrollment may exist.

This sequencing rejects the former implementation because a service that
relies only on the successful preflight proceeds to mutate after the disablement.

### ACTIVE-to-PAUSED Convention transition

A pause worker starts an explicit transaction, locks the initially ACTIVE
Convention row with `SELECT FOR UPDATE`, updates it to PAUSED, and signals while
holding the uncommitted row lock.

Only after that signal does the test start the real enrollment endpoint on a
second connection. The test gates enrollment immediately before
`ConventionEnrollment.objects.get_or_create`, and the worker reports its
PostgreSQL backend PID. The observer connection requires
`pg_blocking_pids(waiter_pid)` to identify the pause backend while the
downstream gate is still unreached. This uniquely proves enrollment blocked at
its explicit Convention read lock, before any foreign-key insert lock exists.

After this positive signal, the pause worker is released and commits.
Enrollment re-reads the locked row as PAUSED, returns 400, and creates no
enrollment. An implementation that reads without `SELECT FOR UPDATE` reaches
the downstream gate first and fails immediately. A later foreign-key key-share
wait therefore cannot produce a false-positive lifecycle-lock proof.

### Same-user active mutations

The concurrent active-enrollment and active-selection tests pause the first
request at an always-reached downstream ORM seam, after the corrected service
has acquired the profile row lock. Enrollment gates immediately before
`ConventionEnrollment.objects.get_or_create`; active selection gates before
the target-enrollment lookup. The two requests target distinct Convention and
enrollment rows, leaving the shared profile row as the only expected blocker.

After the first request reaches its seam, the second request begins and reports
its backend PID. The observer asserts that `pg_blocking_pids(second_pid)`
contains the first request's PID, then releases the first request. Both requests
must complete successfully, all intended enrollments must remain durable, and
exactly one enrollment must be active.

The tests deliberately do not gate on `_locked_eligible_profile`: an old
implementation that omits the profile lock must still start both requests and
reach both downstream seams. Its second backend has no blocker relationship to
the first, so the PostgreSQL assertion fails for the intended behavioral
reason rather than because a private helper was not called.

## PostgreSQL Observation Helper

A small test helper performs bounded polling of `pg_blocking_pids`. Threading
events establish the required ordering; the database predicate provides the
proof of serialization. The bound exists only to fail cleanly when expected
database state never appears. It must not infer correctness from elapsed time.

Backend PIDs are captured inside their owning worker connections with
`SELECT pg_backend_pid()`. The observer uses the main autocommit connection and
does not retain a transaction snapshot.

## Failure Handling

Every event wait and future result has a bounded timeout so a broken lock does
not hang the suite. Worker connections are closed in `finally` blocks. Holder
transactions are always released in cleanup paths so assertion failures cannot
strand executor threads.

Every worker also installs PostgreSQL `lock_timeout` and `statement_timeout`
session bounds. Cleanup retains each worker backend PID and uses
`pg_cancel_backend` for unfinished futures before executor shutdown. Observer
helpers surface early worker completion or exceptions instead of masking them
as event timeouts. A short polling backoff reduces database load; correctness
still requires an event or positive PostgreSQL predicate.

Timeouts use one strict hierarchy: 5 seconds for observation, 15 seconds for
holder gates, 18 seconds for PostgreSQL lock timeout, 20 seconds for statement
timeout, and 25 seconds for future results.

## Regression Evidence

In addition to running the corrected suite, regression strength will be checked
with temporary local mutants representing the former defects:

- omit locked profile revalidation after preflight;
- omit the Convention `SELECT FOR UPDATE`; and
- omit the same-user profile serialization lock.

Each affected test must fail for the behavior it is intended to protect. The
mutants are verification-only and must not remain in the final worktree.

## Verification

Run the focused concurrency module first, followed by `make api-check`. The
existing lock-order assertion remains in place. No browser QA, schema check
beyond the repository gate, migration, API documentation, or rollout work is
required because observable product behavior and persistent contracts do not
change.
