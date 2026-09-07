# V0 persistent fursuit identity and Convention-scoped catch credentials

**Issue:** [#119 — Implement persistent TailTag identity and Convention-scoped
QR catch credentials](https://github.com/TailTag-Game/tailtag/issues/119)

**Parent:** [#111 — Establish V0 participation and catchability
domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved design, Acceptance Contract, and Test Surface Contract;
frozen on 2026-09-01 before production implementation

## Goal and domain distinctions

Give each fursuit one persistent public TailTag identity and one independently
revocable, opaque catch credential for each Convention activation. A credential
can be represented as a QR payload and resolved to a safe current preview, but
it is neither a permanent global QR identifier nor authorization to record a
catch.

The V0 state layers are distinct:

```text
Fursuit.id
    = internal application/database identity

Fursuit.tailtag_id
    = immutable public identity across Conventions

FursuitActivation
    = durable owner intent for one fursuit at one Convention

FursuitCatchCredential
    = current or historical opaque locator for one activation

FursuitCatchSession
    = bounded declaration that the fursuit is presently out

Credential resolution
    = safe current preview only

Catch creation
    = future independent authoritative validation
```

A current Convention credential may survive routine catch-session boundaries.
Operational eligibility loss, owner rotation, or operator revocation terminally
revokes it. A revoked row never becomes current again.

## Existing contracts and dependencies

- Clerk remains the authentication authority and `accounts.User.id` remains
  the canonical internal TailTag application-user identity.
- `fursuits.Fursuit` remains the durable participating-character entity. No
  separate persistent-identity entity is introduced.
- Existing owner routes continue to use internal integer `Fursuit.id` values.
- `profiles.eligibility.is_participation_eligible` remains the profile-level
  participation predicate.
- Enrollment existence, not `ConventionEnrollment.is_active`, proves
  Convention enrollment.
- `Convention.is_playable` remains the Convention lifecycle authority.
- `conventions.services.is_fursuit_activation_eligible` and
  `get_operational_fursuit_activation` remain authoritative for operational
  participation.
- `conventions.catch_sessions` remains authoritative for temporary session
  lifecycle and effective active-session state.
- Issue #118 is complete and supplies the existing lifecycle mutation seams and
  PostgreSQL lock hierarchy extended by this issue.
- `/api/` remains the unversioned V0 product namespace.

## Scope and Scope Guard

### Included

- immutable, opaque `Fursuit.tailtag_id` values and safe migration backfill;
- the required `tailtag_id` field in every canonical owner fursuit response;
- append-only Convention-scoped catch-credential history under the
  `conventions` domain;
- lazy, idempotent owner credential fetch and explicit owner rotation;
- authenticated, caller-authorized, privacy-safe credential resolution;
- synchronous credential revocation from every repository-owned operational-
  eligibility-loss mutation;
- restricted Django-admin inspection and per-object operator revocation;
- exact OpenAPI contracts and focused automated evidence;
- real PostgreSQL race coverage for credential creation, rotation, revocation,
  eligibility transitions, resolution, and session interaction;
- explicit preservation of the future Wave 3 catch-write boundary.

### Excluded

- catch creation, persistence, history, collection, XP, or progression;
- treating resolution, `tailtag_id`, or any client assertion as catch
  authorization;
- QR PNG, SVG, base64, printable-card, badge, or other visual rendering;
- camera UI or photo-library/live-camera policy enforcement;
- global reusable QR identifiers, HTTPS universal links, or mobile deep links;
- BLE, NFC, GPS, proximity proof, per-catch owner approval, or advanced
  anti-cheat;
- a separate persistent-identity model, tombstone/archive infrastructure, or a
  destructive-deletion policy;
- credential encryption or new key-management infrastructure;
- a mutable current-credential pointer on `FursuitActivation`;
- operator credential HTTP APIs, bulk credential operations, or replacement
  creation through admin;
- signals, database triggers, background workers, leases, reservations, or
  durable resolution records;
- frontend/mobile implementation or production rollout.

### Review-unit Scope Guard

**Outcome:** Establish the frozen persistent fursuit identity, scoped credential
lifecycle, safe preview APIs, eligibility-loss integration, and operator support
without creating a catch-authorization path.

**Non-goals:** Every exclusion above, especially catch writes, QR rendering,
public probing, identifier-route migration, encryption infrastructure,
background processing, and unrelated domain cleanup.

**Expected change surface:** `fursuits` model, staged migration, serializers,
admin, and existing exact-response tests; `conventions` model and migration; a
focused `conventions.catch_credentials` domain module; activation-oriented
canonical eligibility/session seams where narrowly required; `conventions`
views, serializers, URLs, admin, and the six existing upstream lifecycle
services/admin paths; focused backend tests; OpenAPI; `CONTEXT.md`; and
implementation-coupled documentation. No new Django application or dependency
is authorized.

**Proof:** Acceptance-first tests mapped to AC-01 through AC-18, named database
constraints, exact API/OpenAPI assertions, admin secret-exposure checks, real
PostgreSQL race evidence, deterministic repository checks including Semgrep,
independent adversarial test review, fresh specification/security/code review,
and parent authoritative verification.

## Persistent fursuit identity

Add the following field to `fursuits.Fursuit`:

```python
tailtag_id = models.UUIDField(
    default=uuid.uuid4,
    unique=True,
    editable=False,
)
```

`tailtag_id` is server-generated, non-null, globally unique, immutable through
supported product/admin paths, and distinct from the internal primary key. It
is not accepted in create or mutation bodies and does not replace integer route
IDs in this issue.

The migration must not use one migration-time default for all existing rows.
Use a safe staged migration:

1. add a nullable temporary field state;
2. assign a distinct UUID to each existing fursuit;
3. alter the field to its final non-null, defaulted, unique contract.

Every canonical owner-facing fursuit response becomes exactly:

```json
{
  "id": 17,
  "tailtag_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Example Suit",
  "photo_url": "https://media.example.test/...",
  "is_enabled": true
}
```

This applies to create, list, detail, name-update, and photo-update success
responses. Existing closed request schemas remain unchanged and reject
`tailtag_id`.

## Credential persistence

Create `conventions.FursuitCatchCredential` as historical state:

| Field | Persistence contract |
| --- | --- |
| `id` | Repository-default `BigAutoField`; internal primary key |
| `activation` | Required `ForeignKey(FursuitActivation, on_delete=PROTECT, related_name="catch_credentials")` |
| `token` | Required raw 43-character output of `secrets.token_urlsafe(32)` |
| `created_at` | Required server-controlled creation timestamp |
| `updated_at` | Required server-controlled latest-mutation timestamp |
| `revoked_at` | Nullable server-controlled terminal timestamp |
| `revocation_reason` | Nullable enum: `owner_rotation`, `operator`, or `eligibility_lost` |

Use named database constraints that enforce:

```text
revoked_at IS NULL <=> revocation_reason IS NULL
revocation_reason IS NULL OR revocation_reason IN (
    owner_rotation, operator, eligibility_lost
)
token is globally unique
at most one row per activation WHERE revoked_at IS NULL
```

The partial uniqueness constraint is the sole persistent authority for the
current credential. Do not add a current pointer to `FursuitActivation`.

No credentials are created by migration. Existing activations obtain them only
through the normal runtime owner-fetch lifecycle.

Credential history is append-only except for one terminal current-to-revoked
transition. That transition sets `revoked_at`, `revocation_reason`, and
`updated_at` together. A revoked row is never edited, reassigned, reactivated,
or deleted through product/admin paths.

## Token generation and canonical payload

Generate tokens with exactly:

```python
secrets.token_urlsafe(32)
```

The stored value is the raw 43-character token only. The database does not
store the protocol envelope.

The only V0 payload grammar is:

```text
tailtag:catch:v1:<43 characters from [A-Za-z0-9_-]>
```

Payload formatting and parsing belong to `conventions.catch_credentials` so
the application protocol can evolve independently from persisted identity.
Parsing is exact: do not trim, normalize, decode alternate encodings, accept
padding, or accept another version.

The payload contains no fursuit, owner, activation, Convention, session,
database, or mutable domain value. The stored token-to-activation relationship
is authoritative for Convention scope.

## Credential-domain module

Create one cohesive `conventions.catch_credentials` module. It owns:

- owner get-or-create;
- owner rotation;
- payload formatting and parsing;
- credential resolution;
- operator revocation;
- typed eligibility-loss revocation helpers for activation, profile, fursuit,
  enrollment, and Convention scopes;
- credential locking and recognized uniqueness-conflict recovery;
- privacy-safe domain results and errors.

Do not split command/query modules unless implementation evidence reveals a
concrete dependency problem that requires replanning. Do not place credential
lifecycle logic in `catch_sessions.py` or general `conventions.services`.

Temporary session transitions and credential transitions do not implicitly call
each other. Only an upstream operational-eligibility-loss service deliberately
orchestrates both domains.

### Canonical target checks

Caller authorization and target eligibility are independent. Credential
resolution must never pass the resolving caller as the owner argument to an
owner-scoped target helper.

Use a narrow activation-oriented canonical seam:

```text
credential.activation
    -> canonical operational-participation check for that activation
    -> canonical effective-session check for that activation
```

Reuse `is_fursuit_activation_eligible(activation)` and add an activation-oriented
effective-session helper without changing established public/service behavior.
Target catchability never depends on whether the resolving caller owns the
fursuit.

## Owner credential lifecycle

### Fetch/get-or-create

Lock and revalidate in this order:

```text
PlayerProfile
Convention
ConventionEnrollment
Fursuit
FursuitActivation
current FursuitCatchCredential, if present
```

Then:

```text
current credential exists
    -> return it without mutation

no current credential exists
    -> create exactly one and return it
```

Normal fetch is idempotent. It does not start a catch session and does not
require an active catch session.

The activation lock normally serializes creation. The named one-current-
credential constraint is the final defense. If that exact conflict is observed,
recover the winning current row without leaking `IntegrityError`. One bounded
regeneration retry handles only the exact named global-token constraint; a
repeated collision propagates. Every unrelated integrity failure propagates.

### Owner rotation

Under the same locks and operational validation:

```text
current credential exists
    -> revoke it at captured now as owner_rotation
    -> create and return one replacement

no current credential exists
    -> create and return one credential
```

Rotation is intentionally state-changing, not idempotent. Two serialized
rotations may create two successive replacements; only the final row remains
current.

## Credential and session lifecycle independence

These boundaries are invariant:

```text
session start                 != credential creation or rotation
session stop                  != credential revocation
session expiration            != credential revocation
operator session termination  != credential revocation
credential fetch              != session start
credential rotation           != session transition
operator credential revocation != session transition
```

A current credential may fail resolution while its session is stopped or
expired and resolve again during a later effective session. Operator credential
revocation may leave an active session intact. The eligible owner may later
fetch a replacement.

## Eligibility-loss integration

Every repository-owned mutation that makes an activation operationally
ineligible performs this sequence in one transaction:

```text
acquire required upstream locks
identify and lock affected activations once
catch_credentials revokes current credentials
catch_sessions terminates sessions using those already-locked activations
persist upstream eligibility-losing mutation
```

Neither child helper may reacquire an activation after credential locks exist.
Where needed, add a narrowly typed session helper whose contract requires
already-locked activations.

Use one captured `now` for credential revocation, session termination, and the
upstream transition. Every affected current credential receives:

```text
revoked_at = now
revocation_reason = eligibility_lost
updated_at = normal mutation timestamp
```

Credential revocation has no expiration concept. It occurs whether the session
is live, expired-but-unfinalized, or already terminal. The session domain
separately preserves its expiration precedence.

The integration inventory is:

| Eligibility loss | Existing upstream authority | Required credential/session orchestration |
| --- | --- | --- |
| Owner activation deactivation | `conventions.services.set_fursuit_activation_state` | locked activation -> credential revocation -> session termination -> deactivate |
| Operator activation deactivation | `conventions.services.deactivate_fursuit_activation_as_operator` | same order and reason as owner deactivation |
| Fursuit enabled to disabled | `fursuits.services.set_fursuit_enabled` | locked fursuit -> affected activations -> credentials -> sessions -> disable |
| Profile enabled to disabled | `profiles.services.set_profile_enabled` | locked profile -> affected activations -> credentials -> sessions -> disable |
| Enrollment removal | `conventions.services.remove_convention_enrollment` | profile -> Convention -> enrollment -> affected activations -> credentials -> sessions -> delete |
| Convention active to non-playable | `conventions.services.set_convention_admin_state` | Convention -> affected activations -> credentials -> sessions -> update |

Restoring eligibility creates no credential. The next eligible owner fetch may
create a new row. Selecting or clearing `ConventionEnrollment.is_active` is not
eligibility loss and does not affect credentials.

As in #118, direct ad hoc ORM mutation is an unsupported bypass. This issue
guarantees repository-owned product/admin mutation paths and does not add model
signals or database triggers.

## HTTP APIs

### Owner credential fetch

```http
GET /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/
```

There is no request body. Success is HTTP `200` with exactly:

```json
{
  "payload": "tailtag:catch:v1:<43-character-token>"
}
```

External precedence is:

```text
authentication
-> owned fursuit or concealed 404
-> Convention or 404
-> existing activation or 404
-> locked operational-participation validation
-> fetch/create current credential
```

After the activation relationship resolves, an ineligible owner profile returns
the established sanitized `403`. Missing current enrollment, inactive
activation, disabled fursuit, or non-playable Convention returns one sanitized
operational `400`. Missing enrollment must not be reinterpreted as a missing
activation relationship.

### Owner rotation

```http
POST /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/rotate/
```

Success is HTTP `200` with the same exact one-field payload representation.
The operation accepts zero body bytes and OpenAPI has no `requestBody`:

```text
zero raw body bytes     -> valid
any nonzero body bytes  -> sanitized 400
```

An incidental content-type on an empty request is irrelevant. Do not access
`request.data` to decide body presence. Resource/ownership resolution precedes
raw-body rejection:

```text
authentication
-> owned fursuit or concealed 404
-> Convention or 404
-> existing activation or 404
-> reject nonempty raw body
-> locked operational-participation validation
-> rotate credential
```

### Credential resolution

```http
POST /api/conventions/{convention_id}/catch-credentials/resolve/
Content-Type: application/json
```

The request is exactly:

```json
{
  "payload": "tailtag:catch:v1:<43-character-token>"
}
```

The closed serializer uniformly rejects absent/additional fields, null or
non-string values, non-ASCII text, whitespace, a wrong prefix, an unsupported
version, a token of another length, `=` padding, or characters outside
`[A-Za-z0-9_-]`. It does not normalize input.

External precedence is:

```text
authentication
-> closed JSON/request validation
-> path Convention existence
-> caller profile participation eligibility
-> caller enrollment existence
-> generic target resolution
```

Caller profile ineligibility and missing caller enrollment each produce a
sanitized `403`. Caller ownership and active-Convention selection are
irrelevant. Convention playability is target state, not caller authorization.

After caller authorization, locate only an unrevoked token scoped through its
activation to the path Convention. Evaluate canonical target operational
participation and effective active-session state. Recheck that the credential
is still current before returning. Do not add a row lock, reservation, lease,
or durable resolution record merely to remove unavoidable preview staleness.

Every target failure returns exactly HTTP `404` with:

```json
{
  "detail": "Catch credential not found."
}
```

This includes an unknown token, revoked token, wrong Convention, inactive
activation, ineligible target owner, disabled target fursuit, missing target
enrollment, non-playable Convention, missing/stopped/expired session, and a
credential that ceases to be current during resolution.

Success is HTTP `200` with exactly:

```json
{
  "convention_id": 4,
  "fursuit": {
    "tailtag_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Example Suit",
    "photo_url": "https://media.example.test/..."
  }
}
```

The response uses the persisted `tailtag_id` and existing safe media URL
service. It exposes no internal fursuit ID, owner identity, Clerk identity,
credential/token, activation/session ID, timestamp, eligibility/moderation
state, or revocation information. Resolution never echoes the submitted
payload.

## Resolution authority and Wave 3 boundary

Resolution succeeds only when all are true when evaluated:

```text
payload structure is valid
AND current credential exists for the path Convention
AND activation is active and operationally eligible
AND one effective active/unexpired catch session exists
AND final current-credential check succeeds
```

A successful resolution means only that the credential resolved to a currently
catchable target when resolution was evaluated. It is not authorization to
create a catch.

A rotation, stop, or eligibility transition may commit immediately after the
final check. That staleness is intentional. Wave 3 must receive the original
scanned payload and independently revalidate credential status, Convention
scope, operational participation, effective session, catcher eligibility,
duplicate-catch rules, and every future catch-specific requirement in its own
write-time transaction.

## Transactions and global lock order

Credential-related lifecycle mutations use `transaction.atomic()` and preserve
this global relative PostgreSQL row-lock order:

```text
1. PlayerProfile
2. Convention
3. ConventionEnrollment
4. Fursuit
5. FursuitActivation
6. FursuitCatchCredential
7. FursuitCatchSession
```

Operations may skip unneeded types but never acquire an earlier type after a
later type. Multiple rows of one type lock in ascending primary-key order.

Owner fetch/rotation locks the full eligibility chain through activation, then
the current credential. Operator revocation preliminarily discovers IDs, then
locks activation before the selected credential. Multi-activation eligibility
loss locks all activations, then all current credentials, then all relevant
sessions.

Normal races must produce a valid serial outcome without leaked deadlock,
`IntegrityError`, or HTTP `500`. Resolution is intentionally lock-free preview
logic; its allowed stale success does not weaken write-time requirements.

## Django admin

Register `FursuitCatchCredential` as a restricted support/history surface
following the catch-session admin pattern.

Safe metadata may include credential row ID, activation, safe fursuit and
Convention metadata, derived current/revoked state, timestamps, and revocation
reason. `current` means exactly `revoked_at IS NULL`; it is not persisted.

The raw token is absent from fields, readonly fields, list display, filters,
search, forms, messages, object labels, custom ordering, model string/repr, and
admin log/history representations.

Safe search is limited to:

```text
id__exact
activation__id__exact
activation__fursuit__id__exact
activation__fursuit__tailtag_id__exact
activation__fursuit__owner__id__exact
activation__convention__id__exact
activation__fursuit__name
activation__convention__name
```

There is no token or token-derived search.

The only mutation is a per-object custom form control:

```python
revoke = forms.BooleanField(
    required=False,
    label="Revoke current credential",
)
```

The form exposes no editable model fields. Submission performs a safe
preliminary lookup, locks activation then credential, and terminally revokes a
current row with reason `operator`. Repeated revocation is a no-op and preserves
the prior timestamps/reason. Stale admin state cannot overwrite an intervening
rotation or eligibility-loss revocation.

Operator credential revocation changes no activation, fursuit, enrollment,
profile, Convention, or session state and creates no replacement. Admin denies
add/delete, sets `actions = None`, and provides no reassignment, token editing,
history editing, reactivation, rotation, or replacement path. No operator HTTP
API is added.

`FursuitAdmin` displays `tailtag_id` as immutable read-only metadata and permits
exact search by it. It provides no regeneration action.

## Repository-controlled secret non-exposure

Raw tokens and canonical payloads must never be deliberately emitted by
repository-owned logging, exception, tracing, metrics, admin, serialization,
or OpenAPI code.

- Credential endpoints do not log request or response bodies.
- Exception messages do not interpolate tokens or payloads.
- Admin history/log object representations use safe identifiers only.
- OpenAPI may describe the grammar with a clearly synthetic placeholder, never
  a generated or usable credential.
- Resolution errors never echo submitted payloads.

The repository does not claim control over every external infrastructure or
framework diagnostic facility. Tests cover repository-controlled surfaces that
could reasonably expose values.

## OpenAPI

Generated OpenAPI exposes exactly these Issue #119 product routes:

```text
GET  /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/
POST /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/rotate/
POST /api/conventions/{convention_id}/catch-credentials/resolve/
```

It freezes Bearer authentication, exact methods, closed schemas, required and
read-only fields, UUID/URI formats, no request body for fetch or rotation, the
exact resolution body, applicable `200`/`400`/`401`/`403`/`404`/`405`
semantics, generic target non-resolution, the payload grammar, safe preview,
and explicit preview-not-authorization language. Unsupported methods use
sanitized `405`. No QR image/rendering route exists.

## Acceptance Contract

### AC-01 — Persistent fursuit identity

- Every fursuit has a non-null, globally unique, server-generated UUID
  `tailtag_id`.
- Existing rows receive distinct backfilled values.
- Supported updates never change it.
- It remains distinct from integer `id` and all credentials.

### AC-02 — Canonical owner representation

- Create, list, detail, name-update, and photo-update responses contain exactly
  `id`, `tailtag_id`, `name`, `photo_url`, and `is_enabled`.
- All request schemas remain closed and reject `tailtag_id`.

### AC-03 — Credential persistence

- Credentials are historical rows protected through `FursuitActivation`.
- Named constraints enforce paired revocation fields, exact reasons, globally
  unique tokens, and one unrevoked credential per activation.
- No current pointer or migration credential backfill exists.
- Revocation is the only legitimate post-creation mutation.

### AC-04 — Token and payload security

- Generation calls `secrets.token_urlsafe(32)` and persists only its raw
  43-character result.
- Formatting and exact parsing produce only the frozen V1 grammar.
- Payloads contain no predictable/internal identifiers or domain data.

### AC-05 — Idempotent owner fetch

- The exact authenticated GET requires ownership, an existing activation, and
  locked current operational participation.
- Repeated fetch returns the unchanged payload with no timestamp/history write.
- First fetch creates exactly one credential.
- Concurrent first fetches converge on one current row and payload.

### AC-06 — Explicit owner rotation

- The exact authenticated POST accepts zero body bytes only.
- Rotation terminally revokes the current row as `owner_rotation`, if present,
  and creates one replacement.
- Rotation without a current row creates one.
- Serialized concurrent rotations may create successive history but leave one
  current row.
- Only named credential conflicts receive narrow recovery.

### AC-07 — Credential/session independence

- Routine session transitions never mutate credentials.
- Credential fetch, rotation, and operator revocation never mutate sessions.
- A credential may survive a stopped/expired session and resolve during a later
  effective session.

### AC-08 — Eligibility loss

- Every supported repository-owned eligibility loss revokes affected current
  credentials as `eligibility_lost` and terminates sessions in one transaction.
- Activations, credentials, and sessions are locked once in frozen order.
- Restoration never revives a credential; a later eligible fetch creates a
  distinct replacement.
- Active-Convention selection changes have no credential effect.

### AC-09 — Owner authorization and concealment

- Owner routes follow the frozen precedence.
- Missing and cross-owner fursuits are indistinguishable.
- After an activation relationship resolves, an ineligible profile yields the
  sanitized `403`; absent enrollment, inactive activation, disabled fursuit,
  and non-playable Convention yield one indistinguishable sanitized `400`.
- Missing current enrollment is never reclassified as a missing activation.

### AC-10 — Resolution input and caller authorization

- The exact POST route accepts only the frozen closed JSON and exact payload
  grammar.
- Authentication precedes validation.
- Caller profile ineligibility and missing caller enrollment yield sanitized
  `403`.
- Caller ownership and active-Convention selection are irrelevant.
- Convention playability is target state only.

### AC-11 — Generic target non-resolution

- Every frozen target failure produces exactly HTTP `404` and
  `{"detail":"Catch credential not found."}`.
- Wrong-Convention, random, revoked, and currently ineligible credentials are
  externally indistinguishable.
- No target-state reason reaches status, detail, fields, or metadata.

### AC-12 — Safe successful preview

- Success returns exactly `convention_id` and nested `tailtag_id`, `name`, and
  safe `photo_url`.
- `tailtag_id` matches the canonical owner representation.
- No internal/private identity, credential, relationship, lifecycle,
  eligibility, or moderation data is returned.

### AC-13 — Preview, not authorization

- Resolution creates no reservation, nonce, lease, record, or authorization
  artifact.
- A concurrent transition may make a successful preview immediately stale.
- OpenAPI/specification require Wave 3 to submit and revalidate the original
  payload at authoritative catch-write time.

### AC-14 — Locking and concurrency

- All credential mutations preserve the global row-type and same-type ordering.
- Child helpers never reacquire activations after credential locking.
- Normal races produce valid serial outcomes without leaked deadlock,
  `IntegrityError`, or HTTP `500`.
- At most one credential remains current per activation.

### AC-15 — Restricted operator support

- Admin safely displays credential history and derived current/revoked state.
- Its sole mutation is per-object idempotent operator revocation.
- Revocation leaves activation and session state unchanged.
- Add, delete, edit, reassignment, reactivation, rotation, replacement, token
  search, and bulk actions are unavailable.

### AC-16 — Repository-controlled secret non-exposure

- Raw tokens and canonical payloads are never deliberately emitted through
  repository-owned logging, exceptions, tracing, metrics, admin,
  serialization, or OpenAPI.
- Only a successful authorized owner credential response returns the raw token
  within its canonical payload.
- Resolution never echoes it, including errors.

### AC-17 — OpenAPI

- Generated OpenAPI contains exactly the three Issue #119 routes and methods.
- It freezes authentication, closed schemas, formats, statuses, no-body
  rotation, payload grammar, generic non-resolution, safe preview, and
  non-authorization semantics.
- No QR rendering endpoint exists.

### AC-18 — Scope and regression safety

- No excluded catch write, rendering, operator API, pointer, encryption system,
  tombstone system, signal, trigger, worker, reservation, or mobile behavior is
  introduced.
- Existing fursuit, activation, enrollment, Convention, and session behavior
  changes only at approved identity/credential integration points.

## Test Surface Contract

Tests observe behavior through these approved seams:

- the exact DRF routes and generated OpenAPI document;
- canonical fursuit response projections;
- `Fursuit` and `FursuitCatchCredential` metadata, migrations, and PostgreSQL
  constraints;
- package-internal `conventions.catch_credentials` operations;
- activation-oriented canonical operational-participation and effective-session
  helpers;
- the six existing upstream service/admin mutation paths;
- credential and fursuit Django admin forms, pages, permissions, search, and
  admin log/history;
- real PostgreSQL transactions on separate connections with controlled
  threads/barriers.

Tests may use existing forced-authentication and fixture helpers, direct ORM
setup for preconditions/constraint probes, deterministic patching of the
existing clock and `secrets.token_urlsafe`, the existing media URL test seam,
and Django admin request/form helpers.

No public testing endpoint, model signal, database trigger, production clock or
randomness injection API, new dependency, or test-only domain abstraction is
approved.

Every test maps to an Acceptance Contract item, frozen invariant, named race,
or selected assurance modifier. Tests assert observable behavior rather than
private helper names.

## Review-unit and test-group traceability

| Review unit / test group | Expected areas | Governing acceptance items |
| --- | --- | --- |
| Persistent identity schema and migration | `fursuits` model/migration, migration executor tests | AC-01, AC-03, AC-18 |
| Canonical fursuit representation | fursuit serializers/views/OpenAPI/exact-response tests | AC-01, AC-02, AC-16, AC-17 |
| Credential persistence and payload protocol | `conventions` model/migration, `catch_credentials`, integrity/protocol tests | AC-03, AC-04, AC-14, AC-16 |
| Owner credential API | credential domain, serializers/views/URLs, owner API tests | AC-05, AC-06, AC-09, AC-16, AC-17 |
| Resolution API | activation/session canonical seams, credential domain/API, resolution tests | AC-04, AC-10, AC-11, AC-12, AC-13, AC-16, AC-17 |
| Eligibility-loss integration | profile/fursuit/convention services, credential/session helpers, lifecycle tests | AC-07, AC-08, AC-14, AC-18 |
| Operator support | convention/fursuit admin, operator service, admin/log tests | AC-01, AC-15, AC-16, AC-18 |
| PostgreSQL concurrency | credential concurrency tests extending existing harness | AC-05, AC-06, AC-07, AC-08, AC-13, AC-14 |
| Whole contract and documentation | OpenAPI, glossary, implementation-coupled docs, deterministic checks | AC-13, AC-16, AC-17, AC-18 |

The implementation plan must break these into dependency-ordered tasks and map
each task and test group back to the same acceptance items. A task may combine
adjacent rows only when it remains one coherent review unit.

## Required deterministic and behavioral evidence

### Identity and schema

- per-row UUID backfill, uniqueness, non-null state, default generation, and
  supported-path immutability;
- exact five-field owner responses across create/list/detail/update;
- rejection of client-supplied `tailtag_id`;
- credential `PROTECT`, named constraints, no backfill, and one terminal
  mutation;
- exact 32-byte generator invocation and raw-token persistence.

### Owner APIs

- first/repeated fetch and unchanged timestamps/history;
- first/repeated rotations, rotation without prior credential, and distinct
  replacement rows/tokens;
- exact route methods, raw-body behavior, error precedence, profile `403`,
  operational `400`, and ownership concealment;
- named uniqueness-conflict handling and propagation of unrelated integrity
  failures.

### Resolution

- every malformed grammar/input case produces the same sanitized field `400`;
- caller eligibility/enrollment `403` cases;
- exact success response and safe media URL;
- all target failures produce the exact generic `404`;
- wrong-Convention equals random-token behavior;
- activation-oriented target checks never use the resolving caller as owner;
- final current-row recheck and non-authorization documentation.

### Lifecycle

- activation deactivation through owner and operator paths;
- fursuit/profile disablement, enrollment removal, and Convention becoming
  non-playable;
- same-transaction credential revocation and session termination;
- one captured timestamp and frozen lock ordering;
- restored eligibility creates no state until fetch and never revives history;
- active-Convention selection and every routine session transition leave
  credentials unchanged.

### Admin and non-exposure

- normal staff/admin access requirements;
- safe list/detail/current-state/search behavior;
- no add/delete/bulk/history editing/token search;
- operator reason, session independence, repeat no-op, and stale-form safety;
- absence of a known token from HTML, forms, messages, labels, admin log/history,
  errors, unrelated serialization, and OpenAPI;
- read-only searchable `FursuitAdmin.tailtag_id`.

## PostgreSQL concurrency matrix

Use real PostgreSQL connections and controlled barriers/lock observation. For
timing-dependent races, assert allowed serial outcomes and forbidden states
rather than one deterministic winner.

1. **Two first fetches:** both return the same payload; one current row exists.
2. **Fetch vs rotation:** fetch-first may return the soon-revoked old value;
   rotation-first makes fetch return the replacement. Final state has one
   current row.
3. **Two rotations:** the winner order may vary; two successive terminal
   rotations are valid and only the last replacement remains current.
4. **Rotation vs operator revocation:** either valid serial order may win;
   existing terminal history is never rewritten and final state has zero or one
   current row according to whether rotation validly created a later row.
5. **Operator revocation vs owner fetch:** fetch-first returns the existing value
   and operator then revokes it, leaving no current row; operator-first revokes
   it and fetch creates one distinct replacement. Never more than one current
   row; the revoked row is never rewritten/reactivated.
6. **Fetch vs activation deactivation:** fetch-first may return a value later
   revoked by deactivation; deactivation-first makes fetch fail operational
   validation. After deactivation commits, no current row remains.
7. **Rotation vs activation deactivation:** rotation-first may create a
   replacement that deactivation then revokes; deactivation-first makes
   rotation fail. No current row remains after deactivation.
8. **Fetch/rotation vs fursuit disablement:** either valid serial outcome is
   accepted; committed disablement leaves no current credential.
9. **Fetch/rotation vs profile disablement:** either valid serial outcome is
   accepted; committed disablement leaves no current credential.
10. **Fetch/rotation vs enrollment removal:** either valid serial outcome is
    accepted; committed removal leaves no current credential.
11. **Fetch/rotation vs Convention non-playability:** either valid serial
    outcome is accepted; committed transition leaves no current credential.
12. **Eligibility restoration vs fetch:** an old revoked row never revives;
    only an explicitly created distinct row may become current after restoration.
13. **Resolution vs rotation/operator revocation:** resolution may succeed
    before the mutation or return generic `404` after it; the old payload fails
    after commit and success remains only a preview.
14. **Resolution vs eligibility loss:** resolution may succeed before the
    transaction or return generic `404` after it; it fails after commit.
15. **Resolution vs session stop/expiration/restart:** results follow valid
    evaluation timing; the credential row remains unchanged and may resolve
    again after a later effective session.
16. **Session start/stop vs credential operations:** valid independent serial
    outcomes are accepted; neither history domain receives an unauthorized
    side effect and global lock order is preserved.

Across the matrix:

- no deadlock escapes;
- no expected race leaks `IntegrityError` or HTTP `500`;
- unrelated integrity failures are not swallowed;
- no revoked credential is reactivated or terminal history rewritten;
- at most one unrevoked credential exists per activation;
- committed eligibility loss leaves no current credential;
- credential and session history remain independently correct;
- stale successful resolution remains only a preview.

## Plausible-mutant analysis

Before implementation approval, independently confirm that tests reject at
least these plausible defects:

- migration assigns one UUID to all existing fursuits;
- clients submit or mutate `tailtag_id`;
- protocol envelope rather than raw token is persisted;
- token generation is predictable or payload includes domain IDs;
- resolution passes the resolving caller to an owner-scoped target helper;
- a Convention A credential resolves through Convention B;
- resolution checks only `revoked_at IS NULL` and omits the final proof that the
  row remains current for its activation;
- one operational-participation or effective-session predicate is skipped;
- target failures produce distinguishable responses;
- routine session stop/expiration revokes a credential;
- one upstream eligibility-loss seam omits revocation;
- restored eligibility revives an old credential;
- owner fetch validates eligibility before locks but does not revalidate under
  the frozen lock set;
- successful preview leaks internal/private fields;
- repository-controlled admin/log/error/OpenAPI output leaks a token;
- a lifecycle helper reacquires activation after credential locks;
- resolution is treated as catch authorization.

Do not add mutation tooling solely for this issue.

## Rollout and rollback

The fursuit migration backfills one distinct public UUID per existing row. The
credential migration is additive and creates no operational secrets or rows.

Before credential use begins, normal credential-migration reversal is
acceptable. Once credential history exists, rollback must preserve those rows
and use compatible code or a forward schema repair; it must not delete history
to restore older application behavior. Reversing the fursuit identity migration
after clients consume `tailtag_id` would break a public contract and requires a
separate migration/compatibility decision.

No production deployment, data export, external credential issuance, or Wave 3
catch rollout is part of Issue #119.

## Risks and resolved decisions

Primary risks are lifecycle races, old-token revival, cross-Convention use,
target-state privacy leakage, accidental token exposure, and erosion of the
Wave 3 authorization boundary. The frozen lock order, terminal history,
generic target failure, restricted surfaces, real PostgreSQL matrix, and
adversarial review address these risks.

There are no unresolved product, security, lifecycle, API, persistence, admin,
test-surface, or concurrency decisions in this specification. Exact internal
names and dependency-ordered implementation sequencing belong to the approved
implementation plan and must not alter observable behavior.
