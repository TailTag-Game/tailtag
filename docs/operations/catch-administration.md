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

#### Upstream ingress boundary and operational constraint

- **Edge ingress limitation:** Upstream infrastructure—specifically Railway's edge reverse proxy—receives and logs inbound HTTP request lines at the network perimeter before traffic reaches the container runtime or application code. Application-level logic (such as Django's 302 redirect) cannot prevent an edge reverse proxy from logging a request line for a request that has already been dispatched over the network.
- **Operational rule:** Because client-side JavaScript interception is the active barrier against transmitting credentials to edge ingress, **operators must never manually craft, bookmark, or navigate to direct GET URLs containing raw QR credential tokens or payload strings**. Catch inspection must always be conducted using the supported safe identifiers (Catch ID, Catcher user ID, Clerk ID, Fursuit name, Fursuit TailTag UUID, or Convention name) submitted through the admin changelist search form.

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
