# Use Railway and Sentry for V0 observability

**Status:** proposed

**Related issues:** [#209 — Define the V0 observability architecture and telemetry backend](https://github.com/TailTag-Game/tailtag/issues/209), parent [#198 — Field-Beta Observability](https://github.com/TailTag-Game/tailtag/issues/198)

**Instrumentation boundary:** [V0 backend observability architecture](../architecture/backend/observability.md)

## Context and constraints

Field-beta operators must be able to tell whether TailTag is healthy, whether catches succeed, whether requests are slow, whether PostgreSQL or authentication is degraded, whether credential, session, or eligibility failures are rising, whether traffic is abnormal, and which build is deployed. They must be able to follow one request without searching by sensitive user data.

The API runs Django and DRF under Gunicorn sync workers on Railway ([ADR 0004](0004-use-railway-for-v0-hosting.md)). It has standard Python logging and no telemetry dependency. Build identity (`source_sha`, `deployment_id`, `environment`) from [#201](https://github.com/TailTag-Game/tailtag/issues/201) and the `/health/live`, `/health/ready`, and `/health/identity` routes from [#203](https://github.com/TailTag-Game/tailtag/issues/203) already exist. This decision reuses them rather than adding a second version or health source.

Railway's documentation (reviewed 2026-09-29) shows that Railway provides:

- environment-wide search over structured JSON stdout logs;
- edge HTTP logs with method, path, status, duration, and request ID;
- CPU, memory, network, and disk graphs;
- resource-threshold monitors on Pro;
- deployment webhooks.

It does not collect application metrics, latency percentiles, or error rates. It has no log-pattern alerting and no built-in log drain. Its OTLP receiver accepts traces only. Log access is workspace-wide rather than per environment.

Constraints from #198 and #209:

- no large self-hosted stack, data warehouse, or product analytics;
- no new public API solely for observability;
- bounded metric cardinality;
- the same redaction rules in every environment;
- portable, OpenTelemetry-compatible concepts where practical.

The V0 cost ceiling is deliberately undecided until player activity is better understood.

## Decision

Use **Railway** for structured logs and runtime resource signals, and hosted **Sentry** for exceptions, tracing, bounded application metrics, the operator dashboard, and alerts. The application sends telemetry directly to Sentry through the Python `sentry-sdk`. No collector, forwarder, or scrape endpoint is deployed.

| Responsibility | Owner |
| --- | --- |
| Structured application logs and search | Railway (JSON stdout) |
| Edge HTTP request logs | Railway |
| CPU, memory, network, and disk | Railway |
| Exception reporting and grouping | Sentry |
| Request tracing | Sentry (native SDK tracing) |
| Application and domain metrics | Sentry application metrics |
| Operator dashboard | Sentry |
| Alerts | Sentry monitors and uptime monitoring; Railway resource monitors and deployment webhooks are optional supplements |
| Log retention and log access | Railway plan and workspace |
| Error, trace, and metric retention and access | Sentry plan and project teams |

Sentry's log product is not used in V0, so logs have a single store. Logging breadcrumbs attached to Sentry errors follow the same redaction rules as stdout logs.

The linked architecture document defines the data paths, environment separation, access boundaries, and the instrumentation boundary that later observability issues must follow.

## Alternatives considered

- **Railway alone.** Rejected. Railway's own documentation says it does not collect request latency, error rates, or business metrics. It cannot alert on log patterns and does not group exceptions, so it cannot answer the catch, authentication, or error-rate questions in #198.
- **Grafana Cloud through OpenTelemetry, plus Sentry for exceptions.** This is the strongest metrics, dashboard, and alerting fit and the most portable option. It is not selected for V0 because it adds a second vendor and SDK and requires per-worker OpenTelemetry initialization under Gunicorn prefork. The OpenTelemetry Python fork-process guidance is traces-only and conflicts with other upstream guidance. It also relies on pre-1.0 Django and psycopg instrumentation. This is the documented fallback if Sentry's metrics or alerting prove insufficient.
- **Better Stack or Axiom through OpenTelemetry.** Not selected. Both are capable log and metric stores, but they are less established for exception grouping. Using them would still mean a second error tool or a weaker error workflow, and adding a second vendor would bring the same operating costs as the Grafana option.
- **Honeycomb.** Not selected. It is strong for tracing but has no exception-grouping product, and its paid entry tier is priced well above the other hosted options.
- **Self-hosted Prometheus, Loki, and Grafana, or a Railway-hosted collector or forwarder.** Rejected by the #198 and #209 scope. A collector or forwarder would also be the only way to move Railway logs off-platform, because Railway has no log drain. A Prometheus scrape endpoint would add an observability-only HTTP surface and need a multiprocess workaround under Gunicorn.
- **Sentry's OTLP integration instead of native SDK tracing.** Deferred. Sentry's OTLP intake was in open beta for traces and logs only. It cannot be combined with native Sentry tracing, and it would still leave metrics and exceptions on the Sentry SDK.

## Consequences and risks

- **Vendor lock-in.** Instrumentation uses a proprietary SDK. This is mitigated by the portable instrumentation boundary: OpenTelemetry semantic-convention names, bounded dimensions, and a single TailTag-owned place that records domain outcomes. Moving to an OTLP backend later then changes that boundary rather than every call site.
- **Sentry sends sensitive data by default.** The default SDK behavior sends full request URLs with query strings and JSON or form request bodies. Server-side scrubbing is documented for errors and logs, not spans or metrics. SDK-side configuration and hooks are therefore the primary redaction control ([#211](https://github.com/TailTag-Game/tailtag/issues/211)).
- **Plan limits.** The free Sentry plan allows one user and email-only alert notification. Shared operator access and chat notification need a paid plan. That cost decision is intentionally deferred.
- **Split retention.** Logs follow Railway plan retention and everything else follows Sentry's. [#215](https://github.com/TailTag-Game/tailtag/issues/215) must set policy across both.
- **Correlation spans two tools.** Log lines and Sentry events must share correlation fields, or operators lose the link between a log and its trace.
- **Workspace-wide log access.** Railway log access is workspace-wide, so separating future Production log access needs a separate Railway project or workspace. That is decided with Production, not here.

## Validation and rollback

This ADR is accepted after two demonstrations in Development.

- [#210](https://github.com/TailTag-Game/tailtag/issues/210) must show:
  - Sentry SDK initialization per Gunicorn worker;
  - sanitized exception reporting;
  - correlation between a Railway log line and its Sentry event.
- The first application metric from [#212](https://github.com/TailTag-Game/tailtag/issues/212) must be queryable in Sentry and able to drive a monitor.

If either demonstration fails, revisit the Grafana Cloud fallback before instrumentation continues. Staging-authoritative validation depends on [#200](https://github.com/TailTag-Game/tailtag/issues/200) and belongs to [#217](https://github.com/TailTag-Game/tailtag/issues/217).

Rollback is two-way at V0 scale. Removing the SDK and its configuration returns to Railway-only visibility with no data migration. Replacing Sentry follows the fallback above and is confined to the instrumentation boundary.
