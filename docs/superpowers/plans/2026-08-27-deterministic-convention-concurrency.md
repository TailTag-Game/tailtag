# Deterministic Convention Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Convention concurrency tests deterministically prove PostgreSQL serialization and reject the previously reproduced eligibility and lifecycle races.

**Architecture:** Keep production code unchanged and coordinate real endpoint requests with test-only threading events. Capture each worker's PostgreSQL backend PID and query `pg_blocking_pids` from the observer connection so tests prove actual row-lock contention instead of inferring it from scheduler timing.

**Tech Stack:** Python 3.13, Django 6.0, pytest-django, PostgreSQL 17, `ThreadPoolExecutor`, and `threading`/`queue` synchronization primitives.

## Global Constraints

- GitHub issue 142 is the frozen Acceptance Contract.
- Use real PostgreSQL transactions and separate connections.
- Do not use sleeps as the mechanism that establishes correctness.
- Keep observable API behavior, persistence, migrations, and production service interfaces unchanged.
- Preserve the profile-before-Convention lock order and its existing assertion.
- Do not modify the user's unrelated `.gitignore` change.
- The final authoritative gate is `make api-check`.

## Final Review Amendment

This amendment supersedes every raw `Queue.get`, `Event.wait`,
`Future.result`, and polling timeout shown later in Task 1. Use one strict
hierarchy:

```python
_OBSERVER_TIMEOUT_SECONDS = 5.0
_HOLDER_GATE_TIMEOUT_SECONDS = 15.0
_SESSION_LOCK_TIMEOUT_MS = 18_000
_SESSION_STATEMENT_TIMEOUT_MS = 20_000
_FUTURE_RESULT_TIMEOUT_SECONDS = 25.0
_INITIAL_POLL_SECONDS = 0.005
_MAX_POLL_SECONDS = 0.050
```

Every worker configures its fresh PostgreSQL session before publishing its PID:

```python
def _configure_worker_session_and_get_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('lock_timeout', %s, false)",
            [f"{_SESSION_LOCK_TIMEOUT_MS}ms"],
        )
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            [f"{_SESSION_STATEMENT_TIMEOUT_MS}ms"],
        )
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])
```

Observer helpers must:

- wait at most `_OBSERVER_TIMEOUT_SECONDS` for a PID, event, or PostgreSQL
  blocker predicate;
- check `future.done()` on each poll and immediately surface its exception or
  unexpected result;
- use exponential polling backoff from `_INITIAL_POLL_SECONDS` through
  `_MAX_POLL_SECONDS`; and
- treat only the expected event or positive PostgreSQL predicate as success.

All futures and backend PIDs are initialized to `None`. In the `finally` block
inside each executor context, set every release event, then cancel any known
unfinished backend with `SELECT pg_cancel_backend(pid)` before executor
shutdown. Every result uses `_FUTURE_RESULT_TIMEOUT_SECONDS`. Worker-side
preflight, downstream, and pause gates use
`_HOLDER_GATE_TIMEOUT_SECONDS`.

For the lifecycle race, patch `ConventionEnrollment.objects.get_or_create`
with `_pause_first_downstream_call`. The lifecycle observer accepts the pause
backend as the enrollment backend's blocker only while the downstream event is
false, and rechecks that event before returning. Reaching the downstream seam
first is immediate failure. This proves the explicit Convention read lock and
prevents a later foreign-key key-share wait from satisfying the assertion.

---

### Task 1: Implement the deterministic Convention concurrency acceptance suite

**Files:**
- Modify: `services/api/tests/test_convention_concurrency.py`
- Test: `services/api/tests/test_convention_concurrency.py`

**Interfaces:**
- Consumes: Django's thread-local `connection`, PostgreSQL functions `pg_backend_pid()` and `pg_blocking_pids(integer)`, and downstream `ConventionEnrollment` manager operations reached by both corrected and historical implementations.
- Produces: the bounded worker/observer/cancellation helpers defined by the Final Review Amendment, `_pause_first_downstream_call(function: Callable[P, R]) -> tuple[Callable[P, R], Event, Event]`, and four deterministic behavioral regression scenarios.

- [ ] **Step 1: Extend the synchronization imports**

Add `time`, `Queue`, `Event`, `Lock`, and `cast`; remove `Barrier` when the
timing-only tests are replaced in this same task:

```python
import time
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Event, Lock
from typing import Any, cast

from django.db.models import QuerySet

from conventions import services
```

- [ ] **Step 2: Add backend identity and lock-observation helpers**

Place these after `_record_call`:

```python
def _postgres_backend_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _assert_backend_blocked_by(
    *, waiter_pid: int, holder_pid: int, timeout: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT %s = ANY(pg_blocking_pids(%s))",
                [holder_pid, waiter_pid],
            )
            row = cursor.fetchone()
        assert row is not None
        if bool(row[0]):
            return
        if time.monotonic() >= deadline:
            pytest.fail(
                f"PostgreSQL backend {waiter_pid} was not blocked by {holder_pid}"
            )
```

The loop may retry only until it positively observes PostgreSQL's blocker
relationship. Elapsed time is a failure bound, not evidence of correctness.

- [ ] **Step 3: Add the reusable downstream-operation gate**

Pause only the first caller before an original downstream ORM operation runs.
Fresh lock/event state is created for each test, and the second caller is never
artificially paused:

```python
def _pause_first_downstream_call[**P, R](
    function: Callable[P, R],
) -> tuple[Callable[P, R], Event, Event]:
    first_call_guard = Lock()
    first_call = True
    first_at_downstream_seam = Event()
    release_first = Event()

    def paused(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal first_call
        with first_call_guard:
            pause_this_call = first_call
            first_call = False
        if pause_this_call:
            first_at_downstream_seam.set()
            if not release_first.wait(10):
                raise TimeoutError("first downstream request was never released")
        return function(*args, **kwargs)

    return paused, first_at_downstream_seam, release_first
```

#### Behavioral acceptance tests

- [ ] **Step 4: Add the transaction import**

Make holder commits explicit:

```python
from django.db import close_old_connections, connection, transaction
```

- [ ] **Step 5: Strengthen concurrent active enrollment**

Add `monkeypatch: pytest.MonkeyPatch` and gate the first request immediately
before `get_or_create`, which both corrected and missing-profile-lock
implementations reach. The corrected request already holds the real profile
and target Convention locks at this seam:

```python
backend_pids: Queue[int] = Queue()
original_get_or_create = cast(
    Callable[..., tuple[ConventionEnrollment, bool]],
    ConventionEnrollment.objects.get_or_create,
)
gated_get_or_create, first_at_enrollment_create, release_first = (
    _pause_first_downstream_call(original_get_or_create)
)
monkeypatch.setattr(
    ConventionEnrollment.objects,
    "get_or_create",
    cast(Any, gated_get_or_create),
)

def enroll(con_id: int) -> Any:
    return _request_in_bounded_worker(
        user_id=user.pk,
        backend_pids=backend_pids,
        request=lambda client: client.post(
            "/api/conventions/enrollments/",
            {"convention_id": con_id, "set_active": True},
            content_type="application/json",
        ),
    )

first: Future[Any] | None = None
second: Future[Any] | None = None
first_pid: int | None = None
second_pid: int | None = None
with ThreadPoolExecutor(max_workers=2) as executor:
    try:
        first = executor.submit(enroll, con1.pk)
        first_pid = _wait_for_pid_or_worker_finish(
            backend_pids=backend_pids,
            future=first,
            expected="the first enrollment request setup",
        )
        _wait_for_event_or_worker_finish(
            event=first_at_enrollment_create,
            future=first,
            expected="the first enrollment downstream gate",
        )
        second = executor.submit(enroll, con2.pk)
        second_pid = _wait_for_pid_or_worker_finish(
            backend_pids=backend_pids,
            future=second,
            expected="the second enrollment request setup",
        )
        _assert_backend_blocked_by(
            waiter_pid=second_pid,
            holder_pid=first_pid,
            worker=second,
            expected="the same-user profile lock during active enrollment",
        )
        release_first.set()
        assert first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code in (
            200,
            201,
        )
        assert second.result(
            timeout=_FUTURE_RESULT_TIMEOUT_SECONDS
        ).status_code in (200, 201)
    finally:
        release_first.set()
        _cancel_if_unfinished(future=first, backend_pid=first_pid)
        _cancel_if_unfinished(future=second, backend_pid=second_pid)
```

Retain assertions that both enrollments exist and exactly one is active. The
inner `finally` releases the first downstream call before executor shutdown can
join workers.

- [ ] **Step 6: Strengthen concurrent active selection**

Gate the first request immediately before the target-enrollment lookup. Both
corrected and historical implementations reach this manager method, while the
two target Convention and enrollment rows remain distinct:

```python
backend_pids: Queue[int] = Queue()
original_target_lookup = cast(
    Callable[..., QuerySet[ConventionEnrollment]],
    ConventionEnrollment.objects.select_for_update,
)
gated_target_lookup, first_at_target_lookup, release_first = (
    _pause_first_downstream_call(original_target_lookup)
)
monkeypatch.setattr(
    ConventionEnrollment.objects,
    "select_for_update",
    cast(Any, gated_target_lookup),
)

def switch_active(con_id: int) -> Any:
    return _request_in_bounded_worker(
        user_id=user.pk,
        backend_pids=backend_pids,
        request=lambda client: client.put(
            "/api/conventions/active/",
            {"convention_id": con_id},
            content_type="application/json",
        ),
    )

first: Future[Any] | None = None
second: Future[Any] | None = None
first_pid: int | None = None
second_pid: int | None = None
with ThreadPoolExecutor(max_workers=2) as executor:
    try:
        first = executor.submit(switch_active, con1.pk)
        first_pid = _wait_for_pid_or_worker_finish(
            backend_pids=backend_pids,
            future=first,
            expected="the first selection request setup",
        )
        _wait_for_event_or_worker_finish(
            event=first_at_target_lookup,
            future=first,
            expected="the first selection downstream gate",
        )
        second = executor.submit(switch_active, con2.pk)
        second_pid = _wait_for_pid_or_worker_finish(
            backend_pids=backend_pids,
            future=second,
            expected="the second selection request setup",
        )
        _assert_backend_blocked_by(
            waiter_pid=second_pid,
            holder_pid=first_pid,
            worker=second,
            expected="the same-user profile lock during active selection",
        )
        release_first.set()
        assert (
            first.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code == 200
        )
        assert (
            second.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code == 200
        )
    finally:
        release_first.set()
        _cancel_if_unfinished(future=first, backend_pid=first_pid)
        _cancel_if_unfinished(future=second, backend_pid=second_pid)
```

Assert exactly one enrollment is active and one is inactive. Do not share
synchronization state between tests.

- [ ] **Step 7: Reproduce profile disablement between preflight and locked revalidation**

Change the test signature to accept `monkeypatch`. Wrap the real preflight,
pause only after it succeeds, run the real endpoint in a separate worker, commit
disablement from the observer connection, and release the request:

```python
preflight_passed = Event()
release_after_disable = Event()
original_preflight = services.require_convention_participation_eligible

def pause_after_preflight(db_user: User) -> None:
    original_preflight(db_user)
    preflight_passed.set()
    if not release_after_disable.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
        raise TimeoutError("enrollment was never resumed after disablement")

backend_pids: Queue[int] = Queue()

def enroll() -> Any:
    return _request_in_bounded_worker(
        user_id=user.pk,
        backend_pids=backend_pids,
        request=lambda client: client.post(
            "/api/conventions/enrollments/",
            {"convention_id": con.pk},
            content_type="application/json",
        ),
    )

monkeypatch.setattr(
    services,
    "require_convention_participation_eligible",
    pause_after_preflight,
)

request: Future[Any] | None = None
request_pid: int | None = None
with ThreadPoolExecutor(max_workers=1) as executor:
    try:
        request = executor.submit(enroll)
        request_pid = _wait_for_pid_or_worker_finish(
            backend_pids=backend_pids,
            future=request,
            expected="the enrollment request setup",
        )
        _wait_for_event_or_worker_finish(
            event=preflight_passed,
            future=request,
            expected="successful eligibility preflight",
        )
        with transaction.atomic():
            PlayerProfile.objects.filter(user=user).update(is_enabled=False)
        release_after_disable.set()
        assert (
            request.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code == 403
        )
    finally:
        release_after_disable.set()
        _cancel_if_unfinished(future=request, backend_pid=request_pid)
```

Assert no enrollment exists. The main test connection and endpoint worker are
separate connections; leaving `transaction.atomic()` commits the disablement
before the request resumes.

- [ ] **Step 8: Reproduce an ACTIVE-to-PAUSED transition that wins the row lock**

Start with an ACTIVE Convention. The pause worker locks and updates the row,
signals while its transaction remains open, and reports its backend PID. Start
the endpoint only after the holder signal. Gate enrollment before
`get_or_create`, then prove the endpoint is blocked by the pause backend while
that downstream event remains false:

```python
original_get_or_create = cast(
    Callable[..., tuple[ConventionEnrollment, bool]],
    ConventionEnrollment.objects.get_or_create,
)
gated_get_or_create, downstream_reached, release_downstream = (
    _pause_first_downstream_call(original_get_or_create)
)
monkeypatch.setattr(
    ConventionEnrollment.objects,
    "get_or_create",
    cast(Any, gated_get_or_create),
)
pause_row_updated, release_pause = Event(), Event()
pause_pids: Queue[int] = Queue()
enrollment_pids: Queue[int] = Queue()
pause: Future[Any] | None = None
enrollment: Future[Any] | None = None
pause_pid: int | None = None
enrollment_pid: int | None = None

def pause_convention() -> None:
    close_old_connections()
    try:
        with transaction.atomic():
            pause_pids.put(_configure_worker_session_and_get_pid())
            locked = Convention.objects.select_for_update().get(pk=con.pk)
            locked.status = ConventionStatus.PAUSED
            locked.save(update_fields=["status", "updated_at"])
            pause_row_updated.set()
            if not release_pause.wait(_HOLDER_GATE_TIMEOUT_SECONDS):
                raise TimeoutError("pause transaction was never released")
    finally:
        connection.close()

def enroll() -> Any:
    return _request_in_bounded_worker(
        user_id=user.pk,
        backend_pids=enrollment_pids,
        request=lambda client: client.post(
            "/api/conventions/enrollments/",
            {"convention_id": con.pk},
            content_type="application/json",
        ),
    )

with ThreadPoolExecutor(max_workers=2) as executor:
    try:
        pause = executor.submit(pause_convention)
        pause_pid = _wait_for_pid_or_worker_finish(pause_pids, pause)
        _wait_for_event_or_worker_finish(pause_row_updated, pause)
        enrollment = executor.submit(enroll)
        enrollment_pid = _wait_for_pid_or_worker_finish(
            enrollment_pids,
            enrollment,
        )
        _assert_blocked_by_holder_before_downstream(
            waiter_pid=enrollment_pid,
            holder_pid=pause_pid,
            downstream_reached=downstream_reached,
            worker=enrollment,
        )
        release_pause.set()
        assert pause.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS) is None
        assert (
            enrollment.result(timeout=_FUTURE_RESULT_TIMEOUT_SECONDS).status_code
            == 400
        )
    finally:
        release_pause.set()
        release_downstream.set()
        _cancel_if_unfinished(future=pause, backend_pid=pause_pid)
        _cancel_if_unfinished(future=enrollment, backend_pid=enrollment_pid)
```

Refresh the Convention and assert it is PAUSED, then assert no enrollment
exists.

- [ ] **Step 9: Run the focused module and confirm all five tests pass**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_convention_concurrency.py
```

Expected: all deterministic race tests and the existing lock-order test pass
against PostgreSQL with no hang or timeout.

- [ ] **Step 10: Format and commit the deterministic test suite**

Run:

```bash
uv --directory services/api run --locked --no-sync ruff format tests/test_convention_concurrency.py
git diff --check
git add services/api/tests/test_convention_concurrency.py
git commit -m "test(api): make convention concurrency regressions deterministic"
```

Do not stage `.gitignore`.

---

### Task 2: Prove regression strength and run authoritative verification

**Files:**
- Temporarily modify and restore: `services/api/conventions/services.py`
- Verify: `services/api/tests/test_convention_concurrency.py`

**Interfaces:**
- Consumes: the deterministic tests from Task 1 and the current production locking implementation.
- Produces: fresh evidence that each test rejects its corresponding former defect, plus the full repository completion evidence.

- [ ] **Step 1: Verify the missing locked revalidation mutant is rejected**

Temporarily remove only `_locked_eligible_profile(user)` from
`enroll_in_convention`, run:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_convention_concurrency.py::test_disablement_committed_before_locked_validation_forbids_enrollment
```

Expected: FAIL because enrollment returns success or mutates after the committed
disablement. Restore the production line immediately and confirm
`git diff -- services/api/conventions/services.py` is empty.

- [ ] **Step 2: Verify the missing Convention row lock mutant is rejected**

Temporarily replace the enrollment query's
`Convention.objects.select_for_update()` with `Convention.objects`, run:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_convention_concurrency.py::test_convention_paused_during_enrollment_is_rejected
```

Expected: FAIL because enrollment reaches the gated `get_or_create` seam before
the pause transaction is observed as its blocker. Retain the downstream-first
failure transcript; a later foreign-key insert wait must not satisfy the test.
Restore the production query immediately and confirm the service diff is empty.

- [ ] **Step 3: Verify missing same-user serialization is rejected**

Temporarily remove `_locked_eligible_profile(user)` from both
`enroll_in_convention` and `set_active_convention`, then run:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_convention_concurrency.py::test_concurrent_active_enrollments_same_user_serialize_cleanly_and_leave_exactly_one_active \
  tests/test_convention_concurrency.py::test_concurrent_active_selections_same_user_serialize_cleanly_and_leave_exactly_one_active
```

Expected: FAIL because the second backend is not blocked by the first profile
lock even though both requests started and reached their downstream ORM seams.
Restore both lines immediately and confirm the service diff is empty.

- [ ] **Step 4: Run the deterministic inner-loop checks**

Run:

```bash
uv --directory services/api run --locked --no-sync ruff format --check tests/test_convention_concurrency.py
uv --directory services/api run --locked --no-sync ruff check tests/test_convention_concurrency.py
uv --directory services/api run --locked --no-sync pyright tests/test_convention_concurrency.py
uv --directory services/api run --locked --no-sync pytest -q tests/test_convention_concurrency.py
```

Expected: all pass.

- [ ] **Step 5: Run the authoritative repository gate**

Run:

```bash
make api-check
```

Expected: formatting, Ruff lint, strict Pyright, Semgrep, the PostgreSQL-backed
test suite, Django checks, migration drift, OpenAPI validation, and Gunicorn
configuration all pass. When an isolated database is needed, record its exact
generated identifier and sanitized creation/drop transcript so cleanup is
auditable without exposing credentials or altering the user's existing local
database.

- [ ] **Step 6: Inspect the final diff and worktree**

Run:

```bash
git diff --check
git status --short
git diff main...HEAD -- services/api/tests/test_convention_concurrency.py
```

Expected: no production-service diff or temporary mutant remains; `.gitignore`
is still the user's unrelated unstaged modification.
