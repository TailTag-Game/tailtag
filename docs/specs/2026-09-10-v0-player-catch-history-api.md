# V0 player catch-history API

**Issue:** [#177 — Implement V0 player collection and catch-history
APIs](https://github.com/TailTag-Game/tailtag/issues/177)

**Parent:** [#173 — Establish V0 catch creation and persistent
collections](https://github.com/TailTag-Game/tailtag/issues/173)

**Depends on:** [#176 — Expose the V0 catch confirmation
API](https://github.com/TailTag-Game/tailtag/issues/176)

**Status:** Approved public API contract, Acceptance Contract, Test Surface
Contract, and Scope Guard; frozen on 2026-09-10 before production
implementation

## Goal

Expose the authenticated TailTag application user's durable Catch history
through one private, read-only endpoint. The same Catch-derived resource supplies
the product's all-time and Convention-scoped collection views without creating a
second collection resource, read contract, model, or source of truth.

## Canonical resource and route

The sole player catch-history endpoint is:

```text
GET /api/catches/
```

It uses the repository-standard Bearer authentication and DRF
`IsAuthenticated` permission contract. No other method is supported on this
route. Catch confirmation remains solely at `POST /api/catches/confirm/` under
the approved #176 contract.

“Collection” is a product and UI interpretation of Catch history. There is no
`/collection/` route, mutable collection model, collection-entry table, or
second player read contract over the same Catch rows.

The request never accepts a player or catcher selector. It has no player path
parameter and no `user_id`, `catcher_id`, or equivalent query parameter. The
base queryset is always derived from the authenticated TailTag application
identity:

```python
Catch.objects.filter(catcher_user=request.user)
```

The optional Convention filter narrows that already owner-scoped queryset. It
never selects ownership or causes an authorization branch over a client-chosen
identity.

## Query contract

The endpoint accepts only these optional query parameters:

| Parameter | Contract |
| --- | --- |
| `convention_id` | One positive base-10 integer identifying an existing Convention |
| `page` | One positive base-10 integer; defaults to `1` |
| `page_size` | One positive base-10 integer no greater than `100`; defaults to `20` |

Each parameter may occur at most once. Unknown parameters, repeated parameters,
blank values, non-integers, zero, negative integers, and `page_size` values above
`100` return HTTP 400 using the closed validation response described below.
Integers with a leading `+` sign, surrounding whitespace, decimal points, or
exponents are malformed; accepted integer values contain ASCII digits only and
must be positive after parsing.

Without `convention_id`, the endpoint returns the authenticated player's
all-time history. With `convention_id`, it returns only that player's catches at
the identified Convention.

A syntactically valid positive Convention ID that does not identify an existing
Convention returns HTTP 404. Convention existence is evaluated independently of
the player's catches so that a nonexistent Convention and an existing Convention
with no matching catches remain distinguishable. An existing Convention requires
no enrollment, active-Convention, current lifecycle, or current eligibility
state to read historical catches.

An existing Convention with no matching Catch rows returns HTTP 200 with
`catch_count: 0` and an empty `results` array. A requested page beyond the
available page range returns HTTP 404 using the closed invalid-page response.
For an empty result set, the default or explicit first page is valid; later
pages are invalid.

Ordering is server-owned and exactly:

```python
("-caught_at", "-id")
```

The immutable Catch primary key is the deterministic secondary key when
timestamps collide. The API does not accept an ordering parameter.

## Successful response

Every HTTP 200 response uses this closed envelope:

```json
{
  "catch_count": 21,
  "next": "https://api.example.test/api/catches/?page=2",
  "previous": null,
  "results": [
    {
      "id": 123,
      "fursuit": {
        "id": 42,
        "name": "Example Character",
        "photo_url": "https://media.example.test/signed-read"
      },
      "convention": {
        "id": 7,
        "name": "Example Convention"
      },
      "caught_at": "2026-09-10T12:34:56Z"
    }
  ]
}
```

The envelope contains exactly:

- `catch_count`: a non-negative integer equal to the total number of Catch rows
  matching the current request scope before pagination;
- `next`: the URI of the next page or `null`;
- `previous`: the URI of the previous page or `null`; and
- `results`: the current page's ordered Catch entries.

For an unfiltered request, `catch_count` is the authenticated player's all-time
Catch count. For a Convention-filtered request, it is that player's Catch count
for the selected Convention. It is never the current page length. V0 exposes no
separate all-time count on a filtered request and no caught/total denominator.

Each Catch entry contains exactly:

- `id`: the immutable Catch primary key;
- `fursuit.id`: the fursuit primary key;
- `fursuit.name`: the fursuit name;
- `fursuit.photo_url`: a fresh player-authorized read URL;
- `convention.id`: the Convention primary key;
- `convention.name`: the Convention name; and
- `caught_at`: the server-recorded Catch timestamp serialized as an RFC 3339 UTC
  date-time using the repository's existing API convention.

The response does not expose catcher or owner identity, Clerk/provider data,
activation or session provenance, credentials, fursuit enablement or ownership,
Convention lifecycle or configuration, enrollment or eligibility, operator
metadata, unrelated timestamps, progression, rarity, or denominator data.

Pagination links retain the accepted request scope and page size, are generated
through the repository/DRF request boundary, and contain no player selector or
sensitive data. `next` and `previous` are response metadata, not an authorization
input; every linked request repeats authentication and reconstructs the
owner-scoped queryset.

## Validation and error responses

Authentication failures retain the repository-standard closed HTTP 401
response:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Invalid query input returns HTTP 400 with this closed shape:

```json
{
  "code": "invalid_query",
  "detail": "The catch-history query is invalid."
}
```

The response deliberately does not echo attacker-controlled parameter names or
values. Unknown, repeated, or malformed query parameters are publicly collapsed
to the same response.

A syntactically valid but nonexistent Convention returns HTTP 404:

```json
{
  "code": "convention_not_found",
  "detail": "The convention was not found."
}
```

An out-of-range page returns HTTP 404:

```json
{
  "code": "invalid_page",
  "detail": "The requested page does not exist."
}
```

Unexpected query, serialization, media-signing, or response-construction
failures return only the repository's sanitized HTTP 500 response:

```json
{
  "code": "server_error",
  "detail": "An unexpected error occurred."
}
```

Unexpected-failure logging may include a fixed stage discriminator but must not
include exception text, presigned URLs, signatures, media object keys, Catch or
related-object identifiers, user identity, query values, or response content.

## Fursuit photo boundary

Every Catch entry has a non-null `fursuit.photo_url`. The projection passes the
durable `Fursuit.photo_key` to the existing `media.service.read_image_url`
boundary and exposes only the returned player-authorized read URL. Production
storage continues to provide a fresh short-lived signed read URL under the
approved V0 media contract.

Issue #177 does not add absent-photo or nullable-photo behavior. A media-signing
failure is an unexpected sanitized HTTP 500 failure for the entire request; the
API does not return a partial page, substitute `null`, omit the field, reveal the
object key, or fall back to a public media URL.

Tests replace only the approved media-service boundary with deterministic fake
URLs. They assert invocation with the expected durable photo key and never
generate, log, snapshot, or retain real expiring URL contents, signatures,
storage keys, or equivalent bearer material.

## Query and pagination design

The view constructs a direct Catch queryset equivalent to:

```python
Catch.objects.filter(catcher_user=request.user).select_related(
    "fursuit", "convention"
).order_by("-caught_at", "-id")
```

When present, `convention_id` adds a `convention_id=<validated id>` predicate to
this owner-scoped queryset. Convention existence is checked separately before
pagination. The implementation must not use client assertions, enrollment,
active-Convention state, fursuit ownership, activation/session state, or the
catch-confirmation service as read authority.

Use a focused DRF `PageNumberPagination` subclass with:

```python
page_size = 20
page_query_param = "page"
page_size_query_param = "page_size"
max_page_size = 100
```

Strict query validation occurs before pagination so invalid and over-maximum
values are rejected rather than silently ignored or clamped. The paginator's
count supplies `catch_count`; no second aggregate count query is introduced.
The paginator returns the frozen `catch_count`, `next`, `previous`, `results`
envelope rather than DRF's default `count` field name.

Database query count must not grow with page occupancy. Eager loading supplies
the fursuit and Convention fields for every row without per-row lookups. Signed
photo URL generation is outside the database query count. Deterministic tests
compare otherwise equivalent one-entry and full 20-entry pages and require the
same database query count while forcing authentication and replacing media URL
generation with a non-database fake.

No new database index or migration is authorized by this issue. The owner and
Convention foreign-key indexes, canonical Catch uniqueness constraint, and
model ordering established by #174 are the approved starting point. Evidence of
a genuinely inadequate query plan is a replan trigger, not authorization to add
an index silently.

## OpenAPI contract

Generated OpenAPI documents exactly one Bearer-authenticated `GET` operation at
`/api/catches/` and preserves the separate #176 `POST` operation at
`/api/catches/confirm/`.

The operation documents:

- the optional integer `convention_id`, `page`, and `page_size` query parameters
  with their positivity, uniqueness, defaults, and maximum constraints;
- newest-first server-owned ordering by `caught_at` then `id`;
- the exact closed HTTP 200 envelope and nested Catch, fursuit, and Convention
  objects;
- nullable URI schemas for `next` and `previous`;
- the distinction between `catch_count` and page length;
- HTTP 400 `invalid_query`;
- repository-standard HTTP 401 authentication failure;
- HTTP 404 `convention_not_found` and `invalid_page` outcomes;
- HTTP 500 `server_error` for sanitized unexpected failures, including media
  signing; and
- the privacy boundary and absence of client-selectable player identity.

Every response object and nested object sets `additionalProperties: false` and
lists its exact required fields. The operation has no request body, ordering
parameter, player/catcher parameter, public alternative, mutation method, or
denominator field. OpenAPI must not contain a `/collection/` path or another
catch-history read route.

## Acceptance Contract

- **AC-01 — Canonical private route:** `GET /api/catches/` is the sole
  authenticated player Catch-history read contract; no `/collection/` or second
  read resource is introduced.
- **AC-02 — Ownership by construction:** The base queryset is derived solely
  from the authenticated TailTag application user and accepts no player,
  catcher, owner, or provider-identity selector.
- **AC-03 — All-time history:** An unfiltered request returns only the
  authenticated player's Catch rows and reports their total as `catch_count`.
- **AC-04 — Convention history:** A validated `convention_id` only narrows the
  owner-scoped query and `catch_count` reports the total matching rows for that
  Convention.
- **AC-05 — Convention distinction:** A nonexistent Convention returns the
  frozen 404 response; an existing Convention with no matching catches returns
  HTTP 200, `catch_count: 0`, and `results: []`.
- **AC-06 — Closed query:** Only one each of `convention_id`, `page`, and
  `page_size` is accepted under the exact syntax and bounds above; all malformed,
  repeated, unknown, or over-maximum input returns the same sanitized closed 400
  response.
- **AC-07 — Deterministic order:** Results are always ordered by
  `-caught_at, -id`; equal timestamps use the immutable Catch ID tie-breaker and
  clients cannot choose ordering.
- **AC-08 — Bounded pagination:** Page-number pagination defaults to 20 entries,
  permits an explicit maximum of 100, reports matching-row total rather than page
  length, produces scoped next/previous links, and returns the frozen invalid-page
  404 for an out-of-range page.
- **AC-09 — Exact safe projection:** Each result contains exactly Catch `id`,
  nested fursuit `id`, `name`, and `photo_url`, nested Convention `id` and `name`,
  and server-recorded `caught_at`.
- **AC-10 — No sensitive or expanded context:** Responses expose no
  catcher/owner/provider identity, credential/session/activation data, lifecycle,
  configuration, eligibility, operator, progression, rarity, social, analytics,
  unrelated timestamp, or denominator fields.
- **AC-11 — Private media:** Every result obtains a fresh non-null photo URL
  through the existing media read boundary; signing failure fails the whole
  request through the sanitized 500 path without exposing bearer or storage
  material.
- **AC-12 — Query performance:** Fursuit and Convention data are eager-loaded,
  and deterministic query-count evidence proves database query count does not
  grow between otherwise equivalent one-entry and 20-entry pages.
- **AC-13 — OpenAPI completeness:** OpenAPI exactly describes the route,
  authentication, parameters, ordering, closed schemas, pagination/count
  semantics, success, every supported error, private-media failure behavior, and
  privacy boundary.
- **AC-14 — Read-only source of truth:** All counts and entries derive directly
  from durable Catch rows; no persistence, deletion, catch authority, mutable
  collection state, public/social history, or excluded V0/V1 surface is added.
- **AC-15 — Existing behavior preservation:** The implementation does not alter
  #176 catch confirmation, #175 catch creation, the Catch persistence contract,
  or existing fursuit/media/Convention API behavior.

## Test Surface Contract

Tests may use DRF's test client/request factory, repository authentication
helpers, the public URL, generated OpenAPI, the public Django model/ORM surface,
and existing account, Catch, fursuit, Convention, activation, and catch-session
fixtures or support helpers.

Tests may force-authenticate a TailTag application user where isolating query
behavior from Clerk authentication is necessary. They may use privileged
`QuerySet.update()` to arrange equal or ordered historical `caught_at` values,
consistent with the #174 testing contract. They may replace only
`catches.serializers.media_service.read_image_url` (or the final module-local
import path selected by the implementation) with a deterministic non-database
fake and inspect its call arguments.

The approved deterministic API tests cover:

- unauthenticated rejection and repository Bearer semantics (AC-01);
- absence of another read route or supported mutation method (AC-01, AC-14);
- all-time own-player isolation with interleaved other-player catches (AC-02,
  AC-03);
- rejection of player/catcher/owner/provider selectors as unknown query input
  (AC-02, AC-06);
- Convention-scoped isolation and matching-scope count (AC-04);
- nonexistent versus existing-empty Convention behavior (AC-05);
- every class of invalid, repeated, unknown, and over-maximum query input
  collapsed to the exact 400 response (AC-06);
- newest-first ordering plus equal-timestamp descending-ID tie-breaking (AC-07);
- default 20, explicit smaller pages, explicit 100 maximum, next/previous links,
  stable multi-page results, total-count semantics, empty first page, and
  out-of-range-page behavior (AC-08);
- exact entry and envelope keys, types, nesting, UTC timestamps, and forbidden
  field absence (AC-09, AC-10);
- deterministic photo URL projection, one signing call per result with the
  expected key, and sanitized fail-closed behavior without secret-bearing logs
  or partial output (AC-11);
- equal database query counts for one-entry and 20-entry first pages, with
  explicit proof that related fields are accessed during serialization (AC-12);
- exact OpenAPI path, method, security, parameters, bounds/defaults, response
  statuses, closed schemas, field sets, required/nullability/format metadata,
  descriptions, and absence of alternate routes or selectors (AC-13); and
- unchanged confirmation route behavior plus absence of model, migration,
  service, dependency, or settings changes (AC-14, AC-15).

Query-count assertions measure only the database work owned by the catch-history
read after authentication has been isolated. They compare occupancy rather than
freeze a framework-internal absolute count. The test must fail if either fursuit
or Convention eager loading is removed.

Tests must not mock Catch queryset results, replace pagination internals, mock
fursuit or Convention property access, add production-only test seams, assert
real presigned URL contents, or alter approved #174–#176 tests to accommodate the
implementation. Passing tests may not authorize model, migration, service,
dependency, settings, admin, or unrelated refactoring changes.

### Acceptance-test traceability

Every new or materially changed test must map to at least one AC item or the
selected SECURITY or TEST ADEQUACY assurance modifier. Tests outside this table
require replanning rather than silently expanding scope.

| Test area | Approved source |
| --- | --- |
| Route, authentication, method closure | AC-01, SECURITY |
| Owner-only queryset and forbidden identity selectors | AC-02, SECURITY |
| All-time entries and count | AC-03 |
| Convention-filtered entries and count | AC-04 |
| Missing versus existing-empty Convention | AC-05 |
| Strict query syntax, multiplicity, names, and bounds | AC-06, SECURITY |
| Ordering and timestamp collision | AC-07, TEST ADEQUACY |
| Page sizes, links, total, empty, and invalid page | AC-08 |
| Exact projection and envelope | AC-09 |
| Sensitive and excluded field absence | AC-10, SECURITY |
| Signed-media boundary and sanitized failure | AC-11, SECURITY |
| Occupancy-independent database query count | AC-12, TEST ADEQUACY |
| Generated OpenAPI contract | AC-13 |
| Read-only/source-of-truth and regression boundaries | AC-14, AC-15 |

## Scope Guard

**Outcome:** One authenticated, closed, paginated `GET /api/catches/` endpoint
projects the current player's all-time or Convention-scoped durable Catch
history with matching count, deterministic ordering, safe context, and private
photo access.

**Non-goals:** Catch persistence or write behavior; mutable collection entries;
catch deletion; public or other-player history; credentials or session authority;
admin/correction; Flutter UI; XP/progression; achievements; rarity; leaderboards;
social surfaces; denominator calculations; analytics infrastructure; new indexes
or migrations; dependencies; and unrelated cleanup.

**Expected production change surface:** Focused additions to
`services/api/catches/serializers.py`, `services/api/catches/views.py`, and
`services/api/catches/urls.py`. A focused pagination module may be added under
`services/api/catches/` if keeping query validation and envelope behavior out of
the view materially improves cohesion. No model, migration, service,
configuration, dependency, Convention, fursuit, media, authentication, or
settings change is authorized.

**Expected test change surface:** New focused catch-history API and OpenAPI test
modules under `services/api/tests/`, reusing existing support. Existing catch
test support may receive only the smallest fixture helper needed to remove
duplication. No new general test infrastructure is authorized.

**Proof:** Acceptance-first tests mapped to AC-01 through AC-15; focused API,
OpenAPI, query-count, and regression checks; repository `make api-check`
including Semgrep; explicit privacy and plausible-mutant analysis; one fresh
independent review covering specification, correctness, test adequacy, security,
and scope; and parent authoritative verification.

## Replan triggers

Stop and replan if implementation requires changing this public contract, the
approved #174–#176 semantics, a model or migration, an index, a dependency,
settings, global DRF pagination or exception behavior, the existing V0 media
contract, or another subsystem. Also replan if deterministic evidence shows the
approved direct indexed query cannot meet the occupancy-independent query
contract without broader persistence work.
