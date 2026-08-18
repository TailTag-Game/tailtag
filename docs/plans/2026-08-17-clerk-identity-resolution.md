# Clerk Identity Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve verified Clerk subjects to one stable TailTag-owned application user and expose that user through the canonical global DRF authentication contract.

**Architecture:** `accounts/resolution.py` owns exact application-user lookup, minimal just-in-time provisioning, constraint-specific PostgreSQL race recovery, and conservative dependency-availability classification. `authentication/drf.py` composes the existing verification-only Clerk adapter with that resolver and returns `(accounts.User, None)` through one global DRF authentication class.

**Tech Stack:** Python 3.13, Django 6.0.8, Django REST Framework 3.17.1, PostgreSQL 17, psycopg 3.3.4, pytest-django 4.12.0, Ruff, strict Pyright.

## Global Constraints

- Issue #97 and `docs/specs/2026-08-17-clerk-identity-resolution.md` are authoritative.
- Do not modify `accounts.User`, existing migrations, Clerk verification semantics, or production URLs.
- Do not add global permission policy, a current-user endpoint, profile behavior, provider metadata synchronization, `last_login` writes, lifecycle behavior, deletion, roles, permissions, or webhooks.
- Use `User.objects.create_user(clerk_user_id=subject)` for first-use provisioning; do not use raw SQL or replace the model constraint.
- Recover only SQLSTATE `23505` naming `accounts_user_clerk_user_id_42d1a61f_uniq` as the expected race.
- Translate only conservatively classified connection/availability failures to a provider-neutral unavailable exception and generic `503`; all other failures retain the generic `500` path.
- Public responses and new exception messages must not contain Clerk subjects, tokens, SQL text, connection details, constraint details, or provider internals.
- Acceptance tests are independently authored and may not be weakened to accommodate production implementation.
- Do not push, merge, deploy, close the issue, modify external environments, or perform a database reset.

## File map

- `services/api/accounts/resolution.py`: application-user lookup, provisioning, exact race recovery, and availability classification.
- `services/api/authentication/drf.py`: DRF `BaseAuthentication` adapter and generic `503` translation.
- `services/api/config/settings/base.py`: global DRF authentication-class installation without permission changes.
- `services/api/tests/test_identity_resolution.py`: independent resolution, concurrency, failure, and assembled-DRF acceptance tests.
- `services/api/tests/test_clerk_authentication.py`: replace only issue #96's temporary assertion that no global authentication class exists; retain its verification-only boundary assertions.
- `services/api/README.md`: implementation-coupled final identity flow and issue boundaries.
- `docs/specs/2026-08-17-clerk-identity-resolution.md`: approved canonical design and Acceptance Contract; no behavioral edits during implementation.

---

### Task 1: Lock independent acceptance and regression tests

**Files:**
- Create: `services/api/tests/test_identity_resolution.py`
- Modify: `services/api/tests/test_clerk_authentication.py`

**Interfaces:**
- Consumes: only issue #97 and the approved spec; do not inspect a proposed production implementation.
- Produces: locked behavioral tests for `resolve_application_user(clerk_user_id: str) -> accounts.User`, `ApplicationUserResolutionUnavailable`, `EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT`, and `authentication.drf.TailTagAuthentication`.

- [ ] **Step 1: Add first-use, repeat, distinct, case-sensitive, and no-side-effect tests**

Create `tests/test_identity_resolution.py` with PostgreSQL-backed tests equivalent to:

```python
@pytest.mark.django_db
def test_first_resolution_provisions_only_the_minimal_tailtag_user() -> None:
    user = resolve_application_user("user_first_use")

    assert user.clerk_user_id == "user_first_use"
    assert User.objects.filter(clerk_user_id="user_first_use").count() == 1
    assert not user.is_staff
    assert not user.is_superuser
    assert user.last_login is None
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_repeated_resolution_returns_the_same_unchanged_user() -> None:
    first = resolve_application_user("user_repeat")
    with CaptureQueriesContext(connection) as queries:
        second = resolve_application_user("user_repeat")

    assert second.pk == first.pk
    assert User.objects.filter(clerk_user_id="user_repeat").count() == 1
    assert second.last_login is None
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries.captured_queries
    )


@pytest.mark.django_db
def test_distinct_and_case_distinct_subjects_get_distinct_users() -> None:
    exact = resolve_application_user("user_CaseSensitive")
    different_case = resolve_application_user("user_casesensitive")
    other = resolve_application_user("user_other")

    assert len({exact.pk, different_case.pk, other.pk}) == 3
```

Also create an existing user with nondefault Django administration flags and assert resolution returns the same row without changing any field.

- [ ] **Step 2: Add migrated-constraint and real concurrency tests**

Use `@pytest.mark.django_db(transaction=True)`, `ThreadPoolExecutor`, `Barrier`, `close_old_connections()`, and per-worker connections. Synchronize both calls immediately before their `create_user()` insert so PostgreSQL sees competing inserts for one subject. Assert:

```python
manager = User.objects
original_create_user = manager.create_user
insert_barrier = Barrier(2)

def synchronized_create_user(*args: object, **kwargs: object) -> User:
    insert_barrier.wait(timeout=10)
    return original_create_user(*args, **kwargs)

monkeypatch.setattr(manager, "create_user", synchronized_create_user)
```

Each worker calls `close_old_connections()` before resolution and closes its
thread-local connection in `finally`. Assert:

```python
assert set(returned_primary_keys) == {winning_primary_key}
assert User.objects.filter(clerk_user_id=subject).count() == 1
```

Inspect `connection.introspection.get_constraints()` and assert the centralized constraint identifier exists, is unique, and covers exactly `clerk_user_id`. The concurrency test must execute actual ORM inserts against PostgreSQL; a mocked `IntegrityError` is not sufficient.

- [ ] **Step 3: Add constraint-specific negative tests**

Use ORM operations to make a patched provisioning call fail on `accounts_user_pkey` and on `accounts_user_clerk_user_id_not_empty`. Assert both real `IntegrityError` instances propagate rather than returning a user. Add a focused test proving an `IntegrityError` without a psycopg `23505` cause or without the expected diagnostic constraint is propagated.

Also simulate expected `23505` metadata without a winning row and assert the
original integrity failure propagates; a missing winner must not become
`User.DoesNotExist` or a successful resolution.

The expected-race test must prove the winning-row reread occurs after the failed inner savepoint by successfully querying through an outer `transaction.atomic()` block after recovery.

- [ ] **Step 4: Add conservative availability-classifier tests**

Construct Django `OperationalError` wrappers with structured psycopg causes and patch the initial ORM lookup to raise them. Cover:

```text
08xxx connection exception                 -> ApplicationUserResolutionUnavailable
57P01 admin_shutdown                       -> ApplicationUserResolutionUnavailable
57P02 crash_shutdown                       -> ApplicationUserResolutionUnavailable
57P03 cannot_connect_now                    -> ApplicationUserResolutionUnavailable
no SQLSTATE plus absent/bad connection      -> ApplicationUserResolutionUnavailable
53xxx resource error                        -> original OperationalError
plain Django OperationalError               -> original OperationalError
arbitrary DatabaseError/IntegrityError      -> original exception
```

Assert the provider-neutral exception string and representation contain none of the original error text, subject, SQLSTATE, connection information, or constraint name.

- [ ] **Step 5: Add a test-only DRF request harness**

Define test-local `APIView` classes and a test-local URL configuration. Use one `AllowAny` view to inspect anonymous/successful request state and one `IsAuthenticated` view only to prove the standard Bearer challenge; do not add a production route.

Tests must establish:

```python
assert response.status_code == 200
assert response.json() == {"user_id": resolved_user.pk, "auth_is_none": True}
```

Patch only the verification boundary to return
`VerifiedClerkIdentity(subject="user_test_subject")`; allow the real resolver
to provision and retrieve the user. For disabled settings, make both the
verifier and resolver fail the test if called, then assert the request remains
anonymous.

- [ ] **Step 6: Add assembled failure-response tests**

Through the test-only URL configuration and `DEBUG=False`, verify:

- malformed supplied credentials return generic `401` plus `WWW-Authenticate: Bearer`;
- a resolver `ApplicationUserResolutionUnavailable` returns a fixed generic `503` containing none of a sentinel subject or underlying error detail;
- an unexpected resolver exception follows the generic `500` response path and contains none of its sentinel detail;
- missing credentials on the test-only protected view return `401` plus the Bearer challenge.

- [ ] **Step 7: Lock global settings and production-surface tests**

Assert:

```python
assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
    "authentication.drf.TailTagAuthentication"
]
assert "DEFAULT_PERMISSION_CLASSES" not in settings.REST_FRAMEWORK
```

Update the existing issue #96 boundary test so it continues to prove `ClerkSessionVerifier` performs no user lookup or request mutation while now expecting #97's one global authentication class. Retain the schema assertion that no production product route was added.

- [ ] **Step 8: Run the independent tests and verify the expected red state**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest \
  tests/test_identity_resolution.py tests/test_clerk_authentication.py -q
```

Expected: collection or focused assertion failures because `accounts.resolution`, `authentication.drf`, and global configuration do not exist. Existing issue #96 verifier tests should otherwise remain green. Review every failure and confirm it represents missing approved behavior rather than a fixture defect.

- [ ] **Step 9: Commit the independently authored tests**

```bash
git add services/api/tests/test_identity_resolution.py \
  services/api/tests/test_clerk_authentication.py
git commit -m "test(api): lock Clerk identity resolution contract"
```

### Task 2: Implement application-user resolution and concurrency safety

**Files:**
- Create: `services/api/accounts/resolution.py`
- Test: `services/api/tests/test_identity_resolution.py`

**Interfaces:**
- Consumes: `accounts.models.User`, Django transactions/exceptions, and structured psycopg error metadata.
- Produces: `EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT: Final[str]`, `ApplicationUserResolutionUnavailable`, and `resolve_application_user(clerk_user_id: str) -> User`.

- [ ] **Step 1: Run the resolver test subset and preserve the approved red state**

```bash
uv --directory services/api run --locked --no-sync pytest \
  tests/test_identity_resolution.py -q -k "resolution or concurrency or constraint or availability"
```

Expected: failures identify only the missing resolver interfaces and behavior.

- [ ] **Step 2: Define the narrow public resolver interface**

Create `accounts/resolution.py` with these public names:

```python
EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT: Final = (
    "accounts_user_clerk_user_id_42d1a61f_uniq"
)


class ApplicationUserResolutionUnavailable(Exception):
    """A transient application-user persistence dependency failure."""
```

Define `resolve_application_user(clerk_user_id: str) -> User` with the lookup,
provisioning, race recovery, and availability behavior in the following three
steps. The exception must use a fixed provider-neutral message or no message.
It must never interpolate `clerk_user_id` or a database exception.

- [ ] **Step 3: Implement exact lookup and minimal provisioning**

Perform an exact, case-sensitive ORM lookup on
`clerk_user_id=clerk_user_id` without prescribing a particular QuerySet lookup
method. If no user exists, call only:

```python
with transaction.atomic():
    return User.objects.create_user(clerk_user_id=clerk_user_id)
```

Do not call `get_or_create()`, normalize the subject, pass privilege flags, or write another field.

- [ ] **Step 4: Implement exact uniqueness-race recovery**

Catch `IntegrityError` outside the inner `atomic()` block. Walk the structured cause chain to the psycopg error and recover only when:

```python
driver_error.sqlstate == "23505"
and driver_error.diag.constraint_name \
    == EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT
```

After rollback, reread with exact `clerk_user_id`. If the row is unexpectedly absent, re-raise the original integrity failure. Propagate every nonmatching integrity error unchanged.

- [ ] **Step 5: Implement conservative transient-availability classification**

Catch Django `OperationalError` only around resolver database operations. Translate it only when its structured psycopg cause has:

```python
sqlstate is not None and (
    sqlstate.startswith("08")
    or sqlstate in {"57P01", "57P02", "57P03"}
)
```

or when SQLSTATE is absent and psycopg reports an absent or `pq.ConnStatus.BAD` connection. Raise `ApplicationUserResolutionUnavailable()` from `None`. Re-raise every other `OperationalError`; do not catch `DatabaseError` broadly.

- [ ] **Step 6: Run resolver, concurrency, and classifier tests**

```bash
uv --directory services/api run --locked --no-sync pytest \
  tests/test_identity_resolution.py -q -k "resolution or concurrency or constraint or availability"
```

Expected: resolver-focused tests pass; DRF/global-configuration tests remain red.

- [ ] **Step 7: Commit the resolver**

```bash
git add services/api/accounts/resolution.py
git commit -m "feat(api): resolve Clerk identities to application users"
```

### Task 3: Assemble and install canonical DRF authentication

**Files:**
- Create: `services/api/authentication/drf.py`
- Modify: `services/api/config/settings/base.py`
- Test: `services/api/tests/test_identity_resolution.py`
- Test: `services/api/tests/test_clerk_authentication.py`

**Interfaces:**
- Consumes: `settings.CLERK_AUTHENTICATION`, `ClerkSessionVerifier`, `VerifiedClerkIdentity.subject`, `resolve_application_user()`, and `ApplicationUserResolutionUnavailable`.
- Produces: `TailTagAuthentication.authenticate(request: Request) -> tuple[User, None] | None` and `TailTagAuthentication.authenticate_header(request: Request) -> str`.

- [ ] **Step 1: Run assembled-DRF tests and confirm only adapter/configuration failures remain**

```bash
uv --directory services/api run --locked --no-sync pytest \
  tests/test_identity_resolution.py tests/test_clerk_authentication.py -q
```

Expected: resolver behavior passes; adapter imports, request propagation, failures, challenge, and settings assertions fail.

- [ ] **Step 2: Define a fixed generic DRF 503**

In `authentication/drf.py`, define a private `APIException` subclass with:

```python
status_code = status.HTTP_503_SERVICE_UNAVAILABLE
default_detail = "Service temporarily unavailable."
default_code = "service_unavailable"
```

Do not attach the resolver exception as a public detail.

- [ ] **Step 3: Implement `TailTagAuthentication`**

Subclass `BaseAuthentication`. Read `settings.CLERK_AUTHENTICATION` at request time. Return `None` immediately when it is `None`; otherwise verify the underlying Django `HttpRequest` with `ClerkSessionVerifier`. Return `None` when verification finds no credentials. On success:

```python
try:
    user = resolve_application_user(identity.subject)
except ApplicationUserResolutionUnavailable:
    raise _ServiceUnavailable() from None
return user, None
```

Do not expose the identity through `request.auth`, create a temporary user, or catch another exception. Implement `authenticate_header()` to return `"Bearer"`.

- [ ] **Step 4: Install the class globally without a permission policy**

Extend the existing `REST_FRAMEWORK` mapping in `config/settings/base.py`:

```python
"DEFAULT_AUTHENTICATION_CLASSES": [
    "authentication.drf.TailTagAuthentication",
],
```

Do not add `DEFAULT_PERMISSION_CLASSES` and do not conditionally remove the class when Clerk authentication is disabled.

- [ ] **Step 5: Run all identity and Clerk authentication tests**

```bash
uv --directory services/api run --locked --no-sync pytest \
  tests/test_identity_resolution.py tests/test_clerk_authentication.py \
  tests/test_local_settings.py tests/test_production_settings.py -q
```

Expected: all selected tests pass, including existing fail-closed configuration and verification-only boundaries.

- [ ] **Step 6: Commit the DRF adapter and global configuration**

```bash
git add services/api/authentication/drf.py \
  services/api/config/settings/base.py
git commit -m "feat(api): expose resolved users through DRF authentication"
```

### Task 4: Update implementation-coupled identity documentation

**Files:**
- Modify: `services/api/README.md`

**Interfaces:**
- Consumes: implemented resolver, global DRF adapter, and approved issue boundaries.
- Produces: contributor guidance for the final verified-Clerk-to-`request.user` contract.

- [ ] **Step 1: Replace the temporary #96/#97 boundary wording**

Document the implemented flow:

```text
Bearer token -> verified Clerk subject -> exact TailTag user resolution or
minimal first-use provisioning -> accounts.User as request.user
```

State that `request.auth` is `None`, authentication is global but authorization is not, and explicitly disabled authentication leaves requests anonymous.

- [ ] **Step 2: Document integrity and failure behavior**

Explain that PostgreSQL's Clerk-ID uniqueness constraint is authoritative for concurrent first use, only the expected unique race is recovered, classified dependency unavailability is a generic `503`, and unexpected failures remain generic `500`s. Do not publish tokens, subjects, connection data, or internal failure detail in examples.

- [ ] **Step 3: Preserve child-issue boundaries**

State that #98 owns the protected current-user endpoint and permission convention, #99 owns reusable/live developer tooling, and #100 owns Railway validation. Confirm the README adds no profile, metadata-sync, lifecycle, webhook, or production-operation claim.

- [ ] **Step 4: Validate and commit documentation**

```bash
git diff --check
./scripts/doctor.sh
git add services/api/README.md
git commit -m "docs(api): document Clerk identity resolution"
```

Expected: the diff has no whitespace errors; required contributor checks pass, with any optional environment warning reported.

### Task 5: Authoritative verification and review handoff

**Files:**
- Verify all changed files; do not add a parallel command surface or unrelated cleanup.

**Interfaces:**
- Consumes: repository Make targets, approved spec, locked acceptance tests, and full branch diff.
- Produces: deterministic evidence for independent specification, quality, and integration review.

- [ ] **Step 1: Run focused tests with a fresh PostgreSQL test database**

```bash
uv --directory services/api run --locked --no-sync pytest --create-db \
  tests/test_identity_resolution.py tests/test_clerk_authentication.py \
  tests/test_local_settings.py tests/test_production_settings.py -q
```

Expected: all focused tests pass against freshly migrated PostgreSQL.

- [ ] **Step 2: Run migration-drift and schema checks**

```bash
make api-migrations-check
make api-schema-check
```

Expected: `No changes detected`; schema generation passes and contains no new product endpoint.

- [ ] **Step 3: Run the complete API verification contract**

```bash
make api-check
```

Expected: formatting, Ruff, strict Pyright, PostgreSQL-backed tests, Django checks, migration drift, schema validation, and Gunicorn configuration all pass.

- [ ] **Step 4: Run repository checks and inspect scope**

```bash
./scripts/doctor.sh
git diff --check
git status --short --branch
git diff main...HEAD --stat
git diff main...HEAD
```

Expected: required environment checks pass; no whitespace errors or unrelated files appear; `accounts.User`, migrations, Clerk verification semantics, and production URLs are unchanged.

- [ ] **Step 5: Run targeted adequacy checks**

The repository has no owned mutation-testing or Semgrep command. Record those gates as unavailable rather than installing an ad-hoc tool. Independently inspect whether the tests reject these plausible incorrect implementations:

```text
case-fold Clerk subjects
use get_or_create without constraint classification
recover any unique violation
catch every OperationalError as 503
return VerifiedClerkIdentity through request.auth
omit the global class or Bearer challenge
add global IsAuthenticated
```

- [ ] **Step 6: Dispatch independent reviews**

Provide fresh reviewers only the approved spec, locked tests, and `main...HEAD` diff:

1. specification-compliance review;
2. code-quality/security/maintainability review;
3. whole-change integration review after any remediation.

Do not provide the implementer's persuasive summary as review evidence.
