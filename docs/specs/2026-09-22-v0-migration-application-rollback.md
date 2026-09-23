# V0 migration and application rollback contract

Issue: [#206](https://github.com/TailTag-Game/tailtag/issues/206).
Parent: #197. Prerequisites: #200 and #202 (complete). Blocks: OR-8.

## Status and phase ledger

The user-approved migration, compatibility, recovery, and no-live-rehearsal
decisions are frozen by this contract. Execution is STANDARD EXPANDED with
MIGRATION, DATA INTEGRITY, RELIABILITY, and TEST ADEQUACY assurance.

Completed: alignment; repository and live Railway reconnaissance; migration and
schema review; disposable PostgreSQL compatibility proof; the final NO-GO
decision; independent tests and documentation; authoritative `make api-check`
(2,031 tests plus static, schema, and server gates); final specification and
code reviews with no unresolved findings; and task cleanup. No live Staging
mutation occurred. `PRE_DEPLOY_COMMAND` behavior during rollback remains
unverified.

The implementation and test handoff is maintained in
[`2026-09-22-v0-migration-application-rollback-implementation-plan.md`](2026-09-22-v0-migration-application-rollback-implementation-plan.md).

No live Staging rollback is authorized or required by #206. The allowed
alternate acceptance path applies: the exact unverified live boundary and the
safe evidence-based fallback are recorded because affirmative evidence showed
that the retained representative rollback would be unsafe.

## Outcome

TailTag has one fail-closed maintainer contract for deciding whether an older
application image may run against the schema and persisted state left by a newer
deployment. Normal recovery preserves the database and fixes forward.
Application-image rollback is exceptional and is permitted only after positive
compatibility proof. Database rollback and routine reverse migration are not
part of the V0 incident path.

## Expand, compatible, contract policy

Schema evolution should separate the lifetime of application dependencies from
the lifetime of database objects:

1. **Expand:** add backward-compatible objects or capabilities while retaining
   the schema required by the currently deployed and immediately previous
   application revisions.
2. **Compatible transition:** deploy and validate application revisions that
   can operate safely while both old and new schema shapes or persisted states
   coexist. Migrate or backfill data through separately reviewed, resumable
   operations when necessary.
3. **Contract:** remove or tighten the obsolete shape only after no supported
   application rollback depends on it and a separately reviewed rollout proves
   the destructive step safe.

Prefer additive, backward-compatible changes. An extra table, index, nullable
column, or other object is only a *candidate* for compatibility; its constraints,
foreign keys, defaults, data, and effects on old reads and writes still require
review.

Destructive or contract migrations cross the application-rollback boundary by
default. This includes removing or renaming tables or columns, incompatible type
changes, tightened nullability or constraints, destructive data transformations,
and any change that makes the retained schema or data unsafe for an older
application. A separately reviewed compatibility plan may prove a specific
exception; absence of proof means rollback is prohibited.

Application rollback restores application code, not PostgreSQL. It is allowed
only when the exact old application has been positively shown compatible with
the actual schema and persisted state that will remain. A forward fix is the
default whenever compatibility is uncertain, broken, or cannot be reconciled.
Reverse migration, database restore, and manual schema reversal are separate,
migration-specific recovery decisions. OR-8 owns restore behavior.

## Fail-closed application rollback compatibility procedure

Before authorizing rollback from current/new application **N** to old
application **O** while retaining schema and data **S**, a maintainer must
complete every step below. A missing, ambiguous, or contradictory result is a
NO-GO and requires a forward fix.

### 1. Bind exact application and deployment identities

Record the immutable full O and N source SHAs and their exact Railway deployment
IDs. Confirm the canonical project, Staging environment, API service, image
identity, deployment status, and current active deployment set. The selected O
deployment must report `canRollback=true`; availability in a dashboard or source
history alone is insufficient.

### 2. Review the complete migration delta

Enumerate every migration between O and S, including dependency ordering and
operations supplied by framework or application hooks. For every affected
existing table, inspect how O reads, inserts, updates, and deletes rows.

Explicitly review:

- added, removed, or renamed tables and columns;
- nullability, Python defaults, database defaults, generated values, and whether
  O can omit new fields on inserts and updates;
- `NOT NULL`, `UNIQUE`, `CHECK`, foreign-key, exclusion, and other constraints;
- type, collation, index, trigger, sequence, and database-expression changes;
- every `RunPython`, `RunSQL`, state/database split, manual SQL operation,
  non-atomic migration, and operation with uncertain transactional behavior;
- destructive or lossy reverse behavior, even though reversal is not planned;
  and
- new tables or relationships whose foreign keys can reject O-era deletion or
  lifecycle behavior.

### 3. Reconcile migration history and actual schema

Compare the reviewed graph with the actual applied `django_migrations` history
and the relevant PostgreSQL tables, columns, defaults, indexes, and constraints.
Reject rollback if the graph and live state do not reconcile, migration state
may be partial, a non-transactional operation failed or has uncertain
completion, or manual database changes are suspected.

### 4. Review persisted application state

Schema shape alone is insufficient. Identify values, rows, permissions,
relationships, state-machine transitions, and invariants introduced or made
valid by N. Prove that O will neither misinterpret them nor mutate them into an
unsafe state. Manually review every data migration and any newer application
behavior that persists values O did not previously accept.

### 5. Prove compatibility on disposable PostgreSQL

Where practical, create a task-owned disposable PostgreSQL database, apply S
with N first, and then run immutable O against that unchanged database. Do not
run reverse migrations. Require at least:

- O's migration plan is empty;
- Django system checks pass under O;
- focused O reads and writes cover every affected existing domain;
- newer migration records and additive objects remain present;
- relevant database constraints are exercised, including negative cases where
  they restrict O behavior; and
- O's invariants do not reinterpret or mutate newer valid persisted state.

Generic pytest execution against a fresh O-owned test schema is not sufficient.
The proof must run O against the same disposable database already migrated to S.
This is a pair-specific review and test, not a general migration analyzer.

### 6. Decide and record

Authorize the exact O/S pair only when every preceding result is affirmative.
Record sanitized commands/actions, fixed outcomes, limitations, and the planned
runtime evidence. Do not retain credentials, variable values, private URLs,
database contents, password material, or personal identifiers.

Use forward-fix when any identity, history, schema, data, or behavior conclusion
is uncertain. Never weaken the gate to obtain a rehearsal PASS.

## #206 Staging investigation and final NO-GO

The sanitized investigation record is
[`../development/staging-recovery/2026-09-22-issue-206-no-go.json`](../development/staging-recovery/2026-09-22-issue-206-no-go.json).

### Preferred representative boundary

The preferred boundary was:

- O: `04f8383fe750bec712ced27a1932b82b1eabb292`, retained as Railway
  deployment `57f17ef7-7b34-4c2f-9272-b8091b1eafad`; and
- N: `77b6c55130f1b69304a8fd748590b4bbad3bf721`.

O to N contains exactly `rehearsal.0001_initial`. It creates the additive
`rehearsal_stagingresetidentity` table without modifying an existing table and
contains no `RunPython`, `RunSQL`, state/database split, or non-atomic operation.
Its foreign keys can nevertheless reject deletion of referenced users,
Conventions, or fursuits, so even this additive migration is not universally
ignorable.

N was never deployed to Staging. There is no exact N deployment or retained N
image to select, so the preferred pair cannot be rehearsed.

### Retained O to current boundary

At investigation time the exact active deployment was
`cbe83780-0256-49c2-b026-34709ddb69b0`, source
`856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`. The retained O deployment reported
`canRollback=true`, and the O and current historical variable maps matched
without retaining their values.

The actual O-to-current migration delta additionally crosses
`accounts.0002_staff_local_password`, the operator-permission migrations, and
`operator_audit.0001_initial`. Live read-only inspection found those migrations
applied and the relevant schema consistent with the reviewed graph.

Disposable PostgreSQL proof showed that O had an empty migration plan, passed
Django checks, and could perform focused user, profile, Convention-enrollment,
and fursuit-activation reads and writes while preserving the newer rehearsal
table and migration record. It also showed the new rehearsal foreign key
correctly rejected an O-unaware deletion.

The same proof found affirmative incompatibility in persisted application
state. The [#239](https://github.com/TailTag-Game/tailtag/issues/239) change
permits a limited staff/non-superuser to hold a usable local password and
authentication state, and sanitized Staging inspection confirmed that this
state is valid and current.
O requires usable local passwords to belong to a user who is both staff and
superuser. When the disposable current-valid user was loaded and saved by O,
its usable password became unusable. O would also remove
the newer operation-level authorization and audit behavior. Therefore the
retained O image is technically rollback-capable in Railway but is not
application-safe against current Staging state.

### Non-representative retained boundary

Deployment `3acf7fee-260b-472d-9b20-d1dd76efcb25`, source
`756f48e2d90bbb803060cd015e8bcf2d47ad4fbc`, precedes current source
`856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` but has no migration delta.
Rolling between those revisions would exercise Railway mechanics only; it would
not validate the representative schema/application recovery contract.

### Decision

The final #206 decision is **NO-GO** for live Staging application rollback. No
live mutation was performed. No artificial migration pair will be manufactured,
and no mechanics-only rollback is authorized. The safe recovery path is a
reviewed forward fix.

## Verified Railway rollback interface and boundary

Live read-only GraphQL introspection established these current fields:

```graphql
type Deployment {
  canRollback: Boolean!
}

type Mutation {
  deploymentRollback(id: String!): Boolean!
}
```

The mutation selects an exact historical deployment ID and returns only a
Boolean; it does not return the resulting deployment ID. Railway documents that
rollback restores the selected deployment's retained image and historical
custom-variable snapshot without rebuilding it. `canRollback=false` or an image
outside retention is a NO-GO.

Whether a rollback emits or runs `PRE_DEPLOY_COMMAND` remains **unverified**.
Neither the live schema nor the #206 read-only inspection proves that behavior.
Do not state that it runs or that it is skipped; observe the exact resulting
deployment's lifecycle if a future qualified rehearsal is approved.

## Future exact evidence procedure

For a future pair that passes the compatibility procedure:

1. Establish an exclusive Staging operation window with no concurrent promotion
   or configuration change.
2. Verify approved GitHub and Railway identities and the canonical
   project/environment/service target.
3. Capture rollback target **R**, current active deployment **A**, their full
   source SHAs, image digests, snapshot IDs, `canRollback`, approved migration
   and readiness configuration, and the complete scoped pre-operation deployment
   set. Retain no variable values.
4. Invoke `deploymentRollback(id: R)` exactly once through the verified API.
5. Derive exactly one new deployment **D** from the scoped pre/post deployment
   sets. Require its creation after the invocation and its source/image identity
   to match R. Zero or multiple candidates, concurrency, or a lost/ambiguous
   mutation response is INDETERMINATE; stop and do not retry blindly.
6. Query lifecycle events only for D. Missing, duplicate, conflicting, or
   error-bearing lifecycle evidence fails closed. Separately record whether
   `PRE_DEPLOY_COMMAND` occurred or was skipped, and assess that observation
   together with D's exact startup and readiness evidence; neither observed
   execution outcome is inherently passing or failing.
7. Compare D's variable snapshot with R without retaining values.
8. Select D's exact RUNNING instance and use the #201 image-local identity plus
   exact-deployment join. Require the expected old source SHA and canonical
   Staging environment.
9. Require D to be in the final active deployment set.
10. Run the canonical Staging HTTP smoke plus the smallest authenticated
    affected-domain read/write proof. Shared-endpoint smoke is never image
    attribution.
11. Return to A's source SHA through the normal #202 exact-SHA promotion path,
    never a second rollback. Verify that restoration as its own exact deployment.

The mutation's Boolean response is not deployment completion evidence. Every
observation after mutation binds to exact D, never `latest`.

## Automation boundary

Do not add a generic migration-compatibility analyzer, syntax-based safety
classifier, speculative rule engine, or automatic rollback to `make api-check`.
Application-state compatibility cannot be inferred reliably from Django
migration syntax.

Existing migration-drift, Django, PostgreSQL test, Semgrep, build, and smoke
checks remain useful deterministic controls. Repository tests may enforce this
documented policy, evidence schema, links, and fail-closed wording. Focused
pair-specific fixtures may be added when they protect an approved compatibility
claim. Human maintainer review remains the authorization gate.

## Acceptance Contract

1. The expand/compatible/contract policy and forward-fix default are explicit.
2. The compatibility procedure binds exact identities; reviews migrations,
   actual schema, persisted state, and O reads/writes; and fails closed.
3. Disposable current-schema/old-code PostgreSQL proof is required where
   practical without reverse migration or a generic analyzer.
4. The #239 staff/non-superuser password incompatibility is retained as the
   concrete proof that schema compatibility alone is insufficient.
5. The preferred, actual, and non-representative boundaries and the final
   NO-GO decision are recorded with sanitized identifiers.
6. The exact Railway API shape is recorded; rollback `PRE_DEPLOY_COMMAND`
   behavior remains explicitly unverified.
7. The future exact-D evidence and normal #202 restoration procedure is
   actionable and rejects ambiguous mutation outcomes without retry.
8. No live Staging mutation, artificial migration, database reversal, restore,
   mechanics-only rehearsal, or generalized analyzer is introduced.
9. Durable evidence records commands/actions, outcomes, limitations, cleanup,
   and the forward-fix fallback without secrets or database contents.

## Test Surface Contract

Tests may read the specification, Staging runbook, Development delivery runbook,
spec index, and the sanitized JSON evidence artifact. They may assert objective
headings, exact API signatures, exact source/deployment identifiers, required
NO-GO and forward-fix language, the explicitly unverified
`PRE_DEPLOY_COMMAND` boundary, and the absence of secret-bearing evidence keys.

Tests must not contact Railway or GitHub, inspect environment credentials,
create production APIs for test convenience, encode migration syntax as a
general safety oracle, or require a live rollback. Existing
`services/api/tests/test_runtime_commands.py` is the approved documentation
contract surface; extend it rather than creating new test infrastructure.

## Scope Guard

**Outcome:** Freeze the V0 application/schema rollback policy, current Staging
NO-GO evidence, fail-closed compatibility procedure, and future exact evidence
sequence in maintained documentation.

**Non-goals:** Live rollback, mechanics-only rehearsal, reverse migration,
restore, artificial schema change, generic compatibility analyzer, automatic
rollback, Production, observability, or unrelated product behavior.

**Expected files:** this specification and plan,
`docs/specs/README.md`, `docs/development/backend-delivery-operations.md`,
`docs/development/staging.md`, one sanitized JSON evidence record under
`docs/development/staging-recovery/`, and focused assertions in
`services/api/tests/test_runtime_commands.py`.

**Proof:** focused documentation/evidence tests, `git diff --check`,
`./scripts/doctor.sh`, `make api-check`, independent specification and code
review, and final diff/scope inspection. No live Staging mutation is proof.

## References

- [Railway deployment actions](https://docs.railway.com/deployments/deployment-actions)
- [Railway Public API deployment operations](https://docs.railway.com/integrations/api/manage-deployments)
- [Railway pre-deploy command](https://docs.railway.com/deployments/pre-deploy-command)
- [Controlled Staging promotion contract](2026-09-16-controlled-staging-promotion.md)
- [Staging synthetic reset/reseed contract](2026-09-17-staging-synthetic-reset-reseed.md)
- [Field-beta operator authorization and auditability](2026-09-21-field-beta-operator-authorization-audit.md)
