# Railway development authentication validation

Date: 2026-08-18 (live validation completed in UTC on 2026-08-19)

Issue: [#100](https://github.com/TailTag-Game/tailtag/issues/100)

## Scope

This review records the final Wave 1 validation of TailTag's authentication and
application-identity path in the shared, explicitly non-production Railway
Development environment:

```text
Clerk Development user
  -> genuine short-lived session token
  -> Railway Development API
  -> offline Clerk verification
  -> exact TailTag user provisioning or resolution
  -> GET /api/me/
```

The exercise did not access or configure production Clerk or TailTag resources.
It did not add frontend sign-in, profiles, gameplay behavior, organizations,
permissions, account deletion, webhook synchronization, or unrelated
infrastructure. No credential, Clerk subject, TailTag user ID, database row,
session ID, ticket, bearer token, JWT claim value, or JWT public-key contents is
recorded here.

## Validated revision and environment

| Item | Validated value |
| --- | --- |
| Repository revision | `8f11558a41d57cf375316a8f5095a535474f3624` on `main` |
| Railway target | `TailTag` / `development` / `api` |
| Public API root | `https://api-development-8fa7.up.railway.app` |
| Clerk boundary | The existing TailTag Clerk Development instance and one dedicated persistent smoke user |
| TailTag identity state | One persistent application user linked to the exact opaque Clerk subject after first authentication |

Railway deployment metadata reported the expected revision as `SUCCESS` and
the preceding revision as removed before authentication configuration or live
validation continued. The canonical credential-free smoke then passed against
the public API root.

## Railway Clerk configuration boundary

The API service received the complete Clerk configuration in one non-replacing
Railway variable-collection update. Sanitized post-update verification proved
that exactly these `CLERK_*` names were present:

| Variable | Verified Development contract |
| --- | --- |
| `CLERK_AUTHENTICATION_ENABLED` | Exactly `true`. |
| `CLERK_JWT_KEY` | A valid RSA public key copied from the Clerk Development instance's JWKS Public Key surface. The contents were neither printed nor recorded. |
| `CLERK_AUTHORIZED_PARTIES` | Exactly `http://localhost:3000`, the fixed synthetic backend-tooling origin. |

`CLERK_SMOKE_USER_ID` and `TAILTAG_DEVELOPMENT_API_BASE_URL` were confirmed
absent from Railway runtime configuration. They remain non-secret local
operator inputs. The Clerk Development `sk_test_` credential was supplied only
through the authenticated smoke command's hidden interactive prompt and was
never configured on Railway.

The configuration update created one same-revision Railway deployment. That
deployment reached `SUCCESS`, after which the credential-free smoke passed
again. No partial Clerk configuration was deployed to a running API.

## Acceptance evidence

| #100 acceptance criterion | Result | Sanitized evidence |
| --- | --- | --- |
| Railway Development contains only the required Clerk Development configuration. | **PASS** | Exactly the three approved `CLERK_*` names and values described above were verified; both operator-only inputs were absent. Existing unrelated Django, PostgreSQL, and Railway platform configuration was preserved. |
| A genuine short-lived Clerk Development session authenticates to the deployed API. | **PASS** | The canonical interactive `make api-auth-smoke` workflow completed successfully against the explicit Railway Development API root. |
| First authenticated use provisions a TailTag application user and returns the expected response. | **PASS** | A parameterized read-only precondition query reported no row for the exact subject. The first authenticated smoke then returned the exact `{"id": <integer>}` response contract, and a second read-only query reported that the row existed. |
| Repeating the request resolves the same stable TailTag identity. | **PASS** | A second independent authenticated smoke for the same dedicated Clerk user passed. A final exact-subject read-only predicate confirmed exactly one TailTag row, consistent with the unique identity mapping and repeat-resolution contract. |
| Missing, malformed, invalid, and expired credentials return sanitized `401` responses. | **PASS** | Missing, non-Bearer, and syntactically valid but invalid credentials each returned HTTP 401, a Bearer challenge, and the generic one-field error shape without verification detail. A bounded one-run probe proved causality for expiry: the same genuine token first returned the exact authenticated response, then returned the same generic 401 only after its `exp` plus Clerk's five-second verification skew. |
| The canonical authenticated smoke workflow passes against the explicit Railway API base URL. | **PASS** | The canonical command passed twice with `API_BASE_URL` and `TAILTAG_DEVELOPMENT_API_BASE_URL` set to the same approved HTTPS root. Each invocation completed required provider cleanup before reporting success. |
| Deployed OpenAPI represents the current-user authentication contract. | **PASS** | The live schema exposed one HTTP Bearer scheme; `GET /api/me/` required exactly that scheme, documented 401, and returned an object with exactly one required integer `id`. |
| Backend and deployment documentation matches the verified workflow and secret boundary. | **PASS** | The API README and backend delivery operations guide now record the verified Development-only runtime configuration, operator-input separation, and link to this review. |
| Durable evidence records sanitized actions, outcomes, limitations, and fixes or follow-ups. | **PASS** | This review records the complete validation without sensitive identifiers or credential material. No application defect or follow-up issue was identified. |
| No production or excluded product scope is introduced. | **PASS** | All provider and API interaction used Development resources. The repository change is documentation-only. |

## Validation sequence

1. Correlated current `main`, successful GitHub checks, and Railway deployment
   metadata to the expected revision. A queued deployment required operator
   approval before the exact revision became active.
2. Ran the canonical credential-free smoke against the public Development API.
3. Applied the three approved Clerk variables together and waited for the
   same-revision configuration deployment to succeed.
4. Re-ran credential-free smoke and verified the sanitized runtime
   configuration shape without rendering values.
5. Used Railway SSH into the API service for a parameterized PostgreSQL
   `SELECT EXISTS` in an explicitly read-only transaction. The exact subject
   initially had no TailTag row. PostgreSQL remained private; no public TCP
   proxy was added.
6. Ran `make api-auth-smoke` with the dedicated Development user, exact remote
   target, and interactive hidden secret. The genuine session passed Clerk and
   TailTag verification and returned the exact current-user response.
7. Repeated the read-only predicate, the authenticated smoke, and a final
   exact-subject `COUNT(*) = 1` predicate. The row transitioned from absent to
   present and remained exactly one.
8. Exercised missing, malformed, and invalid credentials against the deployed
   endpoint and verified the generic 401 boundary.
9. Ran one approved, non-persistent expiry probe. It retained the token only in
   process memory, required a successful authenticated response before
   waiting, reused the same token after expiry plus verification skew, observed
   the generic 401, completed provider cleanup, and was then removed with its
   generated bytecode.
10. Parsed the deployed OpenAPI document and verified the exact Bearer security
    and response schema contract without dumping the full document.

## Sanitized command shapes

The reusable public commands were:

```bash
API_BASE_URL=https://<exact-development-api-host> make api-smoke

API_BASE_URL=https://<exact-development-api-host> \
TAILTAG_DEVELOPMENT_API_BASE_URL=https://<exact-development-api-host> \
CLERK_SMOKE_USER_ID=<opaque-development-user-id> \
make api-auth-smoke
```

The database checks used driver-bound parameters and emitted only Boolean
results. Their query shapes were:

```sql
SELECT EXISTS (
  SELECT 1
  FROM accounts_user
  WHERE clerk_user_id = $1
);

SELECT COUNT(*) = 1
FROM accounts_user
WHERE clerk_user_id = $1;
```

No raw Railway variable listing, table dump, model representation, or query
result containing identifiers was produced.

## Persistent and ephemeral state

The dedicated Clerk Development smoke user and its corresponding TailTag
application user are intentional persistent validation state. They must be
reused and must not be silently replaced, deleted, or recreated per run.

Sign-in tickets, Clerk sessions, and bearer tokens were ephemeral per
invocation. The canonical smoke and the bounded expiry probe treated cleanup
failure as an unsuccessful result. No live token survived its process as a
supported credential-transfer artifact.

## Limitations and remaining risk

- Revision attribution is supplied by Railway deployment metadata plus a
  same-target HTTP smoke. API responses do not carry an application build ID,
  so this is not response-level or cryptographic revision proof.
- This validates only the shared Railway and Clerk Development environments.
  It makes no production-readiness or production-authentication claim.
- The expiry causality check was deliberately one-run and non-persistent. It
  did not add another supported Clerk credential workflow; `make
  api-auth-smoke` remains the sole repository-supported live workflow.
- Offline verification means revoking a Clerk session does not retroactively
  revoke an already issued JWT before its expiry. The validated short token
  lifetime bounds that Development smoke exposure; broader revocation design
  remains outside Wave 1.

## Findings and follow-ups

No application defect, authentication-policy exception, data repair, or
follow-up issue was required. The live exercise did not weaken `sid`, session
token, authorized-party, target, redirect, secret-handling, or cleanup
validation.
