# V0 backend observability architecture

**Status:** proposed with [ADR 0007](../../adrs/0007-v0-observability-backend.md)

**Related issues:** [#209](https://github.com/TailTag-Game/tailtag/issues/209) (this architecture), parent [#198](https://github.com/TailTag-Game/tailtag/issues/198)

This is a living document. [ADR 0007](../../adrs/0007-v0-observability-backend.md) records the tooling decision. This document records how that decision is applied: data paths, environment and access boundaries, and the instrumentation boundary.

The later observability issues refine it:

- [#211](https://github.com/TailTag-Game/tailtag/issues/211) owns the privacy and cardinality rules;
- [#215](https://github.com/TailTag-Game/tailtag/issues/215) owns retention and access policy;
- the other #198 children implement against it.

Those issues amend this document rather than defining a parallel convention.

## 1. Components

| Component | Responsible for | Not responsible for |
| --- | --- | --- |
| Railway | Structured JSON stdout logs and search; edge HTTP logs; CPU, memory, network, and disk graphs; deployment events | Application metrics, error grouping, tracing, alerting on application behavior |
| Sentry | Exceptions and grouping; request traces and spans; bounded application and domain metrics; the field-beta dashboard; monitors, uptime checks, and alert routing | Application log storage (Sentry Logs is not enabled in V0) |
| TailTag API | Emitting correlated structured logs; initializing the Sentry SDK; enforcing redaction before data leaves the process; recording domain outcomes through one shared module | Hosting any collector, forwarder, or scrape endpoint |

## 2. Operator questions

This table maps the #198 operator questions to where each is answered.

| Question | Primary signal | Where |
| --- | --- | --- |
| Is TailTag healthy? | Uptime check of `/health/ready`; 5xx count from `tailtag.http.server.requests` | Sentry |
| Are catches succeeding? | Catch outcome metric by bounded outcome | Sentry |
| Are requests slow? | Transaction duration percentiles by route template | Sentry; per-request detail in Railway HTTP logs |
| Is PostgreSQL degraded? | Readiness failures; connection-attempt outcomes, reasons, and duration ([#214](https://github.com/TailTag-Game/tailtag/issues/214)); database spans | Sentry; resource pressure in Railway |
| Is media storage failing? | Storage operation outcomes and reasons ([#214](https://github.com/TailTag-Game/tailtag/issues/214)) | Sentry |
| Is authentication degraded? | Authentication outcome metric by bounded failure class | Sentry |
| Are credential, session, or eligibility failures rising? | Domain outcome metrics ([#213](https://github.com/TailTag-Game/tailtag/issues/213)) | Sentry |
| Is traffic abnormal? | Request count by route template from `tailtag.http.server.requests` | Sentry; raw volume in Railway HTTP logs |
| Which build produced this? | `release` and `deployment_id` on every event and log line | Both |
| What happened to one request? | `request_id` and `trace_id` | Sentry trace; Railway logs filtered by `@request_id` |

## 3. Data paths

```text
Mobile client ──HTTPS──► Railway edge ──► Gunicorn worker (Django/DRF)
                              │                     │
                              │                     ├─ stdout JSON logs ──────► Railway logs
                              ▼                     │
                      Railway HTTP logs             └─ sentry-sdk (HTTPS push) ─► Sentry
                                                         errors, spans, metrics

Sentry uptime monitor ──HTTPS──► /health/ready   (per monitored environment)
```

- All telemetry is **pushed**. Nothing scrapes the API, and no observability-only route is added.
- Redaction runs in the API process, before stdout or SDK transmission. Sentry server-side scrubbing is a second layer, not the control.
- The mobile client sends no telemetry in V0.

## 4. Environments

- Each Railway environment reports as itself. Sentry's `environment` comes from the build identity's `environment` field (`RAILWAY_ENVIRONMENT_NAME`), not from a separately maintained value.
- Sentry `release` is the build identity's `source_sha` when present.
- Development and Staging share one Sentry project, separated by `environment`, which follows Sentry's guidance to use projects for services and environments for stages.
- A future Production environment uses its **own Sentry project** so its access can be restricted by project team. Production also needs its own Railway project or workspace if log access must be narrower than the current workspace-wide Railway access. That choice is made with Production.
- Dashboards and monitors filter on `environment`. A Development spike must never page as a Staging or Production alert.
- The redaction rules are identical in every environment.

## 5. Access and authentication boundaries

- **Railway logs:** workspace Admin and Member roles can read logs. Deployer cannot. Per-environment access control needs Railway committed spend, so Production will be separated by project or workspace instead.
- **Sentry:** access is granted per project through project teams. Open Membership should be off, so that joining an access-granting team requires approval.
- **Ingest credential:** the Sentry DSN is runtime configuration held in Railway variables per environment. It is never committed, echoed in logs, or recorded in issues or evidence.
- **Operator access:** operators use their own named accounts in both tools. Shared accounts are not used.
- Retention, operator roles, and evidence preservation are in the [telemetry retention and access policy](telemetry-retention-access.md) ([#215](https://github.com/TailTag-Game/tailtag/issues/215)).

## 6. Instrumentation boundary

Every later observability issue must use this boundary.

### 6.1 SDK initialization

- Initialize `sentry-sdk` once, from Django settings, only when a DSN is configured. Local development and tests run without it.
- Metrics require `sentry-sdk` 2.44.0 or later.
- Gunicorn currently runs without `--preload`, so each worker imports Django, and initializes the SDK, after fork. Do not add `--preload` or a pre-fork initialization path without moving SDK initialization into a post-fork hook and validating it.
- Use native SDK tracing. Do not enable Sentry's OTLP integration alongside it.
- Keep `send_default_pii` off, or its successor data-collection option at the equivalent setting.
- Disable request-body capture.
- Strip query strings from reported URLs. [#211](https://github.com/TailTag-Game/tailtag/issues/211) allow-lists none, so every query string is stripped ([telemetry privacy policy](telemetry-privacy.md#6-sql-spans-and-query-strings)).

### 6.2 Correlation fields

Every structured log line, Sentry event, and span carries these fields where applicable.

| Field | Meaning |
| --- | --- |
| `request_id` | Per-request correlation ID, generated by the API for every request. Client-supplied correlation headers are ignored. Decided in [#210](https://github.com/TailTag-Game/tailtag/issues/210). |
| `railway_request_id` | Railway's edge ID from the inbound `X-Railway-Request-Id` header, recorded only when it is 1–64 characters of `[A-Za-z0-9_-]`. It links log lines to Railway HTTP logs. Railway returns the same ID to clients as the `x-railway-request-id` response header, so TailTag adds no response header of its own. |
| `trace_id`, `span_id` | Active Sentry trace context. |
| `environment` | From build identity. |
| `release` | From build identity (`source_sha`). |
| `deployment_id` | From build identity. |

Railway's log query syntax supports custom JSON attribute filters, so operators should be able to filter logs by `@request_id` or `@trace_id`. Check D-1 of [#210](https://github.com/TailTag-Game/tailtag/issues/210) will confirm this in Development after merge, because Railway does not document whether every custom key is indexed. Correlation keys contain no dots, so they do not depend on how Railway treats dotted keys. The field contract and request lookup steps are in [backend logging and request correlation](../../operations/backend-logging.md).

### 6.3 Structured log events

- Emit one JSON object per line with `message`, `level`, `logger`, and the correlation fields.
- Domain events use an `event` field named `tailtag.<module>.<event>`, for example `tailtag.catches.confirmation`.
- Where an [OpenTelemetry semantic convention](https://opentelemetry.io/docs/specs/semconv/) name exists, use it for Sentry span and metric attributes: for example `http.request.method`, `http.route`, `http.response.status_code`, and `error.type`. TailTag-specific Sentry attributes use the `tailtag.` prefix.
- Log keys never contain dots, because Railway log search cannot filter on keys that contain dots; values containing dots filter normally ([#210 D-1](../../operations/backend-logging.md#development-evidence)). [#212](https://github.com/TailTag-Game/tailtag/issues/212) chose flat underscore names over nested objects, because underscore keys are proven to filter and nested filtering is undocumented. A log key is the OpenTelemetry name with underscores for dots, for example `http_route` and `error_type`, or uses the `tailtag_` prefix.
- Gunicorn's `gunicorn.error` records use the same JSON formatter, through `services/api/gunicorn.conf.py`.
- Logging breadcrumbs attached to Sentry errors follow the same redaction rules as stdout logs. The key allow-list, text redaction, and third-party logger caps are in the [telemetry privacy policy](telemetry-privacy.md).

### 6.4 Metrics and dimensions

- Record metrics through the Sentry SDK (`count`, `distribution`, `gauge`). Name them `tailtag.<module>.<measure>`.
- The generic request metric is `tailtag.http.server.requests`, a count of 1 per request with `http.route`, `http.request.method`, and `http.response.status_class`. It is emitted by the request correlation middleware and is not sampled ([#212](https://github.com/TailTag-Game/tailtag/issues/212)).
- Allowed dimensions are **closed, bounded sets only**:
  - `environment`;
  - `http.route` (the route template, never the raw path);
  - `http.request.method`;
  - HTTP status class;
  - `tailtag.outcome` and `tailtag.reason`, from enumerations defined in code;
  - `rpc.method`, for object storage operations.
- Never use these as dimensions: user, account, Clerk, fursuit, convention, catch, or session IDs; credentials or tokens; raw paths or query strings; exception messages; or any free text.
- Build identity (`release`, `deployment_id`) is not a TailTag metric dimension, because every deployment would add new values. It stays on log lines, errors, and spans, and deployment-regression questions use those signals.
- The SDK attaches `sentry.release` to metrics automatically. [#211](https://github.com/TailTag-Game/tailtag/issues/211) decided to keep it as a narrow exception, alongside `sentry.environment` and `sentry.sdk.*`. TailTag code never adds `release` or `deployment_id` as a dimension.
- The `before_send_metric` hook removes every other attribute that is not allow-listed with a bounded value.
- Internal entity IDs may appear raw in protected logs and span attributes, never as metric attributes, and are never hashed. Clerk user and subject IDs are prohibited in all telemetry. See the [telemetry privacy policy](telemetry-privacy.md#4-entity-ids).
- Domain outcomes are recorded through **one shared backend module**, named by [#210](https://github.com/TailTag-Game/tailtag/issues/210), that owns the outcome and reason enumerations. It emits the metric and the log event together. Feature code does not call the Sentry metrics API directly. That keeps a future OTLP backend swap confined to this module.
- [#213](https://github.com/TailTag-Game/tailtag/issues/213) delivered this module as `services/api/observability/outcomes.py`. The values and how to read them are in [backend domain outcomes](../../operations/backend-domain-outcomes.md).

### 6.5 Error reporting

- Unhandled exceptions and unexpected dependency failures are Sentry errors.
- Expected domain rejections are outcomes, not errors. Examples are duplicate catch, stale credential, ineligible player, and failed authentication. They do not call `capture_exception`, and isolated 4xx responses never page.

### 6.6 Traces

- Transactions are named by route template. A request that matches no route is named `<unmatched>`, never its raw path.
- Spans for SQL keep parameterized query text and never include parameter values. [#211](https://github.com/TailTag-Game/tailtag/issues/211) decided to keep the query text and remove parameter data in `before_send_transaction`. [#212](https://github.com/TailTag-Game/tailtag/issues/212) proved this on real transactions.
- Sampling rates are per-environment configuration, not code constants. `SENTRY_TRACES_SAMPLE_RATE` sets the rate; unset means tracing is off. `/health/live` and `/health/ready` are never traced, `HEAD` and `OPTIONS` requests are never traced (the SDK's Django integration default), and the sampler ignores a client's sampling decision. The request metric counts all of them.
- Latency percentiles come from transactions. Sentry weights sampled transactions by the inverse sample rate. Counts come from the request metric, which is not sampled.

## 7. Constraints handed to later issues

- **[#211](https://github.com/TailTag-Game/tailtag/issues/211):** delivered. The rules are in the [telemetry privacy policy](telemetry-privacy.md).
  - Redaction is enforced through SDK-side controls, because server-side scrubbing is not documented for spans or metrics.
  - The hooks are `before_send`, `before_send_transaction`, `before_breadcrumb`, and `before_send_metric`. `before_send_span` is needed only if stream mode is adopted.
  - The dimension allow-list above is enforced in code.
  - Later issues extend the allow-lists as described in the policy's extension section.
- **[#212](https://github.com/TailTag-Game/tailtag/issues/212):** delivered. How to read the generic service signals is in [backend service signals](../../operations/backend-service-signals.md).
- **[#213](https://github.com/TailTag-Game/tailtag/issues/213):** delivered. How to read and extend the domain outcomes is in [backend domain outcomes](../../operations/backend-domain-outcomes.md).
- **[#214](https://github.com/TailTag-Game/tailtag/issues/214):** delivered. How to read database, storage, Clerk, and runtime dependency health is in [backend dependency health](../../operations/backend-dependency-health.md).
- **[#215](https://github.com/TailTag-Game/tailtag/issues/215):** delivered. Retention and access rules are in the [telemetry retention and access policy](telemetry-retention-access.md). Evidence preservation and export are in the [evidence preservation runbook](../../operations/telemetry-evidence-preservation.md).
- **[#216](https://github.com/TailTag-Game/tailtag/issues/216):**
  - Build one Sentry dashboard, plus monitors built on the errors, spans, and metrics datasets, plus an uptime monitor of `/health/ready`.
  - The free and Team plans each include one uptime monitor, so plan the environments monitored accordingly.
  - Chat or webhook alert routing needs a paid plan.
- **Cost:** no ceiling is set yet. As reviewed on 2026-09-29, Sentry's free plan allowed one user and email alerts, and the Team plan started at $26/month with unlimited users. Every plan includes 5 GB of application metrics.

## 8. Out of scope

This architecture does not include:

- product or engagement analytics;
- mobile or frontend telemetry;
- simulation tooling (#199);
- any self-hosted collector or observability stack;
- any new public API for observability;
- a 24/7 on-call program.
