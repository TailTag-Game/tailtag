# V0 per-Convention fursuit activation

**Issue:** [#117 — Implement per-Convention fursuit activation](https://github.com/TailTag-Game/tailtag/issues/117)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved for implementation; Acceptance Contract and Test Surface
Contract frozen on 2026-08-31

## Goal

Allow an authenticated fursuit owner to durably select which owned fursuits
participate in each Convention without conflating that selection with current
operational eligibility or temporary catchability. The resulting relationship
is owner-readable, retry-safe, operator-inspectable, and suitable as the single
participation authority consumed by the later catch-session domain.

## Domain distinctions

- **Enrollment** means that a player participates in a Convention.
- **Fursuit activation** means that the owner selected a specific fursuit to
  participate in that Convention.
- **Operational eligibility** means that all current upstream requirements for
  an activation are satisfied.
- **Operational participation** means that the durable activation is active and
  currently operationally eligible.
- **Catch session** means that an operationally participating fursuit is
  temporarily out and catchable.

These are separate states. Enrollment never activates every owned fursuit,
activation never starts a catch session, and loss of current eligibility never
rewrites the owner's durable activation selection.

## Existing contracts

- Clerk remains the external authentication authority.
- `accounts.User.id` remains the canonical TailTag application identity.
- Fursuit ownership is authoritative through `fursuits.Fursuit.owner`.
- `profiles.eligibility.is_participation_eligible` remains the canonical
  profile-level predicate and is reused rather than redefined.
- An existing `conventions.ConventionEnrollment` proves enrollment. Its
  `is_active` field represents the selected active gameplay Convention and is
  not an activation prerequisite.
- `conventions.Convention.is_playable` remains the Convention lifecycle
  authority; only `ACTIVE` Conventions are playable.
- `fursuits.Fursuit.is_enabled` remains the operator-controlled global fursuit
  enablement state.
- `/api/` remains the unversioned V0 product namespace.

## Scope

Issue #117 owns:

- the durable `FursuitActivation` model and migration in the `conventions`
  application;
- owner-scoped list and desired-state mutation APIs nested under Convention;
- the canonical current-eligibility and operational-participation domain query;
- ownership concealment and asymmetric activation/deactivation authorization;
- atomic, idempotent state transitions with explicit transition timestamps;
- PostgreSQL row locking, uniqueness, and race handling for this domain;
- restricted Django admin inspection and active-to-inactive moderation;
- OpenAPI and focused automated coverage, including real PostgreSQL races.

Issue #117 does not own:

- catch sessions, session termination, or speculative session hooks;
- QR identities, credentials, or credential resolution;
- catch validation, creation, persistence, history, or progression;
- automatic activation of all owned fursuits;
- automatic activation-row mutation after upstream lifecycle changes;
- enrollment or active-Convention selection behavior;
- fursuit ownership transfer or broader fursuit/profile/Convention moderation;
- operator HTTP APIs, bulk activation, moderation reasons, audit-event models, or
  a separate activation-history system;
- frontend or mobile implementation;
- speculative rewrites of adjacent mutation paths without a demonstrated
  PostgreSQL concurrency defect.

## Persistence contract

Create `conventions.FursuitActivation` with:

| Field | Persistence contract |
| --- | --- |
| `id` | Repository-default `BigAutoField`; stable internal primary key |
| `fursuit` | Required `ForeignKey("fursuits.Fursuit", on_delete=PROTECT)` |
| `convention` | Required `ForeignKey("conventions.Convention", on_delete=PROTECT)` |
| `is_active` | Required `BooleanField`; durable owner-selected participation state |
| `activated_at` | Required server-controlled timestamp of the latest inactive-to-active transition |
| `deactivated_at` | Nullable server-controlled timestamp of the latest active-to-inactive transition |
| `created_at` | Required server-controlled creation timestamp |
| `updated_at` | Required server-controlled timestamp of the latest actual durable mutation |

Add a named database uniqueness constraint on `(fursuit, convention)`. Owner
identity is derived from `fursuit.owner`; it is not copied onto the activation.
Enrollment is an authorization prerequisite, not part of activation identity,
and is not referenced by foreign key. Inactive rows are durable and there is no
normal deletion path.

Persisted transition invariants are:

- active rows have `deactivated_at = null`;
- inactive rows preserve the latest `activated_at` and have the timestamp of
  the latest real deactivation in `deactivated_at`;
- no-op desired-state writes preserve all persisted timestamps, including
  `updated_at`.

## Current eligibility and operational participation

For an owned activation, compute `is_eligible` from current authoritative
state as:

```text
canonical profile participation eligibility
AND ConventionEnrollment exists for owner + Convention
AND Convention is playable/ACTIVE
AND fursuit is globally enabled
```

Stored `is_active` is deliberately not part of `is_eligible`. Therefore an
inactive relationship can be eligible for activation, and an active
relationship can be ineligible because upstream state changed.

Operational participation is:

```text
activation.is_active AND activation.is_eligible
```

Disabling a fursuit or profile, removing enrollment, or pausing, completing, or
cancelling a Convention changes computed current eligibility but never rewrites
the activation row.

Expose one canonical package-internal service/query for later domains to
resolve whether an owned fursuit is operationally participating in a
Convention. It evaluates stored activation, ownership, profile eligibility,
enrollment existence, Convention playability, and fursuit enablement. The
callable lives in `conventions.services`, accepts the application user plus
Convention ID and fursuit ID, and returns the matching `FursuitActivation` only
when it is owned, active, and currently eligible; otherwise it returns `None`
without revealing whether a cross-owner or ineligible relationship exists. It
has no write side effects. The exact internal function name is
implementation-level. Issue #118 consumes this contract and owns its own
transactional session validation and termination.

## HTTP interface

All routes explicitly require TailTag authentication:

```text
GET /api/conventions/{convention_id}/fursuit-activations/
PUT /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/
```

Unsupported methods return HTTP `405`.

### Canonical representation

Every successful list item and mutation response contains exactly:

```json
{
  "fursuit_id": 17,
  "convention_id": 4,
  "is_active": true,
  "is_eligible": true,
  "activated_at": "2026-08-31T12:34:56Z",
  "deactivated_at": null
}
```

`is_eligible` is computed from current upstream state and is never persisted.
The representation does not embed fursuit or Convention objects and does not
expose activation ID, owner identity, Clerk identity, `created_at`, or
`updated_at`.

### GET list

`GET /api/conventions/{convention_id}/fursuit-activations/` returns HTTP `200`
with an unpaginated JSON array containing only the authenticated owner's
existing durable relationships for that Convention, ordered by `fursuit_id`.
It includes active rows, inactive rows, rows for subsequently disabled
fursuits, and rows made ineligible by current profile, enrollment, or
Convention state.

The read requires authentication and an existing Convention but does not
require current profile eligibility, enrollment, or Convention playability.
An unknown Convention returns HTTP `404`. The endpoint never synthesizes rows
for owned fursuits that have no relationship in that Convention.

### PUT desired state

`PUT /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/`
accepts only `application/json` with exactly one field:

```json
{
  "is_active": true
}
```

The field is required, non-null, and boolean. Empty objects, unknown or
read-only fields, extra fields mixed with `is_active`, non-boolean values, and
unsupported media types fail with sanitized HTTP `400` responses. Successful
creation or mutation, including a no-op retry, returns HTTP `200` with the
canonical representation.

#### Set active

Setting `is_active=true` creates the relationship if absent or reactivates an
existing inactive relationship. It requires all of:

```text
authenticated
AND caller owns the fursuit
AND canonical profile participation eligibility
AND enrollment exists for caller + Convention
AND Convention is playable/ACTIVE
AND fursuit is globally enabled
```

`ConventionEnrollment.is_active` is not required. A player may configure
fursuits independently for multiple enrolled playable Conventions.

Initial activation sets `activated_at=now` and `deactivated_at=null`.
Reactivation sets a new `activated_at=now` and clears `deactivated_at`.
Setting an already-active relationship active is a no-op that preserves
`activated_at`, `deactivated_at`, and `updated_at`.

#### Set inactive

Setting `is_active=false` requires an existing relationship for the caller's
owned fursuit and Convention. A missing relationship returns HTTP `404`; the
request does not create an inactive row.

Deactivation does not require profile participation eligibility, enrollment,
Convention playability, fursuit enablement, or active-Convention selection.
An actual active-to-inactive transition preserves `activated_at`, sets
`deactivated_at=now`, and updates `updated_at`. Setting an already-inactive
relationship inactive is a no-op that preserves all three timestamps.

## Authorization and error precedence

The detail mutation path follows this externally observable ordering where
practical:

```text
authentication
-> resolve fursuit by id + owner
-> resolve Convention
-> resolve any existing activation
-> parse and validate the closed desired-state body
-> determine the requested transition
-> for activation, enforce current eligibility
-> atomically set desired state
```

Authentication failure returns HTTP `401`. A missing or cross-owner fursuit
returns the same HTTP `404` before request-body parsing or eligibility checks.
An unknown Convention returns HTTP `404` after the owned fursuit is resolved.
A missing relationship on deactivation also returns HTTP `404`.

For a resolved owned fursuit and Convention, activation failures use existing
participation conventions rather than ownership concealment:

- profile participation ineligibility returns HTTP `403`;
- missing enrollment, non-playable Convention, or disabled fursuit returns a
  sanitized field-level HTTP `400` validation response;
- malformed desired-state input returns HTTP `400` only after the ownership and
  resource checks above.

Responses do not reveal whether another user owns a supplied fursuit ID and do
not expose provider identities or internal relationship IDs.

## Transaction and concurrency contract

Activation operations use `transaction.atomic()` and acquire real PostgreSQL
row locks in this order:

```text
1. PlayerProfile
2. Convention
3. ConventionEnrollment
4. Fursuit
5. existing FursuitActivation, if present
```

Activation rereads authoritative state under those locks before committing.
The named `(fursuit, convention)` uniqueness constraint is the final defense
against duplicate creation. Concurrent first activations must converge on one
active row and successful HTTP `200` responses without leaking an
`IntegrityError` or returning HTTP `500`.

Deactivation does not require or create missing upstream eligibility rows. It
locks only the owned fursuit and existing activation needed for that transition,
preserving their relative order from the activation lock chain. Concurrent
desired-state writes for the same pair must serialize and produce one valid
state with timestamps corresponding only to real transitions. No-op retries
never create new transitions.

PostgreSQL update locking defines races with upstream moderation:

```text
operator mutation commits first
-> activation waits, locks, rereads, and rejects stale eligibility

activation commits first
-> operator mutation waits and then commits
-> stored activation may remain active
-> computed operational eligibility becomes false
```

The second outcome is valid. Do not redesign adjacent mutation paths unless a
real PostgreSQL-backed test demonstrates an unserialized race or invariant
violation.

## Django admin

Register `FursuitActivation` for restricted per-object support:

- operators can inspect, search, and filter rows;
- all identity, ownership, relationship, and timestamp fields are read-only;
- the only allowed mutation is `is_active: true -> false`;
- operators cannot create, delete, activate, reactivate, transfer, or
  bulk-activate participation;
- an admin no-op preserves transition and update timestamps;
- no new operator HTTP API, moderation reason, audit-event model, or activation
  history is introduced.

## OpenAPI

The generated schema documents both routes, the exact closed request and
response representations, authentication, success and error statuses,
nullability of `deactivated_at`, list ordering semantics, idempotency, and the
distinction between stored `is_active` and computed `is_eligible`.

## Acceptance Contract

The following observable requirements are frozen for implementation and
independent test authorship.

### AC-01 — Durable identity and integrity

- Exactly one durable activation relationship may exist for a fursuit and
  Convention.
- Both foreign keys use `PROTECT`; ownership is derived from the fursuit and
  enrollment is not persisted on the activation.
- Inactive relationships remain durable and normal APIs/admin expose no delete
  path.

### AC-02 — Owner-scoped reads

- Authenticated owners can list only their existing relationships for the
  requested Convention in ascending `fursuit_id` order.
- Reads include inactive and currently ineligible relationships without
  requiring current write eligibility.
- Unknown Conventions return `404`; no absent relationship is synthesized.

### AC-03 — Exact API projection

- Owner responses expose exactly `fursuit_id`, `convention_id`, `is_active`,
  computed `is_eligible`, `activated_at`, and `deactivated_at`.
- They expose no owner/provider/activation identity, embedded domain objects,
  `created_at`, or `updated_at`.

### AC-04 — Closed desired-state request

- PUT accepts only JSON containing exactly one non-null boolean `is_active`.
- Invalid shape or media type fails safely without mutating state.
- Every successful create, transition, or retry returns `200` and the canonical
  projection.

### AC-05 — Activation authorization

- Only the owner can activate a fursuit.
- Activation requires current canonical profile eligibility, enrollment in the
  target Convention, Convention playability, and global fursuit enablement.
- Active-Convention selection is not required.
- Missing/cross-owner fursuits are concealed as `404`; profile ineligibility is
  `403`; resolved participation-state failures are sanitized `400` responses.

### AC-06 — Deactivation escape path

- An owner can deactivate an existing own active relationship after any
  upstream eligibility condition is lost.
- Deactivation never creates an absent relationship, and an absent relationship
  returns `404`.

### AC-07 — Transition timestamps and idempotency

- Initial activation, deactivation, and reactivation obey the frozen timestamp
  rules.
- Repeating the current desired state is a database no-op preserving
  `activated_at`, `deactivated_at`, and `updated_at`.
- Retried and concurrent requests do not create duplicate rows or artificial
  transitions.

### AC-08 — Eligibility without lifecycle rewriting

- `is_eligible` is computed from current profile, enrollment, Convention, and
  fursuit state and excludes stored `is_active`.
- Operational participation is `is_active AND is_eligible`.
- Upstream lifecycle changes affect the computed predicate without rewriting
  durable activation state.

### AC-09 — Canonical downstream contract

- One package-internal domain query is the authority for current operational
  participation and evaluates every frozen input.
- The query is importable from `conventions.services`, accepts application user,
  Convention ID, and fursuit ID, returns the owned operationally participating
  activation or `None`, and has no write side effects.
- No catch session, session hook, credential, or catch behavior is introduced.

### AC-10 — Restricted operator support

- Django admin supports searchable/filterable inspection and only
  active-to-inactive per-object mutation.
- Admin add, delete, activation/reactivation, ownership mutation, and bulk
  activation are unavailable.

### AC-11 — PostgreSQL concurrency

Real PostgreSQL-backed tests prove safe outcomes for:

- two simultaneous first activations;
- activation racing with fursuit disablement;
- activation racing with Convention pause or cancellation;
- activation racing with profile disablement;
- activation racing with enrollment removal, which the current admin supports;
- activation/deactivation racing with another desired-state request for the
  same fursuit and Convention.

No transaction may successfully enter operational participation based on stale
eligibility. Valid activation-first/upstream-mutation-second outcomes may retain
`is_active=true` while computing `is_eligible=false`.

### AC-12 — OpenAPI and regression safety

- OpenAPI exactly describes the owner API and its state distinction.
- Automated tests cover authentication, ownership concealment, every
  eligibility boundary, list behavior, idempotency, constraints, admin
  restrictions, and error precedence.
- Existing profile, Convention, enrollment, and fursuit behavior remains
  unchanged except for concrete adjacent changes proven necessary by failing
  PostgreSQL race evidence.

## Test Surface Contract

The intentional test surfaces are:

- the two authenticated HTTP endpoints for owner-observable behavior and
  OpenAPI;
- the `FursuitActivation` model and named database constraint for persistence
  invariants;
- the package-internal activation service/query for focused state-transition
  and downstream-contract tests;
- the registered Django admin for operator permissions and timestamp behavior;
- real PostgreSQL transactions using separate connections/threads for race
  behavior.

Tests may use the repository's existing forced-authentication, profile,
Convention, enrollment, and fursuit fixtures/helpers. Deterministic clock
control may be used to prove timestamp changes and no-ops. PostgreSQL locking
and uniqueness behavior must not be mocked, and SQLite is not acceptable
evidence for the required race cases. No production seam, callback, or public
API may be added solely for test convenience.

## Scope Guard

**Outcome:** Deliver the frozen durable per-Convention fursuit activation and
current-eligibility contract.

**Non-goals:** All exclusions in this specification, especially catch sessions,
credentials, lifecycle cascades, new operator APIs, history/audit systems, and
speculative adjacent-domain rewrites.

**Expected change surface:** `conventions` model/migration, service, serializer,
view, URL, and admin modules; focused backend tests; generated OpenAPI behavior;
and implementation-coupled documentation only where required. Adjacent profile,
fursuit, or Convention mutation code is outside the expected surface unless a
required PostgreSQL test proves a concrete invariant violation.

**Proof:** Acceptance-first tests, real PostgreSQL race evidence, migration and
constraint verification, OpenAPI assertions, deterministic repository checks
including Semgrep, plausible-mutant analysis of authorization/state-transition
logic, independent specification and code-quality review, and final parent
verification.

## Rollout and rollback

The migration is additive and begins with no activation rows. Before durable
activation data exists, normal migration reversal is acceptable. After data is
used, rollback preserves the activation table and rows and uses compatible code
or a forward schema repair; it does not delete durable player selections.

No production deployment or data backfill is part of #117.

## Resolved decisions

The contracts in this document are approved. Implementation-level names and
private decomposition may vary without changing observable behavior, the
persistence contract, lock order, or test surfaces. Evidence requiring a public
contract, persistence, security, or adjacent-domain change triggers ADW
replanning rather than silent scope expansion.
