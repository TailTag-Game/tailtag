# Backend telemetry privacy and cardinality policy

**Status:** implemented by [#211](https://github.com/TailTag-Game/tailtag/issues/211)

**Related:** [V0 backend observability architecture](observability.md), [ADR 0007](../../adrs/0007-v0-observability-backend.md), [backend logging and request correlation](../../operations/backend-logging.md), parent [#198](https://github.com/TailTag-Game/tailtag/issues/198)

This is the canonical rule set for what the API may put in logs, Sentry errors, breadcrumbs, spans, and metrics. It applies identically in every environment. Staging is treated as production-like, and there is no environment switch in the policy.

The policy is enforced in code by `services/api/observability/privacy.py`, wired into `logging.py` and `sentry.py`. Redaction runs in the API process, before stdout or SDK transmission. Sentry server-side scrubbing is a second layer, not the control.

## 1. Prohibited data

Never put these in any telemetry, in any environment:

- `Authorization` headers and any other request headers;
- Clerk bearer or session tokens, and Clerk user or subject IDs;
- raw QR or catch credentials, including the `tailtag:catch:v1:<token>` payload;
- secrets, passwords, API keys, and the Sentry DSN;
- presigned media URLs, and any URL query string;
- request bodies;
- cookies;
- exception messages on stdout (they belong only in Sentry, after redaction);
- personal data such as email addresses and names.

## 2. Safe fields

### Log fields

Only these keys pass from a logger call's `extra` to stdout or to Sentry breadcrumbs (`ALLOWED_EXTRA_FIELDS` in `services/api/observability/logging.py`):

| Key | Notes |
| --- | --- |
| `event` | Named event, `tailtag.<module>.<event>`. |
| `stage` | Where a failure happened. |
| `http.request.method` | HTTP method. |
| `http.route` | URLconf route template, never the raw path. |
| `http.response.status_code` | Integer status. |
| `duration_ms` | Request duration. |
| `error.type` | Exception class name. |

The formatter also adds these itself, from request and build context: `timestamp`, `level`, `message`, `logger`, `request_id`, `railway_request_id`, `trace_id`, `span_id`, `environment`, `release`, and `deployment_id`. Anything else passed through `extra`, including Django's attached `request`, is dropped silently.

Values of allow-listed keys are not pattern-redacted. Pass only constants, enumerations, and bounded values in them.

### Sentry data

- Events keep only allow-listed `extra` keys.
- The event `release` is the build identity `source_sha`, or absent when identity is unavailable. Environment comes from build identity, or is `unknown`.
- `send_default_pii` is off, local variables are not captured, and request bodies are not captured.

## 3. Redaction layers

Each layer covers what the others cannot. No single layer is the whole control.

1. **Key allow-list.** Only the keys above leave the process from `extra`. This is the primary control for structured fields.
2. **Semgrep rules** in `.semgrep/rules/tailtag-security.yml`, which fail CI. A logger call is a call on a named logger, a `logging.getLogger(...)` chain, or module-level `logging`:
   - `tailtag.logging.interpolated-message` flags a logger call whose message is an f-string, a `.format(...)` result, or a `%`-formatted or concatenated string. Lazy `%s` arguments remain allowed;
   - `tailtag.logging.sensitive-argument` flags a logger call's positional argument, `extra` value, or `extra` key whose expression matches `token|credential|payload|authorization|secret|password|presigned|cookie`;
   - `tailtag.observability.direct-sentry-metrics` flags `sentry_sdk.metrics.*` calls outside `services/api/observability/`.
3. **Text backstop.** `redact_text` replaces only unmistakable shapes and keeps the surrounding text:

   | Shape | Becomes |
   | --- | --- |
   | `Bearer <token>`, case-insensitive scheme | `Bearer [redacted]` |
   | JWT-shaped string, `eyJ….….…` | `[redacted]` |
   | `tailtag:catch:v1:<token>` | `[redacted]` |
   | A query string, `?name=value…`, in an absolute or path-relative URL | `?[redacted]` |

   It runs on the JSON `message`, breadcrumb messages, and Sentry event text: the message, log-entry message, formatted message and params, and exception values. It does not run on `extra` values or on other event fields such as tags.
4. **Third-party logger caps.** `botocore`, `boto3`, `s3transfer`, `urllib3`, and `django.db.backends` are pinned at WARNING, so their INFO and DEBUG output, which carries URLs and SQL detail, never reaches stdout even though the root logger stays at INFO.
5. **Sentry hooks**, registered in `init_sentry`:
   - **Errors (`before_send`):** removes request `query_string`, `data`, `cookies`, and `headers`; strips the query string and fragment from `request.url`; allow-lists `extra`; applies the text backstop.
   - **Breadcrumbs (`before_breadcrumb`):** allow-lists logging breadcrumb data; applies the text backstop to messages; for any breadcrumb data, strips the query string and fragment from `url`, `http.url`, and `url.full`, and removes `http.query`, `http.fragment`, and SQL parameter data.
   - **Transactions and spans (`before_send_transaction`):** applies the error scrubbing, then for the root trace context and every span strips query strings and fragments from HTTP span descriptions and URL data, applies the text backstop to descriptions, and removes `http.query`, `http.fragment`, and SQL parameter data (`db.params`, `db.query.parameter.*`).
   - **Metrics (`before_send_metric`):** see section 5.

## 4. Entity IDs

- Internal TailTag IDs (convention, user, fursuit, activation, session, and catch) may appear raw in **protected logs and span attributes**. Protected means the Railway and Sentry access boundaries in [observability §5](observability.md#5-access-and-authentication-boundaries).
- They are **never metric attributes**. Each is an unbounded, high-cardinality value.
- They are **not hashed**. The ID spaces are small and enumerable, so a hash gives false assurance while stopping operators from looking up a specific entity.
- The convention-ID policy from [#198](https://github.com/TailTag-Game/tailtag/issues/198) applies: keep convention IDs available in protected structured logs and traces where useful, but never use them as a general metric dimension.
- Clerk user and subject IDs are prohibited in all telemetry.
- Note that entity IDs also pass through the log key allow-list. A new key that carries one needs the extension steps in section 8.

## 5. Metric dimension rules

Every metric passes through `scrub_metric`, the `before_send_metric` hook. It keeps an attribute only if it is an SDK attribute, or its key is allow-listed and its value is in that key's bounded set. Any other attribute is removed. The metric itself is still sent.

| Key | Bounded value set |
| --- | --- |
| `http.request.method` | `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, `TRACE`, `CONNECT` |
| `http.route` | A route template from the project URLconf, as `request.resolver_match.route` yields it, for example `api/conventions/<int:pk>/`. A raw path such as `api/v1/fursuits/42/` is rejected. |
| `http.response.status_class` | `1xx`, `2xx`, `3xx`, `4xx`, `5xx` |
| `tailtag.outcome` | Empty until [#213](https://github.com/TailTag-Game/tailtag/issues/213), so every value is rejected today |
| `tailtag.reason` | Empty until #213, so every value is rejected today |

Values must be strings. A non-string value is rejected for every key.

### SDK attributes

- Retained: `sentry.environment`, `sentry.release`, `sentry.sdk.name`, and `sentry.sdk.version`. The SDK attaches these itself.
- Stripped: everything else the SDK or scope attaches, including `server.address`, `process.runtime.*`, `user.id`, `user.email`, `user.name`, and attributes set through `sentry_sdk.set_attribute`.
- **`sentry.release` decision.** It stays as a narrow exception. It is added by the SDK, its value is the build identity `source_sha` only, and it lets an operator see which build produced a metric. TailTag code never adds `release` or `deployment_id` as a metric dimension. Deployment-regression questions still use logs, errors, and spans. If release cardinality becomes a cost problem, remove `sentry.release` from `SDK_METRIC_ATTRIBUTES`.

### Rejection warnings

A rejected attribute logs one WARNING per key per process, naming the metric that first carried it and the key, never the value. Attributes the SDK attaches itself and this policy strips by design (`server.address`, `process.runtime.*`, `user.*`) are dropped silently. The metric is sent either way.

### Where metrics are emitted

Feature code does not call `sentry_sdk.metrics` directly. The `direct-sentry-metrics` Semgrep rule enforces this outside `services/api/observability/`. Domain outcomes go through the shared module that [#213](https://github.com/TailTag-Game/tailtag/issues/213) creates.

## 6. SQL spans and query strings

- SQL spans keep **parameterized query text** and never parameter values. `db.params` and `db.query.parameter.*` data are removed.
- The **query-string allow-list is empty**. Every query string and fragment is stripped from reported URLs, in events, breadcrumbs, and spans. To allow one parameter later, edit the stripping code in `privacy.py` and add a test.

## 7. Known limitations

- **Railway edge HTTP logs are outside app control.** Railway produces these logs before a request reaches the API, so the API cannot redact them. Do not put secrets or personal data in request URLs.
- **A bare catch token in free text is not pattern-detectable.** Only the `tailtag:catch:v1:` prefixed payload is matched. A bare 43-character token in a message has no distinguishing shape, so the Semgrep rules, not the text backstop, are the control.
- **The text backstop covers only its four shapes.** It is a backstop, not a scanner.
- **The route set is cached per process.** `http.route` values are checked against the URLconf as loaded at first use. Routes added at runtime are not recognized.
- **Tracing is not yet enabled.** The transaction and span hooks are proven only on synthetic transaction events until [#212](https://github.com/TailTag-Game/tailtag/issues/212) turns tracing on. Re-check real spans then.
- **Dotted log keys.** #211 adds none. Railway log search cannot filter on dotted keys ([backend logging](../../operations/backend-logging.md#development-evidence)), and #212 decides whether log attributes become nested objects or underscore names.

## 8. Extending the policy

Every addition needs a test in `services/api/tests/test_telemetry_privacy.py` (or a test next to the feature that adds it) and a review against the prohibited list in section 1.

- **New log field ([#212](https://github.com/TailTag-Game/tailtag/issues/212) and later):** add the key to `ALLOWED_EXTRA_FIELDS` in `services/api/observability/logging.py`. Use an OpenTelemetry semantic-convention name where one exists, otherwise a `tailtag.` prefix. Update the table in section 2 and in [backend logging](../../operations/backend-logging.md).
- **New metric dimension:** add the key and its bounded value set to `_is_bounded` in `services/api/observability/privacy.py`, with the value set as a constant beside `_HTTP_METHODS`. Update the table in section 5. Never add an unbounded key.
- **Outcome and reason values ([#213](https://github.com/TailTag-Game/tailtag/issues/213)):** populate `_OUTCOMES` and `_REASONS` in `privacy.py`. Each value must be a member of the enumeration in the outcomes module, and the two must not drift.
- **New text shape:** add a pattern to `_TEXT_REDACTIONS` only for a shape that is unmistakable. Prefer a Semgrep rule for anything ambiguous.
- **New third-party logger cap:** add the logger name to `_QUIET_THIRD_PARTY_LOGGERS` in `logging.py`. `config/settings/production.py` adds stricter botocore, boto3, and s3transfer entries on top of these caps; settings must extend the base `loggers`, never replace them.
- **New span or breadcrumb data key that can hold a URL or SQL value:** extend `scrub_url_data` in `privacy.py`.
