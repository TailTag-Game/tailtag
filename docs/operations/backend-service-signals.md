# Backend service signals

This guide explains the API's generic service-level signals: request counts,
throughput, latency, server errors, and runtime failures. It covers what each
signal means, where to read it, and what it cannot tell you.

The contract is defined in the
[#212 spec](../specs/2026-09-29-http-runtime-telemetry.md). The wider
observability boundary is in
[observability](../architecture/backend/observability.md). Log fields and
request lookup are in [backend logging](backend-logging.md).

These signals describe the service, not the game. A rise in 4xx responses, for
example, does not say whether catches are failing. Domain outcomes are in
[backend domain outcomes](backend-domain-outcomes.md), and dependency
health is in [backend dependency health](backend-dependency-health.md).

## Signals and where they live

| Question | Signal | Where |
| --- | --- | --- |
| How many requests, and on which routes? | `tailtag.http.server.requests` count by `http.route` | Sentry metrics |
| Are server errors rising? | `tailtag.http.server.requests` count where `http.response.status_class` is `5xx` | Sentry metrics |
| Which failures are they? | Error events, grouped by exception | Sentry issues |
| Are requests slow? | p50, p95, and p99 of transaction duration by transaction name | Sentry traces (Explore) |
| Why was one request slow? | That request's transaction and its spans, including SQL | Sentry trace; Railway logs by `@request_id` |
| Did a worker hang, crash, or run out of memory? | `gunicorn.error` log lines | Railway service logs |
| Did the container restart or run out of memory? | Deployment events, and CPU and memory graphs | Railway |
| Is the service ready? | `/health/ready` | Sentry uptime monitor ([#216](https://github.com/TailTag-Game/tailtag/issues/216)) |

## The request metric

Every request that reaches Django adds a count of 1 to
`tailtag.http.server.requests`. It is recorded whether or not the request is
traced, so counts are exact rather than estimated. Its attributes are:

| Attribute | Values |
| --- | --- |
| `http.route` | Django's route template, for example `api/conventions/<int:pk>/`, or `<unmatched>` when no route matched |
| `http.request.method` | A standard HTTP method, or `_OTHER` for anything else |
| `http.response.status_class` | `1xx`, `2xx`, `3xx`, `4xx`, or `5xx` |

Sentry adds `sentry.environment` and `sentry.release`. Filter by environment
before reading any number.

- **Throughput** is the count over time. Group by `http.route` to see which
  routes carry the traffic.
- **The 5xx rate** is the `5xx` count divided by the total count. Exclude
  `http.route` values `health/live` and `health/ready` from both. A failing
  readiness check returns 503 on purpose, and health checks can outnumber real
  requests when traffic is low.
- **`<unmatched>`** counts requests that finished without matching a route.
  Most are 404s for URLs the API does not serve; a burst usually means a
  scanner or a client calling a removed route. Requests answered by middleware
  before routing also land here: static files served by WhiteNoise (`2xx`),
  missing-slash redirects (`3xx`), and disallowed `Host` headers (`4xx`).
- **`_OTHER`** counts requests with a non-standard HTTP method. These should be
  rare.
- The status class is what the API returned. A 4xx is a client outcome, such as
  a failed authentication or a validation error, not a server problem. Do not
  read 4xx counts as a domain failure rate.

## Latency

Latency comes from Sentry transactions, one per traced request. A transaction
is named by Sentry's form of the route, for example `/api/conventions/{pk}/`.
The request metric uses Django's form of the same route,
`api/conventions/<int:pk>/`. Requests that match no route are named
`<unmatched>`, and their transactions carry no request URL, because the path is
whatever the client sent.

- In Sentry Explore, choose the traces dataset, filter by environment and
  transaction name, and chart p50, p95, and p99 of span duration.
- Sentry weights each sampled transaction by the inverse of the sample rate, so
  percentiles and counts stay representative when sampling below 1.0.
- A percentile over few requests is an estimate. At low traffic, treat p99 on a
  quiet route as noisy, and compare it with p50 and the request count before
  acting.
- `/health/live` and `/health/ready` are never traced. They are frequent and
  fast, and would drown out real requests.
- `HEAD` and `OPTIONS` requests are never traced, which is the Sentry SDK's
  default. They are mostly probes, scanners, and preflights. The request metric
  still counts them under their method.
- A transaction's spans include SQL queries with parameterized text, for
  example `SELECT … WHERE id = %s`. Parameter values are never sent.

Tracing is controlled by `SENTRY_TRACES_SAMPLE_RATE`, a number from `0` to `1`.
When it is unset or empty, no transactions are sent, but the request metric and
error events still are. Any other value stops API startup with an error that
names the variable. Development and Staging use `1.0` while traffic is low. The
rate is revisited with retention and cost in
[#215](https://github.com/TailTag-Game/tailtag/issues/215).

The sampler ignores a client's `sentry-trace` sampling flag, so clients cannot
turn tracing on or off. The SDK does continue an incoming trace, so a client can
still choose the `trace_id` of its own requests until
[#260](https://github.com/TailTag-Game/tailtag/issues/260). Use `request_id`,
which the API always generates, as the authoritative request key.

## Server errors

An unhandled exception returns a 500 to the client and creates one Sentry error
event. The event carries the exception class, the stack trace, the transaction
name, and the `request_id` tag. The same request's completion log line has
`http_response_status_code` 500, and Django's error line has `error_type`.

Expected rejections, such as 401, 403, 404, and validation errors, do not create
error events. A rising 5xx count with no matching error events means the API is
returning 5xx deliberately, most often a 503 from a failing readiness check.
Worker timeouts do not appear in the 5xx count at all; see Runtime failures.

## Runtime failures

Gunicorn's master process writes these lines, from logger `gunicorn.error`, as
JSON with the build identity fields. Search Railway service logs with
`@logger:gunicorn.error`.

| Message | Level | Meaning |
| --- | --- | --- |
| `Booting worker with pid: …` | `info` | A worker started. Repeated boots outside a deploy mean workers are dying. |
| `WORKER TIMEOUT (pid:…)` | `error` | A request held a worker past Gunicorn's timeout. The worker is killed and the client gets an error from Railway's edge. |
| `Worker (pid:…) was sent SIGKILL! Perhaps out of memory?` | `error` | A worker was killed outright, usually by the kernel's out-of-memory killer. |
| `Worker (pid:…) was sent SIGTERM!` | `info` | Normal shutdown during a deploy or restart. |

These failures happen outside Django, so they have no Sentry event and no
request metric. The request that was running never writes its completion line.

If the whole container runs out of memory or restarts, no log line explains it.
Check Railway's deployment events and the service's memory graph.

## Correlating with health

- `/health/ready` is counted in the request metric under `http.route`
  `health/ready`, with status class `2xx` when ready and `5xx` when not. A
  readiness 5xx alongside rising server errors on other routes points at a
  shared dependency. Dependency detail is in
  [backend dependency health](backend-dependency-health.md#correlating-with-readiness).
- The Sentry uptime monitor of `/health/ready` is set up in
  [#216](https://github.com/TailTag-Game/tailtag/issues/216).
- The health responses themselves are defined by
  [#203](https://github.com/TailTag-Game/tailtag/issues/203) and are unchanged.

## Build identity

Error events, transactions, and log lines carry `environment` and `release`
(the Git commit SHA). Log lines also carry `deployment_id`. To check whether a
deploy caused a change, compare error events and transactions by release.
Metrics carry `sentry.release` but no deployment ID.

## Development evidence

Recorded on 2026-09-30 against Development deployment `2ffd2190` of `main` at
`8593b60` (the #212 merge), with `SENTRY_TRACES_SAMPLE_RATE=1.0`. Traffic was
read-only: 5 each of `/health/live` and `/health/ready`, 25 unauthenticated
`/api/conventions/<id>/` (401), 10 `/api/schema/`, one `HEAD /api/schema/`,
3 requests to an unknown path carrying a unique marker, and one authenticated
`/api/me/` from `make api-auth-smoke`. Sentry was read through its API and the
monitor builder; Railway logs through the CLI.

- **D-4 passed.** Transactions are named by route, for example
  `/api/conventions/{pk}/` (25; p50 1.6 ms, p95 2.6 ms, p99 2.8 ms) and
  `/api/schema/` (p50 21.8 ms, p95 64.8 ms). A monitor built from the Explore
  query kept `p95(span.duration)` and accepted a static threshold. It was not
  saved; monitors belong to #216, which can alert on p95 latency directly.
- **D-5 passed.** `tailtag.http.server.requests` groups by `http.route`,
  `http.request.method`, and `http.response.status_class`, for example
  `api/conventions/<int:pk>/` `4xx` 25 and `<unmatched>` `4xx` 3. A monitor
  built from the metric kept a `5xx` filter and accepted a static count
  threshold. It was not saved.
- **D-6 passed.** The 3 unknown-path requests appear as `<unmatched>` in
  transactions and the metric. Their transactions carry no URL, and a Sentry
  search for the marker returns nothing. The path appears only in Django's
  `Not Found` WARNING lines in Railway, as the privacy policy allows.
- **D-7 passed.** `@logger:gunicorn.error` returns the deploy's Gunicorn lines
  with `environment`, `release`, and `deployment_id`.
  `@http_route:"api/conventions/<int:pk>/"` returns exactly the 25 completion
  lines, and so does the unquoted form, so quoting route values is optional.
- **D-8 passed.** No transactions exist for `/health/live`, `/health/ready`, or
  the `HEAD` request, and all of them are counted by the request metric.
- **D-9 passed.** The `/api/me/` transaction's only query is
  `… WHERE "accounts_user"."clerk_user_id" = %s`: the Clerk user ID, which is
  prohibited in telemetry, is not sent.
- **D-10 passed.** The 102 service log lines in the deploy window contain no
  plain-text Gunicorn access lines. No error event occurred for this build, so
  there were no breadcrumbs to inspect; the Gunicorn access test covers that
  path.

The merge first deployed without `SENTRY_TRACES_SAMPLE_RATE` (deployment
`a819ba17`). That deployment's requests appear in the request metric but not as
transactions, so metric counts for `api/schema/`, `api/docs/`, and
`health/identity` exceed their transaction counts by exactly those requests.
This confirms the metric does not depend on tracing.
