# Backend dependency health

This guide explains how to tell whether the API's dependencies are healthy:
PostgreSQL, media storage, Clerk, and the Render runtime. It covers what each
signal means, where to read it, how it relates to `/health/ready`, and what it
cannot tell you.

The contract is defined in the
[#214 spec](../specs/2026-09-30-dependency-health-telemetry.md). Request,
latency, and runtime failure signals are in
[backend service signals](backend-service-signals.md). Domain and
authentication outcomes are in
[backend domain outcomes](backend-domain-outcomes.md). Log fields and request
lookup are in [backend logging](backend-logging.md).

## Signals and where they live

| Question | Signal | Where |
| --- | --- | --- |
| Can the API reach PostgreSQL? | `tailtag.db.connection.attempts` by `tailtag.outcome` and `tailtag.reason` | Sentry metrics; failure lines in Render logs |
| Is PostgreSQL slow to accept connections? | p50, p95, and p99 of `tailtag.db.connection.duration` where `tailtag.outcome` is `succeeded` | Sentry metrics |
| Are queries slow? | Database spans in sampled transactions | Sentry traces and the Queries view |
| Is the database host under resource pressure? | CPU, memory, disk, and connections of the Render Postgres database | Render |
| Is media storage failing? | `tailtag.media.storage.operations` by `rpc.method`, `tailtag.outcome`, and `tailtag.reason` | Sentry metrics; failure lines in Render logs |
| Is Clerk degraded? | Authentication reasons and traffic to authenticated routes; see [Clerk](#clerk) | Sentry metrics |
| Is the API container under resource pressure? | CPU and memory graphs, deploy events, `gunicorn.error` lines | Render |

Every failed connection attempt or storage call also writes one WARNING log
line with `event` set to the signal, `tailtag_outcome`, and `tailtag_reason`.
Database lines add `duration_ms`; storage lines add `rpc_method`. Successes
write no line. Search Render logs for the text
`tailtag.db.connection.attempts` or
`tailtag.media.storage.operations`, then follow the line's
`request_id` as described in
[backend logging](backend-logging.md#following-one-request).

These signals never carry a host, port, database or role name, connection
string, bucket, object key, URL, access key, exception message, or provider
response. When a failure makes a request fail, the exception also reaches
Sentry issues through the normal error path, scrubbed by the
[telemetry privacy policy](../architecture/backend/telemetry-privacy.md).
Readiness checks and best-effort image cleanup handle their failures, so those
appear only in these signals.

## PostgreSQL

In Development and Staging, each Gunicorn worker keeps its PostgreSQL
connection between requests (`CONN_MAX_AGE` is 60 seconds). Django checks the
age only when a request starts or ends. It does not close a connection on a
timer, so an idle worker keeps its connection until its next request or until
the process stops. Before it reuses the connection in a new request, Django
checks that the connection still works (`CONN_HEALTH_CHECKS`). If the check
fails, Django opens a new connection. Local `runserver` still opens a new
connection for each request.

Each connection has `tcp_user_timeout` set to 10 seconds. If PostgreSQL stops
acknowledging sent data, for example after a silent network drop, the query
fails after 10 seconds. This is well below Gunicorn's 30-second worker
timeout, so the request fails and is recorded instead of the worker being
killed.

Each new connection attempt adds a count of 1 to
`tailtag.db.connection.attempts` and one value, in milliseconds, to
`tailtag.db.connection.duration`. These signals count new connections, not
requests. A busy worker opens about one connection each minute, so the count
follows workers, restarts, and dropped connections. The duration covers only
new connections. Reused connections add nothing to either signal. A connection attempt waits at most 5
seconds for each address the database host name resolves to. The DNS lookup
itself is not included, so a host with both an IPv4 and an IPv6 address can
take about 10 seconds to fail.

| Outcome | Reason | Meaning | What to check |
| --- | --- | --- | --- |
| `succeeded` | | A connection was opened. | Nothing, unless its duration is rising. |
| `failed` | `timeout` | PostgreSQL did not accept the connection within 5 seconds at any of its addresses. | Render Postgres CPU, memory, and disk; whether the service is restarting. |
| `failed` | `too_many_connections` | PostgreSQL refused because every connection slot is in use. | Other clients holding connections; see [connection capacity](#connection-capacity). |
| `failed` | `unreachable` | The host could not be resolved or reached, or refused the connection. | Whether the Postgres service is running, and the private network. |
| `failed` | `rejected` | PostgreSQL answered but refused the login: password, role, database, or access rule. | `DATABASE_URL` and the Postgres service's credentials. Usually a configuration change, not load. |
| `failed` | `other` | Any other connection failure. | The matching Sentry issue and the failure line's `request_id`. |

Reading the signals together:

- **Healthy:** attempts are `succeeded`, and connection duration is steady and
  small.
- **Degraded:** connection duration p95 is rising, or occasional `timeout` or
  `too_many_connections` failures appear, while most attempts succeed.
- **Unavailable:** most or all attempts fail, `/health/ready` returns 503, and
  requests that use the database return 5xx.

Connection reasons are classified from PostgreSQL's English error text. If the
wording changes in a future PostgreSQL version or locale, failures fall back to
`other`; they are never lost.

Only failures while opening a connection are classified. An error after the
connection is open, such as a query failure or a dropped connection, appears
as a Sentry issue and a 5xx, not in these signals.

### Query latency

There is no per-query metric. Query timing comes from the database spans in
sampled Sentry transactions: open a slow transaction to see its SQL spans, or
use Sentry's Queries view for aggregate timing. Spans keep the query text with
placeholders, never parameter values. Because transactions are sampled,
aggregate query timing is an estimate.

### Connection capacity

Each Gunicorn sync worker holds at most one connection. Since #448, a worker
keeps that connection between requests, also while it is idle. Expect about
one open connection for each worker at all times, not only under load. The API's peak
is therefore about `2 × workers` during a deploy, when the old and the new
instance both run. Add one pre-deploy migration and each open relay or
operator `render ssh` session.

| Setting | Development and Staging on Render (2026-11-03) |
| --- | --- |
| API instances | 1 |
| Gunicorn workers | 3 sync workers, set in `services/api/gunicorn.conf.py` |
| Gunicorn worker timeout | 30 seconds (default) |
| `CONN_MAX_AGE` | 60 seconds, with `CONN_HEALTH_CHECKS` on |
| PostgreSQL `max_connections` | 100, the Render limit for plans under 8 GB of memory |
| Expected API peak | about 10: 6 during a deploy, 1 migration, and a few ssh sessions |

Render sets `WEB_CONCURRENCY=1` on the `0.5c-512mb` plan. The `workers`
value in `gunicorn.conf.py` overrides it. The API cannot exhaust PostgreSQL's
connections at this size, so `too_many_connections` means something else
holds them. The API has no connection pool, so there is no pool to exhaust
and no pool-exhaustion signal.

To count connections, run `SELECT count(*) FROM pg_stat_activity` on the
database.

After a `normal-profile` run on 2026-11-04, Staging showed 4 connections,
including the counting session. That is one for each worker. See the
[#448 Staging proof](../specs/2026-11-04-connection-reuse-workers-staging-proof.md).

Revisit this section if the API adds a connection pool, PgBouncer, async
workers, or threads, or raises workers or instances close to
`max_connections`. Pool wait and exhaustion then become real signals and need
their own telemetry.

## Media storage

Every storage call that reaches the object store adds a count of 1 to
`tailtag.media.storage.operations`. A call is counted once, even when the
client retries it internally. Creating a signed read URL makes no network call
and is not counted.

| `rpc.method` | Used by |
| --- | --- |
| `PutObject` | Storing an uploaded image. |
| `GetObject` | Opening a stored image. |
| `HeadObject` | Checking whether an image exists, or reading its size. |
| `DeleteObject` | Removing a replaced or cleared image. |

| Outcome | Reason | Meaning |
| --- | --- | --- |
| `succeeded` | | The call completed. An existence check that finds no object is a success. |
| `failed` | `unavailable` | The storage endpoint could not be reached or did not answer in time. |
| `failed` | `access_denied` | Storage refused the credentials or signature. Usually a configuration or key problem. |
| `failed` | `not_found` | The object does not exist. |
| `failed` | `throttled` | Storage asked the API to slow down (HTTP 429 or 503). |
| `failed` | `server_error` | Storage returned another 5xx. |
| `failed` | `other` | Any other failure. |

A failed `DeleteObject` during image replacement or removal does not fail the
request, because the database change is already committed. It still counts
here, so a rise in `DeleteObject` failures means orphaned objects are
accumulating even though users see no error.

## Clerk

The API verifies Clerk session tokens locally with the configured public key
(`CLERK_JWT_KEY`) and makes no network call to Clerk. A Clerk outage therefore
cannot appear as a backend dependency failure. Read Clerk health from the
existing signals instead:

- **Clerk sign-in is down for players:** requests to authenticated routes
  fall in `tailtag.http.server.requests` (by `http.route`), with no matching
  rise in server errors or authentication rejections. The failure happens in
  the mobile app, before a request reaches the API. Check Clerk's status page.
- **The API's key does not match the Clerk instance:** almost every
  `tailtag.authentication.verification` rejection has `tailtag.reason`
  `token_invalid`, and requests to authenticated routes return 4xx. This
  follows a Clerk key rotation or a wrong `CLERK_JWT_KEY`.
- **The API's key is missing or unusable:** rejections have `tailtag.reason`
  `verifier_misconfigured`.

These reasons are described in
[backend domain outcomes](backend-domain-outcomes.md#authentication).

**Revisit this section** if the API switches to verifying tokens with the
Clerk secret key, which fetches signing keys over the network, or starts
calling the Clerk API. Clerk becomes a runtime dependency then and needs its
own failure signal.

## Runtime resources

Render provides the runtime signals. The API does not record them itself.

| Question | Where |
| --- | --- |
| Is the API container short of CPU or memory? | The API service's CPU and memory graphs |
| Did a worker hang or get killed? | `WORKER TIMEOUT` or `SIGKILL` lines from `gunicorn.error`; see [runtime failures](backend-service-signals.md#runtime-failures) |
| Did the container restart or redeploy? | The service's Render deploy history and events |
| Is the database host short of resources? | The Postgres service's CPU, memory, and disk graphs |

To tie a resource change to a build, match its time against deployment events,
then compare `release` on Sentry events and log lines before and after.
Render graphs carry no build identity of their own, and Render sets no
`deployment_id`.

A `WORKER TIMEOUT` is no longer the expected result of an unreachable database.
A connection attempt fails within 5 seconds per resolved address, well inside
the 30-second worker timeout. A `WORKER TIMEOUT` therefore points at slow
queries or a connection that stalled after it opened, not at a failure to
connect.

## Correlating with readiness

`/health/ready` returns 503 when its configuration check fails or when it
cannot open or reuse a PostgreSQL connection and run `SELECT 1`. Its responses are
defined by [#203](https://github.com/TailTag-Game/tailtag/issues/203) and do
not change; they never say which dependency failed or why.

A readiness check reuses the worker's connection when it can. It adds a
connection attempt only when it opens a new connection or replaces one that
failed the health check. So connection attempts are a partial signal for
readiness. A readiness failure caused by PostgreSQL appears as a failed
`tailtag.db.connection.attempts` with a reason only if the check tried to open
a connection. That reason is the detail readiness deliberately leaves out.

- Readiness 503 with failed connection attempts: PostgreSQL. The reason says
  which kind.
- Readiness 503 with no failed connection attempts at the same time: either
  the configuration check failed, or a connection opened or was reused and
  `SELECT 1` then failed. Readiness does not log which.
  If other routes are also returning 5xx with database errors in Sentry,
  suspect PostgreSQL after the connection opened; otherwise compare the
  environment's variables with the #203 configuration rules.
- Readiness healthy while storage operations fail: storage is not part of
  readiness. Media uploads and image reads fail while the rest of the API
  works.

Readiness checks that open a new connection are included in the
connection-attempt counts. Readiness checks that reuse a connection add
nothing.

## Limits

- Alerting uses failure counts (M4 in the
  [field-beta operations guide](field-beta-operations.md#monitors)). The p95
  connection time is charted on the dashboard but not alerted on.
- Connection reasons depend on PostgreSQL's English error text.
- Failures after a connection opens are not classified here.
- Pool exhaustion and Clerk availability are not observable in the current
  design; see the revisit notes above.

## Development evidence

This evidence was recorded on Railway, before the Render move. Its log search
syntax is Railway syntax and does not work on Render.

Recorded on 2026-10-01 against Development deployment `344ca1f9` of `main` at
`68f8aca` (the #214 merge). Railway service logs were read through the CLI,
linked to project `TailTag`, environment `development`, service `api`. Sentry
metrics and errors were queried through the Sentry API.

Traffic:

- `/health/identity` and `/health/ready` requests, plus the API's normal
  Development traffic after the deploy.
- One run of a temporary probe in a one-off shell on the deployed `api`
  container (`railway ssh`, then `python manage.py shell`), so it ran the
  merged code with the deployment's own build identity and Sentry
  configuration. It printed only stage names and exception class names. It
  stored one synthetic 1×1 PNG under a server-generated key through the
  configured storage, and deleted it in a `finally` block. It then opened a
  separate database connection, using the configured settings with a
  synthetic, nonexistent database name, without touching the default
  connection. The probe was deleted from the container afterwards. No
  service was stopped or reconfigured.

Results:

- **E-1 passed.** `/health/identity` reported `source_sha` `68f8aca…`,
  `environment` `development`, and deployment `344ca1f9`. `/health/ready`
  returned 200, so the readiness configuration check accepts the TailTag
  database backend.
- **E-2 passed.** Sentry recorded five `tailtag.db.connection.attempts` /
  `succeeded`, each with a `tailtag.db.connection.duration` value between 12
  and 28 ms, all with release `68f8aca`.
- **E-3 passed.** Every probe storage stage passed, including byte-equal
  read-back and confirmed absence after delete. Sentry recorded exactly
  `PutObject` 1, `HeadObject` 2, `GetObject` 1, and `DeleteObject` 1, all
  `succeeded`. One `HeadObject` was the absence check after delete, which is a
  success by design.
- **E-4 passed.** The separate connection failed with `OperationalError` and
  Sentry recorded one `tailtag.db.connection.attempts` / `failed` / `rejected`,
  with a `failed` duration of 23 ms. The WARNING line carried only `event`,
  `tailtag_outcome`, `tailtag_reason`, `duration_ms`, and the correlation and
  build fields.
- **E-5 passed.**
  - No `Metric attribute rejected` warning and no error-level line appeared in
    the deployment's Railway logs (19 lines).
  - Neither those logs nor the probe output contained the database host or
    password, the bucket, the storage endpoint host, the access key, the
    synthetic database name, or an object key.
  - No Development error events occurred in Sentry in the window.

The E-4 WARNING line went to the one-off shell's stdout, not to Railway
service logs, because Railway collects only the deployed process's output. A
connection failure on the request path writes the same line to Railway service
logs. Producing one in Development would require breaking the database
connection for live traffic, which this evidence does not do.
