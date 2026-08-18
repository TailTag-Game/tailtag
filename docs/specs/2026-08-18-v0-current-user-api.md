# V0 authenticated current-user API

**Issue:** [#98 — Add the V0 authenticated current-user API contract](https://github.com/TailTag-Game/tailtag/issues/98)

**Parent:** [#94 — Establish V0 authentication and application identity](https://github.com/TailTag-Game/tailtag/issues/94)

**Status:** Approved for implementation

## Goal

Add the smallest product API surface that proves a request authenticated through
TailTag's existing Clerk boundary can consume the canonical TailTag-owned
application identity. This endpoint is an identity proof, not a player-profile
or user-directory API.

```text
Bearer request
  -> TailTagAuthentication
  -> accounts.User as request.user
  -> GET /api/me/
  -> 200 {"id": <TailTag user primary key>}
```

Normal automated tests remain offline. No live Clerk credential, request, or
network dependency is part of this issue.

## Endpoint and namespace

The first TailTag product API route is:

```text
GET /api/me/
```

`/api/` is the current V0 product API namespace. The repository does not yet
establish URL API versioning, so this issue must not introduce `/api/v0/`,
`/api/v1/`, or any other URL-version prefix. The product milestone name "V0"
does not imply an API compatibility scheme.

The route is intentionally not nested under `/users/`. `/api/me/` represents
the currently authenticated TailTag application identity and establishes no
player-profile, user-resource, or directory contract.

## Authenticated response

An authenticated request returns HTTP `200` with exactly:

```json
{
  "id": 123
}
```

The response contract is:

- field name: `id`;
- type: integer; and
- value: the canonical TailTag-owned `accounts.User` primary key exposed as
  `request.user` by the existing DRF authentication stack.

The TailTag application-user ID is a permitted client-facing application
identifier. It is not secret and must never be used as proof of authorization.

The response must not expose `clerk_user_id`, `is_staff`, passwords or other
authentication fields, `last_login`, profile fields, provider/session metadata,
or any additional user field. This issue adds no profile serializer or
speculative reusable user representation.

## Authentication and permission convention

`TailTagAuthentication` remains the configured global DRF authentication class.
Global authentication availability does not make every endpoint private.

`GET /api/me/` explicitly declares `IsAuthenticated`. The downstream V0
convention is:

> TailTag authentication is globally available through the configured
> authentication class. Endpoints requiring an authenticated TailTag user
> explicitly declare `IsAuthenticated`.

This issue must not add or change `DEFAULT_PERMISSION_CLASSES`. Existing public
health, OpenAPI schema, and API documentation behavior remains unchanged.

A request without valid authentication returns HTTP `401` and
`WWW-Authenticate: Bearer` through the existing authentication class. The
response uses DRF's generic authentication-error representation. No particular
English error message becomes a new TailTag-wide compatibility contract.

## OpenAPI contract

The generated OpenAPI document describes:

- `GET /api/me/`;
- HTTP Bearer authentication and the operation security requirement;
- an authenticated `200` response;
- an exact response object containing one required integer property, `id`;
- an unauthenticated `401` response; and
- a minimal generic authentication-error object containing one required string
  property, `detail`.

The schema must not apply the protected operation's security requirement to the
public schema or documentation endpoints. This issue introduces no broader
application error envelope.

## Acceptance Contract

### Focused endpoint behavior

- The production URL configuration resolves `GET /api/me/`.
- A focused view test may use DRF `force_authenticate()` to isolate the
  representation and permission contract.
- An authenticated request returns `200` with exactly the single integer `id`
  for `request.user`.
- The exact-field assertion rejects plausible scope creep, including Clerk,
  administrative, authentication, session, and profile fields.
- A headerless request returns `401` with `WWW-Authenticate: Bearer`.
- Existing public health, schema, and documentation behavior remains unchanged.
- No URL-version prefix or unrelated product resource is added.

### Composed authentication behavior

One focused offline integration test sends a Bearer request to the production
endpoint, replaces only the issue #96 external verification boundary with a
fake verified Clerk identity, and uses the real issue #97 resolver and DRF
authentication composition. The test proves that:

- the verified subject resolves or provisions the canonical `accounts.User`;
- the production endpoint consumes that user as `request.user`;
- the response is `200 {"id": <resolved TailTag user primary key>}`; and
- no live Clerk request or JWT cryptographic matrix is introduced.

### OpenAPI behavior

- The production schema contains `/api/me/` as a `GET` operation.
- The operation declares the documented Bearer security scheme.
- The `200` response schema allows exactly the required integer `id` property.
- The `401` response schema contains the required string `detail` property
  without freezing a specific English message.
- Existing public schema/docs operations do not acquire an authenticated-user
  permission requirement.

## Implementation plan

1. Add an accounts-owned DRF current-user view and route it at `/api/me/`
   through the existing project URL configuration.
2. Keep the view representation deliberately direct and one-field; do not
   introduce a model/profile serializer abstraction.
3. Add the minimal drf-spectacular integration needed to expose the custom
   TailTag Bearer authentication scheme and the exact operation responses.
4. Add focused view, production-route, composed-authentication, permission, and
   OpenAPI regression tests against this contract.
5. Update the API contributor documentation with the namespace, absence of URL
   versioning, explicit-permission convention, and identity-proof boundary.
6. Run focused tests followed by the repository's authoritative backend and
   documentation validation commands.

## Excluded scope

This issue does not add player profiles, usernames, display names, avatars,
biographies, Clerk identifiers, identity-resolution behavior, Clerk-verification
behavior, developer authentication tooling, Railway validation, unrelated API
resources, URL-version infrastructure, roles, account management, or a broader
error-envelope framework.
