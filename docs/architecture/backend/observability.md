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
| Is TailTag healthy? | Uptime check of `/health/ready`; 5xx rate | Sentry |
| Are catches succeeding? | Catch outcome metric by bounded outcome | Sentry |
| Are requests slow? | Transaction duration by route template | Sentry; per-request detail in Railway HTTP logs |
| Is PostgreSQL degraded? | Readiness failures, database errors, connection-health metrics ([#214](https://github.com/TailTag-Game/tailtag/issues/214)) | Sentry; resource pressure in Railway |
| Is authentication degraded? | Authentication outcome metric by bounded failure class | Sentry |
| Are credential, session, or eligibility failures rising? | Domain outcome metrics ([#213](https://github.com/TailTag-Game/tailtag/issues/213)) | Sentry |
| Is traffic abnormal? | Request throughput by route template | Sentry; raw volume in Railway HTTP logs |
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

- **Railway logs:** workspace Admin and Member roles can read logs. Deployer cannot. Railway does not document per-environment log restriction.
- **Sentry:** access is granted per project through project teams. Open Membership should be off, so that joining an access-granting team requires approval.
- **Ingest credential:** the Sentry DSN is runtime configuration held in Railway variables per environment. It is never committed, echoed in logs, or recorded in issues or evidence.
- **Operator access:** operators use their own named accounts in both tools. Shared accounts are not used.
- The detailed access policy belongs to [#215](https://github.com/TailTag-Game/tailtag/issues/215).

## 6. Instrumentation boundary

Every later observability issue must use this boundary.

### 6.1 SDK initialization

- Initialize `sentry-sdk` once, from Django settings, only when a DSN is configured. Local development and tests run without it.
- Metrics require `sentry-sdk` 2.44.0 or later.
- Gunicorn currently runs without `--preload`, so each worker imports Django, and initializes the SDK, after fork. Do not add `--preload` or a pre-fork initialization path without moving SDK initialization into a post-fork hook and validating it.
- Use native SDK tracing. Do not enable Sentry's OTLP integration alongside it.
- Keep `send_default_pii` off, or its successor data-collection option at the equivalent setting.
- Disable request-body capture.
- Strip query strings from reported URLs unless [#211](https://github.com/TailTag-Game/tailtag/issues/211) allow-lists them.

### 6.2 Correlation fields

Every structured log line, Sentry event, and span carries these fields where applicable.

| Field | Meaning |
| --- | --- |
| `request_id` | Per-request correlation ID. [#210](https://github.com/TailTag-Game/tailtag/issues/210) decides whether it is generated or adopted from an inbound header, and how it relates to Railway's edge `@requestId`. |
| `trace_id`, `span_id` | Active Sentry trace context. |
| `environment` | From build identity. |
| `release` | From build identity (`source_sha`). |
| `deployment_id` | From build identity. |

Railway's log query syntax supports custom JSON attribute filters, so operators should be able to filter logs by `@request_id` or `@trace_id`. [#210](https://github.com/TailTag-Game/tailtag/issues/210) confirms this in Development, because Railway does not document whether every custom key is indexed.

### 6.3 Structured log events

- Emit one JSON object per line with `message`, `level`, `logger`, and the correlation fields.
- Domain events use an `event` field named `tailtag.<module>.<event>`, for example `tailtag.catches.confirmation`.
- Where an [OpenTelemetry semantic convention](https://opentelemetry.io/docs/specs/semconv/) name exists, use it for the attribute: for example `http.request.method`, `http.route`, `http.response.status_code`, and `error.type`.
- TailTag-specific attributes use the `tailtag.` prefix.
- Logging breadcrumbs attached to Sentry errors follow the same redaction rules as stdout logs.

### 6.4 Metrics and dimensions

- Record metrics through the Sentry SDK (`count`, `distribution`, `gauge`). Name them `tailtag.<module>.<measure>`.
- Allowed dimensions are **closed, bounded sets only**:
  - `environment`;
  - `http.route` (the route template, never the raw path);
  - `http.request.method`;
  - HTTP status class;
  - `tailtag.outcome` and `tailtag.reason`, from enumerations defined in code.
- Never use these as dimensions: user, account, Clerk, fursuit, convention, catch, or session IDs; credentials or tokens; raw paths or query strings; exception messages; or any free text.
- Build identity (`release`, `deployment_id`) is not a TailTag metric dimension, because every deployment would add new values. It stays on log lines, errors, and spans, and deployment-regression questions use those signals.
- If the SDK attaches `release` to metrics automatically, [#211](https://github.com/TailTag-Game/tailtag/issues/211) decides whether to strip it in `before_send_metric`.
- Where an entity ID is justified, it belongs only in protected logs or span attributes under [#211](https://github.com/TailTag-Game/tailtag/issues/211)'s rules.
- Domain outcomes are recorded through **one shared backend module**, named by [#210](https://github.com/TailTag-Game/tailtag/issues/210), that owns the outcome and reason enumerations. It emits the metric and the log event together. Feature code does not call the Sentry metrics API directly. That keeps a future OTLP backend swap confined to this module.
- [#213](https://github.com/TailTag-Game/tailtag/issues/213) defines the actual outcome and reason values.

### 6.5 Error reporting

- Unhandled exceptions and unexpected dependency failures are Sentry errors.
- Expected domain rejections are outcomes, not errors. Examples are duplicate catch, stale credential, ineligible player, and failed authentication. They do not call `capture_exception`, and isolated 4xx responses never page.

### 6.6 Traces

- Transactions are named by route template.
- Spans for SQL may include parameterized query text but never parameter values. [#211](https://github.com/TailTag-Game/tailtag/issues/211) decides whether query text is kept at all.
- Sampling rates are per-environment configuration, not code constants.

## 7. Constraints handed to later issues

- **[#211](https://github.com/TailTag-Game/tailtag/issues/211):**
  - Enforce redaction through SDK-side controls, because server-side scrubbing is not documented for spans or metrics.
  - The SDK hooks are `before_send`, `before_send_transaction`, and `before_send_metric`, plus `before_send_span` only if stream mode is adopted.
  - Cover headers, Clerk tokens, raw QR or catch credentials, presigned media URLs, request bodies, and query strings.
  - Enforce the dimension allow-list above.
- **[#215](https://github.com/TailTag-Game/tailtag/issues/215):**
  - Set policy across two retention systems.
  - Railway log retention was documented as 7 days on Hobby, 30 on Pro, and up to 90 on Enterprise (reviewed 2026-09-29).
  - Sentry's pricing page and its retention documentation gave different per-plan retention figures at review time. Re-verify retention for errors, spans, and metrics against the chosen plan before setting policy.
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
