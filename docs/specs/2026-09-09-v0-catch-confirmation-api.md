# V0 catch confirmation API

**Issue:** [#176 — Expose the V0 catch confirmation API](https://github.com/TailTag-Game/tailtag/issues/176)

**Parent:** [#173 — Establish V0 catch creation and persistent collections](https://github.com/TailTag-Game/tailtag/issues/173)

**Depends on:** [#175 — Implement authoritative V0 catch validation and creation](https://github.com/TailTag-Game/tailtag/issues/175)

**Status:** Approved public API contract, Acceptance Contract, Test Surface Contract,
and Scope Guard; frozen on 2026-09-09 before production implementation

## Goal

Expose the sole authoritative catch-write service through one authenticated,
closed, privacy-preserving HTTP endpoint. The API validates only the request
structure, delegates the original opaque payload to `catches.services.confirm_catch`,
and projects the returned canonical Catch without adding another source of catch
authority.

## Route, authentication, and request

The endpoint is:

```text
POST /api/catches/confirm/
```

It uses the repository-standard Bearer authentication and DRF
`IsAuthenticated` permission contract. It accepts JSON only. Its request body is
exactly:

```json
{
  "payload": "<opaque Convention-scoped credential>"
}
```

The public field is named `payload`, matching credential issuance and preview
resolution. Do not introduce `credential`, `token`, `credential_payload`, or any
internal identifier.

The request object is closed. Missing fields, extra fields, non-string payloads,
malformed credential payloads, malformed JSON, and unsupported media types return
HTTP 400 using the existing credential-resolution validation shape:

```json
{
  "payload": ["Invalid catch credential payload."]
}
```

The API may perform only structural and credential-grammar validation. It must
pass the authenticated TailTag application user and original opaque payload
directly to:

```python
confirm_catch(user, *, payload=payload)
```

The API must not resolve or decide catch authority, eligibility, ownership,
active Convention state, credential lifecycle, duplicate state, or persistence.

## Successful outcomes

Both service outcomes use one closed response schema with an explicit outcome
discriminator:

- `CatchConfirmationStatus.CREATED` returns HTTP 201 and `outcome: "created"`.
- `CatchConfirmationStatus.ALREADY_CAUGHT` returns HTTP 200 and
  `outcome: "already_caught"`.

The exact response fields are:

```json
{
  "outcome": "created",
  "catch": {
    "id": 123,
    "caught_at": "2026-09-09T16:00:00Z",
    "convention_id": 42,
    "fursuit": {
      "tailtag_id": "00000000-0000-0000-0000-000000000000",
      "name": "Example",
      "photo_url": "https://api.example.test/api/media/images/example"
    }
  }
}
```

The public Catch projection contains exactly:

- `id`;
- `caught_at`;
- `convention_id`;
- `fursuit.tailtag_id`;
- `fursuit.name`; and
- `fursuit.photo_url`.

This extends the approved safe credential-preview projection only with the
durable Catch identity and server-owned catch timestamp. The API serializes the
canonical Catch returned by the service. For `ALREADY_CAUGHT`, it preserves the
existing Catch ID, `caught_at`, and all durable state without mutation.

The response must not expose catcher/user IDs, owner IDs, internal fursuit IDs,
activation IDs, catch-session IDs, credential row IDs, raw credentials or
tokens, activation/session lifecycle details, target eligibility or moderation
state, ownership relationships, or other database/internal provenance.

## Error contract

Serializer and DRF authentication errors retain their existing repository
envelopes. This issue does not globally replace those envelopes.

Catch-domain errors that carry a stable machine code use this closed shape:

```json
{
  "code": "<stable_machine_code>",
  "detail": "<sanitized human-readable message>"
}
```

The object has `additionalProperties: false`. The exact mappings are:

| Condition | HTTP | Code | Detail |
| --- | ---: | --- | --- |
| Closed-request, malformed payload, malformed JSON, or unsupported media type | 400 | Existing `payload` field validation | `Invalid catch credential payload.` |
| Unauthenticated request or `CatchAuthenticationError` | 401 | Existing authentication envelope | Repository-standard sanitized authentication detail |
| `CatchParticipationIneligibleError` | 403 | `catcher_ineligible` | `You are not eligible to catch this target.` |
| `CatchActiveConventionMismatchError` | 409 | `active_convention_mismatch` | `Your active convention does not match the catch target.` |
| `CatchSelfCatchError` | 409 | `self_catch_not_allowed` | `You cannot catch your own fursuit.` |
| `CatchTargetInvalidError` | 404 | `catch_target_unavailable` | `The catch target is unavailable.` |
| Unexpected or unmapped exception | 500 | `server_error` | `An unexpected error occurred.` |

`CatchTargetInvalidError` is intentionally collapsed. Unknown, revoked, stale,
stopped, expired, disabled, ineligible, or otherwise invalid target conditions
must have identical HTTP status, code, response schema, and detail. The response
must not differ based on whether preview previously succeeded.

The actionable catcher-owned outcomes `catcher_ineligible`,
`active_convention_mismatch`, and `self_catch_not_allowed` may remain distinct.

Unexpected failures return only:

```json
{
  "code": "server_error",
  "detail": "An unexpected error occurred."
}
```

They must not expose exception names, tracebacks, database errors, constraint
names, credential values, internal IDs, or domain diagnostics. Repository-standard
server-side exception logging may continue, but raw credential payloads must not
be emitted to logs, tracing, metrics, screenshots, test diagnostics, or durable
evidence.

## OpenAPI contract

OpenAPI documents the route, Bearer security, exact closed request, HTTP 201 and
200 success outcomes, HTTP 400/401/403/404/409/500 errors, and exact closed
success and domain-error schemas. The success outcome enum is exactly
`created | already_caught`. The 201 and 200 responses reference the same reusable
success schema. The 404 documentation states that target-unavailable conditions
are deliberately privacy-collapsed.

## Acceptance Contract

- **AC-01 — Route and authentication:** `POST /api/catches/confirm/` uses the
  repository Bearer authentication and `IsAuthenticated` contract.
- **AC-02 — JSON-only closed input:** The endpoint accepts only JSON containing
  exactly one string field named `payload` and rejects missing, extra, renamed,
  non-string, malformed, malformed-JSON, and unsupported-media inputs with the
  existing sanitized `payload` validation shape.
- **AC-03 — Delegation boundary:** The API passes the exact authenticated TailTag
  user and original opaque payload to `confirm_catch(user, *, payload=...)` and
  contains no catch authority, eligibility, ownership, Convention, credential
  lifecycle, duplicate, or persistence logic.
- **AC-04 — Created outcome:** `CREATED` maps to HTTP 201 and `outcome: "created"`.
- **AC-05 — Already-caught outcome:** `ALREADY_CAUGHT` maps to HTTP 200 and
  `outcome: "already_caught"`, using the canonical existing Catch unchanged.
- **AC-06 — One safe success schema:** Both outcomes use the same closed schema
  containing exactly `outcome` and the approved Catch projection.
- **AC-07 — Durable retry identity:** An already-caught response preserves the
  existing Catch `id` and original `caught_at` and performs no mutation.
- **AC-08 — No sensitive success fields:** The projection contains no internal
  provenance, owner/catcher/provider identity, credential data, lifecycle data,
  moderation state, or ownership relationships.
- **AC-09 — Typed error mapping:** Every approved service exception maps to the
  frozen HTTP status, code/envelope, and sanitized detail.
- **AC-10 — Target privacy collapse:** Every service condition represented by
  `CatchTargetInvalidError` is publicly indistinguishable and returns HTTP 404,
  `catch_target_unavailable`, and `The catch target is unavailable.`
- **AC-11 — Unexpected failure sanitization:** Every unexpected/unmapped failure
  returns only the closed HTTP 500 `server_error` response and never exposes
  diagnostics or raw credentials.
- **AC-12 — OpenAPI completeness:** OpenAPI includes the full closed route,
  security, request, shared success, error, enum, and privacy-collapse contract.
- **AC-13 — No upstream semantic change:** The implementation does not alter the
  approved #175 service semantics or a frozen Wave 2 invariant.

## Test Surface Contract

API tests may use DRF's test client/request factory, repository authentication
helpers, the public URL, the generated OpenAPI document, existing Catch/fursuit
fixtures, and mocks applied only at `catches.views.confirm_catch` to control the
approved service boundary. Tests may inspect mock call arguments to prove exact
delegation and may query the Catch returned by the service to prove retry
identity and lack of mutation.

Tests must not mock or assert internal #175 validation/transaction helpers, add a
production seam solely for tests, or require serializers/views/permissions to
reimplement service decisions. Target-condition API cases should parameterize
the single public `CatchTargetInvalidError` result; #175's service tests remain
the authority proving which underlying conditions produce that exception.

Tests map to AC-01 through AC-13 and cover authentication, JSON-only handling,
request closure, malformed-payload concealment, exact delegation, both success
statuses, shared projection, retry preservation, sensitive-field absence, every
typed error, target collapse, unexpected sanitization, raw-payload absence, and
OpenAPI completeness.

## Scope Guard

**Outcome:** One authenticated, closed, documented HTTP endpoint safely exposes
the canonical #175 catch-confirmation service and nothing else.

**Non-goals:** Catch validation or persistence; duplicate logic; credential
resolution authority; changes to #175 or Wave 2 semantics; collection/history
reads; Catch admin/correction; Flutter UI; generic idempotency; global DRF error
envelope changes; dependencies; migrations; and unrelated cleanup.

**Expected production change surface:** New focused `catches` API serializer/
projection and view/URL modules, registration under `config.urls`, and no model,
migration, service, convention, authentication, dependency, or settings change.

**Expected test change surface:** Focused catch-confirmation API and OpenAPI
tests, reusing existing repository test support. No new general test
infrastructure is authorized.

**Proof:** Acceptance-first tests mapped to AC-01 through AC-13; narrow tests
first; repository `make api-check` including Semgrep; explicit privacy and
plausible-mutant analysis; independent specification/code/test/security review;
and parent authoritative verification.

## Replan trigger

Stop and replan if implementation would require changing the approved #175
service semantics, a frozen Wave 2 invariant, a public contract above, an
unapproved dependency, a model or migration, or another subsystem.
