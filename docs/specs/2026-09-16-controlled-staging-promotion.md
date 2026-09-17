# Controlled Staging promotion

Issue: [#202](https://github.com/TailTag-Game/tailtag/issues/202). Parent: #197.
Dependencies: #200 Staging boundary and #201 build/deployment identity.

## Status and authorization

The user-approved behavior below is frozen for implementation handoff.
Scope: STANDARD COMPACT, one maintainer promotion review unit.
Assurance: SECURITY, RELIABILITY, TEST ADEQUACY, DATA INTEGRITY.
Completed: alignment, repository inspection, authenticated read-only interface
research, Acceptance Contract, Test Surface Contract, Scope Guard and plan.
Completed additionally: environment baseline (`make api-check`: 1,529 tests),
74 independently authored acceptance cases and parent test-adequacy approval.
Draft review findings have scoped regression coverage.
Completed additionally: final `make api-check` (1,604 tests and all static/
Django/schema/Gunicorn gates), documentation doctor and fresh Compact review.
Current: normal reviewed publication/merge. Pending: one authorized live
promotion, final verification and evidence accounting.

Research/design is complete. The user subsequently authorized continuing until
issue completion, including implementation, normal reviewed publication/merge
and one Staging promotion. Infrastructure/configuration changes remain excluded.
The [implementation plan](2026-09-16-controlled-staging-promotion-implementation-plan.md)
is the execution handoff. No #202 live acceptance has been performed.

## Acceptance Contract

1. Accept candidate S only as a full lowercase 40-character immutable Git SHA.
   Resolve S through `TailTag-Game/tailtag`; require returned SHA == S.
2. Resolve accepted remote `main` to immutable M through GitHub immediately
   during eligibility checking. Compare S...M through GitHub, requiring
   `base_commit.sha == S`, `merge_base_commit.sha == S`, `behind_by == 0`, and
   status `ahead` or `identical`. Local branches are not evidence. S need not
   equal M, and subsequent advancement of main does not change S.
3. Require at least one completed successful run of
   `.github/workflows/api.yml` with exact `head_sha == S` and `event == push`
   in the canonical repository. Preserve its run ID and attempt as evidence.
   The push workflow is authoritative: no PR run, dispatch, check-name-only
   substitution, backend-relevance reimplementation or mutable-head validation.
4. The sole supported submission is `serviceInstanceDeployV2` with explicit
   `commitSha = S` and canonical Staging/API IDs. Capture the returned deployment
   ID immediately as D and durably checkpoint the safe S/D association before
   any lifecycle observation. Never substitute a latest-deployment lookup.
5. Validate every exact-D record against D and canonical project, service and
   Staging environment. Deployment timestamp is D's unchanged `createdAt`, as
   defined by #201. Query D's lifecycle and events, paging events to completion.
6. Observe the existing configured pre-deploy migration gate, application
   startup and readiness contract. Success requires deployment `SUCCESS`, a
   completed non-skipped PRE_DEPLOY_COMMAND event without error, completed
   CREATE_CONTAINER and HEALTHCHECK events without errors/skips, and a RUNNING
   instance belonging to D. Completion alone is not success evidence.
7. Execute #201's existing backend identity command on an explicitly selected
   RUNNING instance returned for D. Pass its actual output unchanged to the
   existing exact-deployment join; require joined deployment ID == D,
   environment == staging and image-local source SHA == S. No hand-constructed
   identity tuple, runtime SHA substitute, new endpoint or version mechanism.
8. Run the existing credential-free canonical Staging HTTP smoke from the
   repository root and require success. It checks liveness, readiness, schema and docs; it does not redefine
   readiness or cryptographically bind HTTP responses to D.
9. Immediately before declaring success, query canonical Staging/API
   `activeDeployments`, validate the target and require membership of exact D,
   with D still SUCCESS and a RUNNING instance. This is an active-set comparison,
   not permission to select a different deployment. If D is absent and another
   deployment is active, record SUPERSEDED; if none is active, record INACTIVE.
   Neither is current-promotion success. Preserve previously established
   historical results for D. Failed/unknown final membership cannot pass.
10. Any migration/startup/readiness/identity/smoke failure ends ordinary
    promotion. Unknown or incomplete evidence cannot pass. Ambiguous migration
    or database state hands off to OR-7. No automatic submission retry,
    rollback, reverse migration, restore or database recovery.
11. Repository-owned durable JSON evidence contains every required field below,
    including failed or interrupted outcomes. Persist only allowlisted public
    identities and fixed outcome codes, never raw metadata/logs/configuration.
12. Validate final implementation through one normal reviewed Staging promotion
    of an eligible main ancestor, after separate live-operation authorization.
    Keep Staging autodeploy disabled and Development delivery unchanged.

Effective success predicate:

```text
eligible_main_ancestor(S)
AND successful_push_api_validation(S)
AND exact_SHA_submission(S) -> D
AND deployment(D) succeeded
AND migration(D) succeeded
AND application_startup(D) succeeded
AND exact_instance_identity(D).source_sha == S
AND approved_readiness(D) succeeded
AND existing_Staging_HTTP_smoke passed
AND D remains active at declaration
```

## Live interface research (2026-09-16 local date)

GitHub account verification returned `FinnThePanther`. Railway `whoami`
verified Finn's approved name/email. Only read queries and schema inspection
were executed. No mutation was submitted. The live schema, rather than an
older API cookbook, is authoritative for the shapes below.

Canonical IDs: project `85324de4-be6a-49c3-a3f9-6cac13877849`, API service
`2247da27-97df-4d5d-b1dc-d21eeb7901d9`, Staging environment
`5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e`. Remote project inspection returned only
`development` and `staging`. The scoped deployment-trigger connection was empty,
with `hasNextPage == false`, confirming disabled Staging GitHub autodeploy.
Allowlisted configuration comparisons confirmed canonical repository source,
no image-only source, existing API root, approved migration and readiness path.
No Dockerfile-path override is required or authorized by this issue.

### Exact-SHA submission (shape verified; not executed)

```graphql
mutation PromoteStaging($serviceId: String!, $environmentId: String!, $commitSha: String!) {
  serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId, commitSha: $commitSha)
}
```

Schema arguments are `serviceId: String!`, `environmentId: String!`, and
`commitSha: String`; return is `String!`, described as a deployment ID, not an
object. The operator document deliberately makes commitSha non-null and always
supplies S. Response shape is
`{"data":{"serviceInstanceDeployV2":"<D>"}}`. Reject GraphQL errors,
missing/malformed ID, or transport failure; do not resubmit. A lost response
may mean submission occurred: record indeterminate submission and stop rather
than discovering a substitute D through latest metadata.

### Exact-D lifecycle

```graphql
query PromotionObservation($id: String!, $after: String) {
  deployment(id: $id) {
    id projectId serviceId environmentId createdAt status deploymentStopped
    environment { name }
    instances { id status }
  }
  deploymentEvents(id: $id, first: 100, after: $after) {
    edges { node { id step completedAt payload { skipped error } } }
    pageInfo { hasNextPage endCursor }
  }
}
```

`Query.deployment(id: String!): Deployment!`.
`Deployment.instances: [DeploymentDeploymentInstance!]!`; instance `id` is
`String!`, `status` is `DeploymentInstanceStatus!`. Events are a cursor
connection; `completedAt` and payload are nullable, `skipped` is nullable
Boolean and `error` is nullable String. Consume errors in memory as presence
only; never output/store their text. Do not request payload detail/reason,
diagnosis, URLs or general logs. Duplicate, conflicting or insufficient stage
evidence is indeterminate; missing payload alone is not an error, as the live
successful example has nullable skipped fields.

Deployment statuses: BUILDING, CRASHED, DEPLOYING, FAILED, INITIALIZING,
NEEDS_APPROVAL, QUEUED, REMOVED, REMOVING, SKIPPED, SLEEPING, SUCCESS, WAITING.
INITIALIZING/QUEUED/WAITING/BUILDING/DEPLOYING are progress, not success.
CRASHED/FAILED/SKIPPED/REMOVED/REMOVING end ordinary promotion.
NEEDS_APPROVAL/SLEEPING cannot pass; stop without changing platform controls.
Unknown future status fails closed. Polling successful read queries observes
progress; a failed authenticated query ends the task rather than being retried.
A bounded observation timeout yields INDETERMINATE, not a deployment failure
inference or permission to cancel/redeploy.

Instance statuses: CRASHED, CREATED, EXITED, INITIALIZING, REMOVED, REMOVING,
RESTARTING, RUNNING, SKIPPED, STOPPED. Select only a RUNNING instance from D,
never the default SSH instance. Historical stopped/removed instances alongside
a current RUNNING instance are expected and do not alone fail D.

Event steps include PRE_DEPLOY_COMMAND, CREATE_CONTAINER, HEALTHCHECK, BUILD_IMAGE,
CONFIGURE_NETWORK, DRAIN_INSTANCES, MIGRATE_VOLUMES, PUBLISH_IMAGE, SNAPSHOT_CODE,
WAIT_FOR_DEPENDENCIES. MIGRATE_VOLUMES is not the Django migration gate.
Read-only lookup of historical D `bd411e7e-cbc9-4c3e-b332-9f7e522b4b72` found
completed PRE_DEPLOY_COMMAND, CREATE_CONTAINER and HEALTHCHECK events, without
error or affirmative skip, status SUCCESS and a RUNNING instance.

There is no separate structured migration-result field on Deployment.
The configured command remains
`python manage.py migrate --settings=config.settings.production --noinput`.
[Railway's pre-deploy contract](https://docs.railway.com/deployments/pre-deploy-command)
requires exit zero to proceed; failure prevents deployment and is not retried.
Combine the matching configured gate, completed event and subsequent successful
lifecycle to establish success. An event error establishes gate failure,
not that database state is clean. Absence establishes NOT_REACHED only when
exact-D diagnostics affirm the attempt stopped before the gate; otherwise use
INDETERMINATE. The operator may inspect the smallest exact-D pre-deploy/build
diagnostic surface to classify failure, retaining only fixed sanitized outcomes.
Uncertain database state belongs to OR-7.

[Railway's healthcheck contract](https://docs.railway.com/deployments/healthchecks)
gates activation on the configured check. The observed path is `/health/ready`.
This is a deployment-time gate, not continuous monitoring. #202 changes neither
the path nor response semantics; OR-4 owns detailed readiness behavior.

### Final active check

```graphql
query PromotionActive($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId environmentId
    activeDeployments {
      id projectId serviceId environmentId status instances { id status }
    }
  }
}
```

`Query.serviceInstance(...): ServiceInstance!` and
`ServiceInstance.activeDeployments: [Deployment!]!`, described as all currently
active deployed/running deployments. It is not a connection or latest object.
The live read query succeeded with the canonical selectors. Membership is a
point-in-time claim, not a guarantee after declaration. Multiple active entries
must not be reduced to the first or latest; evaluate exact D's membership.

### GitHub eligibility

Use authenticated REST through gh, verifying `gh api user --jq .login` exactly
before each authenticated operation. Stop on identity/auth/access failure; do
not change credentials or use another transport as a fallback.

```text
GET /repos/TailTag-Game/tailtag/commits/S
GET /repos/TailTag-Game/tailtag/commits/main          -> capture M = .sha
GET /repos/TailTag-Game/tailtag/compare/S...M?per_page=1
GET /repos/TailTag-Game/tailtag/actions/workflows/api.yml/runs
    ?head_sha=S&event=push&status=success&per_page=100
GET /repos/TailTag-Game/tailtag/actions/runs/RUN_ID
```

Follow run-list pagination and revalidate the selected run's path, repository,
head_sha, event, completed status and successful conclusion. Preserve run ID
and attempt. No successful qualifying run means ineligible. Main resolution
and compare use remote immutable objects; no fetch or stale local ref is needed.
Compare uses merge-base/top-level fields, not the paginated commit/file listing.
Accepted-main ancestry refers to the protected canonical main history; this
does not claim to detect or legitimize privileged historical protection bypass.

Live remote M was `2586ade0c1115e090044c9385831b33538918dcf`. An older main
commit `eb518d36baa21b7943acd9744f2499d80d527e61` resolved in the repository;
comparison to M returned ahead, behind_by zero and merge-base equal to that
older commit. The exact-M workflow list and exact run lookup returned run
`35179642379`, attempt 1, canonical repository/path, push, completed, success.
These are interface proofs, not a selected deployment candidate or #202 proof.

Historical #201 image source `84237fd2e8db35ecf06c33a8eb09d104858195ff` compared
to M as diverged, with a different merge-base and behind_by 2. It remains valid
historical identity evidence but cannot pass #202 eligibility. A reviewed main
ancestor containing the implementation is required for final live proof.

Primary references: [GitHub commit comparison](https://docs.github.com/en/rest/commits/commits#compare-two-commits)
and [workflow run queries](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow).

## Frozen implementation design

Add one opt-in maintainer operator script `scripts/api_staging_promote.py`.
It orchestrates the supported flow locally using existing gh/Railway CLIs and
the existing #201 join and Staging HTTP smoke. No CI deployment workflow,
service-side Railway credential, new dependency or application change.

Entry point: `--source-sha S --confirm promote-tailtag-staging`.
Evidence directory is fixed to repository-owned
`docs/development/staging-deployments/`; successful submission creates D.json.
Before mutation, validate local evidence directory writability, approved
identity, candidate eligibility and canonical target/source/autodeploy/migration/
readiness configuration. Require a coordinated maintainer window with no
concurrent configuration changes or unrelated pending changes. A mismatch stops
without repairing it. Repeat Railway identity verification immediately before
the sole exact-SHA mutation. GitHub author/committer checks apply before any
later commit; the operator does not commit or publish evidence.

Capture both subprocess streams without a shell; never forward raw CLI errors.
Once returned D is validated, atomically write an initial record with pending
observations. Update that same allowlisted record as observations are obtained.
Use a 30-second request timeout, poll successful lifecycle reads every five
seconds up to 20 minutes; timeouts stop observation, not the Railway deployment.
Do not automatically rerun a failed subprocess or mutation. Record the safest
known result before stopping, without attempting more remote operations after
identity/authentication failure. If persistence fails after submission, surface
only safe S and D and stop; operator preserves them in the approved repository
record without resubmission. Pre-submission rejection creates no fictional D.

After positive lifecycle evidence, execute the documented explicit-instance
#201 readback and pass actual stdout to `scripts/api_deployment_identity.py`.
Capture its four-field joined output and compare S/D/staging; reuse its
createdAt meaning and exact-D source join. Existing raw metadata consumed
internally by that helper must never be retained in evidence.
Run `API_BASE_URL=https://staging.tailtag.app make api-smoke` with the child
working directory explicitly set to the repository root, recording fixed
outcomes only. Then perform the final active query as the final remote gate
before atomic success declaration. Active membership cannot resurrect an
earlier failed identity, migration, readiness or smoke check.

HTTP smoke targets a shared canonical endpoint. It has no response-level image
attestation. Identity comes from exact-D SSH and join; the final active check
limits the current-promotion claim to its observation instant. No new version
endpoint or exclusive-active-entry requirement is introduced.

## Evidence contract

Each D.json contains exactly the following fields; no arbitrary diagnostic text:

```text
source_sha, deployment_id, environment, deployment_timestamp,
accepted_main_sha, validation_run_id, validation_run_attempt,
deployment_outcome, migration_outcome, startup_outcome, readiness_outcome,
identity_outcome, smoke_outcome, final_active_state, overall_outcome
```

Identities are validated full SHAs/UUIDs, environment is `staging`, timestamp
is exact D.createdAt or null until observed, validation IDs are positive integers.
Gate outcomes use PENDING, SUCCEEDED, FAILED, NOT_REACHED or INDETERMINATE.
Final active state uses NOT_CHECKED, ACTIVE, SUPERSEDED, INACTIVE, INDETERMINATE.
Overall uses PENDING, SUCCEEDED, FAILED, SUPERSEDED, INDETERMINATE,
OR7_HANDOFF. Success requires all gates SUCCEEDED and active state ACTIVE.
Supersession preserves past successful gate values but changes overall outcome
to SUPERSEDED. An interrupted run is INDETERMINATE until manually accounted for;
it is never silently treated as success. Diagnostic classification may change
an indeterminate failure record only after exact-D inspection and review, without
submitting another deployment or rewriting historical successful observations.

Do not retain environment values, raw meta/event payload/error strings, secrets,
credentials, tokens, private URLs, snapshots or indiscriminate logs. No screenshots
or log attachments are required. Sanitized records are reviewed before commit.
No test fixture is claimed as real deployment evidence.

## Test Surface Contract

Test the opt-in script's `main()` via existing subprocess mocking patterns and
temporary evidence directories bound by tests at the internal `_REPOSITORY_ROOT`
filesystem constant. This is not a CLI target/path override.
Internal pure parsing/predicate helpers may be exercised directly; they accept
decoded objects and return validated allowlisted data or sanitized failures.
The production entry point fixes canonical targets and repository evidence path.
No configurable target, runtime SHA override or new backend injection API.

Fake gh/Railway responses cover exact commit resolution, ahead/identical/diverged
comparison, paginated workflow lists and exact run verification, mutation return,
exact-D deployment/events, instance selection, #201 actual-output subprocess join,
smoke result and active-set membership. Assert query variables and subprocess
arguments for S, D and instance ID. Tests never contact Railway/GitHub, perform
SSH, start databases, deploy or provision resources. Independently authored tests
receive this contract, not a proposed implementation.

Required mutants to reject: current-main equality requirement; stale local ancestry;
PR/dispatch or different-SHA validation; mutable/no-SHA mutation; latest-D lookup;
completed-but-skipped/error migration; completion alone treated as success;
wrong instance/default SSH; invented identity input; wrong image source; smoke
failure ignored; active check omitted/wrong D; supersession reported successful;
automatic retry/recovery; arbitrary diagnostic material retained. Tests must also
accept an older valid ancestor while main advances and accept historical removed
instances alongside a selected RUNNING instance.

## Scope Guard

Outcome: one reviewed exact-SHA Staging promotion procedure/operator with durable
sanitized exact-D evidence and the complete success predicate.
Non-goals: alternate promotion paths, autodeploy, Production, OR-7 recovery,
readiness redesign, observability, destructive tests, new infrastructure,
dependency changes and unrelated backend behavior.
Expected files: operator script; its focused existing-suite test file; Makefile,
Pyright and existing backend-CI/Semgrep verification registries and their relevant
path matrices; existing Staging runbook; this spec/plan; real allowlisted D.json.
Preserve #201 implementation unchanged unless a contract contradiction requires
stopping and replanning. No Dockerfile, application code, schema or CI workflow
change is expected.
Proof: independent tests/adequacy, narrow tests, `make api-check` including
Semgrep, fresh Compact reviewer, one separately authorized normal reviewed
Staging promotion, parent evidence review, `./scripts/doctor.sh` and
`git diff --check`. No Docker/Compose resources were created in research.
