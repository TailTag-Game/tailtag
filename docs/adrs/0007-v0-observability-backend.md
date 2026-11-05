# Use Render and Sentry for V0 observability

**Status:** proposed

**Related issues:** [#209 — Define the V0 observability architecture and telemetry backend](https://github.com/TailTag-Game/tailtag/issues/209), parent [#198 — Field-Beta Observability](https://github.com/TailTag-Game/tailtag/issues/198)

**Instrumentation boundary:** [V0 backend observability architecture](../architecture/backend/observability.md)

**Hosting change:** This ADR first named Railway. [ADR 0011](0011-move-v0-hosting-from-railway-to-render.md) moved V0 hosting to Render, so [#412](https://github.com/TailTag-Game/tailtag/issues/412) changed the log and resource owner to Render on 2026-11-04. The Sentry decision did not change.

## Context and constraints

Field-beta operators must be able to tell whether TailTag is healthy, whether catches succeed, whether requests are slow, whether PostgreSQL or authentication is degraded, whether credential, session, or eligibility failures are rising, whether traffic is abnormal, and which build is deployed. They must be able to follow one request without searching by sensitive user data.

The API runs Django and DRF under Gunicorn sync workers on Render ([ADR 0011](0011-move-v0-hosting-from-railway-to-render.md)). It has standard Python logging and no telemetry dependency. Build identity (`source_sha`, `deployment_id`, `environment`) from [#201](https://github.com/TailTag-Game/tailtag/issues/201) and the `/health/live`, `/health/ready`, and `/health/identity` routes from [#203](https://github.com/TailTag-Game/tailtag/issues/203) already exist. This decision reuses them rather than adding a second version or health source.

Render's documentation (reviewed 2026-11-04) shows that a Render Pro workspace provides these signals:

- Search over structured JSON stdout logs. Pro keeps logs for 14 days ([Render logging](https://render.com/docs/logging)).
- HTTP request logs for public requests, with method, status, host, path, and a `requestID`. These need Pro. Render sends the same value to the service in the `Rndr-Id` header.
- CPU, memory, and outbound bandwidth graphs for the web service. HTTP request counts and p50 to p99 response times need Pro ([Render service metrics](https://render.com/docs/service-metrics)).
- CPU, memory, disk, and connection graphs for Render Postgres.
- Email and Slack notifications for failed deploys and unhealthy services, and deploy webhooks on Pro.
- Log streams over syslog or HTTPS ([Render log streams](https://render.com/docs/log-streams)), and metric streams to OpenTelemetry providers on Pro.

Render does not collect application metrics, error rates, or domain outcomes. It has no log-pattern alerting and no CPU or memory threshold alerts. It does not group exceptions. Log access follows the workspace role, not the environment.

Constraints from #198 and #209:

- no large self-hosted stack, data warehouse, or product analytics;
- no new public API solely for observability;
- bounded metric cardinality;
- the same redaction rules in every environment;
- portable, OpenTelemetry-compatible concepts where practical.

The V0 cost ceiling is deliberately undecided until player activity is better understood.

## Decision

Use **Render** for structured logs and runtime resource signals, and hosted **Sentry** for exceptions, tracing, bounded application metrics, the operator dashboard, and alerts. The application sends telemetry directly to Sentry through the Python `sentry-sdk`. No collector, forwarder, or scrape endpoint is deployed.

| Responsibility | Owner |
| --- | --- |
| Structured application logs and search | Render (JSON stdout) |
| Edge HTTP request logs | Render (Pro) |
| CPU, memory, network, and disk | Render |
| Exception reporting and grouping | Sentry |
| Request tracing | Sentry (native SDK tracing) |
| Application and domain metrics | Sentry application metrics |
| Operator dashboard | Sentry |
| Alerts | Sentry monitors and uptime monitoring. Render deploy and health notifications and deploy webhooks are optional supplements. |
| Log retention and log access | Render plan (14 days on Pro) and workspace roles |
| Error, trace, and metric retention and access | Sentry plan and project teams |

Sentry's log product is not used in V0, so logs have a single store. Render log streams and metric streams exist, but V0 does not use them. Logging breadcrumbs attached to Sentry errors follow the same redaction rules as stdout logs.

The linked architecture document defines the data paths, environment separation, access boundaries, and the instrumentation boundary that later observability issues must follow.

## Alternatives considered

- **Render alone.** Rejected. Render does not collect error rates or business metrics. It cannot alert on log patterns and does not group exceptions, so it cannot answer the catch, authentication, or error-rate questions in #198. (The first version of this ADR rejected Railway alone for the same reasons.)
- **Grafana Cloud through OpenTelemetry, plus Sentry for exceptions.** This is the strongest metrics, dashboard, and alerting fit and the most portable option. It is not selected for V0 because it adds a second vendor and SDK and requires per-worker OpenTelemetry initialization under Gunicorn prefork. The OpenTelemetry Python fork-process guidance is traces-only and conflicts with other upstream guidance. It also relies on pre-1.0 Django and psycopg instrumentation. This is the documented fallback if Sentry's metrics or alerting prove insufficient.
- **Better Stack or Axiom through OpenTelemetry.** Not selected. Both are capable log and metric stores, but they are less established for exception grouping. Using them would still mean a second error tool or a weaker error workflow, and adding a second vendor would bring the same operating costs as the Grafana option.
- **Honeycomb.** Not selected. It is strong for tracing but has no exception-grouping product, and its paid entry tier is priced well above the other hosted options.
- **Self-hosted Prometheus, Loki, and Grafana, or a hosted collector or forwarder.** Rejected by the #198 and #209 scope. Render log streams can move logs off-platform without a collector, so a collector adds no value. A Prometheus scrape endpoint would add an observability-only HTTP surface and need a multiprocess workaround under Gunicorn.
- **Sentry's OTLP integration instead of native SDK tracing.** Deferred. Sentry's OTLP intake was in open beta for traces and logs only. It cannot be combined with native Sentry tracing, and it would still leave metrics and exceptions on the Sentry SDK.

## Consequences and risks

- **Vendor lock-in.** Instrumentation uses a proprietary SDK. This is mitigated by the portable instrumentation boundary: OpenTelemetry semantic-convention names, bounded dimensions, and a single TailTag-owned place that records domain outcomes. Moving to an OTLP backend later then changes that boundary rather than every call site.
- **Sentry sends sensitive data by default.** The default SDK behavior sends full request URLs with query strings and JSON or form request bodies. Server-side scrubbing is documented for errors and logs, not spans or metrics. SDK-side configuration and hooks are therefore the primary redaction control ([#211](https://github.com/TailTag-Game/tailtag/issues/211)).
- **Plan limits.** The free Sentry plan allows one user and email-only alert notification. Shared operator access and chat notification need a paid plan. That cost decision is intentionally deferred.
- **Split retention.** Logs follow Render plan retention (14 days on Pro) and everything else follows Sentry's. [#215](https://github.com/TailTag-Game/tailtag/issues/215) must set policy across both.
- **Correlation spans two tools.** Log lines and Sentry events must share correlation fields, or operators lose the link between a log and its trace.
- **Workspace-wide log access.** On Render, every Admin and Developer in the workspace can view service logs. Protected environments do not list log viewing as an Admin-only action. Separating future Production log access can need a separate workspace. That is decided with Production, not here.

## Validation and rollback

This ADR is accepted after two demonstrations in Development.

- [#210](https://github.com/TailTag-Game/tailtag/issues/210) must show:
  - Sentry SDK initialization per Gunicorn worker;
  - sanitized exception reporting;
  - correlation between a host log line and its Sentry event. #210 showed this on Railway before the Render move.
- The first application metric from [#212](https://github.com/TailTag-Game/tailtag/issues/212) must be queryable in Sentry and able to drive a monitor.

If either demonstration fails, revisit the Grafana Cloud fallback before instrumentation continues. Staging-authoritative validation depends on [#200](https://github.com/TailTag-Game/tailtag/issues/200) and belongs to [#217](https://github.com/TailTag-Game/tailtag/issues/217).

Rollback is two-way at V0 scale. Removing the SDK and its configuration returns to Render-only visibility with no data migration. Replacing Sentry follows the fallback above and is confined to the instrumentation boundary.
