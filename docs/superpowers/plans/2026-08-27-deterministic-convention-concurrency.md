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

---

### Task 1: Add PostgreSQL lock-observation test helpers

**Files:**
- Modify: `services/api/tests/test_convention_concurrency.py`
- Test: `services/api/tests/test_convention_concurrency.py`

**Interfaces:**
- Consumes: Django's thread-local `connection` and PostgreSQL functions `pg_backend_pid()` and `pg_blocking_pids(integer)`.
- Produces: `_postgres_backend_pid() -> int` and `_assert_backend_blocked_by(*, waiter_pid: int, holder_pid: int, timeout: float = 10.0) -> None` for later concurrency scenarios.

- [ ] **Step 1: Extend the synchronization imports**

Add `time`, `Queue`, and `Event` while retaining `Barrier` for any existing test that still needs it during the red phase:

```python
import time
from queue import Queue
from threading import Event
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

- [ ] **Step 3: Run static checks on the helper shape**

Run:

```bash
uv --directory services/api run --locked --no-sync ruff check tests/test_convention_concurrency.py
uv --directory services/api run --locked --no-sync pyright tests/test_convention_concurrency.py
```

Expected: both commands pass. If strict Pyright does not accept the cursor row
inference, narrow it explicitly without weakening project-wide type checking.

---

### Task 2: Replace timing-only races with deterministic acceptance tests

**Files:**
- Modify: `services/api/tests/test_convention_concurrency.py`
- Test: `services/api/tests/test_convention_concurrency.py`

**Interfaces:**
- Consumes: `_postgres_backend_pid`, `_assert_backend_blocked_by`, `conventions.services.require_convention_participation_eligible`, and `conventions.services._locked_eligible_profile`.
- Produces: four deterministic regression scenarios covering same-user active enrollment, same-user active selection, post-preflight profile disablement, and ACTIVE-to-PAUSED Convention serialization.

- [ ] **Step 1: Add the service and transaction imports**

Use the production module as the monkeypatch boundary and make holder commits
explicit:

```python
from django.db import close_old_connections, connection, transaction

from conventions import services
```

- [ ] **Step 2: Strengthen concurrent active enrollment**

Add `monkeypatch: pytest.MonkeyPatch`, replace the start-only barrier with
`Queue[int]`, `Event`, and a wrapper around the real profile-lock helper. Submit
the first request alone, wait until its wrapper has acquired the real profile
lock, then submit the second request and assert its backend is blocked by the
first before releasing the holder:

```python
backend_pids: Queue[int] = Queue()
first_holds_profile = Event()
release_first = Event()
original_locked_profile = services._locked_eligible_profile
lock_calls = 0

def hold_first_profile_lock(db_user: User) -> PlayerProfile:
    nonlocal lock_calls
    profile = original_locked_profile(db_user)
    lock_calls += 1
    if lock_calls == 1:
        first_holds_profile.set()
        assert release_first.wait(10)
    return profile

def enroll(con_id: int) -> int:
    close_old_connections()
    try:
        backend_pids.put(_postgres_backend_pid())
        db_user = User.objects.get(pk=user.pk)
        response = force_authenticated_client(user=db_user).post(
            "/api/conventions/enrollments/",
            {"convention_id": con_id, "set_active": True},
            content_type="application/json",
        )
        return response.status_code
    finally:
        connection.close()

monkeypatch.setattr(services, "_locked_eligible_profile", hold_first_profile_lock)

with ThreadPoolExecutor(max_workers=2) as executor:
    first = executor.submit(enroll, con1.pk)
    first_pid = backend_pids.get(timeout=10)
    assert first_holds_profile.wait(10)
    second = executor.submit(enroll, con2.pk)
    second_pid = backend_pids.get(timeout=10)
    try:
        _assert_backend_blocked_by(
            waiter_pid=second_pid,
            holder_pid=first_pid,
        )
    finally:
        release_first.set()
    statuses = (first.result(timeout=15), second.result(timeout=15))
```

Retain assertions that both responses are 200/201, both enrollments exist, and
exactly one is active. Keep the release in `finally` so failed blocker evidence
cannot strand the executor.

- [ ] **Step 3: Strengthen concurrent active selection**

Use fresh synchronization state and make the first selection own the real
profile lock before the second request starts:

```python
backend_pids: Queue[int] = Queue()
first_holds_profile = Event()
release_first = Event()
original_locked_profile = services._locked_eligible_profile
lock_calls = 0

def hold_first_profile_lock(db_user: User) -> PlayerProfile:
    nonlocal lock_calls
    profile = original_locked_profile(db_user)
    lock_calls += 1
    if lock_calls == 1:
        first_holds_profile.set()
        assert release_first.wait(10)
    return profile

def switch_active(con_id: int) -> int:
    close_old_connections()
    try:
        backend_pids.put(_postgres_backend_pid())
        db_user = User.objects.get(pk=user.pk)
        return force_authenticated_client(user=db_user).put(
            "/api/conventions/active/",
            {"convention_id": con_id},
            content_type="application/json",
        ).status_code
    finally:
        connection.close()

monkeypatch.setattr(services, "_locked_eligible_profile", hold_first_profile_lock)

with ThreadPoolExecutor(max_workers=2) as executor:
    first = executor.submit(switch_active, con1.pk)
    first_pid = backend_pids.get(timeout=10)
    assert first_holds_profile.wait(10)
    second = executor.submit(switch_active, con2.pk)
    second_pid = backend_pids.get(timeout=10)
    try:
        _assert_backend_blocked_by(
            waiter_pid=second_pid,
            holder_pid=first_pid,
        )
    finally:
        release_first.set()
    statuses = (first.result(timeout=15), second.result(timeout=15))
```

Assert both statuses are 200 and exactly one enrollment is active. Do not share
synchronization state between tests.

- [ ] **Step 4: Reproduce profile disablement between preflight and locked revalidation**

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
    assert release_after_disable.wait(10)

def enroll() -> int:
    close_old_connections()
    try:
        db_user = User.objects.get(pk=user.pk)
        return force_authenticated_client(user=db_user).post(
            "/api/conventions/enrollments/",
            {"convention_id": con.pk},
            content_type="application/json",
        ).status_code
    finally:
        connection.close()

monkeypatch.setattr(
    services,
    "require_convention_participation_eligible",
    pause_after_preflight,
)

with ThreadPoolExecutor(max_workers=1) as executor:
    request = executor.submit(enroll)
    assert preflight_passed.wait(10)
    try:
        with transaction.atomic():
            PlayerProfile.objects.filter(user=user).update(is_enabled=False)
    finally:
        release_after_disable.set()
    assert request.result(timeout=15) == 403
```

Assert no enrollment exists. The main test connection and endpoint worker are
separate connections; leaving `transaction.atomic()` commits the disablement
before the request resumes.

- [ ] **Step 5: Reproduce an ACTIVE-to-PAUSED transition that wins the row lock**

Start with an ACTIVE Convention. The pause worker locks and updates the row,
signals while its transaction remains open, and reports its backend PID. Start
the endpoint only after the holder signal, capture the endpoint PID, and prove
the blocker relationship before allowing the pause transaction to commit:

```python
backend_pids: Queue[int] = Queue()
pause_holds_convention = Event()
release_pause = Event()

def pause_convention() -> None:
    close_old_connections()
    try:
        backend_pids.put(_postgres_backend_pid())
        with transaction.atomic():
            locked = Convention.objects.select_for_update().get(pk=con.pk)
            locked.status = ConventionStatus.PAUSED
            locked.save(update_fields=["status", "updated_at"])
            pause_holds_convention.set()
            assert release_pause.wait(10)
    finally:
        connection.close()

def enroll() -> int:
    close_old_connections()
    try:
        backend_pids.put(_postgres_backend_pid())
        db_user = User.objects.get(pk=user.pk)
        return force_authenticated_client(user=db_user).post(
            "/api/conventions/enrollments/",
            {"convention_id": con.pk},
            content_type="application/json",
        ).status_code
    finally:
        connection.close()

with ThreadPoolExecutor(max_workers=2) as executor:
    pause = executor.submit(pause_convention)
    pause_pid = backend_pids.get(timeout=10)
    assert pause_holds_convention.wait(10)
    request = executor.submit(enroll)
    request_pid = backend_pids.get(timeout=10)
    try:
        _assert_backend_blocked_by(
            waiter_pid=request_pid,
            holder_pid=pause_pid,
        )
    finally:
        release_pause.set()
    pause.result(timeout=15)
    assert request.result(timeout=15) == 400
```

Refresh the Convention and assert it is PAUSED, then assert no enrollment
exists.

- [ ] **Step 6: Run the focused module and confirm all five tests pass**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_convention_concurrency.py
```

Expected: all deterministic race tests and the existing lock-order test pass
against PostgreSQL with no hang or timeout.

- [ ] **Step 7: Format and commit the deterministic test suite**

Run:

```bash
uv --directory services/api run --locked --no-sync ruff format tests/test_convention_concurrency.py
git diff --check
git add services/api/tests/test_convention_concurrency.py
git commit -m "test(api): make convention concurrency regressions deterministic"
```

Do not stage `.gitignore`.

---

### Task 3: Prove regression strength and run authoritative verification

**Files:**
- Temporarily modify and restore: `services/api/conventions/services.py`
- Verify: `services/api/tests/test_convention_concurrency.py`

**Interfaces:**
- Consumes: the deterministic tests from Task 2 and the current production locking implementation.
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

Expected: FAIL because PostgreSQL never reports the pause transaction as the
request's blocker, or because enrollment commits against stale ACTIVE state.
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
lock. Restore both lines immediately and confirm the service diff is empty.

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
configuration all pass.

- [ ] **Step 6: Inspect the final diff and worktree**

Run:

```bash
git diff --check
git status --short
git diff main...HEAD -- services/api/tests/test_convention_concurrency.py
```

Expected: no production-service diff or temporary mutant remains; `.gitignore`
is still the user's unrelated unstaged modification.
