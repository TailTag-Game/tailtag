# Staging backend first response

This is the first-response guide for the Render Staging backend at
`https://staging.tailtag.app`. The backend is the web service `tailtag-api-stg`
and the database `tailtag-postgres-stg`. This guide covers the nine V0
operational scenarios in [#208](https://github.com/TailTag-Game/tailtag/issues/208).
Use it with the [Staging runbook](../development/staging.md), the
[operator authorization runbook](operator-authorization-audit.md), and the
[readiness evidence matrix](../development/v0-backend-operational-readiness-matrix.md).
It does not authorize a new deployment, reset, rollback, restore, credential
change, database repair, or provider configuration change. Those actions retain
their own target checks, operator authority, and approval boundaries.

The current [readiness matrix](../development/v0-backend-operational-readiness-matrix.md)
records the #204 baseline, the #243 operator and audit results, and the #207
isolated restore. Those results come from the Railway era, before the Render
move. They are historical records and do not prove the current Render target.
Use only the current commands in the Staging runbook.

## Common first check and evidence

1. Identify the Render project `tailtag`, environment `staging`. Select the
   exact `tailtag-api-stg` deploy and, for database incidents, the
   `tailtag-postgres-stg` database. Development is a separate contributor
   environment. Stop if the target or acting account cannot be verified. Never
   infer the target from a stale CLI setting, a shared public response, or a
   `latest` label.
2. Run the [credential-free canonical preflight](../development/staging.md#health-and-public-staging-preflight-203)
   if HTTP is reachable. It performs only health/identity GETs. Record its
   fixed outcome and the safe source SHA. If it fails, inspect the exact
   Render service and deploy directly. Do not bypass the guard to send
   acceptance, reset, or simulation traffic. `/health/live` proves only a
   responding process. `/health/ready` proves local configuration and a small
   PostgreSQL query, not Clerk or R2 provider availability.
3. In the Render dashboard, open `tailtag-api-stg` and its deploy list. Bind
   diagnostics to the affected deploy ID D. Inspect its status, build log,
   pre-deploy migration log, and runtime logs as appropriate. Use `render logs`
   with the service ID and a time window for bounded reads. For database
   symptoms, open `tailtag-postgres-stg` and read its status and metrics. To
   follow one request, use [backend logging](backend-logging.md#following-one-request).
   Sanitize before sharing, because logs can contain sensitive details. Render
   keeps logs for 14 days on Pro, so keep the sanitized evidence you need before
   then. Do not treat a live status or a shared URL alone as exact-deploy proof.
4. Record the observation time, exact environment/service, safe SHA and
   deployment ID when known, health results, first failing stage, affected
   operation, action owner, and fixed outcome. Preserve the selected
   deployment's evidence before any separately approved recovery changes it.
   Do not record credentials, tokens, user identities, private URLs, bucket
   names, raw requests/responses, database contents, or broad log exports.
5. If the first safe action below does not resolve the symptom, stop new
   rehearsal activity and escalate to the backend maintainer and the owner of
   the affected Render, Clerk, or R2 resource. Keep Staging's existing state
   intact until the recovery decision is explicit. Follow the relevant linked
   procedure; do not improvise a database mutation or use #204 reset as a
   recovery shortcut.

The [Render Staging promotion](../development/staging.md#render-staging-promotion-409),
the #206 [migration/application recovery contract](https://github.com/TailTag-Game/tailtag/issues/206),
the #204 [synthetic reset](../development/staging.md#synthetic-baseline-reset-and-reseed-204),
and the [PITR restore](../development/staging.md#restore-the-database-with-pitr)
are separate opt-in operations. A failed pre-deploy migration does not prove
that the database is unchanged. An application rollback does not reverse schema
or restore R2 objects. If compatibility is uncertain, preserve the database
and fix forward. The #410 drill proved the Render rollback mechanics only,
because no migration changed between its two deploys. See
[Application rollback on Render](../development/staging.md#application-rollback-on-render).

## Bad deployment

**Recognize and diagnose.** A candidate fails build, pre-deploy, startup,
readiness, exact-image identity, smoke, or active-deployment checks; or a newly
active revision correlates with a new symptom. Use the promotion receipt's
source SHA and its `dep-...` deploy ID D. Inspect only that D's Render deploy
status and its build, pre-deploy, and runtime logs. Confirm whether the old
serving deploy remains live. Distinguish a failed attempt from a bad active
revision; do not diagnose by public HTTP alone.

**First safe mitigation and recovery.** Stop further promotion attempts and
pause Staging rehearsal traffic. If the candidate never became active, preserve
the existing serving deployment and correct the cause through the reviewed
code/configuration process. If it became active, use the #206 compatibility
decision before considering any application rollback. When rollback proof is
missing or the database state is ambiguous, use a reviewed forward fix through
a new Render promotion. A lost submission response or interrupted `PENDING`
record is indeterminate: inspect the exact attempt before any new submission.

**Preserve / avoid.** Retain S, D, validation run/attempt, sanitized failed
gate, live-deploy observation and relevant migration output. Do not rerun a
promotion blindly, start a deploy outside the promotion command (a Blueprint
sync or a variable change), reverse a migration, assume pre-deploy failure had
no database effect, or call rollback without the exact compatibility decision.

## Database unavailable or degraded

**Recognize and diagnose.** Compare `/health/live` with `/health/ready` and
the API deployment's errors. A live process with readiness 503 suggests the
database or required local configuration, not an automatic diagnosis of
PostgreSQL failure. Inspect the status and metrics of `tailtag-postgres-stg` in
Render and bounded database-related API and pre-deploy logs. Check whether a
reset connection gate or migration/recovery operation is in progress before
interpreting denied connections.

**First safe mitigation and recovery.** Pause writes, reset, promotion and
rehearsal activity; preserve the current database and exact deployment state.
If an approved reset left its maintenance gate closed, use only the
[Reset recovery on Render](../development/staging.md#reset-recovery-on-render) procedure after its
own target checks. The Railway-era #204 sentinel and baseline passed the
[guarded live reset and matrix readback](../development/v0-backend-operational-readiness-matrix.md#replacement-or-5--204-reset-evidence-2026-09-29)
in their observation window. That result is historical. If the current
operation's own target guard fails, stop and hand off to the backend and Render
resource owners. For partial
migration state use #206's reviewed
forward-fix decision. For suspected data loss use the
[PITR restore](../development/staging.md#restore-the-database-with-pitr) to plan separately approved
recovery. A PITR restore makes a new database and does not replace Staging's
active database.

**Preserve / avoid.** Retain readiness/live results, D, Postgres status,
operation window and sanitized error class. Do not terminate PostgreSQL to
test this guide, repeatedly rerun migrations, clear the database, invoke #204
reset as incident repair, or point the API at a restore clone.

## Clerk or authentication failure

**Recognize and diagnose.** A normal authenticated request fails while basic
API health may remain ready. Confirm the canonical Staging
origin and dedicated `TailTag Staging Replacement` Clerk application/Production instance.
Compare affected API responses and bounded exact-D logs with Clerk's own
read-only authorized status/diagnostic surface. Distinguish token/session problems,
local verification configuration, and provider availability without exposing
the token or changing an ordinary account.

**First safe mitigation and recovery.** Pause authenticated rehearsal and
preserve the current identity/configuration. Escalate configuration or provider
faults to the backend/Clerk owner. Run a bounded synthetic authenticated check
only with the [Render Staging authenticated smoke](../development/staging.md#render-staging-smoke-checks).
It needs an owner-controlled synthetic Clerk user and session cleanup. Resume
only after the owning fix and a safe canonical authenticated check. Readiness
alone does not validate live Clerk service.

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
operation. Use read-only R2 ownership and provider status/diagnostics first. Run the media
check with the Render Staging media smoke in
[Render Staging smoke checks](../development/staging.md#render-staging-smoke-checks).

**First safe mitigation and recovery.** Pause new media operations and retain
existing object references. Escalate R2 access or availability to its owner;
use a reviewed configuration/code fix and then the owner-controlled Render
media smoke, which cleans up. For a partial
replace/remove, follow the [media lifecycle boundary](../development/backend-delivery-operations.md#media-lifecycle-and-recovery-boundary):
a failed best-effort deletion can leave an orphan, while a committed absent
reference must not be recreated from a stale object. Investigate object and
database state independently.

**Preserve / avoid.** Retain sanitized operation stage, D, fixed smoke and
cleanup outcomes. Do not disclose object keys, bucket names, presigned URLs
or credentials; do not make the bucket public, restore a stale DB reference,
or assume application rollback restores R2 state.

## Abnormal API load

**Recognize and diagnose.** In Render, open `tailtag-api-stg` and its deploy
list. Select the exact affected D. Review its status and bounded logs alongside
canonical liveness and readiness. Read the CPU, memory, and bandwidth graphs
for the same time window. Correlate the window with known controlled
promotions, resets, synthetic rehearsal or smoke activity and its task owner.
Request rate and latency are on the
[field-beta dashboard](field-beta-operations.md#dashboard), and M3 alerts on
severe sustained latency. Do not assume that a Render resource alert or a
quantitative capacity threshold exists. Record that gap for #198.

**First safe mitigation and recovery.** Stop only known task-owned synthetic
traffic under the maintainer's control and pause new rehearsal/acceptance
jobs. Keep the serving deployment and database stable while the backend and
Render owners classify the load. A scale/configuration change or traffic
control requires its own reviewed operation. Verify return to ordinary
health and observed resource behavior before resuming rehearsal.

**Preserve / avoid.** Retain time window, D, Render resource and status summary,
health outcome and known synthetic-job identifiers without personal data.
Do not induce load or terminate services to test response. Severe sustained
latency is alerted by M3 in the
[field-beta operations guide](field-beta-operations.md#monitors); hand other
detection and alerting gaps to [#198](https://github.com/TailTag-Game/tailtag/issues/198)
and simulation gaps to [#199](https://github.com/TailTag-Game/tailtag/issues/199).

## Elevated catch-confirmation failures

**Recognize and diagnose.** Correlate sanitized failed confirmation outcomes
and exact-D API diagnostics with the current Convention, enrollment,
activation, fursuit, credential and catch-session state. Use approved
[Catch administration](catch-administration.md) and the explicit
[operator inspection permissions](operator-authorization-audit.md#authority-and-inspection-matrix).
Server errors on catch confirmation are alerted by M5 in the
[field-beta operations guide](field-beta-operations.md#monitors). An elevated
rate of player rejections has no alert; the dashboard, a report, or available
logs initiate this procedure.

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
`OperatorAuditEvent` has no viewer. If an approved bounded audit read is
unavailable, preserve the action time and sanitized target class, stop further
correction or resumption, and escalate to the backend/database owner.
Application and Render logs are not audit proof.
Detection and alerting are described in the
[field-beta operations guide](field-beta-operations.md).

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
operation when its destructive scope is actually appropriate and the reviewed
replacement-target command is available; it preserves users and audit evidence
but replaces disposable domain state. For uncertain
configuration or schema state, stop and escalate to the owning maintainer.

**Preserve / avoid.** Retain sanitized before/after state class, D, action
type, audit outcome and reset receipt if used. Do not bypass permissions with
a superuser as the routine path, alter the database directly, reset merely to
hide an unexplained defect, or manufacture data corruption for rehearsal.
`OperatorAuditEvent` has no viewer. If an approved bounded audit read is
unavailable, preserve the action time and sanitized target class, stop further
correction or resumption, and escalate to the backend/database owner.
Application and Render logs are not audit proof.

## Application rollback

**Recognize and diagnose.** First establish that the problem is in
application code/runtime and that the exact previous image is available.
Use #206's O/N/D identity, complete migration delta, actual PostgreSQL schema
and persisted-state review, old-code read/write compatibility proof where
practical, and an exact previous deploy R in the Render deploy list before
considering the action. Dashboard presence or schema shape alone is
insufficient. A failed or ambiguous check is a NO-GO.

**First safe mitigation and recovery.** Preserve the current database and
choose a reviewed forward fix by default. Only an explicitly approved,
positively compatible rollback follows
[Application rollback on Render](../development/staging.md#application-rollback-on-render). Run it
once, and do not retry a failed rollback. Restore the intended source through a
new exact-SHA Render promotion after separate review. The Railway-era #206
candidate was NO-GO because older code could invalidate a limited operator's
local authentication. That finding does not cover a Render rollback. Do not
create a migration merely to make a rollback candidate.

**Preserve / avoid.** Retain O/N/D, R, reviewed schema/data and old-code proof
outcomes, approval decision, the new deploy D and the final live deploy. Do not
reverse schema, treat rollback as database restore, use `latest`, assume
pre-deploy is a no-op, or retry a failed rollback. The #410 drill proved the
Render rollback mechanics only.

## Restore from backup

**Recognize and diagnose.** Establish whether this is data loss/corruption,
database unavailability, or a reversible code/configuration failure. Record
the source identity and intended recovery point. Review the maintained
[PITR restore procedure](../development/staging.md#restore-the-database-with-pitr). The PITR history
of `tailtag-postgres-stg` starts at its creation on 2026-11-04 at 06:28:38Z.
A recovery point must fall inside that history, and the dashboard does not
accept a time within 10 minutes of now. A practice drill on 2026-11-01 passed on
an earlier Render database, and all 25 tables matched. Treat that result as a
point-in-time observation. It proves a PITR restore into a new database for
that source. It does not prove restoration of active Staging, and it does not
prove Production recovery. The Railway-era logical dump and isolated restore receipts are
historical. See [the Railway drill record](../development/staging.md#railway-postgresql-backup-restoration-drill-207).

**First safe mitigation and recovery.** Stop writes and preserve the source
database, current deployment, and relevant logs while the backend/database
owners decide the recovery target and data-loss boundary. A PITR restore makes
a new database and leaves the source unchanged. It is not active Staging
restoration. Moving Staging to a restored database changes the pinned database
identity of the guards, so it needs a reviewed plan, authorization, target
isolation, and validation first. Never use #204 reset as a substitute for
backup recovery.

**Preserve / avoid.** Retain sanitized source/target class, recovery-point
time, outcome, backend/integrity checks, nonimpact and cleanup result. Do not
publish a dump or row contents, point the API at the practice copy, or rerun a
restore solely to duplicate #208 evidence. After owner approval, delete the
practice database, because it is a paid resource.
