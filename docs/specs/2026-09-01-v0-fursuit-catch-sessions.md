# V0 fursuit catch sessions

**Issue:** [#118 — Implement V0 fursuit catch sessions](https://github.com/TailTag-Game/tailtag/issues/118)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved lifecycle, Acceptance Contract, and Test Surface Contract;
frozen on 2026-09-01 before production implementation

## Goal and domain distinctions

Allow an authenticated fursuit owner to declare one bounded period during which
an operationally participating fursuit is out and catchable at a Convention.
Every real start creates durable history. Owner stop, operator stop, eligibility
loss, or expiration permanently ends that session; restored eligibility never
resurrects it.

The V0 state layers remain distinct:

```text
FursuitActivation
    = durable owner intent to participate in this Convention

Operational participation
    = active FursuitActivation + current upstream eligibility

FursuitCatchSession
    = one bounded historical declaration that the fursuit is presently out

Effective catchability
    = active, unexpired catch session + current operational participation
```

Activation may survive temporary eligibility loss. A catch session does not.
Issue #118 terminates temporary session state without rewriting the owner's
durable activation selection.

## Existing contracts and dependencies

- Clerk remains the authentication authority and `accounts.User.id` remains the
  canonical TailTag application identity.
- Fursuit ownership remains authoritative through `fursuits.Fursuit.owner`.
- `profiles.eligibility.is_participation_eligible` remains the canonical
  profile-level predicate: authenticated, onboarding complete, and enabled.
- `conventions.ConventionEnrollment` existence, not its `is_active` active-
  Convention-selection field, proves Convention enrollment.
- `Convention.is_playable` remains the lifecycle authority; only `ACTIVE` is
  playable.
- `Fursuit.is_enabled` remains the operator-controlled global enablement state.
- `FursuitActivation.is_active` remains durable owner intent. The canonical
  operational-participation query remains
  `conventions.services.get_operational_fursuit_activation`.
- `/api/` remains the unversioned V0 product namespace.
- Issue #117 is complete and is the direct prerequisite. Issue #119 consumes
  this issue's catchability contract for Convention-scoped QR resolution.

This specification deliberately refines how later temporary gameplay state
responds to the earlier domains:

- #113 profile disablement still preserves the profile, enrollments, fursuits,
  activations, and catch-session history. It now ends an active temporary catch
  session; re-enablement does not reconstruct or resume that session.
- #115 fursuit disablement still preserves the durable fursuit and owner editing
  behavior. It ends active catch sessions for that fursuit.
- #116 Convention lifecycle changes and enrollment removal do not rewrite
  surviving enrollment or activation intent. They end affected active sessions.
  Changing or clearing `ConventionEnrollment.is_active` alone does not affect
  operational participation and does not end sessions.
- #117's rule that upstream eligibility loss does not rewrite
  `FursuitActivation.is_active` remains authoritative. Issue #118 appends the
  required temporary-session termination after the activation lock.

## Scope and Scope Guard

### Included

- append-only fursuit catch-session persistence under the `conventions` domain;
- one unended session per activation, enforced by PostgreSQL;
- a 12-hour server-controlled lifetime and cleanup-independent expiration;
- an owner-scoped desired-state API with idempotent start and stop behavior;
- synchronous session termination from every repository-owned eligibility-loss
  mutation path;
- restricted Django-admin inspection and per-object operator termination;
- exact OpenAPI documentation and focused automated evidence;
- real PostgreSQL race coverage for owner, operator, expiration, and upstream
  eligibility transitions.

### Excluded

- catch creation or persistence;
- XP, scoring, progression, collection, or catch history;
- QR credential generation or resolution;
- BLE, NFC, GPS, or physical-proximity proof;
- per-catch owner approval;
- advanced abuse scoring or speculative anti-cheat;
- background expiration workers, schedulers, or periodic cleanup;
- arbitrary moderation notes or a custom audit-event subsystem;
- operator HTTP APIs;
- bulk catch-session termination in Django admin;
- catch-session deletion or resurrection;
- frontend or mobile work;
- speculative refactoring of unrelated state paths.

### Review-unit Scope Guard

**Outcome:** Persist and expose bounded catch sessions whose lifecycle obeys
the frozen owner, eligibility, expiration, operator, and concurrency rules.

**Non-goals:** Every exclusion above, especially catch writes, credentials,
background cleanup, new operator APIs, and unrelated domain cleanup.

**Expected change surface:** `conventions` model and migration; a focused
catch-session service module or equivalent package-internal boundary;
`conventions` serializer, view, URL, and admin integration; the existing
profile, fursuit, enrollment, activation, and Convention service/admin mutation
seams named below; focused backend tests; generated OpenAPI behavior; and the
minimum implementation-coupled documentation. No new Django application or
dependency is authorized.

**Proof:** Acceptance-first tests mapped to the numbered contract, named
database-constraint checks, exact API/OpenAPI assertions, real PostgreSQL race
evidence, admin restrictions, deterministic repository checks including
Semgrep, plausible-mutant analysis of authorization and lifecycle transitions,
independent specification/code review, and parent authoritative verification.

## Persistence and schema contract

Create `conventions.FursuitCatchSession` as an append-only historical model:

| Field | Persistence contract |
| --- | --- |
| `id` | Repository-default `BigAutoField`; stable internal primary key |
| `activation` | Required `ForeignKey("conventions.FursuitActivation", on_delete=PROTECT, related_name="catch_sessions")` |
| `started_at` | Required server-controlled timestamp of the real start |
| `expires_at` | Required server-controlled timestamp exactly 12 hours after `started_at` |
| `ended_at` | Nullable server-controlled terminal timestamp |
| `end_reason` | Nullable enum containing exactly `owner`, `operator`, `eligibility_lost`, or `expired` |
| `created_at` | Required server-controlled creation timestamp |
| `updated_at` | Required server-controlled timestamp of the latest actual durable mutation |

Use a `TextChoices`-style V0 reason enum and named database constraints that
enforce:

```text
expires_at > started_at
ended_at IS NULL <=> end_reason IS NULL
ended_at IS NULL OR ended_at >= started_at
end_reason IS NULL OR end_reason IN (
    owner, operator, eligibility_lost, expired
)
```

`ended_at == expires_at` is valid and canonical for expiration. No additional
ordering between `ended_at` and `expires_at` is imposed.

Add a named conditional uniqueness constraint on `activation` where
`ended_at IS NULL`. An expired but lazily unfinalized row remains unended for
this database constraint and must be locked and finalized before replacement.

Normal application and admin surfaces expose no deletion path. An ended row is
never edited or reactivated. A real new start always creates a new row. A no-op
retry never changes `updated_at` or any lifecycle timestamp. Default historical
ordering is newest first by `started_at`, then `id`; the same order selects the
latest session for an inactive response.

## Lifecycle and effective catchability

At one captured server time, a session is effectively active only when:

```text
ended_at IS NULL
AND now < expires_at
AND activation is currently operationally participating
```

Effective catchability is this computed session state. It is never inferred
from `ended_at` alone. At `now == expires_at`, the session is inactive.

If an upstream mutation makes operational participation false while a session
is effectively active, that same transaction permanently ends the session:

```text
ended_at = mutation time
end_reason = eligibility_lost
```

This applies at minimum to:

- `FursuitActivation.is_active: true -> false`;
- `Fursuit.is_enabled: true -> false`;
- `PlayerProfile.is_enabled: true -> false` or another supported mutation that
  makes the canonical profile predicate false;
- removal of the owner's `ConventionEnrollment`;
- `Convention.status: ACTIVE ->` any non-playable status.

Restoring any condition does not touch prior session rows. A later catchable
period requires a new explicit start. A no-op upstream mutation does not alter
session history. Active-Convention selection changes do not affect sessions.

Every transition that locks an unended row evaluates expiration first using
the operation's one captured `now`. If `now >= expires_at`, it finalizes the row
as `expired` at `expires_at`; only a row that is still live may receive
`owner`, `operator`, or `eligibility_lost`. Expiration therefore wins over the
reason that caused stale state to be encountered, without overwriting an
earlier terminal transition.

Wave 3 catch creation must revalidate the active, unexpired session, current
operational participation, and every catch-specific requirement at write time.
Neither a session row nor a prior QR resolution is catch authorization.

## Expiration contract

Define one package/domain constant for V0:

```text
FURSUIT_CATCH_SESSION_LIFETIME = 12 hours
```

The exact internal name is implementation-level; there is one authority and no
environment override. Creation uses one server-controlled instant:

```text
started_at = now
expires_at = started_at + 12 hours
```

Expiration requires no worker. Reads and projections treat `now >= expires_at`
as inactive even while `ended_at` remains null.

Whenever catch-session state-transition code encounters an expired unended
row, it finalizes that row under lock with:

```text
ended_at = expires_at
end_reason = expired
```

Starting after expiration atomically finalizes the old row and creates one new
row. Stopping after expiration finalizes and returns the expired row. A still-
live repeated start is a complete database no-op: it does not reset
`started_at`, extend `expires_at`, update `updated_at`, or create history.
Repeated inspection computes state but creates no writes or artificial history.

## Owner HTTP API

Expose exactly one owner mutation route:

```text
PUT /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-session/
```

The endpoint explicitly requires TailTag authentication and accepts only
`application/json` with exactly one required, non-null, boolean field:

```json
{
  "is_active": true
}
```

Empty objects, additional fields, unknown/read-only fields, non-booleans,
`null`, arrays, and other shapes fail with sanitized HTTP `400`. Unsupported
media types follow #117 and become the same sanitized field-level HTTP `400`,
not DRF's default `415`. Unsupported methods return HTTP `405`. There are no
separate POST, PATCH, or DELETE start/stop routes and no GET route in V0.

Every successful transition or retry returns HTTP `200` and the canonical
representation.

### Desired `is_active=true`

- Require an existing activation for the caller's owned fursuit and Convention.
- Under the frozen locks, authoritatively require current operational
  participation: active activation, eligible profile, enrollment existence,
  playable Convention, and enabled fursuit.
- If a valid active session already exists, return it without any database
  mutation.
- If the unended session has expired, finalize it as `expired`, then create and
  return exactly one replacement.
- Otherwise create a new session with the frozen 12-hour lifetime.

### Desired `is_active=false`

- Require an existing activation for the caller's owned fursuit and Convention,
  but do not require current operational eligibility.
- If a live unended session exists, end it at `now` with `end_reason=owner`.
- If an unended session has expired, finalize it at `expires_at` with
  `end_reason=expired`; do not overwrite it with `owner`.
- If no unended session exists, perform no database write and return the latest
  historical session.
- If no session has ever existed, perform no database write and return the
  canonical empty inactive state.

The absence of a current session is successful desired-state convergence, not
HTTP `404`.

## Canonical owner representation

Every successful response is a closed object containing exactly:

```json
{
  "fursuit_id": 17,
  "convention_id": 4,
  "is_active": true,
  "started_at": "2026-09-01T17:00:00Z",
  "expires_at": "2026-09-02T05:00:00Z",
  "ended_at": null,
  "end_reason": null
}
```

`fursuit_id` and `convention_id` are derived through the activation.
`is_active` is computed from the effective-catchability expression at one
captured server time. It is false for ended, expired, or currently ineligible
sessions. An expired lazily unfinalized row therefore projects false while its
`ended_at` and `end_reason` may still be null.

When no historical session exists, return exactly:

```json
{
  "fursuit_id": 17,
  "convention_id": 4,
  "is_active": false,
  "started_at": null,
  "expires_at": null,
  "ended_at": null,
  "end_reason": null
}
```

All four timing/reason fields are nullable in HTTP even though persisted
sessions always have `started_at` and `expires_at`. The response exposes no
session ID, activation ID, owner/application-user identity, Clerk identity,
embedded domain object, `created_at`, or `updated_at`.

## Authorization and error precedence

Follow this externally observable order where practical:

```text
authentication
-> resolve fursuit by ID + owner
-> resolve Convention
-> resolve existing FursuitActivation
-> parse and validate the closed desired-state body
-> determine the requested transition
-> for start, enforce current operational participation
-> perform the atomic desired-state transition
```

Status semantics are:

- missing or invalid authentication: HTTP `401`;
- missing or cross-owner fursuit: indistinguishable HTTP `404`;
- unknown Convention: HTTP `404` after resolving the owned fursuit;
- absent activation relationship: HTTP `404`;
- malformed body or unsupported media type: sanitized field-level HTTP `400`;
- profile participation ineligibility on start: HTTP `403`;
- a resolved activation that cannot operationally participate on start because
  of enrollment, Convention, activation, or fursuit state: sanitized
  `is_active` field HTTP `400`;
- stop on an owned existing activation after any eligibility loss: HTTP `200`.

Resource and ownership resolution precede body parsing. Responses disclose no
cross-owner existence, internal relationship identity, provider identity, or
detailed moderation state beyond existing APIs.

## Transactions and global lock order

All lifecycle mutations use `transaction.atomic()` and preserve this global
relative PostgreSQL row-lock order whenever they acquire multiple row types:

```text
1. PlayerProfile
2. Convention
3. ConventionEnrollment
4. Fursuit
5. FursuitActivation
6. unended FursuitCatchSession, if present
```

An operation may skip unneeded row types but may never acquire an earlier type
after a later type. When locking multiple rows of one type, lock in ascending
primary-key order. Multi-scope operations must determine the relevant IDs
before locking without treating that preliminary read as authorization, then
lock and re-read authoritative state.

- Start locks the full eligibility chain, activation, then an existing unended
  session. It revalidates every condition under those locks.
- Owner stop may lock only fursuit, activation, then unended session.
- Expiry finalization and operator termination may lock activation, then
  session.
- Activation deactivation locks fursuit, activation, then session.
- Profile disablement locks profile, then affected activations and sessions.
- Fursuit disablement locks fursuit, then affected activations and sessions.
- Enrollment removal locks profile, Convention, enrollment, then affected
  activations and sessions.
- Convention transition to non-playable locks Convention, then affected
  activations and sessions.

The conditional uniqueness constraint is the final defense, but normal same-
activation starts serialize on the activation row. Recognize and recover only
the named unended-session uniqueness conflict if a creation race still reaches
the constraint; unrelated integrity failures remain server errors.

Concurrent terminal operations use first-lock-winner serial semantics, subject
to expiration precedence at the winner's captured time. The winner writes one
stable `ended_at` and `end_reason`; the later operation sees no unended session
and does not overwrite history. A race may have either valid serial winner, but
no deadlock, `IntegrityError`, or HTTP `500` may escape a normal transition
race.

## Concrete upstream mutation integration seams

Catch-session termination is centralized within the `conventions` catch-
session domain. Use narrowly typed package-internal operations for one
activation and the supported profile/user, fursuit, enrollment, and Convention
scopes. Do not introduce a generic arbitrary-model dispatcher, Django signal,
model `save()` hook, database trigger, or background reconciler.

The current repository-owned mutation inventory and required #118 integration
are:

| Eligibility mutation | Current concrete path | Required #118 integration |
| --- | --- | --- |
| Profile enabled to disabled | `profiles.admin.PlayerProfileAdmin` uses Django's default `save_model`; no profile enablement service or explicit row lock exists | Override the admin mutation to call a profile-owned transactional enablement service. On an actual disable, lock the profile first and invoke the typed user/profile session-termination seam before commit. Finalize expired rows as `expired`; terminate only still-live rows as `eligibility_lost`. Re-enable creates no session. |
| Fursuit enabled to disabled | `fursuits.admin.FursuitAdmin.save_model` performs a direct queryset `update` | Route through a fursuit-owned transactional enablement service. On actual disable, lock the fursuit, then affected activations/sessions. Finalize expired rows as `expired`; terminate only still-live rows as `eligibility_lost`. Re-enable creates no session. |
| Enrollment removal | `conventions.admin.ConventionEnrollmentAdmin` currently uses default add/edit/delete behavior and the default bulk delete action; no owner HTTP removal exists | Route per-object and queryset admin deletion through one transactional enrollment-removal service. Lock rows in the frozen order, finalize expired rows as `expired`, and terminate still-live rows as `eligibility_lost` before deletion. Disable direct bulk `delete_selected` unless its override uses the same service and deterministic ordering. Treat reassignment of `user` or `convention` as loss of the old enrollment; the minimum V0 change is to make those identity fields immutable after creation rather than invent a reassignment workflow. |
| Owner activation deactivation | `conventions.services.set_fursuit_activation_state` calls `_deactivate_fursuit`, locking fursuit then activation | Extend this canonical service transaction by locking the unended session after the activation. Finalize it as `expired` if its lifetime has elapsed; otherwise terminate it with `eligibility_lost`. An already-inactive no-op changes no session history. |
| Operator activation deactivation | `conventions.admin.FursuitActivationAdmin.save_model` performs a direct conditional queryset `update` | Replace the direct update with an operator-authorized activation service using the same fursuit, activation, then session order and the same expiration-first, otherwise-`eligibility_lost` rule. |
| Convention active to non-playable | `conventions.admin.ConventionAdmin` uses Django's default `save_model`; no Convention status-transition service exists | Route status changes through a Convention-owned transactional service. On an actual `ACTIVE` to non-playable transition, lock the Convention, then affected activations/sessions in deterministic order; finalize expired rows as `expired` and terminate still-live rows as `eligibility_lost`. Other field/status changes do not create session history. |

Clearing or selecting `ConventionEnrollment.is_active` through
`clear_active_convention`, `set_active_convention`, or `enroll_in_convention`
does not remove enrollment and must not terminate sessions.

### Explicit mutation-boundary hazard

The models currently permit direct ORM `save()`, `update()`, and `delete()`;
there are no model hooks, signals, or database triggers that can synchronously
terminate sessions for arbitrary shell scripts, ad hoc data migrations, or new
callers that bypass domain services. The #118 guarantee therefore covers all
repository-owned product and admin paths after they are rerouted above. Direct
ORM eligibility mutations remain an unsupported bypass and must be called out
in future code review and operational work. The implementation must not claim
model-level universal enforcement or add signals to disguise this boundary.

## Activation deactivation integration

Every real `FursuitActivation.is_active: true -> false` transition handles its
unended catch session in the same transaction. An expired row is finalized at
`expires_at` with `end_reason=expired`; a still-live row ends at mutation time
with `end_reason=eligibility_lost`, regardless of whether the owner API or
operator admin initiated deactivation. `owner` is reserved for explicit catch-
session stop. An already-inactive activation is a complete session-history
no-op.

## Django admin

Register `FursuitCatchSession` for restricted support:

- inspect, search, filter, and order complete history;
- identify effectively active versus ended/expired sessions without exposing a
  mutation that edits raw lifecycle fields;
- terminate one effectively active session through a per-object control that
  calls the canonical termination service;
- operator termination uses one `now`, sets `ended_at=now` and
  `end_reason=operator`, and preserves all other history;
- an expired unended row is finalized as `expired`, never relabeled operator;
- all IDs/relationships, timestamps, and reason fields are read-only;
- add, delete, restart/reactivation, transfer, timestamp/reason editing, and
  bulk actions are prohibited.

No operator HTTP API is added. Normal Django admin logging remains sufficient;
no custom moderation-note or audit-event model is introduced.

## OpenAPI

Generated OpenAPI must document:

- the exact PUT route and no additional catch-session route;
- TailTag authentication;
- `application/json` only and the exact closed request;
- the exact closed seven-field response;
- nullable `started_at`, `expires_at`, `ended_at`, and `end_reason`;
- `end_reason` enum values `owner`, `operator`, `eligibility_lost`, and
  `expired` when non-null;
- HTTP `200`, `400`, `401`, `403`, `404`, and `405` semantics;
- desired-state idempotency, fixed expiration, and computed `is_active`;
- that session state is not catch authorization.

## Acceptance Contract

### AC-01 — Durable append-only history

- Every real start creates one new `FursuitCatchSession` associated with one
  activation through `PROTECT`.
- Ended sessions remain durable, immutable, and undeletable through normal
  product/admin paths.
- Responses expose no internal session or activation identity.

### AC-02 — Database integrity

- Named constraints enforce expiration after start, paired end fields, terminal
  time not before start, exact reason values, and at most one unended row per
  activation.
- Invalid direct persistence fails at the database boundary.

### AC-03 — Effective catchability

- `is_active` is true only for an unended, unexpired session whose activation is
  currently operationally participating.
- `now == expires_at` is inactive.
- Catchability never depends on cleanup having run.

### AC-04 — Fixed expiration

- Every new session expires exactly 12 hours after its captured start time.
- The policy is a single domain constant with no environment override.
- Lazy finalization uses `ended_at=expires_at` and `end_reason=expired`.

### AC-05 — Exact desired-state API

- The only owner mutation is the frozen PUT route and exact JSON boolean body.
- Successful transitions and retries return HTTP `200` with exactly the seven
  frozen response fields.
- Unsupported methods and inputs obey the frozen status and sanitization rules.

### AC-06 — Idempotent start

- A live repeated start returns the unchanged row without extending its life,
  updating timestamps, or creating history.
- A start after expiration atomically finalizes the old row and creates exactly
  one replacement after locked operational-participation validation.

### AC-07 — Idempotent stop and empty state

- A live owner stop writes one terminal transition with reason `owner`.
- A repeated stop writes nothing and returns the latest session.
- A stop before any session exists returns the exact empty inactive projection,
  without synthesizing persistence.
- Stop remains available after eligibility loss.

### AC-08 — Authorization and concealment

- Start and stop require authentication, ownership, Convention, and an existing
  activation, resolved in the frozen order.
- Start alone requires current operational participation.
- Cross-owner fursuits are indistinguishable from missing fursuits and responses
  expose no private or provider identity.

### AC-09 — Eligibility loss is terminal

- Every repository-owned supported eligibility-losing mutation finalizes
  affected expired unended rows as `expired` and permanently ends affected live
  rows with `eligibility_lost` in the same transaction.
- Re-enabling, re-enrolling, reactivating, or returning a Convention to ACTIVE
  never resurrects an ended session.
- Surviving durable enrollment, fursuit, profile, and activation intent is not
  rewritten merely to end a catch session.

### AC-10 — Activation deactivation semantics

- Owner and operator activation deactivation both use `eligibility_lost`, not
  `owner` or `operator`, for a still-live session; an expired unended row retains
  expiration precedence.
- An already-inactive activation is a session-history no-op.

### AC-11 — Restricted operator support

- Django admin permits inspection and one per-object active-to-ended operation
  with reason `operator`.
- It prohibits add, delete, reactivation, transfer, raw history editing, and
  bulk actions.

### AC-12 — Stable terminal transitions

- Owner, operator, eligibility, and expiration races produce one stable terminal
  reason and timestamp selected by valid lock-serialized order.
- Later operations never rewrite the winning terminal state.

### AC-13 — Global locking and concurrency

- All repository-owned lifecycle paths preserve the frozen relative lock order
  and ascending primary-key order within a row type.
- Normal races yield a serializable valid state with at most one unended row and
  no leaked deadlock, `IntegrityError`, or HTTP `500`.
- No start commits from eligibility state made stale by a concurrent supported
  mutation.

### AC-14 — Concrete upstream integration

- Each current mutation path in the inventory table is rerouted through a
  transactionally compatible domain seam before completion.
- Tests prove the admin/service path, not only direct test-only ORM updates.
- Direct ad hoc ORM writes are documented as an unsupported bypass rather than
  silently presented as covered.

### AC-15 — OpenAPI accuracy

- Generated OpenAPI exactly describes the route, closed schemas, nullability,
  enum, authentication, statuses, idempotency, expiration, and authorization
  boundary.

### AC-16 — Wave 3 defense in depth

- The package-internal catchability query evaluates session time/state and the
  canonical current operational-participation contract without write side
  effects.
- Future catch creation must revalidate all session, participation, and catch-
  specific requirements and cannot treat session or QR resolution as authority.

### AC-17 — Scope discipline and regression safety

- No excluded catch, credential, scoring, hardware, approval, worker, audit,
  operator-HTTP, bulk-session, deletion, resurrection, or frontend behavior is
  introduced.
- Existing #113/#115/#116/#117 behavior remains unchanged except for the named
  session-aware mutation integrations required by this contract.

## Test Surface Contract

Tests observe behavior through these approved seams:

- the exact DRF owner route and generated OpenAPI document;
- `FursuitCatchSession` model metadata, migration constraints, and PostgreSQL
  persistence behavior;
- package-internal catch-session state-transition/catchability services;
- the existing profile, fursuit, enrollment, activation, and Convention
  service/admin mutation entry points named in the inventory;
- registered Django admin permissions, forms, and per-object operation;
- real PostgreSQL transactions on separate connections/threads for races.

Tests may use existing forced authentication and domain fixture helpers, direct
ORM setup for preconditions and intentionally invalid constraint probes, Django
admin request/form helpers, and deterministic patching of the repository's
clock call. No production clock-injection API, public testing endpoint, model
hook, signal, new dependency, or test-only production seam is approved.

Every test must map to an Acceptance Contract item, a frozen invariant, a
listed race, or a selected assurance modifier. Extend the existing backend test
surface before creating new infrastructure. Tests assert observable state and
responses rather than private helper names.

### Required schema and integrity evidence

- activation `PROTECT` behavior and append-only history;
- named one-unended-session uniqueness;
- expiration/start, end-field consistency, terminal time, and reason constraints;
- exact 12-hour creation;
- ended-row immutability through product/admin surfaces.

### Required owner API evidence

- exact route and PUT-only method contract;
- exact closed request and seven-field response;
- first start and owner stop;
- repeated start and stop;
- stop before any session has existed;
- expired-session restart;
- no timestamp/update/history mutation on no-op retries;
- unsupported methods and media types;
- authentication and ownership concealment;
- missing Convention/activation and every start eligibility failure;
- stop escape behavior after eligibility loss.

### Required lifecycle evidence

- profile disablement terminates active sessions;
- fursuit disablement terminates active sessions;
- enrollment removal terminates active sessions;
- owner and admin activation deactivation terminate active sessions;
- Convention transition to non-playable terminates active sessions;
- every eligibility-loss seam finalizes an expired unended row as `expired`
  rather than mislabeling it `eligibility_lost`;
- active-Convention selection changes do not terminate sessions;
- restoration of each eligibility condition does not resurrect history;
- explicit start after restoration creates one new row.

### Required expiration evidence

- `now == expires_at` is inactive;
- expired unfinalized rows are never catchable;
- lazy finalization uses the exact expiration instant and reason;
- restart finalizes the old row and creates exactly one replacement;
- repeated reads/projections create no artificial history.

### Required admin evidence

- searchable/filterable history inspection and active-state visibility;
- per-object operator termination;
- expired rows cannot be relabeled operator;
- no add, delete, reactivation, transfer, history editing, or bulk action.

### Required OpenAPI evidence

- exact path and no extra catch-session paths;
- exact closed request/response schemas and required fields;
- timing/reason nullability and exact reason enum;
- authentication and status documentation;
- desired-state, idempotency, expiration, computed state, and non-authorization
  descriptions.

### Plausible-mutant analysis

Before implementation approval, independently confirm that the tests reject at
least these plausible defects: extending expiry on retry; treating
`now == expires_at` as active; creating an inactive row on first stop; returning
404 for no-session stop; omitting one upstream eligibility check; ending an
expired row at observation time; overwriting a winning terminal reason;
deactivation using `owner`; restoring an ended row; leaking cross-owner
existence; and bypassing session termination in one current admin path. Do not
introduce mutation tooling solely for this issue.

## PostgreSQL concurrency matrix

Use real PostgreSQL connections and controlled barriers/lock observation. Each
test accepts either valid serial winner unless the contract states otherwise.

1. Two simultaneous first starts converge on one active historical row.
2. Two simultaneous stops produce one owner terminal transition.
3. Start racing stop produces one valid serial current/history state.
4. Restart racing lazy expiration finalization finalizes once and creates at
   most one replacement.
5. Owner stop racing operator termination preserves one winner's stable reason
   and timestamp.
6. Start racing activation deactivation cannot leave a catchable session after
   deactivation commits.
7. Start racing fursuit disablement cannot commit from stale enablement.
8. Start racing profile disablement cannot commit from stale eligibility.
9. Start racing enrollment removal cannot commit from stale membership.
10. Start racing Convention transition to non-playable cannot commit from stale
    playability.
11. Restored eligibility racing restart cannot resurrect the prior session;
    only an explicit valid start may create a new row.
12. Two simultaneous restarts after one expired unended row finalize that row
    once and create exactly one replacement.
13. An eligibility-losing mutation racing the expiration boundary applies the
    captured-time rule: an already-expired row ends at `expires_at` as
    `expired`, while a still-live row may end at mutation time as
    `eligibility_lost`.

Across the matrix:

- at most one unended session exists per activation;
- no start commits based on stale eligibility;
- no terminated session becomes active again;
- every real start produces exactly one historical row;
- every real terminal transition has exactly one stable reason/timestamp;
- no normal race leaks an `IntegrityError`, deadlock, or HTTP `500`.

## Rollout and rollback

The migration is additive and starts with no catch-session rows. Before durable
session data exists, normal migration reversal is acceptable. After use begins,
rollback must preserve session history and use compatible code or a forward
schema repair; it must not delete rows to restore an older application version.

No deployment, backfill, credential work, or production data mutation is part
of issue #118.
