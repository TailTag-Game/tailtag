# Field-beta observability validation

Issue: [#217](https://github.com/TailTag-Game/tailtag/issues/217) (OB-9).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #210 ([backend logging](../operations/backend-logging.md)), #211 ([telemetry privacy](../architecture/backend/telemetry-privacy.md)), #212 ([backend service signals](../operations/backend-service-signals.md)), #213 ([backend domain outcomes](../operations/backend-domain-outcomes.md)), #214 ([backend dependency health](../operations/backend-dependency-health.md)), #215 ([telemetry retention and access](../architecture/backend/telemetry-retention-access.md)), #216 ([field-beta operations](../operations/field-beta-operations.md)).
Staging foundations: #200, #201, #203, and the #204 [synthetic reset](2026-09-17-staging-synthetic-reset-reseed.md).
Consumer: #199 (simulations).

## Status and phase ledger

Execution: STANDARD EXPANDED. Assurance: SECURITY (tokens, catch
credentials, and canary values handled by a temporary probe; public evidence),
DATA INTEGRITY (Staging designated media and the #204 baseline).
Completed: scope review and research; maintainer approval of decisions 1 to 8
below (2026-10-01), with decision 6 revised after research (see decision 6).
Access (2026-10-01): the maintainer, as observability owner, authorized
Claude's Sentry access for #217. Claude uses only the connector's read tools,
because the dashboard and monitors are built by hand (decision 4).
Spec approved by the maintainer (2026-10-01); run authorized the same day.
V-1 passed (2026-10-01): Staging `/health/identity` reported `environment`
`staging`, `source_sha` `b1d8a7e`, deployment `95c3ee64`; readiness 200. `main`
is at `19abf91`, but `b1d8a7e..19abf91` changes documentation only, so the
served API code matches `main` and no promotion was needed. Sentry showed
`staging` `tailtag.http.server.requests` for release `b1d8a7e`. The approved
Railway account was active with the `TailTag` project linked.
V-2 passed (2026-10-01): the guarded #204 reset ran from 21:50:34 to 21:50:55
UTC and returned baseline version 1 with profiles 2, conventions 1, fursuits 2,
enrollments 2, activations 2, and zero catches, sessions, and credentials, with
cleanup confirmed. Sentry then showed one `tailtag.media.storage.operations`
`HeadObject` / `succeeded` for `staging` at release `b1d8a7e`. No `GetObject`
was recorded.
Probe target (2026-10-01): the replacement auth smoke's pinned candidate
origin now returns 400, so the probe uses the canonical #203 preflight
(`scripts/api_staging_preflight.validate_target`) against
`https://staging.tailtag.app`.
V-3 (2026-10-01): the maintainer built D10 grouped by `rpc.method` only.
Sentry does not offer `tailtag.reason` for the storage metric because Staging
has recorded no failed storage operation, and the reason attribute is set only
on failures. The `tailtag.reason` grouping is added when Staging first records
one.
V-4 passed (2026-10-01): independent review found no BLOCKER or HIGH; SPEC,
QUALITY, SCOPE, and SECURITY passed. Fixed before the run: M-1 the probe now
requires exactly the owner's two baseline activations and that the catcher
owns none (catching a swapped account); M-2 the absence scan requires its own
walkthrough lines in both the service and HTTP log exports, requests
`--lines 5000`, and refuses empty scan inputs; L-1 a failed scan can be
retried without losing in-memory values; L-2 the credential token without its
`tailtag:catch:v1:` prefix is scanned; L-3 W-4's Railway request ID is
validated. W-7b was added so Sentry offers `payload_invalid` before M6 is
built.
V-5 attempt 1 (2026-10-01): a token from the catcher account at the first
owner prompt stopped the probe at the activation check before any write.
V-5 attempt 2 (2026-10-01, stopped at 22:17:11 UTC): W-1 to W-6 passed (W-4 `created` with
Railway request ID recorded, W-5 `already_caught`); W-7 returned 200 instead
of 404 and the probe stopped. This was a walkthrough design error, not a
defect: confirmation recovers an existing catch before checking revocation,
so the catcher who had just caught the fursuit correctly received
`already_caught` ([catch confirmation spec](2026-09-08-v0-authoritative-catch-confirmation.md)).
W-7 now uses the owner, who has not caught the fursuit, as #213 E-2 did.
The probe change moves one request to the owner step and adds no output or
data handling, so it was not re-reviewed; the maintainer accepted running it
without a second review (2026-10-01). The aborted attempt's window is
not covered by the absence scan.
Reset (2026-10-01, 22:17:57 to 22:18:09 UTC): the guarded #204 reset restored
the same baseline counts with cleanup confirmed.
V-5 passed (2026-10-01, attempt 3, 22:19:01 to 22:19:34 UTC): W-1 to W-8
returned the expected statuses and outcomes, recorded in the
[validation record](../development/field-beta-observability-validation.md#walkthrough).
W-9 (stop session) ran after W-10, at 22:29:34, rather than in phase A, so
the session stayed on through the burst; this does not affect any check.
V-6 passed (2026-10-01): the maintainer built D6, D7, and M6 and connected M6
to the shared alert from the monitor. A read-only check confirmed each against
the operations guide and that the alert is connected to exactly M1 to M7.
V-7 passed (2026-10-01): six malformed confirmations at 22:29:23 made M6
evaluate 6 above 4 at 22:35:01 and open `TAILTAG-TESTING-A`; the maintainer confirmed the alert email arrived.
The issue had resolved by 22:47.
V-8 passed (2026-10-01) with stated limits: trace, absence, dimension, and
alert checks, recorded in the validation record. The Sentry side of the
absence check and the per-attribute metric check are narrower than planned;
both are stated in the record's limitations and dimension check. `TAILTAG-TESTING-9`, a `DisallowedHost` error from
the diagnostic requests to the retired candidate origin, is recorded there and
was resolved by the maintainer.
V-9 passed (2026-10-01, 22:36:57 to 22:37:12 UTC): the closing guarded #204
reset restored the baseline counts with cleanup confirmed; readiness 200. The
probe directory was deleted and no log export remained. The maintainer
signed out of both synthetic accounts.
V-10 (2026-10-01): the validation record, operations guide, observability §7,
and the #216 spec ledger were updated.
Independent documentation review (2026-10-01): SPEC, QUALITY, SCOPE, and
SECURITY passed with no BLOCKER or HIGH. Remediated: M-1 the dimension check
cites the metric scrubber and notes the once-per-process warning; M-2 the
narrower Sentry absence check is a stated limitation; M-3 recorded above;
L-1 to L-3 and the nits corrected. `./scripts/doctor.sh` and
`git diff --check` passed.
Current: commit and pull request.

## Problem

#210 to #216 each proved part of the #198 contract, mostly in Development.
Nobody has shown the whole contract working in Staging, and #216 left M6, D6,
D7, D10, and rehearsal R-6 unbuilt because Staging had never emitted a catch
outcome or a storage operation and had no approved way to send authenticated
catch traffic. #199 needs to know which signals it can trust before its
simulation runs count as readiness evidence.

## Evidence

- No API code path can be made to fail on demand, and the architecture forbids
  observability-only routes ([observability §3](../architecture/backend/observability.md#3-data-paths)).
- A request-path 500 creating a Sentry error has not been observed in a
  deployed environment. #210 D-3 proved error delivery from a Development
  shell; request-bound hygiene was verified locally.
- #213 sent authenticated catch traffic with a temporary, reviewed probe under
  the [Wave 3 probe security contract](../development/wave-3-catching-validation.md#one-off-probe-security-contract).
  #243 sent one authenticated request to replacement Staging with a one-use,
  reviewed client and hidden token prompts.
  `scripts/api_replacement_auth_smoke.py` prompts for tokens without echoing
  them, and `scripts/api_staging_preflight.py` pins the canonical Staging
  origin and runs the #203 identity and readiness preflight.
- Staging uses its own Clerk application. Session tokens expire after about
  60 seconds, so each group of authenticated steps needs a fresh token.
- The #204 baseline sets both synthetic profiles' avatars and both fursuit
  photos to the one designated image (`services/api/rehearsal/reset.py`).
  Replacing or clearing an image deletes the old object
  (`media/service.py`), so any avatar or photo change on a baseline record
  would delete the designated image and break future resets.
- The #204 reset's safety check reads the designated image through the
  configured storage (`exists`, then `open`), and the configured storage is the
  instrumented `S3MediaStorage`. #214 E-3 showed storage calls from a one-off
  shell reach Sentry.
- After a #204 reset the baseline has zero catches, sessions, and credentials.
  The last reset was 2026-09-29; #216 sent only unauthenticated traffic since.

## Decisions

Approved by the maintainer on 2026-10-01.

1. **Authenticated traffic.** A temporary probe, reviewed in full before it
   runs and deleted afterwards, sends the authenticated requests. It follows
   the Wave 3 probe security contract adapted to Staging (see
   [Probe contract](#probe-contract)). It is not committed and is not a
   reusable launcher; #199 builds its own harness.
2. **No fault triggers.** No code or configuration is added to make the API
   fail. Readiness, database, and latency degradation cite #214 Development
   evidence and the #216 swap rehearsals. A request-path server error in a
   deployed environment is recorded as a limitation.
3. **Canary-scoped absence proof.** The probe plants unique synthetic markers
   where leaks could occur. Railway logs and Sentry are searched for the
   markers and for the probe's in-memory sensitive values. The claim is
   limited to that window and those values; the general guarantee rests on the
   #211 redaction hooks and their tests.
4. **Built by hand, verified read-only.** The maintainer builds M6, D6, D7,
   and D10 in the Sentry UI from the operations guide. Claude checks the saved
   configuration through the read-only connector.
5. **Cite, then walk through once.** A coverage table links each of the 13
   areas to its earlier evidence and states what one Staging walkthrough
   showed. Earlier issues' checks are not repeated one by one.
6. **Storage signal from the reset, not an upload.** *Revised from the
   agreed avatar upload-and-clear, because the baseline avatars are the
   designated image.* The opening #204 reset reads the designated image, which
   emits `tailtag.media.storage.operations` (`HeadObject`, `GetObject`) for
   Staging and makes D10 buildable. No Staging image is uploaded, replaced, or
   cleared.
7. **Reset before and after.** A guarded #204 reset runs before the walkthrough
   (known baseline, storage signal) and after it (clean state for #199). Each
   uses the full #204 guards; the maintainer has allowed the whole day as the
   window.
8. **Evidence by hand.** Records are written on the day of the run from
   allow-listed values only, following the
   [evidence preservation runbook](../operations/telemetry-evidence-preservation.md).
   No screenshots, exports, or provider URLs are committed.

## Prerequisites

- **P-1 Staging serves the current build.** `/health/identity` reports
  `environment` `staging` and a `source_sha` whose API code matches `main`;
  readiness returns 200; Sentry shows recent `staging` telemetry for that
  release.
  If Staging serves an older build, a controlled promotion runs first.
- **P-2 Synthetic accounts.** The maintainer can sign in to the owner and
  catcher synthetic Staging accounts in a browser.
- **P-3 Railway identity.** The approved Railway account is active and the
  replacement Staging project and `api` service are selected for log reads.

## Procedure

Run in one day, in order. Times are UTC. Stop at the first unexpected result;
cleanup still runs.

| Step | Action | Expected |
| --- | --- | --- |
| V-1 | P-1 to P-3 | All pass |
| V-2 | Guarded #204 reset | Baseline counts match; Sentry shows `tailtag.media.storage.operations` `succeeded` for `staging` |
| V-3 | Maintainer builds D10; Claude checks it | D10 matches the guide |
| V-4 | Independent review of the probe source | No blocking finding |
| V-5 | Probe phase A: catch walkthrough | See [walkthrough](#walkthrough) |
| V-6 | Maintainer builds M6, D6, D7 and reconnects the shared alert; Claude checks | Alert connected to exactly M1 to M7 |
| V-7 | Probe phase B: R-6 burst | M6 opens an issue and email arrives; resolves |
| V-8 | Trace, absence, and dimension checks | See [checks](#checks) |
| V-9 | Guarded #204 reset | Baseline counts match |
| V-10 | Write evidence and documentation | Passes the must-not-contain list |

### Walkthrough

Owner steps use an owner token; catcher steps use a catcher token. The probe
pauses before each group for a fresh token.

| # | Who | Request | Expected status | Expected outcome |
| --- | --- | --- | --- | --- |
| W-1 | Owner | Start the catch session on the baseline activation | 2xx | `catch_session` `started` |
| W-2 | Owner | Fetch the current catch credential | 200 | — |
| W-3 | Catcher | Resolve the credential | 200 | `credential_resolution` `resolved` |
| W-4 | Catcher | Confirm the catch | 201 | `catches.confirmation` `created` |
| W-5 | Catcher | Send the identical confirmation again | 200 | `already_caught` |
| W-6 | Owner | Rotate the credential | 2xx | — |
| W-7 | Owner | Confirm with the old credential | 404 | `rejected` / `credential_revoked` |
| W-7b | Catcher | One malformed confirmation containing a payload marker | 400 | `rejected` / `payload_invalid` |
| W-8 | None | `GET /api/me/` with a non-token bearer marker, once | 401 | `authentication.verification` `rejected` / `token_invalid` |
| W-9 | Owner | Stop the catch session | 2xx | `catch_session` `ended` / `owner` |
| W-10 | Catcher | 5 or more malformed confirmations containing a payload marker (phase B) | 4xx | `rejected` / `payload_invalid` |

W-7, W-7b, and W-8 are single events, so no monitor should fire for them (M6
and M7 need more than 4). W-7b also makes Sentry offer the `payload_invalid`
value before M6 is built. The probe records the `x-railway-request-id` of W-4 for the
trace check.

### Checks

- **Trace.** From W-4's `railway_request_id`, find its Railway log lines, read
  `request_id`, `trace_id`, `release`, and `deployment_id`, and open the same
  trace in Sentry. No user identifier is used in the search.
- **Absence.** Export the walkthrough window's Railway service logs to a
  temporary directory outside the repository, following the runbook. The probe
  scans the export for each marker, each token, both credential values, and
  each presigned URL it received, and prints only a match count per class.
  The export is then deleted. Claude searches Sentry errors, spans, and
  metrics for the markers. Every count must be zero, except where the privacy
  policy allows a value (for example the unknown-path marker in Django
  `Not Found` lines, if one is used).
- **Dimensions.** Every metric the run produced passes the #211 metric
  scrubber, and no dashboard widget or monitor groups or filters by anything
  outside the allow-list.
- **Alerts.** M6 opened an issue and emailed for W-10. No monitor opened an
  issue for W-7, W-7b, or W-8.

### Probe contract

The Wave 3 contract applies in full, with these Staging changes:

- Targets only the canonical Staging origin through the #203 preflight
  (`scripts/api_staging_preflight.validate_target`), and refuses any other
  origin, redirect, or failed preflight.
- Accepts Clerk session tokens only through hidden prompts. It never uses a
  Clerk secret key, never creates sessions or tokens, and never stores a token
  outside process memory. The maintainer signs out of both accounts afterwards.
- Never uploads, replaces, or clears an image.
- Resolves the convention, fursuit, and activation through the player APIs
  and fails closed if the baseline does not match (for example, W-4 not
  returning `created`).
- Prints only stage names, status codes, outcome classes, match counts,
  W-4's `railway_request_id`, and its two random markers (synthetic values,
  needed for the Sentry search).
- Lives in a temporary directory outside the repository and is deleted after
  the run; deletion is confirmed.

## Durable evidence

- **New `docs/development/field-beta-observability-validation.md`.** The run
  record, the coverage table, limitations, and the #199 handoff.
- **`docs/operations/field-beta-operations.md`.** M6, D6, D7, and D10 marked
  built; the shared alert connected to M1 to M7; R-6 evidence.
- **Ledgers.** The #216 spec ledger records its merge as `19abf91` (#273);
  this spec's ledger records the run; observability §7 points to the
  validation record.

### Coverage table

Each row names the earlier evidence and what the Staging walkthrough showed.

| Area | Earlier evidence | Staging walkthrough |
| --- | --- | --- |
| Architecture and backend | ADR 0007, observability architecture | Telemetry from Staging reached Railway and Sentry as designed |
| Structured JSON logging | #210 D-1, #212 D-7 | Walkthrough log lines |
| Request correlation | #210 D-1, D-2 | Trace check |
| Build and environment identity | #201, #210 D-2, #216 R-8 | `release`, `deployment_id`, D11 |
| Error reporting | #210 D-3 (Development shell) | Not re-observed; limitation |
| HTTP latency, throughput, server errors | #212 D-4 to D-8, #216 R-2, R-3, R-5 | D2 to D5 for the walkthrough |
| Domain outcomes | #213 E-1 to E-5 | W-1 to W-10 |
| Database, runtime, auth, storage | #214 E-1 to E-5, #216 R-1, R-4, R-7 | V-2 storage signal; W-8; D8 |
| Redaction | #211, #212 D-6, D-9, #213 E-5, #214 E-5 | Absence check |
| Bounded dimensions | #211, #212 D-5 | Dimension check |
| Retention and access | #215 | This run's evidence follows the policy |
| Dashboard | #216 R-8 | D2 to D11 including D6, D7, D10 |
| Actionable alerts | #216 R-1 to R-5, R-7 | R-6; no page for W-7 or W-8 |

### #199 handoff

The validation record lists which signals #199 can use and how:

- **Run diagnostics:** request metric by route and status class (D2, D3),
  `release` (D11), `request_id` and `trace_id`.
- **Resource pressure:** D5 p95 and M3, database connection attempts and
  duration (D8, M4), Railway CPU and memory, Gunicorn worker timeout lines.
- **Catch-flow failures:** D6, D7, M5, M6, and the credential-resolution and
  catch-session outcomes.
- **Regression investigation:** `release` and `deployment_id` on log lines,
  errors, and spans; per-request lookup by `request_id`.

It also states the low-traffic threshold caveat and that simulation reports
follow the [retention policy](../architecture/backend/telemetry-retention-access.md#7-simulation-reports).

## Scope

### In scope

- This spec, the probe (temporary, uncommitted), and the run in Staging.
- The maintainer's Sentry build of M6, D6, D7, and D10.
- Two guarded #204 resets.
- The documentation listed under [Durable evidence](#durable-evidence).

### Out of scope

- Application code, settings, telemetry, or public API changes.
- A committed authenticated launcher or test harness.
- Fault injection, stopping services, changing Railway variables, or load.
- Uploading, replacing, or clearing Staging images.
- New monitors, widgets, or dimensions beyond M6, D6, D7, and D10.
- Product analytics, frontend behavior, simulation tooling, on-call programs.

## Acceptance Contract

**AC-1 Coverage.** The validation record covers all 13 areas, each with its
earlier evidence and its Staging result or the reason none was taken.

**AC-2 Foundations reused.** The run uses the #200 Staging target, the #201
build identity, and the #203 health semantics without changing them.

**AC-3 Distinguishable outcomes.** Staging evidence shows `created`,
`already_caught`, `credential_revoked`, `payload_invalid`, and `token_invalid`
as distinct outcomes. Server failure and degradation are cited or recorded as
limitations.

**AC-4 Trace.** One request is followed by `railway_request_id`, `request_id`,
and `trace_id` with build and environment context, without searching by user.

**AC-5 Absence.** No marker, token, credential, or presigned URL from the run
appears in Railway logs, Sentry, dashboards, alerts, or durable evidence.

**AC-6 Bounded dimensions.** Every metric the run produced carries only
allow-listed attributes.

**AC-7 Alerts.** M6, D6, D7, and D10 are built and checked; R-6 fires and
emails; W-7, W-7b, and W-8 do not page.

**AC-8 Handoff.** The record names the signals #199 can use and their limits.

**AC-9 Limitations.** Every limitation and unverified boundary is stated
plainly.

**AC-10 Nothing excluded.** No item from the out-of-scope list is introduced.

## Verification

- No code changes: `NO NEW TEST REQUIRED`.
- Independent review of the probe source before it runs.
- `./scripts/doctor.sh` and `git diff --check`.
- Read-only Sentry check of M6, D6, D7, and D10 against the guide.
- Independent review of the documentation diff.

## Risks

- **Baseline drift.** If Staging changed since 2026-09-29, the opening reset
  restores it; if the reset's guards refuse, the run stops.
- **Token expiry.** A slow step fails with 401. The probe treats it as
  `BLOCKED`, not a result, and asks for a fresh token.
- **Reset storage metric not delivered.** If V-2 shows no storage metric (for
  example, the shell exits before the SDK flushes), D10 is recorded as unbuilt
  with the reason; no upload is used instead.
- **Shared alert disconnection.** Saving the shared alert can disconnect every
  monitor; V-6 checks the connections.

## Known limitations

- A request-path server error has not been observed in a deployed environment.
- Readiness, database, and latency degradation are not reproduced in Staging.
- Absence is proven for this run's values, not for all possible data.
- No Staging request-path media upload is exercised.
- Thresholds remain low-traffic starting points.
