# Post-deploy HTTP smoke verification review

Date: 2026-08-15

## Scope

This review records the #77 GitHub Actions post-deploy verifier. It covers the
workflow's event filtering, real-HTTP smoke invocation, diagnostics, and the
boundary with Railway deployment/migration work. It does not validate automatic
`main`-to-development delivery, rollback, redeploy, or exact active-revision
correlation; those remain #78 concerns.

## Observed integration evidence

The repository's Railway GitHub integration created deployment `5914133382` for
commit/ref `e02dd80d8a1d7c57114830e52977cc1da8f53f97`. Its successful deployment
status was `16833057725`. The observed public GitHub deployment fields were:

| Field | Observed value | Verifier use |
| --- | --- | --- |
| `deployment_status.state` | `success` | Requires a completed successful deployment. |
| `deployment.environment` | `TailTag / development` | Limits automatic verification to the shared non-production environment. |
| `deployment.creator.login` | `railway-app[bot]` | Limits automatic verification to Railway-created deployments. |
| `deployment.sha` / `deployment.ref` | Git commit SHA | Preserved for reporting and used to check out the verifier revision. |
| `deployment.id` / `deployment_status.id` | GitHub numeric identifiers | Preserved for event-to-run diagnostics. |
| `deployment_status.environment_url` | Railway dashboard URL | Not used as the API target. |

The deployment status URL was a Railway dashboard link rather than the public
API URL. The verifier therefore obtains the public URL from the non-secret
repository Actions variable `TAILTAG_DEVELOPMENT_API_BASE_URL`; it does not
need a Railway token.

## Implemented boundary

The workflow rejects unrelated events with a concise sanitized skip message and
does not print the raw GitHub event payload. Relevant events and manual reruns
converge on `API_BASE_URL=... make api-smoke`. The workflow has read-only
repository permissions, provisions no PostgreSQL service, and has no Railway
CLI/API, migration, rollback, redeploy, or database-mutation operation.

Smoke output remains endpoint-specific. An unreachable API reports connection
failure at `/health/live`; a reachable API with an unhealthy PostgreSQL
dependency can report liveness success and readiness HTTP 503. No database
exception, hostname, credential, or topology detail is exposed.

## Verification evidence

| Check | Result |
| --- | --- |
| Existing developer-command baseline with non-secret local test settings | PASS — 12 tests. |
| Focused workflow-contract test before implementation | EXPECTED FAIL — workflow file absent. |
| Focused workflow-contract and developer-command regression tests | PASS — 13 tests. |
| Direct canonical smoke run against the public Railway development API | PASS — liveness, readiness, schema, and docs each returned HTTP 200. |
| `actionlint` | Not run — not installed in the local environment. |
| Healthy remote Actions verifier | Pending a committed/pushed workflow, repository variable configuration, and authorized manual dispatch. |
| Safe failed remote Actions verifier | Pending separate authorization for a temporary repository-variable change; no Railway or PostgreSQL disruption is permitted. |

The event identifies the Railway deployment that triggered verification. The
HTTP request proves the shared development endpoint satisfied the smoke contract
after that event; it does not prove each response was served by the triggering
commit SHA.

## Remaining risk

Because the workflow has not yet been committed, pushed, or dispatched, GitHub
Actions runtime parsing and remote pass/fail signaling remain to be exercised.
This is intentionally not hidden by a local approximation. The stable public
endpoint also cannot independently prove exact active revision without stronger
orchestration or platform integration, which is deferred to #78 if needed.
