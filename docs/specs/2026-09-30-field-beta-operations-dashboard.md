# Field-beta operations dashboard and alerts

Issue: [#216](https://github.com/TailTag-Game/tailtag/issues/216) (OB-8).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #212 ([backend service signals](../operations/backend-service-signals.md)), #213 ([backend domain outcomes](../operations/backend-domain-outcomes.md)), #214 ([backend dependency health](../operations/backend-dependency-health.md)), #215 ([telemetry retention and access](../architecture/backend/telemetry-retention-access.md)).
Response procedures: [Staging backend first response](../operations/staging-first-response.md).
Consumers: #217 (final validation), #199 (simulations).

## Status and phase ledger

Execution: STANDARD COMPACT. Assurance: SECURITY (privacy of dashboard
queries and alert notifications, operator access), RELIABILITY (alert
correctness).
Completed: scope review, uncertainty review and research, maintainer approval
of decisions 1 to 4 below (2026-09-30).
Spec approved by the maintainer (2026-09-30).
P-1 failed (2026-09-30): Sentry has no `staging` environment. Staging
`/health/identity` reports `source_sha` `f16ff75`, which predates the Sentry
SDK (#210, `2416110`), and Staging has no `SENTRY_*` variables. Staging
readiness returned 200.
P-1 remediation (2026-09-30): the maintainer added `SENTRY_DSN` and
`SENTRY_TRACES_SAMPLE_RATE` to Staging. Applying them made Railway redeploy
from the latest `main` commit, outside the controlled promotion path:
deployment `95f3d2dc` at `b1d8a7e`, readiness 200, no promotion receipt. A
first promotion attempt stopped at argument validation (an empty SHA from a
shell quoting error) before any GitHub or Railway call.
Controlled promotion of `b1d8a7e` succeeded (2026-10-01): deployment
`95c3ee64`, every outcome `SUCCEEDED`, final state `ACTIVE`
([receipt](../development/staging-deployments/95c3ee64-bd72-47cf-abdb-280b413fbaa9.json)).
`/health/identity` reports that deployment and readiness returns 200.
P-1 passed (2026-10-01): Sentry shows the `staging` environment with
`/api/schema/` and `/api/docs/` transactions whose release is `b1d8a7e`, and
`tailtag.http.server.requests` grouped by `http.route` (`health/ready` 5,
`health/identity` 2, `health/live`, `api/docs/`, `api/schema/` 1 each). Route
values have no leading slash.
P-2 partial (2026-10-01): metric and span monitors take a project and
environment (`staging`), a dataset, an interval, an aggregate and filter,
and Threshold, Change, or Dynamic detection with High and Medium priority
thresholds and a Default or Custom resolve. No consecutive-evaluation setting
is offered, so the interval is the sustain mechanism. `p95(span.duration)` with
`is_transaction:true` and `p95` of `tailtag.db.connection.duration` are
available. Monitors create issues; notification is a separate alert attached
to the monitor. A metric is offered only after Staging has emitted it; three
bad-token `GET /api/me/` requests (401) were sent to emit
`tailtag.authentication.verification`.
P-2 continued (2026-10-01): `tailtag.authentication.verification` now
appears for Staging, and the filter `tailtag.reason is token_invalid or
claims_missing` matches the 3 rejections, so one filter can match several
values. Dashboard widget datasets are Errors, Spans, Logs, Application
Metrics, Issues, Releases, and Mobile Builds; there is no uptime widget, so D1
uses the dashboard description. Uptime is a monitor type; none exists yet.
Enabling it acknowledges that uptime check data may be stored outside the
organization's data region.
P-2 passed (2026-10-01): monitor intervals offered are 5, 10, 15, and 30
minutes, 1, 2, and 4 hours, and 1 day. The uptime form takes an environment,
a 1, 5, 10, 20, 30, or 60 minute interval, editable failure and recovery
thresholds, a 1 to 60 second timeout, and the HTTP method.
P-3 (2026-10-01): the maintainer, as observability owner, authorized
Claude's use of the Sentry connector directly instead of recording a grant on
#216. The connector also exposes issue-update and Seer tools; Claude uses only
its read tools.
Build (2026-10-01): the maintainer built M1 to M5, M7, the shared email
alert (new issue or regression), and the dashboard with D1 (in D4's
description), D2 to D5, D8 (two widgets), D9, and D11. Claude checked each
against the operations guide through the read-only connector. Application
Metrics widgets cannot be tables, so D3 and D11 are bar charts.
Deferred to #217 (2026-10-01): M6, D6, D7, D10, and R-6. Staging has not
emitted a catch outcome or storage operation, so Sentry does not offer those
metrics, and there is no approved way to send authenticated catch traffic to
replacement Staging. Tracked in
[#217](https://github.com/TailTag-Game/tailtag/issues/217#issuecomment-5924825747).
Rehearsal (2026-10-01): R-1 to R-5, R-7, and R-8 passed in Staging and are
recorded in the
[operations guide](../operations/field-beta-operations.md#staging-evidence).
R-1 found two configuration faults, both fixed and documented in the guide:
the owner's issue alert email was off for the project, and saving the shared
alert for a test notification replaced its monitor connections with
"Issue Stream: All Projects".
Documentation: observability architecture §7, Staging first response,
backend service signals, and backend dependency health now point to the
guide; the #215 spec ledger records its merge.
Independent review (2026-10-01): SPEC, QUALITY, SCOPE, and SECURITY passed;
RELIABILITY failed on one finding. Remediated by the parent:

- H-1 (HIGH): email on a reopened issue had not been shown to work. M7 was
  fired again and reopened `TAILTAG-TESTING-8`; the regression trigger sent
  the email. The overstated R-2 delivery claim was corrected.
- L-1 (LOW): Staging first response no longer says no request-rate chart or
  alert exists.
- L-2 (LOW): D1's location and the R-8 widget list match the guide; M4's
  first look includes `other`.
- L-3 (LOW): the guide names the spec ledger as the connector grant record.

Remediation verification: `./scripts/doctor.sh` and `git diff --check`
passed.
Current: pull request review.

## Problem

The signals from #212, #213, and #214 exist in Sentry, but nothing watches
them. An operator has no single view of whether TailTag is healthy, and
nothing notifies anyone when it is not. The Staging first-response procedures
say there is no alert for elevated catch failures and hand detection to #198.

## Evidence

Sentry public documentation and pricing, read 2026-09-30:

| Fact | Value |
| --- | --- |
| Developer plan | 1 user, 10 custom dashboards, email-only notifications, 1 uptime monitor |
| Application Metrics | Generally available since 2026-05-05 on every plan; usable in dashboards and metric monitors; filter and group by custom attributes |
| Metric aggregates | counter: `sum`, `per_second`, `per_minute`; distribution: percentiles, `avg`, `count`, and others |
| Uptime monitor | Intervals 1, 5, 10, 20, 30, or 60 minutes; down after 3 consecutive failures by default, each from a different region; anything other than 2xx or a followed 3xx is a failure |
| Sampled spans | Weighted by the inverse sample rate in counts and percentiles |
| Monitor creation API | Detectors API accepts `metric_issue` only; uptime creation is not documented; needs `alerts:write` |

Not documented: metric monitor time-window options, resolve behavior,
consecutive-evaluation settings, and whether uptime monitors take an
environment.

TailTag evidence:

- #212 Development evidence: the monitor builder accepted `p95(span.duration)`
  and the request metric filtered to `5xx`, each with a static threshold.
- The API has no connection pool, so pool exhaustion is not observable
  ([backend dependency health](../operations/backend-dependency-health.md)).
- Token verification is networkless, so a Clerk outage never reaches the API.
- All #212 to #214 evidence was collected in Development. Staging delivery to
  Sentry is not yet confirmed.

## Decisions

Approved by the maintainer on 2026-09-30.

1. **Database criterion.** "Database exhaustion or unavailability" is read as
   **PostgreSQL unavailable or refusing connections**. It is detected by the
   readiness uptime monitor and by failed `tailtag.db.connection.attempts`,
   which include `too_many_connections`. No new connection-count telemetry is
   added; the revisit triggers in the dependency health guide still apply.
2. **Rehearsal without failure code.** No code is added to make the API fail.
   Each monitor is proven by temporarily swapping its filter or threshold to a
   signal that can be produced safely, confirming it opens an issue and
   notifies, then restoring it. #212 to #214 already prove that real faults
   produce the signals.
3. **Catch-confirmation alert.** Alerts on server errors on the
   catch-confirmation route and on `payload_invalid` rejections. All other
   rejection reasons are normal player or owner behavior and stay on the
   dashboard only.
4. **Built by hand, verified read-only.** The maintainer builds the dashboard
   and monitors in the Sentry UI from this spec. No write-scoped Sentry token
   or Terraform is introduced. Claude verifies through a read-only Sentry
   connector once that grant is recorded on #216. Configuration as code is
   revisited when Production needs its own Sentry project.

Further decisions in this spec:

5. **Plan.** Stay on the Developer plan. Notifications are email to the
   observability owner. The single uptime monitor watches Staging.
6. **Counts, not rates.** Every metric monitor alerts on a count over a window.
   Traffic is too low for ratios to be stable.
7. **Staging only.** Every widget and monitor filters to `environment:staging`.
   Development is never alerted on.
8. **Starting thresholds.** Thresholds are operational starting points, not
   SLOs. They are recorded in the operations guide and revisited after #199
   simulations or real field-beta traffic.

## Prerequisites

- **P-1 Staging delivers to Sentry.** Recent events, transactions, and
  `tailtag.http.server.requests` exist with `environment:staging`, and
  Staging's `SENTRY_TRACES_SAMPLE_RATE` is `1.0`. If Staging does not deliver,
  #216 stops and the gap is raised against #198.
- **P-2 Monitor builder probe.** In the Sentry UI, without saving, confirm:
  available time windows and evaluation intervals for metric and span
  monitors; how a monitor resolves; whether a metric monitor can filter one
  attribute to several values; whether a dashboard can show uptime status; and
  whether the uptime monitor takes an environment. Thresholds and windows
  below are adjusted to what the UI offers.
- **P-3 Connector grant.** The maintainer records the read-only Sentry
  connector grant on #216, following the
  [grant procedure](../operations/telemetry-evidence-preservation.md#grant-or-remove-access).

## Dashboard

One Sentry dashboard, **TailTag field beta**, with an environment filter set to
`staging`. Every widget uses only allow-listed attributes: route templates,
status classes, outcomes, reasons, `rpc.method`, and release.

| # | Question | Widget |
| --- | --- | --- |
| D1 | Is TailTag healthy? | D4's widget description links the M1 uptime monitor; dashboards have no uptime widget |
| D2 | Traffic and throughput | `sum(tailtag.http.server.requests)` over time, grouped by `http.response.status_class` |
| D3 | Busiest routes | `sum(tailtag.http.server.requests)` grouped by `http.route`, top 10 |
| D4 | Server errors | `sum(tailtag.http.server.requests)` where `http.response.status_class:5xx`, over time, and unresolved Sentry issues |
| D5 | Are requests slow? | `p50` and `p95` of transaction `span.duration`, grouped by transaction |
| D6 | Are catches succeeding? | `sum(tailtag.catches.confirmation)` grouped by `tailtag.outcome` |
| D7 | Why are catches rejected? | `sum(tailtag.catches.confirmation)` where `tailtag.outcome:rejected`, grouped by `tailtag.reason` |
| D8 | Is PostgreSQL healthy? | `sum(tailtag.db.connection.attempts)` grouped by `tailtag.outcome` and `tailtag.reason`; `p95(tailtag.db.connection.duration)` |
| D9 | Is authentication abnormal? | `sum(tailtag.authentication.verification)` grouped by `tailtag.reason` |
| D10 | Is media storage failing? | `sum(tailtag.media.storage.operations)` where `tailtag.outcome:failed`, grouped by `rpc.method` and `tailtag.reason` |
| D11 | Which build is observed? | `sum(tailtag.http.server.requests)` grouped by `release`, so the deployed `source_sha` is visible |

## Monitors

All monitors use the Staging environment, a High priority threshold only, the
Default resolve (the issue resolves when the value falls back to the
threshold or below), and an attached alert that emails the observability
owner. Sentry's "Above N" means more than N. The
[operations guide](../operations/field-beta-operations.md) is authoritative
once the monitors are built; later threshold changes are made there.

| # | Alert | Dataset and query | Interval | High priority | Response |
| --- | --- | --- | --- | --- | --- |
| M1 | Readiness failure | Uptime: `GET` Staging `/health/ready`, timeout 10 s | 1 minute | Down after 3 consecutive failures; up after 1 success | [Bad deployment](../operations/staging-first-response.md#bad-deployment), [Database unavailable or degraded](../operations/staging-first-response.md#database-unavailable-or-degraded) |
| M2 | Server errors | Application Metrics: `sum` of `tailtag.http.server.requests`, `http.response.status_class` is `5xx` | 10 minutes | Above 4 | [Bad deployment](../operations/staging-first-response.md#bad-deployment) |
| M3 | Severe latency | Spans: `p95(span.duration)`, `is_transaction` is `true` | 30 minutes | Above 2,000 ms | [Abnormal API load](../operations/staging-first-response.md#abnormal-api-load) |
| M4 | PostgreSQL refusing connections | Application Metrics: `sum` of `tailtag.db.connection.attempts`, `tailtag.outcome` is `failed` | 10 minutes | Above 2 | [Database unavailable or degraded](../operations/staging-first-response.md#database-unavailable-or-degraded) |
| M5 | Catch confirmation server errors | Application Metrics: `sum` of `tailtag.http.server.requests`, `http.route` is `api/catches/confirm/` and `http.response.status_class` is `5xx` | 10 minutes | Above 1 | [Elevated catch-confirmation failures](../operations/staging-first-response.md#elevated-catch-confirmation-failures) |
| M6 | Catch payload rejections | Application Metrics: `sum` of `tailtag.catches.confirmation`, `tailtag.reason` is `payload_invalid` | 10 minutes | Above 4 | [Elevated catch-confirmation failures](../operations/staging-first-response.md#elevated-catch-confirmation-failures) |
| M7 | Authentication failures | Application Metrics: `sum` of `tailtag.authentication.verification`, `tailtag.reason` is `token_invalid` or `claims_missing` or `verifier_misconfigured` or `user_resolution_unavailable` or `other` | 10 minutes | Above 4 | [Clerk or authentication failure](../operations/staging-first-response.md#clerk-or-authentication-failure) |

Notes:

- The catch-confirmation alert is two monitors because one monitor cannot
  combine two metrics. M5 overlaps M2 at a lower threshold so a catch-flow
  failure is named directly.
- M7 leaves out `token_expired` and `malformed_header`, which are client
  behavior.
- The interval is the window the value is aggregated over. Sentry offers no
  consecutive-evaluation setting, so the interval is what makes a condition
  sustained.
- Sentry offers a metric in the builder only after the environment has emitted
  it. M6 cannot be built until Staging records a catch confirmation outcome;
  R-6 produces one.
- The uptime monitor's 10-second timeout is above the 5-second database
  connect timeout, so a slow database shows as a 503 rather than a timeout.

## Rehearsal

Run in Staging after the monitors are saved. Traffic is a few dozen ordinary
requests at most. No service is stopped, no Railway variable is changed, and no
load is generated. Each swap is restored immediately after its check.

| # | Monitor | Swap | Safe signal | Expected |
| --- | --- | --- | --- | --- |
| R-1 | M1 | URL to an unknown path such as `/health/rehearsal` | 404 from the API | Down after 3 checks, email; restore URL; up |
| R-2 | M2 | `5xx` → `4xx` | Unauthenticated `GET /api/conventions/1/` (401) | Issue and email; restore; resolves |
| R-3 | M3 | Threshold below current p95, 5-minute interval | Ordinary `GET /api/schema/` requests | Issue and email; restore; resolves |
| R-4 | M4 | `failed` → `succeeded` | `GET /health/ready` | Issue and email; restore; resolves |
| R-5 | M5 | `5xx` → `4xx` | Unauthenticated `POST /api/catches/confirm/` (401) | Issue and email; restore; resolves |
| R-6 | M6 | None | Authenticated `POST /api/catches/confirm/` with a malformed body from an approved Staging test player | Issue and email; resolves. If no approved Staging player token is available, record R-6 as not rehearsed |
| R-7 | M7 | None | Requests with `Authorization: Bearer` and a non-token value | Issue and email (`token_invalid`); resolves |
| R-8 | Dashboard | — | Traffic from R-1 to R-7 | D2 to D5, D8, D9, and D11 show the rehearsal; D11 shows the current Staging `source_sha` |

Evidence is written by hand from allow-listed values (counts, outcomes,
reasons, status classes, route templates, release, timestamps) following the
[evidence preservation runbook](../operations/telemetry-evidence-preservation.md).

## Scope

### In scope

- This spec.
- One Sentry dashboard and seven monitors, built by the maintainer.
- A maintainer operations guide: the dashboard, each monitor's condition,
  window, rationale, and response, routing and access, retention, the
  rehearsal procedure, and Staging evidence.
- Updates to the observability architecture (§7), the Staging first-response
  procedures (detection lines that say no alert exists), and the #215 spec
  ledger.

### Out of scope

- Application code, settings, telemetry, or public API changes.
- Failure-injection code, service termination, or load generation.
- A Sentry plan change, Slack or webhook routing, or a second uptime monitor.
- Configuration as code (Sentry API or Terraform) and write-scoped tokens.
- Development or Production monitors.
- Connection-count or pool telemetry.
- Anomaly detection, per-user views, product analytics, or on-call programs.

## Acceptance Contract

**AC-1 Dashboard.** One Sentry dashboard answers D1 to D11 for Staging.

**AC-2 Bounded signals.** Every widget and monitor uses only the bounded
attributes of #212 to #214 and needs no user or entity identifier or request
data.

**AC-3 Monitors.** M1 to M7 exist with the conditions in the operations guide,
covering readiness failure, sustained server errors, severe sustained latency,
PostgreSQL unavailable or refusing connections, catch-confirmation failures,
and authentication failures.

**AC-4 Sustained only.** No monitor fires on a single 4xx, a single error, or
an individual player rejection.

**AC-5 Documentation.** The operations guide records every threshold, window,
routing, access, retention, and response, and states that thresholds are
starting points.

**AC-6 Rehearsal.** R-1 to R-8 are run in Staging and recorded, with any
step not rehearsed stated with its reason. No service is terminated.

**AC-7 Build identity.** An operator can read the Staging environment and
backend build from the dashboard without user data.

**AC-8 Nothing excluded.** No extra dashboards, anomaly detection, product
analytics, new metric dimension, or on-call program.

## Verification

- No code changes: `NO NEW TEST REQUIRED`.
- `./scripts/doctor.sh` and `git diff --check`.
- Read-only connector check that the saved dashboard and monitors match the
  operations guide (after P-3).
- Rehearsal evidence R-1 to R-8.

## Risks

- **Low Staging traffic.** Thresholds are guesses until #199 or field-beta
  traffic exists. A real fault at very low traffic may stay below a count
  threshold.
- **Swap rehearsal.** Proves query, monitor, issue, and notification, but not a
  real database or 5xx failure end to end in Staging. That half rests on #212
  to #214 tests and Development evidence.
- **Hand-built configuration.** Can drift from the guide. The read-only check
  catches drift at #216 and #217; nothing catches it afterwards.
- **Single recipient.** Email to one person, best effort, no on-call.

## Known limitations

- Pool exhaustion and Clerk availability are not observable (#214).
- Latency comes from sampled transactions; if Staging tracing is turned off,
  M3 and D5 go blank.
- Development is not monitored, and Production does not exist yet.
