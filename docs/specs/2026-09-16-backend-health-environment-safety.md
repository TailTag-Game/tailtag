# Backend liveness, readiness, and environment safety

Issue: [#203](https://github.com/TailTag-Game/tailtag/issues/203).
Parent: #197. Staging prerequisite: #200. Identity source: #201.
Consumer: future #199 tooling.

## Status and phase ledger

The user-approved behavioral boundaries below are frozen. Local implementation, verification,
and independent review are complete; live Staging proof passed on 2026-09-17.
Execution: STANDARD COMPACT. Assurance: SECURITY, RELIABILITY, TEST ADEQUACY.
Completed: alignment, focused repository reconnaissance.
Completed additionally: timestamp boundary correction and implementation planning.
Completed additionally: environment baseline (`make api-check`: 1,604 tests,
format/lint/type/Semgrep/system/migration/schema/Gunicorn gates passed).
Completed additionally: independent acceptance tests and parent adequacy/scope
approval. Health tests have 24 intended behavioral failures and eight preserved
passes before implementation; preflight tests await the new module and CI path.
Completed additionally: independent production implementation; 151 focused tests,
Ruff and strict Pyright passed. Default-options regression was reproduced by two
independent characterization cases, then fixed without weakening assertions.
Completed additionally: parent `make api-check` passed 1,707 tests and all
format/lint/type/Semgrep/system/migration/schema/Gunicorn gates. Semgrep ran nine
rules with zero findings. Production-profile focused tests passed 105 cases.
Completed additionally: fresh Compact review passed with no material findings.
Plausible-mutant analysis confirmed tests reject origin/environment/status-only
guards, redirects, skipped config, null/malformed identity, failed readiness,
identity changes, timestamp expansion, and raw diagnostics.
Current: completed acceptance; live evidence publication.
Completed additionally: Gunicorn black-box checks with healthy and unavailable
PostgreSQL; liveness stays 200, readiness fails safely with 503, and all health
responses are allowlisted and no-store. Both task Gunicorn processes were stopped.
AC-1 through AC-9 have local acceptance and assurance evidence; AC-10
deterministic/review/documentation and live canonical Staging proof now pass.
Public preflight is credential-free; timestamp correlation is optional operator
enrichment. Implementation PR #235 is merged; the approved controlled Staging
promotion and credential-free public proof succeeded. No #199 implementation
was performed.

Implementation was authorized after plan approval. The first baseline attempt
passed static gates but lacked local Django settings; the documented local-only
example supplies those values for subsequent checks. Task-created Compose project
`tailtag-issue-203` owns one PostgreSQL container and network for testing. Existing
stopped containers were not started. Preserve its volume and remove only its
disposable container/network after verification.

Cleanup evidence: `docker compose ... -p tailtag-issue-203 ... down` removed
the task container and network; filtered inventory confirmed neither remained.
The persistent `tailtag-issue-203_postgres_data` volume is intentionally retained
under the repository's data-preservation policy. Unrelated containers and images
were untouched. `./scripts/doctor.sh` passed required checks on the feature branch;
the optional Dev Container CLI remains unavailable.

Approved test coverage: liveness/local readiness (AC-1/2/4), DB failure hygiene
(AC-2/9), effective deployed configuration and identity/runtime denials
(AC-2/3/4/9), public identity (AC-6/7/9), origin rejection before networking
(AC-5), strict identity/readiness and stable observation (AC-2/6/7/8), bounded
proxy-free/no-redirect transport and duplicate-key rejection (AC-5/6/9), safe CLI
(AC-5/7/9), and standalone script CI relevance (AC-10). Tests use real ephemeral
RSA validation and PostgreSQL success; no vendor availability dependency.
Added assurance coverage was separately reviewed against AC-3/6/9: effective
storage overrides/constructor validity, malformed host/profile/local Clerk/DB
configuration, incomplete HTTP reads, and bounded JSON parser failure. Test
fixtures must use an allowed request host to reach the view. Empty secret keys
are rejected by Django startup or signing middleware before a real health view
can run; test the configuration validator/view directly with RequestFactory for
that case. No production middleware bypass is authorized. An unavailable process
or pre-view failure still cannot pass public preflight.

## Acceptance Contract

1. Liveness means this application process can answer the request. Preserve
   `/health/live`, HTTP 200, `{"status":"ok"}`, and `Cache-Control: no-store`.
   Do not query PostgreSQL, Clerk, storage, or the Railway control plane to
   answer liveness. An unhealthy dependency does not make a live process dead.
2. Readiness means this process's current effective local configuration and
   required PostgreSQL connection permit normal API traffic safely. Preserve
   `/health/ready`, successful HTTP 200 with `{"status":"ok"}`, and non-cacheable
   responses. A lightweight query must succeed against the configured PostgreSQL
   database. Connection/query failure must return sanitized HTTP 503.
3. Readiness must fail closed on missing, malformed, or contradictory required
   environment, authentication, media/storage, and deployed build/runtime identity
   configuration. It must also reject configuration known to make ordinary API
   operation unsafe or incorrectly routed. Reuse existing application loaders
   and validators; do not duplicate their parsing rules in health views.
4. Clerk and media/storage readiness checks are local validity checks. Never
   actively contact Clerk, R2/Cloudflare, or Railway from readiness. These checks
   do not prove credential authorization, bucket existence, vendor availability,
   or correct live token verification. PostgreSQL is the sole live dependency
   probe in this contract. Additional universal synchronous dependencies require
   an explicit future decision.
5. Before any acceptance/simulation traffic, a reusable target validator must
   reject any proposed base URL other than the exact string
   `https://staging.tailtag.app`, before issuing a request. Reject HTTP, credentials,
   ports (including explicit 443), paths (including a trailing slash), queries,
   fragments, whitespace, case variants, hostname overrides, IPs, alternate hosts,
   localhost, Development, Production, malformed inputs, and unknown targets.
   Do not normalize an unapproved input into an approved origin.
6. After URL approval, obtain safe backend identity and readiness information
   over HTTPS without following redirects. Require explicit
   `environment == "staging"`, valid non-null #201 immutable source SHA and
   deployment identity, and passing
   readiness. Neither the approved origin nor the reported environment alone is
   sufficient. Missing, malformed, contradictory, redirected, unsuccessful,
   unavailable, or otherwise uncertain responses fail closed.
7. The validator returns only the observed sanitized #201 identity fields:
   `source_sha`, `deployment_id`, `environment`.
   Source SHA is 40 lowercase hexadecimal characters; deployment ID is a canonical
   UUID. Deployment timestamp is not required for traffic-safety preflight.
   Reuse #201; do not invent another
   version source, runtime SHA override, or timestamp substitute.
8. This protects against accidental/misconfigured targeting, not cryptographic
   remote attestation. It does not require an expected candidate SHA or prove
   that an HTTP response belongs to a particular Railway instance. #201's stronger
   exact-deployment operator proof remains separate. Future #199 reports must
   capture the observed identity and may optionally compare an expected SHA.
9. Public responses remain small and allowlisted. Failures use fixed sanitized
   status/classification fields; existing `{"status":"unavailable"}` is sufficient
   for readiness. Never expose raw exceptions, stack traces, credentials, tokens,
   database/storage URLs, Clerk keys/authorized parties, private bucket/account
   identifiers, arbitrary environment values, or dependency response bodies.
10. Automated evidence must cover healthy/unhealthy health behavior, database
    and configuration failures, strict target rejection, malformed/contradictory
    identity, redirect rejection, and readiness denial. Validate the implemented
    contract against Staging and document it without private operational values.

Traffic may proceed only when the exact canonical requested origin, affirmative
Staging identity, valid and captured #201 identity, and passing readiness all hold.
Any uncertainty denies traffic. Passing preflight is an observation, not a promise
that readiness or deployment identity cannot change later.

## Repository research

- `services/api/health/views.py`: existing unauthenticated, non-cacheable liveness
  and readiness responses already distinguish process health from DB access.
  Readiness calls `ensure_connection()` and `SELECT 1`, catches `DatabaseError`,
  and returns fixed HTTP 503 without exception details.
- `services/api/tests/test_health.py`: existing liveness independence, real
  PostgreSQL success, and sanitized query-failure tests are the starting surface.
- `services/api/config/settings/production.py`: startup requires Django secret,
  host/origin values, database URL, and S3 settings. It uses shared Clerk/media
  loaders. Startup validation remains valuable; readiness must evaluate effective
  configuration rather than merely assert that the module once imported.
- `services/api/config/settings/clerk.py`: validates enablement, RSA public key,
  and authorized-party origins locally. Disabled authentication returns `None`;
  this is an intentional local-development behavior but does not satisfy required
  deployed authentication readiness.
- `services/api/config/settings/media.py`: validates required S3 settings and
  HTTPS endpoint locally, with redacted configuration representation. It does
  not test remote credentials. Production uses `media.storage.S3MediaStorage`;
  local settings intentionally use filesystem storage.
- `services/api/config/build_identity.py`: canonical baked artifact SHA plus
  runtime Railway deployment ID/environment. Staging requires SHA and ID;
  local absent identity remains explicit null. No timestamp is available here.
- `scripts/api_deployment_identity.py`: validates the three-field backend tuple
  and joins exact deployment D to Railway project/service/environment/source and
  `createdAt`. Only the operator-side joined result contains the fourth field,
  `deployment_timestamp`. No latest-deployment substitution is permitted.
- `scripts/api_smoke.py`: reusable no-redirect transport pattern, five-second
  request timeout, and existing general-purpose health/schema/docs smoke. Its
  permissive HTTP(S) URL parser and status-only checks are not a Staging guard;
  preserve its Development/local use rather than tightening it globally.
- `scripts/api_staging_auth_smoke.py`: exact canonical URL and explicit
  Staging/API runtime targeting already protect a specialized authenticated smoke.
  Its synthetic-user/session workflow belongs to that command, not this primitive.
- `scripts/api_auth_smoke.py`: existing strict root-origin parsing and extensive
  malformed-URL tests are useful characterization evidence, but its policy allows
  local/Development targets and therefore is not the #203 policy. Authenticated
  smoke transports already use proxy-free openers with redirects disabled; reuse
  this transport convention so ambient proxy settings cannot silently reroute
  the target guard. Existing Staging smoke tests assert rejection before runtime
  events; preserve that ordering in the new primitive.
- `scripts/api_staging_promote.py` and `docs/development/staging.md`: controlled
  promotion already consumes `/health/ready`; stronger readiness affects that
  deployment gate. Existing exact-deployment evidence and sanitized records are
  distinct from public HTTP identity. No chaos test is needed for validation.

## Design boundaries

Preserve existing health paths and success bodies. Introduce a narrowly scoped
safe identity surface backed by `config.build_identity.get_identity()` and a
separate reusable Staging preflight primitive. Public identity exposure of the
allowlisted fields is authorized by #203's user-approved boundary; #201 originally
provided only a component/operator command, so document this extension explicitly
without changing its canonical source semantics.

The [#201 specification](2026-09-16-backend-build-deployment-identity.md)
intentionally separates three-field running-application identity from operator
control-plane enrichment. Public preflight must not authenticate to Railway,
require an exact-deployment operator join, or require `deployment_timestamp`.
Do not copy a Railway timestamp into the backend or add a public metadata
mechanism to supply it. A maintainer may optionally correlate the captured
`deployment_id` through #201's exact-D procedure to obtain `createdAt` and stronger
operator proof. That enrichment does not affect permission for public traffic
and is not part of #203 implementation. Future #199 reports capture the observed
source SHA and deployment ID without requiring Railway operator credentials.

Deployed Staging must have enabled valid Clerk authentication, configured S3
storage, production-safe effective settings, recognized environment configuration,
and valid #201 identity. Preserve intentional local Development settings and
filesystem storage; they must never qualify as a Staging acceptance target.
The implementation plan defines the effective-settings validation seam and
deployed environment requirements. Do not assert isolation of private Clerk/R2 resources
from generic configuration syntax alone; existing Staging provisioning and smoke
proof remain authoritative for that stronger operational claim.

## Test Surface Contract

Use the existing Django client and health tests. Observe HTTP status, exact safe
bodies, and non-cacheable headers. Use real PostgreSQL for healthy readiness;
controlled connection/cursor failures for failure paths. Configuration cases use
existing loader mapping seams and effective Django settings. Reuse #201 artifact
and runtime mapping tests; no test-only public production APIs.

The small preflight primitive accepts a proposed origin and returns sanitized
identity or a fixed denial. Test network responses through the normal HTTP
transport boundary with mocked/local responses; production origin approval cannot
be bypassed by a configurable localhost URL. Test denial before any transport
invocation for invalid origins. The implementation plan freezes signatures
before independent test authorship; no timestamp input/lookup seam is needed.

Require bounded timeouts/response reads and strict allowlisted response schemas.
Tests must reject redirects, invalid JSON/types, missing/null/extra fields,
invalid SHA/UUID, identity mismatches, non-Staging environment, network
failure, and failed readiness. Assert no vendor calls from health paths and no
sensitive diagnostics from either HTTP or command failure paths.

Plausible-mutant review must assess guards accepting environment alone, accepting
origin alone, following redirects, allowing URL overrides, ignoring readiness,
accepting missing identity, requiring Railway credentials, and emitting raw
exceptions. Do not introduce mutation infrastructure for this issue.

## Scope Guard and verification

Outcome: freeze and subsequently implement only the health/configuration readiness
and small reusable Staging target-safety contract above.

Non-goals: #198 observability, #199 runners/scenarios/synthetic users/load/reports,
Production support/launch, remote attestation, expected-SHA pinning, vendor probes,
dependency dumps, deliberate failure chaos, reset/reseed, unrelated API behavior,
new dependencies, schema/data migrations, or parallel build identity sources.

Change surface: this spec, `docs/specs/README.md`, and the
[implementation plan](2026-09-16-backend-health-environment-safety-implementation-plan.md), health/configuration/identity modules, URL
registration, one small preflight script/module, relevant existing test surfaces,
existing check lists as necessary, the API health documentation, and the Staging runbook. Timestamp delivery
and operator-join changes are excluded.

Documentation proof: `./scripts/doctor.sh`, `git diff --check`, scope review.
Later implementation proof: environment-ready baseline; focused acceptance and
regression tests; `make api-check` including Semgrep; independent review; sanitized
canonical Staging preflight/readiness evidence. No deliberate live outage.
Record any unavailable verification, retained test resources, and limitations.
Staging publication/deployment requires the applicable authorization and identity
checks. No migrations or persistent-data changes are planned; rollback is to the
previous reviewed backend revision through the existing controlled workflow.

## Specification verification

On 2026-09-16, `./scripts/doctor.sh` passed required checks on
`docs/203-health-safety-contract`. The optional Dev Container CLI was unavailable.
`git diff --check` and the new-spec whitespace check passed. Read-only independent
exploration confirmed the existing target guards and the #201 timestamp gap.
No application changes, live Staging requests, or task-created test containers.

## Live Staging acceptance evidence (2026-09-17)

Merged PR #235 provided source `04f8383fe750bec712ced27a1932b82b1eabb292`;
exact successful push API validation was run 35189808670, attempt 1. The approved
#202 command submitted it once and returned deployment
`57f17ef7-7b34-4c2f-9272-b8091b1eafad`. Its
[sanitized promotion record](../development/staging-deployments/57f17ef7-7b34-4c2f-9272-b8091b1eafad.json)
records all required gates SUCCEEDED, final state ACTIVE, and overall SUCCEEDED.

Independent public GETs at exactly `https://staging.tailtag.app` observed live,
ready, and identity HTTP 200, exact approved small JSON, `application/json`, and
`no-store`, with no redirect. Both the credential-free CLI and reusable primitive
passed, capturing the source/deployment above and environment `staging`. Nine
unsafe-origin variants failed before transport. The
[Staging runbook](../development/staging.md#health-and-public-staging-preflight-203)
retains the meanings, invocation, limitations, and operator-evidence distinction.

The optional operator record includes deployment timestamp; it was not supplied
to or required by the public preflight. No live failure chaos, configuration
changes, vendor probes, synthetic users, or acceptance/load traffic were added.
All acceptance items now have evidence. Observations are point-in-time.
