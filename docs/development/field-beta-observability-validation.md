# Field-beta observability validation

This is the #217 (OB-9) validation record. It shows the #198 field-beta
observability contract working in Staging, links each part to the earlier
evidence that proved it, states what could not be shown, and tells #199 which
signals it can rely on.

The contract and procedure are in the
[#217 spec](../specs/2026-10-01-field-beta-observability-validation.md). The
signals are explained in the [observability architecture](../architecture/backend/observability.md)
and the operations guides it links. The dashboard and monitors are in the
[field-beta operations guide](../operations/field-beta-operations.md).

## Staging run

Recorded on 2026-10-01 against Staging deployment `95c3ee64` at `b1d8a7e`
(`environment` `staging`). Times are UTC. The API code matched `main`
(`19abf91`); the commits in between change documentation only.

- **Opening reset.** A guarded #204 reset (21:50:34 to 21:50:55) restored the
  baseline: 2 profiles, 1 convention, 2 fursuits, 2 enrollments, 2
  activations, and no catches, sessions, or credentials. Its read of the
  designated image recorded one `tailtag.media.storage.operations`
  `HeadObject` / `succeeded`, which let the maintainer build D10.
- **Probe.** Authenticated requests came from a temporary probe, reviewed
  before it ran and deleted afterwards, following the
  [spec's probe contract](../specs/2026-10-01-field-beta-observability-validation.md#probe-contract).
  The maintainer pasted short-lived session tokens from the two synthetic
  Staging accounts at hidden prompts. The probe printed only stage names,
  status codes, counts, two random markers, and one Railway request ID.
- **Two stopped attempts.** The first stopped at the activation check, before
  any write, because the first token belonged to the catcher account. The
  second ran W-1 to W-6 and stopped at W-7, which returned 200: confirmation
  recovers an existing catch before it checks revocation, so the catcher who
  had just made the catch correctly got `already_caught`. W-7 was moved to the
  owner, and a second guarded reset (22:17:57 to 22:18:09) restored the
  baseline before the third attempt.
- **Closing reset.** A third guarded reset (22:36:57 to 22:37:12) restored the
  same baseline. Readiness returned 200 afterwards.

### Walkthrough

The third attempt ran from 22:19:01 to 22:29:34. Each step below is one
request; the outcome is the matching `tailtag.*` log line in Railway.
Sentry's outcome counts match once the second attempt's W-4, W-5, and W-7 are
included.

| Step | Who | Request | Status | Outcome |
| --- | --- | --- | --- | --- |
| W-1 | Owner | Start catch session | 200 | `catch_session` `started` |
| W-2 | Owner | Fetch catch credential | 200 | — |
| W-3 | Catcher | Resolve credential | 200 | `credential_resolution` `resolved` |
| W-4 | Catcher | Confirm catch | 201 | `catches.confirmation` `created` |
| W-5 | Catcher | Same confirmation again | 200 | `already_caught` |
| W-6 | Owner | Rotate credential | 200 | — |
| W-7 | Owner | Confirm with the old credential | 404 | `rejected` / `credential_revoked` |
| W-7b | Catcher | One malformed confirmation | 400 | `rejected` / `payload_invalid` |
| W-8 | None | `GET /api/me/` with a non-token bearer value | 401 | `authentication.verification` `rejected` / `token_invalid` |
| W-10 | Catcher | Six malformed confirmations, 22:29:23 to 22:29:24 | 400 | `rejected` / `payload_invalid` (6) |
| W-9 | Owner | Stop catch session | 200 | `catch_session` `ended` / `owner` |

Every line carried `environment` `staging`, `release` `b1d8a7e…`, and
`deployment_id` `95c3ee64…`.

### Following one request

W-4 was found in Railway by route and status alone
(`@http_route:api/catches/confirm/`, status 201), without any user
identifier.

- Railway request ID `aWkMUHRbQUGXncKo8u2xcg`, the same value the probe read
  from the response header.
- Its two log lines carry `request_id` `a68f92df19ef4fb9a55fd01ef89f69e2` and
  `trace_id` `7c5334591850435c9ac7051d6f15b1c5`.
- That trace in Sentry is the `/api/catches/confirm/` transaction: 91 ms, 23
  spans (authentication, database, and render), no errors.

### Dashboard and alerts

- **Built.** The maintainer built D6, D7, and D10, and M6 connected to the
  shared alert. A read-only check confirmed each against the operations guide
  and that the shared alert is connected to exactly M1 to M7. D10 is grouped
  by `rpc.method` only: the API sets `tailtag.reason` on storage operations only
  when one fails, and Staging has had no failure, so the grouping is not yet
  offered.
- **R-6 passed.** The six W-10 rejections made M6 evaluate 6 above 4 at
  22:35:01 and open `TAILTAG-TESTING-A`, about 5.5 minutes after the burst.
  The alert email arrived, and the issue resolved after the rejections left
  the 10-minute window.
- **No page for single events.** W-7, W-7b, and W-8 each happened once and
  opened no monitor issue.
- **Widget data.** The queries behind the widgets returned, for the last hour:
  `api/catches/confirm/` 4xx 8 and 2xx 5, including the second attempt (D2,
  D3); no 5xx (D4); `/api/catches/confirm/` p50 21.7 ms and p95 86.3 ms over
  13 transactions (D5); `created`, `already_caught`, `credential_revoked`, and
  `payload_invalid` (D6, D7); and one build, `b1d8a7e` (D11).

### Absence and dimension checks

- **Railway.** The probe exported the window's service and HTTP logs to a
  temporary directory outside the repository, confirmed its own lines were
  present (65 service records with 10 confirmations, 7 of them 400s, 2
  catch-session changes, and W-4 in both exports), and counted matches for
  every value it held: 6 session tokens, 4 Clerk subject and session IDs, 2
  catch credential tokens, 1 media URL, and the 2 markers. Every count was 0.
  The export was deleted.
- **Sentry.** No error event occurred in the window, and a search of errors for
  the marker prefix found none. The W-8 and W-10 transactions carry only the
  route and the URL path, with no user, IP address, or query string, and
  Sentry knows no request-header or query attribute in this project. A
  free-text span search for the markers found nothing, but the same search also
  found nothing for a known `request_id`, so it is not counted as evidence.
- **Dimensions.** Every metric passes through the #211 `before_send_metric`
  scrubber, which drops any attribute outside the allow-list before the metric
  leaves the process. Every dashboard widget and monitor groups or filters only
  by status class, route, transaction, outcome, reason, `rpc.method`, and
  release. No `Metric attribute rejected` warning and no error-level line
  appeared in the window's Railway logs, but that warning is logged only once
  per key for the life of a process, so its absence is supporting evidence
  only. Metric attributes were not listed one by one in Sentry.

### Incidental error event

Diagnostic requests to the retired pre-launch Railway domain at 21:53 were
refused by Django (`DisallowedHost`, 400) and produced `TAILTAG-TESTING-9`
(4 events). It is a real Staging error event, with `environment`, `release`,
`request_id`, `railway_request_id`, and trace context, and no headers,
cookies, or query string. It keeps the request path, which the
[privacy policy](../architecture/backend/telemetry-privacy.md) documents as a
known limit for this case. It did not notify, because the shared alert listens
only to M1 to M7. The maintainer resolved it.

## Coverage

| Area | Earlier evidence | Staging run |
| --- | --- | --- |
| Architecture and backend | [ADR 0007](../adrs/0007-v0-observability-backend.md), [observability architecture](../architecture/backend/observability.md) | Railway logs and Sentry received the run as designed |
| Structured JSON logging | #210 D-1, #212 D-7 ([logging](../operations/backend-logging.md#development-evidence)) | Every walkthrough line parsed as one JSON object with event, outcome, correlation, and build fields |
| Request correlation | #210 D-1, D-2 | W-4 followed from Railway request ID to `request_id` to Sentry trace |
| Build and environment identity | #201, #210 D-2, #216 R-8 | `release` and `deployment_id` on every line; D11 one build |
| Error reporting | #210 D-3 (Development shell) | `TAILTAG-TESTING-9`, a handled Staging error event; a request-path 500 was not produced |
| HTTP latency, throughput, server errors | #212 D-4 to D-8; #216 R-2, R-3, R-5 | D2 to D5 for the walkthrough; no 5xx |
| Domain outcomes | #213 E-1 to E-5 | W-1 to W-10 |
| Database, runtime, authentication, storage | #214 E-1 to E-5; #216 R-1, R-4, R-7 | Reset storage signal; W-8 `token_invalid` |
| Redaction | #211, #212 D-6 and D-9, #213 E-5, #214 E-5 | Absence checks above |
| Bounded dimensions | #211, #212 D-5 | Dimension check above |
| Retention and access | #215 | This record follows the preservation runbook and its must-not-contain list |
| Dashboard | #216 R-8 | D2 to D11, including the new D6, D7, and D10 |
| Actionable alerts | #216 R-1 to R-5, R-7 | R-6 fired; no issue for single events |

## Limitations

- **No request-path 500 in a deployed environment.** No safe way exists to
  make the API fail, and #217 adds none. Error delivery is shown by #210 D-3
  and by `TAILTAG-TESTING-9`, a handled error, not by an unhandled exception.
- **No degradation in Staging.** Readiness, database, and latency degradation
  rest on #214 E-4 (Development) and the #216 swap rehearsals R-1, R-3, and R-4.
- **Absence is shown for this run's values only.** The general guarantee is
  the #211 redaction hooks and their tests.
- **The Sentry side of the absence check is narrower than the Railway side.**
  Tokens and credentials were searched for only in Railway, since the probe
  held them only in memory. In Sentry, the check rests on there being no error
  event in the window and on the stored fields of two transactions; a
  free-text search proved nothing, and metrics were not searched for the
  markers.
- **No media upload on the request path.** Uploading, replacing, or clearing a
  baseline image would delete the #204 designated image, so storage is shown
  only through the reset's read.
- **D10 has no reason grouping** until Staging records a failed storage
  operation.
- **The aborted second attempt is not covered by the absence scan.** It sent
  the same kinds of requests as the third attempt.
- **Thresholds are low-traffic starting points**, as the operations guide
  says.

## Signals for #199

#199 simulations can rely on these signals. All are in the `staging`
environment of the shared Sentry project, or in Railway service logs.

- **Run diagnostics.** `tailtag.http.server.requests` by route and status class
  (D2, D3) counts every request, unsampled. `release` (D11) confirms which
  build served the run. Any single request is found by `request_id` in Railway
  and `trace_id` in Sentry.
- **Resource pressure.** D5 p95 and M3 for latency, from sampled transactions
  (tracing must stay on in Staging). D8 and M4 for PostgreSQL connection
  failures and connection time. Railway CPU and memory graphs, and Gunicorn
  `WORKER TIMEOUT` or `SIGKILL` lines under `@logger:gunicorn.error`, for
  worker exhaustion, which produces no Sentry event.
- **Catch-flow failures.** D6 and D7 for confirmation outcomes and reasons; M5
  for server errors on the confirmation route; M6 for payload rejections;
  `tailtag.conventions.credential_resolution` and
  `tailtag.conventions.catch_session` for the steps before a catch.
- **Regression investigation.** `release` and `deployment_id` on every log
  line, error, and span; error grouping in Sentry.

Before trusting a simulation as readiness evidence:

- A simulation at field-beta volume will cross the count thresholds that are
  tuned for near-zero traffic, so expect M2, M6, and M7 to fire on volume
  alone. Revisit the thresholds after the first run.
- Railway keeps logs for 7 days and Sentry for 30. Record anything worth
  keeping in the simulation report, following the
  [retention policy](../architecture/backend/telemetry-retention-access.md#7-simulation-reports).
- Query strings and request bodies are never recorded, so a simulation cannot
  tag its requests that way; correlate by time window, route, and `request_id`.
