# V0 backend operational readiness evidence matrix (#208)

Status: evidence inventory and draft-runbook reconciliation; **no final GO/NO-GO decision**.
Parent: [#197](https://github.com/TailTag-Game/tailtag/issues/197). Scope and verification classes: [#208](https://github.com/TailTag-Game/tailtag/issues/208).

This matrix distinguishes a completed historical exercise from proof that its
procedure still applies to canonical `TailTag/staging`. A historical `PASS` is
not a claim that the same deployment is serving now. Before final reconciliation,
compare the current canonical target, active source/deployment identity,
configuration ownership, migration leaves, and maintained parity record with
the inherited evidence. Record only sanitized identifiers and fixed outcomes.
On 2026-09-23 the repository's credential-free preflight against the exact
canonical origin passed and returned `environment=staging`,
`source_sha=856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, and
`deployment_id=cbe83780-0256-49c2-b026-34709ddb69b0`. This confirms the
public health/identity boundary at that instant. The matching sanitized #202
promotion receipt exists in the separate issue-206 checkout but has not yet
been integrated into this worktree's baseline; the public response alone does
not replace Railway exact-instance attribution or a fresh resource-drift review.

**Verification classes.** *Inherited exercise* checks durable completed live
evidence, present applicability, and material drift without repeating an
expensive or destructive operation. *Live exercise* is reserved for a safe,
bounded gap in empirical proof. *Operational review* traces exact target and
preflight, diagnostics, first safe mitigation, recovery/escalation, retained
evidence, and unsafe actions through current surfaces without creating an
incident. Rows can require an inherited exercise **and** an operational review.

**Readiness rule.** A missing OR-1–OR-8 proof, material Staging contradiction,
nonexistent or inaccessible first diagnostic/safe mitigation, failed required
exercise, unsafe mutating target guard, or recovery step requiring a dangerous
undocumented guess blocks #208. Deliberate outage testing, #198 alerting, #199
simulation, Production behavior, and the naturally compatible-migration
Railway rollback rehearsal in [#241](https://github.com/TailTag-Game/tailtag/issues/241)
do not block by themselves. `Pending` means the row is not yet reconciled; it is
not a final readiness verdict.

## Parent and OR evidence

| Parent/OR | Source evidence | Current mode | Actual surface reviewed or exercised | Result | Limitation / unverified boundary | Blocks #208 readiness? | Focused follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OR-1 / #200: isolated Staging and parity | [Staging target and sanitized parity record](staging.md#supported-target-and-boundary), [live isolation checks](staging.md#2026-09-16-sanitized-parity-record) | Inherited exercise + current operational review | Railway `TailTag/staging` `api`/`Postgres`, dedicated Clerk instance and R2 ownership, Development/Staging difference table | Historical isolation, credential-free API, synthetic media, and Clerk checks recorded PASS; current drift comparison pending | Initial copied configuration interval was explicitly not accepted as isolation proof; September 16 fingerprints are point-in-time | **Pending**; yes if resource ownership or target isolation has materially drifted | None identified |
| OR-2 / #201: immutable identity | [Final Staging identity evidence](../specs/2026-09-16-backend-build-deployment-identity.md#final-staging-acceptance-evidence), [exact deployment join](staging.md#immutable-build-and-deployment-identity-201) | Inherited exercise + current read-only identity check | Exact Railway deployment/instance and baked image source, safe `/health/identity` | Live exact-SHA join proven; current public tuple passes and matches the separate checkout's promotion receipt; fresh Railway exact-instance attribution pending | Public response alone does not attest the serving image or deployment timestamp | **Pending**; yes if current build identity cannot be established | None identified |
| OR-3 / #202: controlled deployment | [Successful exact-SHA deployment receipt](staging-deployments/d7e69108-a6d8-4355-b1ec-8b83057ca11b.json), [operator path](staging.md#controlled-staging-promotion-202) | Inherited exercise + operational review | Railway exact-D lifecycle, pre-deploy, readiness, image join, active set, canonical HTTP smoke | Historical gates `SUCCEEDED` and exact D `ACTIVE`; current command/target review pending | Receipt is a point-in-time success, not proof of today's active deployment | **Pending**; yes if supported promotion or first diagnostics no longer work | None identified |
| OR-4 / #203: health and target safety | [Live #203 evidence](staging.md#health-and-public-staging-preflight-203), [contract](../specs/2026-09-16-backend-health-environment-safety.md) | Inherited exercise + safe read-only preflight | Canonical HTTPS `/health/live`, `/health/ready`, `/health/identity`; repository Staging preflight and its negative-target tests | Historical distinct health and fail-closed target checks PASS; fresh September 23 canonical preflight PASS | No live PostgreSQL outage induced; database/config failure behavior has deterministic test proof | **Pending** only for later material drift or invalidated guard | None identified |
| OR-5 / #204: synthetic reset and reseed | [Two live resets and preservation checks](../specs/2026-09-17-staging-synthetic-reset-reseed.md#authorized-fixture-preparation-and-live-acceptance-pass), [maintained SSH procedure](staging.md#synthetic-baseline-reset-and-reseed-204) | Inherited exercise + operational review | Guarded Staging reset/SSH, pinned instance/database, connection gate, sentinel, protected state and readiness | Two equivalent live resets, safe resumption, and later maintained-command proof recorded PASS; do not repeat for #208 | Failure and negative-target paths are local deterministic proof, not live chaos; private operator configuration is intentionally outside Git | **Pending** only for material drift or unusable current procedure | None identified |
| OR-6 / #205: operator authorization/audit | [#205 closed acceptance](https://github.com/TailTag-Game/tailtag/issues/205), [operator procedure](../operations/operator-authorization-audit.md), [merged implementation PR #239](https://github.com/TailTag-Game/tailtag/pull/239); **2026-09-23 task handoff asserts bounded live validation complete** | Inherited exercise + operational review | Staging Django admin, exact permission matrix, guarded operator bootstrap, `OperatorAuditEvent`, reset preservation | Deterministic authorization/audit evidence exists. The handoff asserts the later bounded Staging proof passed, but its sanitized receipt is not linked in the repository; PR #239 expressly predates that live proof | Preserve the handoff assertion without treating a closed checkbox or implementation PR as the exercise record; locate/record the bounded result before final reconciliation | **Pending**; yes if live bounded proof cannot be substantiated or current operator path is unusable | None yet; evidence-location handoff belongs in #208 |
| OR-7 / #206: migration and application recovery | [#206](https://github.com/TailTag-Game/tailtag/issues/206); `docs/specs/2026-09-22-v0-migration-application-rollback.md` and `docs/development/staging-recovery/2026-09-22-issue-206-no-go.json` in the separate issue-206 checkout | Inherited disposable compatibility exercise + operational review | Migration graph, actual schema/persisted-state comparison, old-code/new-schema PostgreSQL proof, exact Railway rollback preflight | Approved fail-closed policy and concrete NO-GO evidence completed; named source files remain outside this worktree's `main` baseline | Railway rollback `PRE_DEPLOY_COMMAND` behavior and exact live compatible rollback remain unverified; do not invent a migration | **Pending** until durable #206 handoff is integrated; live rollback gap alone does **not** block | [#241](https://github.com/TailTag-Game/tailtag/issues/241) |
| OR-8 / #207: backup restore and integrity | [Final September 23 GO record](staging-recovery/20260923T165714Z-issue-207-restore-d6def5ea5b9442c7992d301a575c6f8b.json), [procedure](staging.md#postgresql-backup-restoration-drill-207) | Inherited exercise + operational review | Real Staging `pg_dump`, isolated PostgreSQL 18 restore, matching-revision backend reads, constraints, source nonimpact, cleanup | Final record: `outcome=GO`, `backend_usability=PASS`, `staging_nonimpact=PASS`, `cleanup_verified=true`, `limitations=[]`; no rerun for #208 | Source Catch, session and credential tables were empty, so representative reads are `NOT_EXERCISED`; schema, constraints and relationship checks passed. Earlier [failed preflight](staging-recovery/2026-09-22-issue-207-preflight-diagnosis.md) is historical, not the final outcome | **Pending** only for material drift or an unusable recovery procedure | None identified |

## Minimum first-response runbooks

Each `Pending` operational review must trace the six fields named above against
current surfaces. The [Staging first-response draft](../operations/staging-first-response.md)
now has all nine paths, using the [Staging runbook](staging.md) for promotion,
reset, identity, health, operator validation and restore. The [Development
delivery guide](backend-delivery-operations.md) is useful background but cannot
be used as an unqualified Staging incident procedure. Drafting the paths does
not itself complete their operational review.

| Runbook | Source evidence | Current mode | Actual surface reviewed or exercised | Result / runbook work | Limitation / unverified boundary | Blocks #208 readiness? | Focused follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bad deployment | #202 exact-D [promotion record](staging-deployments/d7e69108-a6d8-4355-b1ec-8b83057ca11b.json); #206 recovery contract | Inherited exercise + operational review | Canonical target and D/S pins; Railway build, pre-deploy, deploy/runtime logs; active set and safe smoke | Promotion diagnostics exist; assemble one Staging first-response path and review it | Do not infer migration nonimpact from failed pre-deploy or use latest/automatic retry | **Pending**; yes if exact-D diagnosis or safe stop/escalation is unusable | #241 only for compatible rollback rehearsal |
| Database unavailable/degraded | [Health semantics](staging.md#health-and-public-staging-preflight-203); #206 and #207 recovery boundaries | Operational review | Live versus ready response, `Postgres` service/deployment status, exact-D API diagnostics, database recovery handoff | Staging incident runbook needed; no deliberate PostgreSQL degradation | Failure-mode evidence is deterministic, not a live outage | **Pending**; yes if first diagnosis/mitigation requires an unsafe guess | None identified |
| Clerk/authentication failure | [Staging Clerk smoke](staging.md#clerk-authenticated-smoke), [provider boundary](staging.md#supported-target-and-boundary), existing auth failure tests | Operational review + inherited deterministic failure paths | Canonical target, dedicated Clerk instance, safe auth configuration checks, bounded synthetic authenticated smoke and relevant API diagnostics | Staging incident runbook needed; do not break Clerk | Provider outage/remote failure not induced | **Pending**; yes if safe diagnosis or escalation surface is missing | #198 for alerting only if identified |
| Storage/media failure | [Staging synthetic media smoke](staging.md#http-configuration-and-media), [media lifecycle boundary](backend-delivery-operations.md#media-lifecycle-and-recovery-boundary) | Inherited exercise + operational review | Staging R2 ownership, guarded smoke, API/media diagnostics, object/reference distinction | Existing live smoke passed; Staging incident runbook needed | R2 outage not induced; rollback does not restore media objects | **Pending**; yes if safe media diagnosis/mitigation is inaccessible | None identified |
| Abnormal API load | [Railway log access pattern](backend-delivery-operations.md#find-state-and-logs), [Staging target/health](staging.md#supported-target-and-boundary) | Operational review | `TailTag/staging/api` → Deployments → exact D's runtime/deployment logs and status; canonical liveness/readiness; known synthetic client/job owner | Staging draft names bounded exact-D diagnostics and stopping task-owned synthetic traffic; live load generation is unwarranted | Staging resource metrics/dashboard availability has not been substantiated; no #198 alerting or #199 load/simulation implementation | **Pending**; yes if exact-D logs or safe synthetic-traffic stop are unavailable | [#198](https://github.com/TailTag-Game/tailtag/issues/198) for metric/alerting gaps |
| Elevated catch-confirmation failures | [Catch administration](../operations/catch-administration.md), [Wave 3 validation](wave-3-catching-validation.md), [operator audit](../operations/operator-authorization-audit.md) | Operational review | Current API/Railway diagnostics, catch/session/credential domain states, authorized operator inspection and correction | Staging incident runbook needed; trace exact inspection permissions and domain-safe first action | Detection/alerting is #198; no induced failure spike | **Pending**; yes if diagnosis or correction requires undocumented gameplay mutation | [#198](https://github.com/TailTag-Game/tailtag/issues/198) for detection gaps |
| Broken convention/configuration state | [Operator permission matrix](../operations/operator-authorization-audit.md), [reset contract](staging.md#synthetic-baseline-reset-and-reseed-204) | Operational review; safe synthetic action only if evidence gap warrants | Canonical Staging admin inspection, exact convention/playability permission, operator audit, #204 reset boundary | Staging incident runbook needed; decide whether any supported synthetic correction merits bounded exercise after review | No database corruption or arbitrary admin write | **Pending**; yes if authorized correction cannot be located or safely bounded | None identified |
| Application rollback | #206 contract and NO-GO evidence in issue-206 checkout; [#241](https://github.com/TailTag-Game/tailtag/issues/241) | Operational review | Exact O/N/D identities, `canRollback`, migration/schema/data compatibility, Railway rollback action and exact-D observation | Incorporate #206's fail-closed decision and forward-fix path into Staging runbook | Exact live Railway compatible rollback/pre-deploy behavior deferred to #241 | **Pending** for procedure quality; #241 gap alone does **not** block | [#241](https://github.com/TailTag-Game/tailtag/issues/241) |
| Restore from backup | [Final #207 GO record](staging-recovery/20260923T165714Z-issue-207-restore-d6def5ea5b9442c7992d301a575c6f8b.json), [maintained drill](staging.md#postgresql-backup-restoration-drill-207) | Inherited exercise + operational review | Canonical source preflight, isolated local restore target, integrity/backend reads, nonimpact and cleanup | Live restoration proved; review first-response decision and invocation; do not rerun solely for #208 | Logical dump is a point-in-time drill, not automatic PITR or Production recovery | **Pending**; yes if current restore procedure or safe target guard is unusable | None identified |

## Reconciliation queue before a readiness decision

1. Locate or publish the sanitized bounded Staging #205 operator/audit result
   asserted in the 2026-09-23 task handoff; do not replace its missing citation
   with the merged implementation PR or a checked issue box.
2. Bring the completed #206 contract and NO-GO evidence into the same durable
   repository baseline as #208 before final review. Preserve #241 as the exact
   deferred live Railway rollback boundary.
3. Perform a fresh **read-only** canonical Staging identity/health/parity check,
   then assess any material drift against each inherited exercise. Keep remote
   identity checks and evidence sanitization in the owning commands.
4. Write/review the nine implementation-coupled Staging first-response paths.
   Operational review is required for every path. Current evidence does not
   justify a destructive or expensive #208-only live exercise; revisit only if
   review finds a safe, bounded empirical gap.
5. Reconcile each row's result and blocker column with the completed procedures
   before issuing a final #208 GO/NO-GO.
