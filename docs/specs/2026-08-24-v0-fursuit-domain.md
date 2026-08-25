# V0 fursuit domain and owner-scoped APIs

**Issue:** [#115 — Implement the V0 fursuit domain and owner-scoped APIs](https://github.com/TailTag-Game/tailtag/issues/115)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved for implementation

## Goal

Activate the existing `fursuits` Django application as TailTag's durable,
owner-scoped participating-character domain. At completion, an authenticated
eligible player can register a named fursuit with a required valid photo and
can manage that record without gaining control of ownership or global
moderation state. Operators can inspect records and enable or disable them
without receiving a path to forge ownership or media references.

This issue establishes the persistent fursuit identity consumed by later Wave
2 domains. It does not make a fursuit active at a Convention, catchable, or
scannable.

## Existing contracts

- Clerk remains the external authentication authority.
- `accounts.User.id` remains the canonical TailTag application identity.
  Fursuit ownership never stores or exposes a Clerk identifier.
- The profile-owned participation predicate retains exactly this meaning:
  authenticated, onboarding completed, and profile enabled. Fursuit writes
  use that predicate; later Convention domains compose their own additional
  requirements without broadening it.
- The approved #112 media module remains the sole image-validation, storage,
  object-key, read-access, replacement, and compensating-cleanup boundary.
- `/api/` remains the unversioned V0 product namespace.
- `fursuits` remains the application and API term. Use **participating
  character** when domain prose needs to distinguish the durable character
  record from a physical costume.

## Scope

Issue #115 owns:

- the durable `Fursuit` model and migration;
- owner-scoped create, list, retrieve, name-update, and photo-replacement APIs;
- profile-level write eligibility and strict cross-owner concealment;
- operator inspection and global enable/disable administration;
- required-photo media orchestration and same-fursuit replacement
  serialization;
- database constraints, OpenAPI, focused tests, and implementation-coupled
  contributor documentation.

Issue #115 does not own:

- player or operator deletion, archival, restoration, or ownership transfer;
- multiple owners, species taxonomy, descriptions, or other historical POC
  fields;
- Convention enrollment or per-Convention fursuit activation;
- catch sessions, catch records, QR credentials, or a permanent public QR
  identifier;
- aggregate storage quotas, fursuit-specific throttling, general orphan
  reconciliation, or broader abuse-prevention infrastructure.

## Fursuit model

Create `fursuits.Fursuit` with this persistence contract:

| Field | Persistence contract |
| --- | --- |
| `id` | Repository-default `BigAutoField`; stable TailTag-owned internal identity |
| `owner` | Required `ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="fursuits")`; immutable after creation |
| `name` | Required `CharField(max_length=50)` containing the normalized human-facing name |
| `photo_key` | Required `TextField` containing an opaque media object key; never a URL |
| `is_enabled` | Required boolean, default `True`; operator-controlled global moderation state |
| `created_at` | Required server-controlled creation timestamp |
| `updated_at` | Required server-controlled timestamp of the latest actual durable mutation |

The named `fursuits_fursuit_name_not_empty` and
`fursuits_fursuit_photo_key_not_empty` check constraints reject empty `name`
and `photo_key` values. Application services remain responsible for complete
name and media-key validity. Object storage and PostgreSQL cannot provide a
shared foreign-key or transaction, so a nonempty key is defense in depth
rather than proof that an object currently exists.

The owner relationship uses `PROTECT`. Player APIs and Django admin expose no
deletion path. Migration reversal is acceptable only before durable fursuit
data exists. After use begins, rollback preserves the table, rows, and migration
history and uses compatible code or a forward schema repair.

The model's default ordering is ascending `id`, which is also the explicit
owner-list ordering. Names are mutable and non-unique. New records are always
enabled by the server; player input cannot choose the initial state.

`updated_at` changes on successful creation, name changes, photo-reference
changes, and operator enable/disable changes. A normalized no-op name PATCH
does not write the database and does not change `updated_at`.

## Name normalization

Fursuit names use TailTag's established 1–50-code-point, NFC, single-line
human-name policy:

1. Normalize Unicode to NFC.
2. Reject Unicode control characters in category `Cc` and line or paragraph
   separators in categories `Zl` and `Zp`.
3. Trim leading and trailing whitespace.
4. Collapse each remaining run of Unicode whitespace to one ASCII space.
5. Require 1 through 50 Unicode code points in the result.

Validation errors are safe `name` field errors. This issue adds no name
uniqueness, aliases, profanity filtering, taxonomy, or moderation history.

## Player representation

Every successful player-facing fursuit representation contains exactly:

```json
{
  "id": 42,
  "name": "Example Character",
  "photo_url": "https://media.example.test/presigned-read",
  "is_enabled": true
}
```

`photo_url` is required and non-null. Each representation generates a fresh,
short-lived read URL through #112, including for an operator-disabled fursuit.
The URL is a bearer credential: it is never persisted or logged. The response
contains no owner ID, Clerk ID, opaque object key, timestamps, or administrative
metadata.

Unexpected read-URL generation failure follows the normal 5xx path. A database
mutation that already committed remains authoritative even if URL generation
or HTTP delivery subsequently fails. Clients reconcile ambiguous results with
GET or list and must not blindly replay non-idempotent creation.

## HTTP interface

All routes explicitly require TailTag authentication:

```text
POST  /api/fursuits/
GET   /api/fursuits/
GET   /api/fursuits/{id}/
PATCH /api/fursuits/{id}/
PUT   /api/fursuits/{id}/photo/
```

There is no player DELETE, detail PUT, owner mutation, or enable/disable
operation. Unsupported methods return HTTP `405`.

### POST `/api/fursuits/`

Creation accepts only `multipart/form-data` with exactly one text value named
`name` and exactly one uploaded file named `photo`:

```text
name=Example Character
photo=<file>
```

The endpoint checks profile-level participation eligibility before parsing the
multipart body. The form-value key set must be exactly `{name}` and the file
key set exactly `{photo}`, each with a one-item value list. The implementation
must explicitly inspect those lists rather than rely on serializer or
`QueryDict` single-value collapsing. Unknown, forbidden, repeated, or
additional form or file entries fail with HTTP `400`, even when the required
entries are also valid. Missing multipart encoding or required entries is a
sanitized HTTP `400` `photo` or `name` field error as applicable.

A successful request creates one enabled fursuit owned by `request.user` and
returns HTTP `201` with the complete representation. POST is intentionally
non-idempotent. Every successful repeated request creates a distinct record;
the #120 retry contract does not authorize blind creation replay.

### GET `/api/fursuits/`

Return HTTP `200` with an unpaginated JSON array containing only the caller's
fursuits in ascending `id` order. Reads require authentication but do not
require completed onboarding or an enabled profile. Operator-disabled records
remain visible to their owner.

### GET `/api/fursuits/{id}/`

Return HTTP `200` with the complete representation for an owned record.
Missing and cross-owner identifiers both return HTTP `404` through the same
owner-filtered lookup.

### PATCH `/api/fursuits/{id}/`

Accept only JSON with exactly one field, `name`. The schema is closed: an empty
object, any unknown, forbidden, or read-only field, or any such field mixed
with a valid name fails with HTTP `400`.

The endpoint authenticates and resolves the owner-scoped target before reading
the request body, then rejects a profile-ineligible owner before parsing or
validation. A successful actual name change returns HTTP `200` with the
complete representation and updates `updated_at`. A name that normalizes to
the existing value returns the same response without a database write or
timestamp change.

An operator-disabled fursuit remains name-editable by an otherwise eligible
owner for remediation. The operation never changes `owner`, `photo_key`, or
`is_enabled`.

### PUT `/api/fursuits/{id}/photo/`

Photo replacement accepts only `multipart/form-data` with exactly one uploaded
file named `photo`. The form-value key set must be empty and the file key set
exactly `{photo}` with a one-item value list. Explicit list inspection rejects
unknown, forbidden, repeated, or additional form or file entries with HTTP
`400`. Missing multipart encoding or the required file is a sanitized HTTP
`400` `photo` field error.

The endpoint authenticates and resolves the owner-scoped target before reading
the request body or acquiring locks, then rejects a profile-ineligible owner
before multipart parsing, image validation, storage access, or locking. A
successful replacement returns HTTP `200` with the complete representation and
updates `updated_at`.

An operator-disabled fursuit remains photo-editable by an otherwise eligible
owner for remediation. There is no remove-photo operation because the photo is
required.

## Authorization and request ordering

Status semantics are:

- HTTP `401` for missing or invalid authentication;
- HTTP `403` for profile-level write ineligibility;
- HTTP `404` for missing or cross-owner IDs;
- HTTP `400` for closed-schema, name, or supported media-validation failures;
- HTTP `405` for unsupported methods;
- HTTP `5xx` for unexpected storage, database, URL-generation, or programming
  failures.

For every ID-based player operation, authenticate and resolve the record using
both `id` and `owner=request.user` before request-body parsing, validation,
media access, advisory locking, database row locking, or URL generation. This
owner-scoped `404` takes precedence over write eligibility so callers cannot
probe another owner's identifiers.

For creation, where no target identity exists to conceal, check eligibility
before multipart parsing. Every write repeats the same eligibility conditions
authoritatively in the short database commit transaction. The pre-check avoids
unnecessary parsing and media work; it is not the commit-time authority.

Client input never controls `id`, `owner`, `photo_url`, `photo_key`,
`is_enabled`, `created_at`, or `updated_at`.

## Media lifecycle and concurrency

Creation and replacement pass Django uploads directly to the approved #112
media service. Stable #112 client image-validation failures become sanitized
HTTP `400` errors under `photo`. Responses never expose Pillow exceptions,
source filenames or metadata, object keys, provider configuration, bucket
details, credentials, or presigned URLs other than the authorized response's
short-lived `photo_url`. Unexpected storage and programming failures remain on
the 5xx path.

Creation follows:

```text
cheap eligibility pre-check
  -> validate and normalize request/image
  -> store new object
  -> short transaction: lock PlayerProfile, recheck eligibility, create Fursuit
  -> return representation
```

If the database callback fails after upload, #112 attempts to delete the new
object and re-raises the original failure.

Same-fursuit photo replacements are serialized across the complete media
lifecycle by a PostgreSQL advisory lock in a fursuit-specific namespace. The
advisory lock is distinct from the profile-avatar user lock namespace. Do not
hold database row locks while performing storage operations.

Replacement follows:

```text
authenticate and owner-scope target
  -> cheap eligibility pre-check
  -> acquire namespaced per-fursuit advisory lock
  -> read the current authoritative photo key
  -> validate, normalize, and store new object
  -> short transaction: lock PlayerProfile, recheck eligibility,
       then lock Fursuit and commit new key + updated_at
  -> best-effort delete prior object
  -> release advisory lock
  -> return representation
```

All database transactions that need both rows acquire locks in the fixed order
`PlayerProfile` then `Fursuit`. If prior-object cleanup fails after commit, the
new database reference remains authoritative and #112 emits only its sanitized
warning. Cleanup failures can create one orphan for each affected operation;
without reconciliation, those bounded-per-operation orphans may accumulate
over the system's lifetime. General reconciliation is deferred.

Name updates use a short transaction with the same `PlayerProfile` then
`Fursuit` lock order, recheck eligibility, and write only when normalized state
actually changes.

## Implementation architecture

Use a dedicated domain-service architecture:

- the model owns persistence shape and database constraints;
- a fursuit normalization boundary applies the approved human-name policy;
- fursuit services own player-write eligibility rechecks, database lock
  ordering, persistence, timestamps, media lifecycle, and advisory
  serialization;
- views own authentication, owner-scoped lookup precedence, parser timing, and
  HTTP/domain error mapping;
- explicit request serializers and multipart inspection enforce closed schemas
  and cardinality;
- response construction owns ephemeral URL generation;
- the restricted admin form owns its one permitted mutation, `is_enabled`, and
  persists only that field plus `updated_at`.

Do not put storage side effects in model `save()`, model validation, signals, or
serializers. Do not introduce activation-oriented abstractions before #117
composes its own Convention, enrollment, ownership, and enabled-state rules.

## Operator administration

Django admin is inspection plus per-object global enable/disable only:

- disable add, delete, and bulk actions;
- display internal fursuit ID, owner TailTag application ID, name, enabled
  state, photo presence, and timestamps;
- permit editing only `is_enabled` on the object detail page;
- keep owner, name, photo, timestamps, and all media references read-only;
- expose a short-lived, on-demand photo link only on the object detail page;
- show only photo presence on list pages so list rendering generates no media
  URLs;
- never display or search Clerk identity, opaque media keys, credentials, or
  provider details.

An operator enable/disable change updates `updated_at`. Administration provides
no path to manually forge a media reference.

## OpenAPI contract

OpenAPI describes all and only the player routes, methods, authentication,
content types, closed request shapes, exact four-field response, required
multipart fields, and documented status classes in this specification. Schema
tests update the expected global path set as well as endpoint-local details.

The schema must not advertise deletion, owner mutation, client-controlled
enablement, nullable photos, pagination, archival, activation, sessions, QR
credentials, or opaque media keys.

## Acceptance evidence

PostgreSQL-backed automated evidence covers:

- model fields, named constraints, owner `PROTECT`, defaults, timestamps, and
  normalized no-op behavior;
- exact routes, methods, representations, ordering, statuses, and closed input
  schemas;
- authentication, profile eligibility, owner concealment, and request-ordering
  guarantees before parsing, validation, media, URL, or lock side effects;
- creation, replacement, commit compensation, cleanup failure, URL generation,
  and authoritative-reference behavior with deterministic media fakes;
- real PostgreSQL same-fursuit replacement concurrency, advisory namespace,
  and `PlayerProfile` then `Fursuit` database lock ordering;
- restricted admin inspection and enable/disable behavior;
- complete OpenAPI accuracy.

Do not add mutation-testing infrastructure. Independent test-adequacy review
must instead challenge the suite against explicit plausible mutants in
ownership filters, eligibility conditions, database constraints, lifecycle
ordering, advisory serialization, and compensating cleanup.

`make api-check` is the authoritative deterministic completion gate, including
formatting, linting, strict Pyright, Semgrep, PostgreSQL tests, Django checks,
migration drift, OpenAPI validation, and Gunicorn configuration. Issue #120,
not #115, owns live Railway composition of the authenticated participation
flow.

## Controlled-V0 limitations

Issue #115 deliberately introduces no:

- per-owner fursuit cap or aggregate storage quota;
- fursuit-specific throttling or cross-cutting idempotency protocol;
- orphan-object reconciliation;
- player or operator archival/deletion workflow;
- moderation history or approval queue.

Per-upload size, decoded-pixel, format, normalization, object-key, and access
safeguards remain those established by #112. An authenticated eligible player
can create an unbounded number of durable fursuits within this API contract, so
storage exhaustion must be reconsidered before broader untrusted rollout.

## Acceptance Contract

- [ ] A PostgreSQL-backed durable fursuit record uses TailTag ownership,
      required valid media, server timestamps, protected ownership, and
      operator-controlled enabled state.
- [ ] Eligible players can create, list, retrieve, rename, and replace the
      photo of only their own records through the exact closed HTTP contracts.
- [ ] Authenticated owners retain read access, and eligible owners can remediate
      names/photos, while a fursuit is globally disabled.
- [ ] Ownership, moderation state, opaque keys, and administrative metadata are
      immutable or absent from player input and representations as specified.
- [ ] Owner-scoped concealment and eligibility checks occur in the approved
      order without unauthorized parsing, media, URL, or locking side effects.
- [ ] Same-fursuit replacement serialization, database lock ordering,
      authoritative-reference semantics, and compensating cleanup are covered
      by deterministic and real-PostgreSQL evidence.
- [ ] Admin, OpenAPI, migration behavior, documentation, and `make api-check`
      enforce the complete contract.
- [ ] No deletion, archival, activation, catchability, QR behavior, quotas,
      fursuit-specific throttling, reconciliation, or other deferred mechanism
      is introduced.

## Unresolved decisions

None. Changes to this contract require explicit replanning before
implementation continues.
