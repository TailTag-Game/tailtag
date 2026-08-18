# Clerk identity resolution

**Issue:** [#97 — Resolve Clerk identities to TailTag application users](https://github.com/TailTag-Game/tailtag/issues/97)

**Parent:** [#94 — Establish V0 authentication and application identity](https://github.com/TailTag-Game/tailtag/issues/94)

**Status:** Approved for implementation

## Goal

Complete the V0 authenticated identity path after Clerk session verification. A
verified Clerk subject resolves to exactly one stable TailTag-owned
`accounts.User`, and Django REST Framework exposes that user through the single
canonical request identity contract.

```text
request
  -> ClerkSessionVerifier
  -> VerifiedClerkIdentity(subject)
  -> TailTag user resolver
  -> (accounts.User, None)
```

Clerk remains the external authentication authority. `accounts.User.id` remains
the TailTag application and domain identity. `accounts.User.clerk_user_id`
remains only the opaque, case-sensitive external identity link.

## Approved boundaries

The implementation uses two deliberately separate modules:

- `accounts/resolution.py` owns application-user lookup, just-in-time
  provisioning, PostgreSQL concurrency recovery, and dependency-availability
  classification.
- `authentication/drf.py` owns DRF integration and composes the existing Clerk
  verifier with the TailTag resolver.

The implementation must not change `accounts.User`, existing migrations, the
Clerk verification contract from issue #96, or the production URL surface. If
the existing Clerk verifier cannot support this composition without a semantic
change, implementation stops and returns for replanning.

## Application-user resolution

The resolver accepts only the verified Clerk subject string and returns an
`accounts.User`. It does not receive an HTTP request, token, raw Clerk claims,
or provider configuration.

For each resolution:

1. Look up `accounts.User` using an exact `clerk_user_id` match. Do not trim,
   case-fold, normalize, or otherwise transform the verified subject.
2. If the user exists, return that user without writing any fields.
3. If the user does not exist, call the existing `User.objects.create_user()`
   contract with only `clerk_user_id` inside an inner `transaction.atomic()`
   savepoint.
4. If creation succeeds, return the created user.
5. If creation loses the expected Clerk-ID uniqueness race, let the inner
   savepoint roll back, reread by exact `clerk_user_id`, and return the winning
   user.
6. Propagate every other integrity, programming, invariant, schema, or
   unclassified failure unchanged.

Resolution and provisioning do not update `last_login`, synchronize provider
metadata, create a profile, apply lifecycle behavior, assign privileges, emit
webhooks, or perform any other side effect.

### Expected uniqueness race

The PostgreSQL uniqueness constraint on `accounts.User.clerk_user_id` is the
authoritative concurrency guard. An `IntegrityError` is recoverable as a
successful concurrent provisioning race only when structured driver metadata
establishes both:

- SQLSTATE `23505` (`unique_violation`); and
- the violated constraint is the existing unique constraint for
  `accounts_user.clerk_user_id`.

The generated constraint identifier is currently
`accounts_user_clerk_user_id_42d1a61f_uniq`. Production code centralizes that
identifier in one documented constant because race recovery must distinguish
this constraint from the model's nonempty check, password check, primary key,
and any future constraint. Tests verify that the identifier still describes a
single-column unique constraint on `clerk_user_id` in the migrated PostgreSQL
schema.

The resolver may inspect psycopg's structured cause and diagnostic metadata. It
must not parse localized exception text, use raw SQL, change the existing model
constraint, or treat a different unique violation as success.

The insert runs in an inner savepoint. The resolver catches the error outside
that failed savepoint and performs the winning-row lookup only after rollback,
so it does not query through a transaction marked for rollback.

### Transient availability classification

The resolver defines one provider-neutral resolution-unavailable exception.
It raises that exception only for a Django database `OperationalError` whose
structured psycopg cause confidently identifies connection or database
availability failure:

- a PostgreSQL connection-exception SQLSTATE in class `08`;
- PostgreSQL `57P01` (`admin_shutdown`), `57P02` (`crash_shutdown`), or `57P03`
  (`cannot_connect_now`); or
- a psycopg operational failure with no server SQLSTATE only when psycopg's
  structured connection state is absent or bad, as occurs when a connection is
  refused, lost, closed, or times out before PostgreSQL can report a server
  error.

No other SQLSTATE class is implicitly transient. In particular, the resolver
does not broadly catch or translate every Django `OperationalError`,
`DatabaseError`, `IntegrityError`, or psycopg exception. Anything not matched by
the conservative structured classifier propagates unchanged and follows the
normal generic `500` path.

The provider-neutral exception carries no Clerk subject, token, SQL text,
connection detail, constraint name, or provider detail.

## DRF authentication

`TailTagAuthentication` extends DRF's `BaseAuthentication` and is installed as
the sole global TailTag authentication class through
`REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`.

Its behavior is:

- If `settings.CLERK_AUTHENTICATION` is explicitly `None`, return `None` without
  verification or database access. The request remains anonymous.
- Otherwise, construct or use the existing `ClerkSessionVerifier` with the
  validated configuration from issue #96.
- If the verifier reports that no credentials were supplied, return `None`.
- If verification succeeds, pass only `VerifiedClerkIdentity.subject` to the
  TailTag resolver.
- Return `(resolved_user, None)` on successful resolution.
- Translate only the resolver's provider-neutral unavailable exception into a
  fixed, generic DRF `503 Service Unavailable` response.
- Allow every unexpected exception to propagate into normal generic `500`
  handling.
- Return `Bearer` from `authenticate_header()` so authentication failures and
  later protected unauthenticated requests retain the standard Bearer
  challenge and `401` behavior.

`VerifiedClerkIdentity` remains internal to the authentication composition. It
is never assigned to `request.user` or `request.auth`. The successful canonical
contract is:

```text
request.user == resolved accounts.User
request.auth is None
```

Global authentication does not establish global authorization. This issue does
not add or change `DEFAULT_PERMISSION_CLASSES`; issue #98 owns the first
`IsAuthenticated` production endpoint contract. Existing DRF `AllowAny` views
remain public for headerless requests, although a supplied invalid Bearer token
still fails authentication before permissions run.

Enabled but missing or invalid Clerk configuration continues to fail during
settings loading under the issue #96 fail-closed contract. It must never be
converted to disabled authentication at request time.

## Public failure contract

- Missing credentials produce an anonymous request.
- Invalid credentials preserve the existing generic Clerk `401` behavior and
  include `WWW-Authenticate: Bearer` through the assembled authenticator.
- A confidently classified transient resolution dependency failure produces a
  fixed generic `503` response.
- Unexpected invariant, programming, schema, integrity, or unclassified
  database failures follow the generic `500` path.
- Public responses never contain Clerk subjects, tokens, SQL text, database
  connection details, constraint details, or provider internals.

The implementation adds no logging of Clerk subjects or tokens. It does not
include sensitive values in new exception messages.

## Acceptance Contract

### Resolution behavior

- A verified subject with no existing link provisions one minimal
  `accounts.User`.
- Repeated resolution of the same subject returns the same TailTag primary key
  and creates no additional row.
- Distinct subjects resolve to distinct TailTag users.
- Subject matching is exact and case-sensitive.
- Existing users, including an existing administratively privileged user with
  the same external link, are returned unchanged.
- Resolution performs no write or side effect after the first successful
  provisioning.

### Concurrency and integrity

- A real PostgreSQL test uses separate database connections for simultaneous
  first-use resolution of one subject.
- Every concurrent caller succeeds with the same TailTag primary key.
- Exactly one row exists for that `clerk_user_id` after all callers finish.
- The migrated database constraint is the authoritative duplicate guard.
- Recovery occurs only for SQLSTATE `23505` naming the centralized
  Clerk-ID unique constraint.
- A different unique constraint, a non-unique integrity failure, or an
  `IntegrityError` without the expected structured metadata propagates.
- Winning-row lookup happens after rollback of the failed inner savepoint.

### Availability and failure handling

- Structured connection-class and explicitly listed PostgreSQL availability
  failures become the provider-neutral unavailable exception.
- A psycopg client-side operational failure without a server SQLSTATE is
  treated as dependency unavailability only when its structured connection
  state is absent or bad.
- Other operational, database, integrity, programming, and unclassified
  failures are not translated.
- The DRF adapter exposes a sanitized generic `503` only for the provider-neutral
  unavailable exception.
- Unexpected failures remain sanitized generic `500`s at the public boundary.

### DRF integration

- `TailTagAuthentication` is configured globally.
- No global permission class is added or changed.
- Explicitly disabled authentication returns `None` without verification or
  database work.
- Enabled invalid configuration still fails closed during settings loading.
- Successful authentication exposes the resolved `accounts.User` as
  `request.user` and `None` as `request.auth`.
- Invalid credentials remain generic `401`s.
- `authenticate_header()` and authentication failures use the `Bearer`
  challenge.
- A test-only DRF view/request harness proves assembled request propagation.
- No production endpoint or URL is added, and the production OpenAPI path set
  does not gain a current-user or other product route.

### Scope protection

- `accounts.User`, migrations, Clerk verification semantics, and production
  URLs remain unchanged.
- No profile fields, metadata synchronization, `last_login` writes, lifecycle
  behavior, deletion, roles, permissions, webhook behavior, or current-user API
  is introduced.
- Implementation-coupled API documentation describes the final identity and
  authentication contract without exposing secret or personal data.

## Test strategy

Acceptance and regression tests are authored independently from production
implementation. They use the repository's real PostgreSQL test database.

- Normal persistence tests cover first use, repeat use, distinct subjects,
  case sensitivity, minimal fields, and absence of later writes.
- A transactional concurrency test uses separate worker connections and
  synchronization so PostgreSQL arbitrates simultaneous first-use inserts.
- Focused integrity tests exercise the real expected unique constraint and
  prove that unrelated integrity failures are not swallowed.
- Focused classifier tests use structured psycopg exception types and SQLSTATEs,
  not message matching.
- A test-only DRF view/request harness covers disabled behavior, assembled
  success, `request.user`, `request.auth`, `401`, `503`, generic `500`, and the
  Bearer challenge without adding a production route.
- Existing issue #96 tests are retained and updated only where #97 intentionally
  replaces their temporary assertion that no global DRF authentication class
  exists.

The design is based on the repository's locked Django 6.0.8, DRF 3.17.1,
psycopg 3.3.4, and pytest-django 4.12.0 behavior. Relevant upstream contracts
are DRF's [authentication guide](https://www.django-rest-framework.org/api-guide/authentication/),
Django's [transaction guidance](https://docs.djangoproject.com/en/6.0/topics/db/transactions/),
psycopg's [structured error API](https://www.psycopg.org/psycopg3/docs/api/errors.html),
and pytest-django's [database access guidance](https://pytest-django.readthedocs.io/en/latest/database.html).

## Documentation, rollout, and rollback

The API README will describe the completed verified-Clerk-to-TailTag request
identity flow, disabled behavior, canonical `request.user`, provider-neutral
`request.auth`, and issue boundaries.

This change adds no migration, data backfill, endpoint, production operation, or
deployment authorization. Authentication remains disabled where the existing
configuration explicitly disables it. Enabling it continues to require the
complete issue #96 trust configuration.

Rollback removes the global DRF class and the two new composition modules. It
does not require a database rollback because the existing identity schema is
unchanged. Any deployed TailTag users provisioned while the feature is enabled
remain valid application identities and are not deleted by rollback.
