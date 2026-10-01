# Backend dependency health

This guide explains how to tell whether the API's dependencies are healthy:
PostgreSQL, media storage, Clerk, and the Railway runtime. It covers what each
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
| Can the API reach PostgreSQL? | `tailtag.db.connection.attempts` by `tailtag.outcome` and `tailtag.reason` | Sentry metrics; failure lines in Railway logs |
| Is PostgreSQL slow to accept connections? | p50, p95, and p99 of `tailtag.db.connection.duration` where `tailtag.outcome` is `succeeded` | Sentry metrics |
| Are queries slow? | Database spans in sampled transactions | Sentry traces and the Queries view |
| Is the database host under resource pressure? | CPU, memory, disk, and network of the Postgres service | Railway |
| Is media storage failing? | `tailtag.media.storage.operations` by `rpc.method`, `tailtag.outcome`, and `tailtag.reason` | Sentry metrics; failure lines in Railway logs |
| Is Clerk degraded? | Authentication reasons and traffic to authenticated routes; see [Clerk](#clerk) | Sentry metrics |
| Is the API container under resource pressure? | CPU and memory graphs, deployment events, `gunicorn.error` lines | Railway |

Every failed connection attempt or storage call also writes one WARNING log
line with `event` set to the signal, `tailtag_outcome`, and `tailtag_reason`.
Database lines add `duration_ms`; storage lines add `rpc_method`. Successes
write no line. Search Railway service logs with
`@event:tailtag.db.connection.attempts` or
`@event:tailtag.media.storage.operations`, then follow the line's
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

The API opens a new PostgreSQL connection for each request that uses the
database, including every `/health/ready` check, and closes it at the end of
the request. Each attempt adds a count of 1 to
`tailtag.db.connection.attempts` and one value, in milliseconds, to
`tailtag.db.connection.duration`. A connection attempt waits at most 5
seconds for each address the database host name resolves to. The DNS lookup
itself is not included, so a host with both an IPv4 and an IPv6 address can
take about 10 seconds to fail.

| Outcome | Reason | Meaning | What to check |
| --- | --- | --- | --- |
| `succeeded` | | A connection was opened. | Nothing, unless its duration is rising. |
| `failed` | `timeout` | PostgreSQL did not accept the connection within 5 seconds at any of its addresses. | Postgres service CPU, memory, and disk in Railway; whether the service is restarting. |
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

Each Gunicorn sync worker holds at most one connection, and only while it is
handling a request. The API's peak is therefore
`workers × replicas` connections, plus any one-off processes such as
migrations.

| Setting | Development (2026-09-30) |
| --- | --- |
| API replicas | 1 |
| Gunicorn workers | 1 (default; no `WEB_CONCURRENCY` or `GUNICORN_CMD_ARGS`) |
| Gunicorn worker timeout | 30 seconds (default) |
| PostgreSQL `max_connections` | 100, with 3 reserved for superusers |

The API cannot exhaust PostgreSQL's connections at this size, so
`too_many_connections` means something else is holding them. The API has no
connection pool, so there is no pool to exhaust and no pool-exhaustion signal.

Railway does not report PostgreSQL connection counts. To see them, run
`SELECT count(*) FROM pg_stat_activity` on the Postgres service.

**Revisit this section** if the API adds persistent connections
(`CONN_MAX_AGE`), a connection pool, PgBouncer, async workers, or raises
workers or replicas close to `max_connections`. Pool wait and exhaustion become
real signals then and need their own telemetry.

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

Railway provides the runtime signals; the API does not record them itself.

| Question | Where |
| --- | --- |
| Is the API container short of CPU or memory? | The API service's CPU and memory graphs |
| Did a worker hang or get killed? | `WORKER TIMEOUT` or `SIGKILL` lines from `gunicorn.error`; see [runtime failures](backend-service-signals.md#runtime-failures) |
| Did the container restart or redeploy? | Railway deployment events |
| Is the database host short of resources? | The Postgres service's CPU, memory, and disk graphs |

To tie a resource change to a build, match its time against deployment events,
then compare `release` on Sentry events and `deployment_id` on log lines
before and after. Railway graphs carry no build identity of their own.

A `WORKER TIMEOUT` is no longer the expected result of an unreachable database.
A connection attempt fails within 5 seconds per resolved address, well inside
the 30-second worker timeout. A `WORKER TIMEOUT` therefore points at slow
queries or a connection that stalled after it opened, not at a failure to
connect.

## Correlating with readiness

`/health/ready` returns 503 when its configuration check fails or when it
cannot open a PostgreSQL connection and run `SELECT 1`. Its responses are
defined by [#203](https://github.com/TailTag-Game/tailtag/issues/203) and do
not change; they never say which dependency failed or why.

Each readiness check makes one connection attempt, so a readiness failure
caused by PostgreSQL also appears as a failed `tailtag.db.connection.attempts`
with a reason. That reason is the detail readiness deliberately leaves out.

- Readiness 503 with failed connection attempts: PostgreSQL. The reason says
  which kind.
- Readiness 503 with no failed connection attempts at the same time: the
  configuration check failed. Readiness does not log which check; compare the
  environment's variables with the #203 configuration rules.
- Readiness healthy while storage operations fail: storage is not part of
  readiness. Media uploads and image reads fail while the rest of the API
  works.

Readiness checks are included in the connection-attempt counts. When traffic
is low, most attempts may be readiness checks.

## Limits

- Sentry monitors on distribution percentiles are not confirmed. Alert on
  failure counts first; #216 decides the rest.
- Connection reasons depend on PostgreSQL's English error text.
- Failures after a connection opens are not classified here.
- Pool exhaustion and Clerk availability are not observable in the current
  design; see the revisit notes above.
