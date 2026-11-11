# Native Clerk session-token acceptance

Status: accepted on 2026-10-16. The maintainer approved it after the security review. It is a focused amendment to the Clerk session verification rule from issues #96 and #104. Issue #329 tracks it.

The TailTag mobile app uses the official native Clerk SDKs (ADR 0009). Their session tokens have no `azp` claim. The verifier rejects such tokens today, so an app session cannot call the API. Issue #135 confirmed this on an Android emulator against Development, with a `401` from `GET /api/me/` and "azp claim present: no".

This spec changes only the `azp` rule. It adds one lifetime limit for tokens without `azp`. ADR 0003 (Clerk for player authentication) does not change.

## Terms

- `azp` (authorized party) is a session-token claim. Clerk sets it from the `Origin` header of the Frontend API request that created the token. Clerk can omit it when `Origin` is empty or `null`.
- An allowed party is an origin in `CLERK_AUTHORIZED_PARTIES`.
- A token can have no `azp` for two reasons:
  - A native SDK asked for it without an `Origin`.
  - A holder of the Clerk secret key created it through the Backend API.

## Amends

This spec replaces these earlier approved decisions. Each of them made a missing `azp` fail:
- `docs/specs/2026-09-15-v0-railway-staging-environment.md`: "missing ... origins fail closed". That paragraph allows a later replacement.
- `docs/specs/2026-10-02-synthetic-identity-pool.md`:
  - Option C ("accept a missing `azp`") was rejected because it "removes a verifier guarantee for every Staging token". This spec accepts that cost for the mobile app, and adds the lifetime limit below.
  - Native mode was excluded because its tokens have no `azp`.
- `docs/specs/2026-08-18-authentication-test-and-backend-developer-tooling.md`: "do not special-case the resulting token". This spec adds one special case: a lifetime limit for tokens without `azp`.

The kill-switch limit: the synthetic-identity-pool spec (decision D2) calls the authorized-party list a kill switch for simulator tokens. After this change, the switch works only for tokens that carry an `azp`. A client that redeems a ticket in native mode without an `Origin` gets a token without `azp`, which this rule accepts. Decision D3 of that spec showed that this works on Staging. To cut off such tokens, revoke the sessions in Clerk, or revert this change.

## Current rule

`ClerkSessionVerifier` (`services/api/authentication/clerk.py`) passes the allowed parties to `authenticate_request` from `clerk-backend-api` 7.0.0. When the list is set, the SDK rejects a token if its `azp` is missing or is not in the list (`verifytoken.py:62-65`). The test `test_rejected_or_missing_authorized_party_fails_generically` makes both cases explicit. The SDK uses the list for this check only.

## New rule

The verifier makes its own `azp` check. It no longer passes the allowed parties to the SDK.

| Token | Result |
|---|---|
| No `azp` key, and `exp - iat` is 60 seconds or less | Accepted, if all other checks pass |
| No `azp` key, and `exp - iat` is more than 60 seconds, or a time claim is missing | Rejected, generic `401`, `Reason.TOKEN_INVALID` |
| `azp` is a non-empty string in the allowed parties | Accepted, if all other checks pass |
| `azp` is a string that is not in the allowed parties | Rejected, generic `401`, `Reason.TOKEN_INVALID` |
| `azp` is present and is empty, `null`, or not a string | Rejected, generic `401`, `Reason.TOKEN_INVALID` |

The verifier tests whether the `azp` key is present. A key with the JSON value `null` is a present key, so the verifier rejects it.

The 60-second limit is a named constant. It equals the default session-token lifetime of a Clerk instance, and the app tokens use it. If a maintainer raises the token lifetime in the Clerk dashboard, the constant must change in the same release.

The other checks do not change:
- `accepts_token=["session_token"]` excludes the opaque machine tokens.
- The `sid` check excludes JWT template tokens, because they cannot carry `sid`.
- The offline signature check against `CLERK_JWT_KEY` binds a token to its instance. The SDK does not check the issuer (`verifytoken.py:58`). Development and Staging have separate signing keys.
- The SDK checks the time claims.
- `sub` must be a non-empty string.
- The verifier reads the `Authorization` header only, with no cookie fallback.

The `azp` check and the lifetime limit run only after the SDK accepts the signature and the time claims. They run before the identity returns, and they do not skip the `sid` and `sub` checks.

## Environments

The rule is in code. It is the same in Development and Staging, which are the only deployed environments (`services/api/health/configuration.py:93-97`). There is no new setting. `CLERK_AUTHORIZED_PARTIES`, its loader, and the readiness guards for Development and Staging do not change. A future production environment gets the same rule. Its own readiness work can review the rule again.

No native client can reach Staging today. The app accepts only `pk_test_` keys, and its approved API roots are Local and Railway Development (`docs/development/mobile.md`). The rule still applies to Staging, so that the field beta needs no second change.

## Threat analysis

### What `azp` protects

`azp` is a value that the browser supplies, and only a browser enforces it. A browser always sends `Origin` on a cross-origin request, and page script cannot change it. The allowlist therefore stops a web page on a different origin from getting an accepted token for a user. Clerk names one case: a compromised app on another subdomain of the same root domain.

A non-browser client can choose its `Origin`. The Staging proof D3 (`docs/specs/2026-10-02-synthetic-identity-pool.md`) showed this. A client that uses the cookie carrier with an allowed `Origin` got an accepted token whose `azp` was that origin. Native mode together with an `Origin` is refused (`origin_authorization_headers_conflict`). A non-browser client therefore uses the cookie carrier to choose its `azp`. TailTag tooling does the same with the fixed origin `http://localhost:3000`.

### What the change allows

The change accepts tokens that a client asked for without an `Origin`. A non-browser client can do this. It can already get an accepted token today if it uses the cookie carrier with an allowed `Origin`. For Frontend API tokens, the change therefore gives a non-browser client nothing new.

In every case, a Clerk session exists only after a user signs in through that client. The token is bound to the instance by its signature, and to one session by `sid`.

Browser tokens keep the allowlist. A web page that asks for a token sends its own `Origin`. That token carries the page origin as `azp`, and the verifier rejects it unless the origin is allowed.

### Tokens from the Backend API

A holder of the Clerk secret key can create a normal session token through the Backend API. Such a token has no `azp`, and the request can set a long lifetime. The repository observed `expires_in_seconds=600` (`docs/specs/2026-10-02-synthetic-identity-pool.md`). The verifier has no lifetime limit of its own today. It rejects these tokens only because they have no `azp`.

Without a limit, this change makes such tokens accepted until they expire. A revocation in Clerk does not stop them, because the API checks tokens offline. A rotation of the secret key does not stop them either, because the signing key does not change. The 60-second limit for tokens without `azp` closes this gap. It keeps the reach of a leaked secret key the same as today.

### `Origin: null`

A browser sends `Origin: null` in some contexts:
- A sandboxed iframe without `allow-same-origin`.
- `data:` and `file:` documents.
- Some cross-origin redirects.

Clerk can omit `azp` for a `null` `Origin`. The browser case is a risk only if the Clerk Frontend API issues a token for such a request.

In Development, the browser credential is the `__clerk_db_jwt` query parameter. Clerk script adds it, and the browser does not send it on its own. A third-party page cannot use it.

Staging uses a Clerk Production instance (`docs/development/staging.md`). On 2026-10-16, a probe without credentials checked the Staging Frontend API at `https://clerk.staging.tailtag.app`:

| Request | `Origin` | Result |
|---|---|---|
| `GET /v1/client` | `null` | `400`, `origin_invalid` |
| `GET /v1/client` | `https://example.invalid` | `400`, `origin_invalid` |
| `GET /v1/client` | `https://accounts.staging.tailtag.app` | `200` |
| `POST /v1/client/sessions/{id}/tokens` | `null` | `400`, `origin_invalid` |
| `POST /v1/client/sessions/{id}/tokens` | `https://example.invalid` | `400`, `origin_invalid` |
| `POST /v1/client/sessions/{id}/tokens` | `https://accounts.staging.tailtag.app` | `signed_out` |

The Frontend API echoes CORS headers for every `Origin`, including `null`. It refuses a `null` or unknown `Origin` with `origin_invalid` before it looks at a session. The allowed origin reached the session check. A browser context with a `null` `Origin` therefore cannot get a token from the Staging instance. A change of the allowed origins in Clerk, or a change of Clerk behavior, can change this result. If one of these changes happens, run the probe again.

The API never reads cookies (`_AuthorizationOnlyRequest`).

### Residual risk

A malicious native app can ask players to sign in and then call the API as those players. The `azp` rule never stopped this, and this change does not affect it. A public client cannot prove its identity, because the publishable key is public. Account-level controls in Clerk, and server-side authorization in TailTag, stay the defenses.

## Telemetry

The change adds no telemetry signal, outcome, or attribute. Every request from the app has no `azp`, so a count of "accepted without `azp`" equals mobile traffic and finds nothing unusual. Rejected tokens still record `Reason.TOKEN_INVALID`, through the existing rejection path. No observability budget exists yet (#209).

## Alternatives

- A Clerk JWT template with a custom `aud` for the app. This was rejected. Any client with the publishable key can ask for the template, so it binds nothing. It also adds a second token type, Clerk configuration, and a mobile bridge change.
- A custom session claim as a native marker. This is not possible. Custom session claims apply to every token of the instance.
- Removal of the `azp` check. This was rejected. It removes the browser protection for the hosted portal and the tooling tokens.
- A new setting that is on in Development only. This was rejected. The field beta uses Staging, so the setting only delays the same decision and adds a readiness contract.
- Risk acceptance for Backend API tokens instead of the lifetime limit. This was rejected. It extends the reach of a leaked secret key past a Clerk revocation.

## Acceptance contract

The acceptance criteria are AC1 to AC15 of the approved #329 refinement, with its 2026-10-16 amendment. In short:
- A token with no `azp` and a lifetime of 60 seconds or less returns `200` from `GET /api/me/`.
- A token with no `azp` and a longer lifetime fails with the generic `401` and `Reason.TOKEN_INVALID`.
- A present `azp` that is not allowed, empty, `null`, or not a string fails in the same way.
- An allowed `azp` stays accepted, with no new lifetime limit.
- No other verifier check changes, and there is no cookie path.
- The configuration, the readiness guards, and the Railway variables do not change, and no telemetry is added.
- `services/api/README.md` and the `azp` paragraph of `docs/development/mobile.md` describe the rule.

## Test surface

Use the existing `test_clerk_authentication.py` fixtures with synthetic tokens:
- The parameterized test `test_rejected_or_missing_authorized_party_fails_generically` changes. Its "missing" case moves to an explicit acceptance test. Its "unapproved" case stays. It gains the empty-string, non-string, and JSON `null` cases. Build the JSON `null` token explicitly, because the fixture uses `None` to omit a claim.
- A token with no `azp` and a 600-second lifetime fails.
- A token with no `azp` and no `sid` fails with `Reason.CLAIMS_MISSING`. This shows that the new branch does not skip the `sid` check.
- An allowed `azp` stays accepted.
- The tests for the other checks, the configuration loader, and the readiness guards pass without edits.

## Rollout and rollback

Rollout uses the normal path. The merge to `main` deploys to Development, and Staging follows through controlled promotion. No Railway variable changes. After the Development deployment, the #135 proof screen runs once on one platform and must show `200`. A comment on #329 records the result.

Staging promotion needs no hold. The lifetime limit and the `Origin: null` probe close the two conditions of the security review before the merge.

Rollback is a revert of the verifier change. No data, setting, or contract outside the verifier changes, so this is a two-way door.

## Review

The ADW `security-reviewer` agent reviewed this spec on 2026-10-16. Its verdict was "approve with conditions" for Development and Staging. The conditions were:
- The two extra negative tests.
- This "Amends" section and the text corrections.
- A decision on Backend API tokens.
- The Staging `Origin: null` probe.

This revision meets all four. The lifetime limit settles the decision on Backend API tokens.

## References

- Issue #329, its approved refinement comment and its amendment, and issue #135.
- ADR 0003 and ADR 0009.
- `docs/specs/2026-09-24-replacement-development-portal-auth.md`, the earlier amendment of the authorized-party rule.
- `docs/specs/2026-10-02-synthetic-identity-pool.md`, `docs/specs/2026-09-15-v0-railway-staging-environment.md`, and `docs/specs/2026-08-18-authentication-test-and-backend-developer-tooling.md`.
- [Clerk session tokens](https://clerk.com/docs/guides/sessions/session-tokens): the `azp` definition and its omission for an empty or `null` `Origin`.
- [How Clerk works](https://clerk.com/docs/guides/how-clerk-works/overview): the Development browser credential.
- [JWT templates](https://clerk.com/docs/guides/sessions/jwt-templates): template tokens cannot carry `sid`.
- [Clerk production deployment](https://clerk.com/docs/guides/development/deployment/production): why to set `authorizedParties`.
