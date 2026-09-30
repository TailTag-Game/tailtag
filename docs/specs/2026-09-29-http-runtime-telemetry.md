# HTTP and backend runtime telemetry

Issue: [#212](https://github.com/TailTag-Game/tailtag/issues/212) (OB-4).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #210 ([structured logging and request correlation](2026-09-29-structured-logging-request-correlation.md)), #211 ([telemetry privacy policy](../architecture/backend/telemetry-privacy.md)), #203 (health contract).
Consumers: #216 (dashboard and alerts), #199 (simulations).

## Status and phase ledger

Execution: STANDARD EXPANDED. Assurance: SECURITY (telemetry privacy and
cardinality), TEST ADEQUACY.
Completed: scope review, uncertainty review, maintainer approval of all six
design recommendations (2026-09-29), SDK and Sentry documentation research.
Completed additionally: environment baseline (3,345 tests passed against a
disposable PostgreSQL container); independent acceptance tests with parent
approval, red for the missing seams and behavior.
Completed additionally: independent implementation; full gate (3,376 tests,
format, lint, strict Pyright, Semgrep 0 findings, Django, migration, schema, and
Gunicorn checks); local Gunicorn black-box boot under production settings, where
master, worker, and completion lines were single JSON lines with build identity.
Completed additionally: independent review. SCOPE passed; SPEC, QUALITY, and
SECURITY failed on H-1; TEST passed with gaps. Remediated by the parent:

- H-1 (HIGH): setting `logconfig_dict` turns on Gunicorn's access log. Access
  records (client IP, raw path, user agent) did not reach stdout but became
  Sentry breadcrumbs outside the request scope, so they could appear on other
  requests' error events. `gunicorn.access` is now capped at WARNING, and a
  test proves an access record reaches neither stdout nor Sentry.
- M-1 (MEDIUM): the middleware's `<unmatched>` rename ran on the isolation
  scope, which holds no span, so it never reached the transaction. The
  `before_send_transaction` rename already produced the result and is tested.
  The dead code was removed and Decision 2 now names the hook as the mechanism.
- L-1, L-2 (LOW): documentation corrected. Worker timeouts do not raise the 5xx
  count; unmatched transactions kept the client's raw path in `request.url`.
  The maintainer approved removing it in this change (2026-09-29): the same
  hook now drops `request.url` from `url`-sourced transactions, and the
  unmatched-name test checks the whole envelope.
- L-3 (LOW): accepted. A 400 takes the same path as the tested 401 and 404.

Completed additionally: remediation verification. The H-1 test failed before
the fix and passes after it. The full suite (3,377 tests), format, lint, strict
Pyright, Semgrep (0 findings), the Gunicorn check, `./scripts/doctor.sh`, and
`git diff --check` passed.
Completed additionally: maintainer decisions on the two review follow-ups
(2026-09-29). Client trace headers moved to
[#260](https://github.com/TailTag-Game/tailtag/issues/260). Unmatched
transactions now lose `request.url` in this change; the tightened
unmatched-name test failed before the fix and passes after it.
Completed additionally: focused independent re-review of the remediation.
SPEC, QUALITY, TEST, SCOPE, and SECURITY passed. Two LOW documentation findings
were fixed: error events from unmatched requests still keep the raw path (a
pre-existing behavior now listed in the privacy policy's known limitations),
and this ledger now names D-4 to D-10.
Completed additionally: PR review (#261). CodeRabbit noted that the SDK's
Django integration never traces `HEAD` or `OPTIONS`, contrary to AC-2 as
written. The maintainer kept the SDK default; AC-2 and Decision 5 now state it,
and the sampling test proves a `HEAD` request is counted but not traced.
Completed additionally: implementation merged as `8593b60` (PR #261).
Development evidence D-4 to D-10 passed on 2026-09-30 against deployment
`2ffd2190` with `SENTRY_TRACES_SAMPLE_RATE=1.0`, and is recorded in the
[backend service signals](../operations/backend-service-signals.md#development-evidence)
guide. Monitors accept both a p95 span-duration threshold and a `5xx` count
threshold on the request metric, so the percentile fallback is not needed.
Current: complete.

## Problem

The API emits structured logs and Sentry errors (#210) under an enforced privacy
policy (#211), but tracing is off and there is no request count, throughput,
latency, or 5xx signal in Sentry. The request log uses dotted keys that Railway
log search cannot filter. Gunicorn's own messages, including worker timeouts and
out-of-memory kills, are plain text on stderr.

## Decisions

Approved by the maintainer on 2026-09-29.

1. **Latency comes from transactions; counts come from one metric.** Sentry
   transactions supply p50/p95/p99 by route. Sentry weights sampled spans by
   the inverse sample rate, so percentiles stay unbiased under uniform
   sampling. One unsampled count metric, `tailtag.http.server.requests`,
   supplies exact throughput and 5xx counts. No duration distribution metric is
   added.
2. **Unmatched routes get a fixed name.** When no URL pattern matches, the SDK
   names the transaction after the raw path (`request.path_info`, source `url`;
   read in `sentry-sdk` 2.71.0). `before_send_transaction` replaces every
   `url`-sourced name with `<unmatched>` and removes that transaction's
   `request.url`, because the path is client-chosen free text. The approved
   design also renamed it in the middleware; review found that rename could
   not reach the transaction (see the phase ledger), so the hook is the single
   mechanism. SQL parameter capture stays off, which is the SDK default when
   neither `data_collection` nor the `record_sql_params` experiment is set.
3. **Gunicorn logs go through the JSON formatter.** A `gunicorn.conf.py`
   routes `gunicorn.error` to the same stdout handler, formatter, and context
   filter as Django. Gunicorn 26 already logs `WORKER TIMEOUT` (critical) and
   `Worker ... was sent SIGKILL! Perhaps out of memory?` (error) from the
   master. Nothing captures to Sentry from Gunicorn hooks. Whole-container
   out-of-memory kills and restarts are visible only in Railway.
4. **Log keys use underscores.** Stdout keys become `http_request_method`,
   `http_route`, `http_response_status_code`, and `error_type`. Sentry span and
   metric attributes keep the OpenTelemetry names. #210's Development evidence
   proved underscore keys filter in Railway; nesting is untested and not
   pursued.
5. **Health checks are not traced, but are counted.** A `traces_sampler`
   returns `0` for `/health/live` and `/health/ready` and the configured rate
   otherwise. The request metric still counts health requests, labelled by
   route. The rate comes from `SENTRY_TRACES_SAMPLE_RATE`; unset means tracing
   off. The maintainer sets `1.0` in Development and Staging after merge.
   `HEAD` and `OPTIONS` requests are not traced either: the SDK's Django
   integration skips them before the sampler runs, and the maintainer chose to
   keep that default (2026-09-29, from PR review). They are mostly probes,
   scanners, and preflights with little latency value.
6. **Evidence.** Deterministic tests with a capturing Sentry transport gate the
   merge. Development evidence is recorded after merge in a follow-up
   documentation change, and #212 stays open until it is. Staging evidence is
   recorded when Staging is next deployed and does not block the merge.

Parent-selected defaults, reversible:

7. A method outside the known HTTP method set is recorded as `_OTHER`, the
   OpenTelemetry convention, so the metric never loses its method dimension.
8. The sampler ignores any incoming parent sampling decision, so clients cannot
   force traces on.
9. An invalid `SENTRY_TRACES_SAMPLE_RATE` (not a number, or outside 0–1) stops
   production startup with a clear error, matching the other production
   settings. It never echoes the invalid value.

## Scope

### In scope

- `observability/`: tracing options and sampler, unmatched-route naming,
  transaction backstop, request metric, log key rename, Gunicorn logger config.
- `gunicorn.conf.py` in `services/api`.
- Settings wiring for `SENTRY_TRACES_SAMPLE_RATE`.
- Privacy policy values: `<unmatched>` route and `_OTHER` method.
- Tests for the Acceptance Contract; updates to existing tests for the rename.
- Maintainer documentation.

### Out of scope

- Domain outcome metrics (#213), dependency health (#214), dashboards, monitors,
  and alerts (#216), retention (#215).
- A latency distribution metric, Sentry profiling, or span streaming mode.
- Any change to API or health responses, status codes, or headers.
- Setting Railway variables, creating monitors, or any Sentry configuration
  (maintainer actions).
- Ignoring client-supplied `sentry-trace` and `baggage` headers. The SDK
  continues an incoming trace, so a client can choose the `trace_id` that
  appears in logs and Sentry. This predates #212, because the SDK continues
  propagation context even with tracing off. Tracked in
  [#260](https://github.com/TailTag-Game/tailtag/issues/260).

## Acceptance Contract

**AC-1 Tracing configuration.** With `SENTRY_TRACES_SAMPLE_RATE` unset or empty,
no transaction is sent. With a number from 0 to 1, tracing is enabled through
`traces_sampler`. Any other value raises `RuntimeError` at production startup
without echoing the value. Without `SENTRY_DSN`, the SDK stays uninitialized
whatever the rate.

**AC-2 Sampling.** Requests to `/health/live` and `/health/ready` are never
traced. `HEAD` and `OPTIONS` requests are never traced, which is the Sentry
Django integration's default. Other requests are traced at the configured rate,
whatever an incoming trace header says about sampling. The request metric
counts every request either way.

**AC-3 Transaction names.** A request to a matched route produces a transaction
named by its route template with source `route`, never the raw path. A request
that matches no route produces a transaction named `<unmatched>`, and its raw
path appears nowhere in the envelope, including `request.url`. No transaction
event leaves the process with source `url` or a name containing the raw request
path.

**AC-4 SQL spans.** With tracing on, a request that runs a real parameterized
database query produces a transaction whose SQL span keeps the parameterized
query text and whose envelope contains no parameter value.

**AC-5 Request metric.** Whenever Sentry is initialized, every request handled
by Django emits exactly one `tailtag.http.server.requests` count of 1. This
holds whether or not the request is traced, including health requests and when
tracing is off. Its attributes are:

- `http.route`: the Django route template (`request.resolver_match.route`), or
  `<unmatched>`;
- `http.request.method`: a known HTTP method, or `_OTHER`;
- `http.response.status_class`: `1xx` to `5xx`.

The privacy policy keeps all three without a rejection warning. The metric never
carries an ID, raw path, query string, `release`, or `deployment_id`, beyond the
SDK's own `sentry.release`.

**AC-6 Server errors versus client outcomes.** An unhandled view exception still
produces one Sentry error event, and its request metric has status class `5xx`.
A 4xx response, including an unmatched route (404), a rejected authentication
(401), and a validation failure (400), produces no Sentry error event.

**AC-7 Log keys.** No stdout log line contains a key with a dot. The completion
line and exception records use `http_request_method`, `http_route`,
`http_response_status_code`, and `error_type`, with the meanings the dotted keys
had. The completion line omits `http_route` when no route matched, as before.
Breadcrumb allow-listing follows the same keys.

**AC-8 Gunicorn logs.** Records from `gunicorn.error`, in the master and in
workers, are written to stdout as single JSON lines through the same formatter
and context filter as application logs. They include `logger: gunicorn.error`,
the build identity fields when available, and `level: error` for Gunicorn's
critical and error records. `make api-gunicorn-check` passes.

**AC-9 Build identity.** Transactions carry `environment` and `release` from
build identity only, as error events already do.

**AC-10 Health contract unchanged.** `/health/live`, `/health/ready`, and
`/health/identity` responses, status codes, and headers are unchanged.

**AC-11 Documentation.** Maintainer documentation explains:

- each generic signal and where to read it (Sentry transactions, the request
  metric, Railway logs);
- how to exclude health routes from the 5xx rate;
- what `<unmatched>` and `_OTHER` mean;
- that percentiles on low-traffic routes are estimates;
- the out-of-memory and restart visibility limits;
- `SENTRY_TRACES_SAMPLE_RATE`;
- the Development evidence checklist.

The observability doc, the telemetry privacy policy, the logging guide, and the
delivery operations variable table are updated to match.

**AC-12 No other behavior change.** No public API change, no product analytics,
no new metric beyond AC-5, and no request body or SQL parameter capture.
Existing tests change only where the key rename or the new configuration
requires it.

## Design

- `observability/sentry.py`
  - `init_sentry(dsn, identity, *, traces_sample_rate=None)` passes a
    `traces_sampler` only when a rate is given. The sampler reads `PATH_INFO`
    from `sampling_context["wsgi_environ"]`.
  - `parse_traces_sample_rate(value)` returns `None` for unset or empty, a
    float in `[0, 1]`, or raises `RuntimeError`.
  - `before_send_transaction` also renames `url`-sourced transactions to
    `<unmatched>` and removes their `request.url`.
- `observability/middleware.py`
  - It emits the request metric with `sentry_sdk.metrics.count`.
  - The completion line uses the underscore keys.
  - The middleware is part of the observability module, so feature code still
    never calls the metrics API.
- `observability/privacy.py`
  - Owns the `<unmatched>` and `_OTHER` values.
  - Accepts both as bounded values for `http.route` and `http.request.method`.
  - The transaction backstop lives with the other scrubbers.
- `observability/logging.py`
  - The allow-list and formatter use the underscore keys.
  - `build_logging_config()` also configures `gunicorn.error` to propagate to
    the root stdout handler at INFO.
- `gunicorn.conf.py` sets `logconfig_dict` from the same logging configuration.
  Setting it turns on Gunicorn's access log, so `gunicorn.access` is capped at
  WARNING with the other third-party loggers.
  Gunicorn reads `./gunicorn.conf.py` from its working directory by default, so
  the Docker CMD does not change.
- `config/settings/production.py` passes
  `parse_traces_sample_rate(os.environ.get("SENTRY_TRACES_SAMPLE_RATE"))` to
  `init_sentry`.

Sentry's own transaction names use the SDK's route format, for example
`/api/conventions/{pk}/`. The metric's `http.route` uses Django's template, for
example `api/conventions/<int:pk>/`, which is what the privacy allow-list
checks. The documentation states both.

## Test surface

Seams the tests use, which production code must provide:

- `observability.sentry.init_sentry(dsn, identity, *, traces_sample_rate: float | None = None) -> bool`.
- `observability.sentry.parse_traces_sample_rate(value: str | None) -> float | None`.
- `observability.privacy.UNMATCHED_ROUTE == "<unmatched>"` and
  `observability.privacy.OTHER_METHOD == "_OTHER"`.
- `observability.middleware.REQUEST_METRIC == "tailtag.http.server.requests"`.
- `observability.logging.build_logging_config()` includes the `gunicorn.error`
  logger.
- `services/api/gunicorn.conf.py` defines `logconfig_dict`.

Rules:

- Requests go through Django's test client, with the configured stdout handler
  captured and the Sentry client's transport replaced after `init_sentry`. The
  capturing transport is the only substitute.
- Tracing tests serve requests through Django's real `WSGIHandler`
  (`tests.observability_test_support.wsgi_request`), because the SDK starts
  transactions there and the test client bypasses it.
- Gunicorn log tests use Gunicorn's real `Config` and `glogging.Logger` with the
  real `gunicorn.conf.py`, and restore the process logging configuration
  afterwards.
- Negative tests use synthetic sentinel values, never real credentials.
- Extend the existing observability test modules and
  `tests/observability_test_support.py` rather than adding parallel helpers.

## Development deploy evidence

After merge to `main`, which deploys to Development, and after the maintainer
sets `SENTRY_TRACES_SAMPLE_RATE=1.0` there:

- **D-4** Sentry shows transactions named by route. Explore shows p50/p95/p99 of
  duration for one route. Record whether a monitor can use a p95 span duration
  threshold. If it cannot, record the documented equivalent: percentiles on the
  dashboard, with alerts on counts and 5xx.
- **D-5** `tailtag.http.server.requests` appears in Sentry, grouped by
  `http.route` and `http.response.status_class`, and the monitor builder offers
  a count threshold filtered by status class. Nothing is saved; monitors belong
  to #216.
- **D-6** A request to an unknown path appears as `<unmatched>` in transactions
  and in the metric, and no transaction is named by that raw path or carries
  it as its request URL.
- **D-7** Railway log search `@logger:gunicorn.error` returns Gunicorn's boot
  lines as JSON, and `@http_route:<template>` filters completion lines. This
  also settles the quoting syntax for route values.
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

Results are recorded in the
[backend service signals](../operations/backend-service-signals.md) guide. Failures lead to follow-up decisions,
not silent changes to this contract.

## Risks

- Sentry's documentation does not say that monitors support span-duration
  percentiles. Resolved by D-4: the monitor builder accepts a p95 threshold.
- With little traffic, p95/p99 on quiet routes are noisy estimates. At rate
  `1.0` in Development and Staging they are exact for the traffic received.
- The route allow-list is cached per process (#211), so a route added at
  runtime would be stripped from the metric with a one-time warning.
- Gunicorn configures logging before Django in the master. If
  `gunicorn.conf.py` cannot import the logging configuration, Gunicorn fails
  to start. `make api-gunicorn-check` in CI guards this.

## Known limitations

- Error events raised during an unmatched request keep the client's raw path in
  their `transaction` name and `request.url`; the rename covers transactions
  only. This predates #212.
- Client-supplied `sentry-trace` and `baggage` headers are continued by the
  SDK. A client can choose the `trace_id` recorded in logs and Sentry. At rates
  below `1.0`, the `sample_rand` in `baggage` can also influence which of its
  requests are sampled. The `request_id` is unaffected. Ignoring those headers
  is [#260](https://github.com/TailTag-Game/tailtag/issues/260).
