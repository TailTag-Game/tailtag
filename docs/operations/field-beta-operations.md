# Field-beta operations dashboard and alerts

This guide describes the one Sentry dashboard and the seven monitors that watch
TailTag Staging during rehearsal and field beta. It covers what each widget and
monitor uses, why its threshold was chosen, how to respond when it fires, and
how to build or change the configuration.

The contract is defined in the
[#216 spec](../specs/2026-09-30-field-beta-operations-dashboard.md). The
signals are explained in [backend service signals](backend-service-signals.md),
[backend domain outcomes](backend-domain-outcomes.md), and
[backend dependency health](backend-dependency-health.md). What to do about an
incident is in [Staging backend first response](staging-first-response.md).

## Where it lives and who sees it

- The dashboard and monitors live in the Sentry project that Development and
  Staging share. Every widget and monitor is set to the `staging` environment.
  Development is never alerted on.
- Only the observability owner has Sentry access, and alert email goes only to
  them. Access, roles, and how to grant them follow the
  [telemetry retention and access policy](../architecture/backend/telemetry-retention-access.md#5-access).
- Sentry keeps metrics, spans, errors, and uptime results for 30 days on the
  current plan. Monitor issues and their history follow the same retention. To
  keep anything longer, follow the
  [evidence preservation runbook](telemetry-evidence-preservation.md).
- Uptime check results may be stored outside the organization's data region,
  as Sentry warns when uptime monitoring is enabled. The checks only request the
  public `/health/ready`, which returns no personal data.
- Alert emails carry the monitor name, the query, and the value that crossed
  the threshold. They contain no user or entity identifiers.

## Dashboard

The dashboard is named **TailTag field beta**, with its environment filter set
to `staging`. Widgets use only route templates, status classes, outcomes,
reasons, `rpc.method`, and release. Never add a widget that groups by user,
or one of Sentry's default user widgets such as `count_unique(user)`.

| # | Question | Dataset | Widget |
| --- | --- | --- | --- |
| D1 | Is TailTag healthy? | — | D4's widget description links the M1 uptime monitor. Dashboards have no uptime widget |
| D2 | Traffic and throughput | Application Metrics | `sum(tailtag.http.server.requests)`, line, grouped by `http.response.status_class` |
| D3 | Busiest routes | Application Metrics | `sum(tailtag.http.server.requests)`, bar, grouped by `http.route`, top 10 |
| D4 | Server errors | Application Metrics | `sum(tailtag.http.server.requests)` where `http.response.status_class` is `5xx`, line |
| D5 | Are requests slow? | Spans | `p50(span.duration)` and `p95(span.duration)` where `is_transaction` is `true`, grouped by `transaction` |
| D6 | Are catches succeeding? | Application Metrics | `sum(tailtag.catches.confirmation)`, grouped by `tailtag.outcome` |
| D7 | Why are catches rejected? | Application Metrics | `sum(tailtag.catches.confirmation)` where `tailtag.outcome` is `rejected`, grouped by `tailtag.reason` |
| D8 | Is PostgreSQL healthy? | Application Metrics | Two widgets: `sum(tailtag.db.connection.attempts)`, line, grouped by `tailtag.outcome` and `tailtag.reason`; and `p95(tailtag.db.connection.duration)`, line |
| D9 | Is authentication abnormal? | Application Metrics | `sum(tailtag.authentication.verification)`, grouped by `tailtag.reason` |
| D10 | Is media storage failing? | Application Metrics | `sum(tailtag.media.storage.operations)` where `tailtag.outcome` is `failed`, grouped by `rpc.method` and `tailtag.reason` |
| D11 | Which build is observed? | Application Metrics | `sum(tailtag.http.server.requests)`, bar, grouped by `release` |

Application Metrics widgets cannot be tables, so grouped counts use bar or
line charts. A metric appears in the widget builder only after Staging has
emitted it, so a widget for a signal Staging has not produced yet is added
once it has.

## Monitors

M6, D6, D7, and D10 are not built yet. Staging had not emitted their metrics
when the rest was built, and Sentry offers a metric only after it has been
emitted. They are tracked in
[#217](https://github.com/TailTag-Game/tailtag/issues/217#issuecomment-5924825747).

Every monitor uses the `staging` environment, a High priority threshold only,
and the Default resolve: the issue resolves when the value is back at or below
the threshold. Sentry's "Above N" means more than N. Each monitor is connected
to one alert that emails the observability owner.

| # | Alert | Dataset and query | Interval | High priority |
| --- | --- | --- | --- | --- |
| M1 | Readiness failure | Uptime: `GET` Staging `/health/ready`, timeout 10 s | 1 minute | Down after 3 consecutive failures; up after 1 success |
| M2 | Server errors | Application Metrics: `sum` of `tailtag.http.server.requests`, `http.response.status_class` is `5xx` | 10 minutes | Above 4 |
| M3 | Severe latency | Spans: `p95(span.duration)`, `is_transaction` is `true` | 30 minutes | Above 2,000 ms |
| M4 | PostgreSQL refusing connections | Application Metrics: `sum` of `tailtag.db.connection.attempts`, `tailtag.outcome` is `failed` | 10 minutes | Above 2 |
| M5 | Catch confirmation server errors | Application Metrics: `sum` of `tailtag.http.server.requests`, `http.route` is `api/catches/confirm/` and `http.response.status_class` is `5xx` | 10 minutes | Above 1 |
| M6 | Catch payload rejections | Application Metrics: `sum` of `tailtag.catches.confirmation`, `tailtag.reason` is `payload_invalid` | 10 minutes | Above 4 |
| M7 | Authentication failures | Application Metrics: `sum` of `tailtag.authentication.verification`, `tailtag.reason` is `token_invalid` or `claims_missing` or `verifier_misconfigured` or `user_resolution_unavailable` or `other` | 10 minutes | Above 4 |

### Why these thresholds

The thresholds are operational starting points chosen while Staging traffic is
near zero. They are not service level objectives. Revisit them after the #199
simulations, after the first field-beta event, or when a monitor fires
without a real problem.

- **Counts, not rates.** With a handful of requests, a percentage swings from 0
  to 100 on one request. A count over a window is stable at low traffic.
- **The interval is what makes an alert sustained.** Sentry has no "N
  consecutive evaluations" setting for these monitors. A 10-minute window
  means one bad request cannot fire M2, M6, or M7.
- **M1** fires after about 3 minutes of failed readiness. The 10-second timeout
  is above the 5-second database connect timeout, so a slow database appears
  as a 503 rather than a timeout.
- **M3** uses a 30-minute window because a p95 over a few transactions is
  noisy. 2 seconds is far above the tens of milliseconds seen in Development.
- **M4** has a low threshold because a healthy API almost never fails to
  connect. It counts every failure reason, including `too_many_connections`.
- **M5** overlaps M2 at a lower threshold so a catch-flow failure is named
  directly. Catches are the core of the game.
- **M6 and M7** watch only reasons that point to a client bug or a
  configuration problem. Normal player outcomes such as `self_catch`,
  `session_expired`, or `credential_revoked`, and client token outcomes such as
  `token_expired` and `malformed_header`, stay on the dashboard.

## When an alert fires

1. Open the monitor's issue in Sentry. Note the time window and the value.
2. Open the dashboard for the same window. Check D11 for the build and D2 for
   whether traffic changed.
3. Follow the response for that monitor:

| Monitor | First look | Response |
| --- | --- | --- |
| M1 | `/health/identity` and the latest Staging deployment; D8 for failed connection reasons | [Bad deployment](staging-first-response.md#bad-deployment), [Database unavailable or degraded](staging-first-response.md#database-unavailable-or-degraded) |
| M2 | D3 and D4 for the route; Sentry issues for the exception | [Bad deployment](staging-first-response.md#bad-deployment) |
| M3 | D5 for the slow transaction; Railway CPU and memory | [Abnormal API load](staging-first-response.md#abnormal-api-load) |
| M4 | D8 for the reason (`timeout`, `too_many_connections`, `unreachable`, `rejected`, `other`) | [Database unavailable or degraded](staging-first-response.md#database-unavailable-or-degraded) |
| M5, M6 | D6 and D7; Sentry issues on the catch route | [Elevated catch-confirmation failures](staging-first-response.md#elevated-catch-confirmation-failures) |
| M7 | D9 for which reason rose | [Clerk or authentication failure](staging-first-response.md#clerk-or-authentication-failure) |

Response is best effort by the observability owner. There is no on-call
rotation. When preserving anything about the incident, follow the
[evidence preservation runbook](telemetry-evidence-preservation.md).

## Building or changing the configuration

The observability owner builds and changes the dashboard and monitors by hand
in the Sentry UI. There is no Sentry write token and no configuration as code.
This guide is the record of what should exist: change the guide in the same
pull request as, or before, any change in Sentry.

To build a metric or span monitor:

1. Start from **Explore**, with the environment set to `staging`, and enter the
   query from the table. Confirm it returns data, then use **Save as** to
   create a monitor.
2. In the monitor form, confirm the project and the `staging` environment, the
   dataset, the interval, and the filter.
3. Choose **Threshold**, set only **High priority** to the table's value, and
   leave **Resolve** on Default.
4. Name the monitor `Staging M<n>: <alert>`, for example
   `Staging M2: Server errors`. Paste the monitor's response row from this
   guide into **Describe**.
5. Under **Alert**, use **Connect Existing Alerts** to connect
   `Staging field beta: email observability owner`.

The shared alert, `Staging field beta: email observability owner`, emails the
observability owner when a connected monitor's issue is created and when a
resolved issue comes back. Without the second trigger, a monitor that fires a
second time reopens its old issue and sends nothing. The alert's action
interval is 0 minutes, so every trigger notifies.

Saving the shared alert, including after using **Send Test Notification**, can
replace its connected monitors with "Issue Stream: All Projects". That
disconnects every monitor and makes the alert fire on any issue in any
environment. After any edit to the alert, check that it is still connected to
exactly M1 to M5 and M7.

The recipient's own Sentry notification settings must allow issue alert email
for the project (**User Settings → Notifications → Issue Alerts**, including
any project override). If they do not, the alert fires and no email is sent.
The #216 rehearsal hit this.

To build the uptime monitor, choose **Uptime** as the monitor type and use the
M1 row. Set the environment to `staging`. Leave trace sampling off and
response capture on: on a failed check Sentry keeps the response status,
headers, and body of the public readiness endpoint, which contain no personal
data.

A read-only check that the saved configuration matches this guide may use an
assistant Sentry connector under the observability owner's account, read-only,
as the [access policy](../architecture/backend/telemetry-retention-access.md#rules)
allows. For #216 the owner authorized it directly on 2026-10-01; that grant is
recorded in the
[#216 spec ledger](../specs/2026-09-30-field-beta-operations-dashboard.md#status-and-phase-ledger)
rather than as an issue comment.

## Rehearsal

The rehearsal proves that each monitor opens an issue and sends email, without
breaking anything. #212 to #214 already prove that real failures produce the
signals. Run it in Staging after the monitors are saved, and again after any
change to a monitor's query.

- Never stop a service, change a Railway variable, or generate load.
- Change one monitor at a time, and restore it straight after its check.
- Send only a few dozen ordinary requests in total.

| # | Monitor | Temporary change | Safe signal | Expected |
| --- | --- | --- | --- | --- |
| R-1 | M1 | URL to an unknown path such as `/health/rehearsal` | 404 from the API | Down after 3 checks and email; restore the URL; up |
| R-2 | M2 | `5xx` → `4xx` | 5 or more unauthenticated `GET /api/conventions/1/` (401) | Issue and email; restore; resolves |
| R-3 | M3 | Threshold below the current p95, 5-minute interval | A few `GET /api/schema/` | Issue and email; restore; resolves |
| R-4 | M4 | `failed` → `succeeded` | 3 or more `GET /health/ready` | Issue and email; restore; resolves |
| R-5 | M5 | `5xx` → `4xx` | 2 or more unauthenticated `POST /api/catches/confirm/` (401) | Issue and email; restore; resolves |
| R-6 | M6 | None | 5 or more malformed `POST /api/catches/confirm/` from an approved Staging test player | Issue and email; resolves |
| R-7 | M7 | None | 5 or more `GET /api/me/` with `Authorization: Bearer` and a non-token value | Issue and email (`token_invalid`); resolves |
| R-8 | Dashboard | None | Traffic from R-1 to R-7 | D2 to D5, D8, D9, and D11 show the rehearsal; D11 shows the Staging `source_sha`. D7 waits for M6 |

R-6 needs authenticated catch traffic, for which replacement Staging has no
approved launcher yet. It is deferred with M6 to #217.

Write the evidence by hand from allow-listed values: counts, outcomes, reasons,
status classes, route templates, `source_sha`, Sentry issue short IDs, and
times. Check it against the
[must-not-contain list](../architecture/backend/telemetry-retention-access.md#6-preserved-evidence)
before committing it; in particular, no Sentry or Railway URLs.

## Limits

- Pool exhaustion is not observable; the API has no connection pool. M4 and M1
  catch PostgreSQL refusing or failing connections instead.
- A Clerk outage does not reach the API, because token verification makes no
  network call. It shows as falling authenticated traffic and player sign-in
  failures. Check Clerk's status page.
- Thresholds are counts tuned for low traffic. At very low traffic a real fault
  can stay below a threshold; at field-beta traffic the same count may fire too
  easily.
- Latency comes from sampled transactions. If Staging's
  `SENTRY_TRACES_SAMPLE_RATE` is unset, D5 and M3 go blank.
- The configuration is built by hand, so it can drift from this guide. Nothing
  checks it automatically.
- Development is not monitored. Production does not exist yet; it gets its own
  Sentry project and its own copy of this configuration.

## Staging evidence

Recorded on 2026-10-01 against Staging deployment `95c3ee64` at `b1d8a7e`.
Times are UTC.

- **R-1 passed after a notification fix.** With M1's URL set to
  `/health/rehearsal`, checks returned 404 from 04:39. The third failure at
  04:41 opened `TAILTAG-TESTING-2`, and the shared alert fired at 04:41:59.
  After the URL was restored the monitor returned to `ok` and the issue
  resolved. No email arrived, because the owner's issue alert notifications
  were off for the project. After that was turned on, a second run reopened
  the same issue as regressed at 04:52 and the alert fired at 04:53:00 through
  its regression trigger, but email still did not arrive. A test notification
  from the alert then did arrive. Saving the alert for that test replaced its
  connected monitors with "Issue Stream: All Projects"; it was reconnected to
  M1 to M5 and M7 at 05:06 before R-2.
- **R-2 passed.** With M2's filter swapped to `4xx`, 6 unauthenticated
  `GET /api/conventions/1/` requests (401) were sent at 05:06:36. M2 evaluated
  6 above 4 at 05:11:44 and opened `TAILTAG-TESTING-4`. The shared alert fired
  at 05:13:09 and the email arrived, the first email confirmed from a real
  firing. The filter was restored to `5xx` at 05:14:25, still connected to the
  alert. `TAILTAG-TESTING-4` resolved afterwards.
- **R-3 passed.** With M3 set to above 1 ms over 5 minutes, 5 `GET /api/schema/`
  requests (200) were sent at 05:16:42. M3 evaluated a p95 of 31.4 ms at
  05:23:33 and opened `TAILTAG-TESTING-5`; the alert fired and the email
  arrived. M3 was restored to above 2,000 ms over 30 minutes at 05:25:26,
  still connected to the alert. `TAILTAG-TESTING-5` resolved afterwards.
- **R-4 passed.** With M4's filter swapped to `succeeded`, 3
  `GET /health/ready` requests (200) were sent at 05:27:30, on top of M1's
  checks. M4 evaluated 10 above 2 at 05:30:54 and opened
  `TAILTAG-TESTING-6`; the alert email arrived. The filter was restored to
  `failed` at 05:35:10, still connected to the alert. `TAILTAG-TESTING-6`
  resolved afterwards.
- **R-5 passed.** With M5's status class swapped to `4xx`, 3 unauthenticated
  `POST /api/catches/confirm/` requests (401) were sent at 05:37:54. M5
  evaluated 3 above 1 at 05:42:04 and opened `TAILTAG-TESTING-7`; the alert
  email arrived. The filter was restored to `5xx` at 05:44:51, still connected
  to the alert. `TAILTAG-TESTING-7` resolved afterwards.
- **R-7 passed with the real condition.** 6 `GET /api/me/` requests with a
  non-token bearer value (401, `token_invalid`) were sent at 05:45:17. M7
  evaluated 6 above 4 at 05:50:56 and opened `TAILTAG-TESTING-8`; the alert
  email arrived. No swap was needed.
- **Reopen email confirmed.** After `TAILTAG-TESTING-8` resolved, the same 6
  requests were sent again at 06:03:52. M7 evaluated 6 above 4 at 06:08:42
  and reopened the issue as regressed; the alert fired at 06:09:26 through
  its regression trigger and the email arrived. A monitor that fires again
  therefore notifies. Why R-1's reopen at 04:53 sent no email is not known; it
  was the first firing after the owner's notification settings changed.
- **R-8 passed.** Over the last 3 hours the dashboard showed: D2 `2xx` and
  `4xx` only, with the rehearsal 401 spikes; D3 led by `health/ready` (133)
  and `<unmatched>` (22, R-1's checks of the rehearsal path); D4 flat at 0;
  D5 `/api/schema/` p95 31.58 ms; D8 about one successful connection attempt a
  minute, dropping to 0 while M1 checked the rehearsal path, with a p95 of
  15 to 25 ms; D9 `token_invalid` only; D11 one build, `b1d8a7e`.
- **Final state.** At 05:57 every monitor was back on its configured
  condition, and the shared alert was connected to exactly M1 to M5 and M7.
  Rehearsal issues `TAILTAG-TESTING-2` and `-4` to `-7` had resolved, and
  `-8` resolves once its rejections leave M7's window.

Not rehearsed in #216: R-6 and M6, deferred to
[#217](https://github.com/TailTag-Game/tailtag/issues/217#issuecomment-5924825747).
