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
example, does not say whether catches are failing. Domain outcomes come from
[#213](https://github.com/TailTag-Game/tailtag/issues/213), and dependency
health from [#214](https://github.com/TailTag-Game/tailtag/issues/214).

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
  shared dependency. Dependency detail is
  [#214](https://github.com/TailTag-Game/tailtag/issues/214).
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

To be recorded after merge to `main` and after `SENTRY_TRACES_SAMPLE_RATE=1.0`
is set in Development.

- **D-4** Transactions named by route; p50, p95, and p99 for one route in
  Explore. Whether a monitor accepts a p95 span-duration threshold. If not,
  percentiles stay on the dashboard, and alerts use counts and the 5xx count.
- **D-5** `tailtag.http.server.requests` grouped by `http.route` and
  `http.response.status_class`, and the monitor builder offers a count threshold
  filtered by status class. Nothing is saved.
- **D-6** A request to an unknown path appears as `<unmatched>` in transactions
  and the metric, and no transaction is named by its raw path or carries it as
  its request URL.
- **D-7** `@logger:gunicorn.error` returns Gunicorn boot lines as JSON, and an
  `@http_route` filter returns completion lines, which settles the quoting
  syntax for route values.
- **D-8** Requests to `/health/ready` produce no transactions, but appear in
  `tailtag.http.server.requests` under `http.route` `health/ready` with status
  class `2xx`.
- **D-9** A database-backed request produces a transaction whose SQL span shows
  parameter placeholders and no parameter values.
- **D-10** Railway service logs contain no plain-text Gunicorn access lines. If
  an error event occurs in Development before #212 closes, its breadcrumbs
  contain no `gunicorn.access` lines. There is no safe way to force an error
  there, so this second part is opportunistic; the Gunicorn access test proves
  it in-process.
