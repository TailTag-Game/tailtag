# Staging backend first response

This is the first-response guide for the canonical Railway `TailTag` / `staging`
backend at `https://staging.tailtag.app`. It covers the nine V0 operational
scenarios in [#208](https://github.com/TailTag-Game/tailtag/issues/208).
Use it with the [Staging runbook](../development/staging.md), the
[operator authorization runbook](operator-authorization-audit.md), and the
[readiness evidence matrix](../development/v0-backend-operational-readiness-matrix.md).
It does not authorize a new deployment, reset, rollback, restore, credential
change, database repair, or provider configuration change. Those actions retain
their own target checks, operator authority, and approval boundaries.

## Common first check and evidence

1. Identify `Finn the Panther's Projects` / `TailTag` / `staging`; select the
   exact `api` deployment and, for database incidents, the environment-local
   `Postgres` service. Development is a separate contributor environment.
   Stop if the target or acting account cannot be verified. Never infer the
   target from a stale CLI link, a shared public response, or a `latest` label.
2. Run the [credential-free canonical preflight](../development/staging.md#health-and-public-staging-preflight-203)
   if HTTP is reachable. It performs only health/identity GETs. Record its
   fixed outcome and safe source SHA/deployment ID. If it fails, inspect the
   exact Railway service/deployment directly; do not bypass the guard to send
   acceptance, reset, or simulation traffic. `/health/live` proves only a
   responding process; `/health/ready` proves local configuration and a small
   PostgreSQL query, not Clerk or R2 provider availability.
3. In Railway `staging` → `api` → **Deployments**, bind diagnostics to the
   affected deployment ID. Inspect its status, build output, pre-deploy
   migration output, startup/runtime output, instances, and lifecycle events
   as appropriate. For database symptoms inspect `staging` → `Postgres`
   service/deployment status and targeted diagnostics. Use bounded reads and
   sanitize before sharing; logs may contain sensitive details. Do not treat a
   successful event or shared URL alone as exact-deployment proof.
4. Record the observation time, exact environment/service, safe SHA and
   deployment ID when known, health results, first failing stage, affected
   operation, action owner, and fixed outcome. Preserve the selected
   deployment's evidence before any separately approved recovery changes it.
   Do not record credentials, tokens, user identities, private URLs, bucket
   names, raw requests/responses, database contents, or broad log exports.
5. If the first safe action below does not resolve the symptom, stop new
   rehearsal activity and escalate to the backend maintainer and the owner of
   the affected Railway, Clerk, or R2 resource. Keep Staging's existing state
   intact until the recovery decision is explicit. Follow the relevant linked
   procedure; do not improvise a database mutation or use #204 reset as a
   recovery shortcut.

The existing #202 [controlled promotion](../development/staging.md#controlled-staging-promotion-202),
#206 [migration/application recovery contract](https://github.com/TailTag-Game/tailtag/issues/206),
#204 [synthetic reset](../development/staging.md#synthetic-baseline-reset-and-reseed-204),
and #207 [isolated restore drill](../development/staging.md#postgresql-backup-restoration-drill-207)
are separate opt-in operations. A failed pre-deploy migration does not prove
that the database is unchanged. An application rollback does not reverse schema
or restore R2 objects. If compatibility is uncertain, preserve the database
and fix forward. The exact live Railway compatible-rollback/pre-deploy rehearsal
is deferred to [#241](https://github.com/TailTag-Game/tailtag/issues/241).

## Bad deployment

**Recognize and diagnose.** A candidate fails build, pre-deploy, startup,
readiness, exact-image identity, smoke, or active-deployment checks; or a newly
active revision correlates with a new symptom. Use the #202 promotion receipt's
source SHA and returned deployment ID. Inspect only that D's Railway lifecycle
and relevant build/pre-deploy/deployment output. Confirm whether the old serving
deployment remains active. Distinguish a failed attempt from a bad active
revision; do not diagnose by public HTTP alone.

**First safe mitigation and recovery.** Stop further promotion attempts and
pause Staging rehearsal traffic. If the candidate never became active, preserve
the existing serving deployment and correct the cause through the reviewed
code/configuration process. If it became active, use the #206 compatibility
decision before considering any application rollback. When rollback proof is
missing or the database state is ambiguous, use a reviewed forward fix through
#202. A lost submission response or interrupted `PENDING` record is
indeterminate: inspect the exact attempt before any new submission.

**Preserve / avoid.** Retain S, D, validation run/attempt, sanitized failed
gate, active-set observation and relevant migration output. Do not rerun a
promotion blindly, use `railway up` or Deploy Latest Commit, reverse a
migration, assume pre-deploy failure had no database effect, or call rollback
without the exact compatibility decision.

## Database unavailable or degraded

**Recognize and diagnose.** Compare `/health/live` with `/health/ready` and
the API deployment's errors. A live process with readiness 503 suggests the
database or required local configuration, not an automatic diagnosis of
PostgreSQL failure. Inspect the selected Staging `Postgres` service/deployment
state and bounded database-related API/pre-deploy diagnostics. Check whether a
reset connection gate or migration/recovery operation is in progress before
interpreting denied connections.

**First safe mitigation and recovery.** Pause writes, reset, promotion and
rehearsal activity; preserve the current database and exact deployment state.
If an approved reset left its maintenance gate closed, use only the verified
control-database [recovery procedure](../development/staging.md#synthetic-baseline-reset-and-reseed-204)
after its own target and cluster checks. Otherwise hand off to the backend and
Railway resource owners. For partial migration state use #206's reviewed
forward-fix decision; for suspected data loss use #207's restore evidence to
plan separately approved recovery. The #207 drill restores to an isolated
target and is not an instruction to replace Staging's active database.

**Preserve / avoid.** Retain readiness/live results, D, Postgres status,
operation window and sanitized error class. Do not terminate PostgreSQL to
test this guide, repeatedly rerun migrations, clear the database, invoke #204
reset as incident repair, or point the API at a restore clone.

## Clerk or authentication failure

**Recognize and diagnose.** A normal authenticated request or approved
synthetic [Clerk smoke](../development/staging.md#clerk-authenticated-smoke)
fails while basic API health may remain ready. Confirm the canonical Staging
origin and dedicated `TailTag Staging` Clerk application/Production instance.
Compare affected API responses and bounded exact-D logs with Clerk's own
authorized status/diagnostic surface. Distinguish token/session problems,
local verification configuration, and provider availability without exposing
the token or changing an ordinary account.

**First safe mitigation and recovery.** Pause authenticated rehearsal and
preserve the current identity/configuration. If the approved synthetic smoke
was started, follow its mandatory session cleanup; a cleanup failure requires
manual owner follow-up. Escalate configuration or provider faults to the
backend/Clerk owner. Resume only after the owning fix and a safe canonical
authenticated check. Readiness alone does not validate live Clerk service.

**Preserve / avoid.** Retain only sanitized failure class, time, D, smoke
stage/cleanup outcome and provider incident reference if public. Do not put
JWTs, session IDs, passwords, Clerk identifiers or provider configuration
values in logs/evidence; do not disable verification, rotate secrets, or break
the provider merely to reproduce an outage.

## Storage or media failure

**Recognize and diagnose.** Separate an API/database reference problem from
R2 upload, HEAD/GET, presigned GET, or deletion failures. Review exact-D API
diagnostics, Staging-owned private bucket/credential configuration through
approved names/ownership (never rendered values), and the affected media
operation. The existing guarded [Staging media smoke](../development/staging.md#http-configuration-and-media)
is an optional bounded upload/read/delete/absence check only after its target,
authorization and cleanup prerequisites are satisfied.

**First safe mitigation and recovery.** Pause new media operations and retain
existing object references. Escalate R2 access or availability to its owner;
use a reviewed configuration/code fix and then a bounded check. For a partial
replace/remove, follow the [media lifecycle boundary](../development/backend-delivery-operations.md#media-lifecycle-and-recovery-boundary):
a failed best-effort deletion can leave an orphan, while a committed absent
reference must not be recreated from a stale object. Investigate object and
database state independently.

**Preserve / avoid.** Retain sanitized operation stage, D, fixed smoke and
cleanup outcomes. Do not disclose object keys, bucket names, presigned URLs
or credentials; do not make the bucket public, restore a stale DB reference,
or assume application rollback restores R2 state.

## Abnormal API load

**Recognize and diagnose.** In Railway, select `TailTag` → `staging` → `api` →
**Deployments** → the exact affected D. Review its status and bounded
deployment/runtime logs alongside canonical liveness and readiness. Correlate
the time window with known controlled promotions, resets, synthetic rehearsal
or smoke activity and its task owner. Staging resource metrics/dashboard
availability has not been substantiated for this runbook; do not assume an
alert, request-rate chart, or quantitative capacity threshold exists. Record
that gap for #198 while using the exact-D diagnostic surface that does exist.

**First safe mitigation and recovery.** Stop only known task-owned synthetic
traffic under the maintainer's control and pause new rehearsal/acceptance
jobs. Keep the serving deployment and database stable while the backend and
Railway owners classify the load. A scale/configuration change or traffic
control requires its own reviewed operation. Verify return to ordinary
health and observed resource behavior before resuming rehearsal.

**Preserve / avoid.** Retain time window, D, Railway resource/status summary,
health outcome and known synthetic-job identifiers without personal data.
Do not induce load or terminate services to test response; hand detection and
alerting gaps to [#198](https://github.com/TailTag-Game/tailtag/issues/198)
and simulation gaps to [#199](https://github.com/TailTag-Game/tailtag/issues/199).

## Elevated catch-confirmation failures

**Recognize and diagnose.** Correlate sanitized failed confirmation outcomes
and exact-D API diagnostics with the current Convention, enrollment,
activation, fursuit, credential and catch-session state. Use approved
[Catch administration](catch-administration.md) and the explicit
[operator inspection permissions](operator-authorization-audit.md#authority-and-inspection-matrix).
There is no #208 alert or threshold that independently detects an elevated
rate; a report or available logs initiate this procedure.

**First safe mitigation and recovery.** Pause the affected synthetic catch
rehearsal and preserve the original attempts. Confirm whether the failure is
expected from current eligibility/session/credential state before correcting
anything. An authorized operator may use only the documented individual
administrative action for a verified invalid state; a code or configuration
defect goes through a reviewed fix. Resume with an approved bounded ordinary
flow after the cause is corrected.

**Preserve / avoid.** Retain fixed error class, time window, D, sanitized
affected record types and authorized audit outcome. Do not log QR credentials,
tokens or raw payloads, create a Catch through admin, change catch history,
replace a credential arbitrarily, or treat a stale preview as write authority.
Detection/alerting belongs to [#198](https://github.com/TailTag-Game/tailtag/issues/198).

## Broken convention or configuration state

**Recognize and diagnose.** Verify the canonical target and current
Convention/playability, enrollment, activation and fursuit states through the
permitted Django admin inspection surfaces. Compare the claimed symptom with
current configuration, #204's known synthetic baseline, and the relevant
`OperatorAuditEvent` action/outcome. Distinguish an intentional operator
transition from a bad deploy or database problem.

**First safe mitigation and recovery.** Pause affected rehearsal. For an
identified synthetic domain-state mistake, an explicitly permitted
non-superuser operator can use the documented per-object Convention
playability or other exact action, with its audit outcome checked afterward.
Use #204 reset only as the separately authorized Staging synthetic-baseline
operation when its destructive scope is actually appropriate; it preserves
users and audit evidence but replaces disposable domain state. For uncertain
configuration or schema state, stop and escalate to the owning maintainer.

**Preserve / avoid.** Retain sanitized before/after state class, D, action
type, audit outcome and reset receipt if used. Do not bypass permissions with
a superuser as the routine path, alter the database directly, reset merely to
hide an unexplained defect, or manufacture data corruption for rehearsal.

## Application rollback

**Recognize and diagnose.** First establish that the problem is in
application code/runtime and that the exact previous image is available.
Use #206's O/N/D identity, complete migration delta, actual PostgreSQL schema
and persisted-state review, old-code read/write compatibility proof where
practical, and Railway `canRollback=true` before considering the action.
Dashboard presence or schema shape alone is insufficient. A failed or
ambiguous check is a NO-GO.

**First safe mitigation and recovery.** Preserve the current database and
choose a reviewed forward fix by default. Only an explicitly approved,
positively compatible rollback uses the exact Railway selected-deployment
action and #206's exact resulting-D observation; an ambiguous mutation
response must not be retried. Restore the intended source through a new #202
exact-SHA promotion after separate review. Current representative Staging
state had a #206 NO-GO because older code could invalidate a limited
operator's local authentication. Do not create a migration merely to make a
rollback candidate.

**Preserve / avoid.** Retain O/N/D, `canRollback`, reviewed schema/data and
old-code proof outcomes, approval decision, new exact-D lifecycle and final
active set. Do not reverse schema, treat rollback as database restore, use
`latest`, assume pre-deploy is a no-op, or retry an indeterminate mutation.
The exact live Railway compatible-rollback/pre-deploy gap remains [#241](https://github.com/TailTag-Game/tailtag/issues/241).

## Restore from backup

**Recognize and diagnose.** Establish whether this is data loss/corruption,
database unavailability, or a reversible code/configuration failure. Record
the source identity and intended recovery point. Review the maintained #207
[isolated restore procedure](../development/staging.md#postgresql-backup-restoration-drill-207)
and its [final GO evidence](../development/staging-recovery/20260923T165714Z-issue-207-restore-d6def5ea5b9442c7992d301a575c6f8b.json).
The September 23 logical dump/restore proved isolated PostgreSQL 18 restore,
integrity checks, matching-revision backend usability, Staging nonimpact and
cleanup; the earlier failed preflight is historical.

**First safe mitigation and recovery.** Stop writes and preserve the source
database, current deployment, and relevant logs while the backend/database
owners decide the recovery target and data-loss boundary. The #207 command is
a guarded **drill to a disposable isolated target**, not active Staging
restoration. A real active-environment restore requires its own reviewed plan,
authorization, target isolation, and validation. Never use #204 reset as a
substitute for backup recovery.

**Preserve / avoid.** Retain sanitized source/target class, recovery-point
time, outcome, backend/integrity checks, nonimpact and cleanup result. Do not
publish a dump or row contents, point the API at the drill clone, claim PITR
when none was available, or rerun a restore solely to duplicate #208 evidence.
