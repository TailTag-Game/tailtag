# Authentication test and backend developer tooling

**Issue:** [#99 — Add authentication test and backend developer tooling](https://github.com/TailTag-Game/tailtag/issues/99)

**Parent:** [#94 — Establish V0 authentication and application identity](https://github.com/TailTag-Game/tailtag/issues/94)

**Status:** Approved for implementation

## Goal

Add reusable, offline authentication test support and one guarded live command
that proves TailTag's existing Clerk session-token contract against either the
local API or the one explicitly configured Railway development API.

The live workflow is:

```text
validate target
  -> run credential-free api-smoke
  -> hidden Clerk Development secret prompt
  -> validate Clerk Development instance and dedicated user
  -> discover the unique primary Development Frontend API domain
  -> 60-second sign-in ticket
  -> Clerk Frontend API ticket exchange with Origin http://localhost:3000
  -> normal short-lived session token
  -> unchanged TailTag Clerk verifier
  -> GET /api/me/
  -> required cleanup
```

The workflow must not weaken or add an alternative to the authentication
contract established by issue #96. In particular, it retains normal Clerk
session-token validation, the required non-empty `sid`, and exact
`authorizedParties` validation.

## Spike evidence and selected mechanism

Issue #99 was preceded by two narrowly bounded probes against an existing Clerk
Development instance. Both used `clerk-backend-api==7.0.0`, the version locked
by this repository. All evidence below is sanitized; no credential, Clerk user
ID, session ID, token, or sensitive claim value is retained.

### Direct Backend API session creation

The first probe used Clerk Backend API instance metadata, user creation,
session creation, normal session-token creation, JWKS retrieval, session
revocation, and user deletion. The created token was a genuine normal session
token rather than a custom JWT-template token. It had a valid `sid` and the
expected `sub`, but it did not have an `azp` claim. The supported session and
token creation methods exposed no origin, client, or authorized-party input.

Consequently, a token created solely through that Backend API flow cannot pass
TailTag's approved `authorizedParties` verification. Issue #99 must not use
that mechanism, manufacture `azp` with a custom template, or special-case the
resulting token.

### Sign-in ticket and Frontend API exchange

The successful probe used:

- Clerk Backend API v1 through `clerk-backend-api==7.0.0` for instance
  metadata, a 60-second single-use sign-in ticket, JWKS, and cleanup;
- Clerk Frontend API version `2026-05-12` for development-browser creation,
  client creation, ticket-based sign-in, and normal session-token creation;
  and
- the repository's existing `ClerkSessionVerifier` without modification.

Later permanent-helper validation against the fresh Development application
established that the Backend API-created ticket URL may be unavailable, as its
nullable provider schema permits. The permanent helper therefore reads Domains
metadata through the same validated Backend API transport before creating a
ticket. Exactly one non-satellite primary domain must expose a canonical
Development Frontend API root; that metadata is the sole Frontend API
authority. The ticket URL is ignored for authority selection. The ticket is
then consumed through the documented Frontend API flow with the explicit
`Origin` header
`http://localhost:3000`. The resulting token was a normal session token, not a
custom JWT-template token. Its `sid` was present and matched the created
session, its `sub` matched the selected user, and its `azp` was present and
equal to that exact Origin. The unchanged TailTag verifier accepted it with
that value in `authorized_parties`.

The Frontend API token endpoint exposed no input for selecting the session JWT
lifetime. Independently of the sign-in ticket's requested 60-second lifetime,
the successful probe observed a 60-second session JWT lifetime from its `iat`
and `exp` claims. The permanent helper therefore requests a 60-second ticket
and separately verifies that the resulting session JWT is currently valid and
has a positive lifetime no greater than 60 seconds. It does not claim that
ticket expiry controls JWT expiry.

This documented sign-in-ticket to Frontend API flow is the only approved live
credential mechanism for issue #99. It can mint a token locally and send that
token to either an approved local or Railway development TailTag API, so it
supports both development smoke-test destinations without changing token
origin.

## Persistent and ephemeral test state

Exactly one dedicated Clerk user in the Clerk Development instance is the
identity used by every live smoke run. Its opaque Clerk user ID is supplied as
the non-secret `CLERK_SMOKE_USER_ID` configuration value. The corresponding
TailTag `accounts.User` is resolved through the production authentication path
and intentionally persists in the selected TailTag development database.

The dedicated Clerk Development smoke user and its corresponding TailTag user
are intentional persistent test state. They are reused across invocations and
must not be created or deleted by the live helper. The helper must not depend
on email address, name, username, profile data, or any other mutable provider
attribute.

Each invocation creates only ephemeral authentication state:

- one single-use sign-in ticket;
- the Frontend API development-browser and client state needed for the
  documented ticket exchange;
- one active Clerk session; and
- its bearer session token.

The sign-in ticket, session, and bearer token are invocation-local and must not
survive as usable authentication state after required cleanup. Documented
Frontend API browser/client state may expire naturally when Clerk exposes no
supported deletion operation.

If `CLERK_SMOKE_USER_ID` is missing, cannot be found using the validated
Development credential, or therefore belongs to another Clerk environment,
the command fails closed. It must never provision or select a replacement.

## Fixed synthetic credential origin

The live helper has exactly one credential origin:

```text
http://localhost:3000
```

This string is a private implementation constant for backend tooling. It is
not a command-line option, environment variable, or configuration-file value.
The helper always supplies it as the Clerk Frontend API `Origin`, regardless of
the TailTag API destination, and requires the returned token's `azp` to equal
it exactly.

Both supported TailTag API development environments must explicitly contain
`http://localhost:3000` in `CLERK_AUTHORIZED_PARTIES`. This is a synthetic
development-tool origin; no TailTag frontend needs to be listening on port
3000. Production configuration must not gain this allowance as part of issue
#99.

## Atomic command and configuration

The only supported live entry point is:

```text
make api-auth-smoke
```

There is no token-output command, pipe-based credential handoff, loopback
broker, or other supported credential-transfer interface. Ticket and bearer
token values remain entirely within one process workflow and are never printed
or returned.

The command accepts only these non-secret environment inputs:

- `API_BASE_URL`, optionally selecting the TailTag API destination;
- `TAILTAG_DEVELOPMENT_API_BASE_URL`, required to authorize a non-default
  destination; and
- `CLERK_SMOKE_USER_ID`, identifying the persistent Development smoke user.

It accepts no Clerk secret through an argument, positional value, environment
variable, configuration file, repository-managed credential store, operating
system credential store, stdin pipe, or noninteractive fallback.

Clerk Backend API and Frontend API endpoint locations are not user-configurable.
All provider requests must remain bound to the same Clerk instance whose
metadata was validated as Development. The implementation must not accept a
provider base URL, proxy URL, alternate Frontend API host, or cross-instance
redirect from user configuration.

## TailTag API target policy

This strict target policy applies only to `api-auth-smoke`. It must not alter
the existing target contract of credential-free `api-smoke`.

When `API_BASE_URL` is absent, the authenticated command targets exactly:

```text
http://127.0.0.1:8000
```

An explicitly empty `API_BASE_URL` is invalid rather than equivalent to an
absent value. An explicit trailing slash is the only permitted normalization,
so `http://127.0.0.1:8000/` canonicalizes to the default. No alternate
loopback spelling is accepted.

Any non-default target must:

- use lowercase `https`;
- contain no URL username or password;
- contain no query or fragment;
- have no path other than an absent path or `/`; and
- equal `TAILTAG_DEVELOPMENT_API_BASE_URL` after removing only one root
  trailing slash from each value.

The command performs no suffix matching, hostname pattern matching, DNS
resolution equivalence, default-port normalization, percent-encoding
normalization, redirect equivalence, or other canonicalization. If
`TAILTAG_DEVELOPMENT_API_BASE_URL` is configured, it must itself satisfy the
same HTTPS, credentials, query, fragment, and path restrictions even when the
current target is local. A non-default target is invalid when the separate
configured value is absent or empty.

The helper validates all applicable properties of both values before the
secret prompt and before any Clerk request or resource creation.

## Live-flow sequence

`make api-auth-smoke` performs these stages in order:

1. **Validate target configuration.** Resolve the absent-value default and
   enforce the policy above. Failure stops before the baseline smoke, secret
   prompt, or provider access.
2. **Run baseline smoke.** Invoke the existing credential-free `api-smoke`
   behavior against the selected TailTag API. Failure stops before the secret
   prompt and provider access.
3. **Require an interactive secret.** Confirm that the input and prompt streams
   are attached to a terminal and use terminal-safe hidden input with the exact
   prompt `Clerk Development secret:`. A missing TTY fails closed.
4. **Apply the credential-form guard.** Reject a value that is not in the
   `sk_test_` development-key form before sending it anywhere. This is only an
   early guard and is not evidence that the instance is Development.
5. **Validate authoritative instance metadata.** Authenticate to Clerk's fixed
   Backend API, retrieve the credential's instance metadata, and require its
   authoritative environment type to be Development. This must succeed before
   creating any Clerk authentication resource.
6. **Validate the persistent user.** Fetch `CLERK_SMOKE_USER_ID` through that
   same validated instance and fail closed when it is absent. Do not inspect or
   select the user through mutable profile attributes.
7. **Discover the Frontend API authority.** Through that same Backend API
   transport, read Domains metadata and require exactly one non-satellite
   primary domain with a canonical Development Frontend API root. Do this before
   creating authentication resources; a ticket URL is nullable and never an
   authority source.
8. **Create and consume the ticket.** Create a single-use sign-in ticket with a
   requested lifetime of exactly 60 seconds. Use only the documented
   Development Frontend API browser/client flow bound to that authoritative
   domain and consume the ticket with `Origin: http://localhost:3000`.
9. **Obtain and validate the normal token.** Ask the Frontend API for the active
   session's normal session token. Without logging decoded values, require:
   - a non-empty `sid` equal to the created session ID;
   - a non-empty `sub` equal to `CLERK_SMOKE_USER_ID`;
   - `azp` equal to `http://localhost:3000` exactly;
   - numeric `iat` and `exp` claims describing a positive lifetime no greater
     than 60 seconds; and
   - a token that has not expired at the point of use.
10. **Use the unchanged TailTag verifier.** Retrieve the validated instance's
   public verification material and pass the token through the existing
   `ClerkSessionVerifier` configured with the one fixed authorized party. The
   verifier retains its session-token-only, `sid`, `sub`, signature, issuer,
   time, and authorized-party behavior from issue #96.
11. **Call the selected API.** Send the bearer token to `GET /api/me/` at the
    already validated `API_BASE_URL`. Never follow redirects. Require HTTP
    `200`, a JSON object, exactly one field named `id`, and an integer value:

    ```json
    {"id": 123}
    ```

12. **Clean up.** Execute the required cleanup path described below on success
    or failure after any live authentication resource has been created.

The command succeeds only when target validation, baseline smoke, Development
instance validation, persistent-user validation, the ticket flow, token checks,
the unchanged verifier, the exact `/api/me/` contract, and required cleanup all
succeed.

## Credential and sensitive-data handling

The prompted secret is retained only in process memory for the current
invocation. The helper must not place the secret, ticket, bearer token, Clerk
subject, session ID, sensitive claims, or raw sensitive provider responses in:

- standard output or standard error;
- application, HTTP, SDK, or debug logs;
- exception messages surfaced to the caller;
- shell history;
- fixtures or snapshots;
- repository files, plans, or documentation;
- temporary files or credential stores; or
- command return values or supported inter-process interfaces.

HTTP and SDK debug output must be disabled for the live path. The helper must
construct sanitized errors at its own boundary rather than relying on current
third-party exception formatting to remain safe. Python cannot guarantee
physical memory zeroization, so this contract requires in-process-only
retention and prompt release of references, not an unsupported zeroization
claim.

Successful output is stage-level only. It may state that baseline smoke passed,
the Development instance was validated, authenticated smoke passed, and
cleanup completed. It must not print `/api/me/` data or any provider resource
identifier.

## Cleanup contract

Once the first live Clerk authentication resource is created, the workflow
must enter a `finally`-style cleanup path on every success and failure exit.

The cleanup path must:

- revoke an active session created by the invocation;
- revoke an unconsumed sign-in ticket when Clerk exposes the supported
  operation;
- treat a consumed single-use ticket as no longer usable rather than attempt an
  unsupported deletion;
- rely on documented expiry only for Frontend API browser/client state for
  which Clerk exposes no supported deletion operation;
- never delete or modify the persistent dedicated Clerk smoke user; and
- never delete the corresponding persistent TailTag application user.

Any failure of an applicable supported cleanup operation makes the command
unsuccessful. When the primary workflow and cleanup both fail, output preserves
a sanitized indication of the primary failed stage and separately reports that
cleanup was incomplete. It must not replace the primary category with a raw
cleanup exception or silently discard either outcome.

The bearer token has no independent deletion operation. Revoking its session
is the required supported invalidation mechanism.

## Sanitized failure categories

The command may identify only a bounded failed stage, including:

- target configuration invalid;
- baseline smoke unsuccessful;
- interactive terminal unavailable;
- credential form invalid;
- Clerk instance not validated as Development;
- configured smoke user unavailable;
- provider development-browser flow unsuccessful;
- provider development-browser request invalid;
- provider development-browser request unauthenticated;
- provider development-browser request forbidden;
- provider development-browser browser challenge required;
- provider development-browser origin rejected;
- provider development-browser hostname rejected;
- provider development-browser request rejected;
- provider development-browser transport unavailable;
- provider development-browser response invalid;
- provider client initialization unsuccessful;
- provider ticket flow unsuccessful;
- provider sign-in-ticket credential unavailable;
- provider Frontend API authority unavailable;
- provider session-token flow unsuccessful;
- provider session-token request invalid;
- provider session-token request unauthenticated;
- provider session-token request forbidden;
- provider session-token request not found;
- provider session-token request rejected;
- provider session-token transport unavailable;
- provider session-token response invalid;
- token claims or lifetime invalid;
- TailTag verifier rejected the token;
- authenticated API response invalid; or
- cleanup incomplete.

The refined session-token entries are fixed, non-sensitive classifications only.
Messages must not include secrets, tickets, tokens, Clerk identifiers, session
identifiers, sensitive claims, raw provider status, HTTP bodies, request or
response headers, or raw exception representations. A combined failure reports
both sanitized stage categories without their sensitive details.

## Repository-internal pytest authentication support

All reusable authentication test support added by issue #99 lives under
`services/api/tests/`. There is no production test-helper module or
application-facing testing API.

The support provides:

1. **Typed TailTag user factories.** Explicit, narrow factories persist real
   `accounts.User` objects with unique opaque test Clerk IDs. Callers may
   override only relevant model fields deliberately. Defaults must not invent
   email, profile, gameplay, role, or other product assumptions.
2. **Endpoint-isolation authentication helpers.** Helpers authenticate a DRF
   test client through `force_authenticate()` with a real persisted
   `accounts.User`. These isolate endpoint representation and permission
   behavior from the authentication stack.
3. **Composed authentication-path fakes.** A reusable fake replaces exactly
   `ClerkSessionVerifier.verify`. The real DRF `TailTagAuthentication` and real
   TailTag application-user resolver remain active so tests cover bearer
   composition, identity resolution, and downstream `request.user` behavior.

Tests and application code continue treating TailTag's `accounts.User` as the
downstream authenticated-user convention. The helpers must not expose a Clerk
subject or verified-provider identity as a replacement downstream convention.

Issue #99 adds no `factory_boy` dependency. The existing real
Clerk-adapter signed-JWT cryptographic tests remain the narrow provider
integration suite and continue to prohibit outbound network access.

## Automated test contract

Ordinary automated tests remain outbound-network prohibited. They use
controlled fakes at external HTTP/SDK boundaries and cover observable behavior
rather than internal helper structure or incidental SDK call mechanics.
Sequencing may be asserted where order is itself part of the security contract.

### Reusable test support

- Repeated factory calls produce distinct opaque Clerk IDs and persisted
  TailTag users.
- Explicit factory overrides remain possible without implicit profile or game
  state.
- Endpoint-isolation helpers expose a real TailTag user as `request.user`.
- Composed helpers replace only `ClerkSessionVerifier.verify` and retain the
  real authenticator and identity resolver.
- Existing cryptographic verifier coverage remains offline and intact.

### Live-command orchestration

Behavioral tests prove:

- every target acceptance and rejection rule;
- target validation occurs before baseline smoke, secret prompting, or Clerk
  access;
- credential-free baseline smoke occurs before the secret prompt or Clerk
  access;
- invalid targets and baseline failures never prompt or contact Clerk;
- the prompt requires a TTY, hides input, and has no noninteractive fallback;
- `sk_test_` is an early form guard while instance metadata is authoritative;
- all Backend API and Frontend API interaction stays bound to the validated
  instance and provider locations are not user-configurable;
- the dedicated user is fetched by opaque ID and never auto-provisioned;
- the Origin is exactly the non-configurable tooling origin;
- the sign-in ticket requests exactly 60 seconds;
- token `sid`, `sub`, `azp`, and `iat`/`exp` behavior is validated independently;
- the existing verifier is used without a weaker alternative path;
- `/api/me/` redirects are rejected;
- `/api/me/` must return exactly `{"id": <integer>}`;
- supported cleanup is attempted after every failure point following resource
  creation;
- cleanup failure makes the result unsuccessful; and
- a primary-plus-cleanup failure preserves both sanitized stage indications.

The tests should not freeze private function names, module decomposition,
request construction details, or Clerk SDK mechanics where a supported change
would preserve this behavior.

### Adversarial sanitization

Sanitization tests inject synthetic exception messages and response content
containing representative:

- credential-like `sk_test_` values;
- sign-in tickets;
- JWT-shaped bearer tokens;
- Clerk user identifiers;
- Clerk session identifiers; and
- sensitive decoded claims.

The tests then prove that none of those injected values appears through any
supported standard output, standard error, raised user-facing error, command
result, or log-capture path. Test values are deliberately synthetic and are not
usable credentials or real provider identifiers. Coverage must not depend only
on the exception formatting of the currently installed Clerk or HTTP library.

### Offline command boundaries

- `api-smoke` retains its existing credential-free contract.
- `api-check` remains deterministic, noninteractive, and offline with respect
  to Clerk.
- CI must not prompt, hold a Clerk secret, or invoke the real live workflow.
- `make api-auth-smoke` is the only supported path that exercises the real
  Clerk Development workflow, and it is never added as a dependency of
  `api-check`, another ordinary check, or CI.

## Developer documentation

Contributor-facing documentation must explain:

- how a maintainer manually creates and retains the one dedicated user in the
  Clerk Development instance;
- where to copy its opaque user ID and how to configure the non-secret
  `CLERK_SMOKE_USER_ID` without using mutable profile attributes;
- how to configure the non-secret `TAILTAG_DEVELOPMENT_API_BASE_URL` for the
  exact Railway development API root;
- how to add `http://localhost:3000` to `CLERK_AUTHORIZED_PARTIES` in both the
  local and Railway development API environments;
- why that fixed value is a synthetic tooling origin and does not require a
  frontend on port 3000;
- that production configuration must not gain the synthetic origin;
- that the Development secret is prompted invisibly on every live invocation
  and is never configured or stored for this helper;
- local and Railway development invocation examples that contain no secret;
- the persistent Clerk/TailTag user state and ephemeral per-invocation ticket,
  session, and bearer-token state;
- sanitized failure categories and cleanup expectations; and
- that real live validation is explicit, interactive, Development-only, and
  excluded from ordinary tests and CI.

The existing documentation statement that the production TailTag verifier does
not need a Clerk secret remains true. The privileged prompted credential
belongs only to this separate developer-tooling process.

## Acceptance Contract

Issue #99 is accepted when all of the following are true.

### Offline authentication test support

- Typed factories, endpoint-isolation helpers, and composed verifier fakes are
  reusable and live entirely under `services/api/tests/`.
- Factories create persisted TailTag users with unique opaque test Clerk IDs
  and no profile or gameplay assumptions.
- Endpoint-isolation helpers use `force_authenticate()` with real TailTag
  users.
- Composed helpers fake exactly `ClerkSessionVerifier.verify` while retaining
  the real DRF authenticator and TailTag identity resolver.
- Existing real-adapter cryptographic tests remain intact, focused, and
  outbound-network prohibited.
- No new factory dependency, production test helper, or application-facing
  test API exists.

### Guarded authenticated smoke

- `make api-auth-smoke` is atomic and is the sole supported live path.
- Target validation and credential-free baseline smoke occur before the hidden
  secret prompt or any provider request.
- The default and exact-configured Railway target policies are enforced without
  broad matching, unexpected normalization, credentials, paths, query values,
  fragments, or redirects.
- No provider endpoint is user-configurable, and all provider calls stay bound
  to the one metadata-validated Development instance.
- The command requires a TTY, accepts the secret only through the exact hidden
  prompt, applies the `sk_test_` early guard, and uses instance metadata as the
  authoritative environment check.
- The configured persistent Clerk user must exist in that Development instance;
  no replacement user is created.
- The Frontend API ticket flow uses only the fixed synthetic Origin and returns
  a normal session token whose `sid`, `sub`, `azp`, and observed short lifetime
  satisfy the approved requirements.
- The unchanged issue #96 verifier accepts the token.
- `GET /api/me/` does not follow redirects and returns HTTP `200` with exactly
  `{"id": <integer>}`.
- Ticket, session, and token values stay in process memory and never appear in
  supported outputs or repository state.
- Required cleanup succeeds; otherwise the command fails with the specified
  sanitized single or combined failure result.

### Operational boundaries

- The dedicated Clerk Development user and corresponding TailTag user persist
  and are reused; per-invocation authentication resources are ephemeral.
- Both supported development API configurations authorize the fixed tooling
  origin, with no change to production configuration.
- `api-smoke`, `api-check`, and CI remain credential-free, noninteractive, and
  offline with respect to Clerk.
- Documentation covers setup, configuration, invocation, persistence,
  ephemerality, cleanup, failure handling, and production prohibitions.
- Focused automated tests, the repository's deterministic backend gates,
  documentation validation, and an explicitly initiated sanitized live
  Development-instance validation pass.

## Risks and contract-conflict triggers

- **Provider behavior changes.** The selected mechanism depends on Clerk's
  supported Development-only sign-in-ticket and Frontend API behavior. If the
  supported flow no longer produces the spike-established `sid`, `sub`, `azp`,
  or short JWT lifetime, implementation must stop for a new decision rather
  than weaken verification or invent an alternate token.
- **Credential or token disclosure.** Third-party exceptions and HTTP response
  bodies may echo sensitive inputs. The helper owns sanitization at its output
  boundary, disables debug output, and has adversarial non-disclosure tests.
- **Accidental production access.** A key prefix alone is insufficient. The
  command requires authoritative Development metadata, a user present in that
  instance, fixed provider locations, and exact TailTag destination policy
  before creating authentication resources.
- **Incomplete cleanup.** Network or provider failures may interrupt
  revocation. Applicable cleanup is always attempted, any incomplete cleanup
  makes the run unsuccessful, and combined failure reporting retains both
  sanitized outcome categories.
- **Test abstraction drift.** Authentication helpers could accidentally teach
  application tests to depend on provider identity. Keeping every helper under
  the test tree and exposing real `accounts.User` objects downstream preserves
  the TailTag-owned identity convention.

There are no unresolved product or architecture decisions in this spec. A
discovery that requires a weaker authentication contract, another provider
flow, production access, a configurable credential origin, a noninteractive
secret path, persistent bearer state, or a materially different cleanup model
is a consequential contract conflict and requires explicit replanning.

## Excluded scope

Issue #99 does not:

- modify or weaken issue #96 authentication behavior;
- disable or broaden `authorizedParties` validation;
- weaken the required `sid` or session-token checks;
- add a custom JWT template or second authentication path;
- use or configure a production Clerk instance or `sk_live_` credential;
- add the synthetic tooling origin to production;
- automatically provision, replace, or delete the dedicated smoke user;
- delete the persistent TailTag test user;
- persist or expose a token, ticket, secret, or sensitive provider response;
- add a noninteractive secret source or credential-transfer surface;
- add a token-output command;
- change the existing credential-free `api-smoke` target contract;
- add live Clerk behavior to `api-check` or CI;
- add player profiles, gameplay state, frontend behavior, or production Clerk
  infrastructure;
- add a database migration; or
- introduce unrelated refactoring or dependencies.
