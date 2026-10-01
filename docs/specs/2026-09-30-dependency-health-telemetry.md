# Dependency health telemetry

Issue: [#214](https://github.com/TailTag-Game/tailtag/issues/214) (OB-6).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #210 ([structured logging and request correlation](2026-09-29-structured-logging-request-correlation.md)), #211 ([telemetry privacy policy](../architecture/backend/telemetry-privacy.md)), #212 ([HTTP and backend runtime telemetry](2026-09-29-http-runtime-telemetry.md)), #213 ([domain outcome telemetry](2026-09-30-domain-outcome-telemetry.md)).
Readiness semantics: #203.
Consumers: #216 (dashboard and alerts), #217 (final validation), #199 (simulations).

## Status and phase ledger

Execution: STANDARD COMPACT. Assurance: SECURITY (telemetry privacy
containment), RELIABILITY (database connect failure mode).
Completed: scope review, uncertainty review and research, maintainer approval
of the design decisions below (2026-09-30), read-only Railway Development
evidence (2026-09-30).
Completed additionally: independent acceptance tests with parent approval,
red only for the missing `observability.dependencies` seam; clean baseline
(3,434 tests) on a disposable PostgreSQL container.
Completed additionally: independent implementation (the shared
`recorded_outcomes` test helper now ignores dependency signals); documentation;
full gate (3,479 tests, format, lint, strict Pyright, Semgrep 0 findings
including the new modules, Django, migrations, schema and Gunicorn checks,
`./scripts/doctor.sh`, `git diff --check`).
Completed additionally: independent review. SPEC, QUALITY, TEST, SCOPE,
SECURITY, and RELIABILITY passed with LOW findings only. Remediated by the
parent:

- L1 (LOW): the Clerk guidance names `token_invalid` and
  `verifier_misconfigured` as reasons, not outcomes, and describes traffic by
  authenticated route.
- L2 (LOW): the connect timeout is documented as 5 seconds per resolved
  address, excluding the DNS lookup.
- L3 (LOW): the storage absence check that decides `exists()` stays in
  `media/storage.py`, so a telemetry change cannot change storage behavior.

Remediation verification: the dependency, media storage, media service,
fursuit media API, and domain outcome suites (181 tests), format, lint, strict
Pyright, Semgrep on `observability/` and `media/`, `./scripts/doctor.sh`, and
`git diff --check` passed.
Pending: commit and pull request; Development evidence after deployment.

## Problem

Operators cannot tell PostgreSQL unavailable from PostgreSQL slow or healthy,
and storage failures are invisible unless they surface as a 5xx.

The database connection has no connect timeout, so psycopg 3 falls back to its
130-second default. Gunicorn's sync workers use the 30-second default worker
timeout. When PostgreSQL is unreachable or stalled, Gunicorn kills the worker
before psycopg raises, so there is no exception, no Sentry event, and no metric,
and `/health/ready` never returns its 503. The most important degraded state is
the one that produces no telemetry.

## Evidence

Railway Development, read-only, 2026-09-30:

| Fact | Value |
| --- | --- |
| API replicas | 1 |
| Gunicorn workers and timeout | Defaults: 1 sync worker, 30 seconds (no `WEB_CONCURRENCY` or `GUNICORN_CMD_ARGS`) |
| PostgreSQL | Stock `postgres:18.6` image |
| `max_connections` / `superuser_reserved_connections` | 100 / 3 |
| `lc_messages` | `en_US.utf8` |

Railway exposes CPU, memory, disk, and network for the database service, not
connection counts. The backend verifies Clerk session tokens with the configured
`CLERK_JWT_KEY` and makes no Clerk network call in production code.

## Decisions

1. **Connect timeout.** The database configuration sets `connect_timeout` to 5
   seconds in every environment that uses `database_from_url`. Status codes and
   response bodies do not change; an unreachable database fails within 5
   seconds per resolved address (DNS lookup not included) instead of the
   worker being killed at 30.
2. **Connection seam.** A thin PostgreSQL backend subclass wraps
   `get_new_connection` to time and classify each connection attempt. The
   exception still propagates unchanged. `CONN_MAX_AGE` stays 0 and no pool is
   added, so every request, including `/health/ready`, makes one attempt.
3. **Query latency.** No per-query metric. Query latency comes from the sampled
   Sentry database spans. SQL span policy is unchanged
   ([telemetry privacy §6](../architecture/backend/telemetry-privacy.md#6-sql-spans-and-query-strings)).
4. **Clerk.** No new instrumentation. Verification is networkless, so a Clerk
   outage cannot appear as a backend failure. The operations guide explains how
   to read the existing #213 authentication outcomes, and names the change that
   reopens this decision.
5. **Storage.** Every `S3MediaStorage` call that uses one of the four network
   operations (`put_object`, `get_object`, `head_object`, `delete_object`) is
   counted with a bounded outcome and reason, including `size()` as
   `HeadObject`. Read-URL signing makes no network call and is not
   counted.
6. **Runtime resources.** Documentation only: Railway resource graphs, Gunicorn
   worker-timeout log lines, and build identity are correlated by time and
   `deployment_id`. Connection capacity arithmetic is documented with the change
   that reopens pool-exhaustion telemetry.
7. **Separate taxonomy.** Dependency signals use their own enumerations, not
   the domain `Outcome` and `Reason`. They reuse the `tailtag.outcome` and
   `tailtag.reason` attribute keys so dashboards filter them the same way.
   Values are add-only.

## Taxonomy

Signals:

| Signal | Kind | Attributes |
| --- | --- | --- |
| `tailtag.db.connection.attempts` | count of 1 per attempt | `tailtag.outcome`; `tailtag.reason` when failed |
| `tailtag.db.connection.duration` | distribution, milliseconds | `tailtag.outcome` |
| `tailtag.media.storage.operations` | count of 1 per call | `rpc.method`; `tailtag.outcome`; `tailtag.reason` when failed |

Outcomes: `succeeded`, `failed`.

Database connection reasons:

| Reason | Meaning |
| --- | --- |
| `timeout` | The connect timeout expired (`psycopg.errors.ConnectionTimeout`). |
| `too_many_connections` | The server refused for capacity: `too many clients` or `remaining connection slots are reserved`. |
| `unreachable` | The host could not be resolved or reached, or refused the TCP connection. |
| `rejected` | The server was reached but refused the login: authentication failure, unknown role or database, or no `pg_hba.conf` entry. |
| `other` | Any other connect failure. |

psycopg does not expose a SQLSTATE for connect failures, so these reasons are
classified from the server and libpq message inside the process. Only the
reason leaves the process. A wording change degrades to `other`.

Storage reasons:

| Reason | Meaning |
| --- | --- |
| `unavailable` | Endpoint connection failure or connect/read timeout. |
| `access_denied` | HTTP 401 or 403, or `AccessDenied`, `InvalidAccessKeyId`, `SignatureDoesNotMatch`. |
| `not_found` | HTTP 404 or `NoSuchKey`, except where `exists()` treats absence as its answer. |
| `throttled` | HTTP 429 or 503, or `SlowDown`, `Throttling`, `RequestLimitExceeded`. |
| `server_error` | Any other HTTP 5xx. |
| `other` | Any other failure. |

`rpc.method` (OpenTelemetry name) is one of `PutObject`, `GetObject`,
`HeadObject`, `DeleteObject`.

## Scope

### In scope

- Connect timeout and the connection-attempt signals.
- Storage operation signals.
- The dependency taxonomy, its recorder, and the privacy and log allow-list
  extensions.
- A maintainer operations guide covering database, storage, Clerk, runtime
  resources, capacity, and readiness interpretation.
- Updates to the observability architecture and telemetry privacy documents.

### Out of scope

- Connection pooling, `CONN_MAX_AGE`, PgBouncer, or Gunicorn worker changes.
- Per-query metrics, query analytics, or any change to SQL span handling.
- Query-time database errors after a connection exists (they stay Sentry
  exceptions).
- Clerk network calls or new Clerk reasons.
- Dashboards and alerts (#216), Development evidence recording (a follow-up
  after deployment), and any public API or health response change.

## Acceptance Contract

**AC-1 Connect timeout.** `database_from_url` returns a configuration whose
`OPTIONS` sets `connect_timeout` to 5 and whose `ENGINE` is the TailTag
PostgreSQL backend. A connection attempt to an endpoint that never answers
fails with a database error in bounded time instead of waiting for psycopg's
default.

**AC-2 Connection attempts.** Every new database connection attempt through
the default backend records exactly one `tailtag.db.connection.attempts` count
and one `tailtag.db.connection.duration` distribution. A success records
`succeeded` with no reason. A failure records `failed` with the reason from the
taxonomy and re-raises the original error, so Django's behavior and error type
are unchanged.

**AC-3 Classification.** Each database reason in the taxonomy is produced by a
representative failure, and an unrecognized failure produces `other`.

**AC-4 Storage operations.** Each of `PutObject`, `GetObject`, `HeadObject`,
and `DeleteObject` records exactly one `tailtag.media.storage.operations` count
per storage call, whatever the client's internal retries. Success records
`succeeded`. Failure records `failed` with the reason from the taxonomy and
re-raises the original error. `exists()` returning `False` for a missing object
records `succeeded`. `url()` records nothing.

**AC-5 Failure log lines.** Each failed attempt or operation writes one WARNING
log line with `event` set to the signal, `tailtag_outcome`, `tailtag_reason`,
and for storage `rpc_method`, plus `duration_ms` for the database. Successes
write no log line.

**AC-6 Bounded values.** The privacy policy's sets for `tailtag.outcome`,
`tailtag.reason`, and `rpc.method` include the dependency enumeration values,
derived from the enumerations, so every dependency metric keeps its attributes
through `scrub_metric` without a rejection warning. `rpc_method` is an
allow-listed log key. Existing domain and request metric behavior is unchanged.

**AC-7 Containment.** No dependency metric or log line carries a host, port,
database or role name, connection string, password, bucket, object key, URL,
signed URL, access key, exception message, or provider response. Tests prove
this with synthetic sentinel values in the failing error.

**AC-8 Readiness.** `/health/ready` keeps its approved responses. When
PostgreSQL is unavailable it still returns 503 with the same body, and the
failed connection attempt is recorded with its reason.

**AC-9 Documentation.** A maintainer guide explains each signal, how to read
it with `/health/ready`, Railway graphs, Gunicorn log lines, and build
identity, the capacity arithmetic, the Clerk interpretation, and the changes
that reopen the pool-exhaustion and Clerk decisions. The observability
architecture and telemetry privacy documents reflect the new signals and
allow-list entries.

**AC-10 No excluded behavior.** No pool, per-query metric, raw SQL or
parameter telemetry, service termination, dependency-dump endpoint, or public
API change is introduced.

## Design

- `observability/dependencies.py`
  - `DependencySignal`, `DependencyOutcome`, `DatabaseConnectionReason`, and
    `StorageReason` `StrEnum`s holding the taxonomy, and the `rpc.method`
    values.
  - Pure classifiers from a psycopg or botocore exception to a reason.
  - One recorder per signal family. They log through a module logger and call
    `sentry_sdk.metrics`. The module imports nothing from feature modules.
- `observability/postgresql/base.py`: `DatabaseWrapper` subclasses Django's
  PostgreSQL wrapper and overrides only `get_new_connection` to time,
  classify, record, and re-raise.
- `config/settings/base.py`: `database_from_url` sets the `ENGINE` and
  `OPTIONS`.
- `health/configuration.py` and `config/replacement_migrate.py`: their
  PostgreSQL engine guards accept the TailTag backend in place of Django's
  stock engine name, so readiness and the replacement migration guard keep
  their meaning.
- `media/storage.py`: each network call goes through one wrapper that records
  the operation.
- `observability/privacy.py` and `observability/logging.py`: allow-list
  extensions derived from the enumerations.

## Test surface

Seams tests may use, which production code must provide:

- `observability.dependencies` enumerations with the values above.
- `S3MediaStorage(client_factory=...)`, the existing provider seam.
- The psycopg connect call inside the backend, substituted only to raise a
  synthetic provider error. A real refused or wrong-login connection is
  preferred where it is deterministic.

Rules:

- Observe signals through captured stdout JSON lines and the capturing Sentry
  transport in `tests/observability_test_support.py`.
- Parameterize reason tables; do not repeat cases.
- Negative tests use synthetic sentinel values, never real credentials.
- Extend existing test modules and helpers rather than adding parallel ones.
- Never terminate a real database or service.

## Risks

- **Message-based classification.** Depends on English server messages; the
  Development server uses `en_US`. Wording drift degrades to `other`.
- **Timeout tuning.** 5 seconds is far above a healthy private-network connect.
  A database that takes longer than 5 seconds to accept a connection now fails
  the request instead of succeeding slowly, which is the intended signal.
- **Distribution monitors.** Sentry does not document monitors on distribution
  percentiles. #216 must confirm in the UI; the failure count is enough to
  alert on unavailability.

## Known limitations

- Pool exhaustion is not observable because there is no pool; capacity is
  `workers × replicas` connections against `max_connections`.
- A Clerk outage appears as falling authenticated traffic and client sign-in
  failures, not as a backend failure.
- Connection-attempt counts include readiness probes.
- Failures after a connection is established, including in Django's
  connection initialization, are not classified.
