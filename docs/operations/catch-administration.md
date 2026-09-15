# Catch administration and operator correction

## Overview

Catch administration provides authorized TailTag operators with visibility into confirmed catch records and an operational mechanism to remove invalid, disputed, or erroneous catches.

Catch records represent immutable gameplay facts created through player interactions. In rare operational scenarios—such as duplicate or mistaken confirmations during on-site dispute resolution—operators require a safe, auditable method to inspect and correct catch records.

## Immutable catch records

Catches cannot be manually created or edited through the Django administration interface:

- **No manual creation:** Catches can only be minted through the authoritative confirmation pipeline (`confirm_catch` in `catches.services`). Operators cannot create synthetic catches or arbitrary awards via admin.
- **No modification:** Catch attributes (`id`, `catcher_user`, `fursuit`, `convention`, `activation`, `catch_session`, and `caught_at`) are read-only. Gameplay provenance cannot be altered after the fact.
- **Bulk actions disabled:** Standard Django admin bulk actions (including bulk delete) are explicitly removed (`actions = None`, `delete_queryset` raises `PermissionDenied`). Each correction must be reviewed and executed individually.

## Permission boundary and operator authorization

Access to the Catch administration interface is restricted to authorized deletion operators:

- **Staff and superuser authorization:** Access requires an authenticated staff user (`is_staff=True`) with explicit `catches.delete_catch` model permission or superuser status.
- **Inspection tied to deletion authority:** Catch inspection (`has_view_permission`) strictly requires `has_delete_permission`. Staff users with only `catches.view_catch` permission are denied access to prevent unauthorized inspection of gameplay catches.
- **Player access barred:** Non-staff player accounts and unauthenticated requests are denied access and redirected to login.

## Safe search and inspection workflows

Operators locate catch records using safe, non-sensitive search identifiers:

- **Supported search fields:**
  - Catch ID (exact match)
  - Catcher user ID (exact internal integer ID)
  - Catcher Clerk user ID (e.g., `user_...`)
  - Fursuit name (substring match)
  - Fursuit TailTag ID (exact UUID string, e.g. `3fa85f64-5717-4562-b3fc-2c963f66afa6`)
  - Convention name (substring match)

### Sensitive credential protection, query sanitization, and logging boundaries

Raw QR catch credentials and payload strings (e.g., `tailtag:catch:v1:...`) represent short-lived secrets. Operators must never query credential tokens, store them in operational notes, or enter them into browser address bars.

The privacy and sanitization guarantees are divided into application-controlled technical controls and an operational perimeter boundary:

#### Application-controlled guarantees

1. **Client-side submission prevention:** The admin changelist template (`admin/catches/catch/change_list.html`) attaches an active guard to `#changelist-search`. If any input field contains a pattern matching a sensitive QR catch credential token (`CATCH_CREDENTIAL_TOKEN_PATTERN`), client-side JavaScript intercepts the submit event (`event.preventDefault()`), clears the input field, and alerts the operator. This ensures standard operator searches never transmit credential tokens across the wire as HTTP GET query strings.
2. **Server-side multi-parameter sanitization and redirect:** If a credential-bearing GET request reaches Django (e.g. from direct URL navigation, automated scripts, or with JavaScript disabled), `CatchAdmin.changelist_view` scans all query parameters (keys and values). If any sensitive credential token is detected, Django immediately issues an HTTP 302 redirect (`HttpResponseRedirect`) to a sanitized URL:
   - Sensitive search values under `q` are replaced with `__tailtag_admin_credential_query_redacted__`.
   - Any additional or arbitrary query parameters containing sensitive tokens (such as `?foo=<token>` or `?<token>=value`) are stripped and dropped entirely.
   - Non-sensitive parameters (such as convention or timestamp filters) are preserved.
   This redirect replaces the browser's address bar and history, preventing downstream same-origin navigation from leaking credential tokens via `Referer` headers.
3. **Application and container logging boundaries:**
   - **Django structured logging:** Application audit logging (including operator deletion logs) logs only internal entity IDs and never dumps raw GET query strings.
   - **Gunicorn container runtime:** In production, Gunicorn is invoked without `--access-logfile` (`CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]`). Gunicorn does not emit HTTP request-line access logs to container stdout or stderr, ensuring container runtime logs in Railway do not capture query parameters.

#### Railway edge HTTP-log boundary and operational constraint

- **Documented Railway HTTP-log shape:** Railway's maintained
  [`railway logs` documentation](https://docs.railway.com/cli/logs#http-logs)
  describes edge HTTP logs as separate structured fields, including `method`,
  `path`, status, timing, and request ID. It documents no query-string, URL, or
  request-target field. This is distinct from application and container logs.
- **Verified Railway Development behavior:** On 2026-09-15, a direct GET to the
  deployed Catch admin changelist used a unique non-secret user agent and a
  synthetic 43-character value under `q` that matched
  `CATCH_CREDENTIAL_TOKEN_PATTERN`. The request returned HTTP 302. The single
  matching record retrieved with `railway logs --http --json` reported `GET
  /admin/catches/catch/`, status 302, and the documented HTTP metadata fields;
  it contained neither the synthetic value nor any query-related field. The
  synthetic value was not copied into durable evidence.
- **Supported guarantee:** On the verified Railway Development edge HTTP-log
  surface, the query string is not included in or exposed by the documented
  HTTP-log record: the `path` field contains only `/admin/catches/catch/`. This
  evidence supports the no-raw-credential-log requirement for Railway's
  documented, operator-visible edge HTTP logs. It does not claim visibility
  into undocumented Railway-internal telemetry; any future schema or platform-
  behavior change requires the check to be repeated before making a broader
  guarantee.
- **Operational rule:** Edge-log omission is defense in depth, not permission to
  transmit credentials in URLs. Operators must never manually craft, bookmark,
  or navigate to direct GET URLs containing raw QR credential tokens or payload
  strings. Catch inspection must always use the supported safe identifiers
  (Catch ID, Catcher user ID, Clerk ID, Fursuit name, Fursuit TailTag UUID, or
  Convention name) submitted through the admin changelist search form.

## Operator correction and deletion

When a catch is confirmed to be invalid or disputed, authorized staff operators can remove it through the individual object delete view in Django admin.

### Atomic execution and data integrity

Catch removal is executed by `remove_catch_as_operator` in `catches.services`:

1. **Transaction isolation and row locking:** Execution occurs within an atomic transaction (`transaction.atomic()`). The target `Catch` row is locked with `select_for_update()`.
2. **Referential integrity:** The `Catch` model references foreign keys (`catcher_user`, `fursuit`, `convention`, `activation`, `catch_session`) with `on_delete=models.PROTECT`. Deleting the `Catch` removes only the catch event itself; upstream accounts, fursuits, activations, and convention records remain untouched and intact.
3. **Committed audit logging:** Following deletion, a structured audit log entry is registered with `transaction.on_commit()`:
   ```text
   Operator removed catch <catch_id> (catcher_user_id=<user_id>, fursuit_id=<fursuit_id>, convention_id=<convention_id>, activation_id=<activation_id>, catch_session_id=<session_id>).
   ```
   Because it is registered with `transaction.on_commit()`, the log is emitted only after the transaction commits successfully. The audit log contains only internal database identifiers and never includes secrets, tokens, or credential payloads.
