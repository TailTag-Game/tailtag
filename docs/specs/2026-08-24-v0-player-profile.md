# V0 player onboarding and profile

**Issue:** [#113 — Implement V0 player onboarding and profile](https://github.com/TailTag-Game/tailtag/issues/113)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved for implementation

## Goal

Add TailTag's V0 player-facing profile and lightweight onboarding state without
changing the established Clerk authentication boundary, canonical TailTag
application identity, or `/api/me/` identity-proof contract.

At completion, an authenticated player can inspect their conceptual profile,
atomically complete onboarding with a handle and display name, edit those
fields after onboarding, and independently upload, replace, or remove an
optional avatar. Operators can inspect safe profile state and enable or disable
product eligibility. Later participation domains can reuse one fail-closed
eligibility predicate.

## Existing contracts

- Clerk remains the external player-authentication authority.
- `accounts.User.id` remains the canonical TailTag application identity and the
  only identity downstream domain relationships use.
- `accounts.User` remains an identity model. This issue adds no product-profile
  fields to it and copies no profile data from Clerk.
- `GET /api/me/` remains exactly the existing authenticated identity proof. It
  continues to return only `{"id": <TailTag application user ID>}`.
- The approved #97 Clerk identity resolver remains unchanged and does not
  provision or repair profile state.
- The approved #112 media module remains the sole image validation, storage,
  key, read-access, replacement, and removal implementation.
- `/api/` remains the unversioned V0 product namespace.

## Terminology and identity

`handle` is TailTag's unique mutable product identifier. Do not use `username`
as the product or HTTP field name. A handle is presentation and lookup data,
not ownership or authorization identity. Renaming a handle must not change any
TailTag ownership or downstream relationship.

`display_name` is the mutable human-facing name. It is not unique and is not an
identity or authorization input.

`PlayerProfile` is TailTag-owned product state associated one-to-one with an
`accounts.User`. It has no independent client-facing ID. The relationship to
the application user is the profile table's primary key so persistence does
not create a second profile identity.

## Profile model

Create a dedicated `profiles` Django application with a `PlayerProfile` model:

| Field | Persistence contract |
| --- | --- |
| `user` | `OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=CASCADE)` |
| `handle` | Nullable `CharField(max_length=32)` with the database uniqueness constraint `profiles_player_profile_handle_unique` |
| `display_name` | Nullable `CharField(max_length=50)` |
| `avatar_key` | Nullable opaque media object key; never an URL |
| `onboarding_completed_at` | Nullable server-controlled timestamp |
| `is_enabled` | Required boolean, default `True` |

The database must enforce the one-to-one relationship and globally unique
persisted handle. The named
`profiles_player_profile_handle_format` check constraint accepts a null handle
or the exact canonical `^[a-z0-9][a-z0-9_]{1,31}$` form. The named
`profiles_player_profile_onboarding_state_consistent` check constraint accepts
only these text-lifecycle combinations:

- `handle`, `display_name`, and `onboarding_completed_at` are all null; or
- `handle`, `display_name`, and `onboarding_completed_at` are all non-null,
  with `display_name` nonempty.

Application validation remains responsible for normalization, reserved
handles, friendly field errors, and all other product rules.

The incomplete persisted state has `handle`, `display_name`, and
`onboarding_completed_at` all null. A successful initial onboarding write sets
both normalized text fields and `onboarding_completed_at` atomically. Ordinary
product operations cannot stage only one required field.

`onboarding_completed_at` is monotonic and server-controlled. Once non-null,
ordinary profile operations cannot clear it or replace its original value.
The timestamp is not exposed through HTTP. The response field
`onboarding_complete` is the derived boolean
`onboarding_completed_at is not null`.

## Conceptual state and lazy materialization

Every TailTag application user has exactly one conceptual product-profile
state. Before any profile mutation, the default state is:

```json
{
  "handle": null,
  "display_name": null,
  "avatar_url": null,
  "onboarding_complete": false,
  "is_enabled": true
}
```

The `profiles` module may idempotently create the default `PlayerProfile` row
when the authenticated user first accesses the profile surface. In particular,
`GET /api/profile/` may perform this internal materialization. It creates no
product-visible state transition: the representation immediately before and
after materialization is the same incomplete, enabled profile.

Do not add profile creation to authentication, Clerk identity resolution, or
`accounts.User` creation. A TailTag user who has never used the profile surface
may have no physical profile row and therefore may not appear in profile
administration.

Client profile operations use a profiles-owned, concurrency-safe, idempotent
acquisition function. The one-to-one database constraint is authoritative when
simultaneous first accesses attempt to materialize the same default row.

Participation eligibility must use a separate non-creating lookup. It must
never materialize, repair, or infer successful onboarding from a missing or
inconsistent row. Missing, incomplete, disabled, or inconsistent state is
ineligible.

## Handle contract

The HTTP and product field name is exactly `handle`.

- Normalize to lowercase before validation and persistence.
- The normalized value is 2 through 32 ASCII characters.
- Allowed characters are lowercase `a` through `z`, digits `0` through `9`,
  and underscore (`_`).
- The first character must be a letter or digit.
- Whitespace is never valid.
- Handles are globally unique and mutable after onboarding.
- Reserve exactly these V0 handles: `admin`, `api`, `me`, `moderator`, `staff`,
  `support`, `system`, and `tailtag`.
- Do not add profanity filtering, moderation infrastructure, cooldowns, rename
  history, aliases, or public handle lookup in this issue.

Use the stable `profiles_player_profile_handle_unique` database constraint for
handle uniqueness. Both ordinary duplicate validation and a concurrent
database uniqueness race return the same safe DRF `handle` field validation
error with the `unique` code.

When classifying an `IntegrityError`, translate only PostgreSQL SQLSTATE `23505`
whose structured diagnostic constraint name exactly matches the known profile
handle uniqueness constraint. Do not inspect error prose. Unrelated unique,
check, foreign-key, schema, programming, and unclassified integrity failures
must remain on their ordinary server-error path and must never be reported as
duplicate handles.

## Display-name contract

`display_name` is required to complete onboarding and remains mutable after
completion.

Normalize and validate in this order:

1. Normalize Unicode to NFC.
2. Reject Unicode control characters in general category `Cc` and Unicode line
   or paragraph separators in categories `Zl` and `Zp`.
3. Trim leading and trailing whitespace.
4. Collapse each remaining run of Unicode whitespace to one ordinary ASCII
   space.
5. Require 1 through 50 Unicode code points in the resulting value.

The result is single-line, nonempty, and not unique. Do not add profanity
filtering or broader display-name moderation in this issue.

## Onboarding lifecycle

V0 onboarding requires one valid `handle` and one valid `display_name`. Avatar
state does not gate onboarding.

Initial onboarding is one atomic `PUT /api/profile/` operation. A successful
write automatically sets `onboarding_completed_at`; there is no separate
complete action. A validation or persistence failure leaves the prior
conceptual state unchanged.

Completion is irreversible. After completion, handle and display name remain
editable but cannot be cleared, made invalid, or returned to an incomplete
state. `PUT` remains available as a complete replacement of the two mutable
text fields, and `PATCH` supports partial text-field updates after completion.
`PATCH` before completion fails with normal DRF validation and directs the
client to supply the complete onboarding representation through `PUT`.

## Product eligibility

`is_enabled` is TailTag-owned product eligibility. It is separate from Clerk
authentication state and Django's `is_staff` and `is_superuser` flags. New
materialized profiles default to enabled.

A disabled player:

- may authenticate;
- may call `GET /api/me/`;
- may call `GET /api/profile/`;
- may not mutate text profile or avatar state; and
- may not perform later gameplay or participation writes.

Operations requiring an enabled player return HTTP `403`. Disabling does not
delete or rewrite durable profile, enrollment, fursuit, or future gameplay
records. Re-enabling restores eligibility without reconstructing those records.

Expose
`profiles.eligibility.is_participation_eligible(user: User | AnonymousUser) -> bool`
as the reusable downstream predicate with this exact meaning:

```text
authenticated
AND onboarding_complete
AND is_enabled
```

The predicate performs a non-creating query and returns false for anonymous
users, missing profile rows, incomplete onboarding, disabled profiles, or
inconsistent profile state. Later domains may add their own requirements on top
of it.

## Profile HTTP interface

All profile routes explicitly require TailTag authentication through the
existing DRF authentication implementation. They operate only on
`request.user` and accept no user or owner identifier.

```text
GET   /api/profile/
PUT   /api/profile/
PATCH /api/profile/

PUT    /api/profile/avatar/
DELETE /api/profile/avatar/
```

Successful profile GET, PUT, PATCH, and avatar PUT responses contain exactly:

```json
{
  "handle": "finnthepanther",
  "display_name": "Finn",
  "avatar_url": "https://media.example.test/presigned-read",
  "onboarding_complete": true,
  "is_enabled": true
}
```

Before onboarding, `handle` and `display_name` remain null and
`onboarding_complete` remains false. `avatar_url` reflects any independently
uploaded pre-onboarding avatar, and `is_enabled` reflects any operator change;
those fields are not forced back to their untouched defaults. There is no
`id`, profile ID, Clerk ID, provider field, administrative field, timestamp,
or opaque object key in the response.

`onboarding_complete` and `is_enabled` are read-only to ordinary player
requests. Supplying them must not grant lifecycle or eligibility control.

### GET `/api/profile/`

Return HTTP `200` with the complete five-field representation. This operation
is allowed for enabled and disabled players. It may idempotently materialize the
default row without changing the observable conceptual state.

### PUT `/api/profile/`

Own the complete mutable **text-profile** representation. The request requires
both `handle` and `display_name`. Before completion it atomically completes
onboarding; after completion it replaces both mutable text fields while
preserving the original completion timestamp.

PUT intentionally does not replace, remove, or require the independently
managed avatar. Its successful response is HTTP `200` with the complete
five-field profile representation, including current avatar state.

### PATCH `/api/profile/`

After onboarding, accept one or both of `handle` and `display_name`, normalize
and validate the resulting complete text state, and preserve the original
completion timestamp and avatar. An empty patch or a patch before onboarding
fails with normal DRF validation. A successful response is HTTP `200` with the
complete five-field representation.

### Authentication, authorization, and validation errors

- Missing or invalid authentication uses the existing HTTP `401` Bearer
  challenge contract.
- Disabled-player mutations return HTTP `403` without changing state.
- Invalid fields, reserved or duplicate handles, invalid display names, and
  invalid avatar content use normal stable DRF field-validation responses with
  HTTP `400`.
- Do not add a TailTag-wide error envelope or freeze unrelated English error
  prose in this issue.

## Avatar HTTP interface

Avatar operations are authenticated profile mutations and require an enabled
profile. They are allowed before or after onboarding. Performing them neither
completes onboarding nor changes participation eligibility.

### PUT `/api/profile/avatar/`

Accept only `multipart/form-data` with one file field named `avatar`:

```text
avatar=<file>
```

Pass the Django upload directly to the approved #112 media interface. Persist
only the returned opaque object key. Use #112's replacement order exactly:

```text
validate and normalize
  -> upload new object
  -> synchronously commit new profile reference
  -> best-effort delete prior object
```

Do not place an outer transaction around the media replacement call if it would
delay committing the database reference until after old-object cleanup. The
callback supplied to the media module must synchronously commit the new
reference as required by #112.

Map #112's stable `ImageValidationError` classifications to safe `avatar` field
validation errors with HTTP `400`. Do not expose Pillow, storage, object-key,
provider, bucket, credential, or presigned-URL details.

A successful upload returns HTTP `200` with the complete five-field profile
representation and a newly generated read URL.

### DELETE `/api/profile/avatar/`

Use #112's optional-removal order exactly:

```text
synchronously commit absent profile reference
  -> best-effort delete prior object
```

Removal is idempotent when no avatar exists. It neither changes onboarding nor
other text state. Success returns HTTP `204` with no response body.

### Avatar reads

Store only `avatar_key`. Whenever a profile response has an avatar, generate a
fresh authorized read URL through `media.service.read_image_url`. The production
adapter produces a 600-second presigned GET URL. Never persist or log generated
URLs, and do not render one in Django admin.

## Administration

Register a separate `PlayerProfile` administration surface. An operator for
this issue is a Django staff user with the normal `view_playerprofile` or
`change_playerprofile` model permission required by the requested admin action;
Django superusers retain their standard permission override. Do not broaden or
make the existing `accounts.User` administration mutable.

Operators may inspect:

- TailTag application user ID;
- handle;
- display name;
- derived onboarding state;
- enabled state; and
- avatar presence as a boolean.

Only `is_enabled` is editable. Prohibit profile add and delete operations,
bulk-disable actions, player-field editing, avatar upload/removal, and presigned
avatar generation. Do not expose Clerk identifiers, provider/session data,
opaque avatar keys, or credential material through profile administration.
Django's normal per-object admin change log is sufficient; add no suspension
reason or custom audit-history domain.

## Module design

The dedicated `profiles` application owns:

- profile persistence and database invariants;
- pure handle and display-name normalization;
- conceptual-state acquisition and projection;
- atomic onboarding and text-profile mutation;
- enabled-state mutation guards;
- exact duplicate-handle race classification;
- avatar replacement and removal orchestration through `media.service`;
- the non-creating participation-eligibility predicate;
- profile serializers, views, routes, OpenAPI, and administration.

Freeze these module seams for independent tests and later callers:

- `profiles.services.get_or_create_profile(user: User) -> PlayerProfile` owns
  idempotent conceptual-state materialization for profile-surface callers.
- `profiles.services.put_text_profile(user: User, *, handle: str,
  display_name: str) -> PlayerProfile` owns complete text replacement and
  initial completion.
- `profiles.services.patch_text_profile(user: User, *, handle: str | None =
  None, display_name: str | None = None) -> PlayerProfile` owns
  post-completion partial text mutation. `None` means omitted at this module
  seam; the HTTP serializer rejects explicit client nulls before calling it.
- `profiles.services.replace_profile_avatar(user: User, upload: File[bytes]) ->
  PlayerProfile` and `remove_profile_avatar(user: User) -> None` own the #112
  composition.
- `profiles.eligibility.is_participation_eligible(user: User | AnonymousUser)
  -> bool` is the only reusable downstream participation predicate.
- `profiles.services._is_handle_unique_violation(error: IntegrityError) -> bool`
  is an implementation-private but directly testable structured-error
  classifier. Only `put_text_profile` and `patch_text_profile` use it to raise
  `profiles.services.DuplicateHandleError`; HTTP code converts that result to
  the normal `handle`/`unique` field error.

Keep the module interface small. HTTP views supply `request.user` and validated
input; the profiles module owns lifecycle and persistence rules. Neither views
nor future participation domains should reproduce profile-state queries or
normalization logic. Profile code must not import boto3, R2 configuration, or
Clerk provider types.

## OpenAPI contract

The generated schema must document all five operations, the exact unversioned
paths, Bearer authentication, request content types, successful status codes,
the exact five-field profile representation, nullable pre-onboarding text and
avatar fields, and read-only lifecycle/eligibility fields.

Document PUT as replacing only the complete mutable text-profile
representation while retaining avatar state. Document avatar PUT as
`multipart/form-data` with the required `avatar` file. Document expected
`400`, `401`, and `403` responses without introducing a new global error
schema.

The existing `/api/me/`, public schema, documentation, health, and
administration contracts remain otherwise unchanged.

## Acceptance Contract

### Identity and conceptual profile state

- `accounts.User.id` remains canonical; no product field is added to
  `accounts.User` and no profile data is copied from Clerk.
- `/api/me/` continues returning exactly one integer `id` field.
- The profile model uses the application-user relationship as its primary key
  and exposes no second ID.
- The first profile GET for an otherwise untouched user returns the exact
  incomplete, enabled default representation whether or not it materializes a
  row.
- A pre-onboarding profile with an avatar returns a fresh non-null `avatar_url`
  while its required text fields remain null and onboarding remains incomplete.
- Profile access may materialize a default row; authentication and the #97
  resolver do not.
- Participation eligibility never creates a row and fails closed for missing
  or inconsistent state.

### Onboarding and text fields

- Initial PUT requires both text fields, normalizes them, and atomically sets
  the original completion timestamp.
- A failed initial PUT leaves onboarding incomplete.
- Completion is irreversible and the completion timestamp cannot be replaced.
- PUT after onboarding replaces both text fields without touching avatar state.
- PATCH after onboarding safely updates supplied text fields and cannot clear
  either required field; PATCH before onboarding is rejected.
- Every accepted handle rule, reserved name, display-name normalization, and
  display-name rejection rule is covered by observable tests.

### Handle concurrency and integrity

- The named database constraint is the global handle uniqueness authority.
- Simultaneous claims for one normalized handle yield one successful owner and
  the same safe `handle`/`unique` validation response for the loser.
- Only the exact PostgreSQL `23505` plus expected named constraint is translated
  to duplicate-handle validation.
- Unrelated integrity failures are not mislabeled or swallowed.

### Eligibility and ownership

- All endpoints require authentication and operate only on the authenticated
  user's profile.
- Disabled players retain `/api/me/` and profile read access but receive `403`
  for every text or avatar mutation.
- Only operators can change `is_enabled`; disabling preserves durable records
  and re-enabling restores eligibility.
- The reusable predicate returns true only for an authenticated, completed,
  enabled profile and performs no persistence writes.

### Avatar behavior

- An enabled player may upload, replace, or remove an avatar before or after
  onboarding without changing completion or participation eligibility.
- Upload accepts the exact multipart `avatar` field and maps every approved
  media rejection classification to a safe field error.
- Replacement/removal use #112's exact commit and cleanup ordering.
- The database stores only an opaque key; responses create fresh read URLs and
  neither persistence nor logs contain those URLs.
- Removal is idempotent and returns `204`.
- Avatar failure cannot revert or corrupt otherwise-valid onboarding state.

### Administration, schema, and scope

- Profile admin exposes only approved safe fields and permits only per-object
  `is_enabled` changes with normal Django logging.
- OpenAPI accurately describes every operation, representation, permission,
  content type, and PUT/avatar distinction.
- No public profiles, directories, search, social behavior, biographies,
  moderation system, deletion workflow, Clerk account management, global error
  envelope, or new live smoke command is introduced.

## Verification

Independent acceptance tests must be authored from this specification before
production implementation. Prefer observable HTTP, persistence, authorization,
concurrency, media-lifecycle, administration, and OpenAPI behavior over view or
serializer implementation details. Normal tests remain deterministic and use
the established in-memory media adapter rather than R2.

Run focused tests during implementation, then the repository's authoritative
`make api-check` completion gate. That gate includes formatting, Ruff lint,
strict Pyright, repository-owned Semgrep analysis, PostgreSQL-backed pytest,
Django checks, migration-drift detection, OpenAPI validation, and Gunicorn
configuration loading. Run `git diff --check` and inspect the final migration
and OpenAPI diff.

The validation/parsing, uniqueness race, irreversible state transition, and
authorization rules justify targeted mutation testing if repository-owned
mutation tooling becomes available. This repository currently exposes no such
command, so #113 must not introduce a mutation framework merely to satisfy that
optional gate.

## Deployment, rollback, and live validation

The schema change is additive: register the `profiles` app and create its table
and constraints through a normal Django migration. Railway Development's
existing pre-deploy migration command applies it before the new application
revision starts. Do not reset or destructively rewrite application-user data.

Rolling application code back does not reverse the schema. The added table may
remain unused by the previous revision. Reversing the migration would delete
profile data and is therefore a separately reviewed destructive operator
action, not the normal application rollback.

Do not add a #113-specific Railway or profile smoke command. #112 already owns
live R2 storage verification. #120 owns the composed real Railway Development
validation of authentication, onboarding/profile, media, and participation.
No independent live Railway run is required to close #113 unless implementation
evidence reveals a specific integration risk that deterministic coverage cannot
address.

## Non-goals

- Public profiles, profile lookup, player directories, or search.
- Biographies, extensive customization, friends, or social graphs.
- Profanity filtering, general moderation, handle aliases/history, or rename
  cooldowns.
- Player-controlled enable/disable, suspension reasons, or custom audit
  history.
- Clerk profile synchronization, Clerk account management, provider metadata,
  or changes to authentication/identity resolution.
- Account or profile deletion and media garbage collection.
- Convention enrollment, fursuit ownership, catchability, catches, or other
  gameplay domains.
- New URL versioning, a global error envelope, a mutation framework, or a live
  profile smoke command.

## Resolved decisions

This specification has no open product or architecture decision required for
implementation. If implementation evidence materially contradicts an approved
identity, media, security, API, or migration contract, stop and return for
replanning rather than silently changing this specification.
